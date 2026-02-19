"""
Serviço de IA para geração automática de conteúdo de anúncios.

Usa OpenAI para:
  - GPT-4o: Gerar copy (headline, texto, CTA), sugerir público e nome de campanha
  - DALL-E 3: Gerar imagem do anúncio a partir de prompt descritivo

Design:
  - Todo campo gerado pela IA pode ser sobrescrito pelo usuário (custom_*)
  - Prompts em português, otimizados para Meta Ads brasileiro
  - Fallback claro quando OPENAI_API_KEY não está configurada
  - Retorna always um dict estruturado — nunca lança exceção silenciosa
"""

import json
from openai import OpenAI, OpenAIError
from app.core.config import get_settings
from app.models.schemas import AIContext
from app.utils.logger import get_logger
from typing import Any

logger = get_logger(__name__)
settings = get_settings()


def _get_client() -> OpenAI:
    """Instancia o cliente OpenAI. Lança ValueError se API key não configurada."""
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY não configurada. Adicione ao .env para usar funcionalidades de IA."
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY)


class AIService:
    """
    Serviço central de IA para geração de anúncios.

    Cada método é independente: pode-se usar geração de copy sem imagem,
    ou imagem sem copy — totalmente flexível.
    """

    # =========================================================================
    # COPY GENERATION
    # =========================================================================

    def generate_copy(self, context: AIContext) -> dict[str, Any]:
        """
        Gera copy completo para anúncio Meta Ads usando GPT-4o.

        Retorna:
            headline: Título (até 40 chars)
            primary_text: Texto principal (até 125 chars)
            description: Descrição complementar (até 30 chars)
            cta: Chamada para ação sugerida
            image_prompt: Prompt em inglês para DALL-E
            campaign_name: Nome sugerido para a campanha
        """
        client = _get_client()

        system_prompt = (
            "Você é um especialista sênior em copywriting para Meta Ads (Facebook e Instagram) "
            "no mercado brasileiro. Cria copy persuasivo, direto e otimizado para conversão. "
            "Responda APENAS com JSON válido, sem markdown, sem explicações extras."
        )

        differentials = f"\nDiferenciais: {context.differentials}" if context.differentials else ""

        user_prompt = f"""Crie copy completo para um anúncio no Meta Ads:

Produto/Serviço: {context.product_name}
Descrição: {context.product_description}{differentials}
Público-alvo: {context.target_audience}
Objetivo: {context.objective}
Tom de voz: {context.tone}
Idioma: {context.language}

Retorne APENAS este JSON (sem markdown):
{{
    "headline": "Título chamativo e direto (máximo 40 caracteres)",
    "primary_text": "Texto principal persuasivo com benefício claro (máximo 125 caracteres)",
    "description": "Frase complementar que reforça o CTA (máximo 30 caracteres)",
    "cta": "Chamada para ação (ex: Saiba Mais, Comprar Agora, Inscreva-se, Obter Oferta)",
    "image_prompt": "Detailed image description in English for DALL-E: scene, style, colors, mood (no text in image)",
    "campaign_name": "Nome interno sugerido para a campanha (ex: Camp_NomeProduto_Objetivo_Mes)"
}}"""

        try:
            response = client.chat.completions.create(
                model=settings.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.75,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            result["_model"] = settings.AI_TEXT_MODEL
            logger.info(f"Copy gerado com IA | produto={context.product_name} | modelo={settings.AI_TEXT_MODEL}")
            return result

        except OpenAIError as exc:
            logger.error(f"Erro OpenAI ao gerar copy: {exc}")
            raise ValueError(f"Erro na API OpenAI: {exc}")

    # =========================================================================
    # AUDIENCE GENERATION
    # =========================================================================

    def generate_audience(self, context: AIContext) -> dict[str, Any]:
        """
        Converte descrição humana de público em targeting spec da Meta API.

        NOTA: A Meta API exige IDs reais para interesses detalhados (interests).
        Esta função gera segmentação por geografia e demografia (sempre funciona)
        e sugere palavras-chave de interesse que o usuário pode pesquisar
        no Audience Insights para obter os IDs reais.
        """
        client = _get_client()

        system_prompt = (
            "Você é especialista em segmentação de anúncios no Meta Ads. "
            "Converta descrições de público em targeting specs válidos para a API. "
            "Use apenas campos que funcionam sem IDs de interesse específicos. "
            "Responda APENAS com JSON válido, sem markdown."
        )

        user_prompt = f"""Crie segmentação de público para Meta Ads:

Produto/Serviço: {context.product_name}
Público descrito: {context.target_audience}
Objetivo: {context.objective}

Retorne APENAS este JSON:
{{
    "targeting": {{
        "geo_locations": {{
            "countries": ["BR"],
            "location_types": ["home", "recent"]
        }},
        "age_min": 18,
        "age_max": 65,
        "genders": [0],
        "interests": [],
        "behaviors": [],
        "flexible_spec": []
    }},
    "description": "Resumo da segmentação escolhida em linguagem humana",
    "suggested_interests": ["lista", "de", "interesses", "para", "pesquisar", "no", "Audience Insights"],
    "estimated_reach_range": "Estimativa de alcance (ex: 500 mil - 2 milhões)"
}}

Ajuste age_min, age_max e genders conforme o público descrito.
Para genders: 0=todos, 1=homens, 2=mulheres."""

        try:
            response = client.chat.completions.create(
                model=settings.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.4,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            logger.info(f"Audience gerado com IA | público={context.target_audience[:60]}")
            return result

        except OpenAIError as exc:
            logger.error(f"Erro OpenAI ao gerar audience: {exc}")
            raise ValueError(f"Erro na API OpenAI: {exc}")

    # =========================================================================
    # IMAGE GENERATION
    # =========================================================================

    def generate_image(self, prompt: str, size: str = "1024x1024") -> dict[str, Any]:
        """
        Gera imagem de anúncio usando DALL-E 3.

        O prompt é enriquecido automaticamente com instruções de qualidade.
        A URL retornada é válida por ~1 hora (hospedada pela OpenAI).

        Para usar em Meta Ads: baixe a imagem e faça upload via AdImage
        ou use o image_url diretamente no criativo (suportado em alguns formatos).
        """
        client = _get_client()

        valid_sizes = ["1024x1024", "1792x1024", "1024x1792"]
        if size not in valid_sizes:
            size = "1024x1024"

        enhanced_prompt = (
            f"Professional advertising image for Facebook and Instagram ads. "
            f"High quality, modern, visually compelling. "
            f"NO text overlays, NO watermarks, NO logos. "
            f"Style: clean, professional photography or digital art. "
            f"{prompt}"
        )

        try:
            response = client.images.generate(
                model=settings.AI_IMAGE_MODEL,
                prompt=enhanced_prompt,
                size=size,
                quality="standard",
                n=1,
            )

            image_url      = response.data[0].url
            revised_prompt = response.data[0].revised_prompt

            logger.info(f"Imagem gerada com DALL-E 3 | size={size}")
            return {
                "url": image_url,
                "revised_prompt": revised_prompt,
                "size": size,
                "model": "dall-e-3",
                "warning": "URL válida por ~1 hora. Baixe a imagem para uso permanente.",
            }

        except OpenAIError as exc:
            logger.error(f"Erro OpenAI ao gerar imagem: {exc}")
            raise ValueError(f"Erro na API OpenAI (DALL-E): {exc}")

    # =========================================================================
    # A/B TEST COPY VARIANTS
    # =========================================================================

    def generate_ab_variants(self, context: AIContext, num_variants: int = 2) -> list[dict[str, Any]]:
        """
        Gera múltiplas variantes de copy para teste A/B.

        Cada variante usa uma abordagem psicológica diferente
        para identificar qual ressoa melhor com o público-alvo.

        Abordagens disponíveis:
          - Benefício direto: foca no resultado que o cliente obtém
          - Urgência/escassez: cria senso de urgência
          - Prova social: usa aprovação de outros
          - Curiosidade: desperta interesse com questão
          - Problema/solução: identifica dor e apresenta solução
        """
        client = _get_client()

        all_approaches = [
            ("A", "benefício direto — mostre o principal resultado que o cliente terá"),
            ("B", "urgência/escassez — crie senso de urgência real (prazo, vagas, oferta)"),
            ("C", "prova social — use aprovação, números ou depoimentos implícitos"),
            ("D", "curiosidade — comece com pergunta ou fato surpreendente"),
        ]
        selected = all_approaches[:min(num_variants, 4)]

        variants_desc = "\n".join(
            f'  - Variante {letter}: {desc}' for letter, desc in selected
        )

        system_prompt = (
            "Você é especialista em testes A/B para Meta Ads brasileiro. "
            "Cria variantes de copy com abordagens psicológicas distintas "
            "para descobrir qual converte mais. Responda APENAS com JSON válido."
        )

        user_prompt = f"""Crie {num_variants} variantes de copy para teste A/B:

Produto: {context.product_name}
Descrição: {context.product_description}
Público: {context.target_audience}
Tom: {context.tone}

Abordagens a usar:
{variants_desc}

Retorne APENAS este JSON:
{{
    "variants": [
        {{
            "name": "Variante A — Benefício",
            "approach": "benefício direto",
            "headline": "título (máx 40 chars)",
            "primary_text": "texto principal (máx 125 chars)",
            "description": "descrição curta (máx 30 chars)",
            "cta": "chamada para ação"
        }}
    ]
}}

Cada variante deve ser claramente diferente das outras em tom e abordagem."""

        try:
            response = client.chat.completions.create(
                model=settings.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.85,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            variants = result.get("variants", [])
            logger.info(f"Variantes A/B geradas | num={len(variants)} | produto={context.product_name}")
            return variants

        except OpenAIError as exc:
            logger.error(f"Erro OpenAI ao gerar variantes A/B: {exc}")
            raise ValueError(f"Erro na API OpenAI: {exc}")

    # =========================================================================
    # OPTIMIZATION ANALYSIS
    # =========================================================================

    def analyze_metrics_and_suggest(self, metrics: dict[str, Any], context: str) -> dict[str, Any]:
        """
        Analisa métricas de uma campanha e sugere ações de otimização com IA.

        Complementa as regras de otimização determinísticas com
        análise contextual e sugestões estratégicas.
        """
        client = _get_client()

        system_prompt = (
            "Você é um especialista em performance de Meta Ads. "
            "Analisa métricas de campanha e sugere ações práticas de otimização. "
            "Seja direto e específico. Responda APENAS com JSON válido."
        )

        user_prompt = f"""Analise as métricas desta campanha Meta Ads e sugira ações:

Contexto: {context}

Métricas atuais:
{json.dumps(metrics, indent=2, ensure_ascii=False)}

Retorne APENAS este JSON:
{{
    "performance_grade": "A/B/C/D/F",
    "summary": "Resumo em 1-2 frases do desempenho geral",
    "critical_issues": ["problemas críticos que precisam de ação imediata"],
    "suggestions": [
        {{
            "priority": "alta/média/baixa",
            "action": "ação específica a tomar",
            "reason": "por que essa ação melhora a performance"
        }}
    ],
    "copy_recommendation": "Sugestão sobre o copy atual (manter/testar/reescrever)",
    "budget_recommendation": "Sugestão sobre o orçamento (aumentar/manter/reduzir)"
}}"""

        try:
            response = client.chat.completions.create(
                model=settings.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            logger.info("Análise de métricas com IA concluída")
            return result

        except OpenAIError as exc:
            logger.error(f"Erro OpenAI ao analisar métricas: {exc}")
            raise ValueError(f"Erro na API OpenAI: {exc}")

    # =========================================================================
    # FULL AD CREATION (ORCHESTRATOR)
    # =========================================================================

    def prepare_full_ad_content(
        self,
        context: AIContext,
        custom_copy: dict | None = None,
        custom_targeting: dict | None = None,
        custom_image_url: str | None = None,
        generate_image: bool = True,
        custom_campaign_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Prepara todo o conteúdo do anúncio usando IA, respeitando overrides manuais.

        Retorna um dict com:
          - copy: headline, primary_text, description, cta, campaign_name
          - targeting: spec completo da Meta API
          - image: url, prompt, model
          - ai_generated_fields: quais campos foram gerados pela IA
        """
        ai_generated_fields = []
        result: dict[str, Any] = {}

        # --- Copy ---
        if custom_copy:
            result["copy"] = custom_copy
            logger.info("Copy: usando override manual.")
        else:
            result["copy"] = self.generate_copy(context)
            ai_generated_fields.append("copy")

        # Aplica nome de campanha personalizado se fornecido
        if custom_campaign_name:
            result["copy"]["campaign_name"] = custom_campaign_name

        # --- Targeting ---
        if custom_targeting:
            result["targeting"] = custom_targeting
            logger.info("Targeting: usando override manual.")
        else:
            audience_data = self.generate_audience(context)
            result["targeting"] = audience_data.get("targeting", {})
            result["audience_info"] = {
                "description": audience_data.get("description"),
                "suggested_interests": audience_data.get("suggested_interests", []),
                "estimated_reach": audience_data.get("estimated_reach_range"),
            }
            ai_generated_fields.append("targeting")

        # --- Imagem ---
        if custom_image_url:
            result["image"] = {"url": custom_image_url, "source": "manual"}
            logger.info("Imagem: usando URL manual.")
        elif generate_image:
            image_prompt = result["copy"].get("image_prompt", f"Professional ad image for {context.product_name}")
            result["image"] = self.generate_image(image_prompt)
            ai_generated_fields.append("image")
        else:
            result["image"] = None

        result["ai_generated_fields"] = ai_generated_fields
        return result
