"""
Camada de serviço — lógica de negócio central da aplicação.

Orquestra o fluxo completo de cada caso de uso:
    1. Validar e buscar credenciais no Firestore
    2. Inicializar Meta API com as credenciais da automação
    3. Executar operação na Meta API
    4. Persistir resultado e log no Firestore
    5. Retornar resultado formatado

Decisão técnica:
- AdsService não é singleton para facilitar testes (injeção de dependência futura)
- Separação clara: esta camada não sabe nada de HTTP (sem Request/Response do FastAPI)
- Erros da Meta API são capturados aqui e relançados como ValueError com mensagem clara
- Erros de Firestore são propagados sem tratamento (falha rápida para diagnóstico)

Multi-tenant: cada operação recebe automacao_id, que determina quais
credenciais Meta serão usadas. Isso permite que N clientes usem a mesma API.
"""

from facebook_business.exceptions import FacebookRequestError

from app.core.meta import (
    init_meta_api,
    create_campaign_meta,
    create_adset_meta,
    create_ad_meta,
    get_campaigns_meta,
    update_campaign_status_meta,
    get_campaign_insights_meta,
    update_campaign_budget_meta,
)
from app.repositories.ads_repository import AdsRepository
from app.models.schemas import (
    AutomacaoCredentials,
    CampaignCreate,
    AdSetCreate,
    AdCreate,
    BudgetUpdate,
    InsightQuery,
)
from app.utils.logger import get_logger
from typing import Any

logger = get_logger(__name__)
repository = AdsRepository()


class AdsService:
    """
    Serviço principal de automação de anúncios Meta.

    Cada método público representa um caso de uso completo e atômico.
    Em caso de falha na Meta API, o log de erro é sempre persistido no Firestore.
    """

    # =========================================================================
    # HELPERS PRIVADOS
    # =========================================================================

    def _get_automacao(self, automacao_id: str) -> dict[str, Any]:
        """
        Busca e valida a existência de uma automação no Firestore.
        Lança ValueError se não encontrada — evita operações com credenciais ausentes.
        """
        automacao = repository.get_automacao(automacao_id)
        if not automacao:
            raise ValueError(
                f"Automação '{automacao_id}' não encontrada. "
                "Registre a automação via POST /api/v1/automacao antes de operar."
            )
        return automacao

    def _init_meta(self, automacao_id: str) -> dict[str, Any]:
        """
        Busca credenciais no Firestore e inicializa a Meta API para essa automação.
        Retorna o documento da automação para uso nos campos subsequentes.
        """
        automacao = self._get_automacao(automacao_id)
        init_meta_api(
            app_id=automacao["app_id"],
            app_secret=automacao["app_secret"],
            access_token=automacao["access_token"],
        )
        return automacao

    def _handle_meta_error(
        self, automacao_id: str, action: str, exc: FacebookRequestError
    ) -> None:
        """
        Formata e persiste erros da Meta API no log do Firestore.
        Sempre relança como ValueError com mensagem amigável.
        """
        code = exc.api_error_code()
        msg = exc.api_error_message()
        subcode = exc.api_error_subcode()

        # Dicas específicas por tipo de erro
        hints = {
            190: "Token inválido ou expirado. Renove o access_token.",
            100: "Parâmetro inválido. Verifique os campos enviados.",
            17: "Rate limit de usuário atingido. Aguarde antes de tentar novamente.",
            4: "Rate limit da aplicação atingido.",
            32: "Rate limit de página atingido.",
        }
        hint = hints.get(code, "Verifique os parâmetros e permissões do token.")

        error_msg = f"Meta API Error {code} (subcode={subcode}): {msg}. Dica: {hint}"
        logger.error(f"[{action}] {error_msg} | automacao_id={automacao_id}")

        repository.add_log(automacao_id, action, {}, error=error_msg)
        raise ValueError(error_msg)

    # =========================================================================
    # CASOS DE USO
    # =========================================================================

    def register_automacao(self, creds: AutomacaoCredentials) -> dict[str, Any]:
        """
        Registra ou atualiza uma automação com suas credenciais Meta.

        Operação de 'onboarding': salva as credenciais no Firestore para
        que todas as operações futuras possam buscá-las pelo automacao_id.
        """
        data = {
            "ad_account_id": creds.ad_account_id,
            "access_token": creds.access_token,
            "app_id": creds.app_id,
            "app_secret": creds.app_secret,
        }

        result = repository.upsert_automacao(creds.automacao_id, data)
        logger.info(f"Automação registrada/atualizada | id={creds.automacao_id}")

        # Remove campos sensíveis da resposta
        return {k: v for k, v in result.items() if k not in ("access_token", "app_secret")}

    def create_campaign(self, payload: CampaignCreate) -> dict[str, Any]:
        """
        Cria uma campanha na Meta API e registra o ID no Firestore.

        Fluxo:
        1. Busca credenciais no Firestore
        2. Inicializa Meta API
        3. Cria campanha
        4. Salva campaign_id no documento da automação
        5. Registra log de sucesso
        """
        try:
            automacao = self._init_meta(payload.automacao_id)

            result = create_campaign_meta(
                ad_account_id=automacao["ad_account_id"],
                name=payload.name,
                objective=payload.objective.value,
                status=payload.status.value,
                special_ad_categories=payload.special_ad_categories,
                daily_budget=payload.daily_budget,
                lifetime_budget=payload.lifetime_budget,
            )

            # Persiste o ID da campanha criada na automação
            repository.set_campaign_id(payload.automacao_id, result["id"])
            repository.add_log(payload.automacao_id, "create_campaign", result)

            logger.info(
                f"Campanha criada com sucesso | automacao={payload.automacao_id} | "
                f"campaign_id={result['id']}"
            )
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(payload.automacao_id, "create_campaign", exc)

    def create_adset(self, payload: AdSetCreate) -> dict[str, Any]:
        """Cria um Ad Set vinculado a uma campanha existente."""
        try:
            automacao = self._init_meta(payload.automacao_id)

            result = create_adset_meta(
                ad_account_id=automacao["ad_account_id"],
                campaign_id=payload.campaign_id,
                name=payload.name,
                daily_budget=payload.daily_budget,
                billing_event=payload.billing_event.value,
                optimization_goal=payload.optimization_goal.value,
                targeting=payload.targeting,
                status=payload.status.value,
                start_time=payload.start_time,
                end_time=payload.end_time,
            )

            repository.add_log(payload.automacao_id, "create_adset", result)
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(payload.automacao_id, "create_adset", exc)

    def create_ad(self, payload: AdCreate) -> dict[str, Any]:
        """Cria um anúncio (Ad) vinculado a um Ad Set."""
        try:
            automacao = self._init_meta(payload.automacao_id)

            result = create_ad_meta(
                ad_account_id=automacao["ad_account_id"],
                adset_id=payload.adset_id,
                name=payload.name,
                creative=payload.creative,
                status=payload.status.value,
            )

            repository.add_log(payload.automacao_id, "create_ad", result)
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(payload.automacao_id, "create_ad", exc)

    def get_campaigns(self, automacao_id: str) -> list[dict[str, Any]]:
        """Lista todas as campanhas da conta de anúncios da automação."""
        try:
            automacao = self._init_meta(automacao_id)
            campaigns = get_campaigns_meta(automacao["ad_account_id"])

            repository.add_log(automacao_id, "list_campaigns", {"count": len(campaigns)})
            return campaigns

        except FacebookRequestError as exc:
            self._handle_meta_error(automacao_id, "list_campaigns", exc)

    def pause_campaign(self, automacao_id: str, campaign_id: str) -> dict[str, Any]:
        """
        Pausa uma campanha e atualiza o status da automação no Firestore.
        """
        try:
            self._init_meta(automacao_id)
            result = update_campaign_status_meta(campaign_id, "PAUSED")

            repository.set_status(automacao_id, "paused")
            repository.add_log(automacao_id, "pause_campaign", result)
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(automacao_id, "pause_campaign", exc)

    def activate_campaign(self, automacao_id: str, campaign_id: str) -> dict[str, Any]:
        """
        Ativa uma campanha pausada e atualiza o status da automação.
        """
        try:
            self._init_meta(automacao_id)
            result = update_campaign_status_meta(campaign_id, "ACTIVE")

            repository.set_status(automacao_id, "active")
            repository.add_log(automacao_id, "activate_campaign", result)
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(automacao_id, "activate_campaign", exc)

    def get_insights(
        self,
        automacao_id: str,
        campaign_id: str,
        query: InsightQuery,
    ) -> dict[str, Any]:
        """
        Obtém métricas de uma campanha e atualiza o snapshot no Firestore.
        O snapshot permite visualizar as últimas métricas sem nova chamada à API.
        """
        try:
            self._init_meta(automacao_id)
            insights = get_campaign_insights_meta(
                campaign_id=campaign_id,
                date_preset=query.date_preset.value,
                fields=query.fields,
            )

            # Salva snapshot mesmo que vazio (indica que foi consultado)
            repository.update_metrics(automacao_id, insights)
            repository.add_log(automacao_id, "get_insights", insights)
            return insights

        except FacebookRequestError as exc:
            self._handle_meta_error(automacao_id, "get_insights", exc)

    def update_budget(
        self,
        automacao_id: str,
        campaign_id: str,
        budget: BudgetUpdate,
    ) -> dict[str, Any]:
        """Atualiza o orçamento de uma campanha."""
        try:
            self._init_meta(automacao_id)
            result = update_campaign_budget_meta(
                campaign_id=campaign_id,
                daily_budget=budget.daily_budget,
                lifetime_budget=budget.lifetime_budget,
            )

            repository.add_log(automacao_id, "update_budget", result)
            return result

        except FacebookRequestError as exc:
            self._handle_meta_error(automacao_id, "update_budget", exc)

    def list_automacoes(self, status: str | None = None) -> list[dict[str, Any]]:
        """
        Lista automações registradas no Firestore.
        Remove campos sensíveis da resposta.
        """
        automacoes = repository.list_automacoes(status=status)
        # Remove access_token e app_secret da listagem
        return [
            {k: v for k, v in a.items() if k not in ("access_token", "app_secret")}
            for a in automacoes
        ]
