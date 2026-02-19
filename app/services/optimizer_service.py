"""
Serviço de Otimização Automática de Campanhas.

Combina duas abordagens:
  1. Regras determinísticas: condições configuráveis → ações automáticas
     Exemplo: se CPC > R$2,50, reduzir orçamento em 10%
  2. Análise com IA: GPT-4 lê as métricas e sugere ações estratégicas

Fluxo:
  1. Busca insights da campanha (período configurável)
  2. Avalia cada regra contra as métricas reais
  3. Executa as ações das regras ativadas (ou simula se dry_run=True)
  4. Opcionalmente, pede análise ao GPT-4
  5. Salva tudo no log de auditoria do Firestore

O endpoint pode ser chamado manualmente ou por um cron job externo
(Cloud Scheduler, GitHub Actions, etc.) para otimização periódica.
"""

from typing import Any
from facebook_business.exceptions import FacebookRequestError

from app.core.meta import (
    init_meta_api,
    get_campaign_insights_meta,
    update_campaign_status_meta,
    update_campaign_budget_meta,
)
from app.repositories.ads_repository import AdsRepository
from app.models.schemas import OptimizeRequest, OptimizationAction, OptimizationCondition
from app.services.ai_service import AIService
from app.utils.logger import get_logger

logger = get_logger(__name__)
repository = AdsRepository()
ai_service = AIService()

# Campos de métricas que precisam de conversão de tipo
FLOAT_METRICS = {"ctr", "cpc", "cpm", "spend", "frequency", "cost_per_result"}
INT_METRICS = {"impressions", "reach", "clicks"}


def _parse_metric(value: Any) -> float:
    """Converte valor de métrica da Meta API para float."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _check_condition(value: float, condition: OptimizationCondition, threshold: float) -> bool:
    """Avalia se a condição da regra é satisfeita."""
    if condition == OptimizationCondition.GREATER_THAN:
        return value > threshold
    elif condition == OptimizationCondition.LESS_THAN:
        return value < threshold
    return False


class OptimizerService:
    """
    Serviço de otimização de campanhas baseado em regras + análise de IA.
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
    # EXECUTE OPTIMIZATION RULES
    # =========================================================================

    def optimize(
        self,
        payload: OptimizeRequest,
        use_ai_analysis: bool = True,
    ) -> dict[str, Any]:
        """
        Executa otimização automática de uma campanha com base em regras + IA.

        Parâmetros:
            payload: Regras de otimização e configuração
            use_ai_analysis: Se True, adiciona análise contextual do GPT-4

        Retorna relatório completo com métricas, regras ativadas e ações executadas.
        """
        automacao = self._get_and_init_meta(payload.automacao_id)

        # --- Busca métricas atuais ---
        try:
            insights_fields = [
                "impressions", "reach", "clicks", "spend",
                "ctr", "cpc", "cpm", "frequency",
                "actions", "cost_per_action_type",
            ]
            insights = get_campaign_insights_meta(
                campaign_id=payload.campaign_id,
                date_preset=payload.date_preset,
                fields=insights_fields,
            )
        except FacebookRequestError as exc:
            raise ValueError(f"Erro ao buscar métricas: {exc.api_error_message()}")

        if not insights:
            return {
                "success": False,
                "message": f"Sem dados de métricas para o período '{payload.date_preset}'. "
                           "A campanha pode não ter tido impressões.",
                "insights": {},
                "rules_evaluated": [],
                "actions_taken": [],
            }

        # --- Avalia regras ---
        rules_evaluated = []
        actions_taken = []

        for rule in payload.rules:
            raw_value = insights.get(rule.metric, 0)
            actual_value = _parse_metric(raw_value)

            triggered = _check_condition(actual_value, rule.condition, rule.threshold)

            rule_result = {
                "metric":         rule.metric,
                "condition":      rule.condition.value,
                "threshold":      rule.threshold,
                "actual_value":   actual_value,
                "triggered":      triggered,
                "action":         rule.action.value,
                "action_applied": False,
            }

            if triggered:
                if payload.dry_run:
                    rule_result["action_applied"] = "dry_run — não executado"
                    logger.info(
                        f"[DRY RUN] Regra ativada: {rule.metric}={actual_value} "
                        f"{rule.condition.value} {rule.threshold} → {rule.action.value}"
                    )
                else:
                    action_result = self._execute_action(
                        campaign_id=payload.campaign_id,
                        action=rule.action,
                        current_insights=insights,
                    )
                    rule_result["action_applied"] = action_result
                    actions_taken.append({
                        "action": rule.action.value,
                        "reason": f"{rule.metric} ({actual_value:.2f}) {rule.condition.value} {rule.threshold}",
                        "result": action_result,
                    })

            rules_evaluated.append(rule_result)

        # --- Análise com IA (opcional) ---
        ai_analysis = None
        if use_ai_analysis and insights:
            try:
                context_str = (
                    f"Campanha ID: {payload.campaign_id} | "
                    f"Automação: {payload.automacao_id} | "
                    f"Período: {payload.date_preset}"
                )
                ai_analysis = ai_service.analyze_metrics_and_suggest(insights, context_str)
            except Exception as exc:
                logger.warning(f"Análise de IA falhou (não crítico): {exc}")
                ai_analysis = {"error": str(exc)}

        # --- Log no Firestore ---
        log_payload = {
            "campaign_id":  payload.campaign_id,
            "date_preset":  payload.date_preset,
            "dry_run":      payload.dry_run,
            "rules_count":  len(payload.rules),
            "triggered":    sum(1 for r in rules_evaluated if r["triggered"]),
            "actions_taken": len(actions_taken),
        }

        if not payload.dry_run:
            repository.add_log(payload.automacao_id, "auto_optimize", log_payload)

        logger.info(
            f"Otimização concluída | campaign={payload.campaign_id} | "
            f"regras={len(rules_evaluated)} | ativadas={sum(1 for r in rules_evaluated if r['triggered'])} | "
            f"dry_run={payload.dry_run}"
        )

        return {
            "success": True,
            "campaign_id": payload.campaign_id,
            "date_preset": payload.date_preset,
            "dry_run": payload.dry_run,
            "insights": insights,
            "rules_evaluated": rules_evaluated,
            "actions_taken": actions_taken,
            "ai_analysis": ai_analysis,
            "summary": (
                f"{sum(1 for r in rules_evaluated if r['triggered'])} regra(s) ativada(s) "
                f"de {len(rules_evaluated)} avaliada(s). "
                f"{len(actions_taken)} ação(ões) {'simulada(s)' if payload.dry_run else 'executada(s)'}."
            ),
        }

    # =========================================================================
    # EXECUTE INDIVIDUAL ACTION
    # =========================================================================

    def _execute_action(
        self,
        campaign_id: str,
        action: OptimizationAction,
        current_insights: dict[str, Any],
    ) -> str:
        """
        Executa uma ação de otimização em uma campanha.

        Retorna string descrevendo o resultado da ação.
        """
        try:
            if action == OptimizationAction.PAUSE:
                update_campaign_status_meta(campaign_id, "PAUSED")
                return "Campanha pausada com sucesso."

            elif action in (
                OptimizationAction.INCREASE_BUDGET_10,
                OptimizationAction.INCREASE_BUDGET_20,
                OptimizationAction.DECREASE_BUDGET_10,
                OptimizationAction.DECREASE_BUDGET_20,
            ):
                return self._adjust_budget(campaign_id, action, current_insights)

            elif action == OptimizationAction.NOTIFY:
                return "Notificação registrada no log de auditoria."

            return f"Ação '{action.value}' não implementada."

        except FacebookRequestError as exc:
            msg = f"Erro Meta API ao executar '{action.value}': {exc.api_error_message()}"
            logger.error(msg)
            return msg

    def _adjust_budget(
        self,
        campaign_id: str,
        action: OptimizationAction,
        current_insights: dict[str, Any],
    ) -> str:
        """
        Ajusta o orçamento da campanha com base na ação configurada.

        NOTA: Para ajustar o budget via Meta API, precisamos do budget atual.
        Buscamos o budget atual via insights (campo spend) e estimamos.
        Em produção, use campaign.api_get() para obter daily_budget exato.
        """
        from facebook_business.adobjects.campaign import Campaign

        try:
            # Busca orçamento atual da campanha
            campaign = Campaign(campaign_id)
            campaign_data = campaign.api_get(fields=["daily_budget", "lifetime_budget"])
            current_daily = int(campaign_data.get("daily_budget", 0))

            if current_daily == 0:
                return "Ajuste de budget não disponível: campanha usa lifetime_budget ou budget pelo Ad Set."

            multiplier = {
                OptimizationAction.INCREASE_BUDGET_10: 1.10,
                OptimizationAction.INCREASE_BUDGET_20: 1.20,
                OptimizationAction.DECREASE_BUDGET_10: 0.90,
                OptimizationAction.DECREASE_BUDGET_20: 0.80,
            }.get(action, 1.0)

            new_budget = int(current_daily * multiplier)

            # Mínimo de R$1,00 (100 centavos)
            new_budget = max(new_budget, 100)

            update_campaign_budget_meta(campaign_id, daily_budget=new_budget)

            change_pct = (multiplier - 1) * 100
            direction = "aumentado" if multiplier > 1 else "reduzido"
            return (
                f"Budget diário {direction} em {abs(change_pct):.0f}%: "
                f"R${current_daily/100:.2f} → R${new_budget/100:.2f}"
            )

        except Exception as exc:
            return f"Erro ao ajustar budget: {exc}"

    # =========================================================================
    # PRESET RULES
    # =========================================================================

    @staticmethod
    def get_preset_rules(preset: str = "conservative") -> list[dict]:
        """
        Retorna conjuntos de regras pré-definidas prontos para uso.

        Presets disponíveis:
          - conservative: regras conservadoras, pausa apenas em casos extremos
          - balanced: equilíbrio entre performance e controle de custo
          - aggressive: otimização agressiva, pausa rápida de campanhas ruins
        """
        presets = {
            "conservative": [
                {"metric": "cpc", "condition": "greater_than", "threshold": 5.0, "action": "decrease_budget_10pct"},
                {"metric": "ctr", "condition": "less_than", "threshold": 0.5, "action": "notify"},
            ],
            "balanced": [
                {"metric": "cpc", "condition": "greater_than", "threshold": 3.0, "action": "decrease_budget_10pct"},
                {"metric": "ctr", "condition": "less_than", "threshold": 1.0, "action": "decrease_budget_10pct"},
                {"metric": "ctr", "condition": "greater_than", "threshold": 3.0, "action": "increase_budget_10pct"},
            ],
            "aggressive": [
                {"metric": "cpc", "condition": "greater_than", "threshold": 2.0, "action": "pause"},
                {"metric": "ctr", "condition": "less_than", "threshold": 0.8, "action": "pause"},
                {"metric": "ctr", "condition": "greater_than", "threshold": 3.0, "action": "increase_budget_20pct"},
                {"metric": "cpm", "condition": "greater_than", "threshold": 50.0, "action": "decrease_budget_20pct"},
            ],
        }
        return presets.get(preset, presets["balanced"])
