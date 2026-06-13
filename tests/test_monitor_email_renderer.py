import copy
import inspect


def _decision(term="bankok casa thai", cost=44.0):
    # "bankok" is an observed typo variant for Bangkok Casa Thai.
    return {
        "decision_type": "negative_leak",
        "term": term,
        "campaign": "Thai Merida - Experiencia 2026",
        "cost_mxn": cost,
        "reason_human": "Parece otro restaurante o negocio. Aún no hay datos suficientes para decidir bloqueo.",
        "digest_reason": "Parece otro restaurante o negocio. Hugo debe confirmar si conviene bloquearlo.",
        "recommended_action": "review_one_by_one",
        "write_action": None,
        "block_allowed": False,
    }


def _digest(decisions=None, anomalies=None, warnings=None):
    decisions = list(decisions if decisions is not None else [_decision()])
    anomalies = list(anomalies if anomalies is not None else [])
    warnings = list(warnings if warnings is not None else [
        {
            "type": "conversion_mapping_incomplete",
            "detected": True,
            "reason_human": "El digest recibe conversion_quality ya calculado.",
        }
    ])
    decision_cost = sum(float(item.get("cost_mxn") or 0) for item in decisions)
    return {
        "status": "success",
        "source": "monitor_digest_v3",
        "read_only": True,
        "date_range": "LAST_7_DAYS",
        "summary": {
            "terms_reviewed": 100,
            "money_signal_cost_mxn": 0.0,
            "local_signal_cost_mxn": 600.85,
            "negative_leak_cost_mxn": decision_cost,
            "protected_cost_mxn": 160.76,
            "decisions_count": len(decisions),
        },
        "campaign_rows": [
            {
                "campaign_name": "Thai Merida - Local",
                "tipo": "smart",
                "objetivo_humano": "Visibilidad y acciones en Maps",
                "mide_local": True,
                "spend_mxn": 307.27,
                "gasto_7d": 307.27,
                "money_conversions": 0.0,
                "conversiones_dinero": 0.0,
                "money_cpa_mxn": None,
                "cpa_dinero": None,
                "etiqueta_conversion": "acciones locales",
                "all_conversions": 93.0,
                "conv_por_mxn": 3.3,
                "ctr": 5.1,
                "local_signals": 93.0,
                "senales_locales": 93.0,
                "salud": 80,
                "salud_label": "salud",
                "salud_color": "verde",
                "presupuesto_diario_mxn": 267.0,
                "sugerencia_presupuesto": {"accion": "mantener", "detalle": "0%", "razon_humana": "Mantener."},
                "nota_vigilancia": "Campaña local: se mide por acciones en Maps.",
            },
            {
                "campaign_name": "Thai Merida - Reservaciones",
                "tipo": "search",
                "objetivo_humano": "Reservaciones en línea",
                "mide_local": False,
                "spend_mxn": 120.0,
                "gasto_7d": 120.0,
                "money_conversions": 2.0,
                "conversiones_dinero": 2.0,
                "money_cpa_mxn": 60.0,
                "cpa_dinero": 60.0,
                "etiqueta_conversion": "reservas",
                "all_conversions": 2.0,
                "conv_por_mxn": 60.0,
                "ctr": 4.0,
                "local_signals": 0.0,
                "senales_locales": 0.0,
                "salud": 75,
                "salud_label": "provisional",
                "salud_color": "verde",
                "presupuesto_diario_mxn": 150.0,
                "sugerencia_presupuesto": {"accion": "mantener", "detalle": "0%", "razon_humana": "Mantener."},
                "nota_vigilancia": "Vigilar el costo por reserva.",
            },
        ],
        "search_terms_summary": {
            "terminos_revisados": 100,
            "marca_intencion_thai_protegida": 6,
            "busquedas_utiles": 9,
            "busquedas_relacionadas": 3,
            "restaurantes_externos_por_confirmar": 13,
            "senales_locales": 75,
            "decisiones_pendientes": len(decisions),
            "desperdicio_confirmado_mxn": decision_cost,
        },
        "decisions": decisions,
        "anomalies": anomalies,
        "warnings": warnings,
        "safety": {
            "writes_google_ads": False,
            "calls_execute_optimization": False,
            "touches_budgets": False,
            "post_required": False,
        },
    }


def _forbidden_strings():
    return [
        "semantic" + "_class",
        "negative" + "_allowed",
        "red" + "_safe",
        "base_negative" + "_eligible",
        "legacy",
        "candidate" + "_negative",
        "business" + "_intent",
        "conversion" + "_quality",
        "already" + "_negative",
        "recommended" + "_action",
        "observe",
        "protect",
        "review",
        "auto" + "_apply",
        "block" + "_allowed",
        "priority" + "_score",
        "suggested_match" + "_type",
        "enough" + "_data",
        "data" + "_floor",
        "weak_local" + "_action",
        "money" + "_action",
        "all" + "_conversions",
        "YESTER" + "DAY",
        "LAST_7" + "_DAYS",
        "health" + "_score",
        "Escalar " + "presupuesto",
        "Pausar " + "automáticamente",
        "Gasto en " + "revisión",
        "Críticas",
        "No cumple elegibilidad base",
        "Conversion no identificada",
        "N/A",
        "null",
        "undefined",
        "NaN",
    ]


def test_html_email_exists_in_digest():
    from engine.monitor_digest_v3 import build_monitor_digest

    payload = {
        "status": "success",
        "date_range": "LAST_7_DAYS",
        "search_terms": [
            {
                "query": "bankok casa thai",
                "campaign_name": "Thai Merida - Experiencia 2026",
                "campaign_id": "111",
                "clicks": 35,
                "cost": 44.0,
                "conversions": 0.0,
                "all_conversions": 0.0,
                "conversion_quality": "none",
                "semantic_class": "neutral",
                "already_negative": False,
                "suggested_match_type": "EXACT",
            }
        ],
    }

    digest = build_monitor_digest(payload)

    assert digest["subject_email"].startswith("Thai Thai Monitor —")
    assert "<html" in digest["html_email"]
    assert "Thai Thai Monitor" in digest["html_email"]


def test_text_email_exists_in_digest():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest({"status": "success", "date_range": "LAST_7_DAYS", "search_terms": []})

    assert digest["text_email"]
    assert "Thai Thai Monitor" in digest["text_email"]
    assert "Nada se ejecuta sin tu confirmación" in digest["text_email"]


def test_html_has_no_forbidden_strings():
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest())

    for text in _forbidden_strings():
        assert text not in rendered["html_email"]


def test_text_has_no_forbidden_strings():
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest())

    for text in _forbidden_strings():
        assert text not in rendered["text_email"]


def test_campaign_grid_has_no_cpa_column():
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest())
    html = rendered["html_email"]

    # CAMBIO 1: la columna "CPA 💰" se eliminó; grid = Gasto | Conv. | $/conv. | CTR.
    assert "CPA 💰" not in html
    local_section = html.split("Thai Merida - Local", 1)[1].split("Thai Merida - Reservaciones", 1)[0]
    for col in (">Gasto<", ">Conv.<", ">$/conv.<", ">CTR<"):
        assert col in local_section


def test_max_5_decisions_rendered():
    from engine.monitor_email_renderer import render_monitor_email

    decisions = [_decision(term=f"restaurante externo {i}", cost=i + 1) for i in range(8)]
    rendered = render_monitor_email(_digest(decisions=decisions))

    assert rendered["html_email"].count("Revisar y bloquear →") == 5  # one block button per decision (A2)
    assert "restaurante externo 4" in rendered["html_email"]
    assert "restaurante externo 5" not in rendered["html_email"]


def test_zero_decisions_email():
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest(decisions=[]))

    # Contrato v6.2: asunto fijo con fecha; formato completo (no el viejo "viernes corto").
    assert rendered["subject_email"] == "Thai Thai Monitor — últimos 7 días"
    assert "Sin decisiones esta semana" in rendered["html_email"]
    assert "Sin decisiones esta semana" in rendered["text_email"]


def test_internal_warnings_never_leak_to_email():
    # v6.2 removes the Avisos section; raw warning internals must never reach the email.
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest(warnings=[
        {"type": "conversion_mapping_incomplete", "detected": True, "reason_human": "raw internal message"}
    ]))

    assert "raw internal message" not in rendered["html_email"]
    assert "conversion_mapping_incomplete" not in rendered["html_email"]


def test_read_only_footer_present():
    from engine.monitor_email_renderer import render_monitor_email

    rendered = render_monitor_email(_digest())

    for field in ("html_email", "text_email"):
        body = rendered[field]
        assert "Nada se ejecuta sin tu confirmación" in body
        assert "Protegido: marca, términos thai, reservas" in body


def test_renderer_does_not_call_external_services():
    import engine.monitor_email_renderer as renderer

    source = inspect.getsource(renderer)

    for text in ["urllib", "requests", "httpx", "UrlFetchApp", "google.ads", "/search" + "-terms", "/negativos"]:
        assert text not in source


def test_renderer_does_not_recalculate_business_logic():
    import engine.monitor_email_renderer as renderer

    source = inspect.getsource(renderer)

    for text in [
        "build_negatives_preview",
        "classify",
        "fetch_",
        "GoogleAds",
        "CPA_TARGETS",
        "health" + "_score",
    ]:
        assert text not in source

    digest = _digest()
    modified = copy.deepcopy(digest)
    modified["campaign_rows"][0]["senales_locales"] = 777.0
    rendered = renderer.render_monitor_email(modified)
    assert "777" in rendered["html_email"]  # local-action count passed through, not recalculated
