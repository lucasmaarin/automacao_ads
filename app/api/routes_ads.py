"""
Camada HTTP — rotas FastAPI da API de automação de anúncios.

Responsabilidade única: receber requisições HTTP, validar entrada via schemas
Pydantic, delegar ao serviço e retornar respostas formatadas.

Não existe lógica de negócio aqui. Apenas:
    - Validação de API Key (middleware de autenticação)
    - Parsing de parâmetros (Query, Path, Body)
    - Chamada ao AdsService
    - Formatação da resposta (APIResponse)
    - Mapeamento de erros para status HTTP adequados

Decisão técnica:
- APIKeyHeader via FastAPI Security — simples e documentado automaticamente no Swagger
- HTTPException com detail claro para facilitar debug pelo consumidor da API
- Todos os endpoints retornam APIResponse para envelope consistente
- Tags no router para organizar o Swagger UI por categoria
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security.api_key import APIKeyHeader

from app.services.ads_service import AdsService
from app.models.schemas import (
    AutomacaoCredentials,
    CampaignCreate,
    AdSetCreate,
    AdCreate,
    BudgetUpdate,
    InsightQuery,
    APIResponse,
    DatePreset,
)
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()
service = AdsService()

# =============================================================================
# AUTENTICAÇÃO — API Key via header X-API-Key
# =============================================================================

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    """
    Dependência de autenticação interna via API Key.

    Verifica se o header X-API-Key corresponde à chave configurada no .env.
    Em produção com múltiplos clientes (SaaS), substitua por JWT + Firebase Auth.
    """
    if api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida. Inclua o header 'X-API-Key' com a chave correta.",
        )
    return api_key


# =============================================================================
# AUTOMAÇÕES — Onboarding de contas
# =============================================================================

@router.post(
    "/automacao",
    summary="Registrar automação",
    description="Registra ou atualiza as credenciais Meta de uma automação no Firestore.",
    tags=["Automações"],
    status_code=status.HTTP_201_CREATED,
)
async def register_automacao(
    creds: AutomacaoCredentials,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Ponto de entrada para registrar uma nova conta de anúncios no sistema.
    Deve ser chamado antes de qualquer outra operação com a automacao_id.
    """
    try:
        result = service.register_automacao(creds)
        return APIResponse(
            success=True,
            message=f"Automação '{creds.automacao_id}' registrada com sucesso.",
            data=result,
        )
    except Exception as exc:
        logger.error(f"Erro ao registrar automação: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/automacoes",
    summary="Listar automações",
    tags=["Automações"],
)
async def list_automacoes(
    status_filter: str | None = Query(None, alias="status", description="Filtrar por status (active, paused, error)"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Lista todas as automações registradas no Firestore (sem dados sensíveis)."""
    try:
        result = service.list_automacoes(status=status_filter)
        return APIResponse(
            success=True,
            message=f"{len(result)} automação(ões) encontrada(s).",
            data=result,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# =============================================================================
# CAMPANHAS
# =============================================================================

@router.post(
    "/campaign",
    summary="Criar campanha",
    tags=["Campanhas"],
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: CampaignCreate,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Cria uma campanha na Meta API e registra o resultado no Firestore.

    O campo `automacao_id` determina quais credenciais serão usadas.
    Certifique-se de registrar a automação antes via POST /automacao.
    """
    try:
        result = service.create_campaign(payload)
        return APIResponse(success=True, message="Campanha criada com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"Erro inesperado em create_campaign: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")


@router.get(
    "/campaigns",
    summary="Listar campanhas",
    tags=["Campanhas"],
)
async def get_campaigns(
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Lista todas as campanhas da conta de anúncios vinculada à automação."""
    try:
        result = service.get_campaigns(automacao_id)
        return APIResponse(
            success=True,
            message=f"{len(result)} campanha(s) encontrada(s).",
            data=result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch(
    "/campaign/{campaign_id}/pause",
    summary="Pausar campanha",
    tags=["Campanhas"],
)
async def pause_campaign(
    campaign_id: str,
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Pausa uma campanha ativa na Meta e atualiza status no Firestore."""
    try:
        result = service.pause_campaign(automacao_id, campaign_id)
        return APIResponse(success=True, message="Campanha pausada.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch(
    "/campaign/{campaign_id}/activate",
    summary="Ativar campanha",
    tags=["Campanhas"],
)
async def activate_campaign(
    campaign_id: str,
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Ativa uma campanha pausada na Meta e atualiza status no Firestore."""
    try:
        result = service.activate_campaign(automacao_id, campaign_id)
        return APIResponse(success=True, message="Campanha ativada.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/campaign/{campaign_id}/insights",
    summary="Métricas da campanha",
    tags=["Insights"],
)
async def get_insights(
    campaign_id: str,
    automacao_id: str = Query(..., description="ID da automação"),
    date_preset: str = Query(DatePreset.LAST_7D.value, description="Período das métricas"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Retorna métricas da campanha (impressões, cliques, gasto, CTR, CPM, etc.).
    O snapshot mais recente também é salvo no Firestore automaticamente.
    """
    try:
        query = InsightQuery(date_preset=date_preset)
        result = service.get_insights(automacao_id, campaign_id, query)
        return APIResponse(success=True, message="Insights obtidos.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch(
    "/campaign/{campaign_id}/budget",
    summary="Atualizar orçamento",
    tags=["Campanhas"],
)
async def update_budget(
    campaign_id: str,
    budget: BudgetUpdate,
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Atualiza o orçamento diário ou total de uma campanha."""
    try:
        result = service.update_budget(automacao_id, campaign_id, budget)
        return APIResponse(success=True, message="Orçamento atualizado.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# =============================================================================
# AD SETS
# =============================================================================

@router.post(
    "/adset",
    summary="Criar Ad Set",
    tags=["Ad Sets"],
    status_code=status.HTTP_201_CREATED,
)
async def create_adset(
    payload: AdSetCreate,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Cria um conjunto de anúncios (Ad Set) vinculado a uma campanha.

    O `targeting` deve seguir o formato da Meta API:
    ```json
    {
        "geo_locations": {"countries": ["BR"]},
        "age_min": 18,
        "age_max": 65
    }
    ```
    """
    try:
        result = service.create_adset(payload)
        return APIResponse(success=True, message="Ad Set criado com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"Erro inesperado em create_adset: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")


# =============================================================================
# ADS (ANÚNCIOS)
# =============================================================================

@router.post(
    "/ad",
    summary="Criar anúncio",
    tags=["Anúncios"],
    status_code=status.HTTP_201_CREATED,
)
async def create_ad(
    payload: AdCreate,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Cria um anúncio (Ad) vinculado a um Ad Set.

    O `creative` pode ser referência a um criativo existente:
    ```json
    {"creative_id": "123456789"}
    ```
    Ou definição inline com image_hash, message, link, etc.
    """
    try:
        result = service.create_ad(payload)
        return APIResponse(success=True, message="Anúncio criado com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"Erro inesperado em create_ad: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")
