"""
Routes de Análisis — análisis de keywords, campañas, insights, historial, estrategia,
actividad del sistema.
"""
import os
import sqlite3
from typing import Optional, List, Dict
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from engine.db_sync import get_db_path

router = APIRouter(tags=["analysis"])

# Models used by these routes
class OptimizationAction(BaseModel):
    type: str
    keyword: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    spend: Optional[float] = None
    reason: Optional[str] = None

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


@router.get("/analyze-campaigns-detailed")
async def analyze_campaigns_detailed():
    try:
        engine = _get_engine()
        if not engine:
            raise Exception("Engine not available")
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id)
        keywords = engine["fetch_keyword_data"](client, target_id)
        search_terms = engine["fetch_search_term_data"](client, target_id)

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


@router.post("/execute-optimization")
async def execute_optimization(request: ExecuteOptimizationRequest):
    try:
        engine = _get_engine()
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
