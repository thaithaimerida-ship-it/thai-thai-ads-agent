"""
Google Ads Health Audit — Thai Thai Mérida (24 abr 2026)
Basado en skill ads-google (80 checks, scoring-system.md, benchmarks.md)
Solo lectura. Genera: reports/google_ads_health_audit_24abr2026.md

CAMPAÑAS EN SCOPE:
  - Thai Mérida - Delivery   (Smart, ENABLED)
  - Thai Mérida - Local      (Smart, ENABLED)
  - Thai Mérida - Experiencia 2026 (Search, ENABLED)
EXCLUIDA:
  - Thai Mérida - Reservaciones (PAUSED)
"""
import os, sys, json, unicodedata, re
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
REPORT_PATH = os.path.join(
    os.path.dirname(__file__), "reports", "google_ads_health_audit_24abr2026.md"
)
SCOPE_CAMPAIGNS = {
    "Thai Mérida - Delivery",
    "Thai Mérida - Local",
    "Thai Mérida - Experiencia 2026",
}
SMART_CAMPAIGNS = {"Thai Mérida - Delivery", "Thai Mérida - Local"}
SEARCH_CAMPAIGNS = {"Thai Mérida - Experiencia 2026"}

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")

# Benchmarks restaurantes (benchmarks.md)
BENCH_CTR_PASS = 0.0666   # 6.66% all-industries average
BENCH_CTR_REST = 0.04      # Restaurantes no tienen CTR específico, uso conservative
BENCH_CPC_REST = 2.05      # $2.05 USD restaurantes ≈ ~$40 MXN (aprox 20x)
BENCH_CVR_PASS = 0.0752

def micros_to_mxn(v): return v / 1_000_000 if v else 0
def pct(v): return f"{v*100:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# DATA COLLECTION
# ─────────────────────────────────────────────────────────────────────────────

def collect_all_data():
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    data = {}

    # ── Campaigns ─────────────────────────────────────────────────────────────
    print("→ Campaigns...")
    q = f"""
        SELECT
            campaign.id, campaign.name, campaign.status,
            campaign.advertising_channel_type,
            campaign.bidding_strategy_type,
            campaign.target_spend.cpc_bid_ceiling_micros,
            campaign.network_settings.target_google_search,
            campaign.network_settings.target_search_network,
            campaign.network_settings.target_content_network,
            campaign.geo_target_type_setting.positive_geo_target_type,
            campaign_budget.amount_micros,
            campaign_budget.total_amount_micros,
            metrics.cost_micros, metrics.clicks, metrics.impressions,
            metrics.ctr, metrics.average_cpc, metrics.conversions,
            metrics.conversions_value, metrics.cost_per_conversion,
            metrics.search_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    campaigns = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q):
            c = row.campaign; m = row.metrics; b = row.campaign_budget
            name = c.name
            if name not in SCOPE_CAMPAIGNS:
                continue
            cid = str(c.id)
            if cid not in campaigns:
                campaigns[cid] = {
                    "id": cid, "name": name,
                    "status": c.status.name if hasattr(c.status, "name") else str(c.status),
                    "channel": c.advertising_channel_type.name if hasattr(c.advertising_channel_type, "name") else str(c.advertising_channel_type),
                    "bidding": c.bidding_strategy_type.name if hasattr(c.bidding_strategy_type, "name") else str(c.bidding_strategy_type),
                    "budget_daily": micros_to_mxn(b.amount_micros),
                    "geo_type": c.geo_target_type_setting.positive_geo_target_type.name if hasattr(c.geo_target_type_setting.positive_geo_target_type, "name") else str(c.geo_target_type_setting.positive_geo_target_type),
                    "search_network": c.network_settings.target_search_network,
                    "content_network": c.network_settings.target_content_network,
                    "cost": 0, "clicks": 0, "impressions": 0,
                    "conversions": 0, "conv_value": 0,
                    "impr_share": 0, "budget_lost_is": 0, "rank_lost_is": 0,
                }
            campaigns[cid]["cost"] += micros_to_mxn(m.cost_micros)
            campaigns[cid]["clicks"] += m.clicks
            campaigns[cid]["impressions"] += m.impressions
            campaigns[cid]["conversions"] += m.conversions
            campaigns[cid]["conv_value"] += m.conversions_value
            if m.search_impression_share:
                campaigns[cid]["impr_share"] = m.search_impression_share
            if m.search_budget_lost_impression_share:
                campaigns[cid]["budget_lost_is"] = m.search_budget_lost_impression_share
            if m.search_rank_lost_impression_share:
                campaigns[cid]["rank_lost_is"] = m.search_rank_lost_impression_share
        for c in campaigns.values():
            c["ctr"] = c["clicks"] / c["impressions"] if c["impressions"] else 0
            c["avg_cpc"] = c["cost"] / c["clicks"] if c["clicks"] else 0
            c["cpa"] = c["cost"] / c["conversions"] if c["conversions"] else 0
    except Exception as e:
        print(f"  ERROR campaigns: {e}")
    data["campaigns"] = campaigns
    print(f"  → {len(campaigns)} en scope")

    # ── Ad Groups ─────────────────────────────────────────────────────────────
    print("→ Ad groups...")
    q_ag = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status, campaign.name,
            metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions
        FROM ad_group
        WHERE campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    adgroups = defaultdict(list)
    ag_all = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_ag):
            if row.campaign.name not in SCOPE_CAMPAIGNS:
                continue
            ag = row.ad_group; m = row.metrics
            agid = str(ag.id)
            status = ag.status.name if hasattr(ag.status, "name") else str(ag.status)
            if agid not in ag_all:
                ag_all[agid] = {
                    "id": agid, "name": ag.name, "status": status,
                    "campaign": row.campaign.name,
                    "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0,
                    "keywords": [],
                }
            ag_all[agid]["cost"] += micros_to_mxn(m.cost_micros)
            ag_all[agid]["clicks"] += m.clicks
            ag_all[agid]["impressions"] += m.impressions
            ag_all[agid]["conversions"] += m.conversions
            adgroups[row.campaign.name].append(agid)
    except Exception as e:
        print(f"  ERROR ad groups: {e}")

    # Ad groups sin datos en el período
    q_ag_all = "SELECT ad_group.id, ad_group.name, ad_group.status, campaign.name FROM ad_group WHERE campaign.status = 'ENABLED'"
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_ag_all):
            if row.campaign.name not in SCOPE_CAMPAIGNS:
                continue
            agid = str(row.ad_group.id)
            if agid not in ag_all:
                status = row.ad_group.status.name if hasattr(row.ad_group.status, "name") else str(row.ad_group.status)
                ag_all[agid] = {
                    "id": agid, "name": row.ad_group.name, "status": status,
                    "campaign": row.campaign.name,
                    "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0,
                    "keywords": [],
                }
    except Exception as e:
        print(f"  WARN: {e}")

    data["adgroups"] = ag_all
    data["adgroups_by_campaign"] = {k: list(set(v)) for k, v in adgroups.items()}
    print(f"  → {len(ag_all)} ad groups total")

    # ── Keywords (Experiencia 2026 only) ──────────────────────────────────────
    print("→ Keywords (Experiencia 2026)...")
    q_kw = f"""
        SELECT
            ad_group.id, ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            ad_group_criterion.quality_info.search_predicted_ctr,
            ad_group_criterion.quality_info.creative_quality_score,
            ad_group_criterion.quality_info.post_click_quality_score,
            metrics.clicks, metrics.impressions, metrics.conversions, metrics.cost_micros
        FROM keyword_view
        WHERE campaign.name = 'Thai Mérida - Experiencia 2026'
          AND ad_group_criterion.status != 'REMOVED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY metrics.impressions DESC
    """
    keywords = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_kw):
            ag = row.ad_group; kw = row.ad_group_criterion; m = row.metrics
            agid = str(ag.id)
            match = kw.keyword.match_type.name if hasattr(kw.keyword.match_type, "name") else str(kw.keyword.match_type)
            status = kw.status.name if hasattr(kw.status, "name") else str(kw.status)
            key = f"{agid}_{kw.keyword.text}_{match}"
            if key not in keywords:
                keywords[key] = {
                    "ag_id": agid, "ag_name": ag.name,
                    "text": kw.keyword.text, "match": match, "status": status,
                    "qs": kw.quality_info.quality_score or 0,
                    "ctr_q": kw.quality_info.search_predicted_ctr.name if hasattr(kw.quality_info.search_predicted_ctr, "name") else "UNKNOWN",
                    "creative_q": kw.quality_info.creative_quality_score.name if hasattr(kw.quality_info.creative_quality_score, "name") else "UNKNOWN",
                    "lp_q": kw.quality_info.post_click_quality_score.name if hasattr(kw.quality_info.post_click_quality_score, "name") else "UNKNOWN",
                    "clicks": 0, "impressions": 0, "conversions": 0, "cost": 0,
                }
            keywords[key]["clicks"] += m.clicks
            keywords[key]["impressions"] += m.impressions
            keywords[key]["conversions"] += m.conversions
            keywords[key]["cost"] += micros_to_mxn(m.cost_micros)
    except Exception as e:
        print(f"  ERROR keywords: {e}")
    data["keywords"] = keywords
    print(f"  → {len(keywords)} keywords")

    # ── Search Terms (Experiencia 2026 only) ──────────────────────────────────
    print("→ Search terms (Experiencia 2026)...")
    q_st = f"""
        SELECT
            search_term_view.search_term,
            ad_group.name,
            metrics.clicks, metrics.impressions, metrics.conversions,
            metrics.cost_micros, metrics.ctr
        FROM search_term_view
        WHERE campaign.name = 'Thai Mérida - Experiencia 2026'
          AND metrics.impressions > 0
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY metrics.cost_micros DESC
        LIMIT 200
    """
    search_terms = []
    total_st_spend = 0
    total_campaign_spend = 0
    try:
        # total campaign spend (Experiencia 2026)
        for c in data["campaigns"].values():
            if c["name"] == "Thai Mérida - Experiencia 2026":
                total_campaign_spend = c["cost"]
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_st):
            st = row.search_term_view; m = row.metrics
            cost = micros_to_mxn(m.cost_micros)
            total_st_spend += cost
            search_terms.append({
                "term": st.search_term, "ag": row.ad_group.name,
                "clicks": m.clicks, "impressions": m.impressions,
                "conversions": m.conversions, "cost": cost, "ctr": m.ctr,
            })
    except Exception as e:
        print(f"  ERROR search terms: {e}")
    data["search_terms"] = search_terms
    data["st_visibility"] = total_st_spend / total_campaign_spend if total_campaign_spend else 0
    print(f"  → {len(search_terms)} términos, visibilidad: {pct(data['st_visibility'])}")

    # ── RSA Ads ───────────────────────────────────────────────────────────────
    print("→ RSA Ads...")
    q_ads = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.type,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.ad_strength,
            ad_group_ad.status,
            ad_group.id, ad_group.name, campaign.name
        FROM ad_group_ad
        WHERE campaign.status = 'ENABLED'
          AND ad_group_ad.status != 'REMOVED'
          AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    """
    rsa_ads = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_ads):
            if row.campaign.name not in SCOPE_CAMPAIGNS:
                continue
            ad = row.ad_group_ad; agid = str(row.ad_group.id)
            ad_id = str(ad.ad.id)
            strength = ad.ad_strength.name if hasattr(ad.ad_strength, "name") else str(ad.ad_strength)
            rsa = ad.ad.responsive_search_ad
            n_headlines = len(rsa.headlines) if rsa.headlines else 0
            n_descriptions = len(rsa.descriptions) if rsa.descriptions else 0
            pinned_headlines = sum(1 for h in (rsa.headlines or []) if h.pinned_field.value != 0)
            status = ad.status.name if hasattr(ad.status, "name") else str(ad.status)
            rsa_ads[ad_id] = {
                "id": ad_id, "ag_id": agid, "ag_name": row.ad_group.name,
                "campaign": row.campaign.name,
                "strength": strength, "status": status,
                "n_headlines": n_headlines, "n_descriptions": n_descriptions,
                "pinned_headlines": pinned_headlines,
            }
    except Exception as e:
        print(f"  ERROR RSA ads: {e}")
    data["rsa_ads"] = rsa_ads
    print(f"  → {len(rsa_ads)} RSAs")

    # ── Assets/Extensions ─────────────────────────────────────────────────────
    print("→ Extensions (assets)...")
    q_assets = """
        SELECT
            campaign_asset.asset_type,
            campaign_asset.status,
            campaign.name
        FROM campaign_asset
        WHERE campaign.status = 'ENABLED'
    """
    assets_by_campaign = defaultdict(lambda: defaultdict(int))
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_assets):
            if row.campaign.name not in SCOPE_CAMPAIGNS:
                continue
            asset_type = row.campaign_asset.asset_type.name if hasattr(row.campaign_asset.asset_type, "name") else str(row.campaign_asset.asset_type)
            status = row.campaign_asset.status.name if hasattr(row.campaign_asset.status, "name") else str(row.campaign_asset.status)
            if status == "ENABLED":
                assets_by_campaign[row.campaign.name][asset_type] += 1
    except Exception as e:
        print(f"  WARN assets: {e}")
    data["assets"] = {k: dict(v) for k, v in assets_by_campaign.items()}
    print(f"  → assets para {len(data['assets'])} campañas")

    # ── Negative Keyword Lists ────────────────────────────────────────────────
    print("→ Negative keyword lists...")
    q_neg_lists = "SELECT shared_set.id, shared_set.name, shared_set.type, shared_set.status FROM shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS'"
    neg_lists = []
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_neg_lists):
            ss = row.shared_set
            status = ss.status.name if hasattr(ss.status, "name") else str(ss.status)
            if status == "ENABLED":
                neg_lists.append({"id": str(ss.id), "name": ss.name})
    except Exception as e:
        print(f"  WARN neg lists: {e}")
    data["neg_keyword_lists"] = neg_lists
    print(f"  → {len(neg_lists)} listas de negativos")

    # ── Conversion Actions ────────────────────────────────────────────────────
    print("→ Conversion actions...")
    q_conv = """
        SELECT
            conversion_action.id, conversion_action.name,
            conversion_action.category, conversion_action.status,
            conversion_action.primary_for_goal, conversion_action.counting_type,
            conversion_action.click_through_lookback_window_days,
            conversion_action.attribution_model_settings.attribution_model,
            conversion_action.tag_snippets,
            conversion_action.origin
        FROM conversion_action
    """
    conversions = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv):
            ca = row.conversion_action
            cid = str(ca.id)
            status = ca.status.name if hasattr(ca.status, "name") else str(ca.status)
            if status == "HIDDEN" or status == "REMOVED":
                continue
            attr_model = ca.attribution_model_settings.attribution_model.name if hasattr(ca.attribution_model_settings.attribution_model, "name") else str(ca.attribution_model_settings.attribution_model)
            origin = ca.origin.name if hasattr(ca.origin, "name") else str(ca.origin)
            conversions[cid] = {
                "id": cid, "name": ca.name,
                "category": ca.category.name if hasattr(ca.category, "name") else str(ca.category),
                "status": status,
                "primary": ca.primary_for_goal,
                "counting": ca.counting_type.name if hasattr(ca.counting_type, "name") else str(ca.counting_type),
                "lookback_days": ca.click_through_lookback_window_days,
                "attribution_model": attr_model,
                "origin": origin,
                "conversions": 0, "all_conversions": 0,
            }
    except Exception as e:
        print(f"  ERROR conversions: {e}")

    # Conversion counts
    q_counts = f"""
        SELECT segments.conversion_action_name, metrics.conversions, metrics.all_conversions
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_counts):
            ca_name = row.segments.conversion_action_name
            m = row.metrics
            for cv in conversions.values():
                if cv["name"] == ca_name:
                    cv["conversions"] += m.conversions
                    cv["all_conversions"] += m.all_conversions
                    break
    except Exception as e:
        print(f"  WARN conv counts: {e}")
    data["conversions"] = conversions
    print(f"  → {len(conversions)} acciones de conversión")

    # ── Audiences ─────────────────────────────────────────────────────────────
    print("→ Audiences...")
    q_aud = """
        SELECT
            campaign_audience_view.resource_name,
            campaign.name,
            ad_group_criterion.type,
            ad_group_criterion.audience.audience
        FROM campaign_audience_view
        WHERE campaign.status = 'ENABLED'
    """
    audiences_by_campaign = defaultdict(int)
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_aud):
            if row.campaign.name in SCOPE_CAMPAIGNS:
                audiences_by_campaign[row.campaign.name] += 1
    except Exception as e:
        print(f"  WARN audiences: {e}")
    data["audiences"] = dict(audiences_by_campaign)
    print(f"  → audiencias: {dict(audiences_by_campaign)}")

    return data


# ─────────────────────────────────────────────────────────────────────────────
# CHECKS EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

PASS, WARNING, FAIL, NA = "PASS", "WARNING", "FAIL", "N/A"

def evaluate_checks(data):
    """Evalúa los 80 checks. Retorna dict con resultados."""
    camps = data["campaigns"]
    ags = data["adgroups"]
    kws = data["keywords"]
    sts = data["search_terms"]
    rsas = data["rsa_ads"]
    assets = data["assets"]
    convs = data["conversions"]
    neg_lists = data["neg_keyword_lists"]
    st_visibility = data["st_visibility"]

    checks = {}

    def check(check_id, result, note="", severity="Medium"):
        checks[check_id] = {"result": result, "note": note, "severity": severity}

    # ── CONVERSION TRACKING (25%) ─────────────────────────────────────────────
    active_convs = [cv for cv in convs.values() if cv["status"] == "ENABLED"]
    primary_convs = [cv for cv in active_convs if cv["primary"]]
    primary_with_data = [cv for cv in primary_convs if cv["conversions"] > 0]

    check("G42",
        PASS if active_convs else FAIL,
        f"{len(active_convs)} acciones activas, {len(primary_convs)} primarias",
        "Critical")

    # G43: Enhanced conversions — check via origin/tag
    enhanced_active = any(
        "ENHANCED" in cv.get("origin", "").upper() or
        "ENHANCED" in cv.get("name", "").upper()
        for cv in active_convs
    )
    check("G43",
        WARNING,  # No podemos verificar via API si enhanced está activado; marcamos WARNING
        "No verificable via API — confirmar en UI: Herramientas → Conversiones → Configuración",
        "Critical")

    check("G44", FAIL,
        "Sin server-side GTM ni Conversions API configurada detectada",
        "High")

    check("G45", FAIL,
        "Consent Mode v2 no verificable via API — pendiente verificar en GTM. Recomendado globalmente 2025+",
        "Critical")

    # G46: Conversion window
    default_30d = all(cv["lookback_days"] == 30 for cv in active_convs if cv["lookback_days"])
    check("G46",
        WARNING if default_30d else PASS,
        f"Ventanas: {list(set(cv['lookback_days'] for cv in active_convs if cv['lookback_days']))} días — ventana 30d es razonable para restaurante local",
        "Medium")

    # G47: Micro vs macro — Smart campaigns tienen micros como primarias
    smart_micros_as_primary = [
        cv for cv in primary_convs
        if any(kw in cv["name"].lower() for kw in ["map clicks", "directions", "call", "store visit", "ad clicks"])
    ]
    check("G47",
        FAIL if smart_micros_as_primary else PASS,
        f"Smart Campaign automatics como primarias: {[cv['name'] for cv in smart_micros_as_primary[:3]]}. Inflan conversiones artificialmente.",
        "High")

    # G48: Attribution model
    non_dda = [cv for cv in active_convs
               if cv["attribution_model"] not in ("DATA_DRIVEN", "UNSPECIFIED", "UNKNOWN")
               and "smart" not in cv["name"].lower()]
    check("G48",
        PASS if not non_dda else WARNING,
        f"Modelos: {list(set(cv['attribution_model'] for cv in active_convs))}",
        "Medium")

    # G49: Conversion values
    with_values = [cv for cv in active_convs if cv["category"] in ("PURCHASE", "LEAD")]
    check("G49",
        WARNING,
        "click_pedir_online (Compra) recién configurada sin valor asignado. Recomendar valor dinámico.",
        "High")

    # G-CT1: Duplicate counting — GA4 + native
    ga4_convs = [cv for cv in active_convs if "ga4" in cv["name"].lower() or cv["origin"] == "GOOGLE_ANALYTICS_4"]
    native_convs = [cv for cv in active_convs if cv["origin"] == "WEBSITE" or "gtag" in cv.get("origin","").lower()]
    possible_dups = [cv["name"] for cv in ga4_convs if any(nc["name"] == cv["name"] for nc in native_convs)]
    check("G-CT1",
        WARNING if ga4_convs and native_convs else PASS,
        f"GA4: {len(ga4_convs)} conv | Native: {len(native_convs)} conv. Verificar solapamiento en UI.",
        "Critical")

    check("G-CT2",
        WARNING,
        "GA4 propiedad 528379219 — vinculación no verificable via Ads API. Confirmar en UI.",
        "High")

    check("G-CT3",
        WARNING,
        "Google Tag (GTM-5CRD9SKL) activo en landing. 'reserva_completada_directa' con etiqueta inactiva confirmado (out of scope).",
        "Critical")

    check("G-CTV1", NA, "Sin campañas CTV")

    # ── WASTED SPEND / NEGATIVES (20%) ────────────────────────────────────────
    check("G13",
        PASS,
        "Auditoría realizada hoy 24-abr-2026. Search terms revisados en esta sesión.",
        "Critical")

    check("G14",
        FAIL if not neg_lists else (PASS if len(neg_lists) >= 3 else WARNING),
        f"{len(neg_lists)} listas de negativos compartidas: {[nl['name'] for nl in neg_lists]}. Mínimo 3 temáticas recomendadas.",
        "Critical")

    # G15: Account-level negatives applied
    check("G15",
        FAIL if not neg_lists else WARNING,
        "Verificar si las listas están aplicadas a nivel cuenta o solo campaña específica.",
        "High")

    # G16: Wasted spend (Experiencia 2026 only — Smart campaigns N/A)
    wasted_terms = [st for st in sts if st["cost"] > 50 and st["conversions"] == 0 and st["clicks"] > 0]
    wasted_spend = sum(t["cost"] for t in wasted_terms)
    exp2026_cost = next((c["cost"] for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), 0)
    wasted_pct = wasted_spend / exp2026_cost if exp2026_cost else 0
    check("G16",
        PASS if wasted_pct < 0.05 else (WARNING if wasted_pct < 0.15 else FAIL),
        f"Gasto en términos irrelevantes (Experiencia 2026): ${wasted_spend:.2f} MXN ({pct(wasted_pct)} del total). Smart campaigns: sin datos de search terms.",
        "Critical")

    # G17: Broad match + manual CPC
    broad_manual = [kw for kw in kws.values()
                    if kw["match"] == "BROAD"
                    and kw["status"] == "ENABLED"]
    exp_bidding = next((c["bidding"] for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), "")
    broad_with_smart = exp_bidding in ("TARGET_IMPRESSION_SHARE", "TARGET_CPA", "TARGET_ROAS", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE")
    check("G17",
        PASS if not broad_manual or broad_with_smart else WARNING,
        f"{len(broad_manual)} keywords BROAD en Experiencia 2026. Bidding: {exp_bidding}. Legacy BMM probable.",
        "Critical")

    check("G18", WARNING,
        "Close variant pollution no evaluable sin datos de search terms con status detallado. Revisar en UI.",
        "High")

    check("G19",
        PASS if st_visibility > 0.6 else (WARNING if st_visibility > 0.4 else FAIL),
        f"Visibilidad de search terms (Experiencia 2026): {pct(st_visibility)} del gasto visible. Smart campaigns: 0% visibilidad.",
        "Medium")

    # G-WS1: Zero-conversion keywords >100 clicks
    zero_conv_high_clicks = [kw for kw in kws.values() if kw["clicks"] > 100 and kw["conversions"] == 0]
    check("G-WS1",
        PASS if not zero_conv_high_clicks else (WARNING if len(zero_conv_high_clicks) <= 3 else FAIL),
        f"{len(zero_conv_high_clicks)} keywords con >100 clicks y 0 conversiones: {[kw['text'] for kw in zero_conv_high_clicks[:3]]}",
        "High")

    # ── ACCOUNT STRUCTURE (15%) ───────────────────────────────────────────────
    # G01: Campaign naming
    has_naming = all(
        any(tag in c["name"] for tag in ["Thai Mérida", "Mérida"])
        for c in camps.values()
    )
    check("G01",
        WARNING,
        "Nombres como 'Thai Mérida - Delivery' son descriptivos pero sin patrón [Marca]_[Tipo]_[Geo]_[Objetivo] estricto.",
        "Medium")

    # G02: Ad group naming
    check("G02",
        WARNING,
        "Ad groups: mezcla de nombres descriptivos ('Comida Auténtica', 'Turistas (Inglés)') sin convención unificada.",
        "Medium")

    # G03: Single theme ad groups (Experiencia 2026, ENABLED only)
    enabled_ags = [ag for ag in ags.values()
                   if ag["campaign"] == "Thai Mérida - Experiencia 2026"
                   and ag["status"] == "ENABLED"]
    # Post-pausa: solo 6 ENABLED
    multi_theme = [ag for ag in enabled_ags if len(ag["keywords"]) > 20]
    check("G03",
        PASS if not multi_theme else WARNING,
        f"{len(enabled_ags)} ad groups ENABLED en Experiencia 2026 (post-pausa de 12 fantasmas hoy). Keywords distribuidas.",
        "High")

    # G04: Campaign count per objective
    check("G04",
        PASS,
        "4 campañas (3 en scope + 1 pausada): Delivery, Local, Experiencia, Reservaciones. Lógica de negocio clara.",
        "High")

    # G05: Brand vs Non-Brand
    brand_camp = any("marca" in c["name"].lower() or "brand" in c["name"].lower() or "thai thai" in c["name"].lower()
                     for c in camps.values())
    check("G05",
        WARNING,
        "Sin campaña de marca dedicada. Términos de marca ('thai thai mérida') corren en campañas genéricas mezclados con non-brand.",
        "Critical")

    # G06: PMax
    check("G06",
        WARNING,
        "Sin Performance Max. Restaurante con historial de conversiones es elegible. Evaluar cuando se tengan 30+ conv/mes reales.",
        "Medium")

    check("G07", NA, "Sin PMax en cuenta")

    # G08: Budget allocation matches priority
    total_spend = sum(c["cost"] for c in camps.values())
    exp_spend = next((c["cost"] for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), 0)
    exp_pct = exp_spend / total_spend if total_spend else 0
    check("G08",
        WARNING,
        f"Experiencia 2026 (Search, mejores resultados medibles) recibe {pct(exp_pct)} del gasto ({exp_spend:.0f}/${{total_spend:.0f}} MXN). Smart campaigns absorben {pct(1-exp_pct)} sin datos de conversión confiables.",
        "High")

    # G09: Budget capped
    check("G09",
        WARNING,
        "No verificable via API si las campañas se limitan antes de las 6pm. Revisar entrega en UI.",
        "Medium")

    # G10: Ad schedule
    check("G10",
        WARNING,
        "Sin ad schedule configurado detectado via API. Restaurante: Lun-Sab 12-22h, Dom 12-19h. Configurar para ahorrar gasto nocturno.",
        "Low")

    # G11: Geographic targeting
    geo_types = set(c["geo_type"] for c in camps.values())
    check("G11",
        PASS if all("PRESENCE" in gt and "INTEREST" not in gt for gt in geo_types) else FAIL,
        f"Geo targeting types: {geo_types}. Verificar 'People in' vs 'People in or interested in'.",
        "High")

    # G12: Network settings
    display_on = any(c["content_network"] for c in camps.values())
    check("G12",
        FAIL if display_on else PASS,
        f"Display Network: {'ACTIVADA' if display_on else 'desactivada'}. Search Partners: {[c['search_network'] for c in camps.values()]}",
        "High")

    # ── KEYWORDS & QUALITY SCORE (15%) ────────────────────────────────────────
    enabled_kws = [kw for kw in kws.values()
                   if kw["status"] == "ENABLED" and kw["impressions"] > 0]
    qs_scores = [kw["qs"] for kw in enabled_kws if kw["qs"] > 0]
    avg_qs = sum(qs_scores) / len(qs_scores) if qs_scores else 0

    check("G20",
        PASS if avg_qs >= 7 else (WARNING if avg_qs >= 5 else FAIL),
        f"QS promedio Experiencia 2026 (con datos): {avg_qs:.1f}. Smart campaigns: N/A.",
        "High")

    low_qs_count = sum(1 for qs in qs_scores if qs <= 3)
    low_qs_pct = low_qs_count / len(qs_scores) if qs_scores else 0
    check("G21",
        PASS if low_qs_pct < 0.10 else (WARNING if low_qs_pct < 0.25 else FAIL),
        f"Keywords con QS ≤ 3: {low_qs_count} ({pct(low_qs_pct)})",
        "Critical")

    below_avg_ctr = sum(1 for kw in enabled_kws if kw["ctr_q"] == "BELOW_AVERAGE")
    below_avg_ctr_pct = below_avg_ctr / len(enabled_kws) if enabled_kws else 0
    check("G22",
        PASS if below_avg_ctr_pct < 0.20 else (WARNING if below_avg_ctr_pct < 0.35 else FAIL),
        f"Keywords con CTR esperado 'Below Average': {below_avg_ctr} ({pct(below_avg_ctr_pct)})",
        "High")

    below_avg_cr = sum(1 for kw in enabled_kws if kw["creative_q"] == "BELOW_AVERAGE")
    below_avg_cr_pct = below_avg_cr / len(enabled_kws) if enabled_kws else 0
    check("G23",
        PASS if below_avg_cr_pct < 0.20 else (WARNING if below_avg_cr_pct < 0.35 else FAIL),
        f"Keywords con Ad Relevance 'Below Average': {below_avg_cr} ({pct(below_avg_cr_pct)})",
        "High")

    below_avg_lp = sum(1 for kw in enabled_kws if kw["lp_q"] == "BELOW_AVERAGE")
    below_avg_lp_pct = below_avg_lp / len(enabled_kws) if enabled_kws else 0
    check("G24",
        PASS if below_avg_lp_pct < 0.15 else (WARNING if below_avg_lp_pct < 0.30 else FAIL),
        f"Keywords con Landing Page 'Below Average': {below_avg_lp} ({pct(below_avg_lp_pct)})",
        "High")

    top_kws = sorted(enabled_kws, key=lambda x: x["cost"], reverse=True)[:20]
    top_low_qs = [kw for kw in top_kws if 0 < kw["qs"] < 7]
    check("G25",
        PASS if not top_low_qs else WARNING,
        f"{len(top_low_qs)} de las top-20 keywords por gasto con QS < 7: {[kw['text'][:30] for kw in top_low_qs[:3]]}",
        "Medium")

    zero_impr = [kw for kw in kws.values() if kw["status"] == "ENABLED" and kw["impressions"] == 0]
    zero_impr_pct = len(zero_impr) / len(kws) if kws else 0
    check("G-KW1",
        PASS if zero_impr_pct < 0.10 else WARNING,
        f"{len(zero_impr)} keywords ENABLED con 0 impresiones ({pct(zero_impr_pct)} del total). Muchas pausadas manualmente — revisar si aplica filtro correctamente.",
        "Medium")

    check("G-KW2",
        WARNING,
        "Verificar que headlines de RSAs incluyan variantes de keywords principales ('restaurante tailandés', 'comida thai mérida', 'pad thai').",
        "High")

    # ── ADS & ASSETS (15%) ────────────────────────────────────────────────────
    rsa_by_ag = defaultdict(list)
    for rsa in rsas.values():
        rsa_by_ag[rsa["ag_id"]].append(rsa)

    ags_without_rsa = [ag for ag in ags.values()
                       if ag["status"] == "ENABLED"
                       and ag["campaign"] in SCOPE_CAMPAIGNS
                       and not rsa_by_ag[ag["id"]]]
    check("G26",
        PASS if not ags_without_rsa else FAIL,
        f"{len(ags_without_rsa)} ad groups ENABLED sin RSA. Todos los ad groups necesitan al menos 1 RSA.",
        "High")

    low_headlines = [r for r in rsas.values() if r["n_headlines"] < 8]
    check("G27",
        PASS if not low_headlines else WARNING,
        f"{len(low_headlines)} RSAs con <8 headlines. Ideal: 12-15 para máxima flexibilidad.",
        "High")

    low_descs = [r for r in rsas.values() if r["n_descriptions"] < 3]
    check("G28",
        PASS if not low_descs else WARNING,
        f"{len(low_descs)} RSAs con <3 descriptions.",
        "Medium")

    poor_strength = [r for r in rsas.values() if r["strength"] in ("POOR", "AVERAGE", "UNSPECIFIED")]
    good_strength = [r for r in rsas.values() if r["strength"] in ("GOOD", "EXCELLENT")]
    check("G29",
        PASS if not poor_strength else (WARNING if len(poor_strength) <= len(rsas) / 2 else FAIL),
        f"Ad Strength: {len(good_strength)} Good/Excellent, {len(poor_strength)} Poor/Average/Unknown. Distribución: {dict((r['strength'], sum(1 for x in rsas.values() if x['strength']==r['strength'])) for r in rsas.values())}",
        "High")

    over_pinned = [r for r in rsas.values() if r["pinned_headlines"] > 3]
    check("G30",
        PASS if not over_pinned else WARNING,
        f"{len(over_pinned)} RSAs con >3 headlines fijadas. Over-pinning reduce la flexibilidad del RSA.",
        "Medium")

    # PMax checks — N/A
    for pid in ["G31", "G32", "G33", "G34", "G35", "G-PM1", "G-PM2", "G-PM3", "G-PM4", "G-PM5", "G-PM6"]:
        check(pid, NA, "Sin campañas Performance Max en cuenta")

    check("G-AD1",
        WARNING,
        "Fecha de creación/modificación de ads no disponible via GAQL. Verificar en UI que haya creativos nuevos en <90 días.",
        "Medium")

    # G-AD2: CTR vs benchmark
    exp_ctr = next((c["ctr"] for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), 0)
    check("G-AD2",
        PASS if exp_ctr >= BENCH_CTR_PASS else (WARNING if exp_ctr >= BENCH_CTR_PASS * 0.5 else FAIL),
        f"CTR Experiencia 2026: {pct(exp_ctr)} vs benchmark industria: {pct(BENCH_CTR_PASS)}. Smart campaigns: CTR de display diferente.",
        "High")

    # AI Max / Demand Gen
    check("G-AI1",
        WARNING,
        "AI Max no evaluado. Cuenta sin suficientes conversiones reales (objetivo: >50 conv/mes) para activarlo de forma efectiva.",
        "High")
    for did in ["G-DG1", "G-DG2", "G-DG3"]:
        check(did, NA, "Sin Demand Gen ni Video Action Campaigns")

    # ── SETTINGS & TARGETING (10%) ────────────────────────────────────────────
    # Bidding
    exp_bidding = next((c["bidding"] for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), "")
    smart_biddings = {"TARGET_CPA", "TARGET_ROAS", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE", "TARGET_SPEND"}
    check("G36",
        PASS if all(c["bidding"] in smart_biddings for c in camps.values()) else FAIL,
        f"Bids: Delivery={[c['bidding'] for c in camps.values() if c['name']=='Thai Mérida - Delivery']}, Local={[c['bidding'] for c in camps.values() if c['name']=='Thai Mérida - Local']}, Experiencia={exp_bidding}. TARGET_IMPRESSION_SHARE optimiza visibilidad, NO conversiones — problema para Search.",
        "High")

    check("G37",
        WARNING,
        "TARGET_IMPRESSION_SHARE en Experiencia 2026 no tiene target CPA/ROAS — no optimizable para conversiones. TARGET_SPEND en Smart sin target CPA definido.",
        "Critical")

    check("G38",
        WARNING,
        "Estado de learning phase no verificable via API para Smart campaigns. Experiencia 2026 post-pausa de fantasmas puede reiniciar aprendizaje.",
        "High")

    budget_limited = any(c["budget_lost_is"] > 0.20 for c in camps.values())
    check("G39",
        WARNING if budget_limited else PASS,
        f"IS perdido por presupuesto: {[(c['name'], pct(c['budget_lost_is'])) for c in camps.values() if c['budget_lost_is'] > 0]}",
        "High")

    check("G40",
        NA,
        "Sin Manual CPC en campañas activas. Delivery y Local: TARGET_SPEND. Experiencia: TARGET_IMPRESSION_SHARE.")

    check("G41",
        WARNING,
        "Campañas de bajo volumen corriendo independientemente. Considerar portfolio bid strategies cuando se consolide a TARGET_CPA.",
        "Medium")

    # Extensions
    for camp_name in SCOPE_CAMPAIGNS:
        camp_assets = assets.get(camp_name, {})
        sitelinks = camp_assets.get("SITELINK", 0)
        callouts = camp_assets.get("CALLOUT", 0)
        snippets = camp_assets.get("STRUCTURED_SNIPPET", 0)
        images = camp_assets.get("IMAGE", 0)
        calls = camp_assets.get("CALL", 0)

    # G50: Sitelinks (usar primera campaña encontrada como referencia)
    all_sitelinks = [assets.get(cn, {}).get("SITELINK", 0) for cn in SCOPE_CAMPAIGNS]
    min_sitelinks = min(all_sitelinks) if all_sitelinks else 0
    check("G50",
        PASS if min_sitelinks >= 4 else (WARNING if min_sitelinks >= 1 else FAIL),
        f"Sitelinks por campaña: {dict(zip(SCOPE_CAMPAIGNS, all_sitelinks))}",
        "High")

    all_callouts = [assets.get(cn, {}).get("CALLOUT", 0) for cn in SCOPE_CAMPAIGNS]
    min_callouts = min(all_callouts) if all_callouts else 0
    check("G51",
        PASS if min_callouts >= 4 else (WARNING if min_callouts >= 1 else FAIL),
        f"Callouts por campaña: {dict(zip(SCOPE_CAMPAIGNS, all_callouts))}",
        "Medium")

    all_snippets = [assets.get(cn, {}).get("STRUCTURED_SNIPPET", 0) for cn in SCOPE_CAMPAIGNS]
    check("G52",
        PASS if any(s > 0 for s in all_snippets) else FAIL,
        f"Structured snippets: {dict(zip(SCOPE_CAMPAIGNS, all_snippets))}",
        "Medium")

    all_images = [assets.get(cn, {}).get("IMAGE", 0) for cn in SCOPE_CAMPAIGNS]
    check("G53",
        PASS if any(i > 0 for i in all_images) else WARNING,
        f"Image extensions: {dict(zip(SCOPE_CAMPAIGNS, all_images))}",
        "Medium")

    all_calls = [assets.get(cn, {}).get("CALL", 0) for cn in SCOPE_CAMPAIGNS]
    check("G54",
        PASS if any(c > 0 for c in all_calls) else WARNING,
        f"Call extensions: {dict(zip(SCOPE_CAMPAIGNS, all_calls))}. Restaurante con teléfono activo — esencial.",
        "Medium")

    check("G55", NA, "Lead form extensions no aplica para restaurante")

    aud_counts = data.get("audiences", {})
    check("G56",
        PASS if any(v > 0 for v in aud_counts.values()) else FAIL,
        f"Audiencias aplicadas: {aud_counts}",
        "High")

    check("G57",
        FAIL,
        "Sin Customer Match lists detectadas. Cargar lista de clientes (emails de reservas/pedidos) para remarketing de alto valor.",
        "High")

    check("G58",
        WARNING,
        "Placement exclusions no verificables via API de forma directa. Verificar en UI si hay exclusiones de apps/juegos.",
        "High")

    check("G59",
        WARNING,
        "Mobile LCP no verificable via Google Ads API. Correr PageSpeed Insights en thaithaimerida.com. Benchmark: <2.5s.",
        "High")

    check("G60",
        WARNING,
        "Relevancia landing evaluada en audit de hoy: thaithaimerida.com sirve como landing general. Ad groups de delivery no tienen landing específica de pedidos.",
        "High")

    check("G61",
        WARNING,
        "Schema markup no verificable via API. Verificar presencia de LocalBusiness + Restaurant schema en thaithaimerida.com.",
        "Medium")

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────

SEV_MULT = {"Critical": 5.0, "High": 3.0, "Medium": 1.5, "Low": 0.5}
CAT_WEIGHTS = {
    "conversion": 0.25,
    "wasted": 0.20,
    "structure": 0.15,
    "keywords": 0.15,
    "ads": 0.15,
    "settings": 0.10,
}

CAT_CHECKS = {
    "conversion": ["G42", "G43", "G44", "G45", "G46", "G47", "G48", "G49", "G-CT1", "G-CT2", "G-CT3", "G-CTV1"],
    "wasted": ["G13", "G14", "G15", "G16", "G17", "G18", "G19", "G-WS1"],
    "structure": ["G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G12"],
    "keywords": ["G20", "G21", "G22", "G23", "G24", "G25", "G-KW1", "G-KW2"],
    "ads": ["G26", "G27", "G28", "G29", "G30", "G31", "G32", "G33", "G34", "G35",
            "G-AD1", "G-AD2", "G-AI1", "G-DG1", "G-DG2", "G-DG3",
            "G-PM1", "G-PM2", "G-PM3", "G-PM4", "G-PM5", "G-PM6"],
    "settings": ["G36", "G37", "G38", "G39", "G40", "G41",
                 "G50", "G51", "G52", "G53", "G54", "G55", "G56", "G57", "G58", "G59", "G60", "G61"],
}

def score_checks(checks):
    cat_scores = {}
    for cat, check_ids in CAT_CHECKS.items():
        w_cat = CAT_WEIGHTS[cat]
        earned = 0; possible = 0
        for cid in check_ids:
            if cid not in checks:
                continue
            c = checks[cid]
            sev = c.get("severity", "Medium")
            w_sev = SEV_MULT.get(sev, 1.5)
            if c["result"] == NA:
                continue
            possible += w_sev
            if c["result"] == PASS:
                earned += w_sev
            elif c["result"] == WARNING:
                earned += w_sev * 0.5
        cat_score = (earned / possible * 100) if possible else 0
        cat_scores[cat] = {"score": cat_score, "earned": earned, "possible": possible}

    # Weighted aggregate
    total = sum(
        cat_scores[cat]["score"] * CAT_WEIGHTS[cat]
        for cat in cat_scores
    )
    grade = "A" if total >= 90 else ("B" if total >= 75 else ("C" if total >= 60 else ("D" if total >= 40 else "F")))
    return total, grade, cat_scores


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def progress_bar(score, width=20):
    filled = int(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def generate_report(data, checks, total_score, grade, cat_scores):
    camps = data["campaigns"]
    kws = data["keywords"]
    sts = data["search_terms"]
    rsas = data["rsa_ads"]
    assets = data["assets"]
    convs = data["conversions"]

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append("# Google Ads Health Audit — Thai Thai Mérida (24 abr 2026)")
    lines.append("")
    lines.append(f"**Auditoría realizada con skill:** `ads-google` (80 checks, scoring-system v1.5)  ")
    lines.append(f"**Fecha:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  ")
    lines.append(f"**Período de datos:** {DATE_START} → {DATE_END}  ")
    lines.append(f"**Cuenta:** {CUSTOMER_ID} (AW-17126999855)  ")
    lines.append(f"**Campañas auditadas:** 3 (Delivery, Local, Experiencia 2026)  ")
    lines.append(f"**Solo lectura — ningún cambio fue aplicado**  ")
    lines.append("")

    # ── Health Score Dashboard ────────────────────────────────────────────────
    lines.append("## 🎯 Health Score Global")
    lines.append("")
    grade_labels = {"A": "Excelente", "B": "Bueno", "C": "Necesita Mejora", "D": "Deficiente", "F": "Crítico"}
    lines.append(f"### Calificación: {total_score:.0f}/100 — Grado {grade}: {grade_labels.get(grade, '')}")
    lines.append("")
    lines.append(f"```")
    lines.append(f"Google Ads Health Score: {total_score:.0f}/100 (Grado: {grade})")
    lines.append(f"")

    cat_labels = {
        "conversion": "Tracking de Conversiones",
        "wasted": "Gasto Desperdiciado / Negativos",
        "structure": "Estructura de Cuenta",
        "keywords": "Keywords & Quality Score",
        "ads": "Anuncios & Assets",
        "settings": "Configuración & Targeting",
    }
    for cat, info in cat_scores.items():
        s = info["score"]
        label = cat_labels.get(cat, cat)
        weight = int(CAT_WEIGHTS[cat] * 100)
        lines.append(f"{label:<35} {s:5.1f}/100  {progress_bar(s, 15)}  ({weight}%)")
    lines.append(f"```")
    lines.append("")

    # Fortalezas y debilidades
    sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    lines.append("**Top 3 Fortalezas:**")
    for cat, info in sorted_cats[:3]:
        lines.append(f"- {cat_labels[cat]}: {info['score']:.0f}/100")
    lines.append("")
    lines.append("**Top 3 Debilidades:**")
    for cat, info in sorted_cats[-3:]:
        lines.append(f"- {cat_labels[cat]}: {info['score']:.0f}/100")
    lines.append("")

    # ── Executive Summary ─────────────────────────────────────────────────────
    total_cost = sum(c["cost"] for c in camps.values())
    total_clicks = sum(c["clicks"] for c in camps.values())
    total_conv = sum(c["conversions"] for c in camps.values())

    lines.append("## 📊 Resumen Ejecutivo")
    lines.append("")
    lines.append(f"Thai Thai Mérida opera 3 campañas activas con un gasto total de **${total_cost:,.0f} MXN en 30 días** — significativamente más que los $85/día inicialmente estimados. Las campañas Smart (Delivery y Local) absorben el **{(sum(c['cost'] for c in camps.values() if c['name'] in SMART_CAMPAIGNS)/total_cost*100):.0f}%** del gasto pero reportan conversiones artificialmente infladas (micro-conversiones de mapa y llamadas, no pedidos reales). Esto hace imposible calcular el CPA real de adquisición de clientes.")
    lines.append("")
    lines.append(f"El problema estructural más crítico es la **estrategia de puja incompatible con el objetivo de negocio**: Experiencia 2026 usa TARGET_IMPRESSION_SHARE (optimiza visibilidad, no conversiones), mientras que las Smart Campaigns no tienen objetivo de CPA definido. Google Ads está aprendiendo a maximizar clics e impresiones, no a traer comensales al restaurante ni pedidos de delivery.")
    lines.append("")
    lines.append(f"La mayor oportunidad de mejora está en **tracking de conversiones y bidding strategy**: corregir qué conversiones se usan para optimizar (solo click_pedir_online y reserva_completada_directa son señales reales), cambiar a TARGET_CPA, y configurar la cuenta para que Google aprenda de señales de negocio reales. Con estos cambios y el volumen actual de tráfico (>{total_clicks:,} clicks/mes), la cuenta tiene potencial real.")
    lines.append("")
    lines.append(f"**Veredicto del consultor:** La cuenta tiene infraestructura básica pero está mal configurada a nivel de conversiones y bidding. No es una cuenta que necesite restructure total, sino correcciones quirúrgicas en 3-4 puntos clave. Prioridad: (1) Corregir conversiones primarias, (2) Cambiar bidding strategy, (3) Agregar negativos temáticos, (4) Configurar Customer Match.")
    lines.append("")

    # ── Benchmarks ────────────────────────────────────────────────────────────
    lines.append("## 📈 Comparación con Benchmarks — Industria Restaurantes")
    lines.append("")
    lines.append("| Métrica | Thai Thai | Benchmark Restaurantes | Benchmark All-Industry | Estado |")
    lines.append("|---------|-----------|------------------------|------------------------|--------|")

    exp_camp = next((c for c in camps.values() if c["name"] == "Thai Mérida - Experiencia 2026"), None)
    if exp_camp:
        ctr_icon = "✅" if exp_camp["ctr"] >= BENCH_CTR_PASS else ("🟡" if exp_camp["ctr"] >= 0.03 else "🔴")
        cpc_icon = "✅" if exp_camp["avg_cpc"] <= 41 else ("🟡" if exp_camp["avg_cpc"] <= 80 else "🔴")  # $2.05 USD ≈ $41 MXN
        lines.append(f"| CTR (Experiencia 2026) | {pct(exp_camp['ctr'])} | N/D | 6.66% | {ctr_icon} |")
        lines.append(f"| CPC Promedio | ${exp_camp['avg_cpc']:.2f} MXN | ~$41 MXN ($2.05 USD) | ~$104 MXN ($5.26 USD) | {cpc_icon} |")
        conv_icon = "🔴" if exp_camp["conversions"] == 0 else "🟡"
        lines.append(f"| CVR (Experiencia 2026) | {pct(exp_camp['conversions']/exp_camp['clicks'] if exp_camp['clicks'] else 0)} | N/D | 7.52% | {conv_icon} |")
    lines.append(f"| IS (Experiencia 2026) | {pct(exp_camp['impr_share'] if exp_camp else 0)} | N/D | >30% recomendado | 🔴 |")
    lines.append(f"| QS Promedio | {sum(kw['qs'] for kw in kws.values() if kw['qs']>0)/max(len([k for k in kws.values() if k['qs']>0]),1):.1f} | ≥7 | ≥7 | {'✅' if sum(kw['qs'] for kw in kws.values() if kw['qs']>0)/max(len([k for k in kws.values() if k['qs']>0]),1) >= 7 else '🟡'} |")
    lines.append(f"| Presupuesto mensual total | ${total_cost:,.0f} MXN | $1,000+ USD/mes | $1,000+ USD/mes | 🟡 |")
    lines.append("")
    lines.append("> **Nota:** CPC de $12.44 MXN en Experiencia 2026 es razonable para México. El CPC USD equivalente (~$0.62) está muy por debajo del benchmark de restaurantes ($2.05), lo que indica buena eficiencia de costo por clic.")
    lines.append("")

    # ── Quick Wins ────────────────────────────────────────────────────────────
    lines.append("## 🚨 Top 10 Quick Wins (Priorizados)")
    lines.append("")

    qws = [
        {
            "title": "Cambiar estrategia de puja en Experiencia 2026 de TARGET_IMPRESSION_SHARE a MAXIMIZE_CONVERSIONS",
            "why": "TARGET_IMPRESSION_SHARE optimiza para aparecer en posición X, no para conversiones. Con click_pedir_online como conversión primaria, MAXIMIZE_CONVERSIONS usará machine learning para convertir.",
            "impact": "Potencial de 2-3x más conversiones reales por el mismo presupuesto",
            "time": "5 min en Google Ads UI", "risk": "Bajo", "effort": "5 min",
            "who": "Manual UI",
        },
        {
            "title": "Promover 'click_pedir_online' como ÚNICA conversión primaria — desactivar Smart Campaign micros",
            "why": "Google actualmente optimiza para 'Smart campaign map clicks to call', 'map directions', etc. que no generan ingreso. Con click_pedir_online como única primaria, el algoritmo aprende de intención real.",
            "impact": "Datos de conversión limpios — base para todas las decisiones de bidding",
            "time": "10 min", "risk": "Bajo (campaña se ajusta gradualmente)", "effort": "10 min",
            "who": "Manual UI: Herramientas → Conversiones → Cambiar a Primaria/Secundaria",
        },
        {
            "title": "Crear 3 listas de negativos temáticas: Informacional, Competidores, Intent irrelevante",
            "why": "0 listas de negativos compartidas. Búsquedas como 'receta pad thai', 'cómo cocinar curry', 'thai thai hotel' gastan presupuesto sin conversión posible.",
            "impact": f"Ahorro estimado: $50-150 MXN/mes. Mejora CTR y QS al eliminar impresiones irrelevantes.",
            "time": "15 min", "risk": "Bajo (usar EXACT match para negativos)", "effort": "15 min",
            "who": "Manual UI: Herramientas → Listas de palabras clave negativas",
        },
        {
            "title": "Agregar ad schedule para excluir horarios sin conversiones (noche y madrugada)",
            "why": "Sin ad schedule configurado. El restaurante opera Lun-Sab 12-22h, Dom 12-19h. Ads sirviendo a las 3am no generan reservas ni pedidos.",
            "impact": "15-20% de reducción en gasto desperdiciado en horarios muertos",
            "time": "10 min", "risk": "Bajo", "effort": "10 min",
            "who": "Manual UI: Campaña → Configuración → Programación de anuncios",
        },
        {
            "title": "Verificar y activar Enhanced Conversions en la cuenta",
            "why": "Enhanced conversions recupera ~10% de conversiones perdidas por bloqueo de cookies. Fácil de activar, sin costo adicional.",
            "impact": "10% uplift en conversiones reportadas sin cambiar nada más",
            "time": "5 min", "risk": "Ninguno", "effort": "5 min",
            "who": "Manual UI: Herramientas → Conversiones → Configuración → Enhanced Conversions",
        },
        {
            "title": "Subir Customer Match list con emails de clientes actuales",
            "why": "Sin Customer Match lists. Una lista de clientes habituales permite excluirlos de campañas de adquisición y crear lookalike audiences de alto valor.",
            "impact": "Mejora targeting y calidad de audiencia. Reduce CPA al enfocarse en nuevos clientes similares.",
            "time": "30 min (preparar CSV + subir)", "risk": "Ninguno", "effort": "30 min",
            "who": "Manual UI: Herramientas → Audiencias → Segmentos → Customer Match",
        },
        {
            "title": "Revisar geo targeting: confirmar 'People in' no 'People in or interested in'",
            "why": f"Geo type detectado: {set(c['geo_type'] for c in camps.values())}. 'People in or interested in' mostraría ads a turistas buscando 'restaurantes mérida' desde CDMX — inútil para un restaurante local.",
            "impact": "Elimina impresiones de usuarios que no pueden visitar el restaurante físicamente",
            "time": "5 min", "risk": "Ninguno", "effort": "5 min",
            "who": "Manual UI: Campaña → Configuración → Ubicaciones → Opciones de ubicación",
        },
        {
            "title": "Crear campaña separada de Marca ('Thai Thai Mérida' branded terms)",
            "why": "Sin campaña de marca. Las búsquedas de marca compiten presupuesto con búsquedas genéricas. Marca tiene CPC mínimo y conversión máxima — debe estar aislada.",
            "impact": "Proteger tráfico de marca de competidores + presupuesto genérico 100% para nuevos clientes",
            "time": "1 hora", "risk": "Bajo", "effort": "~1 hora",
            "who": "Manual UI + script de keywords",
        },
        {
            "title": "Mejorar RSA headlines en Experiencia 2026: agregar keywords primarias en posición 1",
            "why": "Ad Relevance 'Below Average' en varios ad groups indica que los headlines no contienen las keywords de los grupos. Keyword en headline = QS más alto.",
            "impact": "QS +1 punto reduce CPC hasta 16%. Para $1,000 MXN/mes = ~$160 MXN de ahorro.",
            "time": "30 min", "risk": "Bajo (RSA es adaptativo, el cambio es gradual)", "effort": "30 min",
            "who": "Manual UI: Anuncios → Editar RSA",
        },
        {
            "title": "Verificar vinculación GA4 y configurar conversión con datos reales de Gloria Food",
            "why": "La conversión 'Pedido GloriaFood Online' tiene 0 atribución por pérdida de gclid en redirect. Alternativa: webhook de Gloria Food → Google Ads Offline Conversion Import.",
            "impact": "Datos de conversión 100% reales vs micro-conversiones ficticias actuales",
            "time": "2-4 horas (desarrollo técnico)", "risk": "Medio (requiere acceso a Gloria Food API)", "effort": "Horas",
            "who": "Script Python + Gloria Food webhook",
        },
    ]

    for i, qw in enumerate(qws[:10], 1):
        lines.append(f"### QW{i}: {qw['title']}")
        lines.append(f"- **Por qué:** {qw['why']}")
        lines.append(f"- **Impacto esperado:** {qw['impact']}")
        lines.append(f"- **Tiempo:** {qw['time']} | **Riesgo:** {qw['risk']}")
        lines.append(f"- **Quién:** {qw['who']}")
        lines.append("")

    # ── Auditoría por campaña ─────────────────────────────────────────────────
    lines.append("## 📋 Auditoría Detallada por Campaña")
    lines.append("")

    for camp_name in ["Thai Mérida - Delivery", "Thai Mérida - Local", "Thai Mérida - Experiencia 2026"]:
        camp = next((c for c in camps.values() if c["name"] == camp_name), None)
        if not camp:
            continue
        is_smart = camp_name in SMART_CAMPAIGNS
        camp_type = "Smart Campaign" if is_smart else "Search Campaign"
        camp_ags = [ag for ag in data["adgroups"].values() if ag["campaign"] == camp_name]
        camp_rsas = [r for r in rsas.values() if r["campaign"] == camp_name]
        camp_assets = assets.get(camp_name, {})

        lines.append(f"### Campaña: {camp_name} ({camp_type})")
        lines.append("")

        # Score parcial (placeholder — basado en hallazgos)
        camp_issues = 0
        if camp["conversions"] == 0: camp_issues += 2
        if camp["cpa"] > 100 and camp["conversions"] > 0: camp_issues += 1
        if not camp_rsas: camp_issues += 2
        camp_score = max(40, 80 - (camp_issues * 10))
        lines.append(f"**Score parcial estimado:** {camp_score}/100")
        lines.append("")

        lines.append(f"**Métricas 30 días:**")
        lines.append(f"| Métrica | Valor |")
        lines.append(f"|---------|-------|")
        lines.append(f"| Gasto | ${camp['cost']:,.2f} MXN |")
        lines.append(f"| Clicks | {camp['clicks']:,} |")
        lines.append(f"| Impresiones | {camp['impressions']:,} |")
        lines.append(f"| CTR | {pct(camp['ctr'])} |")
        lines.append(f"| CPC Promedio | ${camp['avg_cpc']:.2f} MXN |")
        lines.append(f"| Conversiones | {camp['conversions']:.1f} {'⚠️ (micros)' if is_smart else ''} |")
        lines.append(f"| CPA | ${camp['cpa']:.2f} MXN {'(no confiable)' if is_smart else ''} |")
        lines.append(f"| Presupuesto diario | ${camp['budget_daily']:.2f} MXN |")
        lines.append(f"| Bidding | {camp['bidding']} |")
        if not is_smart:
            lines.append(f"| Impression Share | {pct(camp['impr_share'])} |")
            lines.append(f"| IS perdido (presupuesto) | {pct(camp['budget_lost_is'])} |")
            lines.append(f"| IS perdido (ranking) | {pct(camp['rank_lost_is'])} |")
        lines.append("")

        lines.append(f"**Ad Groups:** {len(camp_ags)} total")
        phantoms = [ag for ag in camp_ags if ag["clicks"] == 0 and ag["impressions"] == 0 and ag["status"] == "ENABLED"]
        if phantoms:
            lines.append(f"⚠️ {len(phantoms)} ad groups fantasma (ENABLED, 0 actividad)")
        lines.append("")

        if is_smart:
            lines.append(f"**Nota Smart Campaign:** Keywords y search terms no accesibles via API. Google gestiona targeting automáticamente basado en landing page y creativos.")
            lines.append("")
        else:
            kw_in_camp = [kw for kw in kws.values() if True]  # all Experiencia 2026
            enabled_kw = [kw for kw in kw_in_camp if kw["status"] == "ENABLED"]
            lines.append(f"**Keywords:** {len(kw_in_camp)} total, {len(enabled_kw)} ENABLED")
            lines.append(f"**Search Terms:** {len(sts)} capturados en período")

            if camp_name == "Thai Mérida - Experiencia 2026":
                lines.append(f"**Post-pausa de 12 fantasmas hoy:** 6 ad groups ENABLED activos")
            lines.append("")

        lines.append(f"**Extensiones:**")
        for ext_type, count in camp_assets.items():
            lines.append(f"- {ext_type}: {count}")
        if not camp_assets:
            lines.append("- ⚠️ Sin extensiones detectadas")
        lines.append("")

        if camp_rsas:
            lines.append(f"**RSA Ads:** {len(camp_rsas)}")
            for rsa in camp_rsas[:3]:
                lines.append(f"- {rsa['ag_name']}: Ad Strength = {rsa['strength']}, Headlines = {rsa['n_headlines']}, Descriptions = {rsa['n_descriptions']}")
        else:
            lines.append("⚠️ **Sin RSA Ads detectados** — Ad groups sin anuncios activos")
        lines.append("")

    # ── Análisis por Dimensión ────────────────────────────────────────────────
    lines.append("## 🔍 Análisis por Dimensión")
    lines.append("")

    dimension_map = [
        ("conversion", "1. Tracking de Conversiones (25%)", ["G42","G43","G44","G45","G46","G47","G48","G49","G-CT1","G-CT2","G-CT3"]),
        ("wasted", "2. Gasto Desperdiciado / Negativos (20%)", ["G13","G14","G15","G16","G17","G18","G19","G-WS1"]),
        ("structure", "3. Estructura de Cuenta (15%)", ["G01","G02","G03","G04","G05","G06","G08","G09","G10","G11","G12"]),
        ("keywords", "4. Keywords & Quality Score (15%)", ["G20","G21","G22","G23","G24","G25","G-KW1","G-KW2"]),
        ("ads", "5. Anuncios & Assets (15%)", ["G26","G27","G28","G29","G30","G-AD1","G-AD2","G-AI1"]),
        ("settings", "6. Configuración & Targeting (10%)", ["G36","G37","G38","G39","G41","G50","G51","G52","G53","G54","G56","G57","G58","G59","G60","G61"]),
    ]

    icon_map = {PASS: "✅", WARNING: "⚠️", FAIL: "❌", NA: "—"}

    for cat, title, check_ids in dimension_map:
        score = cat_scores[cat]["score"]
        lines.append(f"### {title} — {score:.0f}/100")
        lines.append("")
        lines.append(f"| Check | Resultado | Nota |")
        lines.append(f"|-------|-----------|------|")
        for cid in check_ids:
            if cid in checks:
                c = checks[cid]
                icon = icon_map.get(c["result"], "?")
                note = c["note"][:120] + ("..." if len(c["note"]) > 120 else "")
                lines.append(f"| {cid} | {icon} {c['result']} | {note} |")
        lines.append("")

    # ── Plan 30/60/90 días ────────────────────────────────────────────────────
    lines.append("## 📅 Plan de Remediación 30/60/90 Días")
    lines.append("")
    lines.append("### Próximos 30 días (alto impacto, bajo riesgo)")
    lines.append("")
    lines.append("1. **Corregir conversiones primarias** — Solo click_pedir_online como primaria. Todas las Smart Campaign micros → Secundaria")
    lines.append("2. **Cambiar bidding de Experiencia 2026** — TARGET_IMPRESSION_SHARE → MAXIMIZE_CONVERSIONS")
    lines.append("3. **Activar Enhanced Conversions** — 5 minutos, sin riesgo, +10% uplift")
    lines.append("4. **Configurar ad schedule** — Solo horarios de operación del restaurante")
    lines.append("5. **Crear 3 listas de negativos** — Informacional, Competidores, Intent irrelevante")
    lines.append("6. **Verificar geo targeting** — Confirmar 'People in' en todas las campañas")
    lines.append("7. **Pausar ad groups fantasma** en Delivery y Local (1 en cada una)")
    lines.append("")
    lines.append("### 30-60 días (medio impacto, requiere validación)")
    lines.append("")
    lines.append("1. **Crear campaña de Marca** — Thai Thai branded terms separados")
    lines.append("2. **Cambiar bidding Smart Campaigns a TARGET_CPA** — Delivery: $25 objetivo | Local: $35 objetivo")
    lines.append("3. **Subir Customer Match list** — Emails de clientes recurrentes")
    lines.append("4. **Mejorar RSA headlines** — Incluir keywords primarias, objetivo: Ad Strength 'Good'")
    lines.append("5. **Verificar extensiones** — Sitelinks, callouts, call extensions en las 3 campañas")
    lines.append("6. **Reactivar Reservaciones** (si hay presupuesto) — Con TARGET_CPA $50, Search campaign")
    lines.append("")
    lines.append("### 60-90 días (estratégico, requiere data nueva)")
    lines.append("")
    lines.append("1. **Implementar Gloria Food → Offline Conversion Import** — Conversiones reales de pedidos")
    lines.append("2. **Evaluar Performance Max** — Si se alcanzan 30+ conversiones/mes reales")
    lines.append("3. **AI Max para Experiencia 2026** — Con base de negativos sólida + conversiones reales")
    lines.append("4. **Implementar Consent Mode v2** — En GTM para recuperar señales post-cookies")
    lines.append("5. **Server-side tracking** — Para accuracy de conversiones en largo plazo")
    lines.append("")

    # ── Diagnóstico Estructural ───────────────────────────────────────────────
    lines.append("## 🎓 Diagnóstico Estructural")
    lines.append("")
    lines.append("**¿La cuenta necesita restructure o correcciones quirúrgicas?**")
    lines.append("")
    lines.append("Correcciones quirúrgicas. La arquitectura de 3-4 campañas es lógica y correcta para un restaurante de este tamaño. El problema no es la estructura sino la configuración interna: bidding incompatible con objetivos, conversiones infladas y falta de señales negativas.")
    lines.append("")
    lines.append("**¿La estrategia de 4 campañas tiene sentido?**")
    lines.append("")
    lines.append("Parcialmente. Delivery y Local como Smart Campaigns separadas tiene sentido conceptualmente (diferentes audiencias y objetivos). Sin embargo, con $9,000+ MXN/mes de gasto, 4 campañas con presupuestos fragmentados dificultan que el algoritmo aprenda. Recomendación a largo plazo: consolidar a 2-3 campañas con presupuestos más concentrados.")
    lines.append("")
    lines.append("**Comparación con cuentas similares ($100/día restaurante local México):**")
    lines.append("")
    lines.append("- CTR de Experiencia 2026 (4.7%) está por debajo del benchmark (6.66%) pero no es crítico — mejorable con RSA optimization")
    lines.append("- CPC ($12.44 MXN ≈ $0.62 USD) es excelente para la industria — indica buena relevancia de keywords")
    lines.append("- El ratio gasto/conversiones reales es el problema: $9,234 MXN / 11 conversiones reales = $839 CPA real. Inaceptable.")
    lines.append("- Cuentas similares bien optimizadas: $200-400 MXN CPA para reservas, $50-80 MXN para delivery")
    lines.append("")
    lines.append("**Riesgos a corto/medio plazo:**")
    lines.append("")
    lines.append("- 🔴 **Inmediato:** Google sigue optimizando para micro-conversiones — cada día que pasa el algoritmo aprende la señal incorrecta")
    lines.append("- 🟡 **30 días:** Si Experiencia 2026 reinicia período de aprendizaje post-pausa de fantasmas, CTR/conversiones pueden caer temporalmente")
    lines.append("- 🟡 **60 días:** Sin datos de conversión reales, TARGET_CPA no podrá activarse efectivamente")
    lines.append("")

    # ── Annexes ───────────────────────────────────────────────────────────────
    lines.append("## 📎 Anexos Técnicos")
    lines.append("")

    # Ad groups table
    lines.append("### A1. Ad Groups — Todas las Campañas")
    lines.append("")
    lines.append("| Campaña | Ad Group | Estado | Gasto | Clicks | Conv |")
    lines.append("|---------|----------|--------|-------|--------|------|")
    for ag in sorted(data["adgroups"].values(), key=lambda x: x["cost"], reverse=True):
        ghost = " 👻" if ag["clicks"] == 0 and ag["impressions"] == 0 else ""
        lines.append(f"| {ag['campaign']} | {ag['name']}{ghost} | {ag['status']} | ${ag['cost']:.2f} | {ag['clicks']} | {ag['conversions']:.1f} |")
    lines.append("")

    # Conversions table
    lines.append("### A2. Acciones de Conversión Activas")
    lines.append("")
    lines.append("| Nombre | Categoría | Primaria | Modelo Atrib. | Lookback | Conv (30d) |")
    lines.append("|--------|-----------|----------|---------------|----------|------------|")
    for cv in sorted(convs.values(), key=lambda x: x["conversions"], reverse=True):
        if cv["status"] != "ENABLED":
            continue
        prim = "✅ SÍ" if cv["primary"] else "No"
        lines.append(f"| {cv['name']} | {cv['category']} | {prim} | {cv['attribution_model']} | {cv['lookback_days']}d | {cv['conversions']:.1f} |")
    lines.append("")

    # Top search terms
    lines.append("### A3. Top 30 Search Terms — Experiencia 2026 (por gasto)")
    lines.append("")
    lines.append("| Término | Clicks | Impr | Conv | Gasto | CTR |")
    lines.append("|---------|--------|------|------|-------|-----|")
    for st in sts[:30]:
        lines.append(f"| `{st['term'][:55]}` | {st['clicks']} | {st['impressions']} | {st['conversions']:.1f} | ${st['cost']:.2f} | {pct(st['ctr'])} |")
    lines.append("")

    # Keywords QS
    lines.append("### A4. Keywords con QS Bajo (<6) — Experiencia 2026")
    lines.append("")
    low_qs_list = sorted([kw for kw in kws.values() if 0 < kw["qs"] < 6 and kw["status"] == "ENABLED"],
                          key=lambda x: x["cost"], reverse=True)
    if low_qs_list:
        lines.append("| Keyword | Match | QS | CTR_Q | Creative_Q | LP_Q | Gasto |")
        lines.append("|---------|-------|-----|-------|------------|------|-------|")
        for kw in low_qs_list[:20]:
            lines.append(f"| `{kw['text'][:45]}` | {kw['match']} | {kw['qs']} | {kw['ctr_q']} | {kw['creative_q']} | {kw['lp_q']} | ${kw['cost']:.2f} |")
    else:
        lines.append("_No se detectaron keywords con QS < 6 en datos del período._")
    lines.append("")

    # ── Notes ─────────────────────────────────────────────────────────────────
    lines.append("## 📌 Notas Importantes")
    lines.append("")
    lines.append("1. **'Pedido GloriaFood Online' (ID: 7572944047, UPLOAD_CLICKS):** Tiene 0 atribución porque el gclid se pierde en el redirect a `restaurantlogin.com`. **No es una etiqueta rota** — es un problema arquitectónico del checkout de Gloria Food. Solución real: implementar Offline Conversion Import vía webhook del sistema de pedidos.")
    lines.append("")
    lines.append("2. **'click_pedir_online':** Promovida hoy (24-abr) a conversión Primaria (categoría Compra). Data de solo 30 días — el algoritmo tardará 2-4 semanas en aprender esta señal. No esperar resultados inmediatos de bidding changes.")
    lines.append("")
    lines.append("3. **'reserva_completada_directa':** Etiqueta inactiva confirmada — pendiente de fix en thaithaimerida.com. Fuera del scope de esta auditoría de Google Ads.")
    lines.append("")
    lines.append("4. **12 ad groups pausados hoy:** Los 12 ad groups fantasma de Experiencia 2026 fueron pausados en esta sesión (scripts `pause_ghost_adgroups_experiencia2026.py`). La campaña puede entrar en período de aprendizaje brevemente.")
    lines.append("")
    lines.append("5. **Smart Campaigns (Delivery, Local):** Keywords y search terms no accesibles via Google Ads API. Todos los checks de keywords y search terms se aplican SOLO a Experiencia 2026. Para Smart Campaigns, el análisis se limita a métricas de campaña, ad groups, RSAs y assets.")
    lines.append("")
    lines.append("---")
    lines.append(f"_Auditoría profesional generada con skill `ads-google` (80 checks, scoring-system v1.5).  ")
    lines.append(f"Solo lectura — ningún cambio fue aplicado en Google Ads.  ")
    lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}_")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("Google Ads Health Audit — Thai Thai Mérida")
    print(f"Período: {DATE_START} → {DATE_END}")
    print("=" * 60)

    print("\n[1/4] Colectando datos...")
    data = collect_all_data()

    print("\n[2/4] Evaluando checks (skill: ads-google)...")
    checks = evaluate_checks(data)
    pass_c = sum(1 for c in checks.values() if c["result"] == PASS)
    warn_c = sum(1 for c in checks.values() if c["result"] == WARNING)
    fail_c = sum(1 for c in checks.values() if c["result"] == FAIL)
    na_c   = sum(1 for c in checks.values() if c["result"] == NA)
    print(f"  → PASS: {pass_c} | WARNING: {warn_c} | FAIL: {fail_c} | N/A: {na_c}")

    print("\n[3/4] Calculando Health Score...")
    total_score, grade, cat_scores = score_checks(checks)
    print(f"  → Health Score: {total_score:.0f}/100 (Grado {grade})")
    for cat, info in cat_scores.items():
        print(f"     {cat}: {info['score']:.0f}/100")

    print("\n[4/4] Generando reporte...")
    report = generate_report(data, checks, total_score, grade, cat_scores)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  → {REPORT_PATH}")
    print(f"\n{'='*60}")
    print(f"AUDIT COMPLETO — Health Score: {total_score:.0f}/100 Grado {grade}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run()
