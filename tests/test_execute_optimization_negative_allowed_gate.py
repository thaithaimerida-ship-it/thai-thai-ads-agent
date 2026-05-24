import os
import sys
from copy import deepcopy
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


TOKEN = "test-token-negative-gate"


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


def _post(client, actions, **payload):
    body = {"actions": actions}
    body.update(payload)
    return client.post(
        "/execute-optimization",
        headers={"X-API-Token": TOKEN},
        json=body,
    )


def _block_action(**overrides):
    action = {
        "type": "block_keyword",
        "keyword": "hacienda teya",
        "campaign_id": "111",
        "match_type": "EXACT",
    }
    action.update(overrides)
    return action


def _setup(monkeypatch, tmp_path, rows=None, gate_status="success"):
    import routes.analysis as analysis

    add_negative = MagicMock(side_effect=_ank)
    gate = MagicMock(return_value={
        "status": gate_status,
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


def _rejected_result(response):
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "rejected"
    return result


def test_block_keyword_allows_when_suggested_negative_campaign_and_match_type_match(monkeypatch, tmp_path):
    add_negative, gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [_block_action()])

    assert response.status_code == 200
    add_negative.assert_called_once()
    assert add_negative.call_args.args[2:4] == ("111", "hacienda teya")
    assert add_negative.call_args.kwargs["match_type"] == "EXACT"
    assert response.json()["results"][0]["status"] == "executed"
    gate.assert_called_once_with("LAST_7_DAYS")


def test_block_keyword_rejects_when_keyword_matches_query_but_not_suggested_negative(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [_block_action(keyword="restaurante hacienda teya")])

    result = _rejected_result(response)
    assert result["reason"] == "suggested_negative_not_found"
    add_negative.assert_not_called()


def test_block_keyword_rejects_suggested_negative_missing(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(suggested_negative=None)])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "suggested_negative_not_found"
    add_negative.assert_not_called()


def test_block_keyword_rejects_campaign_mismatch(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [_block_action(campaign_id="222")])

    result = _rejected_result(response)
    assert result["reason"] == "suggested_negative_not_found"
    add_negative.assert_not_called()


def test_block_keyword_rejects_match_type_mismatch(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(suggested_match_type="PHRASE")])

    response = _post(_client(), [_block_action(match_type="EXACT")])

    result = _rejected_result(response)
    assert result["reason"] == "match_type_mismatch"
    add_negative.assert_not_called()


def test_block_keyword_rejects_broad(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(suggested_match_type="BROAD")])

    response = _post(_client(), [_block_action(match_type="BROAD")])

    result = _rejected_result(response)
    assert result["reason"] == "broad_not_allowed"
    add_negative.assert_not_called()


def test_block_keyword_rejects_negative_allowed_false(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(negative_allowed=False)])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "negative_allowed_false"
    add_negative.assert_not_called()


def test_block_keyword_rejects_base_negative_eligible_false(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(base_negative_eligible=False)])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "base_negative_eligible_false"
    add_negative.assert_not_called()


def test_block_keyword_rejects_semantic_class_not_red_safe(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(semantic_class="external_entity_review")])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "semantic_class_not_red_safe"
    add_negative.assert_not_called()


def test_block_keyword_rejects_conversion_quality_unknown(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(conversion_quality="unknown")])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "conversion_quality_unknown"
    add_negative.assert_not_called()


def test_block_keyword_rejects_conversion_quality_money_action(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(conversion_quality="money_action")])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "conversion_quality_money_action"
    add_negative.assert_not_called()


def test_block_keyword_rejects_already_negative_true(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row(already_negative=True)])

    response = _post(_client(), [_block_action()])

    result = _rejected_result(response)
    assert result["reason"] == "already_negative_true"
    add_negative.assert_not_called()


def test_block_keyword_rejects_metadata_missing(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[_valid_row()])
    cases = [
        ("campaign_id", _block_action(campaign_id=None), "missing_campaign_id"),
        ("keyword", _block_action(keyword=None), "missing_keyword"),
        ("match_type", _block_action(match_type=None), "missing_match_type"),
    ]

    client = _client()
    for _field, action, reason in cases:
        response = _post(client, [action])
        result = _rejected_result(response)
        assert result["reason"] == reason

    add_negative.assert_not_called()


def test_block_keyword_rejects_row_metadata_missing_fail_closed(monkeypatch, tmp_path):
    fields = [
        ("campaign_id", "suggested_negative_not_found"),
        ("suggested_negative", "suggested_negative_not_found"),
        ("suggested_match_type", "suggested_match_type_invalid"),
        ("negative_allowed", "negative_allowed_false"),
        ("base_negative_eligible", "base_negative_eligible_false"),
        ("already_negative", "already_negative_missing"),
        ("conversion_quality", "conversion_quality_missing"),
    ]
    client = _client()
    for field, reason in fields:
        row = _valid_row()
        row.pop(field)
        add_negative, _gate = _setup(monkeypatch, tmp_path, rows=[row])
        response = _post(client, [_block_action()])
        result = _rejected_result(response)
        assert result["reason"] == reason
        add_negative.assert_not_called()


def test_block_keyword_uses_default_last_7_days_when_date_range_missing(monkeypatch, tmp_path):
    _add_negative, gate = _setup(monkeypatch, tmp_path)

    _post(_client(), [_block_action()])

    gate.assert_called_once_with("LAST_7_DAYS")


def test_block_keyword_accepts_valid_date_range(monkeypatch, tmp_path):
    _add_negative, gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [_block_action()], date_range="LAST_14_DAYS")

    assert response.status_code == 200
    gate.assert_called_once_with("LAST_14_DAYS")


def test_block_keyword_rejects_invalid_date_range(monkeypatch, tmp_path):
    add_negative, gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [_block_action()], date_range="FOREVER")

    result = _rejected_result(response)
    assert result["reason"] == "invalid_date_range"
    gate.assert_not_called()
    add_negative.assert_not_called()


def test_gate_payload_built_once_for_batch(monkeypatch, tmp_path):
    add_negative, gate = _setup(
        monkeypatch,
        tmp_path,
        rows=[
            _valid_row(),
            _valid_row(
                query="receta pad thai",
                suggested_negative="receta pad thai",
                suggested_match_type="PHRASE",
            ),
        ],
    )

    response = _post(_client(), [
        _block_action(),
        _block_action(keyword="receta pad thai", match_type="PHRASE"),
    ])

    assert response.status_code == 200
    assert add_negative.call_count == 2
    gate.assert_called_once_with("LAST_7_DAYS")


def test_non_block_keyword_action_does_not_build_gate(monkeypatch, tmp_path):
    add_negative, gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [{"type": "pause_campaign", "campaign_id": "111"}], date_range="FOREVER")

    assert response.status_code == 200
    gate.assert_not_called()
    add_negative.assert_not_called()


def test_non_block_keyword_action_behavior_unchanged(monkeypatch, tmp_path):
    add_negative, _gate = _setup(monkeypatch, tmp_path)

    response = _post(_client(), [{"type": "pause_campaign", "campaign_id": "111", "reason": "test"}])

    assert response.status_code == 200
    add_negative.assert_not_called()
    result = response.json()["results"][0]
    assert result["status"] == "recorded"
    assert result["manual_required"] is True
