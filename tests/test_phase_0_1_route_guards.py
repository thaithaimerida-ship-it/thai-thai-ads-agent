import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


TOKEN = "phase-0-1-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    from main import app
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/deploy-campaign", {"config": {}}),
        ("post", "/deploy-pending/abc123", None),
        ("post", "/restructure-campaigns", None),
        ("post", "/create-reservations-campaign", None),
        ("post", "/update-ad-schedule", None),
        ("post", "/run-quick-wins", None),
        ("post", "/fix-tracking", None),
        ("post", "/fix-tracking/confirm", {"conversion_action_ids": []}),
    ],
)
def test_mutating_routes_require_token(client, method, path, json_body):
    request = getattr(client, method)
    resp = request(path, json=json_body) if json_body is not None else request(path)
    assert resp.status_code == 401


def test_build_campaign_auto_deploy_requires_token_before_builder(client, monkeypatch):
    import agents.builder as builder_mod

    build_mock = MagicMock()
    monkeypatch.setattr(builder_mod.Builder, "build_config", build_mock)

    resp = client.post("/build-campaign", json={"prompt": "test", "auto_deploy": True})

    assert resp.status_code == 401
    build_mock.assert_not_called()


class _FakeMemory:
    def __init__(self, decision):
        self.decision = decision
        self.approved = False

    def get_decision_by_token(self, token):
        return self.decision

    def mark_autonomous_decision_approved(self, decision_id):
        self.approved = True

    def mark_autonomous_decision_rejected(self, decision_id):
        pass

    def mark_autonomous_decision_postponed(self, decision_id):
        pass


class _FakeGoogleAdsService:
    def search(self, customer_id, query):
        return []


def _decision(evidence):
    return {
        "id": 123,
        "decision": "proposed",
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "approved_at": None,
        "rejected_at": None,
        "postponed_at": None,
        "keyword": "sushi merida",
        "campaign_id": "23730364039",
        "campaign_name": "Experiencia 2026",
        "action_type": "block_keyword",
        "session_id": "s1",
        "evidence_json": json.dumps(evidence),
    }


@pytest.fixture
def approval_setup(monkeypatch):
    import engine.memory as memory_mod
    import engine.risk_classifier as risk_mod
    import routes.approvals as approvals

    captured = MagicMock(return_value={"status": "success", "match_type": "EXACT"})
    fake_client = MagicMock()
    fake_client.get_service.return_value = _FakeGoogleAdsService()
    fake_engine = {
        "get_ads_client": lambda: fake_client,
        "add_negative_keyword": captured,
    }
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(approvals, "_get_engine", lambda: fake_engine)
    monkeypatch.setattr(risk_mod, "is_keyword_protected", lambda keyword: False)

    state = {}

    def set_decision(evidence):
        mem = _FakeMemory(_decision(evidence))
        state["memory"] = mem
        monkeypatch.setattr(memory_mod, "get_memory_system", lambda: mem)

    return set_decision, captured, state


def test_approve_block_keyword_without_match_type_fails_closed(client, approval_setup):
    set_decision, captured, _ = approval_setup
    set_decision({})

    resp = client.get("/approve?d=tok&action=approve")

    assert resp.status_code == 200
    assert "Match type ausente" in resp.text
    captured.assert_not_called()


def test_approve_block_keyword_broad_fails_closed(client, approval_setup):
    set_decision, captured, _ = approval_setup
    set_decision({"match_type": "BROAD"})

    resp = client.get("/approve?d=tok&action=approve")

    assert resp.status_code == 200
    assert "BROAD no permitido" in resp.text
    captured.assert_not_called()


def test_approve_block_keyword_invalid_match_type_fails_closed(client, approval_setup):
    set_decision, captured, _ = approval_setup
    set_decision({"match_type": "FUZZY"})

    resp = client.get("/approve?d=tok&action=approve")

    assert resp.status_code == 200
    assert "Match type invalido" in resp.text
    captured.assert_not_called()


@pytest.mark.parametrize("match_type", ["EXACT", "PHRASE"])
def test_approve_block_keyword_passes_safe_match_type(client, approval_setup, match_type):
    set_decision, captured, state = approval_setup
    captured.return_value = {"status": "success", "match_type": match_type}
    set_decision({"match_type": match_type})

    resp = client.get("/approve?d=tok&action=approve")

    assert resp.status_code == 200
    captured.assert_called_once()
    assert captured.call_args.kwargs["match_type"] == match_type
    assert state["memory"].approved is True
