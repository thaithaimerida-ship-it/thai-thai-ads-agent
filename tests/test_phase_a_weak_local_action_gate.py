"""Fase A — endurecer el gate de negativos.

Regla nueva: weak_local_action NUNCA es base_negative_eligible ni negative_allowed,
y /execute-optimization lo rechaza con razon explicita. Solo conversion_quality
== "none" sigue siendo elegible (si cumple el resto del gate red_safe/EXACT-PHRASE).

Cubre las dos capas de defensa:
  - Capa 1: engine.search_term_classifier (_compute_base_negative_eligible)
  - Capa 2: routes.analysis (_validate_block_keyword_gate via /execute-optimization)

Ningun test toca Google Ads real: todo es MagicMock + monkeypatch.
"""
import os
import sys
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.search_term_classifier import classify_search_term


# ── Capa 1: clasificador / base_negative_eligible ────────────────────────────

def test_weak_local_action_no_es_base_eligible():
    r = classify_search_term("hacienda teya", conversion_quality="weak_local_action")
    assert r["semantic_class"] == "red_safe"
    assert r["entity_status"] == "curated"
    assert r["suggested_match_type"] == "EXACT"
    assert r["base_negative_eligible"] is False
    assert r["negative_allowed"] is False


def test_none_sigue_siendo_base_eligible():
    r = classify_search_term("hacienda teya", conversion_quality="none")
    assert r["semantic_class"] == "red_safe"
    assert r["base_negative_eligible"] is True   # red_safe curado + EXACT + sin conversiones
    assert r["negative_allowed"] is False         # se completa en /search-terms (already_negative + campaign_id)


def test_money_action_no_es_base_eligible():
    r = classify_search_term("hacienda teya", conversion_quality="money_action")
    assert r["base_negative_eligible"] is False
    assert r["negative_allowed"] is False


def test_unknown_no_es_base_eligible():
    r = classify_search_term("hacienda teya", conversion_quality="unknown")
    assert r["base_negative_eligible"] is False
    assert r["negative_allowed"] is False


# ── Capa 1b: negative_allowed en /search-terms ───────────────────────────────

def _setup_search_terms_endpoint(monkeypatch, terms, breakdown):
    import routes.analysis as analysis

    engine = {
        "get_ads_client": lambda: MagicMock(),
        "fetch_search_term_data": MagicMock(return_value=terms),
    }
    monkeypatch.setattr(analysis, "_get_engine", lambda: engine)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "fetch_negative_keywords", lambda c, cid: {})
    monkeypatch.setattr(analysis, "aggregate_windows", lambda norms: {})
    monkeypatch.setattr(analysis, "accumulated_reds", lambda today_top100_norms: [])
    monkeypatch.setattr(analysis, "fetch_search_term_conversion_breakdown", lambda c, cid, dr: breakdown)


def test_search_terms_weak_local_action_no_queda_negative_allowed(monkeypatch):
    # hacienda teya con engagement local debil (directions) -> NO aplicable.
    terms = [
        {"query": "hacienda teya merida", "campaign_id": "111", "campaign_name": "Delivery Search",
         "cost_micros": 15_750_000, "conversions": 2.0, "all_conversions": 2.0,
         "clicks": 10, "impressions": 80},
    ]
    breakdown = {
        ("hacienda teya merida", "111"): {
            "actions": [{"name": "Local actions - Directions", "conversions": 2, "all_conversions": 2}],
            "conversions": 2,
            "all_conversions": 2,
        },
    }
    _setup_search_terms_endpoint(monkeypatch, terms, breakdown)

    from main import app
    t = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS").json()["search_terms"][0]

    assert t["conversion_quality"] == "weak_local_action"
    assert t["semantic_class"] == "red_safe"
    assert t["base_negative_eligible"] is False
    assert t["negative_allowed"] is False


# ── Capa 2: gate de /execute-optimization ────────────────────────────────────

TOKEN = "test-token-phase-a"


def _valid_row(**overrides):
    row = {
        "query": "restaurante hacienda teya",
        "campaign_id": "111",
        "campaign_name": "Search",
        "suggested_negative": "hacienda teya",
        "suggested_match_type": "EXACT",
        "negative_allowed": True,
        "base_negative_eligible": True,
        "semantic_class": "red_safe",
        "conversion_quality": "none",
        "already_negative": False,
    }
    row.update(overrides)
    return row


def _ank(client, customer_id, campaign_id, keyword_text, match_type=None):
    return {"status": "success", "keyword": keyword_text, "match_type": match_type}


def _block_action(**overrides):
    action = {
        "type": "block_keyword",
        "keyword": "hacienda teya",
        "campaign_id": "111",
        "match_type": "EXACT",
    }
    action.update(overrides)
    return action


def _setup_gate(monkeypatch, tmp_path, rows=None):
    import routes.analysis as analysis

    add_negative = MagicMock(side_effect=_ank)
    gate = MagicMock(return_value={
        "status": "success",
        "date_range": "LAST_7_DAYS",
        "search_terms": rows if rows is not None else [_valid_row()],
    })
    fake_engine = {"get_ads_client": lambda: MagicMock(), "add_negative_keyword": add_negative}

    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "get_db_path", lambda: str(tmp_path / "exec.db"))
    monkeypatch.setattr(analysis, "_get_engine", lambda: fake_engine)
    monkeypatch.setattr(analysis, "_build_search_terms_payload", gate, raising=False)
    return add_negative, gate


def _client():
    from main import app
    return TestClient(app)


def _post(client, actions):
    return client.post("/execute-optimization", headers={"X-API-Token": TOKEN}, json={"actions": actions})


def _rejected_result(response):
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "rejected"
    return result


def test_gate_rechaza_weak_local_action(monkeypatch, tmp_path):
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(conversion_quality="weak_local_action")])
    result = _rejected_result(_post(_client(), [_block_action()]))
    assert result["reason"] == "conversion_quality_weak_local_action"
    add_negative.assert_not_called()


def test_gate_rechaza_money_action(monkeypatch, tmp_path):
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(conversion_quality="money_action")])
    result = _rejected_result(_post(_client(), [_block_action()]))
    assert result["reason"] == "conversion_quality_money_action"
    add_negative.assert_not_called()


def test_gate_rechaza_unknown(monkeypatch, tmp_path):
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(conversion_quality="unknown")])
    result = _rejected_result(_post(_client(), [_block_action()]))
    assert result["reason"] == "conversion_quality_unknown"
    add_negative.assert_not_called()


def test_gate_rechaza_already_negative_true(monkeypatch, tmp_path):
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(already_negative=True)])
    result = _rejected_result(_post(_client(), [_block_action()]))
    assert result["reason"] == "already_negative_true"
    add_negative.assert_not_called()


def test_gate_rechaza_broad(monkeypatch, tmp_path):
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(suggested_match_type="BROAD")])
    result = _rejected_result(_post(_client(), [_block_action(match_type="BROAD")]))
    assert result["reason"] == "broad_not_allowed"
    add_negative.assert_not_called()


def test_gate_permite_red_safe_none_exact(monkeypatch, tmp_path):
    # happy path: red_safe + none + EXACT + campaign_id + already_negative False -> executed
    add_negative, _ = _setup_gate(monkeypatch, tmp_path,
                                  rows=[_valid_row(conversion_quality="none")])
    response = _post(_client(), [_block_action()])
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "executed"
    add_negative.assert_called_once()
