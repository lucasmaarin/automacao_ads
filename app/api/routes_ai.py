"""
Rotas de IA, A/B Testing e Otimização Automática.

Endpoints neste módulo:

  IA — Geração de conteúdo:
    POST /ai/generate-copy        → Gera copy (headline, texto, CTA)
    POST /ai/generate-audience    → Gera segmentação de público
    POST /ai/generate-image       → Gera imagem com DALL-E 3
    POST /ai/create-full-ad       → Cria campanha + adset + ad completo com IA

  A/B Testing:
    POST /ab-test/create          → Cria teste com variantes manuais
    POST /ab-test/create-with-ai  → Cria teste com variantes geradas pela IA
    GET  /ab-test/{id}            → Detalhes de um teste
    GET  /ab-tests                → Lista testes de uma automação
    POST /ab-test/{id}/evaluate   → Avalia teste e determina vencedor

  Otimização Automática:
    POST /optimize                → Executa otimização com regras customizadas
    GET  /optimize/presets        → Retorna presets de regras prontas
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from fastapi import Security

from app.services.ai_service import AIService
from app.services.ads_service import AdsService
from app.services.ab_service import ABTestService
from app.services.optimizer_service import OptimizerService
from app.core.meta import (
    init_meta_api,
    create_campaign_meta,
    create_adset_meta,
    create_ad_meta,
)
from app.repositories.ads_repository import AdsRepository
from app.models.schemas import (
    AIGenerateCopyRequest,
    AIGenerateAudienceRequest,
    AIGenerateImageRequest,
    AICreateFullAdRequest,
    ABTestCreate,
    ABTestGenerateRequest,
    OptimizeRequest,
    APIResponse,
    CampaignStatus,
)
from app.core.config import get_settings
from app.utils.logger import get_logger
from typing import Any

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()
ai_service      = AIService()
ads_service     = AdsService()
ab_service      = ABTestService()
optimizer       = OptimizerService()
repository      = AdsRepository()

# ── Auth ──────────────────────────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida.")
    return api_key


# =============================================================================
# IA — GERAÇÃO DE COPY
# =============================================================================

@router.post(
    "/ai/generate-copy",
    summary="Gerar copy com IA",
    tags=["IA — Geração"],
)
async def generate_copy(
    payload: AIGenerateCopyRequest,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Gera copy completo para anúncio usando GPT-4o.

    Retorna: headline, primary_text, description, cta, image_prompt, campaign_name.
    Todo o conteúdo pode ser editado antes de usar.
    """
    try:
        result = ai_service.generate_copy(payload.context)
        return APIResponse(success=True, message="Copy gerado com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# IA — GERAÇÃO DE AUDIÊNCIA
# =============================================================================

@router.post(
    "/ai/generate-audience",
    summary="Gerar segmentação de público com IA",
    tags=["IA — Geração"],
)
async def generate_audience(
    payload: AIGenerateAudienceRequest,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Converte descrição do público em targeting spec da Meta API usando GPT-4o.

    Retorna spec pronto para usar no campo `targeting` do Ad Set,
    além de sugestões de interesses para enriquecer a segmentação.
    """
    try:
        result = ai_service.generate_audience(payload.context)
        return APIResponse(success=True, message="Segmentação gerada com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# IA — GERAÇÃO DE IMAGEM
# =============================================================================

@router.post(
    "/ai/generate-image",
    summary="Gerar imagem com DALL-E 3",
    tags=["IA — Geração"],
)
async def generate_image(
    payload: AIGenerateImageRequest,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Gera imagem profissional para anúncio usando DALL-E 3.

    Retorna URL temporária da imagem (~1 hora de validade).
    Baixe e hospede a imagem para uso permanente no Meta Ads.
    """
    try:
        result = ai_service.generate_image(payload.prompt, payload.size)
        return APIResponse(success=True, message="Imagem gerada com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# IA — CRIAR ANÚNCIO COMPLETO (ORQUESTRADOR PRINCIPAL)
# =============================================================================

@router.post(
    "/ai/create-full-ad",
    summary="Criar anúncio completo com IA",
    tags=["IA — Geração"],
    status_code=status.HTTP_201_CREATED,
)
async def create_full_ad_with_ai(
    payload: AICreateFullAdRequest,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Endpoint principal: cria campanha + ad set + anúncio completo usando IA.

    Fluxo automático:
    1. IA gera copy (headline, texto, CTA) → pode ser sobrescrito com custom_copy
    2. IA sugere segmentação de público → pode ser sobrescrito com custom_targeting
    3. DALL-E gera imagem → pode ser sobrescrito com custom_image_url ou generate_image=false
    4. Cria campanha na Meta API
    5. Cria ad set com a segmentação gerada
    6. Cria criativo com copy + imagem
    7. Cria anúncio e salva tudo no Firestore

    Qualquer campo pode ser sobrescrito para uso manual/semi-automático.
    """
    try:
        # --- Busca credenciais e inicializa Meta ---
        automacao = repository.get_automacao(payload.automacao_id)
        if not automacao:
            raise ValueError(f"Automação '{payload.automacao_id}' não encontrada.")

        init_meta_api(
            app_id=automacao["app_id"],
            app_secret=automacao["app_secret"],
            access_token=automacao["access_token"],
        )

        # --- Gera conteúdo com IA (respeitando overrides) ---
        logger.info(f"Iniciando criação de anúncio com IA | automacao={payload.automacao_id}")

        ad_content = ai_service.prepare_full_ad_content(
            context=payload.context,
            custom_copy=payload.custom_copy,
            custom_targeting=payload.custom_targeting,
            custom_image_url=payload.custom_image_url,
            generate_image=payload.generate_image,
            custom_campaign_name=payload.custom_campaign_name,
        )

        copy      = ad_content["copy"]
        targeting = ad_content["targeting"]
        image     = ad_content.get("image")

        campaign_name = copy.get("campaign_name", f"Camp_{payload.context.product_name[:20]}")

        # --- 1. Criar Campanha ---
        campaign = create_campaign_meta(
            ad_account_id=automacao["ad_account_id"],
            name=campaign_name,
            objective=payload.campaign_objective.value,
            status=payload.campaign_status.value,
            special_ad_categories=[],
            daily_budget=payload.daily_budget,
        )

        # --- 2. Criar Ad Set ---
        adset = create_adset_meta(
            ad_account_id=automacao["ad_account_id"],
            campaign_id=campaign["id"],
            name=f"AdSet_{payload.context.product_name[:20]}",
            daily_budget=payload.daily_budget,
            billing_event="IMPRESSIONS",
            optimization_goal="REACH",
            targeting=targeting,
            status=payload.campaign_status.value,
        )

        # --- 3. Montar criativo ---
        from app.services.ab_service import _build_ad_creative
        creative = _build_ad_creative(
            copy=copy,
            page_id=payload.page_id,
            link_url=payload.link_url,
            image_url=image["url"] if image else None,
        )

        # --- 4. Criar anúncio ---
        ad = create_ad_meta(
            ad_account_id=automacao["ad_account_id"],
            adset_id=adset["id"],
            name=copy.get("headline", "Anúncio IA")[:100],
            creative=creative,
            status=payload.campaign_status.value,
        )

        # --- 5. Persistir no Firestore ---
        repository.set_campaign_id(payload.automacao_id, campaign["id"])
        repository.add_log(payload.automacao_id, "ai_create_full_ad", {
            "campaign_id": campaign["id"],
            "adset_id":    adset["id"],
            "ad_id":       ad["id"],
            "ai_generated_fields": ad_content.get("ai_generated_fields", []),
        })

        result = {
            "ai_generated": {
                "copy":              copy,
                "targeting":         targeting,
                "image":             image,
                "ai_generated_fields": ad_content.get("ai_generated_fields", []),
                "audience_info":     ad_content.get("audience_info"),
            },
            "meta_results": {
                "campaign_id": campaign["id"],
                "campaign_name": campaign_name,
                "adset_id":    adset["id"],
                "ad_id":       ad["id"],
                "status":      payload.campaign_status.value,
            },
        }

        logger.info(
            f"Anúncio completo criado com IA | campaign={campaign['id']} | "
            f"ad={ad['id']} | campos_IA={ad_content.get('ai_generated_fields')}"
        )

        return APIResponse(
            success=True,
            message=f"Anúncio criado com sucesso! Campos gerados pela IA: {ad_content.get('ai_generated_fields')}",
            data=result,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Erro inesperado em create_full_ad_with_ai: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {exc}")


# =============================================================================
# A/B TESTING
# =============================================================================

@router.post(
    "/ab-test/create",
    summary="Criar teste A/B (variantes manuais)",
    tags=["A/B Testing"],
    status_code=status.HTTP_201_CREATED,
)
async def create_ab_test(
    payload: ABTestCreate,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Cria teste A/B com variantes de copy definidas manualmente.

    Cria um anúncio por variante no mesmo Ad Set.
    A Meta distribui automaticamente a entrega entre as variantes.
    """
    try:
        result = ab_service.create_ab_test(payload)
        return APIResponse(success=True, message="Teste A/B criado com sucesso.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/ab-test/create-with-ai",
    summary="Criar teste A/B com variantes geradas pela IA",
    tags=["A/B Testing"],
    status_code=status.HTTP_201_CREATED,
)
async def create_ab_test_with_ai(
    payload: ABTestGenerateRequest,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    A IA gera variantes com abordagens psicológicas diferentes
    (benefício, urgência, prova social, curiosidade) e cria o teste automaticamente.
    """
    try:
        result = ab_service.create_ab_test_with_ai(payload)
        return APIResponse(
            success=True,
            message=f"Teste A/B com {len(result.get('variants', []))} variantes geradas pela IA.",
            data=result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/ab-tests",
    summary="Listar testes A/B",
    tags=["A/B Testing"],
)
async def list_ab_tests(
    automacao_id: str = Query(..., description="ID da automação"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Lista todos os testes A/B de uma automação."""
    try:
        result = ab_service.list_ab_tests(automacao_id)
        return APIResponse(success=True, message=f"{len(result)} teste(s) encontrado(s).", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/ab-test/{test_id}",
    summary="Detalhes de um teste A/B",
    tags=["A/B Testing"],
)
async def get_ab_test(
    test_id: str,
    _: str = Depends(require_api_key),
) -> APIResponse:
    """Retorna todos os detalhes de um teste A/B, incluindo resultados."""
    try:
        result = ab_service.get_ab_test(test_id)
        return APIResponse(success=True, message="Teste encontrado.", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/ab-test/{test_id}/evaluate",
    summary="Avaliar teste A/B e determinar vencedor",
    tags=["A/B Testing"],
)
async def evaluate_ab_test(
    test_id: str,
    auto_apply: bool = Query(None, description="Se True, pausa perdedores automaticamente"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Busca métricas de cada variante na Meta API, determina o vencedor
    e opcionalmente pausa as variantes perdedoras.
    """
    try:
        result = ab_service.evaluate_ab_test(test_id, auto_apply=auto_apply)
        winner = result.get("winner", {}).get("name", "—")
        return APIResponse(
            success=True,
            message=f"Avaliação concluída. Vencedor: {winner}",
            data=result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# OTIMIZAÇÃO AUTOMÁTICA
# =============================================================================

@router.post(
    "/optimize",
    summary="Otimizar campanha automaticamente",
    tags=["Otimização Automática"],
)
async def optimize_campaign(
    payload: OptimizeRequest,
    use_ai: bool = Query(True, description="Se True, adiciona análise contextual do GPT-4"),
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Analisa métricas da campanha e executa ações automáticas com base nas regras.

    Use `dry_run=true` para simular sem executar ações reais.
    Use os presets de regras em `GET /optimize/presets` como ponto de partida.
    """
    try:
        result = optimizer.optimize(payload, use_ai_analysis=use_ai)
        return APIResponse(
            success=True,
            message=result.get("summary", "Otimização concluída."),
            data=result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Erro em optimize_campaign: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/optimize/presets",
    summary="Presets de regras de otimização",
    tags=["Otimização Automática"],
)
async def get_optimization_presets(
    _: str = Depends(require_api_key),
) -> APIResponse:
    """
    Retorna conjuntos de regras pré-configuradas para otimização.

    Presets disponíveis:
    - **conservative**: Regras conservadoras, notifica antes de pausar
    - **balanced**: Equilíbrio entre performance e custo (recomendado)
    - **aggressive**: Pausa rápida campanhas ruins, escala winners
    """
    presets = {
        "conservative": optimizer.get_preset_rules("conservative"),
        "balanced":     optimizer.get_preset_rules("balanced"),
        "aggressive":   optimizer.get_preset_rules("aggressive"),
    }
    return APIResponse(
        success=True,
        message="Presets de otimização disponíveis.",
        data=presets,
    )
