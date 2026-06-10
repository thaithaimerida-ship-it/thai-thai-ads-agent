import asyncio


def _term(**overrides):
    term = {
        "query": "restaurante cerca de mi",
        "campaign_name": "Thai Merida - Delivery Search",
        "campaign_id": "111",
        "clicks": 40,
        "cost": 999.0,
        "conversions": 0.0,
        "conversion_quality": "none",
        "semantic_class": "neutral",
        "already_negative": False,
        "suggested_match_type": "EXACT",
    }
    term.update(overrides)
    return term


def test_golden_examples_identity_and_ui_state():
    from engine.negatives_classifier_v3 import classify_negative_v3

    cases = [
        ("hacienda teya merida", "weak_local_action", "restaurante_externo", "senal_local", "Señal local: revisar con cuidado"),
        ("restaurante hacienda teya", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("tabom", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("gio restaurante cerca de mi", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("comida japonesa merida", "none", "categoria_asiatica", "sin_conversion", "Búsqueda relacionada"),
        ("comida japonesa cerca de mi", "none", "categoria_asiatica", "sin_conversion", "Búsqueda relacionada"),
        ("comida china cerca de mi", "none", "categoria_asiatica", "sin_conversion", "Búsqueda relacionada"),
        ("chinese food near me open now", "none", "categoria_asiatica", "sin_conversion", "Búsqueda relacionada"),
        ("comida asiatica merida", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
        ("restaurante cerca de mi", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
        ("comida cerca de mi", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
        ("thai thai merida", "none", "marca_propia", "sin_conversion", "Marca protegida"),
        ("restaurante thai thai", "none", "marca_propia", "sin_conversion", "Marca protegida"),
        ("comida tailandesa merida", "none", "intencion_thai", "sin_conversion", "Marca protegida"),
        ("thai food merida", "none", "intencion_thai", "sin_conversion", "Marca protegida"),
        ("comida tailandesa cerca de mi", "none", "intencion_thai", "sin_conversion", "Marca protegida"),
        ("yakuza merida", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("casa chaya merida", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("lians merida", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("vips cerca de mi", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("chaya maya merida", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("toks merida", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("win chang caucel", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("amada mía bistro café caucel", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("habaneros restaurante cerca de mi", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("1122 restaurante cerca de mi", "none", "restaurante_externo", "sin_conversion", "Restaurante externo por confirmar"),
        ("restaurantes near me", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
        ("food near me", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
        ("lugares comida cerca de mi", "none", "generico_util", "sin_conversion", "Búsqueda útil"),
    ]

    for query, conversion_quality, identity, behavior, state in cases:
        item = classify_negative_v3(_term(query=query, conversion_quality=conversion_quality))
        assert item["identity_axis"] == identity, query
        assert item["behavior_axis"] == behavior, query
        assert item["state_ui"] == state, query
        assert item["block_allowed"] is False, query


def test_insufficient_external_restaurants_show_external_review_state_not_insufficient():
    from engine.negatives_classifier_v3 import classify_negative_v3

    for query in [
        "tabom",
        "fiesta brava",
        "yakuza merida",
        "casa chaya merida",
        "lians merida",
        "vips cerca de mi",
    ]:
        item = classify_negative_v3(_term(query=query, clicks=3, cost=25.0))
        assert item["identity_axis"] == "restaurante_externo", query
        assert item["data_axis"] == "insuficiente", query
        assert item["state_ui"] == "Restaurante externo por confirmar", query
        assert item["recommended_action"] == "no_action", query
        assert item["block_allowed"] is False, query
        assert item["reason_human"] == (
            "Parece otro restaurante o negocio. "
            "Aún no hay datos suficientes para decidir bloqueo."
        ), query


def test_hugo_confirmed_casa_thai_entities_are_high_priority_exact_read_only_candidates():
    from engine.negatives_classifier_v3 import classify_negative_v3

    for query in [
        "casa thai",
        "casa thai merida",
        "bangkok casa thai",
        "bangkok casa thai merida",
        "bankok casa thai",
        "bankok casa thai merida",
    ]:
        item = classify_negative_v3(_term(query=query, clicks=3, suggested_match_type=None))
        assert item["identity_axis"] == "restaurante_externo", query
        assert item["data_axis"] == "insuficiente", query
        assert item["state_ui"] == "Restaurante externo por confirmar", query
        assert item["recommended_action"] == "no_action", query
        assert item["block_allowed"] is False, query
        assert item["confirmado_por_hugo"] is True, query
        assert item["alta_prioridad"] is True, query
        assert item["suggested_match_type"] == "EXACT", query
        assert item["priority_score"] >= 10000, query
        assert item["auto_apply"] is False, query


def test_hugo_confirmed_casa_thai_is_never_broad_or_automatic():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="bangkok casa thai merida", clicks=35, suggested_match_type="BROAD"))

    assert item["identity_axis"] == "restaurante_externo"
    assert item["suggested_match_type"] == "EXACT"
    assert item["confirmado_por_hugo"] is True
    assert item["alta_prioridad"] is True
    assert item["block_allowed"] is False
    assert item["auto_apply"] is False


def test_fiesta_brava_is_not_blocked_by_doubt_or_external_review():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="fiesta brava"))

    assert item["identity_axis"] in {"restaurante_externo", "desconocido"}
    assert item["state_ui"] in {"Restaurante externo por confirmar", "No bloquear por duda"}
    assert item["block_allowed"] is False


def test_money_signal_never_blockable_even_if_clear_junk_and_enough_clicks():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="receta pad thai", conversion_quality="money_action", clicks=80))

    assert item["behavior_axis"] == "senal_dinero"
    assert item["state_ui"] == "No bloquear por duda"
    assert item["block_allowed"] is False
    assert "señal de valor" in item["reason_human"]


def test_local_signal_never_blockable_and_overrides_external_restaurant():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="hacienda teya merida", conversion_quality="weak_local_action", clicks=80))

    assert item["identity_axis"] == "restaurante_externo"
    assert item["behavior_axis"] == "senal_local"
    assert item["state_ui"] == "Señal local: revisar con cuidado"
    assert item["block_allowed"] is False
    assert "rutas" in item["reason_human"]
    assert "Maps" in item["reason_human"]


def test_generic_and_asian_related_are_not_blockable():
    from engine.negatives_classifier_v3 import classify_negative_v3

    for query, identity, state in [
        ("restaurantes near me", "generico_util", "Búsqueda útil"),
        ("comida japonesa merida", "categoria_asiatica", "Búsqueda relacionada"),
    ]:
        item = classify_negative_v3(_term(query=query, clicks=100, cost=5000))
        assert item["identity_axis"] == identity
        assert item["state_ui"] == state
        assert item["block_allowed"] is False


def test_clicks_below_35_is_insufficient_and_cost_does_not_make_it_sufficient():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="receta pad thai", clicks=34, cost=99999.0))

    assert item["data_axis"] == "insuficiente"
    assert item["state_ui"] == "Datos insuficientes"
    assert item["block_allowed"] is False


def test_cost_does_not_change_block_allowed_when_clicks_and_identity_are_same():
    from engine.negatives_classifier_v3 import classify_negative_v3

    cheap = classify_negative_v3(_term(query="receta pad thai", clicks=35, cost=1.0))
    expensive = classify_negative_v3(_term(query="receta pad thai", clicks=35, cost=99999.0))

    assert cheap["data_axis"] == "suficiente"
    assert expensive["data_axis"] == "suficiente"
    assert cheap["block_allowed"] is expensive["block_allowed"]
    assert cheap["priority_score"] < expensive["priority_score"]


def test_broad_never_block_allowed():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="receta pad thai", clicks=80, suggested_match_type="BROAD"))

    assert item["identity_axis"] == "basura"
    assert item["state_ui"] == "Basura clara"
    assert item["block_allowed"] is False


def test_clear_junk_with_enough_clicks_can_be_future_candidate_read_only_flag():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="receta pad thai", clicks=80, suggested_match_type="PHRASE"))

    assert item["identity_axis"] == "basura"
    assert item["data_axis"] == "suficiente"
    assert item["state_ui"] == "Basura clara"
    assert item["recommended_action"] == "future_review_candidate"
    assert item["block_allowed"] is True


def test_external_restaurant_without_hugo_confirmation_is_not_blockable_even_with_enough_clicks():
    from engine.negatives_classifier_v3 import classify_negative_v3

    item = classify_negative_v3(_term(query="hacienda teya merida", clicks=80))

    assert item["identity_axis"] == "restaurante_externo"
    assert item["state_ui"] == "Restaurante externo por confirmar"
    assert item["block_allowed"] is False


def test_build_preview_v3_payload_contract():
    from engine.negatives_classifier_v3 import build_negatives_preview_v3_payload

    payload = {
        "status": "success",
        "date_range": "LAST_7_DAYS",
        "search_terms": [_term(query="thai thai merida"), _term(query="receta pad thai", clicks=80)],
    }

    result = build_negatives_preview_v3_payload(payload)

    assert result["status"] == "success"
    assert result["date_range"] == "LAST_7_DAYS"
    assert result["data_floor"] == {"clicks_min": 35}
    assert result["total"] == 2
    assert result["items"][0]["identity_axis"] == "marca_propia"
    assert result["items"][1]["state_ui"] == "Basura clara"
    assert "search_terms" not in result


def test_preview_v3_endpoint_is_read_only_and_uses_search_terms_payload(monkeypatch):
    import routes.analysis as analysis

    calls = []

    def fake_build(date_range="LAST_7_DAYS"):
        calls.append(date_range)
        return {
            "status": "success",
            "date_range": date_range,
            "search_terms": [_term(query="comida japonesa merida", clicks=40)],
        }

    monkeypatch.setattr(analysis, "_build_search_terms_payload", fake_build)

    result = asyncio.run(analysis.negativos_preview_v3(date_range="LAST_14_DAYS"))

    assert calls == ["LAST_14_DAYS"]
    assert result["status"] == "success"
    assert result["items"][0]["identity_axis"] == "categoria_asiatica"
    assert result["items"][0]["block_allowed"] is False
