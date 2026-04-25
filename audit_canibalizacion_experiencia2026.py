"""
Auditoría de canibalización: Thai Mérida - Experiencia 2026
Solo lectura — no modifica nada en Google Ads.
Output: reports/experiencia2026_audit_24abr2026.md
"""
import os, sys, unicodedata, re
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Experiencia 2026"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "experiencia2026_audit_24abr2026.md")

end_date = datetime.now()
start_date = end_date - timedelta(days=30)
DATE_START = start_date.strftime("%Y-%m-%d")
DATE_END = end_date.strftime("%Y-%m-%d")


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin puntuación extra — para comparar duplicados."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def micros_to_mxn(micros: int) -> float:
    return micros / 1_000_000


def run():
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")

    # ── 1. Ad groups con métricas ─────────────────────────────────────────────
    q_adgroups = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY metrics.cost_micros DESC
    """

    adgroups = {}  # id → dict
    print(f"Consultando ad groups para '{CAMPAIGN_NAME}'...")

    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_adgroups):
            ag = row.ad_group
            m = row.metrics
            agid = str(ag.id)
            if agid in adgroups:
                # acumular si hay múltiples filas por segmento
                adgroups[agid]["cost"] += micros_to_mxn(m.cost_micros)
                adgroups[agid]["clicks"] += m.clicks
                adgroups[agid]["impressions"] += m.impressions
                adgroups[agid]["conversions"] += m.conversions
                adgroups[agid]["conversions_value"] += m.conversions_value
            else:
                status = ag.status.name if hasattr(ag.status, "name") else str(ag.status)
                adgroups[agid] = {
                    "id": agid,
                    "name": ag.name,
                    "status": status,
                    "cost": micros_to_mxn(m.cost_micros),
                    "clicks": m.clicks,
                    "impressions": m.impressions,
                    "ctr": m.ctr,
                    "avg_cpc": micros_to_mxn(m.average_cpc) if m.average_cpc else 0,
                    "conversions": m.conversions,
                    "conversions_value": m.conversions_value,
                    "cost_per_conversion": micros_to_mxn(m.cost_per_conversion) if m.cost_per_conversion else 0,
                    "keywords": [],
                }
    except Exception as e:
        print(f"ERROR consultando ad groups: {e}")
        sys.exit(1)

    # Recalcular CTR y CPA reales después de acumular
    for ag in adgroups.values():
        ag["ctr"] = ag["clicks"] / ag["impressions"] if ag["impressions"] else 0
        ag["cost_per_conversion"] = ag["cost"] / ag["conversions"] if ag["conversions"] else 0
        ag["avg_cpc"] = ag["cost"] / ag["clicks"] if ag["clicks"] else 0

    print(f"  → {len(adgroups)} ad groups encontrados")

    # ── 2. Keywords por ad group ──────────────────────────────────────────────
    q_keywords = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            metrics.cost_micros
        FROM keyword_view
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND ad_group_criterion.status != 'REMOVED'
          AND segments.date BETWEEN '{DATE_START}' AND '{DATE_END}'
        ORDER BY ad_group.id, metrics.clicks DESC
    """

    print("Consultando keywords...")
    kw_seen = {}  # (agid, kw_text, match) → row para deduplicar por segmentos

    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_keywords):
            ag = row.ad_group
            kw = row.ad_group_criterion
            m = row.metrics
            agid = str(ag.id)
            match = kw.keyword.match_type.name if hasattr(kw.keyword.match_type, "name") else str(kw.keyword.match_type)
            status = kw.status.name if hasattr(kw.status, "name") else str(kw.status)
            key = (agid, kw.keyword.text, match)

            if key in kw_seen:
                kw_seen[key]["clicks"] += m.clicks
                kw_seen[key]["impressions"] += m.impressions
                kw_seen[key]["conversions"] += m.conversions
                kw_seen[key]["cost"] += micros_to_mxn(m.cost_micros)
            else:
                kw_seen[key] = {
                    "ag_id": agid,
                    "ag_name": ag.name,
                    "text": kw.keyword.text,
                    "match": match,
                    "status": status,
                    "clicks": m.clicks,
                    "impressions": m.impressions,
                    "conversions": m.conversions,
                    "cost": micros_to_mxn(m.cost_micros),
                }
    except Exception as e:
        print(f"ERROR consultando keywords: {e}")
        sys.exit(1)

    # Agregar keywords a cada ad group
    for kw_data in kw_seen.values():
        agid = kw_data["ag_id"]
        if agid in adgroups:
            adgroups[agid]["keywords"].append(kw_data)

    total_kw = sum(len(v["keywords"]) for v in adgroups.values())
    print(f"  → {total_kw} keywords encontradas")

    # ── 3. Ad groups sin datos en el período (fantasmas potenciales) ──────────
    # También necesitamos los ad groups que existen pero no tienen métricas (0 actividad)
    q_all_adgroups = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
    """

    all_ag_ids = set()
    try:
        for row in ga.search(customer_id=CUSTOMER_ID, query=q_all_adgroups):
            agid = str(row.ad_group.id)
            all_ag_ids.add(agid)
            if agid not in adgroups:
                status = row.ad_group.status.name if hasattr(row.ad_group.status, "name") else str(row.ad_group.status)
                adgroups[agid] = {
                    "id": agid,
                    "name": row.ad_group.name,
                    "status": status,
                    "cost": 0,
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0,
                    "avg_cpc": 0,
                    "conversions": 0,
                    "conversions_value": 0,
                    "cost_per_conversion": 0,
                    "keywords": [],
                }
    except Exception as e:
        print(f"WARN: No se pudo obtener lista completa de ad groups: {e}")

    # ── 4. Análisis de canibalización ─────────────────────────────────────────
    # 4a. Duplicados exactos de keywords (normalizadas) entre ad groups
    kw_map = defaultdict(list)  # normalized_kw → [(ag_name, match, ag_id)]
    for agid, ag in adgroups.items():
        for kw in ag["keywords"]:
            norm = normalize(kw["text"])
            kw_map[norm].append({
                "ag_name": ag["name"],
                "ag_id": agid,
                "text": kw["text"],
                "match": kw["match"],
                "clicks": kw["clicks"],
                "impressions": kw["impressions"],
            })

    exact_duplicates = {k: v for k, v in kw_map.items() if len(v) > 1}

    # 4b. Grupos semánticamente similares (por nombre de ad group)
    # Categorías temáticas detectadas heurísticamente
    THEMES = {
        "brand": ["thai thai", "thaitha", "thai-thai"],
        "tailandes_merida": ["tailand", "comida thai", "restaurante thai"],
        "delivery": ["delivery", "a domicilio", "domicilio", "pedido", "orden"],
        "reservas": ["reserva", "mesa", "booking"],
        "experiencia": ["experiencia", "cena", "romántic", "romantica", "especial"],
        "merida": ["mérida", "merida", "yucatan", "yucatán"],
        "ubicacion": ["calle 30", "col zapata", "emiliano", "norte"],
        "wok": ["wok", "pad thai", "ramen", "fideos"],
        "precio": ["precio", "económic", "barato", "oferta", "promo"],
    }

    ag_themes = {}  # agid → set of themes
    for agid, ag in adgroups.items():
        name_norm = normalize(ag["name"])
        matched = set()
        for theme, keywords_t in THEMES.items():
            for kw_t in keywords_t:
                if kw_t in name_norm:
                    matched.add(theme)
        # También analizar keywords del grupo
        for kw in ag["keywords"]:
            kw_norm = normalize(kw["text"])
            for theme, keywords_t in THEMES.items():
                for kw_t in keywords_t:
                    if kw_t in kw_norm:
                        matched.add(theme)
        ag_themes[agid] = matched

    # Identificar pares de ad groups con temas compartidos
    canibalization_pairs = []
    ag_list = list(adgroups.keys())
    for i in range(len(ag_list)):
        for j in range(i + 1, len(ag_list)):
            id_a, id_b = ag_list[i], ag_list[j]
            shared = ag_themes[id_a] & ag_themes[id_b]
            if shared:
                # Verificar si comparten keywords también
                shared_kws = []
                for kw_norm, entries in exact_duplicates.items():
                    ag_ids_in_dup = {e["ag_id"] for e in entries}
                    if id_a in ag_ids_in_dup and id_b in ag_ids_in_dup:
                        shared_kws.append(kw_norm)
                canibalization_pairs.append({
                    "ag_a": adgroups[id_a]["name"],
                    "ag_b": adgroups[id_b]["name"],
                    "shared_themes": sorted(shared),
                    "shared_keywords": shared_kws,
                })

    # 4c. Fantasmas: 0 clicks Y 0 impressions en 30 días
    fantasmas = [ag for ag in adgroups.values() if ag["clicks"] == 0 and ag["impressions"] == 0]

    # ── 5. Propuesta de consolidación ─────────────────────────────────────────
    # Agrupar 18 → 5-6 grupos temáticos
    consolidation_groups = {
        "Brand & Nombre": {
            "desc": "Búsquedas de marca Thai Thai y variaciones",
            "themes": ["brand"],
            "ag_ids": [],
        },
        "Restaurante Tailandés Mérida": {
            "desc": "Búsquedas genéricas de comida tailandesa en Mérida",
            "themes": ["tailandes_merida", "merida"],
            "ag_ids": [],
        },
        "Delivery & Pedidos": {
            "desc": "Búsquedas de comida a domicilio / pedidos online",
            "themes": ["delivery"],
            "ag_ids": [],
        },
        "Reservas & Experiencia": {
            "desc": "Búsquedas de cena especial, reservas, ocasiones",
            "themes": ["reservas", "experiencia"],
            "ag_ids": [],
        },
        "Platillos & Menú": {
            "desc": "Búsquedas por platillo específico (Pad Thai, Wok, etc.)",
            "themes": ["wok"],
            "ag_ids": [],
        },
        "Sin clasificar / Pausar": {
            "desc": "Ad groups sin tráfico o sin tema claro — candidatos a pausa",
            "themes": [],
            "ag_ids": [],
        },
    }

    for agid, ag in adgroups.items():
        themes = ag_themes[agid]
        placed = False
        for group_name, group_data in consolidation_groups.items():
            if group_data["themes"] and themes & set(group_data["themes"]):
                group_data["ag_ids"].append(agid)
                placed = True
                break
        if not placed:
            consolidation_groups["Sin clasificar / Pausar"]["ag_ids"].append(agid)

    # ── 6. Generar reporte Markdown ───────────────────────────────────────────
    lines = []

    lines.append(f"# Auditoría de Canibalización — Thai Mérida Experiencia 2026")
    lines.append(f"**Fecha:** {datetime.now().strftime('%d de %B de %Y, %H:%M')}  ")
    lines.append(f"**Período analizado:** {DATE_START} → {DATE_END} (últimos 30 días)  ")
    lines.append(f"**Cuenta:** {CUSTOMER_ID}  ")
    lines.append(f"**Campaña:** {CAMPAIGN_NAME}  ")
    lines.append(f"**Ad groups totales:** {len(adgroups)}  ")
    lines.append("")

    total_cost = sum(ag["cost"] for ag in adgroups.values())
    total_clicks = sum(ag["clicks"] for ag in adgroups.values())
    total_impressions = sum(ag["impressions"] for ag in adgroups.values())
    total_conversions = sum(ag["conversions"] for ag in adgroups.values())
    overall_ctr = total_clicks / total_impressions if total_impressions else 0
    overall_cpa = total_cost / total_conversions if total_conversions else 0

    lines.append("## Resumen Ejecutivo")
    lines.append("")
    lines.append(f"| Métrica | Valor |")
    lines.append(f"|---------|-------|")
    lines.append(f"| Gasto total (30d) | ${total_cost:,.2f} MXN |")
    lines.append(f"| Clicks totales | {total_clicks:,} |")
    lines.append(f"| Impresiones totales | {total_impressions:,} |")
    lines.append(f"| CTR global | {overall_ctr*100:.2f}% |")
    lines.append(f"| Conversiones totales | {total_conversions:.1f} |")
    lines.append(f"| CPA global | ${overall_cpa:,.2f} MXN |")
    lines.append(f"| Ad groups fantasma (0 clicks) | {len(fantasmas)} |")
    lines.append(f"| Pares con canibalización | {len(canibalization_pairs)} |")
    lines.append(f"| Keywords duplicadas (inter-adgroup) | {len(exact_duplicates)} |")
    lines.append("")

    # Tabla resumen de ad groups
    lines.append("## Tabla Resumen — 18 Ad Groups")
    lines.append("")
    lines.append("| # | Ad Group | Estado | Gasto (MXN) | Clicks | Impresiones | CTR | CPC Prom | Conv | CPA |")
    lines.append("|---|----------|--------|-------------|--------|-------------|-----|----------|------|-----|")

    sorted_ags = sorted(adgroups.values(), key=lambda x: x["cost"], reverse=True)
    for i, ag in enumerate(sorted_ags, 1):
        fantasma_tag = " 👻" if ag["clicks"] == 0 and ag["impressions"] == 0 else ""
        lines.append(
            f"| {i} | {ag['name']}{fantasma_tag} | {ag['status']} "
            f"| ${ag['cost']:,.2f} | {ag['clicks']:,} | {ag['impressions']:,} "
            f"| {ag['ctr']*100:.2f}% | ${ag['avg_cpc']:,.2f} "
            f"| {ag['conversions']:.1f} | ${ag['cost_per_conversion']:,.2f} |"
        )

    lines.append("")

    # Keywords por ad group
    lines.append("## Keywords por Ad Group")
    lines.append("")
    for ag in sorted_ags:
        lines.append(f"### {ag['name']}")
        if not ag["keywords"]:
            lines.append("_Sin keywords con datos en el período._")
            lines.append("")
            continue
        lines.append("| Keyword | Match | Estado | Clicks | Impr | Conv |")
        lines.append("|---------|-------|--------|--------|------|------|")
        for kw in sorted(ag["keywords"], key=lambda x: x["clicks"], reverse=True):
            lines.append(
                f"| `{kw['text']}` | {kw['match']} | {kw['status']} "
                f"| {kw['clicks']} | {kw['impressions']} | {kw['conversions']:.1f} |"
            )
        lines.append("")

    # Canibalización detectada
    lines.append("## Canibalización Detectada")
    lines.append("")

    if exact_duplicates:
        lines.append("### Keywords Duplicadas Entre Ad Groups")
        lines.append("")
        lines.append("Estas keywords aparecen en más de un ad group, causando que compitan entre sí en la misma subasta:")
        lines.append("")
        lines.append("| Keyword (normalizada) | Ad Groups en conflicto | Clicks totales |")
        lines.append("|----------------------|------------------------|----------------|")
        for kw_norm, entries in sorted(exact_duplicates.items(), key=lambda x: sum(e["clicks"] for e in x[1]), reverse=True):
            ag_names = " vs ".join(f"**{e['ag_name']}** ({e['match']})" for e in entries)
            total_clicks_kw = sum(e["clicks"] for e in entries)
            lines.append(f"| `{kw_norm}` | {ag_names} | {total_clicks_kw} |")
        lines.append("")
    else:
        lines.append("_No se detectaron keywords textuales exactas duplicadas entre ad groups._")
        lines.append("")

    lines.append("### Pares de Ad Groups con Temática Superpuesta")
    lines.append("")
    if canibalization_pairs:
        lines.append("Ad groups que cubren los mismos conceptos semánticos y compiten por las mismas audiencias:")
        lines.append("")
        for pair in sorted(canibalization_pairs, key=lambda x: len(x["shared_keywords"]), reverse=True):
            lines.append(f"- **{pair['ag_a']}** ↔ **{pair['ag_b']}**")
            lines.append(f"  - Temas compartidos: {', '.join(pair['shared_themes'])}")
            if pair["shared_keywords"]:
                lines.append(f"  - Keywords en común: {', '.join(f'`{k}`' for k in pair['shared_keywords'][:5])}")
    else:
        lines.append("_No se detectaron superposiciones temáticas significativas._")
    lines.append("")

    # Ad groups fantasma
    lines.append("## Ad Groups Fantasma — Pausar Inmediato")
    lines.append("")
    if fantasmas:
        lines.append(f"Los siguientes **{len(fantasmas)}** ad groups no tuvieron **ningún click ni impresión** en los últimos 30 días:")
        lines.append("")
        lines.append("| Ad Group | Estado actual | Recomendación |")
        lines.append("|----------|---------------|---------------|")
        for ag in fantasmas:
            rec = "PAUSAR" if ag["status"] == "ENABLED" else "Ya pausado / revisar keywords"
            lines.append(f"| {ag['name']} | {ag['status']} | {rec} |")
        lines.append("")
        lines.append("> **Impacto:** Eliminar ad groups sin actividad reduce la fragmentación y concentra el presupuesto de $85 MXN/día en grupos con historial de calidad.")
    else:
        lines.append("_No se detectaron ad groups fantasma en el período._")
    lines.append("")

    # Propuesta de consolidación
    lines.append("## Propuesta de Consolidación: 18 → 5-6 Ad Groups")
    lines.append("")
    lines.append("### Lógica")
    lines.append("")
    lines.append("Con $85 MXN/día y 18 ad groups, cada grupo recibe en promedio $4.72 MXN/día — insuficiente para salir del período de aprendizaje de Google Ads (mínimo ~50 conversiones/mes por grupo). La consolidación permite que el algoritmo aprenda más rápido.")
    lines.append("")

    for group_name, group_data in consolidation_groups.items():
        if not group_data["ag_ids"]:
            continue
        lines.append(f"### Grupo propuesto: **{group_name}**")
        lines.append(f"_{group_data['desc']}_")
        lines.append("")
        lines.append("Ad groups a consolidar:")
        total_g_cost = 0
        total_g_clicks = 0
        for agid in group_data["ag_ids"]:
            ag = adgroups[agid]
            total_g_cost += ag["cost"]
            total_g_clicks += ag["clicks"]
            lines.append(f"- {ag['name']} (${ag['cost']:,.2f} MXN, {ag['clicks']} clicks)")
        lines.append("")
        lines.append(f"**Volumen consolidado:** ${total_g_cost:,.2f} MXN | {total_g_clicks} clicks")
        lines.append("")

    lines.append("### Pasos de implementación sugeridos")
    lines.append("")
    lines.append("1. **Primero:** Pausar los ad groups fantasma listados arriba")
    lines.append("2. **Segundo:** Crear los 5-6 nuevos ad groups con las keywords consolidadas")
    lines.append("3. **Tercero:** Pausar los ad groups originales (NO eliminar — preservar historial)")
    lines.append("4. **Cuarto:** Monitorear por 2 semanas antes de ajustar bids")
    lines.append("")

    lines.append("---")
    lines.append(f"_Reporte generado automáticamente. Solo lectura — ninguna modificación fue aplicada en Google Ads._")

    report_content = "\n".join(lines)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"\n✓ Reporte guardado en: {REPORT_PATH}")
    print(f"  Ad groups: {len(adgroups)}")
    print(f"  Keywords: {total_kw}")
    print(f"  Fantasmas: {len(fantasmas)}")
    print(f"  Pares canibalizados: {len(canibalization_pairs)}")
    print(f"  Keywords duplicadas: {len(exact_duplicates)}")


if __name__ == "__main__":
    run()
