"""
Camada de integração com a Meta Marketing API.

Responsável exclusivamente por comunicação com a API da Meta.
Nenhuma lógica de negócio aqui — apenas chamadas à API com retry.

Decisão técnica:
- facebook-business SDK oficial para máxima compatibilidade
- Inicialização dinâmica por automação (multi-tenant): cada chamada pode
  usar credenciais diferentes via FacebookAdsApi.init()
- tenacity para retry automático em erros temporários (rate limit, erros 1/2/4)
- Funções puras (sem estado) para facilitar testes e reutilização

Erros da Meta API mais comuns:
    1, 2    → Erro genérico temporário (retry)
    4       → Rate limit da aplicação
    17      → Rate limit do usuário
    32      → Rate limit de página
    100     → Parâmetro inválido
    190     → Token inválido/expirado (OAuthException)
    613     → Limite de chamadas customizado
"""

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.exceptions import FacebookRequestError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from app.core.config import get_settings
from app.utils.logger import get_logger
from typing import Any
import logging

logger = get_logger(__name__)
settings = get_settings()

# Códigos de erro da Meta que indicam problemas temporários (candidatos a retry)
RETRYABLE_ERROR_CODES = {1, 2, 4, 17, 32, 613}

# Códigos que indicam token inválido — não adianta fazer retry
OAUTH_ERROR_CODES = {190, 102, 467}


def _is_retryable(exc: Exception) -> bool:
    """Verifica se o erro da Meta API é temporário e pode ser retentado."""
    if isinstance(exc, FacebookRequestError):
        return exc.api_error_code() in RETRYABLE_ERROR_CODES
    return False


def init_meta_api(app_id: str, app_secret: str, access_token: str) -> None:
    """
    Inicializa a Meta Marketing API com credenciais específicas de uma automação.

    Chamada antes de qualquer operação na Meta API para garantir que
    as credenciais corretas estão em uso (suporte multi-tenant).

    NOTA: FacebookAdsApi.init() é global por thread. Em ambiente com múltiplos
    workers simultâneos, considere usar contextos isolados por requisição.
    """
    FacebookAdsApi.init(
        app_id=app_id,
        app_secret=app_secret,
        access_token=access_token,
        api_version=settings.META_API_VERSION,
    )
    logger.info(
        f"Meta API inicializada | app_id={app_id[:8]}... | versão={settings.META_API_VERSION}"
    )


def _normalize_account_id(ad_account_id: str) -> str:
    """Garante que o ID da conta tenha o prefixo 'act_'."""
    return ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"


# === Campanhas ===

@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def create_campaign_meta(
    ad_account_id: str,
    name: str,
    objective: str,
    status: str,
    special_ad_categories: list[str],
    daily_budget: int | None = None,
    lifetime_budget: int | None = None,
) -> dict[str, Any]:
    """
    Cria uma campanha na Meta API.
    Retry automático em erros temporários (até 3 tentativas com backoff exponencial).
    """
    account = AdAccount(_normalize_account_id(ad_account_id))

    params: dict[str, Any] = {
        Campaign.Field.name: name,
        Campaign.Field.objective: objective,
        Campaign.Field.status: status,
        Campaign.Field.special_ad_categories: special_ad_categories,
    }

    if daily_budget is not None:
        params[Campaign.Field.daily_budget] = daily_budget
    if lifetime_budget is not None:
        params[Campaign.Field.lifetime_budget] = lifetime_budget

    campaign = account.create_campaign(
        fields=[Campaign.Field.id, Campaign.Field.name, Campaign.Field.status],
        params=params,
    )

    logger.info(f"Campanha criada na Meta | id={campaign['id']} | nome={name}")
    return {"id": campaign["id"], "name": name, "status": status}


@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def get_campaigns_meta(ad_account_id: str) -> list[dict[str, Any]]:
    """Lista todas as campanhas de uma conta de anúncios."""
    account = AdAccount(_normalize_account_id(ad_account_id))

    campaigns = account.get_campaigns(
        fields=[
            Campaign.Field.id,
            Campaign.Field.name,
            Campaign.Field.status,
            Campaign.Field.objective,
            Campaign.Field.daily_budget,
            Campaign.Field.lifetime_budget,
            Campaign.Field.created_time,
            Campaign.Field.start_time,
            Campaign.Field.stop_time,
        ]
    )

    result = [dict(c) for c in campaigns]
    logger.info(f"Campanhas listadas | conta={ad_account_id} | total={len(result)}")
    return result


@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def update_campaign_status_meta(campaign_id: str, status: str) -> dict[str, Any]:
    """Atualiza o status de uma campanha (ACTIVE ou PAUSED)."""
    campaign = Campaign(campaign_id)
    campaign.api_update(params={Campaign.Field.status: status})

    logger.info(f"Status da campanha atualizado | id={campaign_id} | status={status}")
    return {"id": campaign_id, "status": status}


@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def update_campaign_budget_meta(
    campaign_id: str,
    daily_budget: int | None = None,
    lifetime_budget: int | None = None,
) -> dict[str, Any]:
    """Atualiza o orçamento de uma campanha."""
    campaign = Campaign(campaign_id)
    params: dict[str, Any] = {}

    if daily_budget is not None:
        params[Campaign.Field.daily_budget] = daily_budget
    if lifetime_budget is not None:
        params[Campaign.Field.lifetime_budget] = lifetime_budget

    if not params:
        raise ValueError("Nenhum orçamento fornecido para atualização.")

    campaign.api_update(params=params)
    logger.info(f"Budget atualizado | id={campaign_id} | params={params}")
    return {"id": campaign_id, **params}


@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def get_campaign_insights_meta(
    campaign_id: str,
    date_preset: str,
    fields: list[str],
) -> dict[str, Any]:
    """
    Obtém insights (métricas) de uma campanha.
    Retorna dict vazio se não houver dados para o período solicitado.
    """
    campaign = Campaign(campaign_id)
    insights = campaign.get_insights(
        params={"date_preset": date_preset},
        fields=fields,
    )

    if insights:
        data = dict(insights[0])
        logger.info(f"Insights obtidos | campaign_id={campaign_id} | preset={date_preset}")
        return data

    logger.warning(f"Sem dados de insights | campaign_id={campaign_id} | preset={date_preset}")
    return {}


# === Ad Sets ===

@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def create_adset_meta(
    ad_account_id: str,
    campaign_id: str,
    name: str,
    daily_budget: int,
    billing_event: str,
    optimization_goal: str,
    targeting: dict[str, Any],
    status: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Cria um Ad Set vinculado a uma campanha."""
    account = AdAccount(_normalize_account_id(ad_account_id))

    params: dict[str, Any] = {
        AdSet.Field.name: name,
        AdSet.Field.campaign_id: campaign_id,
        AdSet.Field.daily_budget: daily_budget,
        AdSet.Field.billing_event: billing_event,
        AdSet.Field.optimization_goal: optimization_goal,
        AdSet.Field.targeting: targeting,
        AdSet.Field.status: status,
    }

    if start_time:
        params[AdSet.Field.start_time] = start_time
    if end_time:
        params[AdSet.Field.end_time] = end_time

    adset = account.create_ad_set(
        fields=[AdSet.Field.id, AdSet.Field.name, AdSet.Field.status],
        params=params,
    )

    logger.info(f"AdSet criado na Meta | id={adset['id']} | nome={name}")
    return {"id": adset["id"], "name": name, "campaign_id": campaign_id, "status": status}


# === Ads ===

@retry(
    retry=retry_if_exception_type(FacebookRequestError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def create_ad_meta(
    ad_account_id: str,
    adset_id: str,
    name: str,
    creative: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    """Cria um anúncio (Ad) vinculado a um Ad Set."""
    account = AdAccount(_normalize_account_id(ad_account_id))

    params: dict[str, Any] = {
        Ad.Field.name: name,
        Ad.Field.adset_id: adset_id,
        Ad.Field.creative: creative,
        Ad.Field.status: status,
    }

    ad = account.create_ad(
        fields=[Ad.Field.id, Ad.Field.name, Ad.Field.status],
        params=params,
    )

    logger.info(f"Ad criado na Meta | id={ad['id']} | nome={name}")
    return {"id": ad["id"], "name": name, "adset_id": adset_id, "status": status}
