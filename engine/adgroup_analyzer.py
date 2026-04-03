"""
Thai Thai Ads Agent — Detector de Ad Groups con Baja Eficiencia (Fase 4 MVP)

Señal AG1 (única en este MVP):
  Ad group con gasto >= ag1_min_spend MXN (por tipo de campaña),
  0 conversiones y >= ag1_min_clicks clicks
  en una ventana de ADGROUP_EVIDENCE_WINDOW_DAYS días.

Los thresholds de gasto, clicks y protección de días varían por tipo de campaña
(delivery / reservaciones / local / default) — definidos en CAMPAIGN_TYPE_CONFIG.

Función pura — no realiza llamadas a la API de Google Ads ni a SQLite.
Testeable con datos sintéticos, sin dependencias externas.

Señales excluidas del MVP:
  AG2 — CPA relativo vs promedio de campaña (requiere calcular promedio ponderado)
  AG3 — CTR anormalmente bajo (más subjetivo; requiere umbral por tipo de campaña)
"""

from config.agent_config import (
    ADGROUP_MIN_SPEND_TO_PROPOSE,
    ADGROUP_MIN_CLICKS_FOR_SIGNAL,
    ADGROUP_EVIDENCE_WINDOW_DAYS,
    ADGROUP_MAX_PROPOSALS_PER_CYCLE,
    CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION,
    CAMPAIGN_TYPE_CONFIG,
)


def detect_adgroup_issues(adgroups: list) -> list:
    """
    Detecta ad groups candidatos a pausa por baja eficiencia (Señal AG1).

    Los thresholds de gasto, clicks y protección de días se resuelven por
    tipo de campaña usando CAMPAIGN_TYPE_CONFIG. Si el tipo no se resuelve,
    usa los valores del tipo 'default' (equivalentes a las constantes globales).

    Solo evalúa ad groups con status 'ENABLED'.

    Cada candidato retornado incluye evidencia completa y explícita:
      campaign_type          — tipo resuelto ('delivery', 'reservaciones', etc.)
      min_spend_required     — umbral de gasto aplicado
      min_clicks_required    — umbral de clicks aplicado
      min_days_protection    — días de protección aplicados para este tipo
      campaign_days_active   — días activa la campaña (None si no disponible)
      days_protection_applied— True si se verificó antigüedad, False si dato ausente

    Args:
        adgroups: lista de dicts, uno por ad group. Claves esperadas:
            adgroup_id          (str)  — ID del ad group en Google Ads
            adgroup_name        (str)  — nombre del ad group
            campaign_id         (str)  — ID de la campaña padre
            campaign_name       (str)  — nombre de la campaña padre
            status              (str)  — p.ej. 'ENABLED', 'PAUSED'
            cost_mxn            (float)— gasto total en MXN en la ventana
            clicks              (int)  — clicks en la ventana
            conversions         (float)— conversiones en la ventana
            impressions         (int)  — impresiones en la ventana
            campaign_days_active(int, opcional) — días activa la campaña padre

    Returns:
        Lista de dicts con los candidatos detectados, ordenados por gasto
        descendente (mayor desperdicio primero).
        Máximo ADGROUP_MAX_PROPOSALS_PER_CYCLE elementos.
    """
    # Importar aquí para evitar dependencias circulares en tests — risk_classifier
    # no importa adgroup_analyzer, pero se mantiene el import lazy por claridad.
    from engine.risk_classifier import get_campaign_type

    candidates = []

    for ag in adgroups:
        # Solo grupos habilitados — no proponer lo que ya está pausado
        if ag.get("status", "").upper() != "ENABLED":
            continue

        # Resolver tipo de campaña y obtener thresholds específicos
        campaign_type = get_campaign_type(
            ag.get("campaign_name", ""),
            ag.get("campaign_id", ""),
        )
        type_cfg = CAMPAIGN_TYPE_CONFIG.get(campaign_type, CAMPAIGN_TYPE_CONFIG["default"])

        min_spend  = type_cfg.get("ag1_min_spend",           ADGROUP_MIN_SPEND_TO_PROPOSE)
        min_clicks = type_cfg.get("ag1_min_clicks",           ADGROUP_MIN_CLICKS_FOR_SIGNAL)
        min_days   = type_cfg.get("ag1_min_days_protection",  CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION)

        # Protección de fase de aprendizaje por tipo de campaña
        # Si campaign_days_active no está disponible, NO se aplica la protección
        # (falta de dato != campaña nueva) y se deja constancia explícita.
        days_active = ag.get("campaign_days_active")
        days_protection_applied = days_active is not None

        if days_active is not None and days_active < min_days:
            continue

        cost_mxn    = float(ag.get("cost_mxn", 0))
        clicks      = int(ag.get("clicks", 0))
        conversions = float(ag.get("conversions", 0))

        # Señal AG1: gasto relevante + clicks suficientes + cero conversiones
        if (
            cost_mxn >= min_spend
            and clicks >= min_clicks
            and conversions == 0
        ):
            # Reason completamente dinámico — sin valores hardcodeados
            reason_parts = [
                f"[{campaign_type}]",
                f"gasto ${cost_mxn:.2f} MXN (req. ${min_spend:.2f})",
                f"clicks {clicks} (req. {min_clicks})",
                f"conv 0 en {ADGROUP_EVIDENCE_WINDOW_DAYS} días",
            ]
            if days_active is not None:
                reason_parts.append(
                    f"campaña activa {days_active} días (req. {min_days})"
                )
            else:
                reason_parts.append("antigüedad de campaña: no disponible")

            candidates.append({
                "adgroup_id":   str(ag.get("adgroup_id", "")),
                "adgroup_name": ag.get("adgroup_name", ""),
                "campaign_id":  str(ag.get("campaign_id", "")),
                "campaign_name": ag.get("campaign_name", ""),
                "cost_mxn":     round(cost_mxn, 2),
                "clicks":       clicks,
                "conversions":  0,
                "impressions":  int(ag.get("impressions", 0)),
                "signal":       "AG1",
                # Evidencia explícita — ajuste #1 y #2 del usuario
                "campaign_type":           campaign_type,
                "min_spend_required":      min_spend,
                "min_clicks_required":     min_clicks,
                "min_days_protection":     min_days,
                "campaign_days_active":    days_active,    # None si no disponible
                "days_protection_applied": days_protection_applied,
                "reason":                 " | ".join(reason_parts),
            })

    # Ordenar por gasto descendente para proponer primero el mayor desperdicio
    candidates.sort(key=lambda x: x["cost_mxn"], reverse=True)

    # Limitar al máximo por ciclo
    return candidates[:ADGROUP_MAX_PROPOSALS_PER_CYCLE]
