"""
Repositório de Analytics — coleta e consulta de dados para melhoria contínua.

Estrutura Firestore:
    quartel/automacao_ads/
        analytics/                          ← Subcollection raiz de analytics
            ai_history/{id}                 ← Cada geração de IA + resultado posterior
            ab_results/{id}                 ← Resultado consolidado de cada teste A/B
            optimizer_actions/{id}          ← Cada ação do otimizador executada
            ad_errors/{id}                  ← Erros da Meta API e rejeições de anúncios
            metrics_history/{id}            ← Snapshots periódicos de métricas por campanha
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.firebase import get_db
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _analytics_col(subcol: str):
    """Retorna referência de uma subcoleção dentro de analytics."""
    db = get_db()
    return (
        db.collection(settings.FIRESTORE_QUARTEL_COLLECTION)
        .document(settings.FIRESTORE_AUTOMACAO_DOC)
        .collection("analytics")
        .document(subcol)
        .collection("entries")
    )


class AnalyticsRepository:

    # =========================================================================
    # AI HISTORY — cada geração de copy/audience/image + feedback posterior
    # =========================================================================

    def save_ai_generation(
        self,
        automacao_id: str,
        generation_type: str,        # "copy" | "audience" | "image" | "full_ad"
        context: dict[str, Any],     # AIContext serializado
        output: dict[str, Any],      # O que a IA gerou
        overrides: dict[str, Any],   # Campos que o usuário substituiu manualmente
        ai_fields: list[str],        # Campos realmente gerados pela IA
        ad_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> str:
        """
        Salva uma geração de IA com contexto completo.
        Retorna o ID do documento para posterior atualização com métricas.
        """
        doc_id = f"ai_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)

        doc = {
            "doc_id": doc_id,
            "automacao_id": automacao_id,
            "generation_type": generation_type,
            "context": context,
            "output": output,
            "overrides": overrides,
            "ai_fields_generated": ai_fields,
            "user_overrode_fields": [k for k, v in overrides.items() if v is not None],
            "ad_id": ad_id,
            "campaign_id": campaign_id,
            "created_at": now,
            # Preenchido depois, quando os insights forem coletados:
            "metrics": None,
            "performance_score": None,
            "feedback_at": None,
        }

        _analytics_col("ai_history").document(doc_id).set(doc)
        logger.info(f"AI generation salva | type={generation_type} | id={doc_id}")
        return doc_id

    def update_ai_generation_metrics(
        self,
        doc_id: str,
        metrics: dict[str, Any],
        performance_score: Optional[float] = None,
    ) -> None:
        """
        Atualiza um registro de geração com os resultados reais do anúncio.
        Chamado quando os insights são coletados da Meta API.
        """
        _analytics_col("ai_history").document(doc_id).update({
            "metrics": metrics,
            "performance_score": performance_score,
            "feedback_at": datetime.now(timezone.utc),
        })
        logger.info(f"Métricas de AI history atualizadas | id={doc_id}")

    def list_ai_generations(
        self,
        automacao_id: Optional[str] = None,
        generation_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lista gerações de IA com filtros opcionais."""
        col = _analytics_col("ai_history")
        query = col

        if automacao_id:
            query = query.where("automacao_id", "==", automacao_id)
        if generation_type:
            query = query.where("generation_type", "==", generation_type)

        docs = query.order_by("created_at", direction="DESCENDING").limit(limit).stream()
        return [d.to_dict() for d in docs]

    # =========================================================================
    # AB RESULTS — resultado consolidado de cada teste A/B
    # =========================================================================

    def save_ab_result(
        self,
        test_id: str,
        automacao_id: str,
        winner: dict[str, Any],
        variants: list[dict[str, Any]],
        metric_used: str,
        delta_pct: Optional[float] = None,
    ) -> None:
        """
        Salva o resultado de um teste A/B após a avaliação.
        Registra qual abordagem de copy venceu e por qual margem.
        """
        now = datetime.now(timezone.utc)
        doc = {
            "test_id": test_id,
            "automacao_id": automacao_id,
            "winner_name": winner.get("name"),
            "winner_approach": winner.get("approach"),
            "winner_metrics": winner.get("metrics"),
            "winner_copy": winner.get("copy"),
            "all_variants": variants,
            "metric_used": metric_used,
            "delta_pct": delta_pct,      # % de melhoria do vencedor sobre perdedor
            "evaluated_at": now,
        }

        _analytics_col("ab_results").document(test_id).set(doc)
        logger.info(f"Resultado A/B salvo | test_id={test_id} | vencedor={winner.get('name')}")

    def list_ab_results(
        self,
        automacao_id: Optional[str] = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        col = _analytics_col("ab_results")
        query = col
        if automacao_id:
            query = query.where("automacao_id", "==", automacao_id)
        docs = query.order_by("evaluated_at", direction="DESCENDING").limit(limit).stream()
        return [d.to_dict() for d in docs]

    # =========================================================================
    # OPTIMIZER ACTIONS — cada ação do otimizador
    # =========================================================================

    def save_optimizer_action(
        self,
        automacao_id: str,
        campaign_id: str,
        rule: dict[str, Any],
        action_taken: str,
        metric_value: float,
        dry_run: bool,
        before_budget: Optional[float] = None,
        after_budget: Optional[float] = None,
    ) -> None:
        """
        Registra cada ação executada pelo otimizador.
        Permite identificar quais regras são mais ativadas e o impacto delas.
        """
        doc_id = f"opt_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        doc = {
            "doc_id": doc_id,
            "automacao_id": automacao_id,
            "campaign_id": campaign_id,
            "rule": rule,
            "metric_triggered": rule.get("metric"),
            "metric_value": metric_value,
            "action_taken": action_taken,
            "dry_run": dry_run,
            "before_budget": before_budget,
            "after_budget": after_budget,
            "executed_at": now,
        }

        _analytics_col("optimizer_actions").document(doc_id).set(doc)
        logger.info(f"Ação do otimizador salva | action={action_taken} | dry_run={dry_run}")

    def list_optimizer_actions(
        self,
        automacao_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        col = _analytics_col("optimizer_actions")
        query = col
        if automacao_id:
            query = query.where("automacao_id", "==", automacao_id)
        if campaign_id:
            query = query.where("campaign_id", "==", campaign_id)
        docs = query.order_by("executed_at", direction="DESCENDING").limit(limit).stream()
        return [d.to_dict() for d in docs]

    # =========================================================================
    # AD ERRORS — erros Meta API e rejeições de anúncios
    # =========================================================================

    def save_ad_error(
        self,
        automacao_id: str,
        error_type: str,          # "meta_api_error" | "ad_rejected" | "rate_limit"
        error_code: Optional[int],
        error_message: str,
        context: dict[str, Any],  # O que estava sendo feito quando o erro ocorreu
        ad_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> None:
        """
        Registra erros da Meta API e rejeições de anúncios.
        Permite identificar padrões de falha e motivos de rejeição recorrentes.
        """
        doc_id = f"err_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        doc = {
            "doc_id": doc_id,
            "automacao_id": automacao_id,
            "error_type": error_type,
            "error_code": error_code,
            "error_message": error_message,
            "context": context,
            "ad_id": ad_id,
            "campaign_id": campaign_id,
            "occurred_at": now,
        }

        _analytics_col("ad_errors").document(doc_id).set(doc)
        logger.info(f"Erro registrado | type={error_type} | code={error_code}")

    def list_ad_errors(
        self,
        automacao_id: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        col = _analytics_col("ad_errors")
        query = col
        if automacao_id:
            query = query.where("automacao_id", "==", automacao_id)
        if error_type:
            query = query.where("error_type", "==", error_type)
        docs = query.order_by("occurred_at", direction="DESCENDING").limit(limit).stream()
        return [d.to_dict() for d in docs]

    # =========================================================================
    # METRICS HISTORY — snapshots periódicos de métricas por campanha
    # =========================================================================

    def save_metrics_snapshot(
        self,
        automacao_id: str,
        campaign_id: str,
        metrics: dict[str, Any],
        ad_id: Optional[str] = None,
        adset_id: Optional[str] = None,
    ) -> None:
        """
        Salva um snapshot de métricas em um momento específico.
        Ao chamar periodicamente, constrói a série histórica de performance.
        """
        doc_id = f"snap_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        doc = {
            "doc_id": doc_id,
            "automacao_id": automacao_id,
            "campaign_id": campaign_id,
            "ad_id": ad_id,
            "adset_id": adset_id,
            "metrics": metrics,
            # Campos extraídos para facilitar queries e agregações futuras:
            "ctr":   metrics.get("ctr"),
            "cpc":   metrics.get("cpc"),
            "cpm":   metrics.get("cpm"),
            "spend": metrics.get("spend"),
            "impressions": metrics.get("impressions"),
            "clicks": metrics.get("clicks"),
            "conversions": metrics.get("conversions"),
            "recorded_at": now,
        }

        _analytics_col("metrics_history").document(doc_id).set(doc)
        logger.info(f"Snapshot de métricas salvo | campaign={campaign_id}")

    def get_metrics_history(
        self,
        campaign_id: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Retorna histórico de snapshots de uma campanha, do mais recente ao mais antigo."""
        col = _analytics_col("metrics_history")
        docs = (
            col.where("campaign_id", "==", campaign_id)
            .order_by("recorded_at", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [d.to_dict() for d in docs]

    # =========================================================================
    # RESUMO AGREGADO — usado no dashboard
    # =========================================================================

    def get_summary(self, automacao_id: str) -> dict[str, Any]:
        """
        Retorna contagens e indicadores agregados de uma automação.
        Útil para o card de resumo no dashboard.
        """
        ai_docs    = list(_analytics_col("ai_history").where("automacao_id", "==", automacao_id).stream())
        err_docs   = list(_analytics_col("ad_errors").where("automacao_id", "==", automacao_id).stream())
        ab_docs    = list(_analytics_col("ab_results").where("automacao_id", "==", automacao_id).stream())
        opt_docs   = list(_analytics_col("optimizer_actions").where("automacao_id", "==", automacao_id).stream())

        ai_data = [d.to_dict() for d in ai_docs]
        overrides_count = sum(
            len(d.get("user_overrode_fields", [])) for d in ai_data
        )
        total_ai_fields = sum(
            len(d.get("ai_fields_generated", [])) for d in ai_data
        )
        override_rate = round(overrides_count / total_ai_fields * 100, 1) if total_ai_fields else 0

        return {
            "automacao_id": automacao_id,
            "total_ai_generations": len(ai_data),
            "total_ab_tests_evaluated": len(ab_docs),
            "total_optimizer_actions": len(opt_docs),
            "total_errors": len(err_docs),
            "ai_override_rate_pct": override_rate,
            "ai_field_breakdown": {
                "copy":      sum(1 for d in ai_data if "copy" in d.get("ai_fields_generated", [])),
                "targeting": sum(1 for d in ai_data if "targeting" in d.get("ai_fields_generated", [])),
                "image":     sum(1 for d in ai_data if "image" in d.get("ai_fields_generated", [])),
            },
        }
