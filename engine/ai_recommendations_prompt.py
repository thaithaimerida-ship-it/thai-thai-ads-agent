"""
Prompt templates para engine.ai_recommendations.

Separación estricta system/user (paso 4 del prompt-injection-reviewer):
- SYSTEM_PROMPT contiene instrucciones, dominio Thai Thai, schema esperado.
- build_user_prompt(payload) construye SOLO el bloque de datos, sanitizado.

Los search_terms se tratan como input ALTAMENTE HOSTIL: vienen de queries de
usuarios reales en Google, pueden contener intentos de prompt injection. La
sanitización:
1. Se serializan dentro de JSON (no concatenados a texto natural) — el modelo
   distingue datos de instrucciones cuando vienen estructurados.
2. Caracteres de control (\\x00-\\x1f, \\x7f) eliminados.
3. Truncados a 200 chars por término.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

# Caracteres de control que NO deben aparecer en datos serializados al modelo.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_SEARCH_TERM_LEN = 200


SYSTEM_PROMPT = """Eres un asistente analítico de Google Ads para Thai Thai, \
restaurante tailandés en Mérida, Yucatán.

Tu trabajo: revisar datos reales (Google Ads + GA4 + estado de landing) y \
proponer entre 3 y 5 acciones concretas en JSON.

CATEGORÍAS PERMITIDAS (action_type):
- "scale":         aumentar presupuesto. Solo si CPA bueno + conversiones reales + spend cap actual.
- "reduce":        bajar presupuesto. Solo si CPA > target + spend significativo (>$50/día).
- "negative":      agregar keyword negativa BROAD a nivel campaña. Solo de search terms con conversión 0 y gasto real. Máx 80 chars.
- "quality_alert": señal informativa que NO muta nada (CTR bajo, QS bajo, tracking roto, landing rota, ad rechazado).

REGLAS DURAS:
- Solo usa campaign_id que aparezcan en INPUT.campaigns. NO inventes ids.
- new_budget_mxn > 20 y <= 500.
- "reason" en español, frase concreta con métricas citadas. Máx 500 chars.
- "risk_level" = 2 siempre (todas son propuestas pendientes de aprobación).
- "urgency": "critical" solo si pérdida de dinero diaria significativa o caída de conversiones >50%; "urgent" si problema persiste >3 días; "normal" en cualquier otro caso.
- Devuelve entre 3 y 5 recomendaciones. Si no hay nada accionable, devuelve {"recommendations": []} — NO inventes acciones.
- NO incluyas categorías mixtas en una sola entrada. Cada recomendación es de un solo action_type.

CONTEXTO DEL NEGOCIO:
- CPA target campañas Delivery (campaign_name contiene "Delivery" sin "Search"): $50 ideal, $65 max, >$90 crítico.
- CPA target campañas Delivery Search (campaign_name contiene "Delivery Search"): $50 ideal, $70 max, >$100 crítico.
- CPA target campañas de reservas (Experiencia): $50 ideal, $85 max, >$120 crítico.
- Conversiones primarias: click_pedir_online (delivery) y click_whatsapp (contacto). NO proponer pausar campañas que las generen.
- Nota Delivery: click_pedir_online es el PROXY de conversión para campañas Delivery porque Gloria Food (proveedor del pedido) NO dispara eventos server-side de pedido completado en Google Ads. click_pedir_online cuenta como primaria por ser lo más cercano a un pedido confirmado que el agente puede medir desde la API.
- Métrica correcta: Local y Experiencia → all_conversions; Delivery → conversions (porque click_pedir_online es primaria).
- Smart Bidding en Experiencia 2026: período de aprendizaje activo, evitar mutaciones de budget en esa campaña por al menos 48h después de cualquier cambio.

FORMATO DE SALIDA:
JSON estricto, sin markdown, sin texto fuera del JSON. Schema:

{
  "recommendations": [
    {"action_type": "scale", "campaign_id": "...", "campaign_name": "...", "reason": "...", "urgency": "normal|urgent|critical", "risk_level": 2, "new_budget_mxn": float},
    {"action_type": "reduce", "campaign_id": "...", "campaign_name": "...", "reason": "...", "urgency": "...", "risk_level": 2, "new_budget_mxn": float},
    {"action_type": "negative", "campaign_id": "...", "campaign_name": "...", "reason": "...", "urgency": "...", "risk_level": 2, "keyword": "..."},
    {"action_type": "quality_alert", "campaign_id": "...", "campaign_name": "...", "reason": "...", "urgency": "...", "risk_level": 2, "alert_type": "low_quality_score|low_ctr|ad_disapproval|broken_landing|tracking_issue|other", "alert_text": "..."}
  ]
}

CUALQUIER cosa fuera del JSON (texto explicativo, markdown, comentarios) hace inválida la respuesta.
"""


def build_user_prompt(payload: dict[str, Any]) -> str:
    """Construye el bloque de datos sanitizado para el rol 'user'.

    payload esperado:
        {
            "campaigns": [{"id": str, "name": str, "spend": float, "conversions": float, "cpa": float, ...}],
            "search_terms": [{"term": str, "campaign_id": str, "clicks": int, "cost": float, "conversions": float, "competitor_term": bool}, ...],
            "ga4_funnel": {...},
            "landing_health": {...}
        }
    """
    sanitized = _sanitize_payload(payload)
    return f"INPUT:\n{json.dumps(sanitized, ensure_ascii=False, indent=2)}"


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Limpia campos derivados de input externo hostil (search terms sobre todo)."""
    cleaned = copy.deepcopy(payload)
    if isinstance(cleaned.get("search_terms"), list):
        cleaned["search_terms"] = [
            _sanitize_search_term(t) for t in cleaned["search_terms"] if isinstance(t, dict)
        ]
    return cleaned


def _sanitize_search_term(term: dict[str, Any]) -> dict[str, Any]:
    """Trunca y limpia caracteres de control en el campo 'term'.

    Los demás campos (clicks, cost, conversions, competitor_term, campaign_id)
    son numéricos/booleanos derivados de Google Ads — no requieren sanitización.
    """
    safe = dict(term)
    raw = safe.get("term")
    if isinstance(raw, str):
        cleaned = _CONTROL_CHAR_RE.sub("", raw)
        safe["term"] = cleaned[:_MAX_SEARCH_TERM_LEN]
    return safe
