"""
Configurações centralizadas da aplicação via Pydantic Settings.

Todas as variáveis sensíveis são lidas do arquivo .env.
Nunca hardcode credenciais no código-fonte.

Decisão técnica: pydantic-settings garante tipagem forte nas configs
e falha na inicialização se variáveis obrigatórias estiverem ausentes.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # === Aplicação ===
    APP_ENV: str = "development"
    APP_NAME: str = "AutomacaoAds"
    APP_VERSION: str = "1.0.0"

    # Chave para autenticação interna via header X-API-Key
    API_SECRET_KEY: str = "changeme-in-production"

    # === Firebase ===
    FIREBASE_CREDENTIALS_PATH: str = "automacoes-royal-x.json"
    FIREBASE_PROJECT_ID: str = "automacoes-royal-x"

    # === Meta API ===
    # Versão da Graph API — manter sempre atualizado
    META_API_VERSION: str = "v20.0"

    # === Estrutura Firestore ===
    # Path final: quartel/automacao_ads/automacoes/{automacao_id}
    FIRESTORE_QUARTEL_COLLECTION: str = "quartel"
    FIRESTORE_AUTOMACAO_DOC: str = "automacao_ads"
    FIRESTORE_AUTOMACOES_SUBCOLLECTION: str = "automacoes"

    # === OpenAI / IA ===
    OPENAI_API_KEY: str = ""
    AI_TEXT_MODEL: str = "gpt-4o"          # Modelo de texto (GPT-4o recomendado)
    AI_IMAGE_MODEL: str = "dall-e-3"       # Modelo de imagem

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",        # Permite variáveis extras no .env sem erro
        case_sensitive=False,  # Variáveis podem ser maiúsculas ou minúsculas
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton das configurações usando cache de função.
    Garante que o .env seja lido apenas uma vez durante toda a execução.
    """
    return Settings()
