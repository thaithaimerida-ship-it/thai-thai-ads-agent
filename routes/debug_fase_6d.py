"""
Ruta de diagnóstico temporal — GET /debug-fase-6d

Ejecuta las 3 queries GAQL de Fase 6D sin try/catch para exponer
errores reales. Solo para debugging — no usar en producción.
"""
import os
from fastapi import APIRouter

router = APIRouter(tags=["debug"])


@router.get("/debug-fase-6d")
def debug_fase_6d():
    from engine.ads_client import (
        get_ads_client,
        fetch_keyword_quality_scores,
        fetch_ad_health,
        fetch_impression_share,
    )

    client      = get_ads_client()
    customer_id = os.environ["GOOGLE_ADS_TARGET_CUSTOMER_ID"]

    kq  = fetch_keyword_quality_scores(client, customer_id)
    ah  = fetch_ad_health(client, customer_id)
    ims = fetch_impression_share(client, customer_id)

    return {
        "customer_id":             customer_id,
        "keyword_quality_scores":  kq,
        "ad_health":               ah,
        "impression_share":        ims,
        "counts": {
            "keyword_quality_scores": len(kq),
            "ad_health":              len(ah),
            "impression_share":       len(ims),
        },
    }
