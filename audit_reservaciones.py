"""
Auditoría Nivel C — Thai Mérida - Reservaciones (Search Campaign, PAUSED)
Solo lectura. Genera: reports/reservaciones_audit_24abr2026.md

NOTA: Reservaciones es Search Campaign (TARGET_IMPRESSION_SHARE), actualmente PAUSED.
Puede tener actividad al inicio del período de 30 días si fue pausada recientemente.
Soporta: search_term_view, keywords, impression share, etc.
"""
import os, sys, unicodedata, re, json
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Reservaciones"
CAMPAIGN_TYPE = "SEARCH"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "reservaciones_audit_24abr2026.md")

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")

CPA_IDEAL = 50
CPA_MAX = 85
CPA_CRITICO = 120

IRRELEVANT_TERMS = [
    "hotel", "vuelo", "airbnb", "booking.com", "hostal", "hospedaje",
    "trabajo", "empleo", "receta", "cocinar", "restaurante chino",
    "restaurante japones", "sushi", "pizza", "hamburguesa", "tacos",
    "cantina", "bar", "cerveza"
]


def micros_to_mxn(v):
    return v / 1_000_000 if v else 0


def normalize(text):
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text))


def is_irrelevant(term):
    norm = normalize(term)
    return any(irr in norm for irr in IRRELEVANT_TERMS)


def run():
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")

    # ── 1. Métricas de campaña ────────────────────────────────────────────────
    print(f"[Reservaciones] Consultando métricas de campaña...")
    q_camp = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion,
            metrics.search_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    camp_data = {
        "id": "", "name": CAMPAIGN_NAME, "status": "PAUSED", "channel": CAMPAIGN_TYPE,
        "bidding": "", "budget": 0, "cost": 0, "clicks": 0, "impressions": 0,
        "ctr": 0, "avg_cpc": 0, "conversions": 0, "conv_value": 0, "cpa": 0,
        "impr_share": 0, "budget_lost_is": 0, "rank_lost_is": 0,
    }
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_camp):
            c = row.campaign; m = row.metrics; b = row.campaign_budget
            camp_data["id"] = str(c.id)
            camp_data["status"] = c.status.name if hasattr(c.status, "name") else str(c.status)
            camp_data["bidding"] = c.bidding_strategy_type.name if hasattr(c.bidding_strategy_type, "name") else str(c.bidding_strategy_type)
            camp_data["budget"] = micros_to_mxn(b.amount_micros)
            camp_data["cost"] += micros_to_mxn(m.cost_micros)
            camp_data["clicks"] += m.clicks
            camp_data["impressions"] += m.impressions
            camp_data["conversions"] += m.conversions
            camp_data["conv_value"] += m.conversions_value
            camp_data["impr_share"] = m.search_impression_share or 0
            camp_data["budget_lost_is"] = m.search_budget_lost_impression_share or 0
            camp_data["rank_lost_is"] = m.search_rank_lost_impression_share or 0
        camp_data["ctr"] = camp_data["clicks"] / camp_data["impressions"] if camp_data["impressions"] else 0
        camp_data["avg_cpc"] = camp_data["cost"] / camp_data["clicks"] if camp_data["clicks"] else 0
        camp_data["cpa"] = camp_data["cost"] / camp_data["conversions"] if camp_data["conversions"] else 0
    except Exception as e:
        print(f"  ERROR métricas campaña: {e}")
    print(f"  → Gasto: ${camp_data['cost']:.2f} | Clicks: {camp_data['clicks']} | Conv: {camp_data['conversions']:.1f}")

    # ── 2. Ad groups ──────────────────────────────────────────────────────────
    print("[Reservaciones] Consultando ad groups...")
    adgroups = {}
    q_ag = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type,
            metrics.cost_micros, metrics.clicks, metrics.impressions,
            metrics.conversions, metrics.conversions_value, metrics.average_cpc
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_ag):
            ag = row.ad_group; m = row.metrics
            agid = str(ag.id)
            if agid in adgroups:
                adgroups[agid]["cost"] += micros_to_mxn(m.cost_micros)
                adgroups[agid]["clicks"] += m.clicks
                adgroups[agid]["impressions"] += m.impressions
                adgroups[agid]["conversions"] += m.conversions
            else:
                adgroups[agid] = {
                    "id": agid, "name": ag.name,
                    "status": ag.status.name if hasattr(ag.status, "name") else str(ag.status),
                    "cost": micros_to_mxn(m.cost_micros), "clicks": m.clicks,
                    "impressions": m.impressions, "conversions": m.conversions,
                    "keywords": [],
                }
    except Exception as e:
        print(f"  ERROR: {e}")

    q_all = f"SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.name = '{CAMPAIGN_NAME}'"
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_all):
            agid = str(row.ad_group.id)
            if agid not in adgroups:
                adgroups[agid] = {
                    "id": agid, "name": row.ad_group.name,
                    "status": row.ad_group.status.name if hasattr(row.ad_group.status, "name") else str(row.ad_group.status),
                    "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0, "keywords": [],
                }
    except Exception as e:
        print(f"  WARN: {e}")

    for ag in adgroups.values():
        ag["ctr"] = ag["clicks"] / ag["impressions"] if ag["impressions"] else 0
        ag["avg_cpc"] = ag["cost"] / ag["clicks"] if ag["clicks"] else 0
        ag["cpa"] = ag["cost"] / ag["conversions"] if ag["conversions"] else 0
    print(f"  → {len(adgroups)} ad groups")

    # ── 3. Keywords ───────────────────────────────────────────────────────────
    print("[Reservaciones] Consultando keywords...")
    q_kw = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            metrics.cost_micros
        FROM keyword_view
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND ad_group_criterion.status != 'REMOVED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY metrics.clicks DESC
    """
    kw_data = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_kw):
            ag = row.ad_group; kw = row.ad_group_criterion; m = row.metrics
            agid = str(ag.id)
            match = kw.keyword.match_type.name if hasattr(kw.keyword.match_type, "name") else str(kw.keyword.match_type)
            status = kw.status.name if hasattr(kw.status, "name") else str(kw.status)
            qs = kw.quality_info.quality_score or 0
            key = (agid, kw.keyword.text, match)
            if key in kw_data:
                kw_data[key]["clicks"] += m.clicks
                kw_data[key]["impressions"] += m.impressions
                kw_data[key]["conversions"] += m.conversions
                kw_data[key]["cost"] += micros_to_mxn(m.cost_micros)
            else:
                kw_data[key] = {
                    "ag_id": agid, "ag_name": ag.name,
                    "text": kw.keyword.text, "match": match, "status": status,
                    "qs": qs, "clicks": m.clicks, "impressions": m.impressions,
                    "conversions": m.conversions, "cost": micros_to_mxn(m.cost_micros),
                }
    except Exception as e:
        print(f"  ERROR keywords: {e}")

    for kw in kw_data.values():
        agid = kw["ag_id"]
        if agid in adgroups:
            adgroups[agid]["keywords"].append(kw)
    print(f"  → {sum(len(ag['keywords']) for ag in adgroups.values())} keywords")

    # ── 4. Search Terms ───────────────────────────────────────────────────────
    print("[Reservaciones] Consultando search terms...")
    q_st = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.status,
            ad_group.name,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.average_cpc
        FROM search_term_view
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND metrics.impressions > 0
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY metrics.cost_micros DESC
        LIMIT 200
    """
    search_terms = []
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_st):
            st = row.search_term_view; m = row.metrics
            status = st.status.name if hasattr(st.status, "name") else str(st.status)
            search_terms.append({
                "term": st.search_term, "status": status,
                "ag": row.ad_group.name,
                "clicks": m.clicks, "impressions": m.impressions,
                "conversions": m.conversions, "cost": micros_to_mxn(m.cost_micros),
                "ctr": m.ctr, "avg_cpc": micros_to_mxn(m.average_cpc),
                "irrelevant": is_irrelevant(st.search_term),
            })
    except Exception as e:
        print(f"  ERROR search terms: {e}")
    print(f"  → {len(search_terms)} términos de búsqueda")

    # ── 5. Conversiones ───────────────────────────────────────────────────────
    print("[Reservaciones] Consultando conversiones...")
    q_conv_meta = """
        SELECT conversion_action.id, conversion_action.name, conversion_action.category,
            conversion_action.status, conversion_action.primary_for_goal,
            conversion_action.counting_type, conversion_action.click_through_lookback_window_days
        FROM conversion_action
    """
    conversions = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv_meta):
            ca = row.conversion_action
            cid = str(ca.id)
            conversions[cid] = {
                "id": cid, "name": ca.name,
                "category": ca.category.name if hasattr(ca.category, "name") else str(ca.category),
                "status": ca.status.name if hasattr(ca.status, "name") else str(ca.status),
                "primary": ca.primary_for_goal,
                "counting": ca.counting_type.name if hasattr(ca.counting_type, "name") else str(ca.counting_type),
                "lookback_days": ca.click_through_lookback_window_days,
                "all_conversions": 0, "conversions": 0,
            }
    except Exception as e:
        print(f"  ERROR conversiones metadata: {e}")

    q_conv_counts = f"""
        SELECT segments.conversion_action_name, metrics.conversions, metrics.all_conversions
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv_counts):
            ca_name = row.segments.conversion_action_name
            m = row.metrics
            for cv in conversions.values():
                if cv["name"] == ca_name:
                    cv["conversions"] += m.conversions
                    cv["all_conversions"] += m.all_conversions
                    break
    except Exception as e:
        print(f"  WARN conteos conversión: {e}")

    print(f"  → {len(conversions)} acciones")

    # ── 6. Análisis ────────────────────────────────────────────────────────────
    fantasmas = [ag for ag in adgroups.values() if ag["clicks"] == 0 and ag["impressions"] == 0]
    active_convs = [cv for cv in conversions.values() if cv["status"] == "ENABLED"]
    conv_problems = []
    for cv in conversions.values():
        if cv["status"] == "ENABLED" and cv["primary"] and cv["conversions"] == 0:
            conv_problems.append(f"**{cv['name']}** — primaria con 0 conversiones en 30d")

    # Análisis search terms
    wasted = [t for t in search_terms if t["cost"] > 50 and t["conversions"] == 0 and t["clicks"] > 0]
    irrelevant_terms = [t for t in search_terms if t["irrelevant"]]
    winners = [t for t in search_terms if t["conversions"] >= 1 and t["status"] == "NONE"]
    high_impr_no_click = [t for t in search_terms if t["impressions"] > 50 and t["clicks"] == 0]

    # Canibalización keywords inter-adgroup
    kw_map = defaultdict(list)
    for kw in kw_data.values():
        norm = normalize(kw["text"])
        kw_map[norm].append(kw)
    duplicates = {k: v for k, v in kw_map.items() if len({kw["ag_id"] for kw in v}) > 1}

    # QS bajo
    low_qs = [kw for kw in kw_data.values() if 0 < kw["qs"] < 5]

    cpa_status = "🟢" if camp_data["cpa"] <= CPA_IDEAL else ("🟡" if camp_data["cpa"] <= CPA_MAX else "🔴")
    if camp_data["conversions"] == 0:
        cpa_status = "⚫" if camp_data["cost"] == 0 else "🔴"

    # ── 7. Generar reporte Markdown ───────────────────────────────────────────
    lines = []
    lines.append(f"# Auditoría — {CAMPAIGN_NAME}")
    lines.append(f"**Tipo:** Search Campaign (TARGET_IMPRESSION_SHARE)  ")
    lines.append(f"**Estado actual:** {camp_data['status']} ⚠️  ")
    lines.append(f"**Fecha auditoría:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  ")
    lines.append(f"**Período:** {DATE_START} → {DATE_END}  ")
    lines.append("")

    lines.append("## Resumen Ejecutivo")
    lines.append("")
    lines.append(f"| Métrica | Valor | Benchmark |")
    lines.append(f"|---------|-------|-----------|")
    lines.append(f"| Presupuesto diario | ${camp_data['budget']:.2f} MXN | — |")
    lines.append(f"| Gasto total 30d | ${camp_data['cost']:.2f} MXN | — |")
    lines.append(f"| Clicks | {camp_data['clicks']:,} | — |")
    lines.append(f"| Impresiones | {camp_data['impressions']:,} | — |")
    lines.append(f"| CTR | {camp_data['ctr']*100:.2f}% | >3% |")
    lines.append(f"| CPC Promedio | ${camp_data['avg_cpc']:.2f} MXN | — |")
    lines.append(f"| Conversiones | {camp_data['conversions']:.1f} | — |")
    lines.append(f"| CPA | ${camp_data['cpa']:.2f} MXN {cpa_status} | Ideal $50 / Máx $85 / Crítico $120 |")
    lines.append(f"| Impression Share | {camp_data['impr_share']*100:.1f}% | — |")
    lines.append(f"| IS perdido por presupuesto | {camp_data['budget_lost_is']*100:.1f}% | <20% |")
    lines.append(f"| IS perdido por ranking | {camp_data['rank_lost_is']*100:.1f}% | <10% |")
    lines.append("")

    lines.append("### Top Hallazgos")
    lines.append("")
    findings = []
    if camp_data["status"] == "PAUSED":
        findings.append("🔴 CAMPAÑA PAUSADA — no está generando tráfico ni conversiones actualmente")
    if camp_data["conversions"] == 0 and camp_data["cost"] > 0:
        findings.append(f"🔴 Gastó ${camp_data['cost']:.2f} MXN sin generar conversiones")
    elif camp_data["cpa"] > CPA_CRITICO and camp_data["conversions"] > 0:
        findings.append(f"🔴 CPA crítico: ${camp_data['cpa']:.2f} MXN")
    if wasted:
        total_wasted = sum(t["cost"] for t in wasted)
        findings.append(f"🟡 {len(wasted)} términos con gasto >${50} MXN y 0 conversiones (${total_wasted:.2f} MXN desperdiciados)")
    if irrelevant_terms:
        findings.append(f"🟡 {len(irrelevant_terms)} términos irrelevantes detectados")
    if duplicates:
        findings.append(f"🟡 {len(duplicates)} keywords duplicadas entre ad groups (canibalización)")
    if low_qs:
        findings.append(f"🟡 {len(low_qs)} keywords con Quality Score < 5")
    if fantasmas:
        findings.append(f"🟡 {len(fantasmas)} ad groups fantasma")
    for i, f in enumerate(findings[:5], 1):
        lines.append(f"{i}. {f}")
    if not findings:
        lines.append("✅ Sin alertas críticas detectadas.")
    lines.append("")

    lines.append("## 1. Estructura")
    lines.append("")
    lines.append("### 1.1 Métricas Globales")
    lines.append("")
    lines.append(f"- **Estrategia de puja:** {camp_data['bidding']}")
    lines.append(f"- **Presupuesto diario:** ${camp_data['budget']:.2f} MXN")
    lines.append(f"- **Estado:** {camp_data['status']}")
    if camp_data["budget_lost_is"] > 0.2:
        lines.append(f"- ⚠️ **IS perdido por presupuesto:** {camp_data['budget_lost_is']*100:.1f}% — presupuesto insuficiente")
    if camp_data["rank_lost_is"] > 0.1:
        lines.append(f"- ⚠️ **IS perdido por ranking:** {camp_data['rank_lost_is']*100:.1f}% — QS o bids bajos")
    lines.append("")

    lines.append("### 1.2 Ad Groups")
    lines.append("")
    if adgroups:
        lines.append("| Ad Group | Estado | Gasto (MXN) | Clicks | Impresiones | CTR | CPC | Conv | CPA |")
        lines.append("|----------|--------|-------------|--------|-------------|-----|-----|------|-----|")
        for ag in sorted(adgroups.values(), key=lambda x: x["cost"], reverse=True):
            tag = " 👻" if ag["clicks"] == 0 and ag["impressions"] == 0 else ""
            lines.append(
                f"| {ag['name']}{tag} | {ag['status']} | ${ag['cost']:.2f} | {ag['clicks']} "
                f"| {ag['impressions']} | {ag['ctr']*100:.1f}% | ${ag['avg_cpc']:.2f} "
                f"| {ag['conversions']:.1f} | ${ag['cpa']:.2f} |"
            )
    lines.append("")

    lines.append("### 1.3 Keywords por Ad Group")
    lines.append("")
    for ag in sorted(adgroups.values(), key=lambda x: x["cost"], reverse=True):
        if not ag["keywords"]:
            lines.append(f"**{ag['name']}** — sin keywords con datos en el período.")
            lines.append("")
            continue
        lines.append(f"**{ag['name']}**")
        lines.append("")
        lines.append("| Keyword | Match | QS | Estado | Clicks | Impr | Conv | Gasto |")
        lines.append("|---------|-------|-----|--------|--------|------|------|-------|")
        for kw in sorted(ag["keywords"], key=lambda x: x["clicks"], reverse=True)[:20]:
            qs_flag = " ⚠️" if 0 < kw["qs"] < 5 else ""
            lines.append(
                f"| `{kw['text']}` | {kw['match']} | {kw['qs'] or '—'}{qs_flag} | {kw['status']} "
                f"| {kw['clicks']} | {kw['impressions']} | {kw['conversions']:.1f} | ${kw['cost']:.2f} |"
            )
        lines.append("")

    if duplicates:
        lines.append("### 1.4 Canibalización — Keywords Duplicadas Entre Ad Groups")
        lines.append("")
        lines.append("| Keyword | Ad Groups en conflicto |")
        lines.append("|---------|------------------------|")
        for kw_norm, entries in list(duplicates.items())[:15]:
            ag_names = " vs ".join(set(kw["ag_name"] for kw in entries))
            lines.append(f"| `{kw_norm}` | {ag_names} |")
        lines.append("")

    lines.append("## 2. Términos de Búsqueda")
    lines.append("")

    if search_terms:
        lines.append("### 2.1 Top 20 por Gasto")
        lines.append("")
        lines.append("| Término | Ad Group | Clicks | Impr | Conv | Gasto | CTR | Status |")
        lines.append("|---------|----------|--------|------|------|-------|-----|--------|")
        for t in search_terms[:20]:
            flag = " 🚨" if t["irrelevant"] else ""
            lines.append(
                f"| `{t['term'][:50]}`{flag} | {t['ag']} | {t['clicks']} | {t['impressions']} "
                f"| {t['conversions']:.1f} | ${t['cost']:.2f} | {t['ctr']*100:.1f}% | {t['status']} |"
            )
        lines.append("")

        top_conv = sorted(search_terms, key=lambda x: x["conversions"], reverse=True)[:10]
        if top_conv and top_conv[0]["conversions"] > 0:
            lines.append("### 2.2 Top 10 por Conversiones")
            lines.append("")
            lines.append("| Término | Ad Group | Conv | Gasto | CPA | Status |")
            lines.append("|---------|----------|------|-------|-----|--------|")
            for t in top_conv:
                if t["conversions"] == 0:
                    break
                cpa = t["cost"] / t["conversions"] if t["conversions"] else 0
                lines.append(f"| `{t['term'][:50]}` | {t['ag']} | {t['conversions']:.1f} | ${t['cost']:.2f} | ${cpa:.2f} | {t['status']} |")
            lines.append("")

        if irrelevant_terms:
            lines.append("### 2.3 Términos Irrelevantes")
            lines.append("")
            lines.append("Términos claramente fuera del objetivo de la campaña (candidatos a negativos):")
            lines.append("")
            lines.append("| Término | Clicks | Gasto | Razón |")
            lines.append("|---------|--------|-------|-------|")
            for t in irrelevant_terms[:15]:
                lines.append(f"| `{t['term']}` | {t['clicks']} | ${t['cost']:.2f} | No relacionado con restaurante tailandés |")
            lines.append("")

        if wasted:
            lines.append("### 2.4 Candidatos a Negativos — Gasto Sin Conversiones")
            lines.append("")
            lines.append(f"Términos con gasto >$50 MXN y 0 conversiones (desperdicio confirmado):")
            lines.append("")
            lines.append("| Término | Clicks | Gasto | Impr | Recomendación |")
            lines.append("|---------|--------|-------|------|---------------|")
            for t in sorted(wasted, key=lambda x: x["cost"], reverse=True):
                lines.append(f"| `{t['term'][:50]}` | {t['clicks']} | ${t['cost']:.2f} | {t['impressions']} | Agregar como negativo EXACT |")
            lines.append("")

        if winners:
            lines.append("### 2.5 Candidatos a Exact Match — Search Terms Winners")
            lines.append("")
            lines.append("Términos que convierten pero aún no están agregados como keywords:")
            lines.append("")
            lines.append("| Término | Ad Group | Conv | Gasto | CPA |")
            lines.append("|---------|----------|------|-------|-----|")
            for t in sorted(winners, key=lambda x: x["conversions"], reverse=True)[:10]:
                cpa = t["cost"] / t["conversions"] if t["conversions"] else 0
                lines.append(f"| `{t['term'][:50]}` | {t['ag']} | {t['conversions']:.1f} | ${t['cost']:.2f} | ${cpa:.2f} |")
            lines.append("")
    else:
        lines.append("_Sin datos de términos de búsqueda en el período (campaña pausada)._")
        lines.append("")

    lines.append("## 3. Conversiones")
    lines.append("")
    if active_convs:
        lines.append("| Conversión | Categoría | Primaria | Conteo | Lookback | Conv (30d) | All Conv |")
        lines.append("|------------|-----------|----------|--------|----------|------------|----------|")
        for cv in sorted(active_convs, key=lambda x: x["conversions"], reverse=True):
            prim = "✅ SÍ" if cv["primary"] else "No"
            lines.append(
                f"| {cv['name']} | {cv['category']} | {prim} | {cv['counting']} "
                f"| {cv['lookback_days']}d | {cv['conversions']:.1f} | {cv['all_conversions']:.1f} |"
            )
    lines.append("")

    if conv_problems:
        lines.append("### Problemas Detectados")
        lines.append("")
        for p in conv_problems:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("## 4. Recomendaciones")
    lines.append("")
    lines.append("### Fase 1 — Alto impacto, riesgo bajo")
    lines.append("")
    if camp_data["status"] == "PAUSED":
        lines.append("- **Decisión estratégica requerida:** Definir si Reservaciones se reactiva o se elimina")
        lines.append("  - Si se reactiva: revisar presupuesto y cambiar estrategia de puja a TARGET_CPA ($50 objetivo)")
        lines.append("  - Si se elimina: migrar keywords con historial a Experiencia 2026 o crear nuevo grupo")
    if wasted:
        total_w = sum(t["cost"] for t in wasted)
        lines.append(f"- Agregar {len(wasted)} términos como negativos EXACT (ahorro estimado: ${total_w:.2f} MXN/período)")
    if irrelevant_terms:
        lines.append(f"- Agregar {len(irrelevant_terms)} términos irrelevantes a lista de negativos de campaña")
    if low_qs:
        lines.append(f"- Revisar y optimizar {len(low_qs)} keywords con QS < 5")
    lines.append("")

    lines.append("### Fase 2 — Requiere validación")
    lines.append("")
    lines.append("- Si se reactiva: cambiar de TARGET_IMPRESSION_SHARE a TARGET_CPA")
    lines.append("  - TARGET_IMPRESSION_SHARE no optimiza para conversiones — solo para visibilidad")
    lines.append("- Si hay presupuesto, considerar agregar keywords de intent alto como exact match")
    if winners:
        lines.append(f"- Agregar {len(winners)} search terms winners como keywords exact match")
    if duplicates:
        lines.append(f"- Resolver {len(duplicates)} keywords duplicadas inter-adgroup")
    lines.append("")

    lines.append("### Fase 3 — Necesita más análisis")
    lines.append("")
    lines.append("- Analizar si vale la pena tener una campaña dedicada a reservaciones vs. incluir el intent de reserva en Experiencia 2026")
    lines.append("- Evaluar si el presupuesto actual es suficiente para competir en subastas de reservas")
    lines.append("")

    lines.append("---")
    lines.append(f"_Auditoría de solo lectura. {datetime.now().strftime('%d/%m/%Y %H:%M')}_")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    summary_data = {
        "campaign": camp_data,
        "adgroups_total": len(adgroups),
        "fantasmas": len(fantasmas),
        "conversions_count": len(active_convs),
        "conv_problems": len(conv_problems),
        "cpa_status": cpa_status,
        "wasted_terms": len(wasted),
        "wasted_spend": sum(t["cost"] for t in wasted),
        "irrelevant_terms": len(irrelevant_terms),
        "winner_terms": len(winners),
        "kw_duplicates": len(duplicates),
        "low_qs_kws": len(low_qs),
    }
    json_path = REPORT_PATH.replace(".md", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"✓ Reporte: {REPORT_PATH}")
    return summary_data


if __name__ == "__main__":
    run()
