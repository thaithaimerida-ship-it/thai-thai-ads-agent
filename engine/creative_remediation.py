"""
Creative Remediation — genera headlines/descriptions para anuncios con Ad Strength POOR o AVERAGE.

Usa Claude Sonnet 4.6 para generar copy y retorna una lista de acciones para el Executor.
Si Sonnet falla o el JSON es inválido, retorna lista vacía (nunca lanza excepción).
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# Guardrails por ciclo
_MAX_HEADLINES_PER_AD    = 5
_MAX_DESCRIPTIONS_PER_AD = 2

_SYSTEM_PROMPT = """Eres el Copywriter de Thai Thai, restaurante tailandés artesanal en Mérida, Yucatán.

CONTEXTO DEL NEGOCIO:
- Restaurante de comida tailandesa artesanal
- Platos estrella: Pad Thai, Curry Verde, Curry Rojo, Spring Rolls, Tom Kha (sopa de coco)
- Ubicación: Calle 30 No. 351, Col. Emiliano Zapata Norte, Mérida
- Público: turistas + locales en Mérida"""


def remediate_weak_ads(
    ad_health_data: list,
    keyword_quality_data: list,
    negocio_data: dict = None,
) -> list:
    """
    Genera propuestas de headlines/descriptions para anuncios POOR o AVERAGE.

    Args:
        ad_health_data:       Lista de dicts de fetch_ad_health()
        keyword_quality_data: Lista de dicts de fetch_keyword_quality_scores()
        negocio_data:         Dict opcional de resumen_negocio_para_agente()

    Returns:
        Lista de acciones:
        [{"action": "add_headlines"|"add_descriptions", "ad_id", "ad_group_resource",
          "campaign_name", "headlines"|"descriptions", "reasoning"}]
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("creative_remediation: ANTHROPIC_API_KEY no configurada — skip")
        return []

    if not ad_health_data:
        return []

    # Candidatos grupo 1: POOR o AVERAGE con < 8 headlines o < 3 descriptions
    candidates_strength = [
        ad for ad in ad_health_data
        if ad.get("ad_strength") in ("POOR", "AVERAGE")
        and (len(ad.get("headlines", [])) < 8 or len(ad.get("descriptions", [])) < 3)
    ]

    # Candidatos grupo 2: marcados _qs_triggered=True (QS bajo, sin importar conteo de headlines)
    _strength_ad_ids = {ad.get("ad_id") for ad in candidates_strength}
    candidates_qs = [
        ad for ad in ad_health_data
        if ad.get("_qs_triggered") and ad.get("ad_id") not in _strength_ad_ids
    ]

    candidates = candidates_strength + candidates_qs
    if not candidates:
        return []

    # Índice de keywords ganadoras por campaña (QS ≥ 4, con costo)
    kw_by_campaign: dict = {}
    # Índice de keywords con QS bajo por campaña (para remediación QS)
    qs_low_kw_by_campaign: dict = {}
    for kw in keyword_quality_data:
        cid = kw.get("campaign_id", "")
        qs  = kw.get("quality_score") or 0
        if qs >= 4 and kw.get("cost_micros", 0) > 0:
            kw_by_campaign.setdefault(cid, []).append(kw.get("keyword_text", ""))
        if qs and qs < 7:
            qs_low_kw_by_campaign.setdefault(cid, []).append(kw.get("keyword_text", ""))

    actions = []
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        logger.warning("creative_remediation: no se pudo inicializar Anthropic — %s", e)
        return []

    for ad in candidates:
        ad_id          = ad.get("ad_id", "")
        campaign_id    = ad.get("campaign_id", "")
        campaign_name  = ad.get("campaign_name", "")
        ad_group_res   = ad.get("ad_group_resource", "")
        existing_heads = ad.get("headlines", [])
        existing_descs = ad.get("descriptions", [])
        ad_strength    = ad.get("ad_strength", "AVERAGE")
        is_qs_triggered = bool(ad.get("_qs_triggered"))

        winning_kws    = kw_by_campaign.get(campaign_id, [])[:10]
        qs_low_kws     = qs_low_kw_by_campaign.get(campaign_id, [])[:10]
        campaign_type  = _infer_campaign_type(campaign_name)

        needs_headlines    = len(existing_heads) < 8
        needs_descriptions = len(existing_descs) < 3

        if is_qs_triggered:
            user_prompt = f"""HEADLINES ACTUALES DEL ANUNCIO (no duplicar):
{chr(10).join(f'- {h}' for h in existing_heads) if existing_heads else '(ninguno)'}

KEYWORDS CON QUALITY SCORE BAJO EN ESTA CAMPAÑA (QS < 7):
{chr(10).join(f'- {k}' for k in qs_low_kws) if qs_low_kws else '(sin datos)'}

TIPO DE CAMPAÑA: {campaign_type}
AD STRENGTH ACTUAL: {ad_strength}

INSTRUCCIONES:
Las keywords de esta campaña tienen Quality Score bajo — el copy de los headlines no es suficientemente relevante para las búsquedas de los usuarios.
Genera headlines MÁS RELEVANTES que incluyan las keywords con QS bajo de forma natural.
- Headlines: máximo 30 caracteres cada uno. Incorporar las keywords de forma directa y natural.
- No duplicar headlines que ya existen.
- No agregar descriptions en esta respuesta (dejar lista vacía).
- Responde SOLO con JSON válido, sin markdown.

Formato:
{{
  "new_headlines": ["headline1", "headline2"],
  "new_descriptions": [],
  "reasoning": "una frase explicando cómo los nuevos headlines mejoran la relevancia para las keywords"
}}"""
        else:
            user_prompt = f"""HEADLINES ACTUALES DEL ANUNCIO (no duplicar):
{chr(10).join(f'- {h}' for h in existing_heads) if existing_heads else '(ninguno)'}

KEYWORDS GANADORAS DE ESTA CAMPAÑA:
{chr(10).join(f'- {k}' for k in winning_kws) if winning_kws else '(sin datos)'}

TIPO DE CAMPAÑA: {campaign_type}
AD STRENGTH ACTUAL: {ad_strength}

INSTRUCCIONES:
Genera headlines y descriptions NUEVOS que complementen los existentes.
- Headlines: máximo 30 caracteres cada uno. Incluir nombre "Thai Thai", ubicación "Mérida", platos estrella, llamadas a la acción.
- Descriptions: máximo 90 caracteres cada uno. Describir la experiencia, mencionar delivery si aplica, reservaciones.
- No duplicar headlines que ya existen.
- Responde SOLO con JSON válido, sin markdown.

Formato:
{{
  "new_headlines": ["headline1", "headline2"],
  "new_descriptions": ["desc1", "desc2"],
  "reasoning": "una frase explicando la estrategia"
}}"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
            # Limpiar markdown si hay
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
        except Exception as e:
            logger.warning("creative_remediation: Sonnet falló para ad %s — %s", ad_id, e)
            continue

        new_heads = data.get("new_headlines", [])
        new_descs = data.get("new_descriptions", [])
        reasoning  = data.get("reasoning", "")

        # Validar longitudes y deduplicar
        valid_heads = [
            h for h in new_heads
            if isinstance(h, str) and len(h) <= 30 and h not in existing_heads
        ][:_MAX_HEADLINES_PER_AD]
        valid_descs = [
            d for d in new_descs
            if isinstance(d, str) and len(d) <= 90 and d not in existing_descs
        ][:_MAX_DESCRIPTIONS_PER_AD]

        if valid_heads:
            _action = "replace_headlines" if is_qs_triggered else "add_headlines"
            if is_qs_triggered or needs_headlines:
                actions.append({
                    "action":            _action,
                    "ad_id":             ad_id,
                    "ad_group_resource": ad_group_res,
                    "campaign_name":     campaign_name,
                    "headlines":         valid_heads,
                    "reasoning":         reasoning,
                })
        if valid_descs and needs_descriptions:
            actions.append({
                "action":            "add_descriptions",
                "ad_id":             ad_id,
                "ad_group_resource": ad_group_res,
                "campaign_name":     campaign_name,
                "descriptions":      valid_descs,
                "reasoning":         reasoning,
            })

    return actions


def _infer_campaign_type(campaign_name: str) -> str:
    name = campaign_name.lower()
    if "delivery" in name or "rappi" in name or "uber" in name:
        return "delivery"
    if "reserva" in name:
        return "reservaciones"
    if "local" in name or "experiencia" in name:
        return "local / tráfico físico"
    return "general"
