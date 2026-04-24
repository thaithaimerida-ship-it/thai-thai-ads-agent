"""
Thai Thai Ads Agent v12.0 - Mission Control Backend
Backend COMPLETO con 7 skills integradas para autonomía total
"""

import os
import json
import logging
logging.basicConfig(level=logging.INFO)
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import random

logger = logging.getLogger(__name__)

# ── GCS import diagnostic (temporal — confirma que el paquete está instalado) ─
try:
    import google.cloud
    _gc_path = getattr(google.cloud, "__file__", getattr(google.cloud, "__path__", "unknown"))
    logger.info("DIAG google.cloud cargado desde: %s", _gc_path)
    from google.cloud import storage as _gcs_diag
    logger.info("DIAG google.cloud.storage OK — %s", getattr(_gcs_diag, "__file__", "unknown"))
except Exception as _diag_exc:
    logger.error("DIAG google.cloud.storage FALLO: %s", _diag_exc)
# ─────────────────────────────────────────────────────────────────────────────

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

_GCS_BUCKET   = os.getenv("GCS_BUCKET", "thai-thai-agent-data")
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
        import traceback
        logger.error(
            "_save_mc_snapshot: FALLO guardando en GCS\n"
            "  bucket=%s blob=%s\n"
            "  error=%s\n"
            "  traceback=%s",
            _GCS_BUCKET, _GCS_SNAPSHOT, exc, traceback.format_exc()
        )

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
        import traceback
        logger.error(
            "_load_mc_snapshot: FALLO leyendo GCS\n"
            "  bucket=%s blob=%s\n"
            "  error=%s\n"
            "  traceback=%s",
            _GCS_BUCKET, _GCS_SNAPSHOT, exc, traceback.format_exc()
        )
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


@app.on_event("startup")
async def startup_event():
    """Restaura la base de datos desde GCS al iniciar la instancia."""
    try:
        from engine.db_sync import download_from_gcs
        ok = download_from_gcs()
        if ok:
            logger.info("startup: DB restaurada desde GCS OK")
        else:
            logger.warning("startup: download_from_gcs() retornó False — se usará DB local")
    except Exception as e:
        logger.error("startup: error restaurando DB desde GCS: %s", e)

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
from routes.analysis import router as analysis_router
from routes.tracking import router as tracking_router
from routes.approvals import router as approvals_router
from routes.reports import router as reports_router
from routes.builder import router as builder_router
from routes.ecosystem import router as ecosystem_router
from routes.keywords import router as keywords_router
app.include_router(analysis_router)
app.include_router(tracking_router)
app.include_router(approvals_router)
app.include_router(reports_router)
app.include_router(builder_router)
app.include_router(ecosystem_router)
app.include_router(keywords_router)
app.include_router(campaigns_router)
from routes.debug_fase_6d import router as debug_fase_6d_router
app.include_router(debug_fase_6d_router)
from routes.gloriafood_webhook import router as gloriafood_router
app.include_router(gloriafood_router)

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

@app.get("/debug/gcs-snapshot-test")
async def debug_gcs_snapshot_test():
    """
    Prueba real de acceso a GCS: crea cliente, valida bucket, escribe blob temporal, lo lee y lo borra.
    No usa mocks. Útil para diagnosticar por qué _save_mc_snapshot falla.
    """
    import traceback
    bucket_name = _GCS_BUCKET
    test_blob   = "debug/gcs_write_test.json"
    result: dict = {
        "bucket": bucket_name,
        "snapshot_blob": _GCS_SNAPSHOT,
        "steps": {},
    }
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        result["steps"]["client_created"] = True
        result["project"] = client.project
    except Exception as exc:
        result["steps"]["client_created"] = False
        result["steps"]["client_error"] = str(exc)
        result["steps"]["traceback"] = traceback.format_exc()
        return JSONResponse(status_code=500, content=result)

    try:
        bucket = client.bucket(bucket_name)
        bucket.reload()
        result["steps"]["bucket_accessible"] = True
    except Exception as exc:
        result["steps"]["bucket_accessible"] = False
        result["steps"]["bucket_error"] = str(exc)
        result["steps"]["traceback"] = traceback.format_exc()
        return JSONResponse(status_code=500, content=result)

    try:
        payload = json.dumps({"test": True, "ts": datetime.now().isoformat()})
        bucket.blob(test_blob).upload_from_string(payload, content_type="application/json")
        result["steps"]["write_ok"] = True
    except Exception as exc:
        result["steps"]["write_ok"] = False
        result["steps"]["write_error"] = str(exc)
        result["steps"]["traceback"] = traceback.format_exc()
        return JSONResponse(status_code=500, content=result)

    try:
        data = json.loads(bucket.blob(test_blob).download_as_text())
        result["steps"]["read_ok"] = True
        result["steps"]["read_data"] = data
    except Exception as exc:
        result["steps"]["read_ok"] = False
        result["steps"]["read_error"] = str(exc)

    try:
        bucket.blob(test_blob).delete()
        result["steps"]["cleanup_ok"] = True
    except Exception:
        result["steps"]["cleanup_ok"] = False

    try:
        snapshot_blob = bucket.blob(_GCS_SNAPSHOT)
        result["steps"]["snapshot_exists"] = snapshot_blob.exists()
        if result["steps"]["snapshot_exists"]:
            result["steps"]["snapshot_size_bytes"] = snapshot_blob.size
            result["steps"]["snapshot_updated"] = str(snapshot_blob.updated)
    except Exception as exc:
        result["steps"]["snapshot_check_error"] = str(exc)

    result["success"] = all([
        result["steps"].get("client_created"),
        result["steps"].get("bucket_accessible"),
        result["steps"].get("write_ok"),
        result["steps"].get("read_ok"),
    ])
    return result


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

# ============================================================================
# ENDPOINTS DE AUDITORÍA — delegan a agents/auditor.py
# ============================================================================

@app.api_route("/run-autonomous-audit", methods=["GET", "POST"])
async def run_autonomous_audit():
    """
    Ejecuta la auditoría de forma síncrona y retorna 200 cuando termina.
    Cloud Run (CPU-only mode) mata los BackgroundTasks tras devolver la respuesta —
    por eso se ejecuta directamente con await para garantizar que el correo se envíe.
    El Cloud Scheduler tiene attemptDeadline=300s, suficiente para completar la tarea.
    """
    from agents.auditor import Auditor
    session_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info("run_autonomous_audit: iniciando auditoría síncrona — sesión=%s", session_id)
    auditor = Auditor()
    await auditor.run_autonomous_audit(run_type="daily")
    return JSONResponse(
        status_code=200,
        content={
            "status":     "completed",
            "session_id": session_id,
            "message":    "Auditoría completada",
        },
    )


@app.post("/run-quick-wins")
async def run_quick_wins():
    """Quick Wins estructurales auditoría 14-abr-2026. Idempotente. Solo campañas Search."""
    from engine.ads_client import (
        get_ads_client, fetch_conversion_actions, disable_conversion_action,
        update_bidding_strategy, update_network_settings,
        clear_ad_schedules, update_ad_schedule
    )
    from engine.credentials import load_credentials

    CUSTOMER_ID = "4021070209"
    EXPERIENCIA_ID = "23730364039"
    RESERVACIONES_ID = "23680871468"

    LEGACY_CONVERSIONS = [
        "Thai Thai Merida (web) reserva_completada",
        "Thai Thai Merida (web) click_pedir_online",
        "Pedido completado Gloria Food",
    ]
    SCHEDULE_DAYS = ["TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"]

    results = {
        "qw2_conversiones": [],
        "qw3_bidding": {},
        "qw4_display": {},
        "qw5_schedule": {},
        "errors": []
    }

    try:
        creds = load_credentials()
        client = get_ads_client(creds)

        # QW2 — Pausar conversiones legacy duplicadas
        for conv in fetch_conversion_actions(client, CUSTOMER_ID):
            if conv["name"] in LEGACY_CONVERSIONS:
                r = disable_conversion_action(client, CUSTOMER_ID, conv["id"], conv["name"])
                results["qw2_conversiones"].append({"name": conv["name"], **r})

        # QW3 — TIS → Maximize Conversions en Experiencia 2026
        results["qw3_bidding"] = update_bidding_strategy(
            client, CUSTOMER_ID, EXPERIENCIA_ID, "MAXIMIZE_CONVERSIONS"
        )

        # QW4 — Desactivar Display Network en Experiencia 2026
        results["qw4_display"] = update_network_settings(
            client, CUSTOMER_ID, EXPERIENCIA_ID, target_content_network=False
        )

        # QW5 — Ad schedule Mar-Dom 11-22h en ambas campañas Search
        for camp_id in [EXPERIENCIA_ID, RESERVACIONES_ID]:
            cleared = clear_ad_schedules(client, CUSTOMER_ID, camp_id)
            days = [update_ad_schedule(client, CUSTOMER_ID, camp_id, d, 11, 22)
                    for d in SCHEDULE_DAYS]
            results["qw5_schedule"][camp_id] = {"cleared": cleared, "days": days}

    except Exception as e:
        results["errors"].append(str(e))

    return results


@app.api_route("/run-compensatory-audit", methods=["GET", "POST"])
async def run_compensatory_audit():
    """
    Corrida compensatoria síncrona: solo corre si no hubo auditoría real hoy.
    Igual que run_autonomous_audit, se ejecuta con await para sobrevivir en Cloud Run CPU-only.
    """
    from engine.activity_log import had_successful_run_today
    from agents.auditor import Auditor

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
    auditor = Auditor()
    await auditor.run_autonomous_audit(run_type="compensatory")
    return JSONResponse(
        status_code=200,
        content={
            "status":     "completed",
            "session_id": session_id,
            "message":    "Corrida compensatoria completada",
        },
    )

