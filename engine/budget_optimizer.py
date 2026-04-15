"""
budget_optimizer.py — Módulo 2 del Thai Thai Ads Agent
Implementa la lógica de presupuesto basada en el skill budget-allocation.md

Reglas del skill:
  - 70/20/10: Smart(Local+Delivery)=70%, Search=20%, Experimentos=10%
  - 20% Rule: escalar si CPA < target -10% AND IS_budget_lost > 20%
  - 3x Kill Rule: pausar si spend > 3x target_CPA AND conversiones == 0
  - Rollback: revertir si CPA subió >15% tras último aumento
  - Semáforo audit_score: bloquear scale si score categoría < 40

Haiku solo para casos HOLD con señales mixtas.
Nunca modifica campañas Smart (Local/Delivery) — protegidas como 70%.
"""

import logging
from datetime import datetime
from typing import Optional

from config.agent_config import (
    CAMPAIGN_TYPE_CONFIG,
    MONTHLY_ADS_BUDGET_MXN,
    BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK,
    BUDGET_CHANGE_MIN_DAILY_MXN,
)

logger = logging.getLogger(__name__)

# ── Constantes del optimizer ──────────────────────────────────────────────────

# 70/20/10 — tipos de campaña por rol
PROVEN_TYPES = {"local", "delivery"}       # 70% — nunca tocar salvo kill
GROWTH_TYPES = {"reservaciones", "experiencia", "search", "default"}  # 20%

# Thresholds del skill
SCALE_CPA_BELOW_TARGET_PCT = 0.10    # CPA debe estar 10% bajo el target para escalar
SCALE_IS_BUDGET_LOST_MIN   = 0.20    # IS perdido por presupuesto debe ser >20%
KILL_SPEND_MULTIPLIER      = 3.0     # spend > 3x target_CPA con 0 conv → kill
ROLLBACK_CPA_INCREASE_PCT  = 0.15   # CPA subió >15% tras aumento → revertir
SCALE_MAX_PCT              = BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK / 100  # 0.20
REDUCE_PCT                 = 0.20    # reducción estándar
BUDGET_FLOOR_MXN           = BUDGET_CHANGE_MIN_DAILY_MXN  # $20/día mínimo
MONTHLY_CAP_MXN            = MONTHLY_ADS_BUDGET_MXN       # $10,000/mes

# Semáforo audit_score
AUDIT_GREEN_THRESHOLD  = 60.0   # puede escalar normalmente
AUDIT_YELLOW_THRESHOLD = 40.0   # Haiku decide
# < 40 → rojo, no scale

# Smart Campaign types (protegidas como 70%)
SMART_CHANNEL_TYPES = {"SMART", "LOCAL", "SHOPPING", "PERFORMANCE_MAX"}

# Días mínimos entre incrementos (del skill: "wait 3-5 days before next increase")
MIN_DAYS_BETWEEN_INCREASES = 3


# ── Utilidades ────────────────────────────────────────────────────────────────

def _get_campaign_type(campaign: dict) -> str:
    """Resuelve el tipo de campaña usando risk_classifier."""
    from engine.risk_classifier import get_campaign_type
    return get_campaign_type(
        campaign.get("name", ""),
        str(campaign.get("id", ""))
    )


def _is_smart_campaign(campaign: dict) -> bool:
    """True si es Smart Campaign (Local, Delivery) — no se escala/reduce con reglas Search."""
    channel = str(campaign.get("channel_type", "") or campaign.get("advertising_channel_type", "")).upper()
    return channel in SMART_CHANNEL_TYPES


def _cpa_target(campaign_type: str) -> float:
    """CPA target (ideal) para el tipo de campaña."""
    cfg = CAMPAIGN_TYPE_CONFIG.get(campaign_type, CAMPAIGN_TYPE_CONFIG.get("default", {}))
    return float(cfg.get("cpa_ideal", 50.0))


def _cpa_critical(campaign_type: str) -> float:
    """CPA crítico para el tipo de campaña."""
    cfg = CAMPAIGN_TYPE_CONFIG.get(campaign_type, CAMPAIGN_TYPE_CONFIG.get("default", {}))
    return float(cfg.get("cpa_critical", 100.0))


def _daily_budget(campaign: dict) -> float:
    """Presupuesto diario actual en MXN."""
    return float(campaign.get("daily_budget_mxn") or
                 campaign.get("budget_micros", 0) / 1_000_000 or 0)


def _spend(campaign: dict) -> float:
    """Gasto en MXN (últimos 30d o el período disponible)."""
    if "cost_mxn" in campaign:
        return float(campaign["cost_mxn"])
    return float(campaign.get("cost_micros", 0)) / 1_000_000


def _conversions(campaign: dict) -> float:
    return float(campaign.get("conversions", 0))


def _cpa_real(campaign: dict) -> Optional[float]:
    spend = _spend(campaign)
    conv = _conversions(campaign)
    if conv <= 0 or spend <= 0:
        return None
    return round(spend / conv, 2)


def _is_lost_budget(campaign: dict) -> float:
    """Porcentaje de IS perdido por presupuesto (0-1)."""
    return float(campaign.get("search_budget_lost_impression_share") or
                 campaign.get("is_lost_budget", 0) or 0)


def _days_since_last_increase(campaign_id: str, recent_actions: list) -> Optional[int]:
    """Días desde el último aumento de presupuesto para esta campaña."""
    for action in sorted(recent_actions or [], key=lambda a: a.get("timestamp", ""), reverse=True):
        if str(action.get("campaign_id", "")) != str(campaign_id):
            continue
        action_type = str(action.get("action_type", "")).lower()
        if "scale" in action_type or "increase" in action_type or "budget_up" in action_type:
            ts = action.get("timestamp", "")
            if ts:
                try:
                    action_date = datetime.fromisoformat(ts[:19])
                    delta = (datetime.utcnow() - action_date).days
                    return delta
                except Exception:
                    pass
    return None


def _previous_budget(campaign_id: str, recent_actions: list) -> Optional[float]:
    """Presupuesto anterior al último cambio (para rollback)."""
    for action in sorted(recent_actions or [], key=lambda a: a.get("timestamp", ""), reverse=True):
        if str(action.get("campaign_id", "")) != str(campaign_id):
            continue
        old_b = action.get("old_budget_mxn") or action.get("evidence", {}).get("old_budget_mxn")
        if old_b:
            return float(old_b)
    return None


def _previous_cpa(campaign_id: str, recent_actions: list) -> Optional[float]:
    """CPA registrado en el último ciclo (para detectar rollback)."""
    for action in sorted(recent_actions or [], key=lambda a: a.get("timestamp", ""), reverse=True):
        if str(action.get("campaign_id", "")) != str(campaign_id):
            continue
        cpa = action.get("current_cpa") or action.get("evidence", {}).get("cpa_real")
        if cpa:
            return float(cpa)
    return None


def _audit_semaphore(audit_result, campaign_type: str) -> str:
    """
    GREEN  → score > 60 → puede escalar
    YELLOW → 40-60 → Haiku decide
    RED    → < 40 → no escalar
    Si no hay audit_result → YELLOW (Haiku decide)
    """
    if audit_result is None:
        return "YELLOW"
    cat_map = {
        "delivery": "CT",
        "local": "Structure",
        "reservaciones": "KW",
        "experiencia": "Ads",
        "search": "Ads",
    }
    cat = cat_map.get(campaign_type, None)
    cat_scores = getattr(audit_result, "category_scores", {})
    score = cat_scores.get(cat) if cat else None
    if score is None:
        score = getattr(audit_result, "score", 50.0)

    if score >= AUDIT_GREEN_THRESHOLD:
        return "GREEN"
    elif score >= AUDIT_YELLOW_THRESHOLD:
        return "YELLOW"
    else:
        return "RED"


# ── Reglas deterministas ──────────────────────────────────────────────────────

def _apply_kill_rule(campaign: dict, campaign_type: str) -> Optional[dict]:
    """
    3x Kill Rule: spend > 3x target_CPA AND conversiones == 0
    Solo aplica a campañas Search (no Smart).
    """
    if _is_smart_campaign(campaign):
        return None

    spend = _spend(campaign)
    conv = _conversions(campaign)
    target = _cpa_target(campaign_type)
    threshold = KILL_SPEND_MULTIPLIER * target

    if spend > threshold and conv == 0:
        return {
            "action": "kill",
            "campaign_id": str(campaign.get("id", "")),
            "campaign_name": campaign.get("name", ""),
            "campaign_type": campaign_type,
            "current_daily_budget_mxn": _daily_budget(campaign),
            "new_daily_budget_mxn": None,
            "change_pct": -100.0,
            "reason": f"3x Kill Rule: gasto ${spend:.0f} MXN > {KILL_SPEND_MULTIPLIER}x target ${target:.0f} con 0 conversiones",
            "rule": "KILL_RULE",
            "confidence": 100,
            "requires_haiku": False,
        }
    return None


def _apply_rollback_rule(campaign: dict, campaign_type: str, recent_actions: list) -> Optional[dict]:
    """
    Rollback: CPA subió >15% tras el último aumento de presupuesto.
    Revierte al presupuesto anterior.
    Solo aplica a campañas Search.
    """
    if _is_smart_campaign(campaign):
        return None

    cpa_now = _cpa_real(campaign)
    if cpa_now is None:
        return None

    days_since = _days_since_last_increase(str(campaign.get("id", "")), recent_actions)
    if days_since is None or days_since > 7:
        return None

    cpa_before = _previous_cpa(str(campaign.get("id", "")), recent_actions)
    if cpa_before is None or cpa_before <= 0:
        return None

    increase_ratio = (cpa_now - cpa_before) / cpa_before
    if increase_ratio <= ROLLBACK_CPA_INCREASE_PCT:
        return None

    prev_budget = _previous_budget(str(campaign.get("id", "")), recent_actions)
    current_budget = _daily_budget(campaign)

    return {
        "action": "rollback",
        "campaign_id": str(campaign.get("id", "")),
        "campaign_name": campaign.get("name", ""),
        "campaign_type": campaign_type,
        "current_daily_budget_mxn": current_budget,
        "new_daily_budget_mxn": prev_budget or max(current_budget * (1 - REDUCE_PCT), BUDGET_FLOOR_MXN),
        "change_pct": round(-REDUCE_PCT * 100, 1),
        "reason": f"Rollback: CPA subió {increase_ratio*100:.0f}% ({cpa_before:.0f}→{cpa_now:.0f} MXN) tras aumento de presupuesto hace {days_since} días",
        "rule": "ROLLBACK",
        "confidence": 90,
        "requires_haiku": False,
    }


def _apply_scale_rule(campaign: dict, campaign_type: str, audit_semaphore: str,
                       recent_actions: list) -> Optional[dict]:
    """
    20% Scale Rule: CPA < target -10% AND IS_budget_lost > 20%
    Bloqueado si: semáforo ROJO, campaña Smart, aumento reciente (<3 días).
    Semáforo AMARILLO → marcar requires_haiku=True.
    """
    if _is_smart_campaign(campaign):
        return None

    if audit_semaphore == "RED":
        return None

    cpa_now = _cpa_real(campaign)
    if cpa_now is None:
        return None

    target = _cpa_target(campaign_type)
    scale_threshold = target * (1 - SCALE_CPA_BELOW_TARGET_PCT)

    if cpa_now >= scale_threshold:
        return None

    is_lost = _is_lost_budget(campaign)
    if is_lost < SCALE_IS_BUDGET_LOST_MIN:
        return None

    days_since = _days_since_last_increase(str(campaign.get("id", "")), recent_actions)
    if days_since is not None and days_since < MIN_DAYS_BETWEEN_INCREASES:
        return None

    current_budget = _daily_budget(campaign)
    if current_budget <= 0:
        return None

    new_budget = round(min(current_budget * (1 + SCALE_MAX_PCT), current_budget * 1.20), 2)
    change_pct = round((new_budget - current_budget) / current_budget * 100, 1)

    return {
        "action": "scale",
        "campaign_id": str(campaign.get("id", "")),
        "campaign_name": campaign.get("name", ""),
        "campaign_type": campaign_type,
        "current_daily_budget_mxn": current_budget,
        "new_daily_budget_mxn": new_budget,
        "change_pct": change_pct,
        "reason": f"CPA ${cpa_now:.0f} < target ${scale_threshold:.0f} (-{SCALE_CPA_BELOW_TARGET_PCT*100:.0f}%) AND IS perdido por budget {is_lost*100:.0f}% > {SCALE_IS_BUDGET_LOST_MIN*100:.0f}%",
        "rule": "SCALE_20PCT",
        "confidence": 85 if audit_semaphore == "GREEN" else 60,
        "requires_haiku": audit_semaphore == "YELLOW",
        "audit_semaphore": audit_semaphore,
    }


def _apply_reduce_rule(campaign: dict, campaign_type: str) -> Optional[dict]:
    """
    Reduce: CPA > umbral crítico del tipo.
    Solo aplica a campañas Search con datos suficientes.
    """
    if _is_smart_campaign(campaign):
        return None

    cpa_now = _cpa_real(campaign)
    if cpa_now is None:
        return None

    if _conversions(campaign) < 2:
        return None

    critical = _cpa_critical(campaign_type)
    if cpa_now <= critical:
        return None

    current_budget = _daily_budget(campaign)
    if current_budget <= 0:
        return None

    new_budget = round(max(current_budget * (1 - REDUCE_PCT), BUDGET_FLOOR_MXN), 2)
    change_pct = round((new_budget - current_budget) / current_budget * 100, 1)

    return {
        "action": "reduce",
        "campaign_id": str(campaign.get("id", "")),
        "campaign_name": campaign.get("name", ""),
        "campaign_type": campaign_type,
        "current_daily_budget_mxn": current_budget,
        "new_daily_budget_mxn": new_budget,
        "change_pct": change_pct,
        "reason": f"CPA ${cpa_now:.0f} > crítico ${critical:.0f} MXN para tipo '{campaign_type}'",
        "rule": "REDUCE_CPA_CRITICAL",
        "confidence": 85,
        "requires_haiku": False,
    }


# ── 70/20/10 check ────────────────────────────────────────────────────────────

def _check_70_20_10(campaigns: list, decisions: list) -> list:
    """
    Verifica que la distribución de presupuesto propuesta respete 70/20/10.
    Local+Delivery = min 70% del total.
    Si después de las decisiones el 70% se viola, protege las campañas PROVEN.
    Retorna lista de decisiones corregidas.
    """
    budget_by_id = {}
    for camp in campaigns:
        cid = str(camp.get("id", ""))
        budget_by_id[cid] = _daily_budget(camp)

    for dec in decisions:
        if dec.get("new_daily_budget_mxn") is not None:
            budget_by_id[dec["campaign_id"]] = dec["new_daily_budget_mxn"]

    total = sum(budget_by_id.values())
    if total <= 0:
        return decisions

    proven_budget = sum(
        b for cid, b in budget_by_id.items()
        if any(str(camp.get("id", "")) == cid and _is_smart_campaign(camp) for camp in campaigns)
    )
    proven_pct = proven_budget / total

    if proven_pct < 0.65 and total > 0:
        logger.warning(
            "[budget_optimizer] 70/20/10 warning: PROVEN campaigns = %.0f%% del budget (esperado >=70%%)",
            proven_pct * 100
        )

    return decisions


# ── Redistribución ────────────────────────────────────────────────────────────

def _apply_active_redistribution(decisions: list, campaigns: list) -> list:
    """
    Redistribución activa: el presupuesto liberado por reduces fluye a campañas
    Search en HOLD que tengan CPA bueno e IS perdido alto.
    Principio del skill: el dinero liberado debe ir a donde genera más valor.
    """
    freed_daily = sum(
        d.get("current_daily_budget_mxn", 0) - (d.get("new_daily_budget_mxn") or 0)
        for d in decisions
        if d.get("action") in ("reduce", "rollback", "kill")
        and d.get("new_daily_budget_mxn") is not None
    )

    if freed_daily <= 0:
        return decisions

    camp_map = {str(c.get("id", "")): c for c in campaigns}
    eligible_holds = []

    for dec in decisions:
        if dec.get("action") != "hold":
            continue
        camp = camp_map.get(dec.get("campaign_id", ""), {})
        if _is_smart_campaign(camp):
            continue

        campaign_type = dec.get("campaign_type", "default")
        cpa_now = _cpa_real(camp)
        target = _cpa_target(campaign_type)
        is_lost = _is_lost_budget(camp)

        # Elegible: CPA bueno (< target) Y hay demanda sin capturar (IS > 20%)
        if cpa_now and cpa_now < target and is_lost > SCALE_IS_BUDGET_LOST_MIN:
            eligible_holds.append({
                "decision": dec,
                "cpa_now": cpa_now,
                "target": target,
                "is_lost": is_lost,
                "score": (target - cpa_now) / target * is_lost,
            })

    if not eligible_holds:
        return decisions

    # Priorizar mayor oportunidad (CPA más bajo + IS más alto)
    eligible_holds.sort(key=lambda x: x["score"], reverse=True)

    remaining_to_distribute = freed_daily

    for eh in eligible_holds:
        if remaining_to_distribute <= 0:
            break

        dec = eh["decision"]
        current_budget = dec.get("current_daily_budget_mxn", 0)
        if current_budget <= 0:
            continue

        max_increase = current_budget * SCALE_MAX_PCT
        actual_increase = round(min(max_increase, remaining_to_distribute), 2)
        new_budget = round(current_budget + actual_increase, 2)

        dec["action"] = "scale"
        dec["new_daily_budget_mxn"] = new_budget
        dec["change_pct"] = round(actual_increase / current_budget * 100, 1)
        dec["reason"] = (
            f"Redistribución activa: CPA ${eh['cpa_now']:.0f} < target ${eh['target']:.0f} "
            f"+ IS perdido {eh['is_lost']*100:.0f}%. "
            f"Recibe ${actual_increase:.0f}/día liberados de campañas reducidas."
        )
        dec["rule"] = "REDISTRIBUTION"
        dec["confidence"] = 80

        remaining_to_distribute -= actual_increase
        logger.info(
            "[redistribution] %s: HOLD -> SCALE +$%.0f/día (redistribución de reduces)",
            dec["campaign_name"], actual_increase
        )

    return decisions


def _calculate_redistribution(decisions: list, campaigns: list) -> dict:
    """
    Calcula cuánto presupuesto se liberó con reducciones/kills
    y cuánto se asignó con scales.
    """
    freed_daily = 0.0
    allocated_daily = 0.0
    freed_monthly = 0.0
    allocated_monthly = 0.0

    reduced = []
    scaled = []
    protected = []

    camp_map = {str(c.get("id", "")): c for c in campaigns}

    for dec in decisions:
        current = dec.get("current_daily_budget_mxn", 0)
        new = dec.get("new_daily_budget_mxn")
        camp = camp_map.get(dec.get("campaign_id", ""), {})

        if _is_smart_campaign(camp):
            protected.append({
                "name": dec["campaign_name"],
                "daily_budget": current,
                "reason": "70% protegida — motor del negocio"
            })
            continue

        if dec["action"] in ("reduce", "kill", "rollback") and new is not None:
            delta = current - new
            freed_daily += delta
            freed_monthly += delta * 30
            reduced.append({
                "name": dec["campaign_name"],
                "before": current,
                "after": new,
                "saved_daily": round(delta, 2),
                "saved_monthly": round(delta * 30, 2),
                "reason": dec["reason"],
            })

        elif dec["action"] == "scale" and new is not None:
            delta = new - current
            allocated_daily += delta
            allocated_monthly += delta * 30
            scaled.append({
                "name": dec["campaign_name"],
                "before": current,
                "after": new,
                "added_daily": round(delta, 2),
                "added_monthly": round(delta * 30, 2),
                "reason": dec["reason"],
            })

    net_daily = allocated_daily - freed_daily
    net_monthly = allocated_monthly - freed_monthly

    return {
        "reduced": reduced,
        "scaled": scaled,
        "protected": protected,
        "freed_daily_mxn": round(freed_daily, 2),
        "freed_monthly_mxn": round(freed_monthly, 2),
        "allocated_daily_mxn": round(allocated_daily, 2),
        "allocated_monthly_mxn": round(allocated_monthly, 2),
        "net_daily_mxn": round(net_daily, 2),
        "net_monthly_mxn": round(net_monthly, 2),
    }


# ── Reporte de redistribución ─────────────────────────────────────────────────

def format_redistribution_report(redistribution: dict) -> str:
    """
    Genera el bloque de texto de redistribución para el correo diario.
    """
    lines = ["💰 REDISTRIBUCIÓN DE PRESUPUESTO HOY:"]

    if redistribution["reduced"]:
        lines.append("\n  REDUCIDO:")
        for r in redistribution["reduced"]:
            lines.append(f"  - {r['name']}: ${r['before']:.0f}/dia -> ${r['after']:.0f}/dia (-${r['saved_daily']:.0f}/dia)")
            lines.append(f"    Motivo: {r['reason'][:80]}")
            lines.append(f"    Liberado: ~${r['saved_monthly']:.0f} MXN/mes")

    if redistribution["scaled"]:
        lines.append("\n  ESCALADO:")
        for s in redistribution["scaled"]:
            lines.append(f"  - {s['name']}: ${s['before']:.0f}/dia -> ${s['after']:.0f}/dia (+${s['added_daily']:.0f}/dia)")
            lines.append(f"    Motivo: {s['reason'][:80]}")
            lines.append(f"    Recibe: +${s['added_monthly']:.0f} MXN/mes")

    if redistribution["protected"]:
        lines.append("\n  PROTEGIDO (70% motor del negocio):")
        for p in redistribution["protected"]:
            lines.append(f"  - {p['name']}: ${p['daily_budget']:.0f}/dia — sin cambio")

    net = redistribution["net_daily_mxn"]
    net_monthly = redistribution["net_monthly_mxn"]
    net_sign = "+" if net >= 0 else ""
    lines.append(f"\n  BALANCE NETO: {net_sign}${net:.0f}/dia ({net_sign}${net_monthly:.0f} MXN/mes proyectados)")

    return "\n".join(lines)


# ── Función principal ─────────────────────────────────────────────────────────

def run_budget_optimization(
    campaigns: list,
    audit_result=None,
    negocio_data: dict = None,
    pedidos_gloriafood_24h: int = 0,
    recent_actions: list = None,
    monthly_budget_status: dict = None,
) -> dict:
    """
    Función principal del budget optimizer.

    Args:
        campaigns:              Lista de campañas con métricas Google Ads.
                                Cada campaña debe incluir:
                                - id, name, status, channel_type
                                - cost_micros (o cost_mxn), conversions
                                - daily_budget_mxn (o budget_micros)
                                - search_budget_lost_impression_share
        audit_result:           AuditResult de audit_engine.run_audit() — opcional.
                                Si None, el semáforo queda en YELLOW.
        negocio_data:           Dict de resumen_negocio_para_agente() — opcional.
        pedidos_gloriafood_24h: Pedidos reales de GloriaFood en las últimas 24h.
        recent_actions:         Historial de acciones recientes (últimas 48h).
        monthly_budget_status:  Estado del presupuesto mensual.

    Returns:
        Dict con:
        - decisions: list de decisiones de presupuesto
        - redistribution: dict de resumen de redistribución
        - requires_haiku: list de decisiones que Haiku debe resolver
        - report: str con el reporte formateado
    """
    if not campaigns:
        return {"decisions": [], "redistribution": {}, "requires_haiku": [], "report": ""}

    decisions = []
    requires_haiku = []

    for camp in campaigns:
        if str(camp.get("status", "")).upper() != "ENABLED":
            continue

        campaign_type = _get_campaign_type(camp)
        camp_id = str(camp.get("id", ""))

        # Smart campaigns — protegidas, solo verificación
        if _is_smart_campaign(camp):
            decisions.append({
                "action": "hold",
                "campaign_id": camp_id,
                "campaign_name": camp.get("name", ""),
                "campaign_type": campaign_type,
                "current_daily_budget_mxn": _daily_budget(camp),
                "new_daily_budget_mxn": None,
                "change_pct": 0.0,
                "reason": "Campaña PROVEN (70%) — motor del negocio, protegida",
                "rule": "70_20_10_PROTECTED",
                "confidence": 100,
                "requires_haiku": False,
            })
            continue

        semaphore = _audit_semaphore(audit_result, campaign_type)

        # Aplicar reglas en orden de prioridad
        decision = None

        # 1. Kill Rule — máxima prioridad
        decision = _apply_kill_rule(camp, campaign_type)

        # 2. Rollback — segunda prioridad
        if decision is None:
            decision = _apply_rollback_rule(camp, campaign_type, recent_actions or [])

        # 3. Reduce — CPA crítico
        if decision is None:
            decision = _apply_reduce_rule(camp, campaign_type)

        # 4. Scale — CPA bueno + IS perdido
        if decision is None:
            decision = _apply_scale_rule(camp, campaign_type, semaphore, recent_actions or [])

        # 5. Hold — sin señal clara
        if decision is None:
            cpa_now = _cpa_real(camp)
            decision = {
                "action": "hold",
                "campaign_id": camp_id,
                "campaign_name": camp.get("name", ""),
                "campaign_type": campaign_type,
                "current_daily_budget_mxn": _daily_budget(camp),
                "new_daily_budget_mxn": None,
                "change_pct": 0.0,
                "reason": f"Sin señal clara. CPA ${cpa_now:.0f} MXN" if cpa_now else "Sin conversiones suficientes para decidir",
                "rule": "HOLD",
                "confidence": 50,
                "requires_haiku": semaphore == "YELLOW",
                "audit_semaphore": semaphore,
            }

        decision["context"] = {
            "comensales_ayer": (negocio_data or {}).get("comensales_total", 0),
            "ventas_locales_7d": (negocio_data or {}).get("venta_local_total", 0),
            "pedidos_gloriafood_24h": pedidos_gloriafood_24h,
            "audit_semaphore": semaphore,
            "audit_score": getattr(audit_result, "score", None),
        }

        decisions.append(decision)

        if decision.get("requires_haiku"):
            requires_haiku.append(decision)

    # Verificar 70/20/10
    decisions = _check_70_20_10(campaigns, decisions)

    # Guardrail mensual — compara gasto PROYECTADO del mes contra el cap
    # NO compara el total diario (Local+Delivery siempre dominan y distorsionan)
    if monthly_budget_status:
        spend_so_far = monthly_budget_status.get("spend_so_far", 0)
        days_remaining = monthly_budget_status.get("days_remaining", 30)
        monthly_cap = monthly_budget_status.get("monthly_cap", MONTHLY_CAP_MXN)

        # Solo el incremento incremental que agregarían los scales
        incremental_from_scales = sum(
            (d.get("new_daily_budget_mxn") or 0) - d.get("current_daily_budget_mxn", 0)
            for d in decisions if d.get("action") == "scale"
        )

        # Gasto proyectado = ya gastado + (presupuesto actual + incremento) * días restantes
        current_total_daily = sum(d.get("current_daily_budget_mxn", 0) for d in decisions)
        projected_spend = spend_so_far + (current_total_daily + incremental_from_scales) * days_remaining

        if projected_spend > monthly_cap and days_remaining > 0:
            logger.warning(
                "[budget_optimizer] Guardrail mensual: proyección $%.0f > cap $%.0f — bloqueando scales",
                projected_spend, monthly_cap
            )
            for dec in decisions:
                if dec["action"] == "scale":
                    dec["action"] = "hold"
                    dec["new_daily_budget_mxn"] = None
                    dec["reason"] += f" [BLOQUEADO: proyección ${projected_spend:.0f} > cap ${monthly_cap:.0f}]"
                    dec["change_pct"] = 0.0
                    if dec in requires_haiku:
                        requires_haiku.remove(dec)

    # Redistribución activa: dinero liberado por reduces fluye a campañas elegibles
    decisions = _apply_active_redistribution(decisions, campaigns)

    redistribution = _calculate_redistribution(decisions, campaigns)
    report = format_redistribution_report(redistribution)

    return {
        "decisions": decisions,
        "redistribution": redistribution,
        "requires_haiku": requires_haiku,
        "report": report,
    }
