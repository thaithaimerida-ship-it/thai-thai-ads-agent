"""
Routes del Ecosistema — Endpoints para alimentar thai-thai-web y thai-thai-dashboard.
Data ligera, rápida, sin autenticación (CORS ya está en *).
"""
import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ecosystem", tags=["ecosystem"])

CLOUD_RUN_URL = "https://thai-thai-ads-agent-624172071613.us-central1.run.app"


def _load_snapshot() -> dict | None:
    """Carga el último snapshot del mission-control desde GCS."""
    try:
        from google.cloud import storage
        _bucket = os.getenv("GCS_BUCKET", "thai-thai-agent-data")
        _blob = "snapshots/dashboard_snapshot.json"   # mismo path que _save_mc_snapshot en main.py
        client = storage.Client()
        bucket = client.bucket(_bucket)
        blob = bucket.blob(_blob)
        if blob.exists():
            return json.loads(blob.download_as_text())
        logger.info("ecosystem._load_snapshot: blob gs://%s/%s no existe aún", _bucket, _blob)
    except Exception as e:
        logger.warning("ecosystem._load_snapshot: %s", e)
    return None


async def _fallback_mission_control() -> dict | None:
    """Llama a mission_control_data(days=1) como fallback cuando no hay snapshot en GCS."""
    try:
        from main import mission_control_data
        result = await mission_control_data(days=1, month=None)
        # result puede ser un dict o un JSONResponse
        if hasattr(result, "body"):
            return json.loads(result.body)
        return result
    except Exception as e:
        logger.error("ecosystem._fallback_mission_control: %s", e)
        return None


@router.get("/ads-summary")
async def ads_summary():
    """
    Resumen de Google Ads para el AdminDashboard de thai-thai-web.
    Retorna datos en el formato exacto que espera AdminDashboard.jsx.
    Responde en <100ms (lee del snapshot, no llama a Google Ads API).
    """
    snapshot = _load_snapshot()
    if not snapshot:
        logger.info("ecosystem.ads_summary: snapshot vacío — usando fallback mission-control")
        snapshot = await _fallback_mission_control()
    if not snapshot:
        return JSONResponse(status_code=503, content={
            "status": "no_data",
            "message": "No hay snapshot disponible y el fallback falló.",
        })

    metrics = snapshot.get("metrics", {})
    waste = snapshot.get("waste", {})
    analysis = snapshot.get("analysis", {})
    campaign_sep = snapshot.get("campaign_separation", {})

    # Construir campaigns array desde el snapshot
    campaigns = []
    for key, label in [("local", "Thai Mérida - Local"), ("delivery", "Thai Mérida - Delivery")]:
        data = campaign_sep.get(key, {})
        spend = data.get("spend", 0)
        conv = data.get("conversions", 0)
        cpa = data.get("cpa", 0)
        campaigns.append({
            "name": label,
            "spend": spend,
            "conversions": conv,
            "cpa": cpa,
            "status": "critical" if (conv == 0 and spend > 50) else "ok",
        })

    # Agregar campaña de reservaciones si existe en proposals/alerts
    reserv_spend = metrics.get("total_spend", 0) - sum(c["spend"] for c in campaigns)
    if reserv_spend > 0:
        campaigns.append({
            "name": "Thai Mérida - Reservaciones",
            "spend": round(reserv_spend, 2),
            "conversions": 0,
            "cpa": 0,
            "status": "warning",
        })

    return {
        "status": "success",
        "timestamp": snapshot.get("timestamp", datetime.now().isoformat()),
        "summary": {
            "spend": metrics.get("total_spend", 0),
            "conversions": metrics.get("total_conversions", 0),
            "cpa": metrics.get("avg_cpa", 0),
            "ctr": analysis.get("summary", {}).get("ctr", 0),
            "conversion_rate": analysis.get("summary", {}).get("conversion_rate", 0),
            "estimated_waste": waste.get("summary", {}).get("total_waste", 0),
            "success_index": analysis.get("summary", {}).get("success_index", 0),
        },
        "campaigns": campaigns,
        "proposals_count": len(analysis.get("proposals", [])),
        "landing_page": snapshot.get("landing_page_health", {}),
    }


@router.get("/business-metrics")
async def business_metrics():
    """
    Métricas de negocio + ads para thai-thai-dashboard.
    Cruza datos de Google Ads con Google Sheets (comensales, ingresos).
    """
    snapshot = _load_snapshot()
    if not snapshot:
        logger.info("ecosystem.business_metrics: snapshot vacío — usando fallback mission-control")
        snapshot = await _fallback_mission_control()

    # Datos de ads del snapshot
    ads_data = {}
    if snapshot:
        metrics = snapshot.get("metrics", {})
        ads_data = {
            "total_spend": metrics.get("total_spend", 0),
            "total_conversions": metrics.get("total_conversions", 0),
            "avg_cpa": metrics.get("avg_cpa", 0),
            "campaigns_active": metrics.get("campaigns_active", 0),
            "total_waste": snapshot.get("waste", {}).get("summary", {}).get("total_waste", 0),
            "campaign_separation": snapshot.get("campaign_separation", {}),
            "timestamp": snapshot.get("timestamp"),
        }

    # Datos de negocio (Sheets) del snapshot
    negocio = {}
    if snapshot:
        negocio = snapshot.get("negocio_mtd", {})

    # Métrica cruzada: costo por comensal
    comensales = negocio.get("total_comensales", 0)
    ads_spend = ads_data.get("total_spend", 0)
    costo_por_comensal = round(ads_spend / comensales, 2) if comensales > 0 else 0

    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "ads": ads_data,
        "negocio": negocio,
        "cross_metrics": {
            "costo_por_comensal": costo_por_comensal,
            "comensales": comensales,
            "ads_spend": ads_spend,
        },
    }


@router.get("/health")
async def ecosystem_health():
    """Estado del ecosistema — verifica qué servicios están respondiendo."""
    snapshot = _load_snapshot()
    snapshot_age_minutes = None
    if snapshot and snapshot.get("timestamp"):
        try:
            ts = datetime.fromisoformat(snapshot["timestamp"])
            snapshot_age_minutes = round((datetime.now() - ts).total_seconds() / 60, 1)
        except Exception:
            pass

    return {
        "ads_agent": "online",
        "snapshot_available": snapshot is not None,
        "snapshot_age_minutes": snapshot_age_minutes,
        "endpoints": {
            "ads_summary": f"{CLOUD_RUN_URL}/ecosystem/ads-summary",
            "business_metrics": f"{CLOUD_RUN_URL}/ecosystem/business-metrics",
        },
    }
