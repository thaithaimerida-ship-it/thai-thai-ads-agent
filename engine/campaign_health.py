"""
Thai Thai Ads Agent — Detector de Salud de Campañas (Fase 6A MVP)

Señales implementadas:
  CH1 — CPA crítico: el CPA real de la campaña supera el umbral crítico
        de su tipo en la ventana de análisis.
  CH3 — Campaña sin conversiones con gasto relevante: 0 conv y gasto
        >= umbral del tipo, con protección conservadora para campañas nuevas.

Señal excluida del MVP:
  CH2 — Caída de CVR semana a semana (requiere doble ventana de API; Fase 6A.1).

Cruce con datos de negocio (negocio_data de Sheets):
  CH3 para campañas "local" con 0 conversiones en Google Ads se omite como alerta
  si el negocio muestra actividad real (comensales > 0 y venta_local > 0).
  La campaña Local mide "cómo llegar" en Google Maps, no compras web — tener
  0 conversiones en Ads no indica campaña muerta si hay comensales reales.
  Se registra como nota informativa en lugar de alerta de problema.

Función pura — no realiza llamadas a la API de Google Ads ni a SQLite.
Testeable con datos sintéticos, sin dependencias externas.

Los campos de entrada esperados en cada dict de campaña (de fetch_campaign_data()):
  id            (int|str)  — ID de campaña en Google Ads
  name          (str)      — nombre de campaña
  status        (str)      — p.ej. 'ENABLED', 'PAUSED'
  cost_micros   (int)      — gasto en micros MXN
  conversions   (float)    — conversiones en la ventana
  clicks        (int)      — clicks en la ventana
  impressions   (int)      — impresiones en la ventana
  days_active   (int|None) — días desde campaign.start_date (None si no disponible)
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


# ── Función pública ───────────────────────────────────────────────────────────

def detect_campaign_issues(campaigns: list, negocio_data: dict = None) -> list:
    """
    Detecta señales de salud CH1 y CH3 en campañas activas.

    Solo evalúa campañas con status 'ENABLED'.
    Solo propone (RISK_PROPOSE) — nunca ejecuta automáticamente.

    negocio_data: dict de resumen_negocio_para_agente() — opcional.
      Si está disponible, CH3 para campañas "local" con 0 conversiones se omite
      como alerta cuando el negocio muestra comensales > 0 y venta_local > 0.
      En su lugar se incluye una nota informativa con los datos reales.

    Cada candidato retornado incluye evidencia completa:
      signal            — 'CH1', 'CH3' o 'CH3_INFO' (nota sin alerta)
      campaign_id       — ID de la campaña
      campaign_name     — nombre de la campaña
      campaign_type     — tipo resuelto ('delivery', 'reservaciones', etc.)
      cost_mxn          — gasto total en MXN en la ventana
      conversions       — conversiones en la ventana
      cpa_real          — CPA real calculado (solo CH1)
      cpa_critical      — umbral crítico del tipo (solo CH1)
      min_spend         — umbral de gasto mínimo (solo CH3)
      days_active       — días activa la campaña (None si no disponible)
      min_days_active   — protección mínima de días del tipo
      days_protection_applied — True si se verificó antigüedad
      reason            — texto descriptivo con evidencia

    Returns:
      Lista de dicts ordenada por gasto descendente (mayor desperdicio primero).
    """
    ch1_cfg = CAMPAIGN_HEALTH_CONFIG.get("ch1", {})
    ch3_cfg = CAMPAIGN_HEALTH_CONFIG.get("ch3", {})
    ch3_by_type = ch3_cfg.get("by_type", {})

    candidates = []

    for camp in campaigns:
        # Solo campañas habilitadas
        if str(camp.get("status", "")).upper() != "ENABLED":
            continue

        name = _campaign_name(camp)
        cid = _campaign_id(camp)
        campaign_type = _get_campaign_type(name, cid)
        type_cfg = _type_cfg(campaign_type)

        cost = _cost_mxn(camp)
        conversions = float(camp.get("conversions", 0))
        days_active = camp.get("days_active")  # None si no disponible

        # ── CH1: CPA crítico ──────────────────────────────────────────────────
        cpa_critical = type_cfg.get("cpa_critical", 100.0)
        min_conv = ch1_cfg.get("min_conversions_for_cpa", 2)

        if conversions >= min_conv and cost > 0:
            cpa_real = cost / conversions
            if cpa_real > cpa_critical:
                reason_parts = [
                    f"[{campaign_type}]",
                    f"CPA real ${cpa_real:.2f} MXN > critico ${cpa_critical:.2f}",
                    f"gasto ${cost:.2f} MXN",
                    f"{conversions:.0f} conversiones en {ch1_cfg.get('evidence_window_days', 14)} dias",
                ]
                if days_active is not None:
                    reason_parts.append(f"campana activa {days_active} dias")
                else:
                    reason_parts.append("antiguedad: no disponible")

                candidates.append({
                    "signal":          "CH1",
                    "campaign_id":     cid,
                    "campaign_name":   name,
                    "campaign_type":   campaign_type,
                    "cost_mxn":        round(cost, 2),
                    "conversions":     conversions,
                    "cpa_real":        round(cpa_real, 2),
                    "cpa_critical":    cpa_critical,
                    "days_active":     days_active,
                    "reason":          " | ".join(reason_parts),
                })

        # ── CH3: campaña sin conversiones con gasto relevante ─────────────────
        ch3_type_cfg = ch3_by_type.get(campaign_type, ch3_by_type.get("default", {}))
        min_spend = ch3_type_cfg.get("min_spend", 350.0)
        min_days = ch3_type_cfg.get("min_days_active", 14)

        days_protection_applied = days_active is not None

        # Protección por antigüedad: si el dato existe y no supera el mínimo → omitir
        if days_active is not None and days_active < min_days:
            continue

        if conversions == 0 and cost >= min_spend:
            # ── Cruce con datos de negocio (Sheets) ──────────────────────────
            # Si la campaña es "local" y el negocio muestra actividad real,
            # no es una campaña muerta — mide Maps/offline, no conversiones web.
            # Registrar como nota informativa en lugar de alerta.
            if negocio_data and campaign_type in ("local", "default"):
                comensales = int(negocio_data.get("comensales_total") or 0)
                venta_local = float(negocio_data.get("venta_local_total") or 0)

                if comensales > 0 and venta_local > 0:
                    venta_total_dia = float(negocio_data.get("venta_total_dia") or 0)
                    candidates.append({
                        "signal":                  "CH3_INFO",
                        "campaign_id":             cid,
                        "campaign_name":           name,
                        "campaign_type":           campaign_type,
                        "cost_mxn":                round(cost, 2),
                        "conversions":             0,
                        "min_spend":               min_spend,
                        "min_days_active":         min_days,
                        "days_active":             days_active,
                        "days_protection_applied": days_protection_applied,
                        "fuente_datos":            "sheets+ads",
                        "comensales_real":         comensales,
                        "venta_local_real":        round(venta_local, 2),
                        "venta_total_dia":         round(venta_total_dia, 2),
                        "reason": (
                            f"[{campaign_type}] 0 conversiones en Google Ads — "
                            f"normal para campaña de visitas (Maps/offline) | "
                            f"negocio activo: {comensales} comensales, "
                            f"${venta_local:.0f} venta local, "
                            f"${venta_total_dia:.0f} venta total | "
                            f"gasto Ads ${cost:.0f} MXN"
                        ),
                    })
                    continue  # No agregar CH3 alerta

            # CH3 estándar: 0 conversiones sin datos de negocio que lo justifiquen
            reason_parts = [
                f"[{campaign_type}]",
                f"0 conversiones en {ch3_cfg.get('evidence_window_days', 14)} dias",
                f"gasto ${cost:.2f} MXN (req. ${min_spend:.2f})",
            ]
            if days_active is not None:
                reason_parts.append(
                    f"campana activa {days_active} dias (req. {min_days})"
                )
            else:
                reason_parts.append("antiguedad: no disponible")

            candidates.append({
                "signal":                  "CH3",
                "campaign_id":             cid,
                "campaign_name":           name,
                "campaign_type":           campaign_type,
                "cost_mxn":                round(cost, 2),
                "conversions":             0,
                "min_spend":               min_spend,
                "min_days_active":         min_days,
                "days_active":             days_active,
                "days_protection_applied": days_protection_applied,
                "fuente_datos":            "ads",
                "reason":                  " | ".join(reason_parts),
            })

    # Ordenar por gasto descendente
    candidates.sort(key=lambda x: x["cost_mxn"], reverse=True)
    return candidates
