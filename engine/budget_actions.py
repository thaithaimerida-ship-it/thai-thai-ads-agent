"""
Thai Thai Ads Agent — Detector de Oportunidades de Presupuesto (Fase 6B MVP)

Señal implementada:
  BA1 — CPA crítico con gasto relevante: propone reducción de presupuesto diario
        cuando el CPA real supera el umbral crítico del tipo de campaña y el gasto
        en la ventana de análisis es significativo.

Señales excluidas del MVP:
  BA2 — Escalar presupuesto en campaña con CPA saludable y limitación de impresiones
        (requiere datos de impression share; Fase 6B.1).

Función pura — no realiza llamadas a la API de Google Ads ni a SQLite.
Testeable con datos sintéticos, sin dependencias externas.

Criterios BA1:
  1. status == ENABLED
  2. conversiones >= min_conversions (mínimo para CPA estadísticamente válido)
  3. CPA real > cpa_critical del tipo
  4. costo en ventana >= min_spend_window del tipo
  5. days_active >= min_days_active del tipo (si disponible — guarda de campaña nueva)

Presupuesto sugerido:
  suggested = current_daily * (cpa_max / cpa_real)
  Piso de seguridad: no sugerir por debajo del budget_floor_pct (30%) del presupuesto actual.

Nota técnica — silencio post-aprobación (6B.1 pendiente):
  Una propuesta aprobada puede reaparecer en el siguiente ciclo si el operador
  no ha hecho el cambio en Google Ads, porque el CPA seguirá siendo crítico.
  La protección de re-propuesta queda como deuda técnica de Fase 6B.1.
"""

from config.agent_config import (
    CAMPAIGN_TYPE_CONFIG,
    CAMPAIGN_HEALTH_CONFIG,
)


# ── Utilidades internas ───────────────────────────────────────────────────────

def _cost_mxn(campaign: dict) -> float:
    """Convierte cost_micros a MXN. Acepta también cost_mxn directo (para tests)."""
    if "cost_mxn" in campaign:
        return float(campaign["cost_mxn"])
    return float(campaign.get("cost_micros", 0)) / 1_000_000


def _campaign_name(campaign: dict) -> str:
    return str(campaign.get("name") or campaign.get("campaign_name") or "")


def _campaign_id(campaign: dict) -> str:
    return str(campaign.get("id") or campaign.get("campaign_id") or "")


def _get_campaign_type(name: str, campaign_id: str) -> str:
    """Reutiliza risk_classifier para resolver el tipo de campaña."""
    from engine.risk_classifier import get_campaign_type
    return get_campaign_type(name, campaign_id)


def _type_cfg(campaign_type: str) -> dict:
    return CAMPAIGN_TYPE_CONFIG.get(campaign_type, CAMPAIGN_TYPE_CONFIG["default"])


def _suggest_budget(current_budget: float, cpa_real: float, cpa_max: float,
                    floor_pct: float = 0.30) -> float:
    """
    Calcula el presupuesto diario sugerido para llevar el CPA hacia cpa_max.

    Fórmula: suggested = current * (cpa_max / cpa_real)
    Si la tasa de conversión se mantiene constante, el nuevo CPA converge a cpa_max.
    Piso de seguridad: no bajar de floor_pct del presupuesto actual.
    """
    if cpa_real <= 0 or cpa_max <= 0 or current_budget <= 0:
        return current_budget
    ratio = cpa_max / cpa_real
    suggested = current_budget * ratio
    floor = current_budget * floor_pct
    return round(max(suggested, floor), 2)


# ── Función pública ───────────────────────────────────────────────────────────

def detect_budget_opportunities(campaigns: list) -> list:
    """
    Detecta señal BA1 en campañas activas.

    Solo evalúa campañas con status 'ENABLED'.
    Solo propone (RISK_PROPOSE) — nunca ejecuta automáticamente.

    Cada candidato retornado incluye evidencia completa:
      signal                — 'BA1'
      campaign_id           — ID de la campaña
      campaign_name         — nombre de la campaña
      campaign_type         — tipo resuelto ('delivery', 'reservaciones', etc.)
      cost_mxn              — gasto total en MXN en la ventana
      conversions           — conversiones en la ventana
      cpa_real              — CPA real calculado
      cpa_critical          — umbral crítico del tipo
      cpa_max               — CPA máximo tolerable del tipo
      daily_budget_mxn      — presupuesto diario actual (0 si no disponible)
      suggested_daily_budget — presupuesto diario sugerido (None si no hay budget)
      reduction_pct         — reducción propuesta en % (None si no hay budget)
      days_active           — días activa la campaña (None si no disponible)
      min_spend_window      — umbral de gasto mínimo en ventana para BA1
      min_days_active       — protección mínima de días del tipo
      reason                — texto descriptivo con evidencia

    Returns:
      Lista de dicts ordenada por gasto descendente (mayor CPA waste primero).
    """
    ba1_cfg = CAMPAIGN_HEALTH_CONFIG.get("ba1", {})
    ba1_by_type = ba1_cfg.get("by_type", {})
    min_conv = ba1_cfg.get("min_conversions", 2)
    floor_pct = ba1_cfg.get("budget_floor_pct", 0.30)
    evidence_window = ba1_cfg.get("evidence_window_days", 14)

    candidates = []

    for camp in campaigns:
        # Solo campañas habilitadas
        if str(camp.get("status", "")).upper() != "ENABLED":
            continue

        name = _campaign_name(camp)
        cid = _campaign_id(camp)
        campaign_type = _get_campaign_type(name, cid)
        type_cfg = _type_cfg(campaign_type)
        ba1_type_cfg = ba1_by_type.get(campaign_type, ba1_by_type.get("default", {}))

        cost = _cost_mxn(camp)
        conversions = float(camp.get("conversions", 0))
        days_active = camp.get("days_active")
        daily_budget_mxn = float(camp.get("daily_budget_mxn") or 0)

        cpa_critical = type_cfg.get("cpa_critical", 100.0)
        cpa_max = type_cfg.get("cpa_max", 60.0)
        min_spend_window = ba1_type_cfg.get("min_spend_window", 250.0)
        min_days = ba1_type_cfg.get("min_days_active", 14)

        # Guarda 1: antigüedad mínima (campaña nueva)
        if days_active is not None and days_active < min_days:
            continue

        # Guarda 2: conversiones mínimas para CPA estadísticamente válido
        if conversions < min_conv:
            continue

        # Guarda 3: gasto mínimo en ventana (evidencia relevante)
        if cost < min_spend_window:
            continue

        # BA1: CPA real > umbral crítico del tipo
        cpa_real = cost / conversions
        if cpa_real <= cpa_critical:
            continue

        # Calcular presupuesto sugerido
        if daily_budget_mxn > 0:
            suggested_daily = _suggest_budget(daily_budget_mxn, cpa_real, cpa_max, floor_pct)
            reduction_pct = round((1.0 - suggested_daily / daily_budget_mxn) * 100.0, 1)
        else:
            suggested_daily = None
            reduction_pct = None

        # Construir razón con evidencia completa
        reason_parts = [
            f"[{campaign_type}]",
            f"CPA real ${cpa_real:.2f} MXN > critico ${cpa_critical:.2f}",
            f"gasto ${cost:.2f} MXN (req. ${min_spend_window:.2f})",
            f"{conversions:.0f} conversiones en {evidence_window} dias",
        ]
        if days_active is not None:
            reason_parts.append(f"campana activa {days_active} dias (req. {min_days})")
        else:
            reason_parts.append("antiguedad: no disponible")
        if suggested_daily is not None:
            reason_parts.append(
                f"presupuesto sugerido: ${suggested_daily:.2f}/dia"
                f" (reduccion {reduction_pct}% desde ${daily_budget_mxn:.2f})"
            )

        candidates.append({
            "signal":                "BA1",
            "campaign_id":          cid,
            "campaign_name":        name,
            "campaign_type":        campaign_type,
            "cost_mxn":             round(cost, 2),
            "conversions":          conversions,
            "cpa_real":             round(cpa_real, 2),
            "cpa_critical":         cpa_critical,
            "cpa_max":              cpa_max,
            "daily_budget_mxn":     daily_budget_mxn,
            "suggested_daily_budget": suggested_daily,
            "reduction_pct":        reduction_pct,
            "days_active":          days_active,
            "min_spend_window":     min_spend_window,
            "min_days_active":      min_days,
            "reason":               " | ".join(reason_parts),
            # Campos necesarios para ejecución en /approve (Fase 6B.1)
            "budget_resource_name":    camp.get("budget_resource_name", ""),
            "budget_explicitly_shared":camp.get("budget_explicitly_shared", False),
        })

    # Ordenar por gasto descendente (mayor desperdicio primero)
    candidates.sort(key=lambda x: x["cost_mxn"], reverse=True)
    return candidates
