"""
Auditoría Nivel C — Thai Mérida - Delivery (Smart Campaign)
Solo lectura. Genera: reports/delivery_audit_24abr2026.md

NOTA: Delivery es Smart Campaign (TARGET_SPEND).
Limitaciones vs Search campaigns:
  - search_term_view: NO disponible
  - search_impression_share: NO disponible
  - keywords individuales: gestionadas automáticamente por Google
"""
import os, sys, unicodedata, re, json
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Delivery"
CAMPAIGN_TYPE = "SMART"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "delivery_audit_24abr2026.md")

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")

CPA_IDEAL = 25
CPA_MAX = 45
CPA_CRITICO = 80


def micros_to_mxn(v):
    return v / 1_000_000 if v else 0


def normalize(text):
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text))


def run():
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    results = {}

    # ── 1. Métricas de campaña ────────────────────────────────────────────────
    print(f"[Delivery] Consultando métricas de campaña...")
    q_camp = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    camp_data = {
        "id": "", "name": CAMPAIGN_NAME, "status": "", "channel": CAMPAIGN_TYPE,
        "bidding": "", "budget": 0, "cost": 0, "clicks": 0, "impressions": 0,
        "ctr": 0, "avg_cpc": 0, "conversions": 0, "conv_value": 0, "cpa": 0,
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
        if camp_data["clicks"]:
            camp_data["ctr"] = camp_data["clicks"] / camp_data["impressions"] if camp_data["impressions"] else 0
            camp_data["avg_cpc"] = camp_data["cost"] / camp_data["clicks"]
        camp_data["cpa"] = camp_data["cost"] / camp_data["conversions"] if camp_data["conversions"] else 0
    except Exception as e:
        print(f"  ERROR métricas campaña: {e}")
    results["campaign"] = camp_data
    print(f"  → Gasto: ${camp_data['cost']:.2f} | Clicks: {camp_data['clicks']} | Conv: {camp_data['conversions']:.1f}")

    # ── 2. Ad groups ──────────────────────────────────────────────────────────
    print("[Delivery] Consultando ad groups...")
    q_ag = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            metrics.conversions_value
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    adgroups = {}
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
                }
    except Exception as e:
        print(f"  ERROR ad groups: {e}")
    for ag in adgroups.values():
        ag["ctr"] = ag["clicks"] / ag["impressions"] if ag["impressions"] else 0
        ag["avg_cpc"] = ag["cost"] / ag["clicks"] if ag["clicks"] else 0
        ag["cpa"] = ag["cost"] / ag["conversions"] if ag["conversions"] else 0

    # Completar con ad groups sin datos en el período
    q_all_ag = f"""SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.name = '{CAMPAIGN_NAME}'"""
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_all_ag):
            agid = str(row.ad_group.id)
            if agid not in adgroups:
                adgroups[agid] = {
                    "id": agid, "name": row.ad_group.name,
                    "status": row.ad_group.status.name if hasattr(row.ad_group.status, "name") else str(row.ad_group.status),
                    "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0,
                    "ctr": 0, "avg_cpc": 0, "cpa": 0,
                }
    except Exception as e:
        print(f"  WARN: {e}")
    results["adgroups"] = adgroups
    print(f"  → {len(adgroups)} ad groups")

    # ── 3. Conversiones (nivel cuenta) ────────────────────────────────────────
    # conversion_action no soporta metrics.conversions — solo metadata
    print("[Delivery] Consultando conversiones...")
    q_conv_meta = """
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.category,
            conversion_action.status,
            conversion_action.primary_for_goal,
            conversion_action.counting_type,
            conversion_action.click_through_lookback_window_days
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

    # Conteos por conversión vía campaign segmentado
    q_conv_counts = f"""
        SELECT
            segments.conversion_action_name,
            metrics.conversions,
            metrics.all_conversions
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv_counts):
            ca_name = row.segments.conversion_action_name
            m = row.metrics
            for cid, cv in conversions.items():
                if cv["name"] == ca_name:
                    cv["conversions"] += m.conversions
                    cv["all_conversions"] += m.all_conversions
                    break
    except Exception as e:
        print(f"  WARN conteos conversión: {e}")

    results["conversions"] = conversions
    print(f"  → {len(conversions)} acciones de conversión")

    # ── 4. Análisis ────────────────────────────────────────────────────────────
    fantasmas = [ag for ag in adgroups.values() if ag["clicks"] == 0 and ag["impressions"] == 0]
    conv_problems = []
    for cv in conversions.values():
        if cv["status"] == "ENABLED" and cv["primary"] and cv["conversions"] == 0:
            conv_problems.append(f"**{cv['name']}** — primaria con 0 conversiones en 30d")
        if cv["status"] == "ENABLED" and cv["all_conversions"] == 0:
            conv_problems.append(f"**{cv['name']}** — 0 all_conversions (posible etiqueta inactiva)")

    cpa_status = "🟢" if camp_data["cpa"] <= CPA_IDEAL else ("🟡" if camp_data["cpa"] <= CPA_MAX else "🔴")
    results["analysis"] = {
        "fantasmas": fantasmas,
        "conv_problems": conv_problems,
        "cpa_status": cpa_status,
    }

    # ── 5. Generar reporte Markdown ───────────────────────────────────────────
    lines = []
    lines.append(f"# Auditoría — {CAMPAIGN_NAME}")
    lines.append(f"**Tipo:** Smart Campaign (TARGET_SPEND)  ")
    lines.append(f"**Fecha:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  ")
    lines.append(f"**Período:** {DATE_START} → {DATE_END}  ")
    lines.append(f"**Estado campaña:** {camp_data['status']}  ")
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
    lines.append(f"| CPA | ${camp_data['cpa']:.2f} MXN {cpa_status} | Ideal $25 / Máx $45 / Crítico $80 |")
    lines.append("")

    lines.append("### Top Hallazgos")
    lines.append("")
    findings = []
    if camp_data["cpa"] > CPA_CRITICO and camp_data["conversions"] > 0:
        findings.append(f"🔴 CPA crítico: ${camp_data['cpa']:.2f} MXN (umbral crítico: $80)")
    elif camp_data["cpa"] > CPA_MAX and camp_data["conversions"] > 0:
        findings.append(f"🟡 CPA sobre el máximo: ${camp_data['cpa']:.2f} MXN (máximo: $45)")
    if camp_data["conversions"] == 0:
        findings.append("🔴 0 conversiones en 30 días — campaña no convierte")
    if fantasmas:
        findings.append(f"🟡 {len(fantasmas)} ad group(s) fantasma (0 clicks/impresiones)")
    if conv_problems:
        for p in conv_problems[:3]:
            findings.append(f"🟡 {p}")
    lines.append("> **Nota:** Esta es una Smart Campaign. Google gestiona keywords y términos de búsqueda automáticamente. Los datos de search terms no están disponibles vía API.")
    lines.append("")
    for i, f in enumerate(findings[:5], 1):
        lines.append(f"{i}. {f}")
    if not findings:
        lines.append("✅ No se detectaron alertas críticas.")
    lines.append("")

    lines.append("## 1. Estructura")
    lines.append("")
    lines.append("### 1.1 Métricas Globales de la Campaña")
    lines.append("")
    lines.append(f"- **Tipo de campaña:** Smart (automatización total por Google)")
    lines.append(f"- **Estrategia de puja:** {camp_data['bidding']}")
    lines.append(f"- **Presupuesto diario:** ${camp_data['budget']:.2f} MXN")
    lines.append(f"- **Impression Share:** No disponible para Smart campaigns")
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
    else:
        lines.append("_Sin datos de ad groups en el período._")
    lines.append("")

    if fantasmas:
        lines.append("### 1.3 Ad Groups Fantasma")
        lines.append("")
        lines.append(f"**{len(fantasmas)} ad group(s)** sin clicks ni impresiones en 30 días:")
        lines.append("")
        for ag in fantasmas:
            lines.append(f"- {ag['name']} (estado: {ag['status']})")
        lines.append("")

    lines.append("### 1.4 Keywords")
    lines.append("")
    lines.append("> ⚠️ **Smart Campaign:** Las keywords son gestionadas automáticamente por Google. No se pueden consultar ni modificar vía GAQL. Google selecciona automáticamente los términos de búsqueda relevantes basándose en el sitio web y los anuncios configurados.")
    lines.append("")

    lines.append("## 2. Términos de Búsqueda")
    lines.append("")
    lines.append("> ⚠️ **No disponible para Smart Campaigns.** Google no expone los términos de búsqueda individuales vía API para este tipo de campaña. Para verlos, ir a Google Ads UI → Campaña → Términos de búsqueda.")
    lines.append("")

    lines.append("## 3. Conversiones")
    lines.append("")
    lines.append("### 3.1 Acciones de Conversión Activas (nivel cuenta)")
    lines.append("")
    active_convs = [cv for cv in conversions.values() if cv["status"] == "ENABLED"]
    if active_convs:
        lines.append("| Conversión | Categoría | Primaria | Conteo | Lookback | Conv (30d) | All Conv (30d) |")
        lines.append("|------------|-----------|----------|--------|----------|------------|----------------|")
        for cv in sorted(active_convs, key=lambda x: x["conversions"], reverse=True):
            prim = "✅ SÍ" if cv["primary"] else "No"
            lines.append(
                f"| {cv['name']} | {cv['category']} | {prim} | {cv['counting']} "
                f"| {cv['lookback_days']}d | {cv['conversions']:.1f} | {cv['all_conversions']:.1f} |"
            )
    lines.append("")

    if conv_problems:
        lines.append("### 3.2 Problemas Detectados en Conversiones")
        lines.append("")
        for p in conv_problems:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("## 4. Recomendaciones")
    lines.append("")
    lines.append("### Fase 1 — Alto impacto, riesgo bajo")
    lines.append("")
    recs_f1 = []
    if fantasmas:
        recs_f1.append(f"Pausar {len(fantasmas)} ad group(s) fantasma: {', '.join(ag['name'] for ag in fantasmas)}")
    if camp_data["cpa"] > CPA_CRITICO and camp_data["conversions"] > 0:
        recs_f1.append(f"CPA crítico (${camp_data['cpa']:.2f}): revisar audiencias y creativos de la Smart Campaign")
    if not recs_f1:
        recs_f1.append("Sin acciones urgentes detectadas.")
    for r in recs_f1:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("### Fase 2 — Requiere validación")
    lines.append("")
    lines.append("- Evaluar si TARGET_SPEND es la estrategia correcta o si TARGET_CPA (con CPA objetivo = $25 MXN) daría mejor control")
    lines.append("- Revisar en UI de Google Ads los términos de búsqueda reales para identificar irrelevantes")
    lines.append("- Comparar rendimiento delivery vs. Experiencia 2026 para decidir distribución de presupuesto")
    lines.append("")

    lines.append("### Fase 3 — Necesita más análisis")
    lines.append("")
    lines.append("- Evaluar si Gloria Food es la landing correcta o si una landing propia mejoraría el CPA")
    lines.append("- Analizar si la campaña Smart convierte mejor en mobile vs desktop")
    lines.append("")

    lines.append("---")
    lines.append(f"_Auditoría de solo lectura. Ningún cambio fue aplicado. {datetime.now().strftime('%d/%m/%Y %H:%M')}_")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Exportar datos para el resumen ejecutivo
    summary_data = {
        "campaign": camp_data,
        "adgroups_total": len(adgroups),
        "fantasmas": len(fantasmas),
        "conversions_count": len(active_convs),
        "conv_problems": len(conv_problems),
        "cpa_status": cpa_status,
    }
    json_path = REPORT_PATH.replace(".md", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"✓ Reporte: {REPORT_PATH}")
    return summary_data


if __name__ == "__main__":
    run()
