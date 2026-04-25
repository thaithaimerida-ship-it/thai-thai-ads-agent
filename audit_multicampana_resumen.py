"""
Resumen Ejecutivo Multi-Campaña — Thai Thai Mérida (24 abr 2026)
Solo lectura. Lee datos de los reportes JSON generados por los scripts individuales
y hace queries adicionales de visión cruzada.
Genera: reports/multicampana_resumen_ejecutivo_24abr2026.md
"""
import os, sys, json
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
REPORT_PATH = os.path.join(
    os.path.dirname(__file__), "reports", "multicampana_resumen_ejecutivo_24abr2026.md"
)
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")

CAMPAIGNS = {
    "Delivery": {
        "name": "Thai Mérida - Delivery",
        "json": os.path.join(REPORTS_DIR, "delivery_audit_24abr2026.json"),
        "type": "Smart",
        "cpa_max": 45,
        "cpa_critico": 80,
    },
    "Local": {
        "name": "Thai Mérida - Local",
        "json": os.path.join(REPORTS_DIR, "local_audit_24abr2026.json"),
        "type": "Smart",
        "cpa_max": 60,
        "cpa_critico": 100,
    },
    "Reservaciones": {
        "name": "Thai Mérida - Reservaciones",
        "json": os.path.join(REPORTS_DIR, "reservaciones_audit_24abr2026.json"),
        "type": "Search",
        "cpa_max": 85,
        "cpa_critico": 120,
    },
}

EXPERIENCIA_2026 = {
    "name": "Thai Mérida - Experiencia 2026",
    "cost": 1001.83,
    "clicks": 81,
    "impressions": 1675,
    "conversions": 11.0,
    "cpa": 91.08,
    "adgroups_total": 18,
    "fantasmas": 12,
    "type": "Search",
}

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")


def micros_to_mxn(v):
    return v / 1_000_000 if v else 0


def health_icon(camp_data, cpa_max, cpa_critico):
    if camp_data["status"] == "PAUSED":
        return "⚫"
    if camp_data["conversions"] == 0 and camp_data["cost"] > 100:
        return "🔴"
    if camp_data["cpa"] > cpa_critico and camp_data["conversions"] > 0:
        return "🔴"
    if camp_data["cpa"] > cpa_max and camp_data["conversions"] > 0:
        return "🟡"
    if camp_data["conversions"] == 0 and camp_data["cost"] == 0:
        return "⚫"
    return "🟢"


def load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def run():
    # ── 1. Cargar datos de los 3 reportes individuales ────────────────────────
    campaign_summaries = {}
    for key, cfg in CAMPAIGNS.items():
        data = load_json(cfg["json"])
        if data:
            campaign_summaries[key] = data
            print(f"  ✓ Cargado: {key} (${data['campaign']['cost']:.2f} MXN, {data['campaign']['clicks']} clicks)")
        else:
            print(f"  ✗ No encontrado: {cfg['json']}")
            campaign_summaries[key] = None

    # ── 2. Query cruzada: conversiones activas y estado general ───────────────
    print("\nConsultando conversiones globales...")
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")

    q_conv_meta = """
        SELECT conversion_action.id, conversion_action.name, conversion_action.category,
            conversion_action.status, conversion_action.primary_for_goal
        FROM conversion_action
    """
    global_convs = {}
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv_meta):
            ca = row.conversion_action
            cid = str(ca.id)
            global_convs[cid] = {
                "name": ca.name,
                "category": ca.category.name if hasattr(ca.category, "name") else str(ca.category),
                "status": ca.status.name if hasattr(ca.status, "name") else str(ca.status),
                "primary": ca.primary_for_goal,
                "all_conversions": 0, "conversions": 0,
            }
    except Exception as e:
        print(f"  ERROR conversiones: {e}")

    # Conteos vía account-level campaign query
    q_conv_counts = f"""
        SELECT segments.conversion_action_name, metrics.conversions, metrics.all_conversions
        FROM campaign
        WHERE segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_conv_counts):
            ca_name = row.segments.conversion_action_name
            m = row.metrics
            for cv in global_convs.values():
                if cv["name"] == ca_name:
                    cv["conversions"] += m.conversions
                    cv["all_conversions"] += m.all_conversions
                    break
    except Exception as e:
        print(f"  WARN conteos: {e}")

    # ── 3. Query cruzada: keywords duplicadas ENTRE campañas ─────────────────
    print("Consultando keywords inter-campaña...")
    q_kw_cross = f"""
        SELECT campaign.name, ad_group.name,
            ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
            metrics.clicks, metrics.cost_micros
        FROM keyword_view
        WHERE campaign.name IN (
            'Thai Mérida - Delivery',
            'Thai Mérida - Local',
            'Thai Mérida - Reservaciones',
            'Thai Mérida - Experiencia 2026'
        )
        AND ad_group_criterion.status != 'REMOVED'
        AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
    """
    cross_kw = defaultdict(list)
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_kw_cross):
            kw = row.ad_group_criterion.keyword.text
            camp = row.campaign.name
            cross_kw[kw.lower().strip()].append({
                "campaign": camp,
                "ag": row.ad_group.name,
                "match": row.ad_group_criterion.keyword.match_type.name
                    if hasattr(row.ad_group_criterion.keyword.match_type, "name")
                    else str(row.ad_group_criterion.keyword.match_type),
                "clicks": row.metrics.clicks,
                "cost": micros_to_mxn(row.metrics.cost_micros),
            })
    except Exception as e:
        print(f"  WARN keywords inter-campaña: {e}")

    inter_campaign_dups = {
        kw: entries for kw, entries in cross_kw.items()
        if len({e["campaign"] for e in entries}) > 1
    }

    # ── 4. Totales consolidados ───────────────────────────────────────────────
    total_cost = EXPERIENCIA_2026["cost"]
    total_clicks = EXPERIENCIA_2026["clicks"]
    total_impressions = EXPERIENCIA_2026["impressions"]
    total_conversions = EXPERIENCIA_2026["conversions"]
    total_fantasmas = EXPERIENCIA_2026["fantasmas"]
    total_ag = EXPERIENCIA_2026["adgroups_total"]

    for key, data in campaign_summaries.items():
        if data:
            c = data["campaign"]
            total_cost += c["cost"]
            total_clicks += c["clicks"]
            total_impressions += c["impressions"]
            total_conversions += c["conversions"]
            total_fantasmas += data["fantasmas"]
            total_ag += data["adgroups_total"]

    total_cpa = total_cost / total_conversions if total_conversions else 0

    # ── 5. Generar reporte Markdown ───────────────────────────────────────────
    lines = []
    lines.append("# Resumen Ejecutivo — Audit Multi-Campaña Thai Thai (24 abr 2026)")
    lines.append("")
    lines.append(f"**Período:** {DATE_START} → {DATE_END}  ")
    lines.append(f"**Cuenta:** {CUSTOMER_ID}  ")
    lines.append(f"**Campañas auditadas:** 4 (Delivery, Local, Reservaciones, Experiencia 2026)  ")
    lines.append(f"**Generado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  ")
    lines.append("")

    lines.append("## Estado Actual de las 4 Campañas")
    lines.append("")
    lines.append("| Campaña | Tipo | Estado | Gasto 30d | Clicks | Conv | CPA | Ad Groups | Salud |")
    lines.append("|---------|------|--------|-----------|--------|------|-----|-----------|-------|")

    # Experiencia 2026 (data from previous audit)
    lines.append(
        f"| Experiencia 2026 | Search | ENABLED | ${EXPERIENCIA_2026['cost']:.2f} | "
        f"{EXPERIENCIA_2026['clicks']} | {EXPERIENCIA_2026['conversions']:.1f} | "
        f"${EXPERIENCIA_2026['cpa']:.2f} | {EXPERIENCIA_2026['adgroups_total']} (12 pausados hoy) | 🟡 |"
    )

    for key, cfg in CAMPAIGNS.items():
        data = campaign_summaries.get(key)
        if data:
            c = data["campaign"]
            icon = health_icon(c, cfg["cpa_max"], cfg["cpa_critico"])
            phantoms_note = f" ({data['fantasmas']} 👻)" if data["fantasmas"] > 0 else ""
            lines.append(
                f"| {key} | {cfg['type']} | {c['status']} | ${c['cost']:.2f} | "
                f"{c['clicks']} | {c['conversions']:.1f} | ${c['cpa']:.2f} | "
                f"{data['adgroups_total']}{phantoms_note} | {icon} |"
            )
        else:
            lines.append(f"| {key} | {cfg['type']} | — | — | — | — | — | — | ❓ |")
    lines.append("")
    lines.append(f"**TOTALES:** ${total_cost:,.2f} MXN gastados | {total_clicks:,} clicks | {total_conversions:.1f} conversiones | CPA global: ${total_cpa:.2f} MXN")
    lines.append("")

    lines.append("## Top 5 Hallazgos Críticos")
    lines.append("")

    critical_findings = []

    # Hallazgo 1: Reservaciones pausada
    reserv = campaign_summaries.get("Reservaciones")
    if reserv and reserv["campaign"]["status"] == "PAUSED":
        critical_findings.append(
            "**Thai Mérida - Reservaciones está PAUSADA** — No genera tráfico. "
            "Decisión urgente: ¿se reactiva o se migran sus keywords a Experiencia 2026? "
            "El objetivo de reservas online es el más valioso (CPA objetivo: $50 MXN)."
        )

    # Hallazgo 2: Fantasmas globales
    critical_findings.append(
        f"**{total_fantasmas} ad groups fantasma** en total (4 campañas) — "
        f"Fragmentación severa del presupuesto. Hoy pausamos los 12 de Experiencia 2026. "
        f"Revisar las demás campañas para hacer lo mismo."
    )

    # Hallazgo 3: Delivery CPA
    delivery = campaign_summaries.get("Delivery")
    if delivery:
        d_cpa = delivery["campaign"]["cpa"]
        d_conv = delivery["campaign"]["conversions"]
        if d_conv == 0:
            critical_findings.append(
                f"**Delivery: 0 conversiones** en 30 días — "
                f"Gastó ${delivery['campaign']['cost']:.2f} MXN sin retorno. "
                "Verificar tracking de Gloria Food y configuración de la conversión."
            )
        elif d_cpa > 80:
            critical_findings.append(
                f"**Delivery CPA crítico: ${d_cpa:.2f} MXN** (umbral: $80) — "
                f"CPA 3.2x sobre el objetivo ideal de $25 MXN. "
                "Revisar audiencias y creativos de la Smart Campaign."
            )

    # Hallazgo 4: Keywords inter-campaña duplicadas
    if inter_campaign_dups:
        critical_findings.append(
            f"**{len(inter_campaign_dups)} keywords duplicadas entre campañas** — "
            "Las campañas compiten entre sí en la misma subasta, inflando CPCs. "
            f"Ejemplos: {', '.join(f'`{k}`' for k in list(inter_campaign_dups.keys())[:3])}"
        )

    # Hallazgo 5: conversiones primarias
    conv_zero_primary = [
        cv["name"] for cv in global_convs.values()
        if cv["status"] == "ENABLED" and cv["primary"] and cv["conversions"] == 0
    ]
    if conv_zero_primary:
        critical_findings.append(
            f"**{len(conv_zero_primary)} conversión(es) primaria(s) con 0 registros** en 30d: "
            f"{', '.join(conv_zero_primary[:3])} — "
            "Riesgo crítico: Google no tiene señal para optimizar las campañas Search."
        )

    if not critical_findings:
        critical_findings.append("Sin hallazgos críticos detectados.")

    for i, f in enumerate(critical_findings[:5], 1):
        lines.append(f"{i}. {f}")
        lines.append("")
    lines.append("")

    lines.append("## Acciones Recomendadas — Fase 1 (Alto impacto, riesgo bajo)")
    lines.append("")
    lines.append("> ⚠️ Solo recomendaciones — nada fue ejecutado en esta auditoría.")
    lines.append("")

    f1 = []
    if reserv and reserv["campaign"]["status"] == "PAUSED":
        f1.append("**Decidir el futuro de Reservaciones** — Reactivar con TARGET_CPA ($50) o migrar keywords a Experiencia 2026")
    for key, data in campaign_summaries.items():
        if data and data["fantasmas"] > 0:
            f1.append(f"**Pausar {data['fantasmas']} ad group(s) fantasma en {key}** — Sin actividad en 30d, consumen presupuesto por fragmentación")
    if inter_campaign_dups:
        f1.append(f"**Agregar negativos cruzados entre campañas** para los {len(inter_campaign_dups)} keywords duplicadas — Elimina canibalización inter-campaña")
    if not f1:
        f1.append("Sin acciones de fase 1 detectadas.")
    for action in f1:
        lines.append(f"- {action}")
    lines.append("")

    lines.append("## Acciones Recomendadas — Fase 2 (Medio impacto, requiere validación)")
    lines.append("")
    lines.append("- **Delivery y Local:** Cambiar de TARGET_SPEND a TARGET_CPA con objetivos claros ($25 para delivery, $35 para local)")
    lines.append("- **Delivery:** Verificar integración Gloria Food → conversión → Smart Campaign (el tracking puede estar roto)")
    lines.append("- **Consolidación de presupuesto:** Con $85/día fragmentado en 4 campañas, considerar concentrar en 2-3 campañas de mayor ROI")
    if reserv and reserv.get("wasted_terms", 0) > 0:
        lines.append(f"- **Reservaciones:** Agregar {reserv['wasted_terms']} términos como negativos (ahorro: ${reserv.get('wasted_spend', 0):.2f} MXN)")
    lines.append("")

    lines.append("## Acciones Recomendadas — Fase 3 (Necesita más análisis)")
    lines.append("")
    lines.append("- Evaluar si tener Delivery + Local como Smart Campaigns separadas tiene sentido o si una sola campaña Smart cubre ambos objetivos")
    lines.append("- Analizar datos de GA4 para confirmar que las conversiones registradas en Google Ads corresponden a pedidos reales")
    lines.append("- Revisar la landing de Experiencia 2026 — el CPA de $91 MXN sugiere que la página puede tener problemas de conversión")
    lines.append("- Considerar una campaña Performance Max cuando el volumen de conversiones sea suficiente (>50/mes)")
    lines.append("")

    lines.append("## Comparación con Experiencia 2026")
    lines.append("")
    lines.append("**Patrones repetidos en todas las campañas:**")
    lines.append("")
    lines.append(f"| Problema | Experiencia 2026 | Delivery | Local | Reservaciones |")
    lines.append(f"|----------|------------------|----------|-------|---------------|")

    def y_n(val, threshold=0):
        return "✅ Sí" if val > threshold else "❌ No"

    exp_ag = campaign_summaries.get("Delivery", {}) or {}
    del_data = campaign_summaries.get("Delivery")
    loc_data = campaign_summaries.get("Local")
    res_data = campaign_summaries.get("Reservaciones")

    lines.append(f"| Ad groups fantasma | ✅ Sí (12/18) | {'✅ Sí' if del_data and del_data['fantasmas'] > 0 else '❌ No'} | {'✅ Sí' if loc_data and loc_data['fantasmas'] > 0 else '❌ No'} | {'✅ Sí' if res_data and res_data['fantasmas'] > 0 else '❌ No'} |")
    lines.append(f"| Keywords duplicadas | ✅ Sí (21) | Smart (N/A) | Smart (N/A) | {'✅ Sí' if res_data and res_data.get('kw_duplicates', 0) > 0 else '❌ No'} |")
    lines.append(f"| CPA sobre objetivo | ✅ Sí ($91) | {'✅ Sí' if del_data and del_data['campaign']['cpa'] > 45 else '❌ No'} | {'✅ Sí' if loc_data and loc_data['campaign']['cpa'] > 60 else '❌ No'} | {'N/A (pausada)'} |")
    lines.append(f"| Conversiones primarias 0 | Parcial | {'✅ Sí' if del_data and del_data['conv_problems'] > 0 else '❌ No'} | {'✅ Sí' if loc_data and loc_data['conv_problems'] > 0 else '❌ No'} | {'✅ Sí' if res_data and res_data['conv_problems'] > 0 else '❌ No'} |")
    lines.append("")
    lines.append("**Conclusión:** La fragmentación excesiva de ad groups y la falta de datos de conversión suficientes son problemas estructurales en todas las campañas, no aislados a Experiencia 2026.")
    lines.append("")

    lines.append("## Resumen Numérico del Cleanup Potencial")
    lines.append("")

    total_wasted_spend = sum(
        (data.get("wasted_spend", 0) if data else 0)
        for data in campaign_summaries.values()
    )
    total_wasted_terms = sum(
        (data.get("wasted_terms", 0) if data else 0)
        for data in campaign_summaries.values()
    )
    total_inter_dups = len(inter_campaign_dups)

    lines.append(f"| Métrica | Valor |")
    lines.append(f"|---------|-------|")
    lines.append(f"| Ad groups fantasma (4 campañas) | {total_fantasmas} |")
    lines.append(f"| Ad groups ya pausados hoy (Experiencia 2026) | 12 |")
    lines.append(f"| Keywords duplicadas inter-campaña | {total_inter_dups} |")
    lines.append(f"| Terms de búsqueda candidatos a negativo | {total_wasted_terms} |")
    lines.append(f"| Gasto estimado en terms sin conversión | ${total_wasted_spend:.2f} MXN |")
    lines.append(f"| Gasto total 30d (4 campañas) | ${total_cost:,.2f} MXN |")
    lines.append(f"| Conversiones totales 30d | {total_conversions:.1f} |")
    lines.append(f"| CPA global actual | ${total_cpa:.2f} MXN |")
    lines.append("")

    lines.append("**Impacto estimado si se ejecuta Fase 1:**")
    lines.append("")
    remaining_fantasmas = total_fantasmas - 12
    if remaining_fantasmas > 0:
        lines.append(f"- Pausar {remaining_fantasmas} ad groups fantasma adicionales → presupuesto concentrado en grupos activos")
    if total_wasted_spend > 0:
        lines.append(f"- Agregar {total_wasted_terms} negativos → ahorro de ~${total_wasted_spend:.2f} MXN en períodos futuros")
    if inter_campaign_dups:
        lines.append(f"- Resolver {total_inter_dups} keywords inter-campaña → reducción de CPCs por eliminación de auto-competencia")
    lines.append("- Reactivar Reservaciones con TARGET_CPA → potencial de capturar el intent de reserva de mayor valor")
    lines.append("")

    lines.append("---")
    lines.append(f"_Resumen ejecutivo generado automáticamente. Solo lectura — ningún cambio fue aplicado. {datetime.now().strftime('%d/%m/%Y %H:%M')}_")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✓ Resumen ejecutivo: {REPORT_PATH}")


if __name__ == "__main__":
    run()
