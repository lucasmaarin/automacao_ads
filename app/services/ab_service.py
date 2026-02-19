"""
Serviço de Testes A/B para campanhas Meta Ads.

Estratégia de A/B test implementada:
  - Cria N anúncios no mesmo Ad Set (um por variante de copy)
  - A Meta distribui a entrega automaticamente entre os anúncios
  - Após o período configurado, compara métricas de cada anúncio
  - Pausa automaticamente os perdedores e mantém o vencedor (se auto_apply=True)

Estrutura Firestore dos testes:
  quartel/automacao_ads/ab_tests/{test_id}
    ├── test_id
    ├── automacao_id
    ├── campaign_id / adset_id
    ├── variants: [{variant_name, ad_id, copy}]
    ├── optimization_metric
    ├── status: active | evaluating | completed | cancelled
    ├── winner: {name, ad_id, metric_value} | null
    ├── results: {ad_id: {metrics...}}
    └── timestamps

Decisão técnica: A/B no nível de anúncio (não ad set) é mais simples
de implementar e suficiente para testes de copy/criativo.
Para testes de segmentação, criar ad sets separados é recomendado.
"""

from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from facebook_business.exceptions import FacebookRequestError

from app.core.meta import (
    init_meta_api,
    create_ad_meta,
    update_campaign_status_meta,
    get_campaign_insights_meta,
)
from app.core.firebase import get_db
from app.core.config import get_settings
from app.repositories.ads_repository import AdsRepository
from app.models.schemas import ABTestCreate, ABTestGenerateRequest
from app.services.ai_service import AIService
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
repository = AdsRepository()
ai_service = AIService()

# Métricas suportadas para definir vencedor
VALID_METRICS = {"ctr", "cpc", "cpm", "clicks", "reach", "impressions"}

# Métrica onde MENOR é melhor (ex: menor CPC = melhor)
LOWER_IS_BETTER = {"cpc", "cpm", "cost_per_action_type"}


def _ab_tests_ref():
    """Referência da subcoleção de testes A/B no Firestore."""
    db = get_db()
    return (
        db.collection(settings.FIRESTORE_QUARTEL_COLLECTION)
        .document(settings.FIRESTORE_AUTOMACAO_DOC)
        .collection("ab_tests")
    )


def _build_ad_creative(copy: dict, page_id: str, link_url: str, image_url: str | None = None) -> dict:
    """
    Monta a especificação de criativo para a Meta API.
    Usa image_url diretamente se fornecida (formato link ad).
    """
    link_data: dict[str, Any] = {
        "link": link_url,
        "message": copy.get("primary_text", ""),
        "name": copy.get("headline", ""),
        "description": copy.get("description", ""),
        "call_to_action": {"type": _cta_to_meta_type(copy.get("cta", "LEARN_MORE"))},
    }

    if image_url:
        link_data["image_url"] = image_url

    return {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": link_data,
        }
    }


def _cta_to_meta_type(cta_text: str) -> str:
    """Converte texto de CTA para o tipo aceito pela Meta API."""
    cta_map = {
        "saiba mais": "LEARN_MORE",
        "comprar agora": "SHOP_NOW",
        "inscreva-se": "SUBSCRIBE",
        "obter oferta": "GET_OFFER",
        "fale conosco": "CONTACT_US",
        "baixar": "DOWNLOAD",
        "cadastre-se": "SIGN_UP",
        "agendar": "BOOK_TRAVEL",
    }
    normalized = cta_text.lower().strip()
    return cta_map.get(normalized, "LEARN_MORE")


class ABTestService:
    """
    Serviço de criação e avaliação de testes A/B.
    """

    def _get_and_init_meta(self, automacao_id: str) -> dict[str, Any]:
        """Busca credenciais e inicializa Meta API."""
        automacao = repository.get_automacao(automacao_id)
        if not automacao:
            raise ValueError(f"Automação '{automacao_id}' não encontrada.")
        init_meta_api(
            app_id=automacao["app_id"],
            app_secret=automacao["app_secret"],
            access_token=automacao["access_token"],
        )
        return automacao

    # =========================================================================
    # CRIAR TESTE A/B (variantes manuais)
    # =========================================================================

    def create_ab_test(self, payload: ABTestCreate) -> dict[str, Any]:
        """
        Cria um teste A/B com variantes de copy fornecidas manualmente.

        Para cada variante:
        1. Cria um anúncio no Ad Set especificado
        2. Salva o mapeamento variante → ad_id no Firestore
        3. Registra test_id para avaliação futura
        """
        automacao = self._get_and_init_meta(payload.automacao_id)
        test_id = f"ab_{uuid4().hex[:12]}"
        created_variants = []

        for i, variant in enumerate(payload.variants):
            try:
                creative = _build_ad_creative(variant.ad_copy, payload.page_id, payload.link_url)

                ad_result = create_ad_meta(
                    ad_account_id=automacao["ad_account_id"],
                    adset_id=payload.adset_id,
                    name=f"[A/B {test_id}] {variant.name}",
                    creative=creative,
                    status="PAUSED",  # Começa pausado — ativar ao lançar o teste
                )

                created_variants.append({
                    "variant_index": i,
                    "name": variant.name,
                    "ad_id": ad_result["id"],
                    "copy": variant.ad_copy,
                })
                logger.info(f"Variante A/B criada | test_id={test_id} | ad_id={ad_result['id']}")

            except FacebookRequestError as exc:
                logger.error(f"Erro ao criar variante '{variant.name}': {exc.api_error_message()}")
                raise ValueError(f"Erro ao criar variante '{variant.name}': {exc.api_error_message()}")

        # Salva teste no Firestore
        now = datetime.now(timezone.utc)
        test_doc = {
            "test_id": test_id,
            "automacao_id": payload.automacao_id,
            "campaign_id": payload.campaign_id,
            "adset_id": payload.adset_id,
            "page_id": payload.page_id,
            "name": payload.name,
            "status": "active",
            "variants": created_variants,
            "optimization_metric": payload.optimization_metric,
            "duration_hours": payload.duration_hours,
            "auto_apply_winner": payload.auto_apply_winner,
            "created_at": now,
            "end_at": now + timedelta(hours=payload.duration_hours),
            "winner": None,
            "results": {},
        }

        _ab_tests_ref().document(test_id).set(test_doc)

        # Ativa todos os anúncios do teste
        for v in created_variants:
            try:
                update_campaign_status_meta(v["ad_id"], "ACTIVE")
            except Exception:
                pass  # Ativação individual — não bloqueia se um falhar

        repository.add_log(payload.automacao_id, "create_ab_test", {
            "test_id": test_id, "variants": len(created_variants)
        })

        logger.info(f"Teste A/B criado | test_id={test_id} | variantes={len(created_variants)}")
        return {
            "test_id": test_id,
            "name": payload.name,
            "variants": created_variants,
            "status": "active",
            "optimization_metric": payload.optimization_metric,
            "end_at": test_doc["end_at"].isoformat(),
        }

    # =========================================================================
    # CRIAR TESTE A/B COM IA
    # =========================================================================

    def create_ab_test_with_ai(self, payload: ABTestGenerateRequest) -> dict[str, Any]:
        """
        Gera variantes de copy com IA e cria o teste A/B automaticamente.

        A IA cria copy com abordagens psicológicas diferentes
        (benefício, urgência, prova social, curiosidade) para identificar
        qual ressoa melhor com o público definido no contexto.
        """
        logger.info(f"Gerando {payload.num_variants} variantes com IA para A/B test...")

        ai_variants = ai_service.generate_ab_variants(payload.context, payload.num_variants)

        if not ai_variants:
            raise ValueError("IA não gerou variantes. Verifique o contexto e tente novamente.")

        # Converte para ABTestVariant
        from app.models.schemas import ABTestVariant, ABTestCreate

        variants = [
            ABTestVariant(
                name=v.get("name", f"Variante {i+1}"),
                copy={
                    "headline":     v.get("headline", ""),
                    "primary_text": v.get("primary_text", ""),
                    "description":  v.get("description", ""),
                    "cta":          v.get("cta", "Saiba Mais"),
                }
            )
            for i, v in enumerate(ai_variants)
        ]

        ab_payload = ABTestCreate(
            automacao_id=payload.automacao_id,
            campaign_id=payload.campaign_id,
            adset_id=payload.adset_id,
            page_id=payload.page_id,
            link_url=payload.link_url,
            name=f"A/B Test — {payload.context.product_name}",
            variants=variants,
            optimization_metric=payload.optimization_metric,
            duration_hours=payload.duration_hours,
            auto_apply_winner=payload.auto_apply_winner,
        )

        result = self.create_ab_test(ab_payload)
        result["ai_generated"] = True
        result["ai_variants_raw"] = ai_variants
        return result

    # =========================================================================
    # AVALIAR TESTE E DETERMINAR VENCEDOR
    # =========================================================================

    def evaluate_ab_test(self, test_id: str, auto_apply: bool | None = None) -> dict[str, Any]:
        """
        Avalia o teste A/B buscando métricas de cada variante na Meta API.

        Determina o vencedor com base na métrica configurada.
        Se auto_apply=True (ou configurado no teste), pausa os perdedores.

        Pode ser chamado a qualquer momento durante ou após o teste.
        """
        test_ref = _ab_tests_ref().document(test_id)
        test_doc = test_ref.get()

        if not test_doc.exists:
            raise ValueError(f"Teste A/B '{test_id}' não encontrado.")

        test = test_doc.to_dict()
        automacao_id = test["automacao_id"]
        metric = test["optimization_metric"]
        should_auto_apply = auto_apply if auto_apply is not None else test.get("auto_apply_winner", False)

        self._get_and_init_meta(automacao_id)

        # Busca métricas de cada variante
        variant_results = []
        for variant in test["variants"]:
            ad_id = variant["ad_id"]
            try:
                insights = get_campaign_insights_meta(
                    campaign_id=ad_id,
                    date_preset="maximum",
                    fields=["impressions", "reach", "clicks", "spend", "ctr", "cpc", "cpm"],
                )
                metric_value = float(insights.get(metric, 0) or 0)
                variant_results.append({
                    **variant,
                    "metrics": insights,
                    "metric_value": metric_value,
                })
            except Exception as exc:
                logger.warning(f"Sem dados para variante {ad_id}: {exc}")
                variant_results.append({
                    **variant,
                    "metrics": {},
                    "metric_value": 0,
                })

        # Determina vencedor
        if not variant_results:
            raise ValueError("Nenhuma métrica disponível. Aguarde o teste ter impressões suficientes.")

        reverse = metric not in LOWER_IS_BETTER
        sorted_variants = sorted(variant_results, key=lambda x: x["metric_value"], reverse=reverse)
        winner = sorted_variants[0]
        losers = sorted_variants[1:]

        # Aplica vencedor se configurado
        applied_actions = []
        if should_auto_apply:
            for loser in losers:
                try:
                    update_campaign_status_meta(loser["ad_id"], "PAUSED")
                    applied_actions.append(f"Pausado: {loser['name']} (ad_id={loser['ad_id']})")
                except Exception as exc:
                    logger.warning(f"Não foi possível pausar variante {loser['ad_id']}: {exc}")

        # Atualiza Firestore
        now = datetime.now(timezone.utc)
        test_ref.update({
            "status": "completed",
            "winner": {
                "name": winner["name"],
                "ad_id": winner["ad_id"],
                "metric": metric,
                "metric_value": winner["metric_value"],
            },
            "results": {v["ad_id"]: v["metrics"] for v in variant_results},
            "evaluated_at": now,
            "updated_at": now,
        })

        repository.add_log(automacao_id, "evaluate_ab_test", {
            "test_id": test_id,
            "winner": winner["name"],
            "metric": metric,
        })

        return {
            "test_id": test_id,
            "winner": {
                "name": winner["name"],
                "ad_id": winner["ad_id"],
                "metric": metric,
                "value": winner["metric_value"],
            },
            "ranking": [
                {
                    "rank": i + 1,
                    "name": v["name"],
                    "ad_id": v["ad_id"],
                    f"{metric}": v["metric_value"],
                }
                for i, v in enumerate(sorted_variants)
            ],
            "actions_applied": applied_actions,
            "auto_applied": should_auto_apply,
        }

    # =========================================================================
    # LISTAR TESTES
    # =========================================================================

    def list_ab_tests(self, automacao_id: str) -> list[dict[str, Any]]:
        """Lista todos os testes A/B de uma automação."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        docs = (
            _ab_tests_ref()
            .where(filter=FieldFilter("automacao_id", "==", automacao_id))
            .stream()
        )

        tests = []
        for doc in docs:
            d = doc.to_dict()
            # Remove campos muito grandes da listagem
            d.pop("results", None)
            tests.append(d)

        return tests

    def get_ab_test(self, test_id: str) -> dict[str, Any]:
        """Retorna detalhes completos de um teste A/B."""
        doc = _ab_tests_ref().document(test_id).get()
        if not doc.exists:
            raise ValueError(f"Teste '{test_id}' não encontrado.")
        return doc.to_dict()
