"""
Schemas Pydantic para validação de entrada e saída da API.

Todos os dados que entram e saem da API passam por esses schemas.
Garante tipagem forte, validação automática e documentação automática no Swagger.

Decisão técnica: Pydantic v2 — validadores via @field_validator e model_config.
Enums para campos de valor fixo (status, objective, etc.) evitam strings mágicas.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS — Valores aceitos pela Meta API
# =============================================================================

class CampaignObjective(str, Enum):
    """Objetivos de campanha disponíveis na API v20+ da Meta."""
    OUTCOME_AWARENESS = "OUTCOME_AWARENESS"
    OUTCOME_TRAFFIC = "OUTCOME_TRAFFIC"
    OUTCOME_ENGAGEMENT = "OUTCOME_ENGAGEMENT"
    OUTCOME_LEADS = "OUTCOME_LEADS"
    OUTCOME_APP_PROMOTION = "OUTCOME_APP_PROMOTION"
    OUTCOME_SALES = "OUTCOME_SALES"


class CampaignStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"


class BillingEvent(str, Enum):
    IMPRESSIONS = "IMPRESSIONS"
    LINK_CLICKS = "LINK_CLICKS"
    APP_INSTALLS = "APP_INSTALLS"
    NONE = "NONE"


class OptimizationGoal(str, Enum):
    REACH = "REACH"
    IMPRESSIONS = "IMPRESSIONS"
    LINK_CLICKS = "LINK_CLICKS"
    LANDING_PAGE_VIEWS = "LANDING_PAGE_VIEWS"
    LEAD_GENERATION = "LEAD_GENERATION"
    CONVERSIONS = "CONVERSIONS"
    APP_INSTALLS = "APP_INSTALLS"
    VALUE = "VALUE"
    THRUPLAY = "THRUPLAY"


class DatePreset(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7D = "last_7d"
    LAST_14D = "last_14d"
    LAST_30D = "last_30d"
    LAST_90D = "last_90d"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"


# =============================================================================
# REQUEST SCHEMAS — Entrada da API
# =============================================================================

class AutomacaoCredentials(BaseModel):
    """
    Credenciais para registrar uma automação no sistema.
    Representa o 'onboarding' de uma nova conta de anúncios.
    Suporte multi-tenant: cada automação tem suas próprias credenciais Meta.
    """
    automacao_id: str = Field(
        ...,
        description="ID único da automação (ex: 'cliente_joao_2024')",
        min_length=3,
        max_length=100,
    )
    ad_account_id: str = Field(
        ...,
        description="ID da conta de anúncios Meta (ex: '123456789' ou 'act_123456789')",
    )
    access_token: str = Field(..., description="Access token válido da Meta API")
    app_id: str = Field(..., description="App ID do Meta Developer App")
    app_secret: str = Field(..., description="App Secret do Meta Developer App")

    @field_validator("ad_account_id")
    @classmethod
    def normalize_account_id(cls, v: str) -> str:
        """Garante que o ID da conta sempre tenha o prefixo 'act_'."""
        return v if v.startswith("act_") else f"act_{v}"


class CampaignCreate(BaseModel):
    """Schema para criação de campanha na Meta API."""
    automacao_id: str = Field(..., description="ID da automação (usado para buscar credenciais no Firestore)")
    name: str = Field(..., min_length=1, max_length=200, description="Nome da campanha")
    objective: CampaignObjective = Field(..., description="Objetivo da campanha")
    status: CampaignStatus = Field(CampaignStatus.PAUSED, description="Status inicial")
    special_ad_categories: list[str] = Field(
        default=[],
        description="Categorias especiais (CREDIT, EMPLOYMENT, HOUSING, ISSUES_ELECTIONS_POLITICS)"
    )
    daily_budget: Optional[int] = Field(
        None,
        gt=0,
        description="Orçamento diário em centavos (ex: 1000 = R$10,00)"
    )
    lifetime_budget: Optional[int] = Field(
        None,
        gt=0,
        description="Orçamento total do voo em centavos"
    )

    @model_validator(mode="after")
    def validate_budget(self) -> "CampaignCreate":
        """Garante que ao menos um tipo de orçamento seja informado."""
        if self.daily_budget is None and self.lifetime_budget is None:
            raise ValueError("Informe daily_budget ou lifetime_budget.")
        if self.daily_budget and self.lifetime_budget:
            raise ValueError("Use apenas daily_budget OU lifetime_budget, não ambos.")
        return self


class AdSetCreate(BaseModel):
    """Schema para criação de Ad Set (conjunto de anúncios)."""
    automacao_id: str
    campaign_id: str = Field(..., description="ID da campanha pai na Meta")
    name: str = Field(..., min_length=1, max_length=200)
    daily_budget: int = Field(..., gt=0, description="Orçamento diário em centavos")
    billing_event: BillingEvent = Field(BillingEvent.IMPRESSIONS, description="Evento de cobrança")
    optimization_goal: OptimizationGoal = Field(OptimizationGoal.REACH, description="Objetivo de otimização")
    targeting: dict[str, Any] = Field(
        ...,
        description="Especificação de targeting da Meta (geo_locations, age_min, age_max, interests, etc.)"
    )
    start_time: Optional[str] = Field(None, description="Data de início em ISO 8601 (ex: '2024-03-01T00:00:00')")
    end_time: Optional[str] = Field(None, description="Data de término em ISO 8601")
    status: CampaignStatus = CampaignStatus.PAUSED


class AdCreate(BaseModel):
    """Schema para criação de anúncio (Ad)."""
    automacao_id: str
    adset_id: str = Field(..., description="ID do Ad Set pai na Meta")
    name: str = Field(..., min_length=1, max_length=200)
    creative: dict[str, Any] = Field(
        ...,
        description="Especificação do criativo Meta (creative_id ou inline com image_hash, message, link, etc.)"
    )
    status: CampaignStatus = CampaignStatus.PAUSED


class BudgetUpdate(BaseModel):
    """Schema para atualização de orçamento de campanha."""
    daily_budget: Optional[int] = Field(None, gt=0, description="Novo orçamento diário em centavos")
    lifetime_budget: Optional[int] = Field(None, gt=0, description="Novo orçamento total em centavos")

    @model_validator(mode="after")
    def at_least_one(self) -> "BudgetUpdate":
        if self.daily_budget is None and self.lifetime_budget is None:
            raise ValueError("Informe daily_budget ou lifetime_budget.")
        return self


class InsightQuery(BaseModel):
    """Schema para consulta de métricas de campanha."""
    date_preset: DatePreset = DatePreset.LAST_7D
    fields: list[str] = Field(
        default=[
            "impressions",
            "reach",
            "clicks",
            "spend",
            "cpm",
            "cpc",
            "ctr",
            "actions",
            "cost_per_action_type",
            "frequency",
        ],
        description="Campos de métricas a retornar"
    )


# =============================================================================
# RESPONSE SCHEMAS — Saída da API
# =============================================================================

class APIResponse(BaseModel):
    """Envelope padrão de resposta da API. Toda rota retorna este schema."""
    success: bool
    message: str
    data: Optional[Any] = None


class CampaignResponse(BaseModel):
    campaign_id: str
    name: str
    status: str
    automacao_id: str


class AdSetResponse(BaseModel):
    adset_id: str
    name: str
    campaign_id: str
    status: str
    automacao_id: str


class AdResponse(BaseModel):
    ad_id: str
    name: str
    adset_id: str
    status: str
    automacao_id: str


class LogEntry(BaseModel):
    """Registro de auditoria de uma ação executada."""
    action: str
    timestamp: str
    result: Optional[dict] = None
    error: Optional[str] = None


class AutomacaoDocument(BaseModel):
    """Representa um documento completo de automação salvo no Firestore."""
    automacao_id: str
    ad_account_id: str
    app_id: str
    campaign_id: Optional[str] = None
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    logs: list[dict] = []
    metrics_snapshot: Optional[dict] = None


# =============================================================================
# SCHEMAS DE IA — Geração automática de anúncios
# =============================================================================

class AdTone(str, Enum):
    """Tom de voz do copy gerado pela IA."""
    PROFISSIONAL = "profissional"
    CASUAL       = "casual"
    URGENTE      = "urgente"
    EMPATICO     = "empático"
    DIVERTIDO    = "divertido"
    AUTORIDADE   = "autoridade"


class AIContext(BaseModel):
    """
    Contexto do produto/serviço para a IA gerar conteúdo relevante.
    Quanto mais detalhado, melhor o resultado gerado.
    """
    product_name: str = Field(..., description="Nome do produto ou serviço")
    product_description: str = Field(..., description="Descrição detalhada do produto/serviço")
    target_audience: str = Field(..., description="Descrição do público-alvo em linguagem natural")
    objective: str = Field("conversão", description="Objetivo do anúncio (ex: conversão, leads, tráfego)")
    tone: AdTone = Field(AdTone.PROFISSIONAL, description="Tom de voz do copy")
    language: str = Field("pt-BR", description="Idioma do copy gerado")
    differentials: Optional[str] = Field(None, description="Diferenciais do produto (opcional)")


class AIGenerateCopyRequest(BaseModel):
    """Request para gerar apenas copy com IA."""
    context: AIContext


class AIGenerateAudienceRequest(BaseModel):
    """Request para gerar segmentação de público com IA."""
    context: AIContext


class AIGenerateImageRequest(BaseModel):
    """Request para gerar imagem com DALL-E."""
    prompt: str = Field(..., description="Descrição da imagem desejada")
    context: Optional[AIContext] = None
    size: str = Field("1024x1024", description="Dimensão da imagem: 1024x1024, 1792x1024, 1024x1792")


class AICreateFullAdRequest(BaseModel):
    """
    Request para criar um anúncio completo com IA.

    A IA gera copy, público e imagem automaticamente.
    Qualquer campo pode ser sobrescrito manualmente (custom_*).
    Fluxo: IA → Meta API → Firestore.
    """
    automacao_id: str
    context: AIContext

    # Identificadores necessários para o criativo Meta
    page_id: str = Field(..., description="ID da Página do Facebook para o criativo")
    link_url: str = Field(..., description="URL da landing page do anúncio")

    # Configuração da campanha
    daily_budget: int = Field(5000, gt=0, description="Orçamento diário em centavos (5000 = R$50)")
    campaign_objective: CampaignObjective = CampaignObjective.OUTCOME_TRAFFIC
    campaign_status: CampaignStatus = CampaignStatus.PAUSED
    generate_image: bool = Field(True, description="Se True, gera imagem com DALL-E 3")

    # Overrides opcionais — se informados, a IA não gera para aquele campo
    custom_copy: Optional[dict] = Field(None, description="Copy manual (headline, primary_text, description, cta)")
    custom_targeting: Optional[dict] = Field(None, description="Targeting spec Meta manual (substitui IA)")
    custom_image_url: Optional[str] = Field(None, description="URL de imagem própria (substitui DALL-E)")
    custom_campaign_name: Optional[str] = Field(None, description="Nome da campanha (se None, IA sugere)")


# =============================================================================
# SCHEMAS DE TESTE A/B
# =============================================================================

class ABTestVariant(BaseModel):
    """Uma variante dentro de um teste A/B."""
    name: str = Field(..., description="Nome da variante (ex: 'Variante A - Benefício')")
    ad_copy: dict = Field(..., description="Copy da variante: headline, primary_text, description, cta")


class ABTestCreate(BaseModel):
    """
    Request para criar um teste A/B com variantes manuais.
    Cria N anúncios no mesmo Ad Set — um por variante.
    """
    automacao_id: str
    campaign_id: str
    adset_id: str = Field(..., description="Ad Set pai onde os anúncios serão criados")
    page_id: str
    link_url: str
    name: str = Field(..., description="Nome do teste A/B")
    variants: list[ABTestVariant] = Field(..., min_length=2, max_length=5)
    optimization_metric: str = Field("ctr", description="Métrica para definir vencedor: ctr, cpc, cpm, clicks")
    duration_hours: int = Field(24, description="Duração do teste em horas")
    auto_apply_winner: bool = Field(True, description="Se True, pausa perdedores automaticamente ao avaliar")


class ABTestGenerateRequest(BaseModel):
    """
    Request para criar teste A/B com variantes geradas pela IA.
    A IA cria copy com abordagens diferentes para cada variante.
    """
    automacao_id: str
    campaign_id: str
    adset_id: str
    page_id: str
    link_url: str
    context: AIContext
    num_variants: int = Field(2, ge=2, le=4, description="Número de variantes (2-4)")
    optimization_metric: str = "ctr"
    duration_hours: int = 24
    auto_apply_winner: bool = True


# =============================================================================
# SCHEMAS DE OTIMIZAÇÃO AUTOMÁTICA
# =============================================================================

class OptimizationAction(str, Enum):
    """Ação a ser tomada quando uma regra é ativada."""
    PAUSE             = "pause"
    INCREASE_BUDGET_10 = "increase_budget_10pct"
    INCREASE_BUDGET_20 = "increase_budget_20pct"
    DECREASE_BUDGET_10 = "decrease_budget_10pct"
    DECREASE_BUDGET_20 = "decrease_budget_20pct"
    NOTIFY            = "notify"


class OptimizationCondition(str, Enum):
    GREATER_THAN = "greater_than"
    LESS_THAN    = "less_than"


class OptimizationRule(BaseModel):
    """
    Regra de otimização: se [metric] [condition] [threshold], então [action].
    Exemplo: se cpc > 2.50, então pause.
    """
    metric: str = Field(..., description="Métrica: ctr, cpc, cpm, spend, clicks, reach, impressions")
    condition: OptimizationCondition
    threshold: float = Field(..., description="Valor de referência (cpc em R$, ctr em %, etc.)")
    action: OptimizationAction


class OptimizeRequest(BaseModel):
    """Request para executar otimização automática em uma campanha."""
    automacao_id: str
    campaign_id: str
    rules: list[OptimizationRule] = Field(..., min_length=1, description="Regras de otimização")
    date_preset: str = Field("last_7d", description="Período de análise das métricas")
    dry_run: bool = Field(False, description="Se True, apenas simula as ações sem executar")
