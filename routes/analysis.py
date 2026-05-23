"""
Routes de Análisis — análisis de keywords, campañas, insights, historial, estrategia,
actividad del sistema.
"""
import os
import sqlite3
import logging
import unicodedata
from typing import Optional, List, Dict
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from engine.db_sync import get_db_path
from routes.auth_token import require_token
from engine.risk_classifier import get_campaign_thresholds
from engine.search_term_classifier import classify_conversion_quality, classify_search_term, _normalize
from engine.search_term_history import aggregate_windows, accumulated_reds
from engine.ads_client import fetch_negative_keywords, fetch_search_term_conversion_breakdown
from engine.negative_matcher import find_blocking_negative

router = APIRouter(tags=["analysis"])
logger = logging.getLogger(__name__)

# Models used by these routes
class OptimizationAction(BaseModel):
    type: str
    keyword: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    spend: Optional[float] = None
    reason: Optional[str] = None
    match_type: Optional[str] = None  # EXACT|PHRASE desde /negativos (suggested_match_type)

class ExecuteOptimizationRequest(BaseModel):
    actions: List[OptimizationAction]


def _get_engine():
    from main import get_engine_modules
    return get_engine_modules()

def _detect_waste(campaigns, keywords, search_terms):
    from agents.strategist import Strategist
    return Strategist().detect_waste(campaigns, keywords, search_terms)

def _analyze_hourly(ga4_data):
    from agents.strategist import Strategist
    return Strategist().analyze_hourly_patterns(ga4_data)


@router.get("/analyze-keywords")
async def analyze_keywords():
    try:
        engine = _get_engine()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        keywords = engine["fetch_keyword_data"](client, target_id)
        search_terms = engine["fetch_search_term_data"](client, target_id)

        formatted_keywords = []
        total_waste_spend = 0
        waste_count = 0

        for kw in keywords:
            spend = kw.get("cost_micros", 0) / 1_000_000
            conversions = float(kw.get("conversions", 0))
            clicks = int(kw.get("clicks", 0))
            impressions = int(kw.get("impressions", 0))
            cpa = spend / conversions if conversions > 0 else 0
            ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0

            if spend > 50 and conversions == 0:
                status = "waste"
                action = "Bloquear inmediatamente"
                total_waste_spend += spend
                waste_count += 1
            elif cpa > 20:
                status = "high_cpa"
                action = "Reducir bid o pausar"
            elif conversions > 0 and cpa <= 15:
                status = "high_performer"
                action = "Escalar presupuesto"
            else:
                status = "needs_review"
                action = "Monitorear"

            formatted_keywords.append({
                "text": kw.get("text", ""),
                "campaign": kw.get("campaign_name", ""),
                "campaign_id": str(kw.get("campaign_id", "")),
                "spend": round(spend, 2),
                "conversions": round(conversions, 1),
                "cpa": round(cpa, 2),
                "ctr": ctr,
                "impressions": impressions,
                "clicks": clicks,
                "status": status,
                "action": action
            })

        neg_suggestions = []
        for st in search_terms:
            st_spend = st.get("cost_micros", 0) / 1_000_000
            st_conv = float(st.get("conversions", 0))
            if st_spend > 20 and st_conv == 0:
                neg_suggestions.append({"term": st.get("query", ""), "spend": round(st_spend, 2)})

        return {
            "status": "success",
            "keywords": formatted_keywords,
            "summary": {
                "total": len(formatted_keywords),
                "waste": waste_count,
                "total_waste_spend": round(total_waste_spend, 2),
                "potential_savings": round(total_waste_spend, 2)
            },
            "negative_suggestions": neg_suggestions[:20]
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}


VALID_DATE_RANGES = {
    "TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS",
    "LAST_30_DAYS", "THIS_MONTH", "LAST_MONTH",
}


_THAI_KEYWORDS = ("thai", "tailand", "pad", "curry")

# Listas de clasificacion (todas son matches por substring tras _norm):
#  - BRAND_TERMS: nunca negative_candidate. Marca propia (no bloquear tu
#    marca) + competidor protegido que decidiste NO auto-negativizar
#    (incluye "casa thai", competidor con "thai" en el nombre).
#  - FORCE_COMPETITOR_TERMS: SIEMPRE competitor_term cuando hay conversiones.
#    Sobrescribe el filtro Thai por substring: para competidores cuyo nombre
#    contiene "thai" pero NO deben contar como conversion thai propia
#    (p.ej. "casa thai" -> seccion ambar, no convThai).
#  - COMPETITOR_THAI_TERMS: NUNCA competitor_term (lista de supresion para
#    el bucket ambar). Vacia tras mover "casa thai" a FORCE el 19-may-2026.
#    Mantenida como hook arquitectonico simetrico a FORCE.
_BRAND_TERMS = ("thai thai", "thaithaimerida", "casa thai")
_FORCE_COMPETITOR_TERMS = ("casa thai",)
_COMPETITOR_THAI_TERMS = ()


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _matches_any(query, terms):
    q = _norm(query)
    return any(t in q for t in terms)


def _is_negative_candidate(query, cost, conversions):
    """Candidato a negativo: gasto > $10 y 0 conversiones. NUNCA si la query
    hace match con BRAND_TERMS (marca propia o competidor thai protegido,
    p.ej. "casa thai")."""
    if _matches_any(query, _BRAND_TERMS):
        return False
    return cost > 10 and conversions == 0


def _is_competitor_term(query, conversions):
    """convInesperada: tuvo conversion (>=1) y NO es Thai propia. Orden:
    1) sin conversiones -> False.
    2) match con FORCE_COMPETITOR_TERMS -> True (override del filtro Thai;
       competidor con "thai" en el nombre, p.ej. "casa thai").
    3) match con COMPETITOR_THAI_TERMS -> False (supresion ambar reservada).
    4) default: True si la query NO contiene ninguna palabra Thai
       (_THAI_KEYWORDS). Mismo criterio que SearchTermsReport.gs, que ya
       consume este flag (NO recalcular regla Thai en el .gs)."""
    if conversions < 1:
        return False
    if _matches_any(query, _FORCE_COMPETITOR_TERMS):
        return True
    if _matches_any(query, _COMPETITOR_THAI_TERMS):
        return False
    q = _norm(query)
    return not any(k in q for k in _THAI_KEYWORDS)


@router.get("/search-terms")
async def search_terms(date_range: str = "LAST_7_DAYS"):
    """
    Lista los search terms de la cuenta para el rango indicado.

    Fase 1: cada termino se clasifica por CONTENIDO (engine.search_term_classifier)
    en rojo|amarillo|verde|blanco con confidence, false_positive_risk, reason,
    suggested_negative, suggested_match_type y auto_apply (SIEMPRE False).
    El gasto NO clasifica; solo acota el pool a top-100 y ordena dentro de grupo.
    Incluye shim retrocompatible (negative_candidate/competitor_term) para el
    monitor pre-Fase 1. Endpoint read-only (solo Google Ads).
    """
    try:
        date_range = date_range.strip().upper()
        if date_range not in VALID_DATE_RANGES:
            return {
                "status": "error",
                "message": f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
            }
        engine = _get_engine()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        raw_terms = engine["fetch_search_term_data"](client, target_id, date_range)
        conversion_breakdown = fetch_search_term_conversion_breakdown(client, target_id, date_range)

        # Pool top-100 por gasto. Fase 1: el gasto solo acota el pool (no clasifica).
        # NOTA Fase 1: top-100 NO resuelve irrelevantes de gasto muy bajo;
        # la acumulacion historica 7/30/90d queda para Fase 2.
        raw_top = sorted(raw_terms, key=lambda st: st.get("cost_micros", 0), reverse=True)[:100]

        _GROUP_ORDER = {"rojo": 0, "amarillo": 1, "verde": 2, "blanco": 3}
        formatted = []
        for st in raw_top:
            cost = st.get("cost_micros", 0) / 1_000_000
            conversions = float(st.get("conversions", 0))
            all_conversions = float(st.get("all_conversions", conversions) or 0)
            breakdown_key = (_normalize(st.get("query", "")), str(st.get("campaign_id", "")))
            breakdown = (conversion_breakdown or {}).get(breakdown_key) if conversion_breakdown is not None else None
            conversion_quality = classify_conversion_quality(
                breakdown.get("actions") if breakdown else None,
                conversions=breakdown.get("conversions", conversions) if breakdown else conversions,
                all_conversions=breakdown.get("all_conversions", all_conversions) if breakdown else all_conversions,
            )
            term = classify_search_term(
                st.get("query", ""),
                cost,
                conversions,
                conversion_quality=conversion_quality,
            )
            term.update({
                "campaign_name": st.get("campaign_name", ""),
                "campaign_id": str(st.get("campaign_id", "")),
                "clicks": int(st.get("clicks", 0)),
                "impressions": int(st.get("impressions", 0)),
                "cost": round(cost, 2),
                "conversions": round(conversions, 1),
                "all_conversions": round(all_conversions, 1),
                # Shim retrocompatible para el monitor pre-Fase 1:
                "negative_candidate": term["classification"] == "rojo",
                "competitor_term": term["classification"] == "amarillo",
            })
            formatted.append(term)

        # Orden final: rojos -> amarillos -> verdes/blancos; dentro de grupo, gasto desc.
        formatted.sort(key=lambda t: (_GROUP_ORDER.get(t["classification"], 9), -t["cost"]))

        # Fase 2: enriquecer con ventanas historicas + acumulados (aditivo, retrocompat).
        # Solo LEE el historial local (read-only respecto a Google Ads).
        _norms = [_normalize(t["query"]) for t in formatted]
        _agg = aggregate_windows(_norms)
        for t in formatted:
            a = _agg.get(_normalize(t["query"]), {})
            t["cost_7d"] = a.get("cost_7d", 0.0)
            t["cost_30d"] = a.get("cost_30d", 0.0)
            t["cost_90d"] = a.get("cost_90d", 0.0)
            t["distinct_days_30d"] = a.get("distinct_days_30d", 0)
            t["distinct_weeks_90d"] = a.get("distinct_weeks_90d", 0)
            t["recurrent"] = a.get("distinct_weeks_90d", 0) >= 2

        # #2/#3: marcar terminos ya bloqueados como negativos (read-only, nivel campana).
        try:
            _negs_by_campaign = fetch_negative_keywords(client, target_id)
        except Exception:
            _negs_by_campaign = {}
        for t in formatted:
            _camp = _negs_by_campaign.get(str(t.get("campaign_id", "")), {})
            _blocking = find_blocking_negative(t["query"], _camp.get("negatives", []))
            t["already_negative"] = _blocking is not None
            t["blocked_by"] = ({"text": _blocking["text"], "match_type": _blocking["match_type"]}
                               if _blocking else None)
            t["negative_smart_uncertain"] = bool(_blocking) and _camp.get("channel_type") == "SMART"

        counts = {k: sum(1 for t in formatted if t["classification"] == k)
                  for k in ("rojo", "amarillo", "verde", "blanco")}

        return {
            "status": "success",
            "date_range": date_range,
            "total": len(formatted),
            "counts": counts,
            # Shim retrocompatible:
            "negative_candidates": counts["rojo"],
            "competitor_terms": counts["amarillo"],
            "search_terms": formatted,
            # Fase 2: rojos recurrentes/acumulados (aditivo, tope 10). auto_apply=False.
            "accumulated_reds": accumulated_reds(today_top100_norms=_norms),
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}


@router.post("/snapshot-search-terms", dependencies=[Depends(require_token)])
async def snapshot_search_terms() -> dict:
    """Snapshot diario READ-ONLY de search terms para el historial Fase 2.1.

    Lee YESTERDAY de Google Ads, clasifica con Fase 1 y persiste via snapshot_terms,
    estampando snapshot_date = ayer (America/Merida) -> evita doble conteo (un dia
    completo por corrida, NUNCA ventana multi-dia). Protegido con X-API-Token.

    NO ejecuta run_autonomous_audit, NO toca presupuestos, NO aplica negativos,
    NO manda correo, NO ejecuta BA1/BA2 ni recomendaciones. Solo LEE Google Ads
    (fetch_search_term_data) y escribe su propio SQLite/GCS via snapshot_terms.
    """
    from datetime import timedelta
    from engine.search_term_history import snapshot_terms
    try:
        from zoneinfo import ZoneInfo
        _yesterday = (datetime.now(ZoneInfo("America/Merida")) - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        _yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        engine = _get_engine()
        if not engine:
            return {"status": "error", "message": "Engine not available", "snapshot_date": _yesterday}
        customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        raw_terms = engine["fetch_search_term_data"](client, customer_id, "YESTERDAY")

        classified = []
        for st in (raw_terms or []):
            cost = st.get("cost_micros", 0) / 1_000_000
            conv = float(st.get("conversions", 0) or 0)
            term = classify_search_term(st.get("query", ""), cost, conv)
            term.update({
                "query_raw": st.get("query", ""),
                "campaign_id": str(st.get("campaign_id", "")),
                "campaign_name": st.get("campaign_name", ""),
                "cost": round(cost, 2),
                "conversions": round(conv, 1),
                "clicks": int(st.get("clicks", 0) or 0),
                "impressions": int(st.get("impressions", 0) or 0),
            })
            classified.append(term)

        res = snapshot_terms(classified, snapshot_date=_yesterday)
        return {
            "status": "skipped" if res.get("skipped_reason") else "success",
            "date_range": "YESTERDAY",
            "snapshot_date": _yesterday,
            "inserted": res.get("inserted", 0),
            "ignored": res.get("ignored", 0),
            "pruned": res.get("pruned", 0),
            "gcs_synced": res.get("gcs_synced", False),
            "skipped_reason": res.get("skipped_reason"),
        }
    except Exception as e:
        logger.error("snapshot-search-terms fallo: %s", e)
        return {"status": "error", "message": str(e), "snapshot_date": _yesterday}


@router.get("/ads-report")
async def ads_report(date_range: str = "LAST_7_DAYS"):
    """
    Reporte por anuncio: titulos, descripciones, aprobacion y ad_strength
    (estado ACTUAL via fetch_ad_health) cruzados por ad_id con CTR / clics /
    impresiones / conversiones del rango (fetch_ad_metrics).

    Spine = anuncios con actividad en el rango: los que no tuvieron
    impresiones no aparecen. date_range solo afecta las metricas; el creativo
    y la aprobacion son el estado actual, no historico.
    Ordenado por CTR desc, maximo 20. Solo lectura.
    """
    try:
        date_range = date_range.strip().upper()
        if date_range not in VALID_DATE_RANGES:
            return {
                "status": "error",
                "message": f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
            }
        engine = _get_engine()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()

        # No estan en el registry get_engine_modules() -> import directo
        # (mismo patron que routes/debug_fase_6d.py para fetch_ad_health).
        from engine.ads_client import fetch_ad_health, fetch_ad_metrics
        health = fetch_ad_health(client, target_id)
        metrics = fetch_ad_metrics(client, target_id, date_range)

        health_by_id = {h.get("ad_id"): h for h in health}

        ads = []
        for m in metrics:
            h = health_by_id.get(m.get("ad_id"), {})
            ads.append({
                "ad_id":           m.get("ad_id", ""),
                "campaign_name":   h.get("campaign_name", ""),
                "ad_group_name":   h.get("ad_group_name", ""),
                "ad_strength":     h.get("ad_strength"),
                "approval_status": h.get("approval_status"),
                "headlines":       h.get("headlines", []),
                "descriptions":    h.get("descriptions", []),
                "ctr_pct":         round(float(m.get("ctr", 0)) * 100, 2),
                "clicks":          int(m.get("clicks", 0)),
                "impressions":     int(m.get("impressions", 0)),
                "conversions":     round(float(m.get("conversions", 0)), 1),
            })

        ads.sort(key=lambda a: a["ctr_pct"], reverse=True)
        ads = ads[:20]

        return {
            "status": "success",
            "date_range": date_range,
            "total": len(ads),
            "ads": ads,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}


# Local (22612348265) y Experiencia 2026 (23730364039) miden por conversiones
# SECUNDARIAS por diseno (reserva_completada / micros de sistema). metrics.conversions
# (solo primarias) siempre da ~0 para ellas -> falso "Sin conversiones / Pausar".
# Para estas dos, la logica de semaforo/alertas/acciones usa all_conversions.
# Delivery y Delivery Search siguen usando conversions (su primaria click_pedir_online).
ALL_CONVERSIONS_CAMPAIGN_IDS = {"22612348265", "23730364039"}


@router.get("/analyze-campaigns-detailed")
async def analyze_campaigns_detailed(date_range: str = "YESTERDAY"):
    try:
        date_range = date_range.strip().upper()
        if date_range not in VALID_DATE_RANGES:
            return {
                "status": "error",
                "message": f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
            }
        engine = _get_engine()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id, date_range)
        keywords = engine["fetch_keyword_data"](client, target_id, date_range)
        search_terms = engine["fetch_search_term_data"](client, target_id, date_range)

        waste_data = _detect_waste(campaigns, keywords, search_terms)
        waste_by_campaign = {}
        for item in waste_data["critical_items"] + waste_data["high_priority"]:
            cid = item.get("campaign_id", "")
            waste_by_campaign[cid] = waste_by_campaign.get(cid, 0) + item["spend"]

        formatted = []
        cnt = {"total": 0, "critical": 0, "warning": 0, "good": 0, "excellent": 0, "total_waste": 0.0}

        for c in campaigns:
            spend = c.get("cost_micros", 0) / 1_000_000
            conversions = float(c.get("conversions", 0))
            all_conversions = float(c.get("all_conversions", 0))
            clicks = int(c.get("clicks", 0))
            impressions = int(c.get("impressions", 0))
            ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0
            camp_id = str(c.get("id", ""))
            waste = waste_by_campaign.get(camp_id, 0)

            if camp_id in ALL_CONVERSIONS_CAMPAIGN_IDS:
                effective_conversions = all_conversions
            else:
                effective_conversions = conversions
            effective_cpa = spend / effective_conversions if effective_conversions > 0 else 0

            cfg = get_campaign_thresholds(c.get("name", ""), camp_id)
            cpa_ideal    = cfg["cpa_ideal"]
            cpa_max      = cfg["cpa_max"]
            cpa_critical = cfg["cpa_critical"]
            min_spend    = cfg["min_spend_to_block"]

            if effective_conversions == 0 and spend > min_spend:
                semaphore = "critical"
                alerts = [f"Sin conversiones con gasto ${spend:.2f} (umbral ${min_spend:.0f})"]
                actions = ["Pausar campaña", "Revisar targeting"]
            elif effective_cpa > cpa_critical:
                semaphore = "critical"
                alerts = [f"CPA ${effective_cpa:.2f} sobre crítico ${cpa_critical:.0f} (ideal ${cpa_ideal:.0f})"]
                actions = ["Reducir bids", "Revisar keywords"]
            elif effective_cpa > cpa_max:
                semaphore = "warning"
                alerts = [f"CPA ${effective_cpa:.2f} sobre máximo ${cpa_max:.0f} (ideal ${cpa_ideal:.0f})"]
                actions = ["Optimizar bids"]
            elif 0 < effective_cpa <= cpa_ideal:
                semaphore = "excellent"
                alerts = []
                actions = ["Escalar presupuesto"]
            else:
                semaphore = "good"
                alerts = []
                actions = ["Monitorear"]

            cnt[semaphore] = cnt.get(semaphore, 0) + 1
            cnt["total"] += 1
            cnt["total_waste"] += waste

            formatted.append({
                "id": camp_id,
                "name": c.get("name", ""),
                "spend": round(spend, 2),
                "conversions": round(conversions, 1),
                "all_conversions": round(all_conversions, 1),
                "cpa": round(effective_cpa, 2),
                "ctr": ctr,
                "impressions": impressions,
                "clicks": clicks,
                "semaphore": semaphore,
                "alerts": alerts,
                "recommended_actions": actions,
                "waste_detected": round(waste, 2)
            })

        # ── Desglose rastreable de total_waste ───────────────────────────
        # cnt["total_waste"] = suma de item["spend"] de critical_items[:5]
        # + high_priority[:5], SOLO para campañas presentes en la respuesta.
        # Aquí reconstruimos esa misma composición para que el email pueda
        # decir de qué está hecho el número sin abrir Google Ads.
        _present_ids = {str(c.get("id", "")) for c in campaigns}
        _waste_items = waste_data.get("critical_items", []) + waste_data.get("high_priority", [])
        _contributing = [
            it for it in _waste_items
            if str(it.get("campaign_id", "")) in _present_ids
        ]
        _excluded = [
            it for it in _waste_items
            if str(it.get("campaign_id", "")) not in _present_ids
        ]
        _kw = [it for it in _contributing if it.get("type") == "keyword"]
        _camp = [it for it in _contributing if it.get("type") == "campaign"]
        _wsum = waste_data.get("summary", {})
        _full_count = _wsum.get("keywords_to_block", 0) + _wsum.get("campaigns_to_pause", 0)
        _capped = _full_count > len(_waste_items)

        _parts = []
        if _kw:
            _parts.append(f"{len(_kw)} keyword(s) con gasto ≥ $50 y 0 conv.")
        if _camp:
            _parts.append(f"{len(_camp)} campaña(s) con gasto > $100 y 0 conv.")
        _desc = (
            f"{len(_contributing)} ítem(s): " + " + ".join(_parts)
            if _parts else "sin ítems de desperdicio detectados"
        )
        _desc += f" — rango {date_range}"
        if _capped:
            _desc += "; lista recortada a top 5 críticos + top 5 altos"
        if _excluded:
            _desc += f"; {len(_excluded)} ítem(s) no sumado(s) (campaña fuera del reporte)"

        return {
            "status": "success",
            "date_range": date_range,
            "campaigns": formatted,
            "summary": {
                "total": cnt["total"],
                "critical": cnt.get("critical", 0),
                "warning": cnt.get("warning", 0),
                "excellent": cnt.get("excellent", 0),
                "total_waste": round(cnt["total_waste"], 2),
                "total_waste_desc": _desc,
                "total_waste_items": len(_contributing),
                "total_waste_keywords": len(_kw),
                "total_waste_campaigns": len(_camp),
                "total_waste_excluded": len(_excluded),
                "total_waste_capped": _capped
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}


@router.post("/execute-optimization", dependencies=[Depends(require_token)])
async def execute_optimization(request: ExecuteOptimizationRequest):
    try:
        engine = _get_engine()
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        results = []

        for action in request.actions:
            if action.type == "block_keyword" and engine and action.keyword and action.campaign_id:
                # ── Fail-closed match_type (micro-fase) ──────────────────────
                # La mini-app /negativos envia suggested_match_type del clasificador
                # (EXACT en entidades curadas, PHRASE en patrones rojos). Aqui:
                #  - ausente   -> NO se aplica (no caer nunca en el default BROAD).
                #  - BROAD      -> rechazado desde /negativos por ahora.
                #  - != EXACT/PHRASE -> rechazado.
                mt = (action.match_type or "").strip().upper()
                if mt == "":
                    result = {"action": action.type, "target": action.keyword,
                              "status": "rejected",
                              "message": "match_type ausente: no se aplica negativo (fail-closed)."}
                elif mt == "BROAD":
                    result = {"action": action.type, "target": action.keyword,
                              "status": "rejected",
                              "message": "BROAD no permitido desde /negativos."}
                elif mt not in ("EXACT", "PHRASE"):
                    result = {"action": action.type, "target": action.keyword,
                              "status": "rejected",
                              "message": f"match_type invalido: {action.match_type!r} (permitidos EXACT, PHRASE)."}
                else:
                    client = engine["get_ads_client"]()
                    try:
                        ank = engine["add_negative_keyword"](
                            client, target_id, action.campaign_id, action.keyword, match_type=mt)
                        if isinstance(ank, dict) and ank.get("status") in ("error", "rejected"):
                            logger.error("execute_optimization: add_negative_keyword %s kw=%r camp=%s mt=%s: %s",
                                         ank.get("status"), action.keyword, action.campaign_id, mt, ank.get("message"))
                            result = {"action": action.type, "target": action.keyword,
                                      "status": ank.get("status"), "message": ank.get("message", "error")}
                        else:
                            result = {"action": action.type, "target": action.keyword,
                                      "status": "executed",
                                      "match_type": ank.get("match_type", mt) if isinstance(ank, dict) else mt}
                    except Exception as ex:
                        logger.exception("execute_optimization: excepcion add_negative_keyword kw=%r camp=%s",
                                         action.keyword, action.campaign_id)
                        result = {"action": action.type, "target": action.keyword, "status": "error", "message": str(ex)}
            else:
                result = {"action": action.type, "status": "recorded", "manual_required": True}

            try:
                conn = sqlite3.connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO decisions (decision_type, reason, confidence_score, executed, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (action.type, action.reason or "Acción desde dashboard", 90, 1 if result.get("status") == "executed" else 0)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

            results.append(result)

        return {
            "status": "success",
            "executed": len([r for r in results if r.get("status") in ("executed", "recorded")]),
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/insights")
async def get_insights():
    try:
        engine = _get_engine()
        ga4_data = {}
        if engine:
            try:
                ga4_data = engine["fetch_ga4_events_detailed"](days=7)
            except Exception:
                pass

        hour_data = _analyze_hourly(ga4_data)
        peak_hours_dict = {}
        if hour_data and hour_data.get("heatmap_data"):
            vals = hour_data["heatmap_data"]["values"]
            for h in range(24):
                peak_hours_dict[h] = vals[0][h] if vals else 0

        return {"status": "success", "insights": {"peak_hours": peak_hours_dict}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/history")
async def get_history(days: int = 30):
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute(
            "SELECT decision_type, reason, confidence_score, created_at, executed FROM decisions WHERE created_at >= datetime('now', ? || ' days') ORDER BY created_at DESC",
            (f"-{days}",)
        )
        rows = cursor.fetchall()
        conn.close()

        history = [{
            "decision_type": r[0],
            "reason": r[1],
            "confidence_score": r[2],
            "created_at": r[3],
            "executed": bool(r[4]),
            "success": bool(r[4])
        } for r in rows]

        total = len(history)
        executed = sum(1 for h in history if h["executed"])
        return {
            "status": "success",
            "history": history,
            "summary": {
                "total_decisions": total,
                "successful": executed,
                "executed": executed,
                "success_rate": round(executed / total * 100) if total > 0 else 0
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/generate-strategy")
async def generate_strategy():
    try:
        engine = _get_engine()
        campaigns = []
        if engine:
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client = engine["get_ads_client"]()
                campaigns = engine["fetch_campaign_data"](client, target_id)
            except Exception:
                pass

        total_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns)
        total_conv = sum(float(c.get("conversions", 0)) for c in campaigns)
        avg_cpa = round(total_spend / total_conv, 2) if total_conv > 0 else 0

        return {
            "status": "success",
            "recommendations": {
                "key_metrics": {
                    "CPA Actual": avg_cpa,
                    "CPA Target": 15,
                    "Gasto Total": round(total_spend, 2),
                    "Conversiones": round(total_conv, 1)
                },
                "campaign_ideas": [
                    {
                        "title": "Escalar campaña Local",
                        "description": "La campaña Local suele tener mejor CPA que Delivery. Considera aumentar budget 20% si CPA <= $15.",
                        "priority": "high",
                        "expected_roi": "+20% conversiones"
                    },
                    {
                        "title": "Agregar extensiones de llamada",
                        "description": "Los anuncios con número de teléfono tienen 30% más CTR en restaurantes.",
                        "priority": "medium",
                        "expected_roi": "+30% CTR"
                    },
                    {
                        "title": "Bloquear búsquedas de recetas",
                        "description": "Términos como 'receta pad thai' no convierten. Agregar como negativos.",
                        "priority": "high",
                        "expected_roi": "Ahorro directo en desperdicio"
                    }
                ]
            },
            "waste_opportunities": {}
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/last-activity")
async def get_last_activity():
    """Retorna el estado de actividad más reciente del sistema."""
    from engine.activity_log import get_last_activity as _get_last
    try:
        return {"status": "ok", **_get_last()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/activity-log")
async def get_activity_log_endpoint(n: int = 14):
    """Retorna el historial de las últimas n corridas del sistema (máximo 30)."""
    from engine.activity_log import get_activity_log as _get_log
    try:
        runs = _get_log(n=min(n, 30))
        return {"status": "ok", "runs": runs, "count": len(runs)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/last-email-preview")
async def get_last_email_preview_endpoint():
    """Retorna el último daily_summary enviado exitosamente."""
    from engine.email_observability import get_last_email_preview as _get_preview
    try:
        preview = _get_preview()
        return {"status": "ok", "preview": preview}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
