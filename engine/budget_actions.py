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

Guardrail ROI real (Sheets):
  Si negocio_data está disponible, una campaña con CPA alto en Google Ads
  NO se propone para reducción si el ROI real del negocio es bueno:
    - Local:    venta_local_total / gasto_ads > 3x
    - Delivery: venta_plataformas_bruto / gasto_ads > 5x
  Esto protege campañas cuyas conversiones se miden fuera de Google Ads
  (Google Maps, visitas físicas, offline) pero que generan ingresos reales.

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
    SMALL_MODE_ENTRY_MIN_COST_RATIO,
    SMALL_MODE_CATEGORY_LIMITS,
    SMALL_MODE_ROLLBACK_CPA_WORSEN_PCT,
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


def _get_small_mode_context(campaign: dict) -> dict:
    from engine.risk_classifier import classify_campaign_functionally
    return classify_campaign_functionally(campaign)


def _has_clear_deterioration(campaign: dict, cpa_real: float) -> bool:
    prev_cpa = float(campaign.get("prev_cpa") or campaign.get("previous_cpa") or 0)
    if prev_cpa > 0 and cpa_real >= prev_cpa * (1 + SMALL_MODE_ROLLBACK_CPA_WORSEN_PCT / 100):
        return True
    return False


def _resolve_ba1_small_mode_decision(
    campaign: dict,
    campaign_type: str,
    cost: float,
    min_spend_window: float,
    cpa_real: float,
    cpa_critical: float,
    small_mode_context: dict,
) -> str:
    from engine.risk_classifier import (
        count_positive_signals,
        has_minimum_positive_signals,
        resolve_final_decision_label,
    )

    labels = [small_mode_context.get("decision_label", "hold")]
    blocking_signals = list(small_mode_context.get("blocking_signals", []))

    positive_signals = count_positive_signals(
        cost >= (min_spend_window * SMALL_MODE_ENTRY_MIN_COST_RATIO),
        cpa_real > cpa_critical,
        campaign_type != "unknown_safe",
    )

    if "cooldown_active" in blocking_signals:
        labels.append("hold")
    elif any(signal in blocking_signals for signal in (
        "tracking_broken",
        "landing_broken",
        "risk_blocked",
        "data_inconsistent",
        "classification_conflict",
        "low_classification_confidence",
    )):
        labels.append("no_action_risk")
    elif _has_clear_deterioration(campaign, cpa_real):
        labels.append("rollback_micro")
    elif has_minimum_positive_signals(positive_signals):
        labels.append("reduce_micro")
    else:
        labels.append("hold")

    return resolve_final_decision_label(labels)


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


def _roi_real_ratio(
    campaign_type: str,
    ads_cost_mxn: float,
    negocio_data: dict,
) -> tuple:
    """
    Calcula el ROI real del negocio para el tipo de campaña dado.

    Compara ingresos reales de Sheets contra gasto de Google Ads.
    Retorna (roi_ratio, venta_real_mxn, campo_sheets) o (None, None, None).

    - Local:    venta_local_total (tarjeta + efectivo) / ads_cost
    - Delivery: venta_plataformas_bruto (col H Cortes_de_Caja) / ads_cost

    Nota: los ingresos son totales del negocio, no atribuibles 100% a Ads.
    El ratio es un proxy de salud del canal, no atribución directa.
    """
    if not negocio_data or ads_cost_mxn <= 0:
        return None, None, None

    if campaign_type in ("local", "default"):
        venta = float(negocio_data.get("venta_local_total") or 0)
        campo = "venta_local_total"
    elif campaign_type == "delivery":
        venta = float(negocio_data.get("venta_plataformas_bruto") or 0)
        campo = "venta_plataformas_bruto"
    else:
        return None, None, None

    if venta <= 0:
        return None, None, campo

    return round(venta / ads_cost_mxn, 2), round(venta, 2), campo


# ── Función pública ───────────────────────────────────────────────────────────

def detect_budget_opportunities(campaigns: list, negocio_data: dict = None) -> list:
    """
    Detecta señal BA1 en campañas activas.

    Solo evalúa campañas con status 'ENABLED'.
    Solo propone (RISK_PROPOSE) — nunca ejecuta automáticamente.

    negocio_data: dict de resumen_negocio_para_agente() — opcional.
      Si está disponible, activa el guardrail de ROI real: campañas con CPA alto
      en Google Ads pero buen ROI de negocio (>3x local / >5x delivery) no se
      proponen para reducción de presupuesto.

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
      roi_real              — ratio ROI real vs gasto Ads (si negocio_data disponible)
      fuente_datos          — "ads" o "sheets+ads"

    Returns:
      Lista de dicts ordenada por gasto descendente (mayor CPA waste primero).
    """
    ba1_cfg = CAMPAIGN_HEALTH_CONFIG.get("ba1", {})
    ba1_by_type = ba1_cfg.get("by_type", {})
    min_conv = ba1_cfg.get("min_conversions", 2)
    floor_pct = ba1_cfg.get("budget_floor_pct", 0.30)
    evidence_window = ba1_cfg.get("evidence_window_days", 14)

    # Umbrales de ROI real para proteger campañas con buen desempeño de negocio
    ROI_PROTECT_LOCAL    = 3.0
    ROI_PROTECT_DELIVERY = 5.0

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

        # ── Guardrail ROI real (Sheets) ───────────────────────────────────────
        # Si el negocio muestra rentabilidad real suficiente, no proponer reducción.
        # CPA alto en Ads puede reflejar atribución incompleta (Maps, offline).
        roi_ratio, venta_real, campo_sheets = _roi_real_ratio(campaign_type, cost, negocio_data)

        if roi_ratio is not None:
            roi_threshold = ROI_PROTECT_DELIVERY if campaign_type == "delivery" else ROI_PROTECT_LOCAL
            if roi_ratio >= roi_threshold:
                import logging as _log
                _log.getLogger(__name__).info(
                    "BA1 skip %s — ROI real %.1fx ≥ %.1fx umbral "
                    "(%s=$%.0f vs gasto_ads=$%.0f) — campaña protegida",
                    name, roi_ratio, roi_threshold, campo_sheets, venta_real, cost,
                )
                continue  # No proponer reducción — el negocio es rentable
        # ─────────────────────────────────────────────────────────────────────

        # Calcular presupuesto sugerido
        if daily_budget_mxn > 0:
            suggested_daily = _suggest_budget(daily_budget_mxn, cpa_real, cpa_max, floor_pct)
            reduction_pct = round((1.0 - suggested_daily / daily_budget_mxn) * 100.0, 1)
        else:
            suggested_daily = None
            reduction_pct = None

        small_mode_context = _get_small_mode_context({
            **camp,
            "campaign_type": campaign_type,
            "cost_mxn": cost,
            "conversions": conversions,
        })
        if small_mode_context.get("small_mode_active"):
            final_action = _resolve_ba1_small_mode_decision(
                camp, campaign_type, cost, min_spend_window, cpa_real, cpa_critical, small_mode_context
            )
            decision_label = final_action
            if final_action == "reduce_micro" and daily_budget_mxn > 0:
                _limits = SMALL_MODE_CATEGORY_LIMITS.get(campaign_type, SMALL_MODE_CATEGORY_LIMITS["unknown_safe"])
                _micro_reduce_pct = float(_limits.get("reduce_pct", 0.0))
                if _micro_reduce_pct > 0:
                    _micro_budget = round(daily_budget_mxn * (1 - _micro_reduce_pct / 100.0), 2)
                    suggested_daily = max(suggested_daily or _micro_budget, _micro_budget)
                    reduction_pct = round((1.0 - suggested_daily / daily_budget_mxn) * 100.0, 1)
        else:
            decision_label = small_mode_context.get("decision_label", "hold")
            final_action = "reduce"

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

        candidate = {
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
            "category":             small_mode_context.get("category"),
            "classification_confidence": small_mode_context.get("classification_confidence"),
            "small_mode_active":    small_mode_context.get("small_mode_active", False),
            "blocking_signals":     small_mode_context.get("blocking_signals", []),
            "decision_label":       decision_label,
            "final_action":         final_action,
            # Campos necesarios para ejecución en /approve (Fase 6B.1)
            "budget_resource_name":    camp.get("budget_resource_name", ""),
            "budget_explicitly_shared":camp.get("budget_explicitly_shared", False),
        }

        # Enriquecer con ROI real si está disponible (aunque no alcanzó umbral de protección)
        if roi_ratio is not None:
            candidate["roi_real"]     = roi_ratio
            candidate["venta_real"]   = venta_real
            candidate["fuente_datos"] = "sheets+ads"
        else:
            candidate["fuente_datos"] = "ads"

        candidates.append(candidate)

    # Ordenar por gasto descendente (mayor desperdicio primero)
    candidates.sort(key=lambda x: x["cost_mxn"], reverse=True)
    return candidates
