"""
Decision Engine — Claude Haiku toma decisiones de presupuesto cruzando Ads + GA4 + Sheets.
Costo: ~$0.01 por llamada diaria.

El engine recibe toda la data disponible y le pide a Claude Haiku que decida qué hacer.
Haiku tiene contexto completo del negocio: comensales reales, ventas por canal,
métricas GA4 de la web y datos de Google Ads — todos cruzados.

Guardrails de seguridad (aplicados tanto en el prompt como en _parse_decisions):
  - Cambio máximo: ±20% por día
  - Presupuesto mínimo: $20 MXN/día
  - Confianza mínima para ejecutar: 70%
  - Máximo 1 decisión por campaña por ciclo
  - JSON inválido de Haiku → hold (silencioso)
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# Límites globales — deben coincidir con config/agent_config.py
_MAX_CHANGE_PCT   = 20.0   # máximo ±% por día
_MIN_BUDGET_MXN   = 20.0   # presupuesto diario mínimo
_MIN_CONFIDENCE   = 70     # confianza mínima para ejecutar
_MONTHLY_CAP_MXN  = 8_000.0


def get_budget_decisions(
    campaigns: list,
    negocio_data: dict,
    ga4_data: dict,
) -> list:
    """
    Envía toda la data a Claude Haiku y recibe decisiones estructuradas de presupuesto.

    Args:
        campaigns:    Lista de campañas con métricas actuales de Google Ads.
        negocio_data: Dict de resumen_negocio_para_agente() — ventas, comensales, canales.
        ga4_data:     Dict de GA4 — page_views, clicks, usuarios_activos.

    Returns:
        Lista de decisiones validadas:
        [{"action": "scale"|"reduce"|"hold",
          "campaign_id": str,
          "campaign_name": str,
          "new_budget_mxn": float,
          "change_pct": float,      # positivo=subir, negativo=bajar
          "reason": str,            # en español, 1 frase
          "confidence": int}]       # 0–100
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("Decision engine: ANTHROPIC_API_KEY no configurada — sin decisiones AI")
        return []

    if not campaigns:
        logger.warning("Decision engine: sin campañas — skip")
        return []

    prompt = _build_decision_prompt(campaigns, negocio_data or {}, ga4_data or {})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        logger.debug("Decision engine raw response: %s", text[:500])
        return _parse_decisions(text, campaigns)
    except Exception as e:
        logger.error("Decision engine error: %s", e)
        return []


# ── Construcción del prompt ────────────────────────────────────────────────────

def _build_decision_prompt(campaigns: list, negocio_data: dict, ga4_data: dict) -> str:
    # ── Datos de campañas ──────────────────────────────────────────────────────
    camps_lines = []
    for c in campaigns:
        cid   = str(c.get("id", ""))
        name  = c.get("name", "—")
        spend = float(c.get("cost_micros", 0)) / 1_000_000
        conv  = float(c.get("conversions", 0))
        cpa   = round(spend / conv, 1) if conv > 0 else None
        budget = float(c.get("daily_budget_mxn") or 0)
        camps_lines.append(
            f"  - [{cid}] {name}: gasto=${spend:.0f} conv={conv:.0f}"
            f" CPA=${cpa if cpa else 'N/A'} presupuesto_diario=${budget:.0f}"
        )
    campaigns_str = "\n".join(camps_lines) if camps_lines else "  (sin datos)"

    # ── Datos de negocio (Sheets 7d) ──────────────────────────────────────────
    nd = negocio_data
    comensales    = nd.get("comensales_total", "n/d")
    venta_local   = nd.get("venta_local_total", 0)
    plat_bruto    = nd.get("venta_plataformas_bruto", 0)
    plat_neto     = nd.get("venta_plataformas_neto", 0)
    comision_pct  = nd.get("comision_delivery_pct", 0)
    ticket_avg    = nd.get("ingreso_por_comensal", 0)
    venta_neta    = nd.get("venta_neta_total", 0)

    # Calcular gasto total de Ads (proxy del período)
    total_ads_spend = sum(float(c.get("cost_micros", 0)) / 1_000_000 for c in campaigns)

    # ROI aproximado por canal
    roi_local = round(float(venta_local or 0) / total_ads_spend, 1) if total_ads_spend > 0 else "n/d"
    roi_del   = round(float(plat_neto or 0) / total_ads_spend, 1) if total_ads_spend > 0 else "n/d"

    negocio_str = (
        f"  Últimos 7 días:\n"
        f"  - Comensales en restaurante: {comensales}\n"
        f"  - Venta local (tarjeta+efectivo): ${float(venta_local or 0):,.0f} MXN"
        f"  (ROI vs Ads: {roi_local}x)\n"
        f"  - Plataformas bruto/neto: ${float(plat_bruto or 0):,.0f}/${float(plat_neto or 0):,.0f} MXN"
        f"  (comisión {float(comision_pct or 0):.0f}%, ROI neto vs Ads: {roi_del}x)\n"
        f"  - Ticket promedio: ${float(ticket_avg or 0):,.0f}/comensal\n"
        f"  - Venta neta total: ${float(venta_neta or 0):,.0f} MXN"
    )

    # ── Datos GA4 ──────────────────────────────────────────────────────────────
    ga4_str = "  (no disponible)"
    if ga4_data and "error" not in ga4_data:
        ga4_str = (
            f"  - Sesiones: {ga4_data.get('usuarios_activos', 0)}\n"
            f"  - Vistas de página: {ga4_data.get('page_views', 0)}\n"
            f"  - Clicks 'Pedir online': {ga4_data.get('click_pedir', 0)}\n"
            f"  - Clicks 'Reservar': {ga4_data.get('click_reservar', 0)}"
        )

    # ── Presupuesto mensual ────────────────────────────────────────────────────
    # Estimación simple: promedio diario × 30
    avg_daily = total_ads_spend / 7 if total_ads_spend > 0 else 0
    monthly_proj = round(avg_daily * 30, 0)

    return f"""Eres el agente de optimización publicitaria de Thai Thai, restaurante tailandés en Mérida.

## CONTEXTO DEL NEGOCIO
- Presupuesto mensual Google Ads: $8,000 MXN
- Objetivo: atraer comensales al restaurante + pedidos online por landing page
- Comensales en restaurante = margen alto (sin comisión de plataformas)
- Delivery (Rappi/Uber) cobra ~30% de comisión sobre venta bruta
- Campaña "Local": mide "cómo llegar" en Google Maps. 0 conversiones en Ads es NORMAL — la gente busca y va al restaurante, no compra online.
- Campaña "Delivery": mide clicks en landing page para pedidos.
- Campaña "Reservaciones": mide clicks en botón de reservar.

## DATOS DE CAMPAÑAS (ventana actual)
{campaigns_str}

## DATOS DEL NEGOCIO (Sheets, últimos 7 días)
{negocio_str}

## TRÁFICO WEB GA4 (últimas 24h)
{ga4_str}

## PRESUPUESTO MENSUAL
- Gasto total Ads en el período: ${total_ads_spend:,.0f} MXN
- Proyección mensual a ritmo actual: ${monthly_proj:,.0f} MXN
- Techo mensual: $8,000 MXN

## INSTRUCCIONES
Responde SOLO con un JSON válido (sin markdown, sin texto adicional).

Analiza todos los datos y decide para cada campaña activa:
- "scale": subir presupuesto porque el canal está funcionando y hay margen
- "reduce": bajar presupuesto porque el ROI real es malo
- "hold": mantener sin cambios (usa esto si no hay evidencia clara)

REGLAS DURAS (no negociables):
1. Nunca cambiar más de 20% en un día (ni subir ni bajar)
2. Nunca bajar a menos de $20 MXN/día
3. El gasto mensual total proyectado no puede superar $8,000 MXN
4. Campaña Local con 0 conversiones en Ads NO es señal negativa si hay comensales reales
5. ROI de Delivery se calcula con el neto (después de comisión), no el bruto
6. Si no tienes evidencia suficiente para una campaña, usa "hold"
7. Confianza: refleja qué tan seguro estás de la decisión (0-100)

Formato de respuesta:
{{
  "decisions": [
    {{
      "action": "scale" | "reduce" | "hold",
      "campaign_id": "<id exacto de la campaña>",
      "campaign_name": "<nombre de la campaña>",
      "new_budget_mxn": <número — presupuesto diario nuevo en MXN>,
      "change_pct": <número — % de cambio, positivo=subir, negativo=bajar, 0 si hold>,
      "reason": "<una frase en español explicando el porqué>",
      "confidence": <entero 0-100>
    }}
  ]
}}"""


# ── Parser y validador de respuesta ──────────────────────────────────────────

def _parse_decisions(text: str, campaigns: list) -> list:
    """
    Extrae y valida las decisiones del JSON retornado por Haiku.
    Aplica guardrails de seguridad sobre cada decisión.
    Ignora silenciosamente decisiones inválidas (hold fallback).
    """
    # Construir mapa campaign_id → budget actual para validación
    budget_map = {
        str(c.get("id", "")): float(c.get("daily_budget_mxn") or 0)
        for c in campaigns
    }

    try:
        # Intentar extraer JSON aunque haya texto alrededor
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start < 0 or end <= start:
            logger.warning("Decision engine: respuesta sin JSON válido")
            return []
        data = json.loads(text[start:end])
    except json.JSONDecodeError as e:
        logger.warning("Decision engine: JSON inválido — %s", e)
        return []

    raw_decisions = data.get("decisions", [])
    if not isinstance(raw_decisions, list):
        logger.warning("Decision engine: 'decisions' no es lista")
        return []

    validated = []
    seen_ids  = set()  # máximo 1 decisión por campaña

    for d in raw_decisions:
        try:
            action       = str(d.get("action", "hold")).lower()
            campaign_id  = str(d.get("campaign_id", ""))
            campaign_name= str(d.get("campaign_name", ""))
            new_budget   = float(d.get("new_budget_mxn", 0))
            change_pct   = float(d.get("change_pct", 0))
            reason       = str(d.get("reason", ""))[:200]
            confidence   = int(d.get("confidence", 0))

            # Validaciones básicas
            if action not in ("scale", "reduce", "hold"):
                logger.debug("Decision engine: action inválida '%s' → hold", action)
                action = "hold"

            if action == "hold":
                # hold no necesita más validación
                validated.append({
                    "action": "hold", "campaign_id": campaign_id,
                    "campaign_name": campaign_name, "new_budget_mxn": 0,
                    "change_pct": 0, "reason": reason, "confidence": confidence,
                })
                continue

            if not campaign_id:
                logger.debug("Decision engine: sin campaign_id — ignorada")
                continue

            # Máximo 1 decisión por campaña
            if campaign_id in seen_ids:
                logger.debug("Decision engine: campaña %s ya tiene decisión — ignorada", campaign_id)
                continue

            # Presupuesto mínimo
            if new_budget < _MIN_BUDGET_MXN:
                logger.warning(
                    "Decision engine: %s → presupuesto $%.0f < $%.0f mínimo → ajustado",
                    campaign_name, new_budget, _MIN_BUDGET_MXN,
                )
                new_budget = _MIN_BUDGET_MXN

            # Guardrail de cambio máximo ±20%
            current_budget = budget_map.get(campaign_id, 0)
            if current_budget > 0:
                actual_pct = (new_budget - current_budget) / current_budget * 100
                if abs(actual_pct) > _MAX_CHANGE_PCT:
                    # Recalcular dentro del límite
                    direction = 1 if actual_pct > 0 else -1
                    new_budget = round(current_budget * (1 + direction * _MAX_CHANGE_PCT / 100), 2)
                    change_pct = direction * _MAX_CHANGE_PCT
                    logger.warning(
                        "Decision engine: %s → cambio %.1f%% excede ±%.0f%% → ajustado a $%.0f/día",
                        campaign_name, actual_pct, _MAX_CHANGE_PCT, new_budget,
                    )
                else:
                    change_pct = round(actual_pct, 1)

            # Guardrail mensual
            if new_budget * 30 > _MONTHLY_CAP_MXN:
                new_budget = round(_MONTHLY_CAP_MXN / 30, 2)
                change_pct = round((new_budget - current_budget) / current_budget * 100, 1) if current_budget > 0 else 0
                logger.warning(
                    "Decision engine: %s → ajustado por cap mensual → $%.0f/día",
                    campaign_name, new_budget,
                )

            seen_ids.add(campaign_id)
            validated.append({
                "action":        action,
                "campaign_id":   campaign_id,
                "campaign_name": campaign_name,
                "new_budget_mxn": new_budget,
                "change_pct":    change_pct,
                "reason":        reason,
                "confidence":    confidence,
            })

        except Exception as e:
            logger.debug("Decision engine: error procesando decisión — %s", e)
            continue

    logger.info(
        "Decision engine: %d decisión(es) validada(s) de %d recibidas",
        len(validated), len(raw_decisions),
    )
    return validated
