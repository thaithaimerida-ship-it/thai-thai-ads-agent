"""
Auditoría Nivel C — Thai Mérida - Local (Smart Campaign)
Solo lectura. Genera: reports/local_audit_24abr2026.md

NOTA: Local es Smart Campaign (TARGET_SPEND).
Limitaciones vs Search campaigns:
  - search_term_view: NO disponible
  - search_impression_share: NO disponible
  - keywords individuales: gestionadas automáticamente por Google
"""
import os, sys, json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Local"
CAMPAIGN_TYPE = "SMART"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "local_audit_24abr2026.md")

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")

CPA_IDEAL = 35
CPA_MAX = 60
CPA_CRITICO = 100


def micros_to_mxn(v):
    return v / 1_000_000 if v else 0


def run():
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    results = {}

    # ── 1. Métricas de campaña ────────────────────────────────────────────────
    print(f"[Local] Consultando métricas de campaña...")
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
        camp_data["ctr"] = camp_data["clicks"] / camp_data["impressions"] if camp_data["impressions"] else 0
        camp_data["avg_cpc"] = camp_data["cost"] / camp_data["clicks"] if camp_data["clicks"] else 0
        camp_data["cpa"] = camp_data["cost"] / camp_data["conversions"] if camp_data["conversions"] else 0
    except Exception as e:
        print(f"  ERROR métricas campaña: {e}")
    results["campaign"] = camp_data
    print(f"  → Gasto: ${camp_data['cost']:.2f} | Clicks: {camp_data['clicks']} | Conv: {camp_data['conversions']:.1f}")

    # ── 2. Ad groups ──────────────────────────────────────────────────────────
    print("[Local] Consultando ad groups...")
    adgroups = {}
    q_ag = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status,
            metrics.cost_micros, metrics.clicks, metrics.impressions,
            metrics.conversions, metrics.conversions_value
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
                }
    except Exception as e:
        print(f"  ERROR ad groups: {e}")

    q_all = f"SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.name = '{CAMPAIGN_NAME}'"
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_all):
            agid = str(row.ad_group.id)
            if agid not in adgroups:
                adgroups[agid] = {
                    "id": agid, "name": row.ad_group.name,
                    "status": row.ad_group.status.name if hasattr(row.ad_group.status, "name") else str(row.ad_group.status),
                    "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0,
                }
    except Exception as e:
        print(f"  WARN: {e}")

    for ag in adgroups.values():
        ag["ctr"] = ag["clicks"] / ag["impressions"] if ag["impressions"] else 0
        ag["avg_cpc"] = ag["cost"] / ag["clicks"] if ag["clicks"] else 0
        ag["cpa"] = ag["cost"] / ag["conversions"] if ag["conversions"] else 0
    results["adgroups"] = adgroups
    print(f"  → {len(adgroups)} ad groups")

    # ── 3. Conversiones (nivel cuenta) ────────────────────────────────────────
    print("[Local] Consultando conversiones...")
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

    results["conversions"] = conversions
    print(f"  → {len(conversions)} acciones de conversión")

    # ── 4. Análisis ────────────────────────────────────────────────────────────
    fantasmas = [ag for ag in adgroups.values() if ag["clicks"] == 0 and ag["impressions"] == 0]
    active_convs = [cv for cv in conversions.values() if cv["status"] == "ENABLED"]
    conv_problems = []
    for cv in conversions.values():
        if cv["status"] == "ENABLED" and cv["primary"] and cv["conversions"] == 0:
            conv_problems.append(f"**{cv['name']}** — primaria con 0 conversiones en 30d")
        if cv["status"] == "ENABLED" and cv["all_conversions"] == 0:
            conv_problems.append(f"**{cv['name']}** — 0 all_conversions (posible etiqueta inactiva)")

    cpa_status = "🟢" if camp_data["cpa"] <= CPA_IDEAL else ("🟡" if camp_data["cpa"] <= CPA_MAX else "🔴")
    if camp_data["conversions"] == 0:
        cpa_status = "🔴"

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
    lines.append(f"| CTR | {camp_data['ctr']*100:.2f}% | >2% |")
    lines.append(f"| CPC Promedio | ${camp_data['avg_cpc']:.2f} MXN | — |")
    lines.append(f"| Conversiones | {camp_data['conversions']:.1f} | — |")
    lines.append(f"| CPA | ${camp_data['cpa']:.2f} MXN {cpa_status} | Ideal $35 / Máx $60 / Crítico $100 |")
    lines.append("")

    lines.append("### Top Hallazgos")
    lines.append("")
    lines.append("> **Nota:** Esta es una Smart Campaign. Google gestiona keywords automáticamente. Datos de search terms no disponibles vía API.")
    lines.append("")
    findings = []
    if camp_data["conversions"] == 0:
        findings.append("🔴 0 conversiones en 30 días — campaña sin retorno")
    elif camp_data["cpa"] > CPA_CRITICO:
        findings.append(f"🔴 CPA crítico: ${camp_data['cpa']:.2f} MXN (umbral: $100)")
    elif camp_data["cpa"] > CPA_MAX:
        findings.append(f"🟡 CPA sobre el máximo: ${camp_data['cpa']:.2f} MXN (máximo: $60)")
    if fantasmas:
        findings.append(f"🟡 {len(fantasmas)} ad group(s) fantasma")
    for p in conv_problems[:2]:
        findings.append(f"🟡 {p}")
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
    lines.append("")

    if fantasmas:
        lines.append("### 1.3 Ad Groups Fantasma")
        lines.append("")
        for ag in fantasmas:
            lines.append(f"- {ag['name']} ({ag['status']})")
        lines.append("")

    lines.append("### 1.4 Keywords")
    lines.append("")
    lines.append("> ⚠️ **Smart Campaign:** Keywords gestionadas automáticamente. No accesibles vía GAQL.")
    lines.append("")

    lines.append("## 2. Términos de Búsqueda")
    lines.append("")
    lines.append("> ⚠️ **No disponible para Smart Campaigns.** Revisar en Google Ads UI → Campaña → Términos de búsqueda.")
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
        lines.append("### Problemas en Conversiones")
        lines.append("")
        for p in conv_problems:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("## 4. Recomendaciones")
    lines.append("")
    lines.append("### Fase 1 — Alto impacto, riesgo bajo")
    lines.append("")
    if fantasmas:
        lines.append(f"- Pausar {len(fantasmas)} ad group(s) fantasma")
    if camp_data["conversions"] == 0:
        lines.append("- URGENTE: Verificar que el pixel de conversión dispara correctamente en esta campaña")
    if not fantasmas and camp_data["conversions"] > 0:
        lines.append("- Sin acciones urgentes.")
    lines.append("")

    lines.append("### Fase 2 — Requiere validación")
    lines.append("")
    lines.append("- Comparar CPA de Local vs Delivery vs Experiencia 2026")
    lines.append("- Evaluar si TARGET_SPEND vs TARGET_CPA ($35 objetivo) mejora resultados")
    lines.append("- Revisar en UI los search terms para detectar irrelevantes y agregar negativos")
    lines.append("")

    lines.append("### Fase 3 — Necesita más análisis")
    lines.append("")
    lines.append("- Analizar si la cobertura geográfica está bien configurada para Mérida")
    lines.append("- Evaluar si 'Local' y 'Delivery' tienen suficiente separación de audiencia o se canibalizan")
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
    }
    json_path = REPORT_PATH.replace(".md", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"✓ Reporte: {REPORT_PATH}")
    return summary_data


if __name__ == "__main__":
    run()
