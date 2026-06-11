"""Read-only Monitor endpoints."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from engine.monitor_digest_v3 import build_monitor_digest
from engine.monitor_sections import build_ads_quality_from_list, build_campaign_metrics
from engine.monitor_sources import (
    build_search_console_context,
    build_seo_context,
    load_gbp_context,
    load_gloriafood_internal,
)
from routes.analysis import VALID_DATE_RANGES, _build_search_terms_payload, _normalize_date_range


router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("MONITOR_BASE_URL", "https://thai-thai-ads-agent-624172071613.us-central1.run.app")
_ACTIONS_TOKEN = os.getenv("ACTIONS_TOKEN", "PENDIENTE_PARTE_B")

_RANGE_DAYS = {"TODAY": 1, "YESTERDAY": 1, "LAST_7_DAYS": 7, "LAST_14_DAYS": 14,
               "LAST_30_DAYS": 30, "THIS_MONTH": 30, "LAST_MONTH": 30}


def _links() -> dict:
    return {
        "ads": "https://ads.google.com/aw/overview",
        "bloqueo_base": f"{_BASE_URL}/acciones/bloqueo",
        "resenas": f"{_BASE_URL}/acciones/resenas?token={_ACTIONS_TOKEN}",
        "revision": f"{_BASE_URL}/acciones/bloqueo?token={_ACTIONS_TOKEN}",
        "token": _ACTIONS_TOKEN,
    }


def _ads_quality(client, target_id: str, date_range: str) -> dict:
    """Merge ad health + metrics (same shape as /ads-report) into ads_quality."""
    from engine.ads_client import fetch_ad_health, fetch_ad_metrics
    health = {h.get("ad_id"): h for h in (fetch_ad_health(client, target_id) or [])}
    ads = []
    for m in fetch_ad_metrics(client, target_id, date_range) or []:
        h = health.get(m.get("ad_id"), {})
        ads.append({
            "ad_id": m.get("ad_id", ""),
            "campaign_name": h.get("campaign_name", ""),
            "ad_strength": h.get("ad_strength"),
            "approval_status": h.get("approval_status"),
            "headlines": h.get("headlines", []),
            "ctr_pct": round(float(m.get("ctr", 0)) * 100, 2),
            "clicks": int(m.get("clicks", 0)),
            "impressions": int(m.get("impressions", 0)),
            "conversions": round(float(m.get("conversions", 0)), 1),
        })
    return build_ads_quality_from_list(ads, _RANGE_DAYS.get(date_range, 7))


def _build_context(date_range: str, mode: str) -> dict:
    """Assemble the read-only enrichment context. Never raises — missing sources
    degrade to data_broken / search-term fallback."""
    context: dict = {
        "mode": "friday" if str(mode).strip().lower() == "friday" else "monday",
        "links": _links(),
    }
    try:
        context.update(load_gbp_context())
    except Exception:
        context["gbp"] = {"data_broken": True}
        context["reviews"] = {"data_broken": True}
    try:
        interno = load_gloriafood_internal()
        if interno:
            context["pedidos_gloriafood_interno"] = interno
    except Exception:
        pass
    # PageSpeed only when a key is configured (keyless PSI is rate-limited / 429).
    if os.getenv("PAGESPEED_API_KEY"):
        try:
            context.update(build_seo_context())
        except Exception:
            context["seo"] = {"data_broken": True}
    else:
        context["seo"] = {"data_broken": True}

    try:
        context.update(build_search_console_context())
    except Exception:
        context["search_console"] = {"data_broken": True}

    # Google Ads sources (read-only). Token may be down → leave sections to fall back.
    try:
        from engine.ads_client import fetch_campaign_conversion_breakdown, fetch_campaign_data, get_ads_client
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = get_ads_client()
        campaigns = fetch_campaign_data(client, target_id, date_range)
        breakdown = fetch_campaign_conversion_breakdown(client, target_id, date_range)
        # 30d window for the 'provisional' health (señales + CTR vs propio promedio 30d).
        campaigns_30d = fetch_campaign_data(client, target_id, "LAST_30_DAYS")
        breakdown_30d = fetch_campaign_conversion_breakdown(client, target_id, "LAST_30_DAYS")
        if campaigns:
            context["campaign_metrics"] = build_campaign_metrics(campaigns, breakdown, campaigns_30d, breakdown_30d)
        context["ads_quality"] = _ads_quality(client, target_id, date_range)
    except Exception as exc:
        logger.warning("monitor context: Google Ads sources unavailable — %s", exc)

    return context


@router.get("/monitor/digest")
async def monitor_digest(date_range: str = "LAST_7_DAYS", mode: str = "monday"):
    """Monitor Digest V3: read-only summary + rendered email for the weekly digest.

    mode=friday renders the short Friday close (decisions + anomalies + spend only).
    """
    date_range = _normalize_date_range(date_range)
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
        )
    payload = _build_search_terms_payload(date_range)
    return build_monitor_digest(payload, _build_context(date_range, mode))
