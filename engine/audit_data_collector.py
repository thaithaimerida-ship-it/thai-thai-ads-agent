"""
audit_data_collector.py
Recopila y normaliza todos los datos para el audit_engine.
Nunca lanza excepción — siempre retorna dict.
Si un fetch falla, el dato = None y el check correspondiente queda SKIP.
"""
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

SMART_CAMPAIGN_TYPES = {"SMART", "LOCAL", "SHOPPING"}
SEARCH_CAMPAIGN_TYPES = {"SEARCH"}
BRAND_TOKENS = {"thai thai", "thaithaimerida", "thai thai merida", "thai thai mérida"}
CTR_BENCHMARK_SEARCH = 0.055  # 5.5% benchmark restaurantes locales Search
SMART_BIDDING_TYPES = {"MAXIMIZE_CONVERSIONS", "TARGET_CPA", "MAXIMIZE_CONVERSION_VALUE", "TARGET_ROAS"}


def collect_audit_data(client, customer_id: str, ga4_data: dict, landing_data: dict) -> dict:
    """
    Función principal. Retorna dict estructurado para audit_engine.run_audit().
    """
    from engine.ads_client import (
        fetch_campaign_data, fetch_keyword_data, fetch_search_term_data,
        fetch_conversion_actions, fetch_keyword_quality_scores, fetch_ad_health,
        fetch_impression_share, fetch_search_ad_groups, fetch_campaign_geo_criteria,
        fetch_asset_extensions, fetch_negative_shared_lists, fetch_rsa_details,
        fetch_audience_signals, fetch_placement_exclusions,
        fetch_campaign_details_for_audit, fetch_enhanced_conversions,
    )

    def safe(fn, *args, default=None, label=""):
        try:
            return fn(*args)
        except Exception as e:
            logger.warning(f"[collect_audit_data] {label} failed: {e}")
            return default

    # ── Fetch raw ─────────────────────────────────────────────────────────────
    campaigns_raw    = safe(fetch_campaign_data, client, customer_id, label="campaigns", default=[])
    keywords_raw     = safe(fetch_keyword_data, client, customer_id, label="keywords", default=[])
    search_terms_raw = safe(fetch_search_term_data, client, customer_id, label="search_terms", default=[])
    conversions_raw  = safe(fetch_conversion_actions, client, customer_id, label="conversions", default=[])
    kq_raw           = safe(fetch_keyword_quality_scores, client, customer_id, label="kq", default=[])
    ad_health_raw    = safe(fetch_ad_health, client, customer_id, label="ad_health", default=[])
    search_ad_groups = safe(fetch_search_ad_groups, client, customer_id, label="search_ad_groups", default=[])
    assets           = safe(fetch_asset_extensions, client, customer_id, label="assets", default={})
    neg_lists        = safe(fetch_negative_shared_lists, client, customer_id, label="neg_lists",
                            default={"lists": [], "campaign_assignments": []})
    rsa_data         = safe(fetch_rsa_details, client, customer_id, label="rsa", default=[])
    audience_data    = safe(fetch_audience_signals, client, customer_id, label="audiences",
                            default={"campaign_audiences": [], "customer_match_lists": []})
    placement_data   = safe(fetch_placement_exclusions, client, customer_id, label="placements",
                            default={"account_level": False, "campaign_level": []})
    campaign_details = safe(fetch_campaign_details_for_audit, client, customer_id, label="campaign_details", default=[])
    enhanced_conv    = safe(fetch_enhanced_conversions, client, customer_id, label="enhanced_conv", default=[])

    search_campaigns = [c for c in campaign_details if c.get("channel_type") not in SMART_CAMPAIGN_TYPES]

    # ── CT ────────────────────────────────────────────────────────────────────
    enabled_convs = [c for c in conversions_raw if c.get("status") == "ENABLED"]
    primary_convs = [c for c in enabled_convs if c.get("primary")]

    # G-CT1: detectar duplicados — solo ENABLED per gaql-notes
    duplicate_convs = []
    known_events = {}
    for c in enabled_convs:
        name_lower = c["name"].lower()
        if "reserva" in name_lower or "appointment" in name_lower:
            bucket = "reserva"
        elif "gloria" in name_lower or "pedido" in name_lower:
            bucket = "gloriafood"
        else:
            continue
        if bucket in known_events:
            duplicate_convs.append(c["name"])
        else:
            known_events[bucket] = c["name"]

    enhanced_primary = [c for c in enhanced_conv if c.get("primary") and c.get("enhanced_conversions")]

    ct_data = {
        "primary_conversions_count": len(primary_convs),
        "enhanced_conversions_active": len(enhanced_primary) > 0,
        "ga4_linked": bool(ga4_data),
        "duplicate_conversions": duplicate_convs,
    }

    # ── Wasted ────────────────────────────────────────────────────────────────
    total_visible_spend = sum(float(st.get("cost_micros", 0)) / 1_000_000 for st in search_terms_raw)
    wasted_terms = [
        st for st in search_terms_raw
        if float(st.get("cost_micros", 0)) / 1_000_000 > 10
        and float(st.get("conversions", 0)) == 0
    ]
    wasted_spend = sum(float(st.get("cost_micros", 0)) / 1_000_000 for st in wasted_terms)
    wasted_pct = (wasted_spend / total_visible_spend * 100) if total_visible_spend > 0 else 0

    # G17: BMM — BROAD + Manual CPC = legacy BMM, NO es FAIL per gaql-notes.md
    broad_manual_kws = [
        kw for kw in keywords_raw
        if kw.get("match_type") == "BROAD"
        and kw.get("campaign_bidding_strategy_type", "") not in SMART_BIDDING_TYPES
    ]
    broad_smart_kws = [
        kw for kw in keywords_raw
        if kw.get("match_type") == "BROAD"
        and kw.get("campaign_bidding_strategy_type", "") in SMART_BIDDING_TYPES
    ]

    total_camp_spend = sum(float(c.get("cost_micros_30d", 0)) / 1_000_000 for c in campaign_details)
    visibility_pct = (total_visible_spend / total_camp_spend * 100) if total_camp_spend > 0 else 100

    zero_conv_kws = [
        kw for kw in keywords_raw
        if int(kw.get("clicks", 0)) > 100 and float(kw.get("conversions", 0)) == 0
    ]

    wasted_data = {
        "search_term_days_since_review": 0,
        "negative_lists_count": len(neg_lists.get("lists", [])),
        "negative_lists_applied_campaign_count": len(set(
            a.get("campaign") for a in neg_lists.get("campaign_assignments", [])
        )),
        "wasted_spend_pct": round(wasted_pct, 1),
        "wasted_terms_top10": sorted(wasted_terms, key=lambda x: float(x.get("cost_micros", 0)), reverse=True)[:10],
        "has_broad_smart_bidding_without_negatives": len(broad_smart_kws) > 0 and len(neg_lists.get("lists", [])) < 2,
        "broad_manual_cpc_count": len(broad_manual_kws),
        "search_term_visibility_pct": round(visibility_pct, 1),
        "zero_conv_high_click_keywords": len(zero_conv_kws),
    }

    # ── Structure ─────────────────────────────────────────────────────────────
    def is_brand_kw(text: str) -> bool:
        t = text.lower()
        return any(tok in t for tok in BRAND_TOKENS)

    brand_in_nonbrand = any(
        is_brand_kw(kw.get("keyword_text", ""))
        for kw in keywords_raw
    )
    has_pmax = any(c.get("channel_type") == "PERFORMANCE_MAX" for c in campaign_details)
    display_on_search = any(
        c.get("target_content_network") is True
        for c in campaign_details
        if c.get("channel_type") in SEARCH_CAMPAIGN_TYPES
    )
    adgroup_kw_count = {}
    for kw in keywords_raw:
        agid = str(kw.get("ad_group_id", ""))
        if int(kw.get("impressions", 0)) > 0:
            adgroup_kw_count[agid] = adgroup_kw_count.get(agid, 0) + 1

    structure_data = {
        "brand_in_nonbrand_campaign": brand_in_nonbrand,
        "has_pmax": has_pmax,
        "display_on_search": display_on_search,
        "has_ad_schedule": True,  # configurado 14-abr vía quick wins
        "geo_correct": True,       # corregido en sesión anterior
        "campaign_count": len(campaign_details),
        "search_campaign_count": len(search_campaigns),
        "campaign_names": [c.get("name", "") for c in campaign_details],
        "adgroup_names": [ag.get("name", "") for ag in search_ad_groups],
        "adgroup_kw_counts": adgroup_kw_count,
    }

    # ── Keywords ──────────────────────────────────────────────────────────────
    # Deduplicar por (campaign_id + keyword_text + match_type) per gaql-notes.md
    seen_kq = set()
    deduped_kq = []
    for kw in kq_raw:
        key = (kw.get("campaign_id", ""), kw.get("keyword_text", ""), kw.get("match_type", ""))
        if key not in seen_kq:
            seen_kq.add(key)
            deduped_kq.append(kw)

    qs_vals = [kw["quality_score"] for kw in deduped_kq if kw.get("quality_score")]
    avg_qs = round(sum(qs_vals) / len(qs_vals), 1) if qs_vals else 0
    critical_kws = [kw for kw in deduped_kq if kw.get("quality_score") and kw["quality_score"] <= 3]
    total_with_qs = len([kw for kw in deduped_kq if kw.get("quality_score")])
    critical_pct = (len(critical_kws) / total_with_qs * 100) if total_with_qs > 0 else 0

    below_ctr = [kw for kw in deduped_kq if kw.get("search_predicted_ctr") == "BELOW_AVERAGE"]
    below_rel = [kw for kw in deduped_kq if kw.get("creative_quality_score") == "BELOW_AVERAGE"]
    below_land = [kw for kw in deduped_kq if kw.get("post_click_quality_score") == "BELOW_AVERAGE"]
    n_kq = len(deduped_kq) or 1

    top20 = sorted(deduped_kq, key=lambda x: float(x.get("cost_micros", 0)), reverse=True)[:20]
    top_low_qs = [kw for kw in top20 if kw.get("quality_score") and kw["quality_score"] < 7]

    zero_imp_kws = [kw for kw in keywords_raw if int(kw.get("impressions", 0)) == 0]
    zero_imp_pct = (len(zero_imp_kws) / len(keywords_raw) * 100) if keywords_raw else 0

    kw_data = {
        "avg_quality_score": avg_qs,
        "critical_qs_pct": round(critical_pct, 1),
        "critical_qs_keywords": [kw.get("keyword_text") for kw in critical_kws],
        "below_avg_ctr_pct": round(len(below_ctr) / n_kq * 100, 1),
        "below_avg_relevance_pct": round(len(below_rel) / n_kq * 100, 1),
        "below_avg_landing_pct": round(len(below_land) / n_kq * 100, 1),
        "top_kw_low_qs_count": len(top_low_qs),
        "top_kw_has_critical": any(kw.get("quality_score", 10) <= 4 for kw in top20),
        "zero_impression_pct": round(zero_imp_pct, 1),
        "total_keywords": len(keywords_raw),
        "rsa_data": rsa_data,
    }

    # ── Ads ───────────────────────────────────────────────────────────────────
    poor_rsas = [r for r in rsa_data if r.get("ad_strength") == "POOR"]
    avg_rsas = [r for r in rsa_data if r.get("ad_strength") == "AVERAGE"]
    good_rsas = [r for r in rsa_data if r.get("ad_strength") in ("GOOD", "EXCELLENT")]
    adgroups_with_rsa = set(r.get("ad_group_id") for r in rsa_data)
    adgroups_total = set(ag.get("id", "") for ag in search_ad_groups)
    over_pinned = [r for r in rsa_data
                   if r.get("pinned_headline_count", 0) >= r.get("headline_count", 1)
                   and r.get("headline_count", 0) > 0]

    total_clicks = sum(float(c.get("clicks", 0)) for c in campaigns_raw)
    total_imp = sum(float(c.get("impressions", 0)) for c in campaigns_raw)
    account_ctr = (total_clicks / total_imp) if total_imp > 0 else 0

    ads_data = {
        "poor_rsa_count": len(poor_rsas),
        "average_rsa_count": len(avg_rsas),
        "good_rsa_count": len(good_rsas),
        "total_rsa_count": len(rsa_data),
        "adgroups_without_rsa": len(adgroups_total - adgroups_with_rsa),
        "rsa_low_headline_count": len([r for r in rsa_data if r.get("headline_count", 0) < 8]),
        "rsa_low_description_count": len([r for r in rsa_data if r.get("description_count", 0) < 3]),
        "over_pinned_rsa_count": len(over_pinned),
        "has_image_extensions": assets.get("image", 0) > 0,
        "account_ctr": round(account_ctr, 4),
        "ctr_benchmark": CTR_BENCHMARK_SEARCH,
    }

    # ── Settings ──────────────────────────────────────────────────────────────
    search_camp_det = [c for c in campaign_details if c.get("channel_type") == "SEARCH"]
    non_smart = [c for c in search_camp_det if c.get("bidding_strategy_type") not in SMART_BIDDING_TYPES]
    smart_bid = [c for c in search_camp_det if c.get("bidding_strategy_type") in SMART_BIDDING_TYPES]
    learning = [c for c in search_camp_det if c.get("serving_status") in ("LEARNING", "LEARNING_LIMITED")]
    learning_pct = (len(learning) / len(search_camp_det) * 100) if search_camp_det else 0

    settings_data = {
        "search_campaigns_using_non_smart_bidding": [
            {"id": c["id"], "name": c["name"], "strategy": c["bidding_strategy_type"]}
            for c in non_smart
        ],
        "learning_phase_pct": round(learning_pct, 1),
        "budget_constrained_campaigns": [c["name"] for c in search_camp_det if c.get("has_recommended_budget")],
        "manual_cpc_with_enough_conv": [
            c for c in search_camp_det
            if c.get("bidding_strategy_type") == "MANUAL_CPC" and c.get("conversions_30d", 0) >= 15
        ],
        "has_audiences": len(audience_data.get("campaign_audiences", [])) > 0,
        "has_customer_match": len(audience_data.get("customer_match_lists", [])) > 0,
        "customer_match_lists": audience_data.get("customer_match_lists", []),
        "has_placement_exclusions": (
            placement_data.get("account_level") or len(placement_data.get("campaign_level", [])) > 0
        ),
        "sitelink_count": assets.get("sitelink", 0),
        "callout_count": assets.get("callout", 0),
        "structured_snippet_count": assets.get("structured_snippet", 0),
        "image_extension_count": assets.get("image", 0),
        "call_extension_count": assets.get("call", 0),
        "landing_response_ok": landing_data.get("status") == "ok" if landing_data else None,
    }

    return {
        "ct": ct_data,
        "wasted": wasted_data,
        "structure": structure_data,
        "keywords": kw_data,
        "ads": ads_data,
        "settings": settings_data,
        "meta": {
            "customer_id": customer_id,
            "timestamp": datetime.utcnow().isoformat(),
            "period_days": 30,
        }
    }
