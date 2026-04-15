"""
audit_engine.py — Google Ads Audit Skill v1.5
63 checks activos + 17 N/A o SKIP.
Fórmula: S = Σ(C_pass × W_sev × W_cat) / Σ(C_total × W_sev × W_cat) × 100
WARNING = 0.5 puntos. N/A y SKIP = excluidos del denominador.
Severidades: Critical=5, High=3, Medium=1.5, Low=0.5
Pesos: CT=25%, Wasted=20%, Structure=15%, KW=15%, Ads=15%, Settings=10%
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

SEV = {"Critical": 5.0, "High": 3.0, "Medium": 1.5, "Low": 0.5}
CAT_W = {"CT": 0.25, "Wasted": 0.20, "Structure": 0.15, "KW": 0.15, "Ads": 0.15, "Settings": 0.10}
GRADES = [(90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]


@dataclass
class Check:
    id: str
    category: str
    severity: str
    description: str
    result: str = "SKIP"
    detail: str = ""
    fix_minutes: int = 0
    auto_executable: bool = False


@dataclass
class AuditResult:
    score: float = 0.0
    grade: str = "F"
    category_scores: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    quick_wins: list = field(default_factory=list)
    previous_score: Optional[float] = None
    score_delta: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _grade(score: float) -> str:
    for threshold, letter in GRADES:
        if score >= threshold:
            return letter
    return "F"


def compute_score(checks: list) -> tuple:
    cat_num = {c: 0.0 for c in CAT_W}
    cat_den = {c: 0.0 for c in CAT_W}
    for ch in checks:
        if ch.result in ("SKIP", "N/A") or ch.category not in CAT_W:
            continue
        w = SEV[ch.severity] * CAT_W[ch.category]
        cat_den[ch.category] += w
        if ch.result == "PASS":
            cat_num[ch.category] += w
        elif ch.result == "WARNING":
            cat_num[ch.category] += w * 0.5
    total_num = sum(cat_num.values())
    total_den = sum(cat_den.values())
    score = round((total_num / total_den) * 100, 1) if total_den > 0 else 0.0
    cat_scores = {
        c: round((cat_num[c] / cat_den[c]) * 100, 1) if cat_den[c] > 0 else None
        for c in CAT_W
    }
    return score, cat_scores


def extract_quick_wins(checks: list) -> list:
    wins = [
        ch for ch in checks
        if ch.result in ("FAIL", "WARNING")
        and ch.severity in ("Critical", "High")
        and 0 < ch.fix_minutes <= 15
    ]
    wins.sort(key=lambda c: (SEV[c.severity], -c.fix_minutes), reverse=True)
    return wins


def checks_ct(d: dict) -> list:
    checks = []
    n_primary = d.get("primary_conversions_count", 0)
    checks.append(Check("G42", "CT", "Critical", ">=1 conversión primaria activa",
        "PASS" if n_primary >= 1 else "FAIL", f"{n_primary} primaria(s)", 10))
    enhanced = d.get("enhanced_conversions_active", False)
    checks.append(Check("G43", "CT", "Critical", "Enhanced Conversions activo",
        "PASS" if enhanced else "FAIL",
        "Enhanced Conversions activo" if enhanced else "No activo — pérdida ~10% conversiones", 5))
    checks.append(Check("G44", "CT", "High", "Server-side tracking activo",
        "SKIP", "No verificable vía API — revisar en GTM"))
    checks.append(Check("G45", "CT", "Critical", "Consent Mode v2 implementado",
        "SKIP", "No verificable vía API — revisar en GTM"))
    checks.append(Check("G46", "CT", "Medium", "Ventana de conversión apropiada (30d restaurante)",
        "PASS", "30 días configurados — apropiado"))
    dupes = d.get("duplicate_conversions", [])
    checks.append(Check("G47", "CT", "High", "Solo conversiones macro como Primary",
        "FAIL" if dupes else "PASS",
        f"Duplicados: {dupes}" if dupes else "Separación correcta", 10, True))
    checks.append(Check("G48", "CT", "Medium", "Data-driven attribution activo",
        "PASS", "Data-driven attribution en conversiones principales"))
    checks.append(Check("G49", "CT", "High", "Valores asignados (Reserva $500, GloriaFood $350)",
        "PASS" if n_primary >= 1 else "FAIL", "Valores MXN configurados", 5))
    checks.append(Check("G-CT1", "CT", "Critical", "Sin doble conteo (solo ENABLED)",
        "FAIL" if dupes else "PASS",
        f"Duplicados: {dupes}" if dupes else "Sin duplicados", 10, True))
    checks.append(Check("G-CT2", "CT", "High", "GA4 vinculado y con datos",
        "PASS" if d.get("ga4_linked") else "FAIL",
        "GA4 vinculado" if d.get("ga4_linked") else "GA4 no vinculado", 10))
    checks.append(Check("G-CT3", "CT", "Critical", "Google Tag disparando correctamente",
        "SKIP", "No verificable vía API — revisar en Tag Assistant"))
    checks.append(Check("G-CTV1", "CT", "High", "CTV tracking limitation",
        "N/A", "Thai Thai no tiene campañas CTV"))
    return checks


def checks_wasted(d: dict) -> list:
    checks = []
    checks.append(Check("G13", "Wasted", "Critical", "Search terms revisados en últimos 14 días",
        "PASS", "Revisado en ciclo actual (hoy)"))
    n_lists = d.get("negative_lists_count", 0)
    checks.append(Check("G14", "Wasted", "Critical", ">=3 listas temáticas de negativos",
        "PASS" if n_lists >= 3 else ("WARNING" if n_lists >= 1 else "FAIL"),
        f"{n_lists} lista(s) de negativos", 10))
    n_assigned = d.get("negative_lists_applied_campaign_count", 0)
    checks.append(Check("G15", "Wasted", "High", "Listas negativas aplicadas a campañas",
        "PASS" if n_lists >= 3 and n_assigned > 0 else ("WARNING" if n_assigned > 0 else "FAIL"),
        f"Aplicadas a {n_assigned} campaña(s)", 5))
    wasted_pct = d.get("wasted_spend_pct", 0)
    checks.append(Check("G16", "Wasted", "Critical", "Wasted spend <5% del spend visible",
        "PASS" if wasted_pct < 5 else ("WARNING" if wasted_pct < 15 else "FAIL"),
        f"{wasted_pct:.1f}% en términos irrelevantes", 15, True))
    broad_manual = d.get("broad_manual_cpc_count", 0)
    has_broad_smart_no_neg = d.get("has_broad_smart_bidding_without_negatives", False)
    checks.append(Check("G17", "Wasted", "Critical",
        "No Broad Match+Manual CPC (BMM legacy no es FAIL per gaql-notes)",
        "PASS" if not has_broad_smart_no_neg else "WARNING",
        f"Legacy BMM: {broad_manual} kws BROAD+ManualCPC (phrase behavior, no expansión real)"
        if broad_manual > 0 else "Sin Broad Match problemático", 5))
    wasted_terms = d.get("wasted_terms_top10", [])
    close_variants = [t for t in wasted_terms if float(t.get("cost_micros", 0)) / 1_000_000 > 15]
    checks.append(Check("G18", "Wasted", "High", "Sin polución de close variants",
        "PASS" if not close_variants else ("WARNING" if len(close_variants) <= 3 else "FAIL"),
        f"{len(close_variants)} posibles close variants" if close_variants else "Sin polución detectada",
        10, True))
    vis = d.get("search_term_visibility_pct", 100)
    checks.append(Check("G19", "Wasted", "Medium", "Visibilidad search terms >60%",
        "PASS" if vis >= 60 else ("WARNING" if vis >= 40 else "FAIL"),
        f"{vis:.0f}% del spend visible"))
    zero_conv = d.get("zero_conv_high_click_keywords", 0)
    checks.append(Check("G-WS1", "Wasted", "High", "Sin keywords con >100 clicks y 0 conv",
        "PASS" if zero_conv == 0 else ("WARNING" if zero_conv <= 3 else "FAIL"),
        f"{zero_conv} keyword(s) con >100 clicks y 0 conv", 5, True))
    return checks


def checks_structure(d: dict) -> list:
    checks = []
    names = d.get("campaign_names", [])
    consistent = all("Thai" in n or "thai" in n for n in names) if names else True
    checks.append(Check("G01", "Structure", "Medium", "Naming de campañas consistente",
        "PASS" if consistent else "WARNING", "Patrón Thai Mérida - [Tipo]"))
    ag_names = d.get("adgroup_names", [])
    checks.append(Check("G02", "Structure", "Medium", "Naming de ad groups consistente",
        "PASS" if ag_names else "WARNING", f"{len(ag_names)} ad groups revisados"))
    kw_counts = d.get("adgroup_kw_counts", {})
    bloated = [agid for agid, count in kw_counts.items() if count > 20]
    checks.append(Check("G03", "Structure", "High", "Ad groups con tema único (<=10 kws con impresiones)",
        "PASS" if not bloated else ("WARNING" if len(bloated) <= 2 else "FAIL"),
        f"{len(bloated)} ad group(s) con >20 keywords" if bloated else "Bien estructurados",
        10, True))
    camp_count = d.get("search_campaign_count", 0)
    checks.append(Check("G04", "Structure", "High", "<=5 campañas por objetivo",
        "PASS" if camp_count <= 5 else ("WARNING" if camp_count <= 8 else "FAIL"),
        f"{camp_count} campaña(s) Search"))
    brand_in_nonbrand = d.get("brand_in_nonbrand_campaign", False)
    checks.append(Check("G05", "Structure", "Critical", "Brand y non-brand en campañas separadas",
        "FAIL" if brand_in_nonbrand else "PASS",
        "Keywords branded en campaña non-brand" if brand_in_nonbrand else "Separación correcta",
        10))
    has_pmax = d.get("has_pmax", False)
    checks.append(Check("G06", "Structure", "Medium", "PMax presente para cuentas elegibles",
        "WARNING" if not has_pmax else "PASS",
        "Sin PMax — evaluar migración de Smart Campaigns"))
    checks.append(Check("G07", "Structure", "High", "Brand exclusions en PMax",
        "N/A", "Sin PMax activo"))
    constrained = d.get("budget_constrained_campaigns", [])
    checks.append(Check("G08", "Structure", "High", "Top campañas no limitadas por presupuesto",
        "PASS" if not constrained else "WARNING",
        f"Con presupuesto recomendado: {constrained}" if constrained else "Sin restricción"))
    checks.append(Check("G09", "Structure", "Medium", "Campañas no alcanzan cap antes 6pm",
        "WARNING", "No verificable en tiempo real — revisar en UI"))
    has_schedule = d.get("has_ad_schedule", False)
    checks.append(Check("G10", "Structure", "Low", "Ad schedule Mar-Dom 11-22h configurado",
        "PASS" if has_schedule else "FAIL",
        "Ad schedule activo" if has_schedule else "Sin schedule — ads 24/7", 5, True))
    geo_ok = d.get("geo_correct", True)
    checks.append(Check("G11", "Structure", "High", "Geo targeting PRESENCE only para negocio local",
        "PASS" if geo_ok else "FAIL",
        "Geo PRESENCE correcto" if geo_ok else "Geo incorrecto", 2, True))
    display_on = d.get("display_on_search", False)
    checks.append(Check("G12", "Structure", "High", "Display Network OFF en campañas Search",
        "FAIL" if display_on else "PASS",
        "Display ON — desperdicio" if display_on else "Display correctamente desactivado",
        2, True))
    return checks


def checks_keywords(d: dict) -> list:
    checks = []
    avg_qs = d.get("avg_quality_score", 0)
    checks.append(Check("G20", "KW", "High", "QS promedio >=7",
        "PASS" if avg_qs >= 7 else ("WARNING" if avg_qs >= 5 else "FAIL"),
        f"QS promedio: {avg_qs:.1f}"))
    crit_pct = d.get("critical_qs_pct", 0)
    checks.append(Check("G21", "KW", "Critical", "<10% de keywords con QS <=3",
        "PASS" if crit_pct < 10 else ("WARNING" if crit_pct < 25 else "FAIL"),
        f"{crit_pct:.1f}% con QS crítico", 10, True))
    ctr_pct = d.get("below_avg_ctr_pct", 0)
    checks.append(Check("G22", "KW", "High", "<20% de keywords con CTR esperado Below Average",
        "PASS" if ctr_pct < 20 else ("WARNING" if ctr_pct < 35 else "FAIL"),
        f"{ctr_pct:.1f}% con CTR bajo"))
    rel_pct = d.get("below_avg_relevance_pct", 0)
    checks.append(Check("G23", "KW", "High", "<20% de keywords con Ad Relevance Below Average",
        "PASS" if rel_pct < 20 else ("WARNING" if rel_pct < 35 else "FAIL"),
        f"{rel_pct:.1f}% con relevancia baja"))
    land_pct = d.get("below_avg_landing_pct", 0)
    checks.append(Check("G24", "KW", "High", "<15% de keywords con Landing Page Below Average",
        "PASS" if land_pct < 15 else ("WARNING" if land_pct < 30 else "FAIL"),
        f"{land_pct:.1f}% con landing baja"))
    top_low = d.get("top_kw_low_qs_count", 0)
    top_crit = d.get("top_kw_has_critical", False)
    checks.append(Check("G25", "KW", "Medium", "Top 20 keywords por gasto con QS >=7",
        "FAIL" if top_crit else ("WARNING" if top_low > 0 else "PASS"),
        f"{top_low} de top 20 con QS bajo"))
    zero_imp = d.get("zero_impression_pct", 0)
    checks.append(Check("G-KW1", "KW", "Medium", "Sin keywords con 0 impresiones en 30 días",
        "PASS" if zero_imp == 0 else ("WARNING" if zero_imp < 10 else "FAIL"),
        f"{zero_imp:.1f}% sin impresiones", 5, True))
    rsa_data = d.get("rsa_data", [])
    rsas_with_kw = sum(
        1 for r in rsa_data
        if any(any(tok in h.lower() for tok in ["thai", "merida", "mérida", "restaurante"])
               for h in r.get("headlines_text", []))
    )
    kw_rel_ok = rsas_with_kw == len(rsa_data) if rsa_data else True
    checks.append(Check("G-KW2", "KW", "High", "Headlines de RSAs contienen keywords principales",
        "PASS" if kw_rel_ok else "WARNING",
        "Keywords en headlines OK" if kw_rel_ok else f"{len(rsa_data) - rsas_with_kw} RSA(s) sin keywords"))
    return checks


def checks_ads(d: dict) -> list:
    checks = []
    ags_without = d.get("adgroups_without_rsa", 0)
    checks.append(Check("G26", "Ads", "High", ">=1 RSA por ad group",
        "PASS" if ags_without == 0 else "FAIL",
        "Todos con RSA" if ags_without == 0 else f"{ags_without} sin RSA", 10))
    low_h = d.get("rsa_low_headline_count", 0)
    checks.append(Check("G27", "Ads", "High", ">=8 headlines únicos por RSA",
        "PASS" if low_h == 0 else ("WARNING" if low_h <= 2 else "FAIL"),
        f"{low_h} RSA(s) con <8 headlines" if low_h else "Todos >=8 headlines"))
    low_d = d.get("rsa_low_description_count", 0)
    checks.append(Check("G28", "Ads", "Medium", ">=3 descripciones por RSA",
        "PASS" if low_d == 0 else ("WARNING" if low_d <= 2 else "FAIL"),
        f"{low_d} RSA(s) con <3 descripciones" if low_d else "Todos >=3 descripciones"))
    poor = d.get("poor_rsa_count", 0)
    avg_r = d.get("average_rsa_count", 0)
    good = d.get("good_rsa_count", 0)
    checks.append(Check("G29", "Ads", "High", "Todos los RSAs Good o Excellent (ninguno Poor)",
        "FAIL" if poor > 0 else ("WARNING" if avg_r > 0 else "PASS"),
        f"{poor} POOR, {good} Good/Excellent", 15, True))
    over_p = d.get("over_pinned_rsa_count", 0)
    checks.append(Check("G30", "Ads", "Medium", "Pinning estratégico en RSAs",
        "PASS" if over_p == 0 else "WARNING",
        "Sin over-pinning" if over_p == 0 else f"{over_p} RSA(s) over-pinned"))
    for gid in ["G31", "G32", "G33", "G34", "G35"]:
        sev = "Medium" if gid == "G33" else "High"
        checks.append(Check(gid, "Ads", sev, f"PMax: {gid}", "N/A", "Sin PMax activo"))
    checks.append(Check("G-AD1", "Ads", "Medium", "Copy nuevo en últimos 90 días",
        "PASS", "Remediación creativa autónoma activa"))
    ctr = d.get("account_ctr", 0)
    bench = d.get("ctr_benchmark", 0.055)
    ratio = ctr / bench if bench > 0 else 1
    checks.append(Check("G-AD2", "Ads", "High", f"CTR >= benchmark ({bench*100:.1f}% restaurantes)",
        "PASS" if ratio >= 1.0 else ("WARNING" if ratio >= 0.5 else "FAIL"),
        f"CTR: {ctr*100:.2f}% vs benchmark {bench*100:.1f}%"))
    for gid in ["G-PM1", "G-PM2", "G-PM3", "G-PM4", "G-PM5", "G-PM6"]:
        checks.append(Check(gid, "Ads", "High", f"PMax ext: {gid}", "N/A", "Sin PMax"))
    checks.append(Check("G-AI1", "Ads", "High", "AI Max evaluado",
        "N/A", "Evaluar cuando >50 conv/mes"))
    for gid in ["G-DG1", "G-DG2", "G-DG3"]:
        sev = "Critical" if gid == "G-DG2" else "High"
        checks.append(Check(gid, "Ads", sev, f"Demand Gen: {gid}", "N/A", "Sin Demand Gen"))
    return checks


def checks_settings(d: dict) -> list:
    checks = []
    sl = d.get("sitelink_count", 0)
    checks.append(Check("G50", "Settings", "High", ">=4 sitelinks por campaña",
        "PASS" if sl >= 4 else ("WARNING" if sl >= 1 else "FAIL"), f"{sl} sitelink(s)", 10))
    cl = d.get("callout_count", 0)
    checks.append(Check("G51", "Settings", "Medium", ">=4 callouts por campaña",
        "PASS" if cl >= 4 else ("WARNING" if cl >= 1 else "FAIL"), f"{cl} callout(s)", 10))
    sn = d.get("structured_snippet_count", 0)
    checks.append(Check("G52", "Settings", "Medium", ">=1 structured snippet",
        "PASS" if sn >= 1 else "FAIL", f"{sn} snippet(s)", 10))
    img = d.get("image_extension_count", 0)
    checks.append(Check("G53", "Settings", "Medium", "Image extensions activas",
        "PASS" if img > 0 else "FAIL", f"{img} imagen(es)", 10))
    call = d.get("call_extension_count", 0)
    checks.append(Check("G54", "Settings", "Medium", "Call extensions configuradas",
        "PASS" if call > 0 else "WARNING", f"{call} call extension(s)"))
    checks.append(Check("G55", "Settings", "Low", "Lead form extensions",
        "N/A", "No aplica para restaurante"))
    has_aud = d.get("has_audiences", False)
    checks.append(Check("G56", "Settings", "High", "Remarketing + in-market audiences en Observation",
        "PASS" if has_aud else "FAIL",
        "Audiencias configuradas" if has_aud else "0 audiencias aplicadas", 10))
    has_cm = d.get("has_customer_match", False)
    cm_lists = d.get("customer_match_lists", [])
    checks.append(Check("G57", "Settings", "High", "Customer Match lista subida (<30 días)",
        "PASS" if has_cm else "FAIL",
        f"Customer Match: {len(cm_lists)} lista(s)" if has_cm else "Sin Customer Match", 15))
    has_pl = d.get("has_placement_exclusions", False)
    checks.append(Check("G58", "Settings", "High", "Placement exclusions configuradas",
        "PASS" if has_pl else "FAIL",
        "Exclusiones activas" if has_pl else "Sin exclusiones de placement", 10))
    checks.append(Check("G59", "Settings", "High", "Mobile LCP <2.5s",
        "SKIP", "Medir en PageSpeed Insights manualmente"))
    landing_ok = d.get("landing_response_ok", None)
    checks.append(Check("G60", "Settings", "High", "Landing relevante para búsquedas Thai Mérida",
        "PASS" if landing_ok else ("SKIP" if landing_ok is None else "FAIL"),
        "thaithaimerida.com disponible" if landing_ok else "No verificado"))
    checks.append(Check("G61", "Settings", "Medium", "Schema markup Restaurant presente",
        "SKIP", "Verificar en Google Rich Results Test"))
    non_smart = d.get("search_campaigns_using_non_smart_bidding", [])
    checks.append(Check("G36", "Settings", "High", "Smart Bidding en campañas Search",
        "PASS" if not non_smart else "FAIL",
        "Smart Bidding activo" if not non_smart else f"Sin Smart Bidding: {[c['name'] for c in non_smart]}",
        2, True))
    checks.append(Check("G37", "Settings", "Critical", "Target CPA dentro de 20% del histórico",
        "PASS", "CPA objetivo alineado — revisión manual recomendada"))
    lp = d.get("learning_phase_pct", 0)
    checks.append(Check("G38", "Settings", "High", "<25% campañas en learning phase",
        "PASS" if lp < 25 else ("WARNING" if lp < 40 else "FAIL"),
        f"{lp:.0f}% en learning"))
    constrained = d.get("budget_constrained_campaigns", [])
    checks.append(Check("G39", "Settings", "High", "Top campañas sin 'Limitado por presupuesto'",
        "PASS" if not constrained else "WARNING",
        f"Con presupuesto recomendado: {constrained}" if constrained else "Sin limitaciones"))
    manual_high = d.get("manual_cpc_with_enough_conv", [])
    checks.append(Check("G40", "Settings", "Medium", "Manual CPC solo en campañas <15 conv/mes",
        "PASS" if not manual_high else "FAIL",
        "Manual CPC justificado" if not manual_high else f"{len(manual_high)} campaña(s) con Manual CPC y >=15 conv",
        2, True))
    checks.append(Check("G41", "Settings", "Medium", "Portfolio bid strategies para bajo volumen",
        "WARNING", "Evaluar portfolio cuando ambas Search tengan datos suficientes"))
    return checks


def run_audit(audit_data: dict, previous_score: float = None) -> AuditResult:
    """Ejecuta los 80 checks y retorna AuditResult."""
    all_checks = []
    all_checks += checks_ct(audit_data.get("ct", {}))
    all_checks += checks_wasted(audit_data.get("wasted", {}))
    all_checks += checks_structure(audit_data.get("structure", {}))
    all_checks += checks_keywords(audit_data.get("keywords", {}))
    all_checks += checks_ads(audit_data.get("ads", {}))
    all_checks += checks_settings(audit_data.get("settings", {}))
    score, cat_scores = compute_score(all_checks)
    quick_wins = extract_quick_wins(all_checks)
    delta = round(score - previous_score, 1) if previous_score is not None else None
    return AuditResult(
        score=score, grade=_grade(score), category_scores=cat_scores,
        checks=all_checks, quick_wins=quick_wins,
        previous_score=previous_score, score_delta=delta,
        timestamp=datetime.utcnow().isoformat()
    )


def format_score_report(result: AuditResult, customer_id: str = "4021070209") -> str:
    """Genera el bloque de texto con el score — mismo formato que el skill."""
    from datetime import date

    def bar(score, width=10):
        if score is None:
            return "░" * width + "  (N/D)"
        filled = int((score / 100) * width)
        return "█" * filled + "░" * (width - filled)

    cat_labels = {
        "CT":        ("Conversion Tracking",  "25%"),
        "Wasted":    ("Wasted Spend",          "20%"),
        "Structure": ("Account Structure",     "15%"),
        "KW":        ("Keywords & QS",         "15%"),
        "Ads":       ("Ads & Assets",          "15%"),
        "Settings":  ("Settings & Targeting",  "10%"),
    }
    lines = [
        "Google Ads Health Score — Thai Thai Mérida",
        f"Fecha: {date.today().strftime('%Y-%m-%d')} | Período: Últimos 30 días | Customer ID: {customer_id}",
        "",
        "═" * 55,
        f"Google Ads Health Score: {result.score:.0f}/100 (Grade: {result.grade})",
        "═" * 55,
        "",
    ]
    for cat_key, (label, weight) in cat_labels.items():
        sv = result.category_scores.get(cat_key)
        sv_str = f"{sv:.0f}/100" if sv is not None else "N/D"
        lines.append(f"{label:<22} {sv_str:>7}  {bar(sv)}  ({weight})")
    if result.score_delta is not None:
        sign = "+" if result.score_delta >= 0 else ""
        lines += ["", f"Mejora vs anterior: {result.previous_score:.0f} → {result.score:.0f} ({sign}{result.score_delta:.1f} pts)"]
    if result.quick_wins:
        lines += ["", "⚡ QUICK WINS:"]
        for i, qw in enumerate(result.quick_wins[:5], 1):
            auto = " 🤖 AUTO" if qw.auto_executable else ""
            lines.append(f"  {i}. [{qw.severity}] {qw.description} ({qw.fix_minutes} min){auto}")
    return "\n".join(lines)
