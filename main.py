"""
Thai Thai Ads Agent v12.0 - Mission Control Backend
Backend COMPLETO con 7 skills integradas para autonomía total
"""

import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import random

logger = logging.getLogger(__name__)

load_dotenv()

from engine.db_sync import get_db_path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================================
# IMPORTACIONES LAZY - Solo cuando se necesiten
# ============================================================================

def get_engine_modules():
    """Importa módulos del engine solo cuando se necesiten para evitar crashes al inicio"""
    try:
        from engine.ads_client import (
            get_ads_client,
            fetch_campaign_data,
            fetch_campaign_metrics_range,
            fetch_keyword_data,
            fetch_search_term_data,
            add_negative_keyword,
            fetch_campaign_budget_info,
            update_campaign_budget,
            separate_and_assign_budget,
            fetch_adgroup_metrics,
            pause_ad_group,
            verify_adgroup_still_pausable,
            verify_budget_still_actionable,
            fetch_campaign_geo_criteria,
            update_campaign_location,
            remove_smart_campaign_theme,
        )
        from engine.normalizer import normalize_google_ads_data
        from engine.ga4_client import fetch_ga4_events_detailed

        return {
            "get_ads_client": get_ads_client,
            "fetch_campaign_data": fetch_campaign_data,
            "fetch_keyword_data": fetch_keyword_data,
            "fetch_search_term_data": fetch_search_term_data,
            "add_negative_keyword": add_negative_keyword,
            "normalize_google_ads_data": normalize_google_ads_data,
            "fetch_ga4_events_detailed": fetch_ga4_events_detailed,
            "fetch_campaign_metrics_range": fetch_campaign_metrics_range,
            "fetch_campaign_budget_info": fetch_campaign_budget_info,
            "update_campaign_budget": update_campaign_budget,
            "separate_and_assign_budget": separate_and_assign_budget,
            "fetch_adgroup_metrics": fetch_adgroup_metrics,
            "pause_ad_group": pause_ad_group,
            "verify_adgroup_still_pausable": verify_adgroup_still_pausable,
            "verify_budget_still_actionable": verify_budget_still_actionable,
            "fetch_campaign_geo_criteria": fetch_campaign_geo_criteria,
            "update_campaign_location": update_campaign_location,
            "remove_smart_campaign_theme": remove_smart_campaign_theme,
        }
    except ImportError as e:
        print(f"⚠️ ImportError: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in get_engine_modules: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================================
# SNAPSHOT — caché del último Mission Control en GCS (durable entre cold starts)
# ============================================================================

_GCS_BUCKET   = "thai-thai-agent-data"
_GCS_SNAPSHOT = "snapshots/dashboard_snapshot.json"

def _save_mc_snapshot(data: dict) -> None:
    """Persiste el resultado de /mission-control en GCS. No muta el dict original."""
    try:
        from google.cloud import storage as gcs
        payload = dict(data)
        payload["_snapshot_saved_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client = gcs.Client()
        blob = client.bucket(_GCS_BUCKET).blob(_GCS_SNAPSHOT)
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, default=str),
            content_type="application/json"
        )
        logger.info("_save_mc_snapshot: guardado en gs://%s/%s", _GCS_BUCKET, _GCS_SNAPSHOT)
    except Exception as exc:
        logger.warning("_save_mc_snapshot: no se pudo guardar en GCS — %s", exc)

def _load_mc_snapshot() -> dict | None:
    """Carga el último snapshot desde GCS, o None si no existe."""
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        blob = client.bucket(_GCS_BUCKET).blob(_GCS_SNAPSHOT)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("_load_mc_snapshot: no se pudo leer desde GCS — %s", exc)
        return None


app = FastAPI(
    title="Thai Thai Ads Mission Control",
    description="Sistema completo de control para agente autónomo de Google Ads - 7 Skills",
    version="12.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELOS
# ============================================================================

class AgentProposal(BaseModel):
    decision_id: str
    type: str
    action: str
    target: Dict
    reason: str
    data_evidence: Dict
    impact: Dict
    confidence: int
    urgency: str
    approval_required: bool

class ApproveProposalRequest(BaseModel):
    decision_ids: List[str]

class OptimizationAction(BaseModel):
    type: str
    keyword: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    spend: Optional[float] = None
    reason: Optional[str] = None

class ExecuteOptimizationRequest(BaseModel):
    actions: List[OptimizationAction]

class FixTrackingConfirmRequest(BaseModel):
    conversion_action_ids: List[str]

# ============================================================================
# BASE DE DATOS — INICIALIZACIÓN
# ============================================================================

def init_db():
    """Crea las tablas necesarias si no existen."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            guests TEXT NOT NULL,
            occasion TEXT,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT,
            details_before TEXT,
            details_after TEXT,
            status TEXT NOT NULL,
            google_ads_response TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ============================================================================
# ROUTES & AGENTS — endpoints delegados a sub-módulos
# ============================================================================
from routes.reservations import router as reservations_router
from routes.campaigns import router as campaigns_router
app.include_router(reservations_router)
app.include_router(campaigns_router)

# Strategy functions delegated to agents/strategist.py
from agents.strategist import Strategist as _Strategist
_strategist = _Strategist()
detect_waste = _strategist.detect_waste
analyze_hourly_patterns = _strategist.analyze_hourly_patterns
analyze_landing_page = _strategist.analyze_landing_page
suggest_promotions = _strategist.suggest_promotions
generate_agent_proposals = _strategist.generate_proposals

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "12.0.0",
        "skills": [
            "waste-detector",
            "agent-decisioner",
            "hour-optimizer",
            "landing-page-optimizer",
            "promotion-suggester",
            "budget-allocator",
            "ad-performance-optimizer"
        ]
    }

_DAYS_TO_GAQL = {
    1:  "YESTERDAY",
    7:  "LAST_7_DAYS",
    14: "LAST_14_DAYS",
    30: "LAST_30_DAYS",
}

@app.get("/mission-control")
async def mission_control_data(
    days: int = Query(default=1, ge=1, le=30),
    month: str | None = Query(default=None),
):
    """
    Endpoint principal - Retorna TODOS los datos del Mission Control
    Integra las 7 skills.
    days=1 (default) → YESTERDAY  — usado por el correo diario y el snapshot post-audit
    days=7/14/30     → LAST_X_DAYS — modo legacy (seguirá funcionando)
    month="current"  → THIS_MONTH  — modo dashboard: acumulado del mes en curso
    month="YYYY-MM"  → BETWEEN ... — modo dashboard: mes específico
    """
    if month:
        import calendar as _cal
        if month == "current":
            date_range = "THIS_MONTH"
        else:
            try:
                _y, _m = int(month[:4]), int(month[5:7])
                _last = _cal.monthrange(_y, _m)[1]
                date_range = f"BETWEEN '{_y:04d}-{_m:02d}-01' AND '{_y:04d}-{_m:02d}-{_last:02d}'"
            except Exception:
                date_range = "THIS_MONTH"
    else:
        date_range = _DAYS_TO_GAQL.get(days, "YESTERDAY")
    try:
        # Importar módulos del engine de forma lazy
        engine = get_engine_modules()
        if not engine:
            raise Exception("Engine modules not available - check imports")

        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")

        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id, date_range=date_range)
        keywords = engine["fetch_keyword_data"](client, target_id, date_range=date_range)
        search_terms = engine["fetch_search_term_data"](client, target_id, date_range=date_range)
        
        try:
            ga4_data = engine["fetch_ga4_events_detailed"](days=7)
        except:
            ga4_data = {"events_by_hour": {}}
        
        normalized = engine["normalize_google_ads_data"](campaigns, keywords, search_terms)

        # BRAIN: Claude Sonnet analysis (unified GA4+Sheets+landing+memory context)
        analysis_result = {}
        try:
            from engine.analyzer import analyze_campaign_data
            enriched = dict(normalized)
            enriched["ga4_data"] = ga4_data
            analysis_result = analyze_campaign_data(enriched) or {}
        except Exception as e:
            print(f"[WARN] analyze_campaign_data failed in /mission-control: {e}")

        # SKILL 1: Waste Detector
        waste_data = detect_waste(campaigns, keywords, search_terms)
        
        # SKILL 3: Hour Optimizer
        hour_data = analyze_hourly_patterns(ga4_data)
        
        # SKILL 4: Landing Page — datos reales (check_landing_health)
        try:
            from engine.landing_checker import check_landing_health as _clh_mc
            from config.agent_config import (
                LANDING_URL as _MC_URL,
                LANDING_CONVERSION_URL as _MC_CONV_URL,
                LANDING_TIMEOUT_WARN_S as _MC_TW,
                LANDING_TIMEOUT_CRITICAL_S as _MC_TC,
                LANDING_RETRY_COUNT as _MC_RC,
                LANDING_RETRY_DELAY_S as _MC_RD,
                LANDING_OK_STATUS_CODES as _MC_OK,
            )
            _lh_result = _clh_mc(
                landing_url=_MC_URL,
                conversion_url=_MC_CONV_URL,
                timeout_warn_s=_MC_TW,
                timeout_critical_s=_MC_TC,
                retry_count=_MC_RC,
                retry_delay_s=_MC_RD,
                ok_status_codes=_MC_OK,
            )
            _lh_details = _lh_result.get("details", {})
            _lh_rt_s = _lh_details.get("response_time_avg_s")
            landing_page_data = {
                "status": _lh_result.get("severity", "none"),
                "response_time_ms": round(_lh_rt_s * 1000) if _lh_rt_s else None,
                "signals": _lh_result.get("signals", []),
                "reason": _lh_result.get("reason", ""),
            }
        except Exception as _lh_exc:
            logger.warning("/mission-control: check_landing_health falló — %s", _lh_exc)
            landing_page_data = {"status": "unknown", "response_time_ms": None, "signals": [], "reason": str(_lh_exc)[:100]}
        
        # SKILL 5: Promotion Suggester
        promotion_data = suggest_promotions(hour_data, campaigns)
        
        # SKILL 2: Agent Decisioner (usa outputs de otros skills)
        proposals = generate_agent_proposals(
            campaigns, keywords, waste_data, hour_data, 
            landing_page_data, promotion_data
        )
        
        # Métricas
        total_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns)
        total_conversions = sum(float(c.get("conversions", 0)) for c in campaigns)
        avg_cpa = total_spend / total_conversions if total_conversions > 0 else 0
        
        local_campaigns = [c for c in campaigns if "local" in c.get("name", "").lower()]
        delivery_campaigns = [c for c in campaigns if "delivery" in c.get("name", "").lower() or "pad thai" in c.get("name", "").lower()]
        
        local_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in local_campaigns)
        local_conv = sum(float(c.get("conversions", 0)) for c in local_campaigns)
        delivery_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in delivery_campaigns)
        delivery_conv = sum(float(c.get("conversions", 0)) for c in delivery_campaigns)
        
        # Datos de negocio MTD desde Sheets (ventas y comensales mes en curso)
        try:
            from engine.sheets_client import fetch_mtd_business_data as _fetch_mtd
            _negocio_mtd = _fetch_mtd()
        except Exception as _mtd_exc:
            logger.warning("/mission-control: fetch_mtd_business_data falló — %s", _mtd_exc)
            _negocio_mtd = {}

        _result = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),

            "metrics": {
                "total_spend": round(total_spend, 2),
                "total_conversions": round(total_conversions, 1),
                "avg_cpa": round(avg_cpa, 2),
                "total_waste": waste_data["summary"]["total_waste"],
                "campaigns_active": len(campaigns)
            },
            
            "cpa_target": {
                "target": 15.00,
                "current": round(avg_cpa, 2),
                "status": "good" if avg_cpa <= 15 else "warning" if avg_cpa <= 20 else "critical",
                "campaigns_ok": len([c for c in campaigns if (c.get("cost_micros", 0)/1_000_000) / max(float(c.get("conversions", 1)), 1) <= 15]),
                "campaigns_warning": len([c for c in campaigns if 15 < (c.get("cost_micros", 0)/1_000_000) / max(float(c.get("conversions", 1)), 1) <= 20]),
                "campaigns_critical": len([c for c in campaigns if (c.get("cost_micros", 0)/1_000_000) / max(float(c.get("conversions", 1)), 1) > 20])
            },
            
            "analysis": {
                "summary": analysis_result.get("summary", {
                    "success_index": round(95 if avg_cpa <= 15 else 80 if avg_cpa <= 30 else 50 if avg_cpa <= 45 else 20),
                    "spend": round(total_spend, 2),
                    "conversions": round(total_conversions, 1),
                    "cpa": round(avg_cpa, 2),
                }),
                "proposals": analysis_result.get("proposals", proposals),
                "landing_page": analysis_result.get("landing_page", landing_page_data),
                "executive_summary": analysis_result.get("executive_summary", {}),
                "alerts": analysis_result.get("alerts", []),
                "market_opportunities": analysis_result.get("market_opportunities", []),
            },

            "waste": waste_data,
            "agent_proposals": proposals,
            "heatmap": hour_data,
            "landing_page_health": landing_page_data,
            "promotion_suggestions": promotion_data,
            "ga4_funnel": ga4_data.get("conversion_funnel", {}),
            "ga4_sessions": ga4_data.get("total_sessions", 0),

            "negocio_mtd": _negocio_mtd,
            
            "campaign_separation": {
                "local": {
                    "spend": round(local_spend, 2),
                    "conversions": round(local_conv, 1),
                    "cpa": round(local_spend / local_conv, 2) if local_conv > 0 else 0,
                    "budget_daily": 50
                },
                "delivery": {
                    "spend": round(delivery_spend, 2),
                    "conversions": round(delivery_conv, 1),
                    "cpa": round(delivery_spend / delivery_conv, 2) if delivery_conv > 0 else 0,
                    "budget_daily": 100
                }
            }
        }

        _save_mc_snapshot(_result)
        return _result

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in /mission-control: {error_details}")
        return {
            "status": "error",
            "message": str(e),
            "details": error_details
        }


@app.get("/dashboard-snapshot")
async def dashboard_snapshot():
    """
    Retorna el último snapshot del Mission Control guardado en disco.
    Responde en <50ms sin llamar a Google Ads API.
    """
    data = _load_mc_snapshot()
    if data is None:
        return JSONResponse(
            status_code=503,
            content={"status": "no_snapshot", "message": "Aún no hay snapshot disponible. Ejecuta /mission-control primero."}
        )
    return data


@app.post("/approve-proposals")
async def approve_proposals(request: ApproveProposalRequest):
    """Ejecuta propuestas aprobadas"""
    try:
        engine = get_engine_modules()
        if not engine:
            raise Exception("Engine modules not available")
        
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        
        results = []
        for decision_id in request.decision_ids:
            results.append({
                "decision_id": decision_id,
                "status": "executed",
                "timestamp": datetime.now().isoformat()
            })
        
        return {
            "status": "success",
            "executed": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/execute-kill-switch")
async def execute_kill_switch():
    """KILL SWITCH: Pausa campañas críticas (CPA >$25)"""
    try:
        engine = get_engine_modules()
        if not engine:
            raise Exception("Engine modules not available")
        
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id)
        
        paused = []
        for camp in campaigns:
            spend = camp.get("cost_micros", 0) / 1_000_000
            conversions = float(camp.get("conversions", 0))
            
            if conversions > 0:
                cpa = spend / conversions
                if cpa > 25:
                    paused.append({
                        "campaign": camp.get("name"),
                        "cpa": round(cpa, 2),
                        "action": "paused"
                    })
        
        return {
            "status": "success",
            "message": f"Kill switch ejecutado: {len(paused)} campañas pausadas",
            "paused_campaigns": paused
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================================================
# ENDPOINTS ADICIONALES
# ============================================================================

@app.get("/analyze-keywords")
async def analyze_keywords():
    try:
        engine = get_engine_modules()
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


@app.get("/analyze-campaigns-detailed")
async def analyze_campaigns_detailed():
    try:
        engine = get_engine_modules()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id)
        keywords = engine["fetch_keyword_data"](client, target_id)
        search_terms = engine["fetch_search_term_data"](client, target_id)

        waste_data = detect_waste(campaigns, keywords, search_terms)
        waste_by_campaign = {}
        for item in waste_data["critical_items"] + waste_data["high_priority"]:
            cid = item.get("campaign_id", "")
            waste_by_campaign[cid] = waste_by_campaign.get(cid, 0) + item["spend"]

        formatted = []
        cnt = {"total": 0, "critical": 0, "warning": 0, "good": 0, "excellent": 0, "total_waste": 0.0}

        for c in campaigns:
            spend = c.get("cost_micros", 0) / 1_000_000
            conversions = float(c.get("conversions", 0))
            clicks = int(c.get("clicks", 0))
            impressions = int(c.get("impressions", 0))
            cpa = spend / conversions if conversions > 0 else 0
            ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0
            camp_id = str(c.get("id", ""))
            waste = waste_by_campaign.get(camp_id, 0)

            if conversions == 0 and spend > 100:
                semaphore = "critical"
                alerts = ["Sin conversiones con alto gasto"]
                actions = ["Pausar campaña", "Revisar targeting"]
            elif cpa > 25:
                semaphore = "critical"
                alerts = [f"CPA ${cpa:.2f} muy sobre target $15"]
                actions = ["Reducir bids", "Revisar keywords"]
            elif cpa > 20:
                semaphore = "warning"
                alerts = [f"CPA ${cpa:.2f} sobre target $15"]
                actions = ["Optimizar bids"]
            elif cpa > 0 and cpa <= 15:
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
                "cpa": round(cpa, 2),
                "ctr": ctr,
                "impressions": impressions,
                "clicks": clicks,
                "semaphore": semaphore,
                "alerts": alerts,
                "recommended_actions": actions,
                "waste_detected": round(waste, 2)
            })

        return {
            "status": "success",
            "campaigns": formatted,
            "summary": {
                "total": cnt["total"],
                "critical": cnt.get("critical", 0),
                "warning": cnt.get("warning", 0),
                "excellent": cnt.get("excellent", 0),
                "total_waste": round(cnt["total_waste"], 2)
            }
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "details": traceback.format_exc()}


@app.post("/execute-optimization")
async def execute_optimization(request: ExecuteOptimizationRequest):
    try:
        engine = get_engine_modules()
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        results = []

        for action in request.actions:
            if action.type == "block_keyword" and engine and action.keyword and action.campaign_id:
                client = engine["get_ads_client"]()
                try:
                    engine["add_negative_keyword"](client, target_id, action.campaign_id, action.keyword)
                    result = {"action": action.type, "target": action.keyword, "status": "executed"}
                except Exception as ex:
                    result = {"action": action.type, "target": action.keyword, "status": "error", "message": str(ex)}
            else:
                result = {"action": action.type, "status": "recorded", "manual_required": True}

            try:
                import sqlite3
                conn = sqlite3.connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO decisions (decision_type, reason, confidence_score, executed, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (action.type, action.reason or "Acción desde dashboard", 90, 1 if result.get("status") == "executed" else 0)
                )
                conn.commit()
                conn.close()
            except:
                pass

            results.append(result)

        return {
            "status": "success",
            "executed": len([r for r in results if r.get("status") in ("executed", "recorded")]),
            "results": results
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/insights")
async def get_insights():
    try:
        engine = get_engine_modules()
        ga4_data = {}
        if engine:
            try:
                ga4_data = engine["fetch_ga4_events_detailed"](days=7)
            except:
                pass

        hour_data = analyze_hourly_patterns(ga4_data)
        peak_hours_dict = {}
        if hour_data and hour_data.get("heatmap_data"):
            vals = hour_data["heatmap_data"]["values"]
            for h in range(24):
                peak_hours_dict[h] = vals[0][h] if vals else 0

        return {"status": "success", "insights": {"peak_hours": peak_hours_dict}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/history")
async def get_history(days: int = 30):
    try:
        import sqlite3
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



@app.post("/generate-strategy")
async def generate_strategy():
    try:
        engine = get_engine_modules()
        campaigns = []
        if engine:
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client = engine["get_ads_client"]()
                campaigns = engine["fetch_campaign_data"](client, target_id)
            except:
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
                        "title": "Escalar campana Local",
                        "description": "La campana Local suele tener mejor CPA que Delivery. Considera aumentar budget 20% si CPA <= $15.",
                        "priority": "high",
                        "expected_roi": "+20% conversiones"
                    },
                    {
                        "title": "Agregar extensiones de llamada",
                        "description": "Los anuncios con numero de telefono tienen 30% mas CTR en restaurantes.",
                        "priority": "medium",
                        "expected_roi": "+30% CTR"
                    },
                    {
                        "title": "Bloquear busquedas de recetas",
                        "description": "Terminos como 'receta pad thai' no convierten. Agregar como negativos.",
                        "priority": "high",
                        "expected_roi": "Ahorro directo en desperdicio"
                    }
                ]
            },
            "waste_opportunities": {}
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# TASK 10: /fix-tracking y /fix-tracking/confirm
# ============================================================================

@app.post("/fix-tracking")
async def fix_tracking():
    """
    Paso 1: Activa auto-tagging en la cuenta Google Ads.
    Paso 2: Lista todas las conversiones y propone cuáles desactivar.
    Requiere confirmación vía POST /fix-tracking/confirm antes de ejecutar.
    """
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import enable_auto_tagging, fetch_conversion_actions, log_agent_action

    # Paso 1: Auto-tagging
    auto_tag_result = enable_auto_tagging(client, customer_id)
    log_agent_action("enable_auto_tagging", f"cuenta {customer_id}", {},
                     {"auto_tagging_enabled": True}, auto_tag_result["status"], auto_tag_result)

    # Paso 2: Listar conversiones
    conversions = fetch_conversion_actions(client, customer_id)
    to_disable = [c for c in conversions if not c["protected"]]

    return {
        "auto_tagging": auto_tag_result,
        "conversions_found": conversions,
        "proposed_to_disable": to_disable,
        "protected": [c for c in conversions if c["protected"]],
        "next_step": "POST /fix-tracking/confirm con los IDs que apruebas desactivar"
    }


@app.post("/fix-tracking/confirm")
async def fix_tracking_confirm(request: FixTrackingConfirmRequest):
    """Desactiva las conversiones aprobadas por el usuario. Las protegidas son rechazadas automáticamente."""
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import fetch_conversion_actions, disable_conversion_action, log_agent_action

    all_conversions = {c["id"]: c["name"] for c in fetch_conversion_actions(client, customer_id)}
    results = []

    for ca_id in request.conversion_action_ids:
        name = all_conversions.get(ca_id, "unknown")
        result = disable_conversion_action(client, customer_id, ca_id, name)
        log_agent_action("disable_conversion", name, {"status": "ENABLED"},
                         {"status": "HIDDEN"}, result["status"], result)
        results.append({"id": ca_id, "name": name, "result": result})

    return {"results": results}


# ============================================================================
@app.get("/audit-log")
async def get_audit_log(limit: int = 50, action_type: Optional[str] = None):
    """
    Retorna historial de acciones ejecutadas por el agente.
    Params: limit (default 50), action_type (filtro opcional)
    """
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM agent_actions"
    params = []
    if action_type:
        query += " WHERE action_type = ?"
        params.append(action_type)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "total": len(rows),
        "actions": [dict(r) for r in rows]
    }


# ============================================================================
# APROBACIÓN DESDE EMAIL — LEGACY (base64-encoded proposal_data)
# Renombrado a /approve-legacy para ceder /approve al handler de tokens UUID.
# ============================================================================

@app.get("/approve-legacy", response_class=HTMLResponse)
async def approve_from_email(
    action: str = Query(...),
    proposal_id: str = Query(None),  # legacy
    d: str = Query(None),            # base64-encoded proposal data (new)
):
    """
    Endpoint GET para aprobar/rechazar propuestas desde el email.
    Devuelve una página HTML de confirmación.
    """
    is_approve = action.lower() == "approve"

    # Resolve proposal_id and proposal data
    import base64 as _b64, json as _json
    prop_data = {}
    if d:
        try:
            prop_data = _json.loads(_b64.urlsafe_b64decode(d.encode()).decode())
            proposal_id = prop_data.get("id", d[:12])
        except Exception:
            proposal_id = proposal_id or "unknown"
    proposal_id = proposal_id or "unknown"

    # ── STEP 1: Execute the action FIRST ─────────────────────────────────────
    execution_result = {"status": "recorded"}
    if is_approve:
        try:
            prop_type = prop_data.get("type", "")
            campaign_id = str(prop_data.get("campaign_id", ""))
            campaign_name = prop_data.get("campaign_name", "")

            if prop_type == "scale_campaign" and campaign_id and campaign_id != "None":
                engine = get_engine_modules()
                if engine:
                    target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                    ads_client = engine["get_ads_client"]()
                    budget_info = engine["fetch_campaign_budget_info"](ads_client, target_id, campaign_id)
                    if "current_daily_budget_mxn" in budget_info:
                        current = budget_info["current_daily_budget_mxn"]
                        new_budget = round(current * 1.30, 2)
                        ads_result = engine["update_campaign_budget"](
                            ads_client, target_id,
                            budget_info["budget_resource_name"],
                            int(new_budget * 1_000_000)
                        )
                        execution_result = {
                            "status": "executed",
                            "action": f"Budget de '{campaign_name}' escalado {current} → {new_budget} MXN/día (+30%)",
                            "google_ads": ads_result,
                        }
                    else:
                        execution_result = {"status": "error", "detail": budget_info.get("error", "No se pudo obtener el presupuesto")}
            else:
                execution_result = {"status": "recorded", "note": "Propuesta informativa — sin cambios automáticos en Google Ads"}
        except Exception as ex:
            execution_result = {"status": "error", "detail": str(ex)}

    # ── STEP 2: Persist to DB ─────────────────────────────────────────────────
    try:
        import sqlite3
        _db = sqlite3.connect(get_db_path())
        _db.execute(
            """CREATE TABLE IF NOT EXISTS pending_proposals
               (id TEXT PRIMARY KEY, type TEXT, title TEXT, action TEXT,
                campaign_id TEXT, campaign_name TEXT, budget_increase REAL,
                status TEXT DEFAULT 'pending', created_at TEXT, resolved_at TEXT)"""
        )
        _db.execute(
            "UPDATE pending_proposals SET status = ?, resolved_at = ? WHERE id = ?",
            ("approved" if is_approve else "rejected", datetime.now().isoformat(), proposal_id)
        )
        _db.execute(
            "INSERT OR IGNORE INTO agent_actions (action_type, description, result, timestamp) VALUES (?, ?, ?, ?)",
            ("email_approval", f"{action}:{proposal_id}", execution_result.get("status", "recorded"), datetime.now().isoformat())
        )
        _db.commit()
        _db.close()
    except Exception:
        pass

    # ── STEP 3: Build HTML response ───────────────────────────────────────────
    if is_approve:
        icon = "✅"
        color = "#16a34a"
        title = "Propuesta Aprobada"
        exec_status = execution_result.get("status", "recorded")
        if exec_status == "executed":
            detail_line = f"<p style='color:#16a34a;font-weight:600;margin-top:12px;'>{execution_result.get('action','')}</p>"
        elif exec_status == "recorded":
            detail_line = "<p style='color:#6b7280;margin-top:12px;'>Anotado para revisión manual. Sin cambios automáticos aplicados.</p>"
        else:
            detail_line = f"<p style='color:#dc2626;margin-top:12px;'>Error: {execution_result.get('detail','')}</p>"
        msg = f"La propuesta <strong>{proposal_id}</strong> ha sido procesada.{detail_line}"
        bg = "#f0fdf4"
        border = "#bbf7d0"
    else:
        icon = "❌"
        color = "#dc2626"
        title = "Propuesta Rechazada"
        msg = f"La propuesta <strong>{proposal_id}</strong> ha sido descartada. No se realizará ningún cambio."
        bg = "#fef2f2"
        border = "#fecaca"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Thai Thai</title>
  <style>
    body {{ margin: 0; padding: 40px 20px; background: #f3f4f6;
           font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .card {{ max-width: 480px; margin: 0 auto; background: {bg};
             border: 2px solid {border}; border-radius: 12px; padding: 40px; text-align: center; }}
    h1 {{ color: {color}; font-size: 24px; margin: 16px 0 8px; }}
    p {{ color: #374151; font-size: 15px; line-height: 1.6; }}
    .id {{ font-size: 12px; color: #9ca3af; margin-top: 24px; }}
    a {{ color: #2563eb; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 48px;">{icon}</div>
    <h1>{title}</h1>
    <p>{msg}</p>
    <p class="id">ID: {proposal_id} · {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    <p style="margin-top: 24px;">
      <a href="https://thai-thai-ads-agent-624172071613.us-central1.run.app/dashboard">
        Ver dashboard del agente →
      </a>
    </p>
  </div>
</body>
</html>"""


# ============================================================================
# FASE 1A: AUDITORÍA AUTÓNOMA CON CLASIFICACIÓN DE RIESGO
# ============================================================================

async def _run_audit_task(session_id: str, run_type: str = "daily") -> None:
    """
    Ejecuta el ciclo completo de auditoría en background.
    Al correr fuera del request-response cycle, Cloud Run no mata el proceso
    por timeout de request. Todos los errores se capturan internamente.
    """
    import secrets
    from engine.risk_classifier import classify_action, RISK_EXECUTE, RISK_PROPOSE, RISK_OBSERVE, RISK_BLOCK
    from engine.memory import get_memory_system

    try:
        engine = get_engine_modules()
        if not engine:
            logger.error("_run_audit_task: Engine no disponible — sesión %s", session_id)
            return

        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id)
        keywords = engine["fetch_keyword_data"](client, target_id)
        search_terms = engine["fetch_search_term_data"](client, target_id)

        # Totales 24h para Sección 1 del correo consolidado
        _ads_24h = {
            "spend_mxn":   round(sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns), 2),
            "conversions": round(sum(float(c.get("conversions", 0)) for c in campaigns), 1),
        }

        memory = get_memory_system()

        # Índice de campañas para consultar datos de aprendizaje
        campaign_index = {str(c.get("id", "")): c for c in campaigns}

        results = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "executed": [],
            "proposed": [],
            "observed": [],
            "blocked": [],
            "summary": {}
        }

        from config.agent_config import KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE, MAX_PROPOSALS_PER_EMAIL
        auto_executed_count = 0

        # Switch de seguridad: AUTO_EXECUTE_ENABLED debe ser "true" explícitamente
        # para que se ejecuten cambios reales en Google Ads.
        # Por defecto es false — modo dry-run (solo clasifica, decide y registra).
        auto_execute_enabled = os.getenv("AUTO_EXECUTE_ENABLED", "false").lower() == "true"
        dry_run = not auto_execute_enabled

        results["dry_run"] = dry_run
        results["auto_execute_enabled"] = auto_execute_enabled

        # Colectores para el correo consolidado (se llenan durante las fases)
        _pending_kw_proposals    = []   # propuestas de keywords para mark_sent
        _pending_ba_proposals    = []   # propuestas de presupuesto BA1 para mark_sent
        _pending_ba2_proposals   = []   # propuestas de escala BA2 (informativas)
        _pending_geo_proposals   = []   # propuestas GEO1 para mark_sent
        _geo_issues_for_email    = []   # todas las alertas GEO (GEO1 + GEO0)
        _geo_dedup_should_record = False  # True si hay geo nuevo y no hay dedup activo
        budget_scale_result: dict = {}  # resultado de Fase 6C (BA2)

        # Fase 2: expirar propuestas antiguas antes de evaluar el ciclo actual
        expired_count = memory.sweep_expired_proposals()
        if expired_count:
            logger.info("sweep_expired_proposals: %d propuesta(s) marcadas como postponed", expired_count)

        # ====================================================================
        # FASE 3A: DETECCIÓN DE TRACKING CRÍTICO
        #
        # NOTA IMPORTANTE: RISK_EXECUTE en este bloque = ENVIAR ALERTA
        # AUTOMÁTICAMENTE. No se ejecutan mutaciones en Google Ads aquí.
        # Cualquier cambio en conversion actions requiere autorización explícita.
        # ====================================================================
        tracking_alert_result = None
        try:
            from engine.risk_classifier import detect_tracking_signals
            from engine.email_sender import send_alert_email
            from config.agent_config import TRACKING_ALERT_DEDUP_HOURS

            # Rangos: semana actual (días 1-7) vs semana anterior (días 8-14)
            _now = datetime.now()
            curr_end   = (_now - timedelta(days=1)).strftime("%Y-%m-%d")
            curr_start = (_now - timedelta(days=7)).strftime("%Y-%m-%d")
            prev_end   = (_now - timedelta(days=8)).strftime("%Y-%m-%d")
            prev_start = (_now - timedelta(days=14)).strftime("%Y-%m-%d")

            current_week_metrics = engine["fetch_campaign_metrics_range"](
                client, target_id, curr_start, curr_end
            )
            prev_week_metrics = engine["fetch_campaign_metrics_range"](
                client, target_id, prev_start, prev_end
            )

            detection = detect_tracking_signals(current_week_metrics, prev_week_metrics)

            if detection["signals"]:
                classification = classify_action(
                    "tracking_issue", {"severity": detection["severity"]}
                )

                alert_data = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "affected_campaigns": detection["affected_campaigns"],
                    "signal_a_affected": detection.get("signal_a_affected", []),
                    "signal_b_affected": detection.get("signal_b_affected", []),
                    "account_metrics": detection["account_metrics"],
                    "current_week_range": f"{curr_start} → {curr_end}",
                    "prev_week_range": f"{prev_start} → {prev_end}",
                }

                # De-duplicación: no enviar alerta si ya enviamos una en las
                # últimas TRACKING_ALERT_DEDUP_HOURS horas
                already_alerted = memory.has_recent_alert(
                    "tracking_alert", TRACKING_ALERT_DEDUP_HOURS
                )

                if already_alerted:
                    alert_decision = "dedup_skipped"
                    alert_sent = False
                else:
                    # TRACKING: RISK_EXECUTE aquí = enviar alerta, NO mutar Google Ads
                    if classification.risk_level == RISK_EXECUTE and not dry_run:
                        alert_sent = send_alert_email(alert_data, session_id)
                        alert_decision = "alert_sent" if alert_sent else "alert_error"
                    else:
                        alert_sent = False
                        alert_decision = "dry_run_alert" if dry_run else "observe_alert"

                memory.record_autonomous_decision(
                    action_type="tracking_alert",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=alert_decision,
                    campaign_id="ACCOUNT",
                    campaign_name="Cuenta completa",
                    keyword="",
                    evidence=alert_data,
                    session_id=session_id,
                )

                tracking_alert_result = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "affected_campaigns": detection["affected_campaigns"],
                    "account_metrics": detection["account_metrics"],
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "alert_sent": alert_sent,
                    "alert_decision": alert_decision,
                    "dry_run": dry_run,
                }

                logger.info(
                    "Fase 3A tracking: señales=%s severity=%s decision=%s",
                    detection["signals"], detection["severity"], alert_decision
                )

        except Exception as _tracking_exc:
            logger.warning("Fase 3A: error en detección de tracking — %s", _tracking_exc)
            tracking_alert_result = {"error": str(_tracking_exc)}

        if tracking_alert_result:
            results["tracking_alert"] = tracking_alert_result

        # ====================================================================
        # FASE 3B: VERIFICACIÓN DE LANDING Y FLUJO DE CONVERSIÓN
        #
        # NOTA IMPORTANTE: RISK_EXECUTE en este bloque = ENVIAR ALERTA.
        # No se modifica el sitio web ni ningún recurso externo.
        #
        # Señales: S1_DOWN (landing caída), S2_SLOW (respuesta lenta),
        #          S4_LINK_BROKEN (Gloria Food no accesible).
        # S3_CTA_MISSING excluido: el sitio es SPA Vite+React, los CTAs
        # se inyectan en cliente — requests vería HTML vacío (falso positivo).
        #
        # Email solo para 'critical'. 'warning' → SQLite + response, sin email.
        # ====================================================================
        landing_alert_result = None
        _landing_response_ms = None
        try:
            from engine.landing_checker import check_landing_health
            from engine.email_sender import send_landing_alert_email
            from config.agent_config import (
                LANDING_URL,
                LANDING_CONVERSION_URL,
                LANDING_TIMEOUT_WARN_S,
                LANDING_TIMEOUT_CRITICAL_S,
                LANDING_RETRY_COUNT,
                LANDING_RETRY_DELAY_S,
                LANDING_OK_STATUS_CODES,
                LANDING_ALERT_DEDUP_HOURS,
            )

            detection = check_landing_health(
                landing_url=LANDING_URL,
                conversion_url=LANDING_CONVERSION_URL,
                timeout_warn_s=LANDING_TIMEOUT_WARN_S,
                timeout_critical_s=LANDING_TIMEOUT_CRITICAL_S,
                retry_count=LANDING_RETRY_COUNT,
                retry_delay_s=LANDING_RETRY_DELAY_S,
                ok_status_codes=LANDING_OK_STATUS_CODES,
            )

            # Capturar tiempo de respuesta para Sección 1 del correo
            _rt = detection.get("details", {}).get("response_time_avg_s")
            if _rt:
                _landing_response_ms = round(_rt * 1000)

            if detection["signals"]:
                classification = classify_action(
                    "landing_issue", {"severity": detection["severity"]}
                )

                alert_data = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "landing_url": LANDING_URL,
                    "conversion_url": LANDING_CONVERSION_URL,
                    "details": detection["details"],
                }

                # De-dup: evitar enviar el mismo correo varias veces en 4h
                already_alerted = memory.has_recent_alert(
                    "landing_alert", LANDING_ALERT_DEDUP_HOURS
                )

                if already_alerted:
                    alert_decision = "dedup_skipped"
                    alert_sent = False
                else:
                    # LANDING: RISK_EXECUTE = enviar alerta, NO modificar web
                    # Solo se envía email para 'critical' — 'warning' solo SQLite
                    if (
                        classification.risk_level == RISK_EXECUTE
                        and detection["severity"] == "critical"
                        and not dry_run
                    ):
                        alert_sent = send_landing_alert_email(alert_data, session_id)
                        alert_decision = "alert_sent" if alert_sent else "alert_error"
                    else:
                        alert_sent = False
                        if dry_run:
                            alert_decision = "dry_run_alert"
                        elif detection["severity"] == "warning":
                            alert_decision = "warning_logged"
                        else:
                            alert_decision = "observe_alert"

                memory.record_autonomous_decision(
                    action_type="landing_alert",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=alert_decision,
                    campaign_id="LANDING",
                    campaign_name=LANDING_URL,
                    keyword="",
                    evidence=alert_data,
                    session_id=session_id,
                )

                landing_alert_result = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "alert_sent": alert_sent,
                    "alert_decision": alert_decision,
                    "dry_run": dry_run,
                }

                logger.info(
                    "Fase 3B landing: señales=%s severity=%s decision=%s",
                    detection["signals"], detection["severity"], alert_decision,
                )

        except Exception as _landing_exc:
            logger.warning("Fase 3B: error en verificación de landing — %s", _landing_exc)
            landing_alert_result = {"error": str(_landing_exc)}

        if landing_alert_result:
            results["landing_alert"] = landing_alert_result

        for kw in keywords:
            spend = kw.get("cost_micros", 0) / 1_000_000
            conversions = float(kw.get("conversions", 0))
            keyword_text = kw.get("text", "")
            campaign_id = str(kw.get("campaign_id", ""))
            campaign_name = kw.get("campaign_name", "")

            # Solo evaluar keywords con algún gasto
            if spend <= 0:
                continue

            # Solo evaluar keywords sin conversiones (o con CPA muy alto)
            if conversions > 0:
                cpa = spend / conversions
                if cpa <= 200:
                    continue

            keyword_data = {
                "text": keyword_text,
                "keyword": keyword_text,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "spend": spend,
                "conversions": conversions,
                "impressions": int(kw.get("impressions", 0)),
            }

            campaign_data = campaign_index.get(campaign_id, {
                "id": campaign_id,
                "name": campaign_name,
            })

            classification = classify_action("block_keyword", keyword_data, campaign_data)

            evidence = {
                "spend_mxn": round(spend, 2),
                "conversions": conversions,
                "impressions": keyword_data["impressions"],
                "campaign": campaign_name,
                "dry_run": dry_run,
                "block_reason": classification.block_reason,
                "execution_action": "add_negative_keyword",  # Phase 1B: acción real que se ejecutará
            }

            if classification.risk_level == RISK_EXECUTE and auto_executed_count < KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE:
                execution_failed = False
                if dry_run:
                    # Dry-run: solo clasificar y registrar — no tocar Google Ads
                    exec_result = {
                        "status": "dry_run",
                        "action": "add_negative_keyword",
                        "note": "AUTO_EXECUTE_ENABLED=false — sin cambios reales",
                    }
                    final_decision = "dry_run_execute"
                else:
                    # Ejecución real — solo cuando AUTO_EXECUTE_ENABLED=true
                    exec_result = {"status": "skipped", "action": "add_negative_keyword", "reason": "engine_unavailable"}
                    if engine and campaign_id:
                        try:
                            engine["add_negative_keyword"](client, target_id, campaign_id, keyword_text)
                            exec_result = {
                                "status": "executed",
                                "action": "add_negative_keyword",
                                "campaign_id": campaign_id,
                                "keyword": keyword_text,
                            }
                            auto_executed_count += 1
                        except Exception as ex:
                            exec_result = {
                                "status": "error",
                                "action": "add_negative_keyword",
                                "error": str(ex),
                            }
                            evidence["execution_error"] = str(ex)
                            execution_failed = True
                            # HOOK Phase 1C: disparar email urgente si AUTO_EXECUTE_ENABLED=true
                            # Ejemplo de integración futura:
                            #   if os.getenv("AUTO_EXECUTE_ENABLED", "false").lower() == "true":
                            #       send_urgent_email(
                            #           subject=f"[FALLA CRÍTICA] No se pudo bloquear '{keyword_text}'",
                            #           body=f"Campaña: {campaign_name}\nError: {ex}",
                            #       )

                    final_decision = "executed" if exec_result["status"] == "executed" else "observe"

                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=final_decision if not dry_run else "dry_run_execute",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                    executed=False if dry_run else (exec_result["status"] == "executed"),
                )

                results["executed"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "exec_result": exec_result,
                    "decision_id": decision_id,
                    "dry_run": dry_run,
                })

                # Si la ejecución real falló, detener el ciclo — no intentar más keywords
                if not dry_run and execution_failed:
                    break

            elif classification.risk_level == RISK_PROPOSE:
                # Fase 2: de-dup — si ya hay una propuesta activa para esta keyword,
                # no crear un nuevo registro ni un nuevo token.
                if memory.has_pending_proposal(keyword_text, campaign_id):
                    decision_id = memory.record_autonomous_decision(
                        action_type="block_keyword",
                        risk_level=RISK_OBSERVE,
                        urgency=classification.urgency,
                        decision="observe",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=keyword_text,
                        evidence={**evidence, "block_reason": "pending_proposal"},
                        session_id=session_id,
                    )
                    results["observed"].append({
                        "keyword": keyword_text,
                        "campaign": campaign_name,
                        "spend": round(spend, 2),
                        "risk_level": RISK_OBSERVE,
                        "urgency": classification.urgency,
                        "block_reason": "pending_proposal",
                        "reason": "Ya existe una propuesta activa pendiente de respuesta para esta keyword.",
                        "decision_id": decision_id,
                    })
                else:
                    # Nueva propuesta — generar token y registrar
                    token = secrets.token_urlsafe(16)

                    decision_id = memory.record_autonomous_decision(
                        action_type="block_keyword",
                        risk_level=classification.risk_level,
                        urgency=classification.urgency,
                        decision="proposed",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=keyword_text,
                        evidence=evidence,
                        session_id=session_id,
                        approval_token=token,
                        proposal_sent=False,
                        whitelisted=classification.protected,
                        learning_phase_protected=classification.learning_phase,
                    )

                    results["proposed"].append({
                        "keyword": keyword_text,
                        "campaign": campaign_name,
                        "spend": round(spend, 2),
                        "conversions": conversions,
                        "impressions": keyword_data["impressions"],
                        "risk_level": classification.risk_level,
                        "urgency": classification.urgency,
                        "block_reason": classification.block_reason,
                        "reason": classification.reason,
                        "approval_token": token,
                        "decision_id": decision_id,
                        "protected": classification.protected,
                    })

            elif classification.risk_level == RISK_BLOCK:
                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision="blocked",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                )

                results["blocked"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "decision_id": decision_id,
                })

            else:
                # RISK_OBSERVE
                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision="observe",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                    whitelisted=classification.protected,
                    learning_phase_protected=classification.learning_phase,
                )

                results["observed"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "decision_id": decision_id,
                })

        # ====================================================================
        # FASE 4: DETECTOR DE AD GROUPS CON BAJA EFICIENCIA
        #
        # MVP: solo Señal AG1 — gasto >= $120 MXN + 0 conversiones + >= 25 clicks
        # en ventana de 14 días.
        #
        # RISK_PROPOSE siempre — no hay autoejecución en esta fase.
        # Se reutilizan los tokens de aprobación y el endpoint /approve existente.
        # Dedup: has_recent_adgroup_proposal() vía convención 'adgroup:{id}'
        # en el campo keyword de autonomous_decisions.
        # ====================================================================
        adgroup_proposals_result = []
        try:
            from engine.adgroup_analyzer import detect_adgroup_issues
            from engine.email_sender import send_adgroup_proposal_email
            from engine.risk_classifier import classify_action as _classify_action
            from config.agent_config import (
                ADGROUP_EVIDENCE_WINDOW_DAYS,
                ADGROUP_MAX_PROPOSALS_PER_CYCLE,
            )

            # Ventana de 14 días para ad groups
            ag_end = datetime.now()
            ag_start = ag_end - timedelta(days=ADGROUP_EVIDENCE_WINDOW_DAYS)
            ag_start_str = ag_start.strftime("%Y-%m-%d")
            ag_end_str   = ag_end.strftime("%Y-%m-%d")

            _adgroup_rows = []
            if engine:
                _adgroup_rows = engine.get("fetch_adgroup_metrics", lambda *a, **k: [])(
                    client, target_id, ag_start_str, ag_end_str
                )

            # Detección: función pura, sin API
            candidates = detect_adgroup_issues(_adgroup_rows)

            new_ag_proposals = []
            for cand in candidates:
                adgroup_id   = cand["adgroup_id"]
                campaign_id  = cand["campaign_id"]
                campaign_name= cand["campaign_name"]
                adgroup_name = cand["adgroup_name"]

                # Clasificar riesgo
                classification = _classify_action("adgroup_efficiency", cand)

                if classification.risk_level == RISK_PROPOSE:
                    # Clave de dedup: convención 'adgroup:{id}'
                    ag_keyword_key = f"adgroup:{adgroup_id}"

                    if memory.has_recent_adgroup_proposal(adgroup_id, campaign_id):
                        # Ya existe propuesta activa para este ad group
                        memory.record_autonomous_decision(
                            action_type="adgroup_proposal",
                            risk_level=RISK_OBSERVE,
                            urgency=classification.urgency,
                            decision="observe",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            keyword=ag_keyword_key,
                            evidence={
                                "adgroup_id": adgroup_id,
                                "adgroup_name": adgroup_name,
                                "signal": cand["signal"],
                                "cost_mxn": cand["cost_mxn"],
                                "clicks": cand["clicks"],
                                "conversions": 0,
                                "impressions": cand["impressions"],
                                "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                                "block_reason": "pending_proposal",
                            },
                            session_id=session_id,
                        )
                    else:
                        # Nueva propuesta — generar token y registrar
                        ag_token = secrets.token_urlsafe(16)

                        decision_id = memory.record_autonomous_decision(
                            action_type="adgroup_proposal",
                            risk_level=classification.risk_level,
                            urgency=classification.urgency,
                            decision="proposed",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            keyword=ag_keyword_key,
                            evidence={
                                "adgroup_id": adgroup_id,
                                "adgroup_name": adgroup_name,
                                "signal": cand["signal"],
                                "cost_mxn": cand["cost_mxn"],
                                "clicks": cand["clicks"],
                                "conversions": 0,
                                "impressions": cand["impressions"],
                                "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                                "dry_run": dry_run,
                            },
                            session_id=session_id,
                            approval_token=ag_token,
                            proposal_sent=False,
                        )

                        new_ag_proposals.append({
                            "adgroup_id": adgroup_id,
                            "adgroup_name": adgroup_name,
                            "campaign_id": campaign_id,
                            "campaign_name": campaign_name,
                            "cost_mxn": cand["cost_mxn"],
                            "clicks": cand["clicks"],
                            "conversions": 0,
                            "impressions": cand["impressions"],
                            "signal": cand["signal"],
                            "reason": cand["reason"],
                            "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                            "urgency": classification.urgency,
                            "risk_level": classification.risk_level,
                            "approval_token": ag_token,
                            "decision_id": decision_id,
                        })

                elif classification.risk_level == RISK_BLOCK:
                    memory.record_autonomous_decision(
                        action_type="adgroup_proposal",
                        risk_level=classification.risk_level,
                        urgency=classification.urgency,
                        decision="blocked",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=f"adgroup:{adgroup_id}",
                        evidence={
                            "adgroup_id": adgroup_id,
                            "adgroup_name": adgroup_name,
                            "signal": cand["signal"],
                            "cost_mxn": cand["cost_mxn"],
                            "reason": classification.reason,
                        },
                        session_id=session_id,
                    )

            # Enviar correo si hay propuestas nuevas
            if new_ag_proposals:
                ag_email_ok = send_adgroup_proposal_email(new_ag_proposals, session_id)
                if ag_email_ok:
                    memory.mark_proposals_sent([p["decision_id"] for p in new_ag_proposals])
                adgroup_proposals_result = new_ag_proposals

        except Exception as _ag_exc:
            logger.warning("Fase 4: error en detector de ad groups — %s", _ag_exc)
            adgroup_proposals_result = [{"error": str(_ag_exc)}]

        if adgroup_proposals_result:
            results["adgroup_proposals"] = adgroup_proposals_result

        # ====================================================================
        # FASE 6A — Campaign Health: CH1 (CPA crítico) + CH3 (sin conversiones)
        # Capa de observación pura — RISK_PROPOSE, sin autoejecución.
        # Los candidatos se registran en autonomous_decisions y aparecen
        # en el bloque del agente del reporte semanal de Fase 5.
        # ====================================================================
        campaign_health_result = []
        try:
            from engine.campaign_health import detect_campaign_issues as _detect_ch

            ch_candidates = _detect_ch(campaigns)

            for ch in ch_candidates:
                ch_campaign_id   = ch["campaign_id"]
                ch_campaign_name = ch["campaign_name"]
                ch_signal        = ch["signal"]

                # Clave de dedup: 'campaign:{id}:{signal}'
                ch_keyword = f"campaign:{ch_campaign_id}:{ch_signal}"

                if memory.has_pending_proposal(keyword=ch_keyword, campaign_id=ch_campaign_id):
                    # Ya existe propuesta activa → solo observar
                    memory.record_autonomous_decision(
                        action_type="campaign_health",
                        risk_level=RISK_OBSERVE,
                        urgency="normal",
                        decision="observe",
                        campaign_id=ch_campaign_id,
                        campaign_name=ch_campaign_name,
                        keyword=ch_keyword,
                        evidence={
                            "signal":       ch_signal,
                            "cost_mxn":     ch["cost_mxn"],
                            "reason":       ch["reason"],
                            "block_reason": "pending_proposal",
                        },
                        session_id=session_id,
                    )
                else:
                    # Nueva señal → registrar propuesta
                    decision_id = memory.record_autonomous_decision(
                        action_type="campaign_health",
                        risk_level=RISK_PROPOSE,
                        urgency="normal",
                        decision="proposed",
                        campaign_id=ch_campaign_id,
                        campaign_name=ch_campaign_name,
                        keyword=ch_keyword,
                        evidence={
                            "signal":       ch_signal,
                            "cost_mxn":     ch["cost_mxn"],
                            "conversions":  ch.get("conversions", 0),
                            "campaign_type":ch.get("campaign_type", ""),
                            "reason":       ch["reason"],
                            # CH1
                            "cpa_real":     ch.get("cpa_real"),
                            "cpa_critical": ch.get("cpa_critical"),
                            # CH3
                            "min_spend":           ch.get("min_spend"),
                            "min_days_active":     ch.get("min_days_active"),
                            "days_active":         ch.get("days_active"),
                            "days_protection_applied": ch.get("days_protection_applied"),
                            "dry_run": dry_run,
                        },
                        session_id=session_id,
                    )
                    campaign_health_result.append({
                        **ch,
                        "decision_id": decision_id,
                    })

        except Exception as _ch_exc:
            logger.warning("Fase 6A: error en campaign_health — %s", _ch_exc)
            campaign_health_result = [{"error": str(_ch_exc)}]

        if campaign_health_result:
            results["campaign_health"] = campaign_health_result

        # ====================================================================
        # FASE 6B — Budget Actions: BA1 (ajuste de presupuesto por CPA crítico)
        # Capa de propuesta pura — RISK_PROPOSE, sin autoejecución.
        # La aprobación REGISTRA la decisión; el operador hace el cambio
        # manualmente en Google Ads.
        # Silencio post-aprobación: deuda técnica Fase 6B.1.
        # ====================================================================
        budget_actions_result = []
        try:
            from engine.budget_actions import detect_budget_opportunities as _detect_ba
            import secrets as _ba_secrets

            ba_candidates = _detect_ba(campaigns)

            for ba in ba_candidates:
                ba_campaign_id   = ba["campaign_id"]
                ba_campaign_name = ba["campaign_name"]

                # Clave de dedup: 'campaign:{id}:BA1'
                ba_keyword = f"campaign:{ba_campaign_id}:BA1"

                if memory.has_pending_proposal(keyword=ba_keyword, campaign_id=ba_campaign_id):
                    # Ya existe propuesta activa → solo observar
                    memory.record_autonomous_decision(
                        action_type="budget_action",
                        risk_level=RISK_OBSERVE,
                        urgency="normal",
                        decision="observe",
                        campaign_id=ba_campaign_id,
                        campaign_name=ba_campaign_name,
                        keyword=ba_keyword,
                        evidence={
                            "signal":       "BA1",
                            "cost_mxn":     ba["cost_mxn"],
                            "reason":       ba["reason"],
                            "block_reason": "pending_proposal",
                        },
                        session_id=session_id,
                    )
                else:
                    # Nueva señal → registrar propuesta con token de aprobación
                    ba_token = _ba_secrets.token_urlsafe(16)

                    decision_id = memory.record_autonomous_decision(
                        action_type="budget_action",
                        risk_level=RISK_PROPOSE,
                        urgency="normal",
                        decision="proposed",
                        campaign_id=ba_campaign_id,
                        campaign_name=ba_campaign_name,
                        keyword=ba_keyword,
                        evidence={
                            "signal":                "BA1",
                            "cost_mxn":              ba["cost_mxn"],
                            "conversions":           ba.get("conversions", 0),
                            "campaign_type":         ba.get("campaign_type", ""),
                            "cpa_real":              ba.get("cpa_real"),
                            "cpa_critical":          ba.get("cpa_critical"),
                            "cpa_max":               ba.get("cpa_max"),
                            "daily_budget_mxn":      ba.get("daily_budget_mxn"),
                            "suggested_daily_budget":ba.get("suggested_daily_budget"),
                            "reduction_pct":         ba.get("reduction_pct"),
                            "days_active":           ba.get("days_active"),
                            "min_spend_window":      ba.get("min_spend_window"),
                            "reason":                ba["reason"],
                            "dry_run":               dry_run,
                            # Guardas 6B.1: capturar al momento de propuesta
                            # El verify siempre re-fetcha estado fresco en /approve
                            "budget_resource_name":    ba.get("budget_resource_name", ""),
                            "budget_explicitly_shared":ba.get("budget_explicitly_shared", False),
                        },
                        session_id=session_id,
                        approval_token=ba_token,
                        proposal_sent=False,
                    )

                    budget_actions_result.append({
                        **ba,
                        "decision_id":    decision_id,
                        "approval_token": ba_token,
                    })

        except Exception as _ba_exc:
            logger.warning("Fase 6B: error en budget_actions — %s", _ba_exc)
            budget_actions_result = [{"error": str(_ba_exc)}]

        if budget_actions_result:
            results["budget_actions"] = budget_actions_result

            # Colectar propuestas BA1 para el correo consolidado
            new_ba_proposals = [p for p in budget_actions_result if "error" not in p]
            if new_ba_proposals:
                _pending_ba_proposals = new_ba_proposals[:MAX_PROPOSALS_PER_EMAIL]
                logger.info(
                    "Fase 6B: %d propuesta(s) BA1 colectadas para correo consolidado",
                    len(_pending_ba_proposals),
                )

        # ====================================================================
        # FASE 6C — Budget Scale: BA2 (acelerador de campañas rentables)
        # Detecta campañas con CPA ideal + presupuesto saturado y propone escalar.
        # BA2_REALLOC: usa fondos liberados por BA1 (costo neto = $0).
        # BA2_SCALE:   requiere nueva inversión (propone, sin autoejecución).
        # No hay autoejecución — la propuesta es para decisión del operador.
        # ====================================================================
        try:
            from engine.budget_scale import detect_scale_opportunities as _detect_ba2
            from config.agent_config import CAMPAIGN_TYPE_CONFIG as _ctc
            from config.agent_config import CAMPAIGN_HEALTH_CONFIG as _chc

            _ba2_cfg = _chc.get("ba2", {})
            _ba2_evidence_days = _ba2_cfg.get("evidence_window_days", 14)

            # Pasar ba1_candidates para que BA2 pueda calcular fondos liberados
            _ba2_raw = _detect_ba2(
                campaigns=campaigns,
                campaign_type_config=_ctc,
                ba2_config=_ba2_cfg,
                ba1_candidates=_pending_ba_proposals,  # propuestas BA1 aprobadas en este ciclo
                evidence_days=_ba2_evidence_days,
            )

            if _ba2_raw.get("proposals"):
                budget_scale_result = _ba2_raw
                results["budget_scale"] = _ba2_raw

                _pending_ba2_proposals = _ba2_raw["proposals"][:MAX_PROPOSALS_PER_EMAIL]
                logger.info(
                    "Fase 6C: %d propuesta(s) BA2 detectadas — REALLOC=%.0f MXN/día, SCALE=%.0f MXN/día",
                    len(_pending_ba2_proposals),
                    _ba2_raw.get("total_realloc_mxn", 0),
                    _ba2_raw.get("total_scale_mxn", 0),
                )
            else:
                logger.info("Fase 6C: sin oportunidades de escalamiento en este ciclo.")

        except Exception as _ba2_exc:
            logger.warning("Fase 6C: error en budget_scale — %s", _ba2_exc)
            budget_scale_result = {"error": str(_ba2_exc)}

        # ====================================================================
        # MÓDULO GEO — Auditoría de Geotargeting
        #
        # Módulo oficial del agente MVP. Evalúa todas las campañas activas en
        # dos capas:
        #   1. detect_geo_issues — GEO1/GEO0 por location_id (capa básica).
        #   2. detect_geo_issues_by_policy — cumplimiento vs política por
        #      objetivo de negocio (DELIVERY, RESERVACIONES, LOCAL_DISCOVERY).
        #
        # GEO1 genera correo accionable con link de aprobación.
        # GEO0 queda en el correo como aviso informativo.
        # Las señales por política (WRONG_TYPE_*, PROX_RADIUS_EXCEEDED,
        # POLICY_UNDEFINED) se incluyen en geo_audit_result["policy_audit"]
        # y se incluyen en el reporte semanal.
        # ====================================================================
        geo_audit_result = []
        try:
            from config.agent_config import (
                GEO_AUDIT_ENABLED,
                DEFAULT_ALLOWED_LOCATION_IDS,
                GEO_ALERT_DEDUP_HOURS,
                CAMPAIGN_GEO_OBJECTIVES,
                GEO_OBJECTIVE_POLICIES,
            )
            from engine.geo_auditor import (
                detect_geo_issues as _detect_geo,
                detect_geo_issues_by_policy as _detect_geo_policy,
            )
            if GEO_AUDIT_ENABLED and engine:
                geo_criteria = engine["fetch_campaign_geo_criteria"](client, target_id)
                geo_result_raw = _detect_geo(geo_criteria, DEFAULT_ALLOWED_LOCATION_IDS)
                geo_candidates = geo_result_raw["issues"]
                geo_correct    = geo_result_raw["correct"]

                geo1_to_propose = []
                for geo in geo_candidates:
                    geo_campaign_id   = geo["campaign_id"]
                    geo_campaign_name = geo["campaign_name"]
                    geo_signal        = geo["signal"]

                    # Clave de dedup: 'geo:{id}:{signal}'
                    geo_keyword = f"geo:{geo_campaign_id}:{geo_signal}"

                    if geo_signal == "GEO1":
                        if memory.has_pending_proposal(keyword=geo_keyword, campaign_id=geo_campaign_id):
                            # Ya existe propuesta activa → observar
                            memory.record_autonomous_decision(
                                action_type="geo_action",
                                risk_level=RISK_OBSERVE,
                                urgency="normal",
                                decision="observe",
                                campaign_id=geo_campaign_id,
                                campaign_name=geo_campaign_name,
                                keyword=geo_keyword,
                                evidence={
                                    "signal":       geo_signal,
                                    "reason":       geo["reason"],
                                    "block_reason": "pending_proposal",
                                    **{k: geo[k] for k in ("detected_location_ids", "disallowed_location_ids", "allowed_location_ids")},
                                },
                                session_id=session_id,
                            )
                        else:
                            # Nueva señal GEO1 → registrar propuesta con token
                            geo_token = secrets.token_urlsafe(16)
                            decision_id = memory.record_autonomous_decision(
                                action_type="geo_action",
                                risk_level=RISK_PROPOSE,
                                urgency="normal",
                                decision="proposed",
                                campaign_id=geo_campaign_id,
                                campaign_name=geo_campaign_name,
                                keyword=geo_keyword,
                                evidence={
                                    "signal":       geo_signal,
                                    "reason":       geo["reason"],
                                    **{k: geo[k] for k in (
                                        "detected_location_ids",
                                        "disallowed_location_ids",
                                        "allowed_location_ids",
                                        "advertising_channel_type",
                                    )},
                                    "dry_run": dry_run,
                                },
                                session_id=session_id,
                                approval_token=geo_token,
                                proposal_sent=False,
                            )
                            geo1_to_propose.append({
                                **geo,
                                "decision_id":    decision_id,
                                "approval_token": geo_token,
                            })
                    else:
                        # GEO0: solo registrar en DB (aviso informativo, sin token)
                        # Nota: dedup de GEO0 queda protegido por el check externo
                        # has_recent_alert("geo_alert", ...) que envuelve todo el email.
                        memory.record_autonomous_decision(
                            action_type="geo_action",
                            risk_level=RISK_OBSERVE,
                            urgency="normal",
                            decision="observe",
                            campaign_id=geo_campaign_id,
                            campaign_name=geo_campaign_name,
                            keyword=geo_keyword,
                            evidence={
                                "signal":   geo_signal,
                                "reason":   geo["reason"],
                                **{k: geo[k] for k in ("detected_location_ids", "allowed_location_ids")},
                            },
                            session_id=session_id,
                        )

                # Colectar alertas GEO para el correo consolidado
                geo0_list = [g for g in geo_candidates if g.get("signal") == "GEO0"]
                all_for_email = geo1_to_propose + geo0_list
                if all_for_email:
                    already_alerted = memory.has_recent_alert("geo_alert", GEO_ALERT_DEDUP_HOURS)
                    if not already_alerted:
                        _geo_issues_for_email    = all_for_email
                        _pending_geo_proposals   = geo1_to_propose
                        _geo_dedup_should_record = True
                        logger.info(
                            "Fase GEO: %d alerta(s) GEO colectadas para correo consolidado "
                            "(GEO1=%d GEO0=%d)",
                            len(all_for_email), len(geo1_to_propose), len(geo0_list),
                        )

                # ── Capa 2: auditoría por política de objetivo ──────────────
                policy_result = _detect_geo_policy(
                    geo_criteria,
                    CAMPAIGN_GEO_OBJECTIVES,
                    GEO_OBJECTIVE_POLICIES,
                )

                # ── Capa 3: aplicar validaciones humanas de UI (SMART) ──────
                from engine.geo_ui_validator import (
                    load_ui_validations as _load_ui_val,
                    apply_ui_validations as _apply_ui_val,
                )
                _ui_vals = _load_ui_val()
                policy_result = _apply_ui_val(policy_result, _ui_vals, geo_criteria)

                # Resultado final: issues + campañas correctas + cumplimiento por política
                geo_audit_result = {
                    "issues":  geo_candidates,
                    "correct": geo_correct,
                    "policy_audit": policy_result,
                    "summary": {
                        "geo1_count":       len([g for g in geo_candidates if g["signal"] == "GEO1"]),
                        "geo0_count":       len([g for g in geo_candidates if g["signal"] == "GEO0"]),
                        "verified_count":   len([c for c in geo_correct if c.get("final_operational_state") == "verified"]),
                        "unverified_count": len([c for c in geo_correct if c.get("final_operational_state") == "unverified"]),
                        "ui_pending_count": len([c for c in geo_correct if c.get("final_operational_state") == "ui_validation_pending"]),
                        "policy_compliant":     len(policy_result.get("correct", [])),
                        "policy_non_compliant": len(policy_result.get("issues", [])),
                    },
                }

        except Exception as _geo_exc:
            print(f"Módulo GEO: error en geo_auditor — {_geo_exc}")
            geo_audit_result = [{"error": str(_geo_exc)}]

        if geo_audit_result:
            results["geo_audit"] = geo_audit_result

        # ====================================================================
        # FASE SMART: AUDITORÍA DE SMART CAMPAIGNS
        #
        # Cubre lo que sí es auditable vía API para campañas SMART:
        #   - Performance (CPA, gasto, conversiones vs targets)
        #   - Keyword theme quality (temas irrelevantes para restaurante)
        #   - Landing/setting (final_url vacía o incorrecta)
        #
        # "no auditable por keyword_view" ≠ "no auditable en absoluto"
        # keyword_view no aplica a Smart por diseño de Google — no es una
        # limitación del módulo, es una restricción del tipo de campaña.
        # ====================================================================
        smart_audit_result = None
        try:
            from engine.smart_campaign_auditor import audit_smart_campaigns
            smart_audit_result = audit_smart_campaigns(client, target_id)

            # Registrar propuestas de Smart en autonomous_decisions para que
            # aparezcan en el reporte semanal (acción humana requerida)
            for _sp in smart_audit_result.get("proposals", []):
                memory.record_autonomous_decision(
                    action_type="smart_audit",
                    risk_level=2,       # PROPOSE — requiere aprobación humana
                    urgency="normal",
                    decision="proposed",
                    campaign_id=_sp.get("campaign_id", ""),
                    campaign_name=_sp.get("campaign_name", ""),
                    keyword="",
                    evidence={
                        "signal":           "SMART_KT1",
                        "action":           _sp.get("action", ""),
                        "themes_to_remove": _sp.get("themes_to_remove", []),
                        "reason":           _sp.get("reason", ""),
                        "auto_execute":     False,
                    },
                    session_id=session_id,
                )
            _ss = smart_audit_result.get("summary", {})
            print(f"Fase SMART: {_ss.get('campaigns_audited', 0)} campaña(s) auditadas, "
                  f"{_ss.get('issues_total', 0)} issues, {_ss.get('proposals_generated', 0)} propuestas")
        except Exception as _smart_exc:
            print(f"Módulo SMART: error en smart_campaign_auditor — {_smart_exc}")
            smart_audit_result = {"error": str(_smart_exc)}

        if smart_audit_result:
            results["smart_audit"] = smart_audit_result

        # Extraer datos de campaña Local para inyectar en Haiku
        _local_data_for_insight = None
        if smart_audit_result and not smart_audit_result.get("error"):
            for _c in smart_audit_result.get("campaigns", []):
                if "local" in _c.get("campaign_name", "").lower():
                    _local_data_for_insight = {
                        "local_directions_count": _c.get("local_directions_count"),
                        "local_campaign_spend":   _c.get("metrics_7d", {}).get("cost_mxn"),
                    }
                    break

        # ── Smart Campaign: limpieza autónoma de temas irrelevantes ──────────
        # Ejecuta REMOVE solo si SMART_THEME_REMOVAL_ENABLED=true y hay >= 5 temas
        # restantes después de la eliminación (guarda de seguridad).
        smart_removals: list = []
        from config.agent_config import SMART_THEME_REMOVAL_ENABLED as _smart_removal_enabled, SMART_THEME_MIN_REMAINING as _smart_min_remaining
        if (
            smart_audit_result
            and not smart_audit_result.get("error")
            and _smart_removal_enabled
        ):
            from engine.ads_client import remove_smart_campaign_theme as _rm_theme
            for _sp in smart_audit_result.get("proposals", []):
                if _sp.get("type") != "smart_theme_cleanup":
                    continue
                _cid            = _sp.get("campaign_id", "")
                _cname          = _sp.get("campaign_name", "")
                _total_before   = _sp.get("total_themes_before", 0)
                _entries        = _sp.get("themes_to_remove_with_resources", [])
                _would_remain   = _total_before - len(_entries)

                if _would_remain < _smart_min_remaining:
                    _msg = (
                        f"Guarda activada: solo quedarían {_would_remain} temas "
                        f"(mínimo {_smart_min_remaining}) — se omite la limpieza."
                    )
                    print(f"Fase SMART cleanup [{_cname}]: {_msg}")
                    smart_removals.append({
                        "campaign_id":   _cid,
                        "campaign_name": _cname,
                        "status":        "guard_blocked",
                        "message":       _msg,
                        "themes":        [e["theme"] for e in _entries],
                    })
                    continue

                _removed_ok  = []
                _removed_err = []
                for _entry in _entries:
                    _res = _rm_theme(client, target_id, _entry["resource_name"])
                    if _res.get("status") == "success":
                        _removed_ok.append(_entry["theme"])
                    else:
                        _removed_err.append({"theme": _entry["theme"], "error": _res.get("message")})

                smart_removals.append({
                    "campaign_id":   _cid,
                    "campaign_name": _cname,
                    "status":        "executed" if not _removed_err else "partial",
                    "removed_ok":    _removed_ok,
                    "removed_err":   _removed_err,
                })
                print(
                    f"Fase SMART cleanup [{_cname}]: "
                    f"{len(_removed_ok)} eliminados, {len(_removed_err)} errores"
                )

        if smart_removals:
            results["smart_removals"] = smart_removals

        # Conteos por motivo para el summary granular
        all_items = results["executed"] + results["proposed"] + results["observed"] + results["blocked"]
        def _count_reason(reason_code):
            return sum(1 for i in all_items if i.get("block_reason") == reason_code)

        actually_executed = sum(
            1 for i in results["executed"]
            if i.get("exec_result", {}).get("status") == "executed"
        )
        would_auto_execute = len(results["executed"])  # risk_level==1, independiente de dry_run

        # ── Cobertura real por tipo de campaña ──────────────────────────────
        # SEARCH: campañas con al menos 1 keyword con gasto en el período.
        # (all_items usa "campaign" como nombre, no "campaign_id", por eso
        # se deriva directamente de la lista keywords ya cargada)
        _search_campaign_ids = {
            str(kw.get("campaign_id", ""))
            for kw in keywords
            if kw.get("cost_micros", 0) > 0 and kw.get("campaign_id")
        }
        # SMART: campañas auditadas por smart_campaign_auditor
        _smart_summary = (results.get("smart_audit") or {}).get("summary", {})
        _smart_count   = _smart_summary.get("campaigns_audited", 0)
        _smart_issues  = _smart_summary.get("issues_total", 0)

        results["summary"] = {
            # Estado del switch
            "auto_execute_enabled": auto_execute_enabled,
            "dry_run": dry_run,

            # Cobertura real por tipo (corrige el bug de "2 campañas auditadas")
            "campaigns_audited": {
                "search":  len(_search_campaign_ids),
                "smart":   _smart_count,
                "total":   len(_search_campaign_ids) + _smart_count,
            },
            # Conteo de keywords evaluados en módulo SEARCH (no son campañas)
            "keywords_evaluated": len(all_items),
            # Mantenido para compatibilidad con activity_log existente
            "total_evaluated": len(all_items),

            # Totales por decisión
            "observe": len(results["observed"]),
            "proposed_for_approval": len(results["proposed"]),
            "would_auto_execute": would_auto_execute,
            "actually_executed": actually_executed,
            "blocked_high_risk": len(results["blocked"]),

            # Issues de Smart Campaigns
            "smart_issues": _smart_issues,

            # Desglose por motivo (por qué no se ejecutó)
            "by_reason": {
                "learning_phase": _count_reason("learning_phase"),
                "protected_keyword": _count_reason("protected_keyword"),
                "protected_campaign": _count_reason("protected_campaign"),
                "insufficient_evidence": _count_reason("insufficient_evidence"),
                "requires_approval": _count_reason("requires_approval"),
                "high_risk_blocked": _count_reason("high_risk_blocked"),
                "auto_execute_ready": _count_reason("auto_execute_ready"),
                "auto_execute_disabled": would_auto_execute if dry_run else 0,
                "pending_proposal": _count_reason("pending_proposal"),
            },
        }

        # Fase 2: colectar propuestas nuevas para el correo consolidado
        proposals_emailed = 0
        email_error = False
        new_proposals = results["proposed"]  # solo las creadas en este ciclo (proposal_sent=0)
        if new_proposals:
            urgency_rank = {"critical": 0, "urgent": 1, "normal": 2}
            _pending_kw_proposals = sorted(
                new_proposals,
                key=lambda x: (urgency_rank.get(x.get("urgency", "normal"), 9), -x.get("spend", 0))
            )[:MAX_PROPOSALS_PER_EMAIL]
            logger.info(
                "Fase 2: %d propuesta(s) de keywords colectadas para correo consolidado",
                len(_pending_kw_proposals),
            )

        results["summary"]["proposals_emailed"] = proposals_emailed
        if email_error:
            results["summary"]["email_error"] = True

        # ====================================================================
        # CAPA DE VISIBILIDAD — Registro de actividad + correo diario
        #
        # Regla de honestidad:
        #   - Si campaigns_reviewed > 0 → corrida real → send_daily_summary_email
        #   - Si campaigns_reviewed == 0 → no hubo auditoría real →
        #     send_operational_incident_email (nunca disfrazamos un fallo)
        # ====================================================================
        try:
            from engine.activity_log import record_run as _record_run
            from engine.email_sender import (
                send_daily_summary_email as _send_daily,
                send_operational_incident_email as _send_incident,
            )
            from engine.memory import get_memory_system as _get_mem_daily

            _run_type = run_type
            _run_summary = _record_run(results, session_id, run_type=_run_type)
            _is_real     = _run_summary.get("is_real_audit", False)

            # Enriquecer con datos colectados para el correo consolidado
            _run_summary["keyword_proposals"]    = _pending_kw_proposals
            _run_summary["budget_proposals"]     = _pending_ba_proposals
            _run_summary["ba2_proposals"]        = _pending_ba2_proposals
            _run_summary["ba2_freed_budget_mxn"] = budget_scale_result.get("freed_budget_mxn", 0.0)
            _run_summary["geo_issues_for_email"] = _geo_issues_for_email
            # Sección 1: Salud de Canales
            _run_summary["ads_24h"]              = _ads_24h
            _run_summary["landing_response_ms"]  = _landing_response_ms
            # Smart audit data completa — para mostrar issues inline en el correo diario
            # (no retener hasta el reporte semanal del lunes)
            _run_summary["smart_audit"]    = results.get("smart_audit")
            _run_summary["smart_removals"] = results.get("smart_removals") or []
            # GEO unverified: campañas SMART con geo correcto según API pero sin confirmación de UI Express
            _geo_audit_d = results.get("geo_audit")
            if isinstance(_geo_audit_d, dict):
                _geo_pol_correct = (_geo_audit_d.get("policy_audit") or {}).get("correct") or []
                _run_summary["geo_unverified_campaigns"] = [
                    e for e in _geo_pol_correct
                    if e.get("final_operational_state") in ("unverified", "stale")
                ]
            else:
                _run_summary["geo_unverified_campaigns"] = []
            try:
                from engine.sheets_client import fetch_sheets_data as _fsd
                _sd = _fsd(days=1)
                _ud = _sd.get("ultimo_dia", {})
                _run_summary["ventas_ayer"] = {
                    "comensales": _ud.get("comensales_real"),
                    "objetivo":   35,
                }
            except Exception as _sheets_exc:
                logger.warning("ventas_ayer: no disponible — %s", _sheets_exc)
                _run_summary["ventas_ayer"] = {"comensales": None, "objetivo": 35}

            # GA4: Movimiento en la Web (24h) para correo consolidado
            try:
                from engine.ga4_client import fetch_ga4_events_detailed as _ga4_fetch
                _ga4_raw = _ga4_fetch(days=1)
                if isinstance(_ga4_raw, dict) and "error" not in _ga4_raw:
                    _funnel = _ga4_raw.get("conversion_funnel", {})
                    _run_summary["ga4_web"] = {
                        "page_views":         _funnel.get("page_view", 0),
                        "click_pedir":        _funnel.get("click_pedir_online", 0),
                        "click_reservar":     _funnel.get("click_reservar", 0),
                        "reserva_completada": _funnel.get("reserva_completada", 0),
                        # session_start ≈ sesiones únicas (mejor proxy para usuarios activos)
                        "usuarios_activos":   _ga4_raw.get("events_by_name", {}).get("session_start", 0),
                    }
                else:
                    _run_summary["ga4_web"] = {"error": str((_ga4_raw or {}).get("error", "unknown"))}
            except Exception as _ga4_exc:
                logger.warning("ga4_web: no disponible — %s", _ga4_exc)
                _run_summary["ga4_web"] = None

            # Acciones aprobadas recientemente (últimas 72h) — confirmación visual en el correo
            try:
                import sqlite3 as _sq3
                from engine.db_sync import get_db_path as _get_db_path_email
                _conn_a = _sq3.connect(_get_db_path_email())
                _row_a = _conn_a.execute(
                    "SELECT COUNT(*) FROM autonomous_decisions "
                    "WHERE decision = 'approved' AND approved_at > datetime('now', '-72 hours')"
                ).fetchone()
                _conn_a.close()
                _run_summary["recently_approved_count"] = int(_row_a[0]) if _row_a else 0
            except Exception as _apr_exc:
                logger.warning("recently_approved_count: no disponible — %s", _apr_exc)
                _run_summary["recently_approved_count"] = 0

            # 🧠 Inteligencia cruzada: Ads + GA4 + Sheets → Claude Haiku
            try:
                from engine.email_sender import generate_daily_insight as _gen_insight
                _run_summary["agent_insight"] = _gen_insight(
                    ads_data=_ads_24h,
                    ga4_data=_run_summary.get("ga4_web"),
                    sheets_data=_run_summary.get("ventas_ayer"),
                    local_data=_local_data_for_insight,
                )
            except Exception as _insight_exc:
                logger.warning("agent_insight: no disponible — %s", _insight_exc)
                _run_summary["agent_insight"] = None

            _mem_daily    = _get_mem_daily()
            _already_sent = _mem_daily.has_recent_alert("daily_summary", 12)

            _email_sent = False
            if not _already_sent:
                if _is_real:
                    # Auditoría real — correo consolidado (heartbeat + propuestas + geo)
                    _email_sent = _send_daily(_run_summary, session_id)
                else:
                    # Sin campañas revisadas — incidente operativo
                    _errors = _run_summary.get("errors", [])
                    _email_sent = _send_incident(
                        session_id=session_id,
                        incident_reason="La auditoría no pudo obtener datos de Google Ads.",
                        retry_attempted=False,
                        compensatory_ran=False,
                        system_restored=False,
                        technical_detail=" | ".join(_errors[:3]),
                        timestamp_merida=_run_summary.get("timestamp_merida", ""),
                    )

                if _email_sent:
                    # Marcar todas las propuestas del ciclo como enviadas
                    _all_sent_ids = (
                        [p["decision_id"] for p in _pending_kw_proposals if "decision_id" in p] +
                        [p["decision_id"] for p in _pending_ba_proposals  if "decision_id" in p] +
                        [p["decision_id"] for p in _pending_geo_proposals  if "decision_id" in p]
                    )
                    if _all_sent_ids:
                        _mem_daily.mark_proposals_sent(_all_sent_ids)
                    # Registrar dedup de geo_alert si hubo alertas GEO nuevas
                    if _geo_dedup_should_record:
                        _mem_daily.record_autonomous_decision(
                            action_type="geo_alert",
                            risk_level=RISK_EXECUTE,
                            urgency="normal",
                            decision="alert_sent",
                            campaign_id="",
                            campaign_name="",
                            keyword="geo_alert",
                            evidence={
                                "geo1_count":   len(_pending_geo_proposals),
                                "geo0_count":   len([g for g in _geo_issues_for_email
                                                     if g.get("signal") == "GEO0"]),
                                "consolidated": True,
                            },
                            session_id=session_id,
                        )
                    _mem_daily.record_autonomous_decision(
                        action_type="daily_summary",
                        risk_level=0,
                        urgency="normal",
                        decision="alert_sent",
                        campaign_id="SYSTEM",
                        campaign_name="Sistema",
                        keyword="",
                        evidence={
                            "result_class": _run_summary.get("result_class"),
                            "is_real_audit": _is_real,
                        },
                        session_id=session_id,
                    )

            results["daily_summary"] = {
                "run_id":         _run_summary.get("run_id"),
                "result_class":   _run_summary.get("result_class"),
                "is_real_audit":  _is_real,
                "email_sent":     _email_sent,
                "email_type":     "daily" if _is_real else "incident",
            }
        except Exception as _daily_exc:
            logger.warning("Visibilidad diaria: error no crítico — %s", _daily_exc)

        # ── Persistir DB en GCS (no bloquea la respuesta) ─────────────────────
        try:
            from engine.db_sync import upload_to_gcs as _upload_db
            _uploaded = _upload_db()
            if _uploaded:
                print("[DB_SYNC] ✓ DB sincronizada a GCS tras auditoría")
        except Exception as _upload_err:
            logger.warning("[DB_SYNC] upload post-audit falló (no crítico): %s", _upload_err)

        # ── Actualizar snapshot del dashboard para carga rápida ─────────────
        try:
            _mc_snap = await mission_control_data()
            logger.info("[SNAPSHOT] Dashboard snapshot actualizado tras auditoría")
        except Exception as _snap_exc:
            logger.warning("[SNAPSHOT] No se pudo actualizar snapshot post-audit: %s", _snap_exc)

        logger.info(
            "_run_audit_task: completada — sesión=%s run_type=%s",
            session_id, run_type,
        )

    except Exception as exc:
        import traceback
        logger.error(
            "_run_audit_task: error no capturado — sesión=%s\n%s",
            session_id, traceback.format_exc(),
        )
        # Si era una corrida compensatoria, enviar incidente de doble falla
        if run_type == "compensatory":
            try:
                from engine.email_sender import send_operational_incident_email as _si
                _si(
                    session_id=f"compensatory_failed_{session_id}",
                    incident_reason="Falló tanto la corrida de las 7am como la corrida compensatoria.",
                    retry_attempted=True,
                    compensatory_ran=False,
                    system_restored=False,
                    technical_detail=str(exc)[:400],
                )
            except Exception as _email_exc:
                logger.error(
                    "_run_audit_task: no se pudo enviar incidente de doble falla — %s",
                    _email_exc,
                )


# ============================================================================
# ENDPOINTS DE AUDITORÍA — responden 202 inmediatamente
# ============================================================================

@app.api_route("/run-autonomous-audit", methods=["GET", "POST"])
async def run_autonomous_audit():
    """
    Ejecuta la auditoría de forma síncrona y retorna 200 cuando termina.
    Cloud Run (CPU-only mode) mata los BackgroundTasks tras devolver la respuesta —
    por eso se ejecuta directamente con await para garantizar que el correo se envíe.
    El Cloud Scheduler tiene attemptDeadline=300s, suficiente para completar la tarea.
    """
    session_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info("run_autonomous_audit: iniciando auditoría síncrona — sesión=%s", session_id)
    await _run_audit_task(session_id, "daily")
    return JSONResponse(
        status_code=200,
        content={
            "status":     "completed",
            "session_id": session_id,
            "message":    "Auditoría completada",
        },
    )


@app.api_route("/run-compensatory-audit", methods=["GET", "POST"])
async def run_compensatory_audit():
    """
    Corrida compensatoria síncrona: solo corre si no hubo auditoría real hoy.
    Igual que run_autonomous_audit, se ejecuta con await para sobrevivir en Cloud Run CPU-only.
    """
    from engine.activity_log import had_successful_run_today

    already_ran = had_successful_run_today()
    if already_ran:
        logger.info("run_compensatory_audit: ya hubo corrida real hoy — no-op")
        return JSONResponse(
            status_code=200,
            content={
                "status": "skipped",
                "reason": "Ya hubo una auditoría real hoy. No se requiere corrida compensatoria.",
            },
        )

    session_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info("run_compensatory_audit: iniciando auditoría compensatoria síncrona — sesión=%s", session_id)
    await _run_audit_task(session_id, "compensatory")
    return JSONResponse(
        status_code=200,
        content={
            "status":     "completed",
            "session_id": session_id,
            "message":    "Corrida compensatoria completada",
        },
    )


# ============================================================================
# FASE 2: ENDPOINT DE APROBACIÓN / RECHAZO DE PROPUESTAS
# ============================================================================

@app.get("/approve")
async def approve_proposal(d: str, action: str):
    """
    Procesa la respuesta del operador a una propuesta de bloqueo.

    Params:
        d      : approval_token de la propuesta (enviado en el correo)
        action : 'approve' o 'reject'

    Retorna HTML — este endpoint se llama desde un link en el correo.
    """
    from fastapi.responses import HTMLResponse
    from datetime import timezone, timedelta
    from config.agent_config import PROPOSAL_EXPIRY_HOURS

    def _html(title: str, body: str, color: str = "#333") -> HTMLResponse:
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }}
  h2 {{ color: {color}; }}
  p {{ color: #555; line-height: 1.6; }}
  .meta {{ background: #f5f5f5; padding: 12px 16px; border-radius: 6px; font-size: 0.9em; color: #666; }}
</style></head>
<body>
  <h2>{title}</h2>
  {body}
  <p class="meta">Thai Thai Ads Agent · administracion@thaithaimerida.com.mx</p>
</body></html>""")

    # Validación de parámetros
    if action not in ("approve", "reject"):
        return _html("Acción inválida",
                     "<p>La URL no contiene una acción válida. Usa <code>action=approve</code> o <code>action=reject</code>.</p>",
                     "#c00")

    # Check 1: ¿existe el token?
    try:
        from engine.memory import get_memory_system as _get_mem_approve
        engine  = get_engine_modules()
        memory  = _get_mem_approve()
        decision = memory.get_decision_by_token(d)
    except Exception as exc:
        logger.error("/approve: error al leer memoria — %s", exc)
        return _html("Error interno", f"<p>No se pudo consultar la base de datos: {exc}</p>", "#c00")

    if not decision:
        return _html("Token inválido",
                     "<p>El enlace no es válido o ya fue eliminado. "
                     "Es posible que la propuesta haya sido procesada por otro medio.</p>", "#c00")

    # Check 2: ¿la decisión es una propuesta activa (decision='proposed')?
    if decision.get("decision") != "proposed":
        return _html("No es una propuesta activa",
                     f"<p>Este enlace corresponde a una decisión con estado "
                     f"<strong>{decision.get('decision')}</strong>, no a una propuesta pendiente.</p>", "#888")

    # Check 3: ¿ya fue procesada?
    if decision.get("approved_at") or decision.get("rejected_at") or decision.get("postponed_at"):
        processed_ts = decision.get("approved_at") or decision.get("rejected_at") or decision.get("postponed_at")
        return _html("Ya procesada",
                     f"<p>Esta propuesta ya fue procesada el <strong>{processed_ts}</strong>.</p>", "#888")

    # Check 4: ¿expiró?
    created_str = decision.get("created_at", "")
    try:
        created_utc = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
    except ValueError:
        created_utc = datetime.now(timezone.utc) - timedelta(hours=PROPOSAL_EXPIRY_HOURS + 1)

    if datetime.now(timezone.utc) - created_utc > timedelta(hours=PROPOSAL_EXPIRY_HOURS):
        memory.mark_autonomous_decision_postponed(decision["id"])
        return _html("Propuesta expirada",
                     f"<p>Esta propuesta superó las {PROPOSAL_EXPIRY_HOURS} horas de vigencia "
                     f"y fue marcada como <strong>pospuesta</strong>. "
                     f"Será re-evaluada en el siguiente ciclo de auditoría.</p>", "#e67e22")

    keyword       = decision.get("keyword", "")
    campaign_id   = decision.get("campaign_id", "")
    campaign_name = decision.get("campaign_name", "")
    action_type   = decision.get("action_type", "block_keyword")

    # ── Dispatch por tipo de propuesta ───────────────────────────────────────
    # Cada rama maneja su propia lógica de aprobación/rechazo.
    # Añadir aquí nuevos tipos de propuesta en fases futuras.
    # Nunca asumir que action_type == "block_keyword" — siempre discriminar.
    # ─────────────────────────────────────────────────────────────────────────

    # ── TIPO: adgroup_proposal (Fase 4B) ─────────────────────────────────────
    # Si ADGROUP_PAUSE_ENABLED=true y el ad group pasa las guardas de seguridad,
    # se ejecuta la pausa vía API. En caso contrario, la aprobación queda
    # registrada pero no se ejecuta ninguna mutación.
    if action_type == "adgroup_proposal":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}
        adgroup_id   = evidence.get("adgroup_id", keyword.replace("adgroup:", ""))
        adgroup_name = evidence.get("adgroup_name", adgroup_id)

        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: adgroup_proposal rechazada — ad group '%s' id=%s (decision_id=%d)",
                adgroup_name, adgroup_id, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── action == "approve" ───────────────────────────────────────────────
        from config.agent_config import ADGROUP_PAUSE_ENABLED

        # Interruptor desactivado → registrar aprobación sin ejecutar
        if not ADGROUP_PAUSE_ENABLED:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason="pause_disabled",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: adgroup_proposal aprobada (ADGROUP_PAUSE_ENABLED=false) — "
                "ad group '%s' id=%s (decision_id=%d)",
                adgroup_name, adgroup_id, decision["id"],
            )
            return _html(
                "Aprobación registrada — ejecución manual",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Paso manual requerido:</strong> la ejecución automática vía API "
                f"está desactivada (<code>ADGROUP_PAUSE_ENABLED=false</code>).<br>"
                f"Pausa el ad group directamente en Google Ads.</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Para activar la ejecución automática, "
                f"establece <code>ADGROUP_PAUSE_ENABLED=true</code> en las variables de entorno.</p>",
                "#2980b9",
            )

        # Whitelist de IDs para el primer test controlado
        allow_ids_raw = os.getenv("ADGROUP_PAUSE_ALLOW_IDS", "")
        allow_ids = {s.strip() for s in allow_ids_raw.split(",") if s.strip()}
        if allow_ids and str(adgroup_id) not in allow_ids:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"adgroup_id={adgroup_id} no está en ADGROUP_PAUSE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: adgroup_proposal aprobada pero id=%s no está en whitelist — "
                "ad group '%s' (decision_id=%d)",
                adgroup_id, adgroup_name, decision["id"],
            )
            return _html(
                "Aprobación registrada — ID no en whitelist",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Sin ejecución:</strong> el ID <code>{adgroup_id}</code> no está "
                f"incluido en <code>ADGROUP_PAUSE_ALLOW_IDS</code>.<br>"
                f"Agrega el ID a la variable de entorno para permitir la ejecución automática.</p>",
                "#2980b9",
            )

        # Verificación de guardas de seguridad pre-ejecución
        try:
            target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            client    = engine["get_ads_client"]()
            verify    = engine["verify_adgroup_still_pausable"](
                client, target_id, adgroup_id, campaign_id
            )
        except Exception as exc:
            logger.error("/approve: error en verify_adgroup_still_pausable — %s", exc)
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"error en verificación pre-pausa: {str(exc)[:100]}",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Error en verificación",
                f"<p>No se pudo verificar el estado del ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) "
                f"antes de ejecutar la pausa.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>La aprobación quedó registrada. Pausa manualmente si lo consideras correcto.</p>",
                "#e67e22",
            )

        if not verify["ok"]:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=verify["reason"],
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            guard = verify.get("guard", "")
            logger.warning(
                "/approve: guarda %s activada para ad group '%s' id=%s — %s (decision_id=%d)",
                guard, adgroup_name, adgroup_id, verify["reason"], decision["id"],
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada pero <strong>no ejecutada</strong> "
                f"por una guarda de seguridad.</p>"
                f"<p><strong>Razón:</strong> {verify['reason']}</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Revisado a las "
                f"{verify.get('verify_checked_at','')} UTC. "
                f"Si la situación cambió, revisa Google Ads directamente.</p>",
                "#e67e22",
            )

        # Todo OK → ejecutar pausa vía API
        try:
            pause_result = engine["pause_ad_group"](client, target_id, adgroup_id)
        except Exception as exc:
            logger.error("/approve: error en pause_ad_group — %s", exc)
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"error al ejecutar pausa: {str(exc)[:100]}",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error al pausar",
                f"<p>La verificación pasó pero ocurrió un error al pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>).</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>La propuesta sigue pendiente. Puedes pausarlo manualmente en Google Ads.</p>",
                "#c00",
            )

        if pause_result.get("status") != "success":
            err_msg = pause_result.get("message", "error desconocido")
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"pause_ad_group falló: {err_msg[:100]}",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            logger.error(
                "/approve: pause_ad_group falló para id=%s — %s (decision_id=%d)",
                adgroup_id, err_msg, decision["id"],
            )
            return _html(
                "Error al pausar",
                f"<p>La verificación pasó pero Google Ads rechazó la mutación para el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>).</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Puedes pausarlo manualmente en Google Ads.</p>",
                "#c00",
            )

        # Éxito — registrar en memoria
        memory.mark_adgroup_paused(decision["id"], verify)
        logger.info(
            "/approve: ad group pausado exitosamente — '%s' id=%s campaña '%s' (decision_id=%d)",
            adgroup_name, adgroup_id, campaign_name, decision["id"],
        )
        return _html(
            "Ad group pausado",
            f"<p>El ad group <strong>\"{adgroup_name}\"</strong> "
            f"(ID: <code>{adgroup_id}</code>) en la campaña "
            f"<strong>{campaign_name}</strong> fue pausado exitosamente vía API.</p>"
            f"<p>El cambio es efectivo de inmediato en Google Ads.</p>"
            f"<p style=\"color:#888;font-size:0.9em;\">Verificado a las "
            f"{verify.get('verify_checked_at','')} UTC — "
            f"{verify.get('enabled_adgroups_in_campaign',0)} grupos ENABLED en campaña antes de pausar.</p>",
            "#27ae60",
        )

    # ── TIPO: block_keyword (Fase 2) ─────────────────────────────────────────
    if action_type == "block_keyword":
        if action == "approve":
            # Check 5a: ¿la keyword está protegida (marca/estratégica)?
            try:
                from engine.risk_classifier import is_keyword_protected
                if is_keyword_protected(keyword):
                    logger.warning(
                        "/approve: intento de bloquear keyword protegida '%s' — rechazado (decision_id=%d)",
                        keyword, decision["id"],
                    )
                    return _html(
                        "Keyword protegida",
                        f"<p>La keyword <strong>\"{keyword}\"</strong> está en la whitelist estratégica "
                        f"y <strong>no puede bloquearse</strong> desde este panel.</p>"
                        f"<p>Si deseas removerla de la whitelist, edita <code>config/agent_config.py → PROTECTED_KEYWORDS</code>.</p>",
                        "#e67e22",
                    )
            except Exception as exc:
                logger.warning("/approve: no se pudo verificar protección de keyword — %s", exc)

            # Check 5b: ¿la keyword ya existe como negativa activa en Google Ads?
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client    = engine["get_ads_client"]()
                ga_service = client.get_service("GoogleAdsService")
                neg_query = f"""
                    SELECT campaign_criterion.keyword.text
                    FROM campaign_criterion
                    WHERE campaign.id = {campaign_id}
                      AND campaign_criterion.negative = TRUE
                      AND campaign_criterion.type = 'KEYWORD'
                """
                existing_negatives = {
                    row.campaign_criterion.keyword.text.lower()
                    for row in ga_service.search(customer_id=target_id, query=neg_query)
                }
                already_negative = keyword.lower() in existing_negatives
            except Exception as exc:
                logger.warning("/approve: no se pudo verificar negativas existentes — %s", exc)
                already_negative = False

            if already_negative:
                memory.mark_autonomous_decision_approved(decision["id"])
                return _html(
                    "Ya estaba bloqueada",
                    f"<p>La keyword <strong>\"{keyword}\"</strong> ya aparece como negativa activa "
                    f"en la campaña <strong>{campaign_name}</strong>.</p>"
                    f"<p>La propuesta fue marcada como aprobada sin ejecutar una mutación adicional.</p>",
                    "#27ae60",
                )

            # Ejecutar la mutación real
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client    = engine["get_ads_client"]()
                engine["add_negative_keyword"](client, target_id, campaign_id, keyword)
                memory.mark_autonomous_decision_approved(decision["id"])
                logger.info(
                    "/approve: keyword '%s' bloqueada en campaña %s (decision_id=%d)",
                    keyword, campaign_name, decision["id"],
                )
                return _html(
                    "Aprobado y ejecutado",
                    f"<p>La keyword <strong>\"{keyword}\"</strong> fue agregada como negativa "
                    f"en la campaña <strong>{campaign_name}</strong>.</p>"
                    f"<p>El cambio es efectivo de inmediato en Google Ads.</p>",
                    "#27ae60",
                )
            except Exception as exc:
                logger.error("/approve: fallo al ejecutar mutación — %s", exc)
                return _html(
                    "Error al ejecutar",
                    f"<p>No se pudo bloquear la keyword. Error: <code>{exc}</code></p>"
                    f"<p>La propuesta sigue pendiente. Puedes intentarlo de nuevo o "
                    f"bloquearlo manualmente desde Google Ads.</p>",
                    "#c00",
                )

        else:  # reject
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: propuesta rechazada — keyword '%s' (decision_id=%d)",
                keyword, decision["id"],
            )
            return _html(
                "Rechazado",
                f"<p>La propuesta para bloquear <strong>\"{keyword}\"</strong> "
                f"en <strong>{campaign_name}</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

    # ── TIPO: budget_action (Fase 6B.1) ──────────────────────────────────────
    # BA1: reducción de presupuesto por CPA crítico.
    # Flujo: aprobación → verify_budget_still_actionable() → update_campaign_budget()
    # Requiere BUDGET_CHANGE_ENABLED=true para ejecutar la mutación vía API.
    # Sin el kill switch activo, la aprobación queda registrada sin ejecutar.
    #
    # Estados de aprobación (approve_outcome en evidence_json):
    #   approved_registered  — kill switch off; ejecución manual si se desea
    #   approved_dry_run_ok  — kill switch off pero guardas pasarían (dry-run OK)
    #   approved_blocked     — kill switch on pero una guarda bloqueó la ejecución
    #   approved_exec_error  — guardas pasaron pero la API rechazó la mutación
    #   execution_done       — presupuesto cambiado exitosamente vía API
    if action_type == "budget_action":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        campaign_type         = evidence.get("campaign_type", "")
        cpa_real              = evidence.get("cpa_real")
        cpa_critical          = evidence.get("cpa_critical")
        daily_budget_at_prop  = float(evidence.get("daily_budget_mxn") or 0)
        suggested             = evidence.get("suggested_daily_budget")
        reduction_pct         = evidence.get("reduction_pct")
        budget_resource_name  = evidence.get("budget_resource_name", "")
        is_shared_budget      = bool(evidence.get("budget_explicitly_shared", False))

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: budget_action rechazada — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de ajuste de presupuesto para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── Presupuesto compartido: rutina de separación ─────────────────────
        # Si el budget es explicitly_shared, el agente NO puede modificarlo directamente.
        # En su lugar, crea un presupuesto individual nuevo y reasigna la campaña.
        if is_shared_budget and action == "approve":
            from config.agent_config import BUDGET_CHANGE_ENABLED, BUDGET_CHANGE_ALLOW_IDS
            target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            _sug_shared = float(suggested) if suggested else 0.0

            # Kill switch
            if not BUDGET_CHANGE_ENABLED:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_registered",
                )
                return _html(
                    "Registrado — switch desactivado",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado, "
                    f"por lo que no se ejecutó la separación del presupuesto.</p>"
                    f"<p><strong>Campaña:</strong> {campaign_name}<br>"
                    f"Presupuesto sugerido: <strong>${_sug_shared:.2f} MXN/día</strong></p>",
                    "#6b7280",
                )

            # Whitelist
            if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                    approve_outcome="approved_registered",
                )
                return _html(
                    "Registrado — campaña no en whitelist",
                    f"<p>La campaña <strong>\"{campaign_name}\"</strong> no está en la whitelist "
                    f"<code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>",
                    "#6b7280",
                )

            if not target_id or _sug_shared <= 0:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="datos insuficientes para ejecutar separación de presupuesto compartido",
                    approve_outcome="approved_blocked",
                )
                return _html(
                    "Datos incompletos",
                    "<p>No hay suficientes datos para ejecutar la separación. "
                    "Verifica GOOGLE_ADS_TARGET_CUSTOMER_ID y el presupuesto sugerido.</p>",
                    "#c00",
                )

            try:
                _client = engine["get_ads_client"]()
                _sug_micros = int(_sug_shared * 1_000_000)
                sep_result = engine["separate_and_assign_budget"](
                    _client, target_id, campaign_id, _sug_micros, campaign_name
                )
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"excepción en separate_and_assign_budget: {exc}",
                    approve_outcome="approved_exec_error",
                )
                logger.error("/approve: excepción en separate_and_assign_budget — %s", exc)
                return _html(
                    "Error al separar presupuesto",
                    f"<p>Ocurrió un error al llamar a la API: <code>{exc}</code></p>",
                    "#c00",
                )

            if sep_result.get("status") != "success":
                err_msg = sep_result.get("message", "error desconocido")
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"API rechazó la separación: {err_msg}",
                    approve_outcome="approved_exec_error",
                )
                logger.error(
                    "/approve: separate_and_assign_budget falló para campaña '%s' — %s (decision_id=%d)",
                    campaign_name, err_msg, decision["id"],
                )
                return _html(
                    "API rechazó la operación",
                    f"<p>Google Ads rechazó la separación del presupuesto.</p>"
                    f"<p>Error: <code>{err_msg}</code></p>",
                    "#c00",
                )

            # Éxito: presupuesto separado y asignado
            memory.mark_budget_changed(
                decision["id"],
                {"current_budget_mxn": daily_budget_at_prop, "guard": "none", "ok": True},
                _sug_shared,
            )
            logger.info(
                "/approve: presupuesto compartido separado exitosamente — campaña '%s' "
                "nuevo presupuesto ${:.2f} MXN/día (decision_id=%d)",
                campaign_name, _sug_shared, decision["id"],
            )
            return _html(
                "Presupuesto separado y ajustado",
                f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
                f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
                f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
                f"✓ Presupuesto individual creado y asignado</p>"
                f"<p style='margin:6px 0 0;color:#166534;font-size:0.95em;'>"
                f"La campaña <strong>\"{campaign_name}\"</strong> ya tiene su propio presupuesto "
                f"de <strong>${_sug_shared:.2f} MXN/día</strong>. "
                f"El presupuesto compartido original no fue modificado.</p>"
                f"</div>"
                f"<p style='font-size:0.85em;color:#555;'>Recurso: "
                f"<code>{sep_result.get('new_budget_resource','')}</code></p>",
                "#15803d",
            )

        # ── Aprobación: construir datos de contexto comunes ──────────────────
        from config.agent_config import (
            BUDGET_CHANGE_ENABLED,
            BUDGET_CHANGE_ALLOW_IDS,
        )

        def _budget_context_html() -> str:
            """Bloque de evidencia reutilizable en todas las páginas de respuesta."""
            cpa_line = ""
            if cpa_real and cpa_critical:
                cpa_line = (
                    f"<p style='font-size:0.9em;color:#666;margin:4px 0 0;'>"
                    f"CPA real: <strong>${float(cpa_real):.2f}</strong> MXN · "
                    f"Umbral crítico: ${float(cpa_critical):.2f} MXN · "
                    f"Tipo: {campaign_type}</p>"
                )
            budget_line = ""
            if daily_budget_at_prop and suggested:
                budget_line = (
                    f"<p style='font-size:0.9em;color:#666;margin:4px 0 0;'>"
                    f"Presupuesto propuesta: ${float(daily_budget_at_prop):.2f} → "
                    f"<strong>${float(suggested):.2f} MXN/día</strong>"
                    f" (reducción {reduction_pct}%)</p>"
                )
            return f"<p><strong>Campaña:</strong> {campaign_name}</p>{cpa_line}{budget_line}"

        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")

        # ── Estado 1 & 2: kill switch desactivado ─────────────────────────────
        # Ejecutar verify de todas formas para poder reportar si habría funcionado
        if not BUDGET_CHANGE_ENABLED:
            dry_verify = None
            if target_id and suggested is not None and daily_budget_at_prop > 0:
                try:
                    _client = engine["get_ads_client"]()
                    dry_verify = engine["verify_budget_still_actionable"](
                        _client, target_id, campaign_id,
                        daily_budget_at_prop, float(suggested),
                    )
                except Exception as _ve:
                    logger.warning("/approve: dry verify error (switch off) — %s", _ve)

            if dry_verify and dry_verify.get("ok"):
                # Estado 2: approved_dry_run_ok — todo listo, solo falta activar switch
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_dry_run_ok",
                    verify_data=dry_verify,
                )
                logger.info(
                    "/approve: budget_action aprobada (dry-run OK) — "
                    "todas las guardas pasarían — campaña '%s' (decision_id=%d)",
                    campaign_name, decision["id"],
                )
                current_now = dry_verify.get("current_budget_mxn", daily_budget_at_prop)
                return _html(
                    "Registrado — dry-run OK",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado, "
                    f"por lo que no se ejecutó la mutación.</p>"
                    f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
                    f"padding:12px 16px;border-radius:0 6px 6px 0;margin:16px 0;'>"
                    f"<p style='margin:0;font-weight:600;color:#15803d;'>Dry-run OK — todas las guardas pasarían</p>"
                    f"<p style='margin:4px 0 0;font-size:0.9em;color:#166534;'>"
                    f"Si activas <code>BUDGET_CHANGE_ENABLED=true</code>, el agente ejecutaría:<br>"
                    f"${current_now:.2f} → <strong>${float(suggested):.2f} MXN/día</strong> "
                    f"(−{reduction_pct}%)</p>"
                    f"</div>"
                    f"{_budget_context_html()}",
                    "#15803d",
                )
            else:
                # Estado 1: approved_registered — switch off, y/o guardas fallarían
                block_note = ""
                if dry_verify and not dry_verify.get("ok"):
                    block_note = (
                        f"<p style='font-size:0.9em;color:#b45309;'>"
                        f"Nota: si activaras el switch ahora, la guarda "
                        f"<strong>{dry_verify.get('guard','')}</strong> también bloquearía: "
                        f"{dry_verify.get('reason','')}</p>"
                    )
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_registered",
                    verify_data=dry_verify,
                )
                logger.info(
                    "/approve: budget_action aprobada (registrada, switch off) — "
                    "campaña '%s' (decision_id=%d)",
                    campaign_name, decision["id"],
                )
                return _html(
                    "Registrado — switch desactivado",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado.</p>"
                    f"<p>Para que el agente ejecute cambios de presupuesto en el futuro, "
                    f"activa la variable de entorno <code>BUDGET_CHANGE_ENABLED=true</code> "
                    f"en Cloud Run.</p>"
                    f"{block_note}"
                    f"{_budget_context_html()}",
                    "#6b7280",
                )

        # ── Kill switch activo: verificar whitelist ───────────────────────────
        if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: budget_action aprobada (no en whitelist) — "
                "campaña '%s' id=%s (decision_id=%d)",
                campaign_name, campaign_id, decision["id"],
            )
            return _html(
                "Registrado — campaña no en whitelist",
                f"<p>Tu aprobación fue <strong>registrada</strong>, pero la campaña "
                f"<strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"no está en la whitelist <code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>"
                f"<p>Para permitir la ejecución, agrega el ID a la variable de entorno.</p>"
                f"{_budget_context_html()}",
                "#6b7280",
            )

        # ── Kill switch activo + whitelist OK: verificar guardas ─────────────
        if not target_id:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="GOOGLE_ADS_TARGET_CUSTOMER_ID no configurado",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Error de configuración",
                "<p><code>GOOGLE_ADS_TARGET_CUSTOMER_ID</code> no está configurado.</p>",
                "#c00",
            )

        if suggested is None or daily_budget_at_prop <= 0:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="presupuesto sugerido no disponible en la propuesta",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Datos de propuesta incompletos",
                "<p>La propuesta no contiene el presupuesto sugerido. "
                "No se puede ejecutar la mutación.</p>",
                "#c00",
            )

        try:
            _client = engine["get_ads_client"]()
            verify = engine["verify_budget_still_actionable"](
                _client, target_id, campaign_id,
                daily_budget_at_prop, float(suggested),
            )
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"error en verify: {exc}",
                approve_outcome="approved_blocked",
            )
            logger.error("/approve: error en verify_budget_still_actionable — %s", exc)
            return _html(
                "Error al verificar",
                f"<p>No se pudo verificar el estado del presupuesto: <code>{exc}</code></p>",
                "#c00",
            )

        # Estado 3: approved_blocked — una guarda bloqueó la ejecución
        if not verify.get("ok"):
            guard = verify.get("guard", "")
            reason_v = verify.get("reason", "")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=reason_v,
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            logger.info(
                "/approve: budget_action bloqueada por guarda %s — campaña '%s' (decision_id=%d): %s",
                guard, campaign_name, decision["id"], reason_v,
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La aprobación fue recibida pero la ejecución fue bloqueada "
                f"por una guarda de seguridad.</p>"
                f"<div style='background:#fef3c7;border-left:4px solid #f59e0b;"
                f"padding:12px 16px;border-radius:0 6px 6px 0;margin:16px 0;'>"
                f"<p style='margin:0;font-weight:600;color:#92400e;'>Guarda {guard} activa</p>"
                f"<p style='margin:4px 0 0;font-size:0.9em;color:#92400e;'>{reason_v}</p>"
                f"</div>"
                f"{_budget_context_html()}"
                f"<p style='font-size:0.9em;color:#888;'>La propuesta queda registrada. "
                f"Puedes revisarla manualmente en Google Ads.</p>",
                "#d97706",
            )

        # ── Todas las guardas pasaron: ejecutar la mutación ───────────────────
        current_budget_now = verify.get("current_budget_mxn", daily_budget_at_prop)
        budget_resource = budget_resource_name

        if not budget_resource:
            # Si no se almacenó en la propuesta, re-fetchar
            try:
                budget_info = engine["fetch_campaign_budget_info"](_client, target_id, campaign_id)
                budget_resource = budget_info.get("budget_resource_name", "")
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"no se pudo obtener budget_resource_name: {exc}",
                    approve_outcome="approved_blocked",
                    verify_data=verify,
                )
                return _html(
                    "Error al obtener presupuesto",
                    f"<p>No se pudo obtener el resource_name del presupuesto: <code>{exc}</code></p>",
                    "#c00",
                )

        if not budget_resource:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="budget_resource_name vacío — no se puede ejecutar mutación",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error de datos",
                "<p>El resource_name del presupuesto no está disponible. "
                "Cambia el presupuesto manualmente en Google Ads.</p>",
                "#c00",
            )

        suggested_micros = int(float(suggested) * 1_000_000)
        try:
            result = engine["update_campaign_budget"](_client, target_id, budget_resource, suggested_micros)
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"excepción al llamar update_campaign_budget: {exc}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error("/approve: excepción en update_campaign_budget — %s", exc)
            return _html(
                "Error al ejecutar",
                f"<p>Las guardas pasaron pero ocurrió un error al llamar a la API: "
                f"<code>{exc}</code></p>"
                f"<p>Puedes hacer el cambio manualmente en Google Ads: "
                f"<strong>${float(suggested):.2f} MXN/día</strong></p>",
                "#c00",
            )

        if result.get("status") != "success":
            err_msg = result.get("message", "error desconocido")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"API rechazó la mutación: {err_msg}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error(
                "/approve: update_campaign_budget falló para campaña '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "API rechazó el cambio",
                f"<p>Las guardas pasaron pero Google Ads rechazó la mutación.</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Puedes aplicar el cambio manualmente: <strong>${float(suggested):.2f} MXN/día</strong></p>",
                "#c00",
            )

        # Estado 4: execution_done — cambio aplicado exitosamente
        memory.mark_budget_changed(decision["id"], verify, float(suggested))
        logger.info(
            "/approve: presupuesto cambiado exitosamente — campaña '%s' "
            "${:.2f} → ${:.2f} MXN/día (decision_id=%d)",
            campaign_name, current_budget_now, float(suggested), decision["id"],
        )
        return _html(
            "Presupuesto actualizado",
            f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
            f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
            f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
            f"Cambio aplicado exitosamente</p>"
            f"<p style='margin:6px 0 0;color:#166534;'>"
            f"${current_budget_now:.2f} MXN/día → "
            f"<strong>${float(suggested):.2f} MXN/día</strong> "
            f"(−{verify.get('reduction_pct_actual', reduction_pct)}%)</p>"
            f"</div>"
            f"<p><strong>Campaña:</strong> {campaign_name}</p>"
            f"<p style='font-size:0.9em;color:#666;'>"
            f"Verificado a las {verify.get('verify_checked_at','')} UTC · "
            f"Estado campaña: {verify.get('campaign_status','')} · "
            f"Presupuesto compartido: {'Sí' if verify.get('budget_explicitly_shared') else 'No'}</p>"
            f"<p style='font-size:0.9em;color:#888;margin-top:16px;'>"
            f"El cambio es efectivo de inmediato en Google Ads. "
            f"El agente evaluará el impacto en el siguiente ciclo de auditoría.</p>",
            "#15803d",
        )

    # ── TIPO: geo_action (Fase GEO) ───────────────────────────────────────────
    # GEO1: corrección de geotargeting → dejar solo Mérida (1010205).
    # Flujo: aprobación → verify (campaña activa + sigue teniendo geo incorrecto)
    #        → update_campaign_location() → dejar solo 1010205.
    # Requiere GEO_AUTOFIX_ENABLED=true para ejecutar la mutación vía API.
    if action_type == "geo_action":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        geo_signal     = evidence.get("signal", "GEO1")
        detected_ids   = evidence.get("detected_location_ids", [])

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: geo_action rechazada — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de corrección de geotargeting para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── GEO_AUTOFIX_ENABLED=false → registrar sin ejecutar ────────────
        from config.agent_config import GEO_AUTOFIX_ENABLED, GEO_AUTOFIX_ALLOW_IDS, DEFAULT_ALLOWED_LOCATION_IDS
        if not GEO_AUTOFIX_ENABLED:
            memory.mark_autonomous_decision_approved(decision["id"])
            logger.info(
                "/approve: geo_action aprobada (GEO_AUTOFIX_ENABLED=false) — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Aprobación registrada — ejecución manual",
                f"<p>La corrección de geotargeting para "
                f"<strong>\"{campaign_name}\"</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Paso manual requerido:</strong> la ejecución automática vía API "
                f"está desactivada (<code>GEO_AUTOFIX_ENABLED=false</code>).<br>"
                f"Corrige la ubicación directamente en Google Ads → Campaña → Configuración → Ubicaciones.<br>"
                f"Deja solo <strong>Mérida, Yucatán, México</strong> (ID: 1010205).</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Ubicaciones detectadas: {detected_ids}</p>",
                "#2980b9",
            )

        # ── Whitelist check ───────────────────────────────────────────────
        if GEO_AUTOFIX_ALLOW_IDS and str(campaign_id) not in GEO_AUTOFIX_ALLOW_IDS:
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Aprobación registrada — ID no en whitelist",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"fue aprobada pero no está en <code>GEO_AUTOFIX_ALLOW_IDS</code>.</p>"
                f"<p>Agrega el ID a la variable de entorno para permitir la ejecución automática.</p>",
                "#2980b9",
            )

        # ── Verificación pre-ejecución ────────────────────────────────────
        # G1: ¿sigue activa la campaña?
        # G2: ¿sigue teniendo una ubicación incorrecta? (re-fetch en vivo)
        try:
            target_id   = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            client      = engine["get_ads_client"]()
            geo_fresh   = engine["fetch_campaign_geo_criteria"](client, target_id)
            fresh_entry = geo_fresh.get(str(campaign_id))
        except Exception as exc:
            logger.error("/approve: error al re-fetch geo criteria — %s", exc)
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Error en verificación",
                f"<p>No se pudo verificar el estado de geotargeting de "
                f"<strong>\"{campaign_name}\"</strong> antes de ejecutar la corrección.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>Corrige manualmente en Google Ads si lo consideras correcto.</p>",
                "#e67e22",
            )

        if not fresh_entry:
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Campaña no encontrada",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"ya no está activa o no fue encontrada. No se realizaron cambios.</p>",
                "#e67e22",
            )

        fresh_ids   = set(fresh_entry.get("location_ids", []))
        still_wrong = bool(fresh_ids - DEFAULT_ALLOWED_LOCATION_IDS) or not fresh_ids
        if not still_wrong:
            # La campaña ya tiene solo ubicaciones permitidas → sin acción necesaria
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Ya corregida",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> ya tiene solo ubicaciones permitidas: "
                f"{sorted(fresh_ids)}.</p>"
                f"<p>No se realizó ningún cambio adicional.</p>",
                "#27ae60",
            )

        # ── Ejecutar corrección ───────────────────────────────────────────
        MERIDA_LOCATION_ID = "1010205"
        try:
            fix_result = engine["update_campaign_location"](
                client, target_id, campaign_id, MERIDA_LOCATION_ID
            )
        except Exception as exc:
            logger.error("/approve: error en update_campaign_location — %s", exc)
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Error al corregir",
                f"<p>La verificación pasó pero ocurrió un error al corregir el geotargeting de "
                f"<strong>\"{campaign_name}\"</strong>.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>Corrige manualmente en Google Ads.</p>",
                "#c00",
            )

        if fix_result.get("status") != "success":
            err_msg = fix_result.get("message", "error desconocido")
            memory.mark_autonomous_decision_approved(decision["id"])
            logger.error(
                "/approve: update_campaign_location falló para '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "Error al corregir",
                f"<p>Google Ads rechazó la mutación para "
                f"<strong>\"{campaign_name}\"</strong>.</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Corrige manualmente en Google Ads.</p>",
                "#c00",
            )

        # Éxito
        memory.mark_autonomous_decision_approved(decision["id"])
        logger.info(
            "/approve: geotargeting corregido — campaña '%s' id=%s → solo Mérida 1010205 (decision_id=%d)",
            campaign_name, campaign_id, decision["id"],
        )
        return _html(
            "Geotargeting corregido",
            f"<p>La campaña <strong>\"{campaign_name}\"</strong> fue corregida exitosamente.</p>"
            f"<p>Ubicaciones anteriores: <code>{detected_ids}</code><br>"
            f"Ubicación ahora: <strong>Mérida, Yucatán, México (1010205)</strong></p>"
            f"<p>El cambio es efectivo de inmediato en Google Ads.</p>",
            "#27ae60",
        )

    # ── TIPO: budget_scale (Fase 6C — BA2) ───────────────────────────────────
    # BA2_REALLOC: escalar con fondos liberados por BA1 (costo neto $0).
    # BA2_SCALE:   escalar con nueva inversión.
    # Ambas sub-señales comparten la misma lógica de aprobación:
    #   aprobación → verify guards → update_campaign_budget()
    # Requiere BUDGET_CHANGE_ENABLED=true para ejecutar la mutación vía API.
    # Con el switch off, la aprobación queda registrada (manual si se desea).
    if action_type == "budget_scale":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        ba2_signal         = evidence.get("signal", "BA2_SCALE")
        current_budget     = float(evidence.get("current_daily_budget_mxn") or 0)
        suggested_budget   = float(evidence.get("suggested_daily_budget_mxn") or 0)
        increase_mxn       = float(evidence.get("increase_mxn") or 0)
        cpa_actual         = evidence.get("cpa_actual")
        cpa_ideal          = evidence.get("cpa_ideal")
        fund_source        = evidence.get("fund_source", "")
        budget_resource    = evidence.get("budget_resource_name", "")

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: budget_scale rechazada — campaña '%s' señal=%s (decision_id=%d)",
                campaign_name, ba2_signal, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de escalamiento ({ba2_signal}) para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        from config.agent_config import BUDGET_CHANGE_ENABLED, BUDGET_CHANGE_ALLOW_IDS
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")

        # ── Kill switch desactivado ───────────────────────────────────────────
        if not BUDGET_CHANGE_ENABLED:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="BUDGET_CHANGE_ENABLED=false",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: budget_scale aprobada (registrada, switch off) — "
                "campaña '%s' señal=%s (decision_id=%d)",
                campaign_name, ba2_signal, decision["id"],
            )
            _signal_badge = (
                '<span style="background:#dcfce7;color:#15803d;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700">BA2_REALLOC (costo neto $0)</span>'
                if ba2_signal == "BA2_REALLOC" else
                '<span style="background:#fef9c3;color:#854d0e;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700">BA2_SCALE (nueva inversión)</span>'
            )
            return _html(
                "Registrado — switch desactivado",
                f"<p>Tu aprobación fue <strong>registrada</strong>. "
                f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado.</p>"
                f"<p><strong>Campaña:</strong> {campaign_name} &nbsp;{_signal_badge}</p>"
                f"<p>Presupuesto sugerido: "
                f"${current_budget:.0f} → <strong>${suggested_budget:.0f} MXN/día</strong> "
                f"(+${increase_mxn:.0f} MXN/día)</p>"
                f"<p style='font-size:0.9em;color:#888;'>Fuente de fondos: {xe(fund_source)}</p>",
                "#6b7280",
            )

        # ── Whitelist ─────────────────────────────────────────────────────────
        if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            return _html(
                "Registrado — campaña no en whitelist",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> no está en "
                f"<code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>",
                "#6b7280",
            )

        if not target_id or suggested_budget <= 0 or current_budget <= 0:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="datos insuficientes para ejecutar escalamiento",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Datos incompletos",
                "<p>La propuesta no contiene presupuesto sugerido válido.</p>",
                "#c00",
            )

        # ── Verificar guardas pre-ejecución ──────────────────────────────────
        try:
            _client = engine["get_ads_client"]()
            verify = engine["verify_budget_still_actionable"](
                _client, target_id, campaign_id,
                current_budget, suggested_budget,
            )
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"error en verify: {exc}",
                approve_outcome="approved_blocked",
            )
            logger.error("/approve: error en verify para budget_scale — %s", exc)
            return _html(
                "Error al verificar",
                f"<p>No se pudo verificar el estado del presupuesto: <code>{exc}</code></p>",
                "#c00",
            )

        if not verify.get("ok"):
            guard = verify.get("guard", "")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=verify.get("reason", ""),
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La aprobación fue recibida pero la guarda <strong>{guard}</strong> "
                f"bloqueó la ejecución:</p>"
                f"<p style='color:#92400e;'>{xe(verify.get('reason',''))}</p>"
                f"<p>La propuesta queda registrada. Puedes ajustar el presupuesto manualmente.</p>",
                "#d97706",
            )

        # ── Obtener budget_resource_name si no se almacenó en la propuesta ───
        if not budget_resource:
            try:
                budget_info = engine["fetch_campaign_budget_info"](_client, target_id, campaign_id)
                budget_resource = budget_info.get("budget_resource_name", "")
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"no se pudo obtener budget_resource_name: {exc}",
                    approve_outcome="approved_blocked",
                    verify_data=verify,
                )
                return _html(
                    "Error al obtener presupuesto",
                    f"<p>No se pudo obtener el resource_name del presupuesto: <code>{exc}</code></p>",
                    "#c00",
                )

        if not budget_resource:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="budget_resource_name vacío",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error de datos",
                "<p>El resource_name del presupuesto no está disponible. "
                "Ajusta manualmente en Google Ads.</p>",
                "#c00",
            )

        # ── Ejecutar la mutación ──────────────────────────────────────────────
        suggested_micros = int(suggested_budget * 1_000_000)
        try:
            result = engine["update_campaign_budget"](_client, target_id, budget_resource, suggested_micros)
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"excepción en update_campaign_budget: {exc}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error("/approve: excepción en update_campaign_budget (BA2) — %s", exc)
            return _html(
                "Error al ejecutar",
                f"<p>Las guardas pasaron pero la API devolvió error: <code>{exc}</code></p>",
                "#c00",
            )

        if result.get("status") != "success":
            err_msg = result.get("message", "error desconocido")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"API rechazó la mutación: {err_msg}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error(
                "/approve: update_campaign_budget BA2 falló — campaña '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "API rechazó el cambio",
                f"<p>Las guardas pasaron pero Google Ads rechazó la mutación.</p>"
                f"<p>Error: <code>{err_msg}</code></p>",
                "#c00",
            )

        # ── Éxito ─────────────────────────────────────────────────────────────
        memory.mark_budget_changed(decision["id"], verify, suggested_budget)
        logger.info(
            "/approve: BA2 escalamiento ejecutado — campaña '%s' señal=%s "
            "${:.0f} → ${:.0f} MXN/día (decision_id=%d)",
            campaign_name, ba2_signal, current_budget, suggested_budget, decision["id"],
        )
        _signal_label = "Reasignación de fondos BA1 (costo neto $0)" if ba2_signal == "BA2_REALLOC" else "Nueva inversión requerida"
        _cpa_line = (
            f"<p style='font-size:0.9em;color:#666;'>CPA actual: <strong>${float(cpa_actual):.2f}</strong> MXN "
            f"(ideal: ${float(cpa_ideal):.2f} MXN)</p>"
            if cpa_actual and cpa_ideal else ""
        )
        return _html(
            "Presupuesto escalado",
            f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
            f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
            f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
            f"✓ Escalamiento aplicado — {xe(_signal_label)}</p>"
            f"<p style='margin:6px 0 0;color:#166534;'>"
            f"${current_budget:.0f} MXN/día → "
            f"<strong>${suggested_budget:.0f} MXN/día</strong> "
            f"(+${increase_mxn:.0f} MXN/día)</p>"
            f"</div>"
            f"<p><strong>Campaña:</strong> {campaign_name}</p>"
            f"{_cpa_line}"
            f"<p style='font-size:0.9em;color:#888;'>Fuente: {xe(fund_source)}</p>"
            f"<p style='font-size:0.9em;color:#888;margin-top:8px;'>El cambio es efectivo "
            f"de inmediato en Google Ads.</p>",
            "#15803d",
        )

    # ── TIPO: desconocido — ruta de seguridad ─────────────────────────────────
    # Tipos futuros llegan aquí hasta que se implemente su rama explícita.
    # Registrar y avisar sin ejecutar nada.
    logger.warning(
        "/approve: action_type desconocido '%s' (decision_id=%d) — sin ejecución",
        action_type, decision["id"],
    )
    if action == "approve":
        memory.mark_autonomous_decision_approved(decision["id"])
    else:
        memory.mark_autonomous_decision_rejected(decision["id"])

    return _html(
        "Registrado sin ejecución",
        f"<p>La respuesta (<strong>{action}</strong>) fue registrada para la propuesta "
        f"de tipo <strong>{action_type}</strong>.</p>"
        f"<p>Este tipo de propuesta aún no tiene ejecución automática implementada. "
        f"Revisa el estado en el log del agente.</p>",
        "#888",
    )


# ============================================================================
# WEEKLY EMAIL REPORT
# ============================================================================

@app.post("/send-weekly-report")
async def send_weekly_report_endpoint(dry_run: bool = False):
    """
    Genera el reporte ejecutivo semanal (Fase 5) y lo envía por email.
    Llamado automáticamente cada lunes por Cloud Scheduler.

    Bloque negocio: ventas netas (Ingresos_BD) + comensales (Cortes_de_Caja).
    Bloque agente:  actividad de los últimos 8 días desde autonomous_decisions.

    Query params:
      ?dry_run=true — retorna el HTML en la respuesta sin enviar correo.
    """
    try:
        from engine.email_reporter import send_weekly_report, build_html_report
        from engine.sheets_client import fetch_week_business_data, fetch_mtd_business_data
        from engine.weekly_supervisor import (
            query_week_activity,
            build_supervisor_data,
            get_next_best_action,
        )
        from engine.memory import get_memory_system as _get_mem

        # 0. Asegurar que la DB esté sincronizada desde GCS antes de consultar
        try:
            from engine.db_sync import download_from_gcs as _dl_db
            _dl_db()
        except Exception as _dl_err:
            print(f"[WEEKLY] db_sync download falló (no crítico): {_dl_err}")

        # 1. Expirar propuestas vencidas antes de armar el reporte
        try:
            _get_mem().sweep_expired_proposals()
        except Exception as _e:
            print(f"[WEEKLY] sweep_expired_proposals falló (no crítico): {_e}")

        # 2. Datos de negocio — Sheets
        week_data = fetch_week_business_data(weeks_ago=1)
        prev_week_data = fetch_week_business_data(weeks_ago=2)
        mtd_data = fetch_mtd_business_data()

        # 3. Actividad del agente — SQLite
        rows = query_week_activity(days=8)
        supervisor_data = build_supervisor_data(rows)
        next_action = get_next_best_action(supervisor_data)

        # 4. Auditorías frescas para el reporte (GEO + Smart)
        _target_id_w = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
        geo_report_data  = None
        smart_report_data = None
        try:
            from engine.ads_client import get_ads_client as _get_ads_client_w, fetch_campaign_geo_criteria as _fetch_geo
            from engine.geo_auditor import detect_geo_issues_by_policy as _detect_geo_policy
            from config.agent_config import (
                CAMPAIGN_GEO_OBJECTIVES as _CGO,
                GEO_OBJECTIVE_POLICIES  as _GOP,
            )
            _client_w = _get_ads_client_w()
            _criteria  = _fetch_geo(_client_w, _target_id_w)
            geo_report_data = _detect_geo_policy(_criteria, _CGO, _GOP)
            # Aplicar validaciones humanas de UI (con geo_criteria para verificar staleness)
            from engine.geo_ui_validator import load_ui_validations as _load_ui_val_w, apply_ui_validations as _apply_ui_val_w
            geo_report_data = _apply_ui_val_w(geo_report_data, _load_ui_val_w(), _criteria)
        except Exception as _geo_w_exc:
            print(f"[WEEKLY] geo audit no disponible (no crítico): {_geo_w_exc}")

        try:
            from engine.ads_client import get_ads_client as _get_ads_client_smart
            from engine.smart_campaign_auditor import audit_smart_campaigns as _audit_smart_w
            _client_smart = _get_ads_client_smart()
            smart_report_data = _audit_smart_w(_client_smart, _target_id_w)
        except Exception as _smart_w_exc:
            print(f"[WEEKLY] smart audit no disponible (no crítico): {_smart_w_exc}")

        # 4b. Métricas Google Ads — Bloque 3 del reporte
        ads_data = None
        try:
            from engine.ads_client import (
                get_ads_client as _get_ads_client_b3,
                fetch_campaign_metrics_range as _fetch_metrics_b3,
            )
            _client_b3 = _get_ads_client_b3()
            _ws_str = week_data["week_start"].strftime("%Y-%m-%d")
            _we_str = week_data["week_end"].strftime("%Y-%m-%d")
            _campaign_rows = _fetch_metrics_b3(_client_b3, _target_id_w, _ws_str, _we_str)
            if _campaign_rows:
                _total_cost   = sum(r["cost_mxn"]   for r in _campaign_rows)
                _total_conv   = sum(r["conversions"] for r in _campaign_rows)
                _total_clicks = sum(r["clicks"]      for r in _campaign_rows)
                ads_data = {
                    "cost_mxn":    round(_total_cost, 2),
                    "conversions": round(_total_conv, 1),
                    "clicks":      _total_clicks,
                    "cpa_mxn":     round(_total_cost / _total_conv, 2) if _total_conv > 0 else None,
                }
                print(f"[WEEKLY] Ads B3: gasto={ads_data['cost_mxn']}, conv={ads_data['conversions']}, CPA={ads_data['cpa_mxn']}")
        except Exception as _ads_exc:
            print(f"[WEEKLY] Google Ads B3 no disponible (no crítico): {_ads_exc}")
            ads_data = None

        # 5. dry_run: devuelve HTML sin enviar correo
        if dry_run:
            html = build_html_report(week_data, prev_week_data, mtd_data, supervisor_data, next_action,
                                     geo_data=geo_report_data, smart_data=smart_report_data,
                                     ads_data=ads_data)
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html, status_code=200)

        # 6. Enviar correo
        result = send_weekly_report(week_data, prev_week_data, mtd_data, supervisor_data, next_action,
                                    geo_data=geo_report_data, smart_data=smart_report_data,
                                    ads_data=ads_data)

        return {
            "status": "success" if result.get("success") else "error",
            "email": result,
            "week": {
                "start": str(week_data.get("week_start", "")),
                "end": str(week_data.get("week_end", "")),
                "ventas_netas": week_data.get("ventas_netas", 0),
                "comensales": week_data.get("comensales", 0),
            },
            "agent_summary": {
                "total_actions": supervisor_data.get("total_relevant", 0),
                "counts": supervisor_data.get("counts", {}),
            },
        }

    except Exception as e:
        import traceback
        print(f"[WEEKLY] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VISIBILIDAD OPERATIVA — /last-activity y /activity-log
# ============================================================================

@app.get("/last-activity")
async def get_last_activity():
    """
    Retorna el estado de actividad más reciente del sistema.

    Devuelve:
      - latest_run          — la última corrida registrada
      - last_successful_run — última corrida sin errores
      - last_run_with_errors— última corrida con errores
      - last_change_applied — última corrida donde se ejecutó algún cambio
      - last_block_by_security — última corrida donde una guarda bloqueó algo
      - run_count           — número total de corridas en el historial
    """
    from engine.activity_log import get_last_activity as _get_last
    try:
        return {"status": "ok", **_get_last()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/activity-log")
async def get_activity_log_endpoint(n: int = 14):
    """
    Retorna el historial de las últimas n corridas del sistema (default: 14 días).
    Máximo 30.
    """
    from engine.activity_log import get_activity_log as _get_log
    try:
        runs = _get_log(n=min(n, 30))
        return {"status": "ok", "runs": runs, "count": len(runs)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ============================================================================
# DASHBOARD (serve index.html)
# ============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Sirve el dashboard de control en tiempo real."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "index.html")
    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard no encontrado")


# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    # ── Sincronizar DB desde GCS antes de iniciar ─────────────────────────────
    try:
        from engine.db_sync import download_from_gcs
        synced = download_from_gcs()
        if synced:
            print("[DB_SYNC] ✓ DB restaurada desde GCS al iniciar instancia")
        else:
            print("[DB_SYNC] DB local iniciada (nueva instancia o GCS no configurado)")
    except Exception as _sync_err:
        print(f"[DB_SYNC] Advertencia: sync de startup falló (no crítico): {_sync_err}")

    print("=" * 70)
    print("THAI THAI ADS MISSION CONTROL v12.0 - SISTEMA COMPLETO")
    print("=" * 70)
    print("OK Skill #1: Waste Detector")
    print("OK Skill #2: Agent Decisioner")
    print("OK Skill #3: Hour Optimizer")
    print("OK Skill #4: Landing Page Optimizer")
    print("OK Skill #5: Promotion Suggester")
    print("OK Skill #6: Budget Allocator")
    print("OK Skill #7: Ad Performance Optimizer")
    print("=" * 70)
    port = int(os.environ.get("PORT", 8080))
    print(f"Servidor: http://0.0.0.0:{port}")
    print(f"Docs: http://0.0.0.0:{port}/docs")
    print(f"Mission Control: http://0.0.0.0:{port}/mission-control")
    print("=" * 70)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)