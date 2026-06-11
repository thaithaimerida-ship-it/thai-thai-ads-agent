import asyncio
import inspect
import json
from pathlib import Path


def _term(**overrides):
    term = {
        "query": "restaurante cerca de mi",
        "campaign_name": "Thai Merida - Delivery Search",
        "campaign_id": "111",
        "clicks": 40,
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
    return {
        "status": "success",
        "date_range": date_range,
        "search_terms": terms,
    }


def test_dinero_y_senales_nunca_se_suman():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(
            query="thai thai merida",
            cost=18.0,
            conversions=1.0,
            all_conversions=1.0,
            conversion_quality="money_action",
        ),
        _term(
            query="hacienda teya merida",
            cost=25.0,
            conversions=2.0,
            all_conversions=2.0,
            conversion_quality="weak_local_action",
        ),
        _term(
            query="bangkok casa thai",
            campaign_name="Thai Merida - Experiencia 2026",
            cost=92.5,
            clicks=8,
            conversion_quality="none",
        ),
    ]))

    assert digest["summary"]["money_signal_cost_mxn"] == 18.0
    assert digest["summary"]["local_signal_cost_mxn"] == 25.0
    assert digest["summary"]["negative_leak_cost_mxn"] == 92.5
    assert digest["summary"]["protected_cost_mxn"] == 18.0
    assert digest["summary"]["money_signal_cost_mxn"] != (
        digest["summary"]["local_signal_cost_mxn"]
        + digest["summary"]["negative_leak_cost_mxn"]
    )


def test_maximo_5_decisiones():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query=f"restaurante externo {i}", clicks=3, cost=20 + i, conversion_quality="none")
        for i in range(8)
    ], date_range="LAST_30_DAYS"))

    assert digest["summary"]["decisions_count"] == 5
    assert len(digest["decisions"]) == 5
    assert digest["max_decisions"] == 5
    assert all(d["decision_type"] == "external_review" for d in digest["decisions"])
    assert all(d["identity_label"] == "Restaurante externo" for d in digest["decisions"])


def test_casa_thai_todas_las_variantes_competidor_confirmado():
    from engine.monitor_digest_v3 import build_monitor_digest, load_term_dictionary

    variants = [
        "casa thai",
        "casa thai merida",
        "casa thai mérida",
        "bangkok casa thai",
        "bangkok casa thai merida",
        "bangkok casa thai mérida",
        "bankok casa thai",
        "bankok casa thai merida",
        "bankok casa thai mérida",
        "BANGKOK CASA THAI MÉRIDA",
    ]
    digest = build_monitor_digest(_payload([
        _term(query=variant, cost=10 + i, clicks=35 + i, conversion_quality="none")
        for i, variant in enumerate(variants)
    ]))

    # B-4: all Casa Thai variants collapse into ONE grouped decision.
    assert len(digest["decisions"]) == 1
    decision = digest["decisions"][0]
    assert decision["decision_type"] == "negative_leak"
    assert decision["identity_axis"] == "restaurante_externo"
    assert decision["confirmado_por_hugo"] is True
    assert decision["alta_prioridad"] is True
    assert decision["suggested_match_type"] == "EXACT"
    assert decision["write_action"] is None
    assert decision["block_allowed"] is False
    assert decision["variantes_count"] == len(variants)
    assert "bankok casa thai" in decision["variantes"]

    dictionary = load_term_dictionary()
    groups = dictionary["term_groups"]
    assert len(groups["confirmed_competitors"]) == 9
    assert len(groups["casa_thai_variants"]) == 9
    assert "bankok casa thai" in groups["casa_thai_variants"]
    assert "casa thai mérida" in groups["casa_thai_variants"]


def test_negativo_con_fuga_detectado():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(
            query="receta pad thai",
            clicks=80,
            cost=300.0,
            conversions=0.0,
            all_conversions=0.0,
            conversion_quality="none",
            suggested_match_type="PHRASE",
        )
    ]))

    assert digest["summary"]["negative_leak_cost_mxn"] == 300.0
    assert digest["summary"]["decisions_count"] == 1
    decision = digest["decisions"][0]
    assert decision["decision_type"] == "negative_leak"
    assert decision["term"] == "receta pad thai"
    assert decision["recommended_action"] == "review_one_by_one"
    assert decision["write_action"] is None
    assert decision["block_allowed"] is False


def test_campana_sin_dinero_no_tiene_cpa():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query="hacienda teya merida", cost=25.0, conversion_quality="weak_local_action"),
        _term(query="vips cerca de mi", cost=10.0, conversion_quality="none"),
    ]))

    digest_json = json.dumps(digest, ensure_ascii=False).lower()
    assert digest["summary"]["money_signal_cost_mxn"] == 0.0
    assert digest["campaign_rows"][0]["money_cpa_mxn"] is None
    assert "cpa_mxn" in digest_json


def test_no_legacy_fields_in_digest():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(
            query="receta pad thai",
            semantic_class="red_safe",
            negative_allowed=True,
            base_negative_eligible=True,
            candidate_negative=True,
            legacy=True,
            cost=40.0,
        )
    ]))

    digest_json = json.dumps(digest, ensure_ascii=False)
    for field in [
        "semantic_class",
        "red_safe",
        "negative_allowed",
        "base_negative_eligible",
        "legacy",
        "candidate_negative",
    ]:
        assert field not in digest_json


def test_no_write_fields():
    from engine.monitor_digest_v3 import build_monitor_digest
    import routes.monitor as monitor

    digest = build_monitor_digest(_payload([
        _term(query="bankok casa thai", cost=44.0, clicks=35, conversion_quality="none")
    ]))
    digest_json = json.dumps(digest, ensure_ascii=False)
    source = Path("engine/monitor_digest_v3.py").read_text(encoding="utf-8")
    route_source = inspect.getsource(monitor)

    for forbidden in [
        "/execute" + "-optimization",
        "PO" + "ST",
        "add" + "_negative",
        "mut" + "ate",
        "update" + "_budget",
        "apply" + "-budget",
        "budget" + " recommendation",
        "apply" + " negative",
    ]:
        assert forbidden not in digest_json
        assert forbidden not in source
        assert forbidden not in route_source

    assert "@router.get" in route_source
    assert digest["safety"]["writes_google_ads"] is False
    assert digest["safety"]["calls_execute_optimization"] is False
    assert digest["safety"]["touches_budgets"] is False
    assert digest["safety"]["post_required"] is False
    assert all(d["write_action"] is None for d in digest["decisions"])
    assert all(d["block_allowed"] is False for d in digest["decisions"])


def test_monitor_digest_endpoint_is_read_only_and_uses_search_terms_payload(monkeypatch):
    import routes.monitor as monitor

    calls = []

    def fake_build(date_range="LAST_7_DAYS"):
        calls.append(date_range)
        return _payload([
            _term(query="almar restaurante merida", clicks=2, cost=40, conversion_quality="none")
        ], date_range=date_range)

    monkeypatch.setattr(monitor, "_build_search_terms_payload", fake_build)
    monkeypatch.setattr(monitor, "_build_context", lambda date_range, mode: {"mode": "monday", "links": {}})

    result = asyncio.run(monitor.monitor_digest(date_range="LAST_14_DAYS"))

    assert calls == ["LAST_14_DAYS"]
    assert result["status"] == "success"
    assert result["read_only"] is True
    assert result["decisions"][0]["term"] == "almar restaurante merida"


def test_monitor_digest_route_accepts_valid_date_range(monkeypatch):
    import routes.monitor as monitor

    calls = []

    def fake_build(date_range="LAST_7_DAYS"):
        calls.append(date_range)
        return _payload([
            _term(query="vips cerca de mi", clicks=2, cost=40, conversion_quality="none")
        ], date_range=date_range)

    monkeypatch.setattr(monitor, "_build_search_terms_payload", fake_build)
    monkeypatch.setattr(monitor, "_build_context", lambda date_range, mode: {"mode": "monday", "links": {}})

    result = asyncio.run(monitor.monitor_digest(date_range="LAST_7_DAYS"))

    assert calls == ["LAST_7_DAYS"]
    assert result["status"] == "success"


def test_monitor_digest_route_rejects_invalid_date_range(monkeypatch):
    import pytest
    from fastapi import HTTPException
    import routes.monitor as monitor

    calls = []

    def fake_build(date_range="LAST_7_DAYS"):
        calls.append(date_range)
        return _payload([], date_range=date_range)

    monkeypatch.setattr(monitor, "_build_search_terms_payload", fake_build)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(monitor.monitor_digest(date_range="BAD_RANGE"))

    assert exc.value.status_code == 400
    assert "date_range invalido" in exc.value.detail
    assert calls == []


def test_campaign_rows_exist():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(
            query="pedido thai",
            campaign_name="Thai Merida - Delivery Search",
            cost=120.0,
            conversions=2.0,
            all_conversions=2.0,
            conversion_quality="money_action",
        ),
        _term(
            query="hacienda teya merida",
            campaign_name="Thai Merida - Experiencia 2026",
            cost=30.0,
            conversions=0.0,
            all_conversions=3.0,
            conversion_quality="weak_local_action",
        ),
    ]))

    rows = {row["campaign_name"]: row for row in digest["campaign_rows"]}
    delivery = rows["Thai Merida - Delivery Search"]
    local = rows["Thai Merida - Experiencia 2026"]

    assert delivery["spend_mxn"] == 120.0
    assert delivery["money_conversions"] == 2.0
    assert delivery["money_cpa_mxn"] == 60.0
    assert delivery["local_signals"] == 0.0
    assert delivery["local_signal_cost_mxn"] is None
    assert delivery["recommendation_human"] == "Monitorear. No escalar automáticamente."

    assert local["spend_mxn"] == 30.0
    assert local["money_conversions"] == 0.0
    assert local["money_cpa_mxn"] is None
    assert local["local_signals"] == 3.0
    assert local["local_signal_cost_mxn"] == 30.0
    assert local["recommendation_human"] == "Monitorear. No escalar automáticamente."


def test_campaign_without_money_has_no_money_cpa():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(
            query="hacienda teya merida",
            campaign_name="Thai Merida - Experiencia 2026",
            cost=88.0,
            conversions=0.0,
            all_conversions=5.0,
            conversion_quality="weak_local_action",
        )
    ]))

    row = digest["campaign_rows"][0]
    assert row["money_conversions"] == 0.0
    assert row["money_cpa_mxn"] is None
    assert row["local_signals"] == 5.0


def test_click_whatsapp_and_click_pedir_online_are_not_money_unless_explicitly_confirmed():
    from engine.search_term_classifier import classify_conversion_quality

    for action_name in ["click_whatsapp", "click_pedir_online"]:
        actions = [{"name": action_name, "conversions": 1, "all_conversions": 1}]
        assert classify_conversion_quality(actions, conversions=1, all_conversions=1) == "weak_local_action"


def test_negative_leak_has_detail_items():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query="bankok casa thai", cost=44.0, clicks=35, conversion_quality="none")
    ]))

    leaks = [item for item in digest["anomalies"] if item["type"] == "negative_leak"]
    assert leaks
    assert leaks[0]["term"] == "bankok casa thai"
    assert leaks[0]["spend_mxn"] == 44.0
    assert leaks[0]["campaign"] == "Thai Merida - Delivery Search"
    assert leaks[0]["reason_human"] == "Ya existe como negativo o variante relacionada, pero sigue gastando."


def test_anomalies_exist_when_negative_leak_cost_positive():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query="bankok casa thai", cost=44.0, clicks=35, conversion_quality="none")
    ]))

    assert digest["summary"]["negative_leak_cost_mxn"] > 0
    assert any(item["type"] == "negative_leak" for item in digest["anomalies"])
    assert any(item["type"] == "conversion_mapping_incomplete" for item in digest["warnings"])
    assert any(item["type"] == "data_broken" for item in digest["warnings"])


def test_search_terms_summary_exists():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query="thai thai merida", cost=10.0, conversion_quality="none"),
        _term(query="restaurante cerca de mi", cost=12.0, conversion_quality="none"),
        _term(query="comida japonesa merida", cost=14.0, conversion_quality="none"),
        _term(query="vips cerca de mi", cost=16.0, conversion_quality="none"),
        _term(query="hacienda teya merida", cost=18.0, all_conversions=2, conversion_quality="weak_local_action"),
    ]))

    summary = digest["search_terms_summary"]
    assert summary["terminos_revisados"] == 5
    assert summary["marca_intencion_thai_protegida"] == 1
    assert summary["busquedas_utiles"] == 1
    assert summary["busquedas_relacionadas"] == 1
    assert summary["restaurantes_externos_por_confirmar"] == 1
    assert summary["senales_locales"] == 1
    assert summary["decisiones_pendientes"] == digest["summary"]["decisions_count"]
    assert summary["desperdicio_confirmado_mxn"] == 0.0


def test_no_budget_recommendations():
    from engine.monitor_digest_v3 import build_monitor_digest

    digest = build_monitor_digest(_payload([
        _term(query="pedido thai", cost=120.0, conversions=2.0, conversion_quality="money_action")
    ]))
    digest_json = json.dumps(digest, ensure_ascii=False)

    assert "Escalar presupuesto" not in digest_json
    assert "Pausar presupuesto" not in digest_json
    assert "Monitorear. No escalar automáticamente." in digest_json
