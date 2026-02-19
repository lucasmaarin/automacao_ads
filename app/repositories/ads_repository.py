"""
Camada de persistência — acesso exclusivo ao Firestore.

O Repository isola completamente o acesso ao banco de dados do resto da aplicação.
Nenhuma lógica de negócio aqui — apenas operações CRUD no Firestore.

Decisão técnica:
- Classe AdsRepository (não singleton) para facilitar testes com mock
- Métodos atômicos e focados: cada método faz uma coisa só
- Log de auditoria como array limitado (100 entradas) para não inflar o documento
- Uso de FieldFilter para compatibilidade com Firestore SDK v6+

Estrutura Firestore:
    quartel/automacao_ads/automacoes/{automacao_id}
    └── automacao_id: str
    └── ad_account_id: str
    └── access_token: str       ← Em produção, usar Secret Manager
    └── app_id: str
    └── app_secret: str         ← Em produção, usar Secret Manager
    └── campaign_id: str        ← Última campanha criada
    └── status: str             ← active | paused | error
    └── created_at: timestamp
    └── updated_at: timestamp
    └── logs: array             ← Histórico de ações (máx 100)
    └── metrics_snapshot: dict  ← Último snapshot de métricas
"""

from datetime import datetime, timezone
from typing import Optional, Any
from google.cloud.firestore import CollectionReference, DocumentReference
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.firebase import get_automacoes_ref
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Limite de entradas no array de logs para evitar documentos muito grandes.
# Firestore tem limite de 1MB por documento.
MAX_LOG_ENTRIES = 100


class AdsRepository:
    """
    Repositório de automações no Firestore.

    Centraliza todas as operações de leitura e escrita de automações.
    Pode ser injetado em qualquer serviço ou instanciado diretamente.
    """

    def _collection(self) -> CollectionReference:
        """Retorna a referência da subcoleção de automações."""
        return get_automacoes_ref()

    def _doc(self, automacao_id: str) -> DocumentReference:
        """Retorna referência do documento de uma automação específica."""
        return self._collection().document(automacao_id)

    # =========================================================================
    # CRUD
    # =========================================================================

    def create_automacao(self, automacao_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Cria um novo documento de automação no Firestore.

        ATENÇÃO: access_token e app_secret são armazenados no Firestore.
        Em produção com dados sensíveis de clientes, migre para Google Secret Manager
        e armazene apenas referências (ex: secret_name) no Firestore.
        """
        now = datetime.now(timezone.utc)
        document = {
            "automacao_id": automacao_id,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "campaign_id": None,
            "logs": [],
            "metrics_snapshot": None,
            **data,
        }

        self._doc(automacao_id).set(document)
        logger.info(f"Automação criada | id={automacao_id}")
        return document

    def get_automacao(self, automacao_id: str) -> Optional[dict[str, Any]]:
        """
        Busca uma automação pelo ID.
        Retorna None se o documento não existir (sem lançar exceção).
        """
        doc = self._doc(automacao_id).get()
        if doc.exists:
            return doc.to_dict()
        logger.warning(f"Automação não encontrada | id={automacao_id}")
        return None

    def update_automacao(self, automacao_id: str, fields: dict[str, Any]) -> None:
        """
        Atualiza campos específicos de uma automação existente.
        Sempre atualiza o campo updated_at automaticamente.
        """
        fields["updated_at"] = datetime.now(timezone.utc)
        self._doc(automacao_id).update(fields)
        logger.info(f"Automação atualizada | id={automacao_id} | campos={list(fields.keys())}")

    def upsert_automacao(self, automacao_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Cria uma automação se não existir, ou atualiza se já existir.
        Operação idempotente — seguro para chamar múltiplas vezes.
        """
        existing = self.get_automacao(automacao_id)
        if existing:
            self.update_automacao(automacao_id, data)
            # Retorna o documento mesclado com os novos dados
            return {**existing, **data, "updated_at": datetime.now(timezone.utc)}
        return self.create_automacao(automacao_id, data)

    def delete_automacao(self, automacao_id: str) -> None:
        """Remove um documento de automação do Firestore."""
        self._doc(automacao_id).delete()
        logger.info(f"Automação deletada | id={automacao_id}")

    # =========================================================================
    # OPERAÇÕES ESPECÍFICAS
    # =========================================================================

    def set_campaign_id(self, automacao_id: str, campaign_id: str) -> None:
        """
        Registra o ID da última campanha criada para esta automação.
        Mantém rastreabilidade de qual campanha pertence a cada automação.
        """
        self.update_automacao(automacao_id, {"campaign_id": campaign_id})

    def set_status(self, automacao_id: str, status: str) -> None:
        """Atualiza o status operacional da automação (active, paused, error)."""
        self.update_automacao(automacao_id, {"status": status})

    def update_metrics(self, automacao_id: str, metrics: dict[str, Any]) -> None:
        """
        Atualiza o snapshot de métricas mais recentes da automação.
        Adiciona timestamp ao snapshot para rastreabilidade temporal.
        """
        metrics_with_ts = {
            **metrics,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }
        self.update_automacao(automacao_id, {"metrics_snapshot": metrics_with_ts})
        logger.info(f"Métricas atualizadas | id={automacao_id}")

    def add_log(
        self,
        automacao_id: str,
        action: str,
        result: dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """
        Adiciona uma entrada de auditoria ao array de logs do documento.

        Mantém um máximo de MAX_LOG_ENTRIES logs para evitar crescimento
        ilimitado do documento (limite de 1MB no Firestore).

        Estratégia: sliding window — remove os mais antigos quando necessário.
        """
        log_entry = {
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "error": error,
        }

        doc_ref = self._doc(automacao_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Tentou adicionar log em automação inexistente | id={automacao_id}")
            return

        current_logs: list = doc.to_dict().get("logs", [])

        # Sliding window: mantém os últimos (MAX_LOG_ENTRIES - 1) + o novo
        trimmed_logs = current_logs[-(MAX_LOG_ENTRIES - 1):] if len(current_logs) >= MAX_LOG_ENTRIES else current_logs
        new_logs = trimmed_logs + [log_entry]

        doc_ref.update({
            "logs": new_logs,
            "updated_at": datetime.now(timezone.utc),
        })
        logger.info(f"Log de auditoria adicionado | id={automacao_id} | ação={action}")

    # =========================================================================
    # QUERIES
    # =========================================================================

    def list_automacoes(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Lista todas as automações com filtro opcional por status.
        Usa FieldFilter para compatibilidade com Firestore SDK v6+.
        """
        query = self._collection()

        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        docs = query.stream()
        result = [doc.to_dict() for doc in docs]
        logger.info(f"Automações listadas | total={len(result)} | filtro_status={status}")
        return result
