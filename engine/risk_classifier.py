"""
Thai Thai Ads Agent — Clasificador de Riesgo y Urgencia

Separa dos dimensiones independientes:
  - risk_level: qué tan riesgosa es la ACCIÓN (0=observar, 1=ejecutar, 2=proponer, 3=bloquear)
  - urgency: qué tan urgente es la SITUACIÓN (normal, urgent, critical)

Alto riesgo NO implica urgencia crítica.
Urgencia crítica NO implica que la acción sea de bajo riesgo.

Ambas dimensiones se evalúan por separado y determinan el comportamiento del agente.
"""

import unicodedata
from typing import Dict, Any, Tuple
from config.agent_config import (
    KEYWORD_MIN_SPEND_TO_BLOCK,
    KEYWORD_MIN_EVIDENCE_DAYS,
    BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK,
    BUDGET_CHANGE_MAX_PCT_HIGH_RISK,
    KEYWORD_MIN_IMPRESSIONS_FOR_EVIDENCE,
    PROTECTED_KEYWORDS,
    PROTECTED_CAMPAIGN_NAMES,
    PROTECTED_CAMPAIGN_IDS,
    CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION,
    LEARNING_PHASE_STATUS_SIGNALS,
    CONVERSION_DROP_CRITICAL_PCT,
    SPEND_ANOMALY_MULTIPLIER_CRITICAL,
    CAMPAIGN_TYPE_CONFIG,
    CAMPAIGN_ID_TYPE_MAP,
    SMALL_MODE_ENABLED,
    SMALL_MODE_CONFIDENCE_MIN,
    SMALL_MODE_CONFIDENCE_GAP_MIN,
    FUNCTIONAL_CATEGORY_DEFAULT,
    FUNCTIONAL_CATEGORY_SIGNALS,
)

# ============================================================================
# CONSTANTES DE NIVEL DE RIESGO
# ============================================================================

RISK_OBSERVE = 0    # No actuar — señal débil, evidencia insuficiente o aprendizaje
RISK_EXECUTE = 1    # Ejecutar automáticamente
RISK_PROPOSE = 2    # Proponer para aprobación
RISK_BLOCK   = 3    # No ejecutar — requiere autorización explícita


# ============================================================================
# CONSTANTES DE URGENCIA
# ============================================================================

URGENCY_NORMAL   = "normal"
URGENCY_URGENT   = "urgent"
URGENCY_CRITICAL = "critical"


# ============================================================================
# DETECCIÓN DE TIPO DE CAMPAÑA
# ============================================================================

def get_campaign_type(campaign_name: str, campaign_id: str = None) -> str:
    """
    Detecta el tipo de campaña para aplicar thresholds específicos.

    Prioridad:
    1. Mapeo explícito por campaign_id (CAMPAIGN_ID_TYPE_MAP en agent_config.py)
       — permite override sin depender del nombre, útil si el nombre cambia.
    2. Match por nombre (case-insensitive, substrings).

    Tipos soportados: 'delivery', 'reservaciones', 'local', 'default'

    Nomenclatura actual de campañas:
      - "Thai Mérida - Local"        → local
      - "Thai Mérida - Delivery"     → delivery
      - "Thai Mérida - Reservaciones"→ reservaciones
      - "Thai Mérida" (pre-rename)   → local (fallback — es la campaña base del restaurante)
      - "Restaurant Thai On Line"    → delivery (pre-rename legacy)
    """
    # 1. Override por ID si existe
    if campaign_id and str(campaign_id) in CAMPAIGN_ID_TYPE_MAP:
        return CAMPAIGN_ID_TYPE_MAP[str(campaign_id)]

    # 2. Match por nombre
    name = (campaign_name or "").lower()

    if "delivery" in name or "pad thai" in name or "on line" in name:
        return "delivery"

    if any(kw in name for kw in ("reserva", "reservaciones", "booking", "book", "mesa")):
        return "reservaciones"

    if "local" in name:
        return "local"

    # Fallback: "Thai Mérida" sin sufijo → campaña base del restaurante → local
    if "thai" in name and "merida" in name:
        return "local"

    return "default"


def get_campaign_thresholds(campaign_name: str, campaign_id: str = None) -> dict:
    """Retorna los thresholds de CPA y gasto para el tipo de campaña detectado."""
    campaign_type = get_campaign_type(campaign_name, campaign_id)
    return CAMPAIGN_TYPE_CONFIG.get(campaign_type, CAMPAIGN_TYPE_CONFIG["default"])


# ============================================================================
# CAPA FUNCIONAL / SMALL MODE (FASE 1)
# Se mantiene separada de la lógica normal de tipo/riesgo existente.
# ============================================================================

def _contains_any(text: str, keywords: tuple) -> bool:
    if not text or not keywords:
        return False
    text_norm = _normalize(text)
    return any(_normalize(keyword) in text_norm for keyword in keywords)


def _get_channel_type(campaign_data: Dict) -> str:
    return str(
        campaign_data.get("advertising_channel_type")
        or campaign_data.get("channel_type")
        or ""
    ).upper()


def _build_blocking_signals(campaign_data: Dict, channel_type: str, top_score: float, gap: float) -> list:
    blocking = []
    if not SMALL_MODE_ENABLED:
        blocking.append("small_mode_disabled")
    if campaign_data.get("tracking_broken"):
        blocking.append("tracking_broken")
    if campaign_data.get("landing_broken"):
        blocking.append("landing_broken")
    if campaign_data.get("risk_blocked"):
        blocking.append("risk_blocked")
    if campaign_data.get("data_inconsistent"):
        blocking.append("data_inconsistent")
    if top_score < SMALL_MODE_CONFIDENCE_MIN:
        blocking.append("low_classification_confidence")
    if gap < SMALL_MODE_CONFIDENCE_GAP_MIN:
        blocking.append("classification_conflict")
    return blocking


def _resolve_functional_category_scores(campaign_data: Dict) -> Dict[str, float]:
    name = str(campaign_data.get("name") or campaign_data.get("campaign_name") or "")
    channel_type = _get_channel_type(campaign_data)
    campaign_type = get_campaign_type(name, str(campaign_data.get("id") or campaign_data.get("campaign_id") or ""))

    scores = {category: 0.0 for category in FUNCTIONAL_CATEGORY_SIGNALS}
    for category, cfg in FUNCTIONAL_CATEGORY_SIGNALS.items():
        score = 0.0
        if _contains_any(name, cfg.get("name_keywords", ())):
            score += float(cfg.get("default_weight", 0.0))
        required_channels = tuple(cfg.get("required_channel_types", ()))
        if required_channels and channel_type in required_channels:
            score += 0.20
        scores[category] = min(score, 1.0)

    # Fallbacks compatibles con la lógica histórica actual
    if scores["delivery_order"] == 0.0 and campaign_type == "delivery":
        scores["delivery_order"] = 0.85
    if scores["reservation_intent"] == 0.0 and campaign_type == "reservaciones":
        scores["reservation_intent"] = 0.85
    if scores["local_visit"] == 0.0 and campaign_type == "local":
        scores["local_visit"] = 0.78
    if channel_type == "SEARCH" and max(scores.values()) < SMALL_MODE_CONFIDENCE_MIN:
        scores["generic_search"] = max(scores["generic_search"], 0.72)

    return scores


def classify_campaign_functionally(campaign_data: Dict) -> Dict[str, Any]:
    """
    Nueva capa funcional para small_mode.

    No reemplaza la lógica normal existente.
    Retorna solo los campos mínimos aprobados para fases posteriores:
    - category
    - classification_confidence
    - small_mode_active
    - decision_label
    - blocking_signals
    """
    scores = _resolve_functional_category_scores(campaign_data)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_category, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    gap = top_score - second_score
    channel_type = _get_channel_type(campaign_data)
    blocking_signals = _build_blocking_signals(campaign_data, channel_type, top_score, gap)

    if any(signal in blocking_signals for signal in ("low_classification_confidence", "classification_conflict")):
        category = FUNCTIONAL_CATEGORY_DEFAULT
        confidence = round(top_score, 2)
    else:
        category = top_category
        confidence = round(top_score, 2)

    small_mode_active = (
        SMALL_MODE_ENABLED
        and category != FUNCTIONAL_CATEGORY_DEFAULT
        and not any(signal in blocking_signals for signal in (
            "tracking_broken",
            "landing_broken",
            "risk_blocked",
            "data_inconsistent",
        ))
    )

    decision_label = "no_action_risk" if blocking_signals else "hold"

    return {
        "category": category,
        "classification_confidence": confidence,
        "small_mode_active": small_mode_active,
        "decision_label": decision_label,
        "blocking_signals": blocking_signals,
    }


# ============================================================================
# HELPERS DE PROTECCIÓN
# ============================================================================

def _normalize(text: str) -> str:
    """Normaliza texto a ASCII folding para comparaciones robustas (é→e, ñ→n, etc.)."""
    return unicodedata.normalize("NFD", text.lower().strip()).encode("ascii", "ignore").decode()


def is_keyword_protected(keyword_text: str) -> bool:
    """Verifica si una keyword está en la whitelist de keywords estratégicas.
    Normaliza acentos para evitar fallos con variantes ortográficas (merida vs mérida)."""
    if not keyword_text:
        return False
    kw_norm = _normalize(keyword_text)
    return any(_normalize(protected) in kw_norm for protected in PROTECTED_KEYWORDS)


def is_campaign_protected(campaign_id: str, campaign_name: str) -> bool:
    """Verifica si una campaña está protegida contra acciones automáticas."""
    if campaign_id and str(campaign_id) in [str(p) for p in PROTECTED_CAMPAIGN_IDS]:
        return True
    if campaign_name:
        name_lower = campaign_name.lower()
        for protected_name in PROTECTED_CAMPAIGN_NAMES:
            if protected_name.lower() in name_lower:
                return True
    return False


def is_learning_phase(campaign_data: Dict) -> bool:
    """
    Determina si una campaña está en fase de aprendizaje.
    Revisa el status de la campaña y los días de actividad.
    """
    status = str(campaign_data.get("learning_status", "")).upper()
    for signal in LEARNING_PHASE_STATUS_SIGNALS:
        if signal.upper() in status:
            return True

    # Si no hay dato de días activos, asumir que puede estar en aprendizaje
    days_active = campaign_data.get("days_active", None)
    if days_active is not None and days_active < CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION:
        return True

    return False


def has_sufficient_evidence(keyword_data: Dict, campaign_name: str = "", campaign_id: str = None) -> bool:
    """
    Verifica si una keyword tiene suficiente evidencia para actuar.
    Usa el umbral de gasto del tipo de campaña (no un valor global).
    """
    spend = float(keyword_data.get("spend", 0))
    impressions = int(keyword_data.get("impressions", 0))

    thresholds = get_campaign_thresholds(campaign_name, campaign_id)
    if spend < thresholds["min_spend_to_block"]:
        return False
    if impressions < KEYWORD_MIN_IMPRESSIONS_FOR_EVIDENCE:
        return False
    return True


# ============================================================================
# CLASIFICADOR DE RIESGO POR TIPO DE ACCIÓN
# ============================================================================

def classify_block_keyword(
    keyword_data: Dict,
    campaign_data: Dict,
) -> Tuple[int, str, str]:
    """
    Clasifica el riesgo y urgencia de bloquear una keyword.
    Usa thresholds de CPA y gasto específicos por tipo de campaña.

    Returns:
        (risk_level, urgency, reason)
    """
    keyword_text = keyword_data.get("text", keyword_data.get("keyword", ""))
    campaign_id = str(keyword_data.get("campaign_id", campaign_data.get("id", "")))
    campaign_name = keyword_data.get("campaign_name", campaign_data.get("name", ""))
    spend = float(keyword_data.get("spend", keyword_data.get("cost_micros", 0)) or 0)
    if spend > 10000:  # probablemente en micros
        spend = spend / 1_000_000

    # Thresholds específicos del tipo de campaña
    thresholds = get_campaign_thresholds(campaign_name, campaign_id)
    campaign_type = get_campaign_type(campaign_name, campaign_id)
    min_spend = thresholds["min_spend_to_block"]
    cpa_critical = thresholds["cpa_critical"]

    # Protección: keyword estratégica
    if is_keyword_protected(keyword_text):
        return RISK_PROPOSE, URGENCY_NORMAL, (
            f"Keyword protegida: '{keyword_text}' — requiere aprobación para cualquier cambio"
        )

    # Protección: campaña protegida
    if is_campaign_protected(campaign_id, campaign_name):
        return RISK_PROPOSE, URGENCY_NORMAL, f"Campaña protegida: '{campaign_name}' — requiere aprobación"

    # Protección: fase de aprendizaje
    if is_learning_phase(campaign_data):
        return RISK_OBSERVE, URGENCY_NORMAL, "Campaña en fase de aprendizaje — esperar más datos antes de actuar"

    # Evidencia insuficiente (usa min_spend del tipo de campaña)
    if not has_sufficient_evidence(keyword_data, campaign_name, campaign_id):
        impressions = int(keyword_data.get("impressions", 0))
        if spend < min_spend:
            evidence_msg = f"gasto ${spend:.2f} < ${min_spend:.0f} mínimo"
        else:
            evidence_msg = f"impresiones {impressions} < {KEYWORD_MIN_IMPRESSIONS_FOR_EVIDENCE} mínimo"
        return RISK_OBSERVE, URGENCY_NORMAL, (
            f"Evidencia insuficiente para campaña '{campaign_type}' "
            f"({evidence_msg}) — observar"
        )

    # 0 conversiones con gasto suficiente — candidata a bloqueo automático
    conversions = float(keyword_data.get("conversions", 0))
    if conversions == 0:
        return RISK_EXECUTE, URGENCY_NORMAL, (
            f"Keyword con ${spend:.2f} gastados y 0 conversiones "
            f"en campaña '{campaign_type}' — bloqueo automático justificado"
        )

    # Tiene conversiones pero CPA supera el crítico del tipo de campaña → proponer
    cpa = spend / conversions
    if cpa > cpa_critical:
        return RISK_PROPOSE, URGENCY_NORMAL, (
            f"CPA ${cpa:.2f} supera el límite crítico (${cpa_critical:.0f}) "
            f"para campaña '{campaign_type}' — proponer revisión"
        )

    return RISK_OBSERVE, URGENCY_NORMAL, "No cumple criterios claros — observar"


def classify_pause_ad_group(
    ad_group_data: Dict,
    campaign_data: Dict,
) -> Tuple[int, str, str]:
    """
    Pausa de un grupo de anuncios.
    Auto-ejecuta si hay ≥$100 MXN gastados con 0 conversiones (evidencia clara de desperdicio).
    """
    campaign_name = campaign_data.get("name", "")
    campaign_id = str(campaign_data.get("id", ""))

    if is_campaign_protected(campaign_id, campaign_name):
        return RISK_BLOCK, URGENCY_NORMAL, f"Campaña protegida — requiere autorización explícita"

    if is_learning_phase(campaign_data):
        return RISK_BLOCK, URGENCY_NORMAL, "Campaña en aprendizaje — no pausar grupo sin autorización"

    spend = float(ad_group_data.get("spend", ad_group_data.get("cost_mxn", 0)) or 0)
    conversions = float(ad_group_data.get("conversions", 0) or 0)

    if spend >= 100.0 and conversions == 0:
        return RISK_EXECUTE, URGENCY_NORMAL, (
            f"Ad group con ${spend:.0f} MXN gastados y 0 conversiones — pausa automática justificada"
        )

    return RISK_PROPOSE, URGENCY_NORMAL, "Pausa de grupo de anuncios — riesgo medio, requiere aprobación"


def classify_budget_change(
    current_budget_mxn: float,
    proposed_budget_mxn: float,
    campaign_data: Dict,
) -> Tuple[int, str, str]:
    """
    Clasifica el riesgo de un cambio de presupuesto.
    El porcentaje de cambio determina el nivel de riesgo.
    """
    campaign_name = campaign_data.get("name", "")
    campaign_id = str(campaign_data.get("id", ""))

    if is_campaign_protected(campaign_id, campaign_name):
        return RISK_BLOCK, URGENCY_NORMAL, "Campaña protegida — cambio de presupuesto requiere autorización explícita"

    if current_budget_mxn <= 0:
        return RISK_BLOCK, URGENCY_NORMAL, "No se puede calcular % de cambio — autorización requerida"

    change_pct = abs((proposed_budget_mxn - current_budget_mxn) / current_budget_mxn) * 100

    # >40%: cambio agresivo — proponer con urgencia alta para que el operador lo vea
    if change_pct > BUDGET_CHANGE_MAX_PCT_HIGH_RISK:
        return RISK_PROPOSE, URGENCY_URGENT, (
            f"Cambio de presupuesto {change_pct:.1f}% — cambio agresivo, requiere aprobación urgente"
        )

    # 20–40%: cambio moderado — proponer para aprobación
    if change_pct > BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK:
        return RISK_PROPOSE, URGENCY_NORMAL, (
            f"Cambio de presupuesto {change_pct:.1f}% — requiere aprobación"
        )

    # ≤20%: cambio menor — auto-ejecutable sin aprobación
    return RISK_EXECUTE, URGENCY_NORMAL, (
        f"Cambio de presupuesto {change_pct:.1f}% ≤{BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK:.0f}% — auto-ejecutable"
    )


def classify_pause_campaign(campaign_data: Dict) -> Tuple[int, str, str]:
    """Pausar una campaña completa — siempre riesgo alto."""
    return RISK_BLOCK, URGENCY_NORMAL, "Pausar campaña completa — riesgo alto, requiere autorización explícita"


def detect_tracking_signals(
    current_week: list,
    prev_week: list,
) -> dict:
    """
    Analiza métricas semanales a nivel cuenta y detecta señales de posible problema de tracking.

    IMPORTANTE: Esta función NO realiza mutaciones en Google Ads.
    Solo produce un diagnóstico. Cuando el clasificador retorna RISK_EXECUTE para
    'tracking_alert', significa ENVIAR ALERTA AUTOMÁTICAMENTE — no mutar nada.

    Señales detectadas:
      A — Caída de CVR ≥ TRACKING_CVR_DROP_THRESHOLD en ≥ TRACKING_MIN_CAMPAIGNS_AFFECTED
          campañas con volumen suficiente (≥ TRACKING_MIN_CLICKS_FOR_SIGNAL clicks).
      B — 0 conversiones con ≥ TRACKING_MIN_CLICKS_FOR_SIGNAL clicks en
          ≥ TRACKING_MIN_CAMPAIGNS_AFFECTED campañas.
      C — 0 conversiones totales en la cuenta con ≥ TRACKING_MIN_CLICKS_SIGNAL_C clicks.
          Condición de volumen obligatoria para evitar falsos positivos en semanas de poco tráfico.

    Args:
        current_week : lista de dicts {id, name, clicks, conversions, cvr, cost_mxn}
                       (semana actual, p. ej. últimos 7 días)
        prev_week    : misma estructura para la semana anterior (días 8-14)

    Returns:
        dict con:
          signals           — lista de códigos detectados ([], ['A'], ['B','C'], etc.)
          severity          — 'critical', 'warning' o 'none'
          reason            — descripción en lenguaje tentativo (para correo de alerta)
          signal_a_affected — campañas que dispararon señal A
          signal_b_affected — campañas que dispararon señal B
          affected_campaigns— lista deduplicada de nombres de campañas afectadas
          account_metrics   — totales a nivel cuenta (clicks, conversiones)
    """
    from config.agent_config import (
        TRACKING_MIN_CLICKS_FOR_SIGNAL,
        TRACKING_CVR_DROP_THRESHOLD,
        TRACKING_MIN_CAMPAIGNS_AFFECTED,
        TRACKING_MIN_CLICKS_SIGNAL_C,
    )

    # Índice de campaña semana anterior
    prev_index = {c["id"]: c for c in prev_week}

    # Totales a nivel cuenta (semana actual)
    total_clicks = sum(c["clicks"] for c in current_week)
    total_conversions = sum(c["conversions"] for c in current_week)

    signal_a_affected = []
    signal_b_affected = []

    for campaign in current_week:
        cid = campaign["id"]
        clicks = campaign["clicks"]
        conversions = campaign["conversions"]
        cvr_current = campaign["cvr"]

        # Condición de volumen: campaña con poco tráfico no cuenta para señales A/B
        if clicks < TRACKING_MIN_CLICKS_FOR_SIGNAL:
            continue

        # Señal A: caída de CVR respecto a la semana anterior
        prev = prev_index.get(cid, {})
        cvr_prev = prev.get("cvr", 0.0)
        if cvr_prev > 0:
            drop = (cvr_prev - cvr_current) / cvr_prev
            if drop >= TRACKING_CVR_DROP_THRESHOLD:
                signal_a_affected.append({
                    "campaign": campaign["name"],
                    "cvr_prev_pct": round(cvr_prev * 100, 2),
                    "cvr_current_pct": round(cvr_current * 100, 2),
                    "drop_pct": round(drop * 100, 1),
                })

        # Señal B: clicks sin ninguna conversión
        if conversions == 0:
            signal_b_affected.append({
                "campaign": campaign["name"],
                "clicks": clicks,
                "conversions": 0,
            })

    signals = []
    reasons = []

    if len(signal_a_affected) >= TRACKING_MIN_CAMPAIGNS_AFFECTED:
        signals.append("A")
        reasons.append(
            f"Señal A: posible caída de CVR en {len(signal_a_affected)} campaña(s) — "
            "señal compatible con problema de tracking (requiere verificación)"
        )

    if len(signal_b_affected) >= TRACKING_MIN_CAMPAIGNS_AFFECTED:
        signals.append("B")
        reasons.append(
            f"Señal B: {len(signal_b_affected)} campaña(s) con clicks y 0 conversiones — "
            "posible problema de tags, requiere verificación"
        )

    # Señal C — requiere volumen mínimo para no confundir con semana de poco tráfico
    if total_conversions == 0 and total_clicks >= TRACKING_MIN_CLICKS_SIGNAL_C:
        signals.append("C")
        reasons.append(
            f"Señal C: 0 conversiones en toda la cuenta con {total_clicks} clicks totales — "
            "posible problema de tracking global, requiere verificación urgente"
        )

    if not signals:
        return {
            "signals": [],
            "severity": "none",
            "reason": "Sin señales de problema de tracking detectadas",
            "signal_a_affected": [],
            "signal_b_affected": [],
            "affected_campaigns": [],
            "account_metrics": {
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "campaigns_evaluated": sum(
                    1 for c in current_week if c["clicks"] >= TRACKING_MIN_CLICKS_FOR_SIGNAL
                ),
            },
        }

    # Severidad: crítica si hay 2+ señales o Señal C sola
    severity = "critical" if (len(signals) >= 2 or "C" in signals) else "warning"
    reason = " / ".join(reasons)

    # Campañas únicas afectadas (union de A y B)
    affected_set = {c["campaign"] for c in signal_a_affected} | {c["campaign"] for c in signal_b_affected}

    return {
        "signals": signals,
        "severity": severity,
        "reason": reason,
        "signal_a_affected": signal_a_affected,
        "signal_b_affected": signal_b_affected,
        "affected_campaigns": sorted(affected_set),
        "account_metrics": {
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "campaigns_evaluated": sum(
                1 for c in current_week if c["clicks"] >= TRACKING_MIN_CLICKS_FOR_SIGNAL
            ),
        },
    }


def classify_adgroup_efficiency_issue(
    adgroup_data: Dict,
    campaign_data: Dict = None,
) -> Tuple[int, str, str]:
    """
    Clasifica la propuesta de pausa de un ad group con baja eficiencia (Fase 4 MVP).

    Siempre retorna RISK_PROPOSE — esta fase no tiene autoejecución.
    Urgencia según monto gastado: si supera el doble del umbral mínimo de bloqueo
    de la campaña, se marca como 'urgent'; de lo contrario 'normal'.

    Args:
        adgroup_data : dict producido por detect_adgroup_issues() —
                       incluye campaign_id, campaign_name, cost_mxn, signal, reason
        campaign_data: datos adicionales de campaña (opcional, puede ser {})
    """
    campaign_data = campaign_data or {}
    campaign_name = adgroup_data.get("campaign_name", campaign_data.get("name", ""))
    campaign_id = str(adgroup_data.get("campaign_id", campaign_data.get("id", "")))

    if is_campaign_protected(campaign_id, campaign_name):
        return (
            RISK_BLOCK,
            URGENCY_NORMAL,
            f"Campaña protegida '{campaign_name}' — propuesta bloqueada, requiere autorización",
        )

    cost_mxn = float(adgroup_data.get("cost_mxn", 0))
    thresholds = get_campaign_thresholds(campaign_name, campaign_id)
    min_spend = thresholds.get("min_spend_to_block", 70.0)

    # Urgencia según magnitud del gasto: >= 2x del umbral mínimo de la campaña → urgent
    urgency = URGENCY_URGENT if cost_mxn >= min_spend * 2 else URGENCY_NORMAL

    reason = adgroup_data.get(
        "reason",
        f"Ad group con señal AG1 — propuesta de revisión para campaña '{campaign_name}'",
    )
    return RISK_PROPOSE, urgency, reason


def classify_tracking_issue(issue_severity: str) -> Tuple[int, str, str]:
    """
    Problema de tracking detectado.

    IMPORTANTE: Para 'tracking_alert', RISK_EXECUTE significa ENVIAR ALERTA
    AUTOMÁTICAMENTE — NO ejecutar mutaciones en Google Ads ni pausar conversion actions.
    El diagnóstico es de bajo riesgo; cualquier cambio en conversion actions es de alto riesgo
    y requiere autorización explícita del operador.
    """
    if issue_severity == "critical":
        return (
            RISK_EXECUTE,
            URGENCY_CRITICAL,
            "Posible problema crítico de tracking — señal compatible con falla global de tags. "
            "Requiere verificación inmediata en Google Tag Assistant y Google Ads.",
        )
    return (
        RISK_OBSERVE,
        URGENCY_URGENT,
        "Posible inconsistencia de tracking — señal aislada que requiere monitoreo. "
        "No se descarta variación normal de tráfico.",
    )


def classify_landing_issue(issue_severity: str) -> Tuple[int, str, str]:
    """
    Problema de landing detectado (Fase 3B).

    IMPORTANTE: Para 'landing_alert', RISK_EXECUTE significa ENVIAR ALERTA
    AUTOMÁTICAMENTE — NO modifica el sitio web ni el código de la landing.
    Cualquier corrección requiere intervención manual del operador.

    Solo se envía correo para 'critical'. 'warning' se registra en SQLite
    y en el response pero NO genera email en este MVP.
    """
    if issue_severity == "critical":
        return (
            RISK_EXECUTE,
            URGENCY_CRITICAL,
            "Falla crítica de landing o flujo de conversión — "
            "alerta enviada, requiere verificación inmediata.",
        )
    return (
        RISK_OBSERVE,
        URGENCY_URGENT,
        "Anomalía de rendimiento en landing (warning) — "
        "registrado para monitoreo, sin alerta por email.",
    )


# ============================================================================
# CLASIFICADOR DE URGENCIA INDEPENDIENTE
# ============================================================================

def classify_urgency_from_metrics(
    current_conversions: float,
    previous_conversions: float,
    current_spend: float,
    weekly_avg_spend: float,
) -> str:
    """
    Evalúa la urgencia de la situación basándose en métricas de rendimiento.
    Esta función es independiente del risk_level de una acción específica.

    Returns:
        urgency string: 'normal', 'urgent', or 'critical'
    """
    # Caída crítica de conversiones
    if previous_conversions > 0:
        drop_pct = ((previous_conversions - current_conversions) / previous_conversions) * 100
        if drop_pct >= CONVERSION_DROP_CRITICAL_PCT:
            return URGENCY_CRITICAL

    # Gasto anormal
    if weekly_avg_spend > 0 and current_spend > 0:
        spend_ratio = current_spend / weekly_avg_spend
        if spend_ratio >= SPEND_ANOMALY_MULTIPLIER_CRITICAL:
            return URGENCY_CRITICAL
        if spend_ratio >= 1.5:
            return URGENCY_URGENT

    return URGENCY_NORMAL


# ============================================================================
# CLASIFICADOR UNIFICADO
# ============================================================================

class RiskClassification:
    """Resultado de clasificación de riesgo para una acción."""

    def __init__(
        self,
        action_type: str,
        risk_level: int,
        urgency: str,
        reason: str,
        can_auto_execute: bool,
        requires_approval: bool,
        is_blocked: bool,
        protected: bool = False,
        learning_phase: bool = False,
    ):
        self.action_type = action_type
        self.risk_level = risk_level
        self.urgency = urgency
        self.reason = reason
        self.can_auto_execute = can_auto_execute
        self.requires_approval = requires_approval
        self.is_blocked = is_blocked
        self.protected = protected
        self.learning_phase = learning_phase

    @property
    def block_reason(self) -> str:
        """
        Código corto del motivo principal por el que no se ejecuta automáticamente.
        Útil para logging, SQLite y análisis del summary.

        Valores posibles:
          learning_phase       — campaña en aprendizaje
          protected_keyword    — keyword en whitelist estratégico
          protected_campaign   — campaña protegida por config
          insufficient_evidence— gasto o impresiones por debajo del umbral
          requires_approval    — riesgo medio, necesita aprobación
          high_risk_blocked    — riesgo alto, requiere autorización explícita
          auto_execute_ready   — clasificado para ejecución automática
        """
        if self.learning_phase:
            return "learning_phase"
        if self.protected and self.risk_level == RISK_PROPOSE:
            # keyword protegida eleva a propose — distinguir de requires_approval genérico
            if self.action_type == "block_keyword":
                return "protected_keyword"
            return "protected_campaign"
        if self.is_blocked:
            return "high_risk_blocked"
        if self.requires_approval:
            return "requires_approval"
        if self.can_auto_execute:
            return "auto_execute_ready"
        # RISK_OBSERVE sin causa específica identificada
        return "insufficient_evidence"

    def to_dict(self) -> Dict:
        return {
            "action_type": self.action_type,
            "risk_level": self.risk_level,
            "urgency": self.urgency,
            "reason": self.reason,
            "block_reason": self.block_reason,
            "can_auto_execute": self.can_auto_execute,
            "requires_approval": self.requires_approval,
            "is_blocked": self.is_blocked,
            "protected": self.protected,
            "learning_phase": self.learning_phase,
        }

    @property
    def decision_label(self) -> str:
        if self.risk_level == RISK_OBSERVE:
            return "observe"
        if self.risk_level == RISK_EXECUTE:
            return "execute"
        if self.risk_level == RISK_PROPOSE:
            return "propose"
        return "block"


def classify_action(
    action_type: str,
    action_data: Dict,
    campaign_data: Dict = None,
) -> RiskClassification:
    """
    Punto de entrada principal del clasificador.
    Recibe el tipo de acción y los datos relevantes, retorna una clasificación completa.

    Args:
        action_type: 'block_keyword', 'pause_ad_group', 'budget_change',
                     'pause_campaign', 'tracking_issue', 'landing_issue'
        action_data: datos de la acción (keyword, spend, campaign, etc.)
        campaign_data: datos de la campaña afectada (puede ser None)
    """
    campaign_data = campaign_data or {}

    if action_type == "block_keyword":
        risk, urgency, reason = classify_block_keyword(action_data, campaign_data)
        protected = is_keyword_protected(action_data.get("text", action_data.get("keyword", "")))
        learning = is_learning_phase(campaign_data)

    elif action_type == "pause_ad_group":
        risk, urgency, reason = classify_pause_ad_group(action_data, campaign_data)
        protected = is_campaign_protected(
            str(campaign_data.get("id", "")), campaign_data.get("name", ""))
        learning = is_learning_phase(campaign_data)

    elif action_type == "budget_change":
        current = float(action_data.get("current_budget_mxn", 0))
        proposed = float(action_data.get("proposed_budget_mxn", 0))
        risk, urgency, reason = classify_budget_change(current, proposed, campaign_data)
        protected = is_campaign_protected(
            str(campaign_data.get("id", "")), campaign_data.get("name", ""))
        learning = False

    elif action_type == "pause_campaign":
        risk, urgency, reason = classify_pause_campaign(campaign_data)
        protected = False
        learning = False

    elif action_type == "tracking_issue":
        severity = action_data.get("severity", "warning")
        risk, urgency, reason = classify_tracking_issue(severity)
        protected = False
        learning = False

    elif action_type == "landing_issue":
        severity = action_data.get("severity", "warning")
        risk, urgency, reason = classify_landing_issue(severity)
        protected = False
        learning = False

    elif action_type == "adgroup_efficiency":
        risk, urgency, reason = classify_adgroup_efficiency_issue(action_data, campaign_data)
        protected = is_campaign_protected(
            str(action_data.get("campaign_id", "")), action_data.get("campaign_name", ""))
        learning = False

    else:
        # Tipo desconocido — conservador: proponer
        risk = RISK_PROPOSE
        urgency = URGENCY_NORMAL
        reason = f"Tipo de acción desconocido '{action_type}' — propuesta para revisión humana"
        protected = False
        learning = False

    return RiskClassification(
        action_type=action_type,
        risk_level=risk,
        urgency=urgency,
        reason=reason,
        can_auto_execute=(risk == RISK_EXECUTE),
        requires_approval=(risk == RISK_PROPOSE),
        is_blocked=(risk == RISK_BLOCK),
        protected=protected,
        learning_phase=learning,
    )
