"""
Inicialização e gerenciamento do Firebase Admin SDK.

Usa o padrão Singleton para evitar múltiplas inicializações do app Firebase,
o que causaria erros de "app already exists" em reinicializações acidentais.

Estrutura Firestore utilizada:
    quartel/                         ← Collection
        automacao_ads/               ← Document (namespace)
            automacoes/              ← Subcollection
                {automacao_id}/      ← Document de cada automação

Decisão técnica: usar Service Account JSON (automacoes-royal-x.json)
em vez de GOOGLE_APPLICATION_CREDENTIALS para maior controle e portabilidade.
"""

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client, CollectionReference
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Singleton do cliente Firestore — inicializado uma única vez
_db: Client | None = None


def init_firebase() -> None:
    """
    Inicializa o Firebase Admin SDK com a service account.
    Chamado no startup da aplicação (lifespan do FastAPI).
    Seguro para chamar múltiplas vezes — verifica se já foi inicializado.
    """
    if firebase_admin._apps:
        logger.info("Firebase já inicializado — ignorando reinicialização.")
        return

    try:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
        logger.info(
            f"Firebase Admin SDK inicializado | projeto={settings.FIREBASE_PROJECT_ID}"
        )
    except FileNotFoundError:
        logger.error(
            f"Arquivo de credenciais não encontrado: {settings.FIREBASE_CREDENTIALS_PATH}"
        )
        raise
    except Exception as e:
        logger.error(f"Falha ao inicializar Firebase: {e}")
        raise


def get_db() -> Client:
    """
    Retorna o cliente Firestore (Singleton).
    Garante que o Firebase esteja inicializado antes de criar o cliente.
    """
    global _db
    if _db is None:
        # Caso o get_db seja chamado antes do startup (ex: testes),
        # garante que o Firebase seja inicializado.
        if not firebase_admin._apps:
            init_firebase()
        _db = firestore.client()
        logger.info("Cliente Firestore instanciado.")
    return _db


def get_automacoes_ref() -> CollectionReference:
    """
    Retorna referência da subcoleção de automações no Firestore.

    Path: quartel/{AUTOMACAO_DOC}/automacoes
    Ex:   quartel/automacao_ads/automacoes

    Centralizado aqui para garantir consistência de path em todo o sistema.
    Se o path precisar mudar, altera-se apenas aqui.
    """
    db = get_db()
    return (
        db.collection(settings.FIRESTORE_QUARTEL_COLLECTION)
        .document(settings.FIRESTORE_AUTOMACAO_DOC)
        .collection(settings.FIRESTORE_AUTOMACOES_SUBCOLLECTION)
    )
