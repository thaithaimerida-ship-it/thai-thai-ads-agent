import asyncio


def _term(**overrides):
    term = {
        "query": "hacienda teya merida",
        "campaign_name": "Thai Merida - Delivery Search",
        "clicks": 20,
        "cost": 150.0,
        "conversions": 0.0,
        "conversion_quality": "none",
        "semantic_class": "red_safe",
        "already_negative": False,
        "suggested_match_type": "EXACT",
        "negative_allowed": True,
        "base_negative_eligible": True,
    }
    term.update(overrides)
    return term


def test_weak_local_action_revisar_con_cuidado_no_bloqueable():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(conversion_quality="weak_local_action"))

    assert item["state"] == "revisar_con_cuidado"
    assert item["recommended_action"] == "no_action"
    assert item["block_allowed"] is False
    assert "pidieron como llegar o llamaron" in item["reason_human"]


def test_money_action_protegido_no_bloqueable():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(conversion_quality="money_action"))

    assert item["state"] == "protegido"
    assert item["recommended_action"] == "no_action"
    assert item["block_allowed"] is False
    assert "accion de valor" in item["reason_human"]


def test_unknown_conversion_quality_protegido_no_bloqueable():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(conversion_quality="unknown"))

    assert item["state"] == "protegido"
    assert item["block_allowed"] is False
    assert "Si hay duda, no se bloquea" in item["reason_human"]


def test_already_negative_no_bloqueable():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(already_negative=True))

    assert item["state"] == "bloqueado"
    assert item["block_allowed"] is False


def test_brand_and_thai_intent_protegidos():
    from engine.negatives_preview_v2 import present_negative_term

    for semantic_class, query in [
        ("brand_protected", "thai thai"),
        ("thai_intent", "comida tailandesa merida"),
        ("thai_intent", "restaurante tailandes"),
        ("thai_intent", "thai food merida"),
    ]:
        item = present_negative_term(_term(query=query, semantic_class=semantic_class))
        assert item["state"] == "protegido"
        assert item["is_protected"] is True
        assert item["block_allowed"] is False


def test_ambiguous_useful_protegido():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(query="donde comer en merida", semantic_class="ambiguous_useful"))

    assert item["state"] == "protegido"
    assert item["is_protected"] is True
    assert item["block_allowed"] is False
    assert "puede traer clientes nuevos" in item["reason_human"]


def test_external_entity_review_competidor_por_confirmar():
    from engine.negatives_preview_v2 import present_negative_term

    for query in ["chaya maya merida", "toks merida"]:
        item = present_negative_term(_term(query=query, semantic_class="external_entity_review"))
        assert item["state"] == "competidor_por_confirmar"
        assert item["recommended_action"] == "needs_confirmation"
        assert item["block_allowed"] is False


def test_red_safe_none_below_floor_datos_insuficientes():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(clicks=8, cost=142.0))

    assert item["enough_data"] is False
    assert item["data_floor_reason"] == "No tiene suficientes clics para decidir."
    assert item["state"] == "datos_insuficientes"
    assert item["block_allowed"] is False


def test_red_safe_none_enough_data_listo_para_bloquear():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(clicks=12, cost=120.0))

    assert item["enough_data"] is True
    assert item["state"] == "listo_para_bloquear"
    assert item["recommended_action"] == "propose_block"
    assert item["block_allowed"] is True
    assert item["suggested_match_type"] == "EXACT"


def test_broad_jamas_bloqueable():
    from engine.negatives_preview_v2 import present_negative_term

    item = present_negative_term(_term(suggested_match_type="BROAD", negative_allowed=True))

    assert item["suggested_match_type"] == "BROAD"
    assert item["block_allowed"] is False
    assert item["recommended_action"] == "no_action"


def test_env_floor_uses_and_not_or(monkeypatch):
    from engine.negatives_preview_v2 import present_negative_term

    monkeypatch.setenv("NEGATIVES_CLICKS_MIN", "12")
    monkeypatch.setenv("NEGATIVES_COST_MIN_MXN", "120")

    enough_clicks_only = present_negative_term(_term(clicks=12, cost=119.99))
    enough_cost_only = present_negative_term(_term(clicks=11, cost=120.0))

    assert enough_clicks_only["enough_data"] is False
    assert enough_cost_only["enough_data"] is False


def test_build_preview_payload_keeps_existing_search_terms_compat_fields():
    from engine.negatives_preview_v2 import build_negatives_preview_payload

    payload = {
        "status": "success",
        "date_range": "LAST_7_DAYS",
        "search_terms": [_term(query="receta pad thai", clicks=13, cost=121.0)],
    }

    result = build_negatives_preview_payload(payload)

    assert result["status"] == "success"
    assert result["date_range"] == "LAST_7_DAYS"
    assert result["total"] == 1
    assert result["items"][0]["term"] == "receta pad thai"
    assert "search_terms" not in result


def test_preview_endpoint_is_read_only_and_uses_search_terms_payload(monkeypatch):
    import routes.analysis as analysis

    calls = []

    def fake_build(date_range="LAST_7_DAYS"):
        calls.append(date_range)
        return {
            "status": "success",
            "date_range": date_range,
            "search_terms": [_term(clicks=12, cost=120.0)],
        }

    monkeypatch.setattr(analysis, "_build_search_terms_payload", fake_build)

    result = asyncio.run(analysis.negativos_preview_v2(date_range="LAST_14_DAYS"))

    assert calls == ["LAST_14_DAYS"]
    assert result["status"] == "success"
    assert result["items"][0]["state"] == "listo_para_bloquear"
