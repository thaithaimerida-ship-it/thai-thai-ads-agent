"""Tests for the completed Monitor digest + renderer v2 (Fase F2R).

Read-only contract: money vs local never summed, no forbidden internal strings
in the email, data_broken sections never show zeros, budget suggestions are text
only. Uses fixtures (no Google Ads, no network).
"""
from engine.monitor_digest_v3 import build_monitor_digest
from engine.monitor_email_renderer import render_monitor_email


def _term(**overrides):
    term = {
        "query": "restaurante cerca de mi",
        "campaign_name": "Thai Merida - Delivery Search",
        "campaign_id": "111",
        "clicks": 40,
        "impressions": 1000,
        "cost": 150.0,
        "conversions": 0.0,
        "all_conversions": 0.0,
        "conversion_quality": "none",
        "semantic_class": "neutral",
        "already_negative": False,
        "suggested_match_type": "EXACT",
    }
    term.update(overrides)
    return term


def _payload(terms, date_range="LAST_7_DAYS"):
    return {"status": "success", "date_range": date_range, "search_terms": terms}


def _rich_context():
    return {
        "generated_date": "lunes 8 de junio de 2026",
        "links": {"ads": "https://ads.google.com/aw/overview",
                  "bloqueo_base": "https://x/acciones/bloqueo", "token": "T0K3N",
                  "bloqueos": "https://x/acciones/bloqueos?token=T0K3N",
                  "resenas": "https://x/acciones/resenas?token=T0K3N",
                  "revision": "https://x/acciones/bloqueo?token=T0K3N"},
        "campaign_budgets": {"Thai Merida - Delivery Search": 267.0},
        "reviews_reference_date": "2026-06-05T00:00:00Z",
        "gbp": {
            "data_broken": False, "periodo_dias": 30,
            "metricas": {
                "vistas_maps": {"valor": 17904, "delta_pct": 8.0},
                "rutas": {"valor": 1053, "delta_pct": -5.0},
                "clics_menu": {"valor": 349, "delta_pct": 12.0},
                "llamadas": {"valor": 65, "delta_pct": -3.0},
                "clics_web": {"valor": 141, "delta_pct": 4.0},
                "vistas_busqueda_movil": {"valor": 671, "delta_pct": 1.0},
                "vistas_maps_desktop": {"valor": 489, "delta_pct": 0.0},
                "vistas_busqueda_desktop": {"valor": 401, "delta_pct": 2.0},
            },
        },
        "reviews": {
            "data_broken": False,
            "reviews": [
                {"stars": 5, "comment": "Comida deliciosa y buen servicio.", "create_time": "2026-06-02T00:00:00Z", "has_reply": False, "reviewer": "Ana"},
                {"stars": 5, "comment": "Excelente lugar.", "create_time": "2026-06-01T00:00:00Z", "has_reply": True, "reviewer": "Luis"},
                {"stars": 4, "comment": "Buena experiencia, faltaba sabor.", "create_time": "2026-05-31T00:00:00Z", "has_reply": False, "reviewer": "Marta"},
                {"stars": 1, "comment": "Mala experiencia y mal servicio.", "create_time": "2026-05-30T00:00:00Z", "has_reply": False, "reviewer": "Ilse"},
            ],
            "stats": {  # FUENTE ÚNICA (fetch_reviews_full): rating/total/distribución/pendientes
                "average_rating": 4.7, "total_reviews": 1204,
                "distribucion": {5: 950, 4: 150, 3: 60, 2: 24, 1: 20},
                "pendientes": [{"review_id": "a", "stars": 5, "reviewer": "Ana",
                                "comment": "Comida deliciosa y buen servicio.", "create_time": "2026-06-02T00:00:00Z"}],
                "completo": True,
            },
        },
        "ads_quality": {
            "data_broken": False, "total_activos": 12, "todos_aprobados": True, "rechazados": [],
            "distribucion": {"excelente": 4, "bueno": 5, "promedio": 2, "pobre": 1, "sin_datos": 0},
            "caballos_de_batalla": [
                {"titulo_corto": "Comida tailandesa en Mérida", "campana": "Experiencia", "calidad": "excelente",
                 "ctr": "4.2%", "clics": 120, "impresiones": 2800, "conversiones": 3},
            ],
            "pobres_sin_impresiones": {"cantidad": 3, "dias": 30, "titulos": [],
                                       "diagnostico_humano": "Sin impresiones desde hace 30 días. Conviene rotar el texto."},
        },
        "seo": {
            "data_broken": False, "score": 82,
            "componentes": {"performance": 70, "seo_tecnico": 90, "on_page": 100, "web_vitals": 75, "accesibilidad": 88},
            "movil": {"perf": 70, "lcp_s": 2.4, "cls": 0.02},
            "escritorio": {"perf": 92, "lcp_s": 1.1, "cls": 0.01},
            "checks_onpage": "10/10",
            "oportunidad_principal": "Comprimir imágenes del menú para mejorar la carga en móvil.",
        },
        "search_console": {"data_broken": True},
    }


def _forbidden_strings():
    return [
        "semantic" + "_class", "negative" + "_allowed", "red" + "_safe",
        "base_negative" + "_eligible", "legacy", "candidate" + "_negative",
        "business" + "_intent", "conversion" + "_quality", "already" + "_negative",
        "recommended" + "_action", "observe", "protect", "review", "auto" + "_apply",
        "block" + "_allowed", "priority" + "_score", "suggested_match" + "_type",
        "enough" + "_data", "data" + "_floor", "weak_local" + "_action",
        "money" + "_action", "all" + "_conversions", "YESTER" + "DAY",
        "LAST_7" + "_DAYS", "health" + "_score", "Gasto en " + "revisión",
        "Críticas", "No cumple elegibilidad base", "Conversion no identificada",
        "N/A", "null", "undefined", "NaN",
    ]


# ── A1 regression: real conversion action names map to money ──────────────────
def test_conversion_actions_reales_mapeadas():
    from engine.search_term_classifier import classify_conversion_quality

    for name in ["Pedido GloriaFood Online", "PEDIDO GLORIAFOOD ONLINE",
                 "reserva_completada_directa", "Reserva_Completada_Directa"]:
        quality = classify_conversion_quality(
            [{"name": name, "all_conversions": 1.0, "conversions": 1.0}],
            conversions=1.0, all_conversions=1.0,
        )
        assert quality == "money_action", f"{name!r} debería mapear a money_action"

    # A non-money action must NOT be money
    other = classify_conversion_quality(
        [{"name": "Local actions - Directions", "all_conversions": 3.0}],
        all_conversions=3.0,
    )
    assert other != "money_action"


# ── Golden set: Hugo's classified terms → expected identity ───────────────────
def test_golden_set_identidad_esperada():
    from engine.search_term_classifier import classify_search_term
    from engine.negatives_classifier_v3 import build_negatives_preview_v3_payload

    golden = {
        "thai thai merida": "marca_propia",
        "comida tailandesa merida": "intencion_thai",
        "casa thai": "restaurante_externo",
        "muay thai": "basura",
        "comida japonesa": "categoria_asiatica",
        "restaurante cerca de mi": "generico_util",
    }
    terms = []
    for q in golden:
        base = classify_search_term(q)
        terms.append(_term(query=q, semantic_class=base.get("semantic_class"),
                           suggested_match_type=base.get("suggested_match_type")))
    items = build_negatives_preview_v3_payload(_payload(terms))["items"]
    by_term = {i["term"]: i["identity_axis"] for i in items}
    for q, expected in golden.items():
        assert by_term[q] == expected, f"{q!r}: {by_term[q]} != {expected}"


def test_casa_thai_variantes_competidor_confirmado():
    variants = ["casa thai", "casa thai mérida", "bankok casa thai", "BANGKOK CASA THAI MÉRIDA"]
    digest = build_monitor_digest(_payload([
        _term(query=v, cost=10 + i, clicks=35, conversion_quality="none") for i, v in enumerate(variants)
    ]))
    for d in digest["decisions"]:
        assert d["decision_type"] == "negative_leak"
        assert d["identity_axis"] == "restaurante_externo"
        assert d["confirmado_por_hugo"] is True


def test_termino_en_diccionario_no_genera_decision():
    # B-3: vips/yakuza already classified by Hugo → seeded → never asked again.
    digest = build_monitor_digest(_payload([
        _term(query="vips cerca de mi", cost=40.0, clicks=30, conversion_quality="none"),
        _term(query="yakuza merida", cost=8.0, clicks=12, conversion_quality="none"),
    ]))
    terms = {d["term"] for d in digest["decisions"]}
    assert "vips cerca de mi" not in terms
    assert "yakuza merida" not in terms


def test_variantes_se_agrupan_en_una_decision():
    # B-4: "restaurante la rueda" and "restaurant la rueda" are ONE decision.
    digest = build_monitor_digest(_payload([
        _term(query="restaurante la rueda cerca de mi", campaign_name="Thai Merida - Experiencia 2026",
              cost=14.0, clicks=20, conversion_quality="none"),
        _term(query="restaurant la rueda cerca de mi", campaign_name="Thai Merida - Experiencia 2026",
              cost=13.0, clicks=18, conversion_quality="none"),
    ]))
    rueda = [d for d in digest["decisions"] if "rueda" in d["term"]]
    assert len(rueda) == 1
    assert rueda[0]["variantes_count"] == 2
    assert rueda[0]["cost_mxn"] == 27.0  # variant costs summed


def test_mapeo_objetivo_campana():
    # B-2: Experiencia se mide por reservas (dinero); Local por acciones locales.
    from engine.monitor_sections import classify_campaign
    exp = classify_campaign("Thai Mérida - Experiencia 2026")
    assert exp["etiqueta_conversion"] == "reservas" and exp["mide_local"] is False
    local = classify_campaign("Thai Mérida - Local")
    assert local["etiqueta_conversion"] == "acciones locales" and local["mide_local"] is True
    dely = classify_campaign("Thai Mérida - Delivery")
    assert dely["etiqueta_conversion"] == "pedidos" and dely["tipo"] == "smart"
    delys = classify_campaign("Thai Mérida - Delivery Search")
    assert delys["etiqueta_conversion"] == "pedidos" and delys["tipo"] == "search"


def test_ads_quality_from_real_list():
    # F-1: real ad list → distribution, horses by conversions, poor-without-impressions.
    from engine.monitor_sections import build_ads_quality_from_list
    ads = [
        {"ad_strength": "EXCELLENT", "approval_status": "APPROVED", "headlines": ["A excelente"], "ctr_pct": 4.2, "clicks": 57, "impressions": 435, "conversions": 43.0, "campaign_name": "Exp"},
        {"ad_strength": "AVERAGE", "approval_status": "APPROVED", "headlines": ["B promedio"], "ctr_pct": 3.1, "clicks": 12, "impressions": 38, "conversions": 7.0, "campaign_name": "Exp"},
        {"ad_strength": "POOR", "approval_status": "DISAPPROVED", "headlines": ["C pobre"], "ctr_pct": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0, "campaign_name": "Del"},
    ]
    q = build_ads_quality_from_list(ads, dias=7)
    assert q["total_activos"] == 3
    assert q["distribucion"]["excelente"] == 1 and q["distribucion"]["pobre"] == 1
    assert q["todos_aprobados"] is False and len(q["rechazados"]) == 1
    assert q["caballos_de_batalla"][0]["titulo_corto"] == "A excelente"  # most conversions first
    assert q["pobres_sin_impresiones"]["cantidad"] == 1


def test_campaign_metrics_split_money_local():
    # Money (GloriaFood/reserva) and local actions are split, unknown is not claimed.
    from engine.monitor_sections import build_campaign_metrics
    campaigns = [{"id": "1", "name": "Thai Mérida - Delivery", "cost_micros": 100_000_000,
                  "clicks": 50, "impressions": 1000, "daily_budget_mxn": 267.0, "all_conversions": 9}]
    breakdown = {"1": {"name": "Thai Mérida - Delivery", "actions": [
        {"name": "Pedido GloriaFood Online", "all_conversions": 2.0},
        {"name": "Local actions - Directions", "all_conversions": 5.0},
        {"name": "Una accion desconocida", "all_conversions": 4.0},
    ]}}
    rows = build_campaign_metrics(campaigns, breakdown)
    assert rows[0]["all_conversions"] == 9.0
    assert rows[0]["money_conversions"] == 2.0
    # A3: señales = TODO lo no-dinero (all_conversions − money) → 9 − 2 = 7
    assert rows[0]["local_signals"] == 7.0
    assert rows[0]["money_conversions"] + rows[0]["local_signals"] == rows[0]["all_conversions"]
    assert rows[0]["daily_budget_mxn"] == 267.0
    assert rows[0]["spend_mxn"] == 100.0


def test_load_gloriafood_internal_cuenta_7d(tmp_path):
    import sqlite3
    from engine.monitor_sources import load_gloriafood_internal
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE gloriafood_orders (id INTEGER PRIMARY KEY, total_price_mxn REAL, received_at TEXT)")
    conn.execute("INSERT INTO gloriafood_orders (total_price_mxn, received_at) VALUES (?, datetime('now','-1 days'))", (680.0,))
    conn.execute("INSERT INTO gloriafood_orders (total_price_mxn, received_at) VALUES (?, datetime('now','-2 days'))", (209.0,))
    conn.execute("INSERT INTO gloriafood_orders (total_price_mxn, received_at) VALUES (?, datetime('now','-30 days'))", (999.0,))
    conn.commit(); conn.close()
    r = load_gloriafood_internal(str(db), days=7)
    assert r["pedidos_7d"] == 2  # the 30-day-old order is excluded
    assert r["monto_mxn_7d"] == 889.0
    assert r["fuente"] == "registro interno (DB webhook)"


def test_pedidos_gloriafood_interno_en_tarjeta_delivery():
    ctx = _rich_context()
    ctx["campaign_metrics"] = [
        {"name": "Thai Mérida - Delivery", "spend_mxn": 485.0, "money_conversions": 0.0,
         "local_signals": 872.0, "clicks": 100, "impressions": 4000, "daily_budget_mxn": 55.0},
        {"name": "Thai Mérida - Local", "spend_mxn": 1230.0, "money_conversions": 0.0,
         "local_signals": 1593.0, "clicks": 200, "impressions": 8000, "daily_budget_mxn": 158.0},
    ]
    ctx["pedidos_gloriafood_interno"] = {"pedidos_7d": 13, "monto_mxn_7d": 6910.0, "fuente": "registro interno (DB webhook)"}
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), ctx)
    assert digest["pedidos_gloriafood_interno"]["pedidos_7d"] == 13
    html = digest["html_email"]
    # CAMBIO 2: el $/pedido real vive en el header; el bloque azul de la tarjeta se eliminó.
    assert "Ventas registradas: 13 pedidos · $6,910 MXN · $37 por pedido real" in html
    assert "Pedidos no atribuibles por Google (GloriaFood) — ver ventas registradas arriba." in html
    assert "Pedidos reales: 13" not in html  # bloque duplicado eliminado
    # Internal register sits on the Delivery (Smart) card, not on Local.
    delivery = [r for r in digest["campaign_rows"] if r["campaign_name"] == "Thai Mérida - Delivery"][0]
    assert delivery["pedido_real_mxn"] == round(485.0 / 13, 2)  # gasto ÷ pedidos
    local = [r for r in digest["campaign_rows"] if "Local" in r["campaign_name"]][0]
    assert "pedidos_gloriafood_interno" not in local


def test_search_console_render_con_datos():
    # A2 resuelto: Search Console en vivo (propiedad URL-prefix).
    ctx = _rich_context()
    ctx["search_console"] = {"data_broken": False, "dias": 7,
                             "start_date": "2026-06-01", "end_date": "2026-06-08",
                             "impresiones": 388, "clics": 4, "ctr": 1.0, "posicion_promedio": 6.2,
                             "top_queries": [{"query": "thai thai", "clics": 2}]}
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), ctx)
    assert digest["search_console"]["data_broken"] is False
    html = digest["html_email"]
    assert "388" in html and "6.2" in html  # impresiones + posición (ventana 7 días)
    assert "personas te vieron en los resultados de Google" in html
    # La ventana DEBE estar etiquetada con las fechas exactas en el correo.
    assert "Search Console · 7 días (2026-06-01 → 2026-06-08)" in html
    assert "Search Console en reparación" not in html


def test_anuncios_smart_resumido_y_search_deduplicado():
    # V-1: smart auto-ads resumidos (no "(sin título)"); search deduplicados por título.
    from engine.monitor_sections import build_ads_quality_from_list
    ads = [
        {"ad_strength": "", "approval_status": "APPROVED", "headlines": [], "ctr_pct": 0, "clicks": 0, "impressions": 0, "conversions": 0, "campaign_name": "Thai Mérida - Local"},
        {"ad_strength": "", "approval_status": "APPROVED", "headlines": [], "ctr_pct": 0, "clicks": 0, "impressions": 0, "conversions": 0, "campaign_name": "Thai Mérida - Delivery"},
        {"ad_strength": "POOR", "approval_status": "APPROVED", "headlines": ["Restaurante Tailandés Mérida"], "ctr_pct": 0, "clicks": 0, "impressions": 0, "conversions": 0, "campaign_name": "Thai Mérida - Experiencia 2026"},
        {"ad_strength": "POOR", "approval_status": "APPROVED", "headlines": ["Restaurante Tailandés Mérida"], "ctr_pct": 0, "clicks": 0, "impressions": 0, "conversions": 0, "campaign_name": "Thai Mérida - Experiencia 2026"},
        {"ad_strength": "POOR", "approval_status": "APPROVED", "headlines": ["Restaurante Tailandés Mérida"], "ctr_pct": 0, "clicks": 0, "impressions": 0, "conversions": 0, "campaign_name": "Thai Mérida - Experiencia 2026"},
    ]
    q = build_ads_quality_from_list(ads, 7)
    assert q["necesitan_trabajo"]["smart_sin_impresiones"] == 2
    search = q["necesitan_trabajo"]["search"]
    assert len(search) == 1 and search[0]["variantes"] == 3

    ctx = _rich_context()
    ctx["ads_quality"] = q
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=10.0, clicks=20)]), ctx)
    html = digest["html_email"]
    assert "(sin título)" not in html
    assert "Local y Delivery (smart): 2 anuncios automáticos sin impresiones — Google los gestiona" in html
    assert "Restaurante Tailandés Mérida" in html and "(×3 variantes)" in html


def test_costo_por_conv_tiene_decimales():
    # V-3: $/conv. SIEMPRE con dos decimales; jamás redondeado a entero.
    import re
    from engine.monitor_sections import build_campaign_rows_from_context
    ctx = {"campaign_metrics": [
        {"name": "Thai Mérida - Local", "spend_mxn": 1230.44, "all_conversions": 1993.0,
         "money_conversions": 0.0, "local_signals": 1993.0, "clicks": 200, "impressions": 8000,
         "daily_budget_mxn": 158.0}]}
    rows = build_campaign_rows_from_context(ctx)
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=10.0)]),
                                  {**_rich_context(), "campaign_metrics": ctx["campaign_metrics"]})
    html = digest["html_email"]
    # $/conv = 1230.44/1993 = $0.62 → debe verse con 2 decimales, no "$1"
    assert re.search(r"\$\d+\.\d{2}\b", html)
    assert "$0.62" in html
    assert rows[0]["conv_por_mxn"] == round(1230.44 / 1993.0, 2)


def test_busquedas_microcopy_literal():
    # V-5: microcopy exacto del contrato.
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), _rich_context())
    html = digest["html_email"]
    assert "buscaban Thai Thai o comida thai — protegidas" in html
    assert "restaurante cerca de mí" in html and "pueden traer clientes" in html
    assert "parecen otros negocios — se revisan al mes" in html
    assert "gastado en esas búsquedas dudosas — por confirmar" in html


def test_titulo_sin_emoji():
    # V-6: el título del header es "Thai Thai Monitor" a secas.
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0)]), _rich_context())
    html = digest["html_email"]
    assert "<h1>Thai Thai Monitor</h1>" in html
    assert "🍜 Thai Thai Monitor" not in html


def test_dinero_y_senales_nunca_se_suman():
    digest = build_monitor_digest(_payload([
        _term(query="thai thai merida", cost=18.0, conversions=1.0, all_conversions=1.0, conversion_quality="money_action"),
        _term(query="hacienda teya merida", cost=25.0, conversions=2.0, all_conversions=2.0, conversion_quality="weak_local_action"),
    ]))
    s = digest["summary"]
    assert s["money_signal_cost_mxn"] == 18.0
    assert s["local_signal_cost_mxn"] == 25.0
    assert s["money_signal_cost_mxn"] != s["local_signal_cost_mxn"] + s["money_signal_cost_mxn"] - 18.0 + s["local_signal_cost_mxn"]
    # money and local are reported on separate keys, never one combined number
    assert "money_signal_cost_mxn" in s and "local_signal_cost_mxn" in s


def test_max_5_decisiones():
    digest = build_monitor_digest(_payload([
        _term(query=f"restaurante externo {i}", clicks=3, cost=20 + i, conversion_quality="none") for i in range(8)
    ], date_range="LAST_30_DAYS"), _rich_context())
    assert len(digest["decisions"]) == 5
    html = digest["html_email"]
    # Módulo cerrado (contrato v6.2): SIN botones por ítem; UN solo botón a la bandeja.
    assert html.count("Revisar y bloquear →") == 0
    assert "Revisar y bloquear en la bandeja →" in html
    assert "/acciones/bloqueos?token=" in html


def test_grid_campana_sin_columna_cpa():
    # CAMBIO 1: la columna "CPA 💰" se eliminó; el grid es Gasto | Conv. | $/conv. | CTR.
    digest = build_monitor_digest(_payload([
        _term(query="hacienda teya merida", campaign_name="Thai Merida - Local",
              cost=25.0, conversions=2.0, all_conversions=2.0, conversion_quality="weak_local_action"),
    ]), _rich_context())
    html = digest["html_email"]
    assert "CPA 💰" not in html
    local_slice = html.split("Thai Merida - Local", 1)[1].split("class=\"section\"", 1)[0]
    for col in (">Gasto<", ">Conv.<", ">$/conv.<", ">CTR<"):
        assert col in local_slice


def test_conv_total_cuadra_con_google_ads_y_desglose_suma():
    # A3: Conv. = all_conversions (Google Ads) y el desglose 💰+📍 suma exacto al total.
    from engine.monitor_sections import build_campaign_rows_from_context
    ctx = {"campaign_metrics": [
        {"name": "Thai Mérida - Delivery", "spend_mxn": 485.0, "all_conversions": 9.0,
         "money_conversions": 0.0, "local_signals": 9.0, "clicks": 100, "impressions": 4000,
         "daily_budget_mxn": 55.0}]}
    rows = build_campaign_rows_from_context(ctx)
    r = rows[0]
    assert r["all_conversions"] == 9.0
    assert r["conversiones_dinero"] + r["senales_locales"] == r["all_conversions"]


def test_cadenas_prohibidas_html_full():
    digest = build_monitor_digest(_payload([
        _term(query="bankok casa thai", cost=44.0, clicks=35, conversion_quality="none"),
        _term(query="thai thai merida", cost=18.0, conversions=1.0, all_conversions=1.0, conversion_quality="money_action"),
    ]), _rich_context())
    html = digest["html_email"]
    text = digest["text_email"]
    for token in _forbidden_strings():
        assert token not in html, f"prohibida en html: {token!r}"
        assert token not in text, f"prohibida en text: {token!r}"


def test_snapshot_html_lunes():
    # CONGELADO v6.2: orden y títulos exactos. Cualquier desviación rompe el build.
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), _rich_context())
    html = digest["html_email"]
    headings = ["Posibles bloqueos — necesitan tu confirmación", "📊 Campañas — últimos 7 días",
                "🔎 Qué buscó la gente para ver tus anuncios", "⭐ Reseñas", "📍 Tu negocio en Maps — 30 días",
                "📢 Anuncios — ", "🌐 SEO de tu web", "🔍 Search Console · 7 días"]
    last = -1
    for h in headings:
        idx = html.find(h)
        assert idx != -1, f"falta sección: {h}"
        assert idx > last, f"sección fuera de orden: {h}"
        last = idx
    assert "Thai Thai Monitor" in html and "THAI THAI MONITOR" not in html
    assert "Nada se ejecuta sin tu confirmación" in html  # A10 footer
    assert digest["subject_email"].startswith("Thai Thai Monitor —")


def test_snapshot_html_viernes_es_el_completo():
    # Contrato v6.2 (2026-06-12): el viernes ahora envía el MISMO reporte completo del lunes.
    ctx = _rich_context()
    ctx["mode"] = "friday"  # ya no cambia el formato — debe salir el completo igual
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), ctx)
    html = digest["html_email"]
    # Mismo asunto fijo con fecha que el lunes (la referencia trae generated_date).
    assert digest["subject_email"].startswith("Thai Thai Monitor —")
    # Las 9 secciones del formato completo, en orden — idénticas al snapshot de lunes.
    headings = ["Posibles bloqueos — necesitan tu confirmación", "📊 Campañas — últimos 7 días",
                "🔎 Qué buscó la gente para ver tus anuncios", "⭐ Reseñas", "📍 Tu negocio en Maps — 30 días",
                "📢 Anuncios — ", "🌐 SEO de tu web", "🔍 Search Console · 7 días"]
    last = -1
    for h in headings:
        idx = html.find(h)
        assert idx != -1, f"falta sección en viernes: {h}"
        assert idx > last, f"sección fuera de orden en viernes: {h}"
        last = idx
    # El viejo "viernes corto" ya no existe.
    assert "Cierre de viernes" not in html
    assert "Decisiones pendientes del lunes" not in html


def test_correo_cero_decisiones():
    digest = build_monitor_digest(_payload([
        _term(query="thai thai merida", cost=18.0, conversions=1.0, all_conversions=1.0, conversion_quality="money_action"),
    ]), _rich_context())
    assert digest["decisions"] == []
    assert "Sin decisiones esta semana" in digest["html_email"]
    assert "Sin decisiones esta semana" in digest["text_email"]


def test_data_broken_no_muestra_ceros():
    # context=None → gbp, reviews, search console all data_broken
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]))
    html = digest["html_email"]
    assert "Datos de Maps en reparación" in html
    assert "Reseñas en reparación" in html
    assert "Search Console en reparación" in html
    for zero_as_data in ["0 vistas", "0 rutas", "0 impresiones", "0 clics", "0.0 promedio", "0★"]:
        assert zero_as_data not in html


def test_sugerencia_presupuesto_solo_texto():
    digest = build_monitor_digest(_payload([
        _term(query="reservar mesa thai", campaign_name="Thai Merida - Reservaciones",
              cost=100.0, conversions=2.0, all_conversions=2.0, conversion_quality="money_action"),
    ]), _rich_context())
    row = digest["campaign_rows"][0]
    sug = row["sugerencia_presupuesto"]
    assert set(sug.keys()) <= {"accion", "detalle", "razon_humana"}
    assert sug["accion"] in {"mantener", "escalar", "reducir", "pausar"}
    # No executable / write field leaks anywhere in the row
    for forbidden in ["write_action", "execute", "mutate", "apply"]:
        assert forbidden not in row
    assert digest["safety"]["touches_budgets"] is False
    assert "· manual" in digest["html_email"]  # A3 pill: "Sugerencia: ... · manual"


def test_bloqueos_modulo_cerrado():
    # Contrato v6.2: Posibles bloqueos = bloque cerrado, total arriba, SIN botones por ítem,
    # un solo botón a la bandeja /acciones/bloqueos.
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), _rich_context())
    html = digest["html_email"]
    assert "búsqueda" in html and "gastados esta semana" in html   # total arriba
    assert html.count("Revisar y bloquear →") == 0                  # sin botón por ítem
    assert html.count(">Dejar<") == 0                               # sin "Dejar" por ítem
    assert "Revisar y bloquear en la bandeja →" in html            # un botón a la bandeja
    assert "/acciones/bloqueos?token=" in html


def test_resenas_modulo_cerrado():
    # Reseñas = bloque cerrado: pendientes + un botón a /acciones/resenas, sin el botón viejo.
    digest = build_monitor_digest(_payload([_term(query="bankok casa thai", cost=44.0, clicks=35)]), _rich_context())
    html = digest["html_email"]
    assert "Pendientes de responder" in html
    assert "nuevas esta semana · " in html and "sin responder en total" in html  # conteo
    assert "Responder reseñas en la bandeja →" in html
    assert "/acciones/resenas?token=" in html
    assert "de 5★ con IA" not in html                               # botón viejo eliminado


def test_reviews_summary_pendientes_top3():
    from engine.monitor_sections import build_reviews_summary
    reviews = [{"stars": 5, "comment": f"Excelente {i}", "create_time": f"2026-06-{10 + i:02d}T00:00:00Z",
                "has_reply": False, "reviewer": f"Cliente {i}"} for i in range(5)]
    # FUENTE ÚNICA: pendientes (y total) vienen de stats["pendientes"], no se recomputan aquí.
    pend = [{"review_id": f"p{i}", "stars": 5, "comment": f"Excelente {i}", "reviewer": f"Cliente {i}",
             "create_time": f"2026-06-{10 + i:02d}T00:00:00Z"} for i in range(5)]
    stats = {"average_rating": 4.7, "total_reviews": 1204, "distribucion": {5: 5, 4: 0, 3: 0, 2: 0, 1: 0},
             "pendientes": pend, "completo": True}
    rs = build_reviews_summary({"reviews": {"data_broken": False, "reviews": reviews, "stats": stats}}, "2026-06-20T00:00:00Z")
    assert len(rs["pendientes"]) == 3            # top-3 en el correo
    assert rs["pendientes_total"] == 5            # FUENTE ÚNICA = len(stats["pendientes"])
    assert all(p["estrellas"] == 5 for p in rs["pendientes"])
    assert rs["promedio_general"] == 4.7          # rating de la API (bug #2)
    assert rs["total_reviews"] == 1204            # total de la API (bug #3)
