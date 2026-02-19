"""
Rotas de Analytics — consulta e feedback dos dados coletados.

Endpoints:
    GET  /analytics/summary               → Resumo geral de uma automação
    GET  /analytics/ai-history            → Histórico de gerações de IA
    POST /analytics/ai-feedback/{id}      → Vincular métricas reais a uma geração de IA
    GET  /analytics/ab-results            → Resultados consolidados de testes A/B
    GET  /analytics/optimizer-actions     → Ações executadas pelo otimizador
    GET  /analytics/errors                → Erros e rejeições registrados
    GET  /analytics/metrics-history       → Série histórica de métricas de uma campanha
    POST /analytics/metrics-snapshot      → Salvar snapshot manual de métricas
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.api_key import APIKeyHeader
from fastapi import Security
from pydantic import BaseModel
from typing import Optional, Any

from app.repositories.analytics_repository import AnalyticsRepository
from app.models.schemas import APIResponse
from app.core.config import get_settings
from app.utils.logger import get_logger

logger   = get_logger(__name__)
settings = get_settings()
router   = APIRouter()
analytics = AnalyticsRepository()

# ── Auth ──────────────────────────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida.")
    return api_key


# ── Schemas de entrada ────────────────────────────────────────────────────────

class AIFeedbackPayload(BaseModel):
    metrics: dict[str, Any]
    performance_score: Optional[float] = None


class MetricsSnapshotPayload(BaseModel):
    automacao_id: str
    campaign_id: str
    metrics: dict[str, Any]
    ad_id: Optional[str] = None
    adset_id: Optional[str] = None


class AdErrorPayload(BaseModel):
    automacao_id: str
    error_type: str
    error_code: Optional[int] = None
    error_message: str
    context: dict[str, Any] = {}
    ad_id: Optional[str] = None
    campaign_id: Optional[str] = None


# =============================================================================
# RESUMO GERAL
# =============================================================================

@router.get(
    "/analytics/summary",
    summary="Resumo de analytics de uma automação",
    tags=["Analytics"],
)
async def get_analytics_summary(
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Retorna indicadores agregados: total de gerações de IA, taxa de override,
    testes A/B avaliados, ações do otimizador e erros registrados.
    """
    try:
        data = analytics.get_summary(automacao_id)
        return APIResponse(success=True, message="Resumo gerado.", data=data)
    except Exception as exc:
        logger.error(f"Erro em get_analytics_summary: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# HISTÓRICO DE GERAÇÕES DE IA
# =============================================================================

@router.get(
    "/analytics/ai-history",
    summary="Histórico de gerações de IA",
    tags=["Analytics"],
)
async def list_ai_history(
    automacao_id: Optional[str] = Query(None, description="Filtrar por automação"),
    generation_type: Optional[str] = Query(None, description="copy | audience | image | full_ad"),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Lista todas as gerações de IA com contexto, output e campos que foram
    sobrescritos manualmente pelo usuário.

    Campos importantes para análise:
    - `ai_fields_generated`: o que a IA gerou
    - `user_overrode_fields`: o que o usuário substituiu (sinal de qualidade da IA)
    - `metrics`: métricas reais vinculadas após o anúncio rodar (via /ai-feedback)
    """
    try:
        data = analytics.list_ai_generations(
            automacao_id=automacao_id,
            generation_type=generation_type,
            limit=limit,
        )
        return APIResponse(
            success=True,
            message=f"{len(data)} geração(ões) encontrada(s).",
            data=data,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/analytics/ai-feedback/{doc_id}",
    summary="Vincular métricas reais a uma geração de IA",
    tags=["Analytics"],
)
async def update_ai_feedback(
    doc_id: str,
    payload: AIFeedbackPayload,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Vincula as métricas reais de um anúncio ao registro de geração de IA.

    Chame este endpoint depois de coletar insights da Meta API para o anúncio
    gerado. Com o tempo, isso cria um banco de dados de "copy IA → resultado real",
    permitindo otimizar os prompts.

    O `doc_id` é retornado em `analytics.ai_history_id` no response de
    `POST /ai/create-full-ad`.
    """
    try:
        analytics.update_ai_generation_metrics(
            doc_id=doc_id,
            metrics=payload.metrics,
            performance_score=payload.performance_score,
        )
        return APIResponse(
            success=True,
            message="Feedback de métricas vinculado à geração de IA.",
            data={"doc_id": doc_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# RESULTADOS DE TESTES A/B
# =============================================================================

@router.get(
    "/analytics/ab-results",
    summary="Resultados consolidados de testes A/B",
    tags=["Analytics"],
)
async def list_ab_results(
    automacao_id: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Lista os resultados avaliados de testes A/B com vencedor, abordagem de copy
    e delta de performance. Útil para identificar quais tipos de copy convertem mais.
    """
    try:
        data = analytics.list_ab_results(automacao_id=automacao_id, limit=limit)
        return APIResponse(
            success=True,
            message=f"{len(data)} resultado(s) de A/B encontrado(s).",
            data=data,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# AÇÕES DO OTIMIZADOR
# =============================================================================

@router.get(
    "/analytics/optimizer-actions",
    summary="Histórico de ações do otimizador",
    tags=["Analytics"],
)
async def list_optimizer_actions(
    automacao_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Lista todas as ações executadas pelo otimizador: pausas, ajustes de orçamento
    e notificações. Inclui também ações em modo dry_run.
    """
    try:
        data = analytics.list_optimizer_actions(
            automacao_id=automacao_id,
            campaign_id=campaign_id,
            limit=limit,
        )
        return APIResponse(
            success=True,
            message=f"{len(data)} ação(ões) do otimizador encontrada(s).",
            data=data,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# ERROS E REJEIÇÕES
# =============================================================================

@router.get(
    "/analytics/errors",
    summary="Erros e rejeições registrados",
    tags=["Analytics"],
)
async def list_errors(
    automacao_id: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None, description="meta_api_error | ad_rejected | rate_limit"),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Lista erros da Meta API e rejeições de anúncios para análise de padrões."""
    try:
        data = analytics.list_ad_errors(
            automacao_id=automacao_id,
            error_type=error_type,
            limit=limit,
        )
        return APIResponse(
            success=True,
            message=f"{len(data)} erro(s) encontrado(s).",
            data=data,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/analytics/errors",
    summary="Registrar erro manualmente",
    tags=["Analytics"],
)
async def record_error(
    payload: AdErrorPayload,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Registra um erro ou rejeição manualmente (para integrações externas)."""
    try:
        analytics.save_ad_error(
            automacao_id=payload.automacao_id,
            error_type=payload.error_type,
            error_code=payload.error_code,
            error_message=payload.error_message,
            context=payload.context,
            ad_id=payload.ad_id,
            campaign_id=payload.campaign_id,
        )
        return APIResponse(success=True, message="Erro registrado.", data={})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# HISTÓRICO DE MÉTRICAS (SÉRIE TEMPORAL)
# =============================================================================

@router.get(
    "/analytics/metrics-history",
    summary="Histórico de métricas de uma campanha",
    tags=["Analytics"],
)
async def get_metrics_history(
    campaign_id: str = Query(..., description="ID da campanha na Meta"),
    limit: int = Query(30, ge=1, le=100),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Retorna snapshots de métricas ao longo do tempo para uma campanha.
    Cada snapshot contém: CTR, CPC, CPM, spend, impressões, cliques.

    Use para visualizar a evolução da performance no dashboard.
    """
    try:
        data = analytics.get_metrics_history(campaign_id=campaign_id, limit=limit)
        return APIResponse(
            success=True,
            message=f"{len(data)} snapshot(s) de métricas encontrado(s).",
            data=data,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/analytics/metrics-snapshot",
    summary="Salvar snapshot de métricas",
    tags=["Analytics"],
)
async def save_metrics_snapshot(
    payload: MetricsSnapshotPayload,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Salva um snapshot de métricas manualmente.

    Chame periodicamente (ex: cron diário) para construir a série histórica
    de performance de cada campanha. Combine com `GET /campaign/{id}/insights`
    para coletar e persistir os dados automaticamente.
    """
    try:
        analytics.save_metrics_snapshot(
            automacao_id=payload.automacao_id,
            campaign_id=payload.campaign_id,
            metrics=payload.metrics,
            ad_id=payload.ad_id,
            adset_id=payload.adset_id,
        )
        return APIResponse(
            success=True,
            message="Snapshot de métricas salvo.",
            data={"campaign_id": payload.campaign_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
