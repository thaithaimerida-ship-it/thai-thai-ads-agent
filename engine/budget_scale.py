"""
budget_scale.py — BA2: Acelerador de Campañas de Alto Rendimiento

Detecta campañas que ya probaron ser rentables (CPA ideal) y están siendo limitadas
por presupuesto (alta utilización), y propone escalar la inversión.

Dos sub-señales:
  BA2_REALLOC — reubica fondos liberados por BA1 (costo neto = $0)
  BA2_SCALE   — requiere nueva inversión

Incrementos ≤20% se auto-ejecutan vía Fase 6C.AUTO en auditor.py (si AUTO_EXECUTE_ENABLED=true).
Incrementos >20% quedan como propuesta informativa para el operador.

Cruce con datos de negocio (negocio_data de Sheets):
  Cuando negocio_data está disponible, se abre una vía alternativa de elegibilidad
  para campañas que Google Ads reporta con 0 conversiones pero que demuestran
  ROI real en el negocio:
    - Delivery: venta_plataformas_neto / gasto_ads > 5x → candidata a escalar
    - Local:    comensales > 0 y venta_local / gasto_ads > 3x → candidata a escalar
  Estas propuestas incluyen roi_real, venta_real y fuente_datos="sheets+ads".
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _roi_real_ratio(
    campaign_type: str,
    ads_cost_mxn: float,
    negocio_data: dict,
) -> tuple:
    """
    Calcula el ROI real del negocio para el tipo de campaña.
    Retorna (roi_ratio, venta_real_mxn, campo_sheets) o (None, None, None).
    """
    if not negocio_data or ads_cost_mxn <= 0:
        return None, None, None

    if campaign_type in ("local", "default"):
        venta = float(negocio_data.get("venta_local_total") or 0)
        campo = "venta_local_total"
    elif campaign_type == "delivery":
        venta = float(negocio_data.get("venta_plataformas_neto") or 0)
        campo = "venta_plataformas_neto"
    else:
        return None, None, None

    if venta <= 0:
        return None, None, campo

    return round(venta / ads_cost_mxn, 2), round(venta, 2), campo


def detect_scale_opportunities(
    campaigns: List[Dict[str, Any]],
    campaign_type_config: Dict[str, Any],
    ba2_config: Dict[str, Any],
    ba1_candidates: Optional[List[Dict[str, Any]]] = None,
    evidence_days: int = 14,
    negocio_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detecta campañas candidatas a escalar presupuesto.

    Args:
        campaigns:            Lista de campañas con métricas del período de evidencia.
        campaign_type_config: CAMPAIGN_TYPE_CONFIG de agent_config (CPA targets por tipo).
        ba2_config:           Sección "ba2" de CAMPAIGN_HEALTH_CONFIG.
        ba1_candidates:       Campañas marcadas por BA1 para reducción de presupuesto.
                              Usado para calcular fondos liberados (BA2_REALLOC).
        evidence_days:        Días de la ventana de evidencia (debe coincidir con BA1).
        negocio_data:         Dict de resumen_negocio_para_agente() — opcional.
                              Cuando está disponible, abre vía alternativa de elegibilidad
                              basada en ROI real del negocio (Sheets + Ads).

    Returns:
        {
            "proposals": [...],        # Lista de propuestas BA2
            "freed_budget_mxn": float, # Fondos diarios liberados por BA1 (para REALLOC)
            "total_realloc_mxn": float, # Total a reasignar via REALLOC
            "total_scale_mxn": float,   # Total nueva inversión sugerida via SCALE
        }
    """
    proposals: List[Dict[str, Any]] = []

    min_conversions = ba2_config.get("min_conversions", 3)
    utilization_threshold = ba2_config.get("utilization_threshold", 0.85)
    max_scale_pct = ba2_config.get("max_scale_pct", 0.30)
    max_scale_abs_mxn = ba2_config.get("max_scale_abs_mxn", 80.0)
    by_type = ba2_config.get("by_type", {})

    # ROI mínimo para elegibilidad vía Sheets cuando Google Ads no reporta conversiones
    ROI_SHEETS_DELIVERY = 5.0
    ROI_SHEETS_LOCAL    = 3.0

    # Calcular fondos diarios liberados por BA1
    freed_daily_mxn = _calc_freed_budget(ba1_candidates or [])

    available_realloc = freed_daily_mxn  # MXN/día disponibles para reasignar

    for camp in campaigns:
        name = camp.get("name", "")
        camp_id = camp.get("id")
        cost_micros = camp.get("cost_micros", 0)
        conversions = camp.get("conversions", 0.0)
        daily_budget_mxn = camp.get("daily_budget_mxn", 0.0)
        days_active = camp.get("days_active")

        cost_mxn = cost_micros / 1_000_000

        # --- Determinar tipo de campaña ---
        try:
            from engine.risk_classifier import get_campaign_type as _get_type
            camp_type = _get_type(name, str(camp_id) if camp_id else "")
        except Exception:
            camp_type = _infer_campaign_type(name, campaign_type_config)
        type_cfg = campaign_type_config.get(camp_type, campaign_type_config.get("default", {}))
        ba2_type_cfg = by_type.get(camp_type, by_type.get("default", {}))

        min_days_active = ba2_type_cfg.get("min_days_active", 14)
        cpa_ideal = type_cfg.get("cpa_ideal", 0.0)
        cpa_max = type_cfg.get("cpa_max", 0.0)

        # --- Guardrail 1: Período de aprendizaje ---
        if days_active is None or days_active < min_days_active:
            logger.debug(
                "BA2 skip %s — days_active=%s < min_days_active=%s",
                name, days_active, min_days_active,
            )
            continue

        # --- Guardrail 3: Presupuesto diario debe ser > 0 ---
        if daily_budget_mxn <= 0:
            continue

        # ── Vía 1: Elegibilidad estándar (Google Ads conversiones) ─────────────
        roi_ratio, venta_real, campo_sheets = _roi_real_ratio(camp_type, cost_mxn, negocio_data)

        via_sheets = False
        cpa_actual = None

        if conversions >= min_conversions:
            # Conversiones suficientes en Google Ads — evaluar CPA
            cpa_actual = cost_mxn / conversions if conversions > 0 else None

            if cpa_actual is None or cpa_ideal <= 0:
                continue

            if cpa_actual > cpa_max:
                logger.debug("BA2 skip %s — CPA %.1f > cpa_max %.1f", name, cpa_actual, cpa_max)
                continue

            if cpa_actual > cpa_ideal:
                logger.debug("BA2 skip %s — CPA %.1f en zona gris (ideal=%.1f)", name, cpa_actual, cpa_ideal)
                continue

        else:
            # ── Vía 2: Elegibilidad por ROI real de Sheets ────────────────────
            # Campañas con 0 conversiones en Google Ads pero buen desempeño real.
            # Local puede tener 0 conv en Ads (mide Maps/offline) pero generar
            # comensales y ventas en efectivo/tarjeta.
            if roi_ratio is None:
                logger.debug(
                    "BA2 skip %s — conversiones %.1f < min=%d y sin datos de Sheets",
                    name, conversions, min_conversions,
                )
                continue

            roi_threshold = ROI_SHEETS_DELIVERY if camp_type == "delivery" else ROI_SHEETS_LOCAL
            comensales = int(negocio_data.get("comensales_total") or 0) if negocio_data else 0

            # Local: requiere comensales > 0 como señal adicional de actividad real
            if camp_type in ("local", "default") and comensales == 0:
                logger.debug("BA2 skip %s — local con 0 comensales en Sheets", name)
                continue

            if roi_ratio < roi_threshold:
                logger.debug(
                    "BA2 skip %s — ROI real %.1fx < umbral %.1fx",
                    name, roi_ratio, roi_threshold,
                )
                continue

            via_sheets = True
            logger.info(
                "BA2 candidato vía Sheets: %s | tipo=%s | ROI_real=%.1fx | "
                "%s=$%.0f | gasto_ads=$%.0f",
                name, camp_type, roi_ratio, campo_sheets, venta_real, cost_mxn,
            )
        # ──────────────────────────────────────────────────────────────────────

        # --- Señal de saturación: Budget Utilization Rate ---
        budget_period_mxn = daily_budget_mxn * evidence_days
        utilization_rate = cost_mxn / budget_period_mxn if budget_period_mxn > 0 else 0.0

        if utilization_rate < utilization_threshold:
            logger.debug(
                "BA2 skip %s — utilization=%.2f < threshold=%.2f (no saturado)",
                name, utilization_rate, utilization_threshold,
            )
            continue

        # --- Campaña candidata: elegible + presupuesto saturado ---
        scale_by_pct = min(max_scale_pct, 1.0)
        suggested_increase_mxn = min(
            daily_budget_mxn * scale_by_pct,
            max_scale_abs_mxn,
        )
        new_budget_mxn = round(daily_budget_mxn + suggested_increase_mxn, 2)
        actual_increase = round(new_budget_mxn - daily_budget_mxn, 2)

        # Determinar sub-señal: REALLOC o SCALE
        if available_realloc >= actual_increase:
            signal = "BA2_REALLOC"
            available_realloc -= actual_increase
            fund_source = f"fondos liberados por BA1 (${actual_increase:.0f} MXN/día reasignados)"
        else:
            signal = "BA2_SCALE"
            fund_source = f"nueva inversión requerida: +${actual_increase:.0f} MXN/día"

        proposal: Dict[str, Any] = {
            "type": "budget_scale",
            "signal": signal,
            "campaign_id": camp_id,
            "campaign_name": name,
            "campaign_type": camp_type,
            "current_daily_budget_mxn": daily_budget_mxn,
            "suggested_daily_budget_mxn": new_budget_mxn,
            "increase_mxn": actual_increase,
            "cpa_actual": round(cpa_actual, 2) if cpa_actual is not None else None,
            "cpa_ideal": cpa_ideal,
            "cpa_max": cpa_max,
            "conversions": conversions,
            "cost_mxn": round(cost_mxn, 2),
            "utilization_rate": round(utilization_rate, 3),
            "days_active": days_active,
            "fund_source": fund_source,
            "evidence_days": evidence_days,
            "fuente_datos": "sheets+ads" if via_sheets else "ads",
        }

        # Enriquecer con ROI real si está disponible
        if roi_ratio is not None:
            proposal["roi_real"]   = roi_ratio
            proposal["venta_real"] = venta_real

        proposals.append(proposal)

        if via_sheets:
            logger.info(
                "BA2 candidato (Sheets): %s | señal=%s | ROI_real=%.1fx | util=%.0f%% | +$%.0f MXN/día",
                name, signal, roi_ratio, utilization_rate * 100, actual_increase,
            )
        else:
            logger.info(
                "BA2 candidato: %s | señal=%s | CPA=%.1f | util=%.0f%% | +$%.0f MXN/día",
                name, signal, cpa_actual, utilization_rate * 100, actual_increase,
            )

    total_realloc = sum(p["increase_mxn"] for p in proposals if p["signal"] == "BA2_REALLOC")
    total_scale = sum(p["increase_mxn"] for p in proposals if p["signal"] == "BA2_SCALE")

    return {
        "proposals": proposals,
        "freed_budget_mxn": freed_daily_mxn,
        "total_realloc_mxn": round(total_realloc, 2),
        "total_scale_mxn": round(total_scale, 2),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_freed_budget(ba1_candidates: List[Dict[str, Any]]) -> float:
    """
    Suma los ahorros diarios estimados de las propuestas BA1 (reducción de presupuesto).
    Usa 'suggested_daily_budget_mxn' y 'current_daily_budget_mxn' cuando estén disponibles.
    """
    freed = 0.0
    for c in ba1_candidates:
        current = c.get("current_daily_budget_mxn", 0.0)
        suggested = c.get("suggested_daily_budget_mxn")
        if suggested is not None and current > suggested:
            freed += current - suggested
    return round(freed, 2)


def _infer_campaign_type(campaign_name: str, campaign_type_config: Dict[str, Any]) -> str:
    """
    Infiere el tipo de campaña desde su nombre usando las keywords de CAMPAIGN_TYPE_CONFIG.
    Retorna la clave del tipo (e.g., "delivery", "reservaciones", "local") o "default".
    """
    name_lower = campaign_name.lower()
    for type_key, type_cfg in campaign_type_config.items():
        if type_key == "default":
            continue
        keywords = type_cfg.get("keywords", [])
        if any(kw.lower() in name_lower for kw in keywords):
            return type_key
    return "default"
