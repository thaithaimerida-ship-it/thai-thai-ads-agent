"""
Ruta de diagnóstico temporal — GET /debug-fase-6d

Ejecuta las 3 queries GAQL de Fase 6D sin try/except para exponer
errores reales. Solo para debugging — no usar en producción.

fetch_keyword_quality_scores: se llama directamente (ya lanza si falla).
fetch_ad_health y fetch_impression_share: lógica inlineada sin try/except
para ver el error crudo de la API en lugar del [] silencioso.
"""
import os
from fastapi import APIRouter

router = APIRouter(tags=["debug"])

_STRENGTH_MAP = {0: None, 1: "POOR", 2: "AVERAGE", 3: "GOOD", 4: "EXCELLENT", 5: "NO_ADS"}


def _debug_ad_health(client, customer_id: str) -> list:
    """fetch_ad_health sin try/except — muestra el error real."""
    query = """
        SELECT
          ad_group_ad.ad.id,
          ad_group_ad.ad.responsive_search_ad.ad_strength,
          ad_group_ad.status,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.ad.responsive_search_ad.headlines,
          ad_group_ad.ad.responsive_search_ad.descriptions,
          ad_group_ad.ad.final_urls,
          campaign.id, campaign.name,
          ad_group.id, ad_group.name
        FROM ad_group_ad
        WHERE ad_group_ad.status IN ('ENABLED', 'PAUSED')
          AND campaign.status = 'ENABLED'
    """
    ga_service = client.get_service("GoogleAdsService")
    results = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        aga = row.ad_group_ad
        ad  = aga.ad
        try:
            rsa          = ad.responsive_search_ad
            strength_val = int(rsa.ad_strength) if rsa.ad_strength else 0
            ad_strength  = _STRENGTH_MAP.get(strength_val)
            headlines    = [h.text for h in rsa.headlines if h.text]
            descriptions = [d.text for d in rsa.descriptions if d.text]
        except Exception:
            # Smart Campaigns no tienen RSA — esto es esperado por fila, no un error GAQL
            ad_strength  = None
            headlines    = []
            descriptions = []

        results.append({
            "ad_id":             str(ad.id),
            "ad_strength":       ad_strength,
            "ad_status":         str(aga.status.name) if aga.status else None,
            "approval_status":   str(aga.policy_summary.approval_status.name)
                                 if aga.policy_summary and aga.policy_summary.approval_status else None,
            "headlines":         headlines,
            "descriptions":      descriptions,
            "final_urls":        list(ad.final_urls) if ad.final_urls else [],
            "campaign_id":       str(row.campaign.id),
            "campaign_name":     row.campaign.name,
            "ad_group_id":       str(row.ad_group.id),
            "ad_group_name":     row.ad_group.name,
            "ad_group_resource": row.ad_group.resource_name,
        })
    return results


def _debug_impression_share(client, customer_id: str) -> list:
    """fetch_impression_share sin try/except — muestra el error real."""
    query = """
        SELECT
          campaign.id, campaign.name,
          metrics.search_impression_share,
          metrics.search_top_impression_rate,
          metrics.search_rank_lost_impression_share,
          metrics.search_budget_lost_impression_share
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date DURING LAST_7_DAYS
    """
    ga_service = client.get_service("GoogleAdsService")
    results = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        m = row.metrics
        results.append({
            "campaign_id":                        str(row.campaign.id),
            "campaign_name":                      row.campaign.name,
            "search_impression_share":            m.search_impression_share,
            "search_top_impression_rate":         m.search_top_impression_rate,
            "search_rank_lost_impression_share":  m.search_rank_lost_impression_share,
            "search_budget_lost_impression_share": m.search_budget_lost_impression_share,
        })
    return results


@router.get("/debug-fase-6d")
def debug_fase_6d():
    from engine.ads_client import get_ads_client, fetch_keyword_quality_scores

    client      = get_ads_client()
    customer_id = os.environ["GOOGLE_ADS_TARGET_CUSTOMER_ID"]

    kq  = fetch_keyword_quality_scores(client, customer_id)
    ah  = _debug_ad_health(client, customer_id)
    ims = _debug_impression_share(client, customer_id)

    return {
        "customer_id":            customer_id,
        "keyword_quality_scores": kq,
        "ad_health":              ah,
        "impression_share":       ims,
        "counts": {
            "keyword_quality_scores": len(kq),
            "ad_health":              len(ah),
            "impression_share":       len(ims),
        },
    }
