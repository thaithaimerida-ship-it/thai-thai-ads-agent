"""
Tests para routes/presupuestos.py — POST /apply-budget-changes (Fase 5b).

NO toca Google Ads real — patches engine.ads_client.{get_ads_client,
fetch_campaign_budget_info, verify_budget_still_actionable,
update_campaign_budget, log_agent_action}.

Aisla SQLite usando tmp_path y patcheando routes.presupuestos.get_db_path.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from engine.memory import MemorySystem


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Inicializa autonomous_decisions en un SQLite temporal y reapunta el
    endpoint a esa DB. Devuelve el MemorySystem para que el test inserte filas."""
    db_path = str(tmp_path / "test_presupuestos.db")
    mem = MemorySystem(db_path=db_path)
    monkeypatch.setattr("routes.presupuestos.get_db_path", lambda: db_path)
    return mem


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-123")
    return "test-token-123"


@pytest.fixture
def customer_id_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")


@pytest.fixture
def client():
    """TestClient sobre la app real (con todos los routers registrados)."""
    from main import app
    return TestClient(app)


@pytest.fixture
def mocked_ads(monkeypatch):
    """Mockea las 5 funciones de engine.ads_client que usa el handler.

    Devuelve un dict con las 5 MagicMocks para que el test ajuste returns/side_effects.
    Defaults son "happy path" — el guard pasa, fetch retorna budget,
    update OK en dry-run y real.
    """
    mocks = {
        "get_ads_client": MagicMock(return_value=MagicMock(name="ads_client")),
        "fetch_campaign_budget_info": MagicMock(return_value={
            "budget_resource_name": "customers/4021070209/campaignBudgets/999",
            "current_daily_budget_mxn": 100.0,
        }),
        "verify_budget_still_actionable": MagicMock(return_value={
            "ok": True, "reason": "", "guard": "",
            "current_budget_mxn": 100.0,
            "suggested_budget_mxn": 150.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }),
        "update_campaign_budget": MagicMock(side_effect=[
            {"status": "success", "validate_only": True, "resource_name": "r"},   # dry-run
            {"status": "success", "validate_only": False, "resource_name": "r"},  # real
        ]),
        "log_agent_action": MagicMock(return_value=None),
    }
    for name, m in mocks.items():
        monkeypatch.setattr(f"engine.ads_client.{name}", m)
    return mocks


# ============================================================================
# Helpers
# ============================================================================


def _insert_scale(memory, *, campaign_id="22612348265",
                  campaign_name="Local", new_budget_mxn=150.0,
                  decision="proposed", executed=False) -> int:
    """Inserta una decision scale pending. Devuelve el id."""
    return memory.record_autonomous_decision(
        action_type="scale", risk_level=2, urgency="normal",
        decision=decision,
        campaign_id=campaign_id, campaign_name=campaign_name,
        evidence={
            "reason": "CPA bajo con conv reales",
            "urgency": "normal",
            "risk_level": 2,
            "new_budget_mxn": new_budget_mxn,
        },
        executed=executed,
    )


def _insert_negative(memory) -> int:
    return memory.record_autonomous_decision(
        action_type="negative", risk_level=2, urgency="normal",
        decision="proposed",
        campaign_id="22612348265", campaign_name="Local",
        keyword="sushi",
        evidence={"reason": "diez chars+", "urgency": "normal",
                  "risk_level": 2, "keyword": "sushi"},
    )


HEADERS_OK = {"X-API-Token": "test-token-123"}


# ============================================================================
# Tests
# ============================================================================


class TestAuth:
    def test_apply_without_token_returns_401(self, client, customer_id_env, admin_token, isolated_db):
        decision_id = _insert_scale(isolated_db)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]})
        assert r.status_code == 401


class TestValidation:
    def test_apply_empty_decision_ids_returns_422(self, client, admin_token, isolated_db, customer_id_env):
        r = client.post("/apply-budget-changes", json={"decision_ids": []}, headers=HEADERS_OK)
        assert r.status_code == 422

    def test_apply_too_many_decision_ids_returns_422(self, client, admin_token, isolated_db, customer_id_env):
        r = client.post(
            "/apply-budget-changes",
            json={"decision_ids": list(range(1, 22))},  # 21 ids
            headers=HEADERS_OK,
        )
        assert r.status_code == 422


class TestInvariantes:
    def test_decision_id_not_found_goes_to_failed(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        r = client.post("/apply-budget-changes", json={"decision_ids": [99999]}, headers=HEADERS_OK)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["failed"] == [{"decision_id": 99999, "reason": "not_found"}]
        assert body["applied"] == []

    def test_wrong_action_type_goes_to_failed(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        neg_id = _insert_negative(isolated_db)
        r = client.post("/apply-budget-changes", json={"decision_ids": [neg_id]}, headers=HEADERS_OK)
        body = r.json()
        assert body["status"] == "error"
        assert body["failed"][0]["reason"] == "wrong_action_type"
        assert body["failed"][0]["detail"] == "negative"
        # No debió haber tocado Google Ads
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()

    def test_already_executed_goes_to_failed(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        decision_id = _insert_scale(isolated_db, executed=True)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]}, headers=HEADERS_OK)
        body = r.json()
        assert body["status"] == "error"
        assert body["failed"][0]["reason"] == "already_executed"
        mocked_ads["update_campaign_budget"].assert_not_called()


class TestGuardrails:
    def test_blocks_when_guardrail_fails(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        mocked_ads["verify_budget_still_actionable"].return_value = {
            "ok": False, "guard": "G_shared",
            "reason": "budget compartido entre campañas",
            "current_budget_mxn": 100.0,
        }
        decision_id = _insert_scale(isolated_db)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]}, headers=HEADERS_OK)
        body = r.json()
        assert body["status"] == "error"
        assert len(body["blocked_by_guardrail"]) == 1
        assert body["blocked_by_guardrail"][0]["guardrail"] == "G_shared"
        # Crítico: update_campaign_budget NUNCA debió llamarse
        mocked_ads["update_campaign_budget"].assert_not_called()
        # log_agent_action debió registrar el block
        log_call = mocked_ads["log_agent_action"].call_args
        assert log_call.kwargs["status"] == "blocked"


class TestDryRun:
    def test_blocks_when_dry_run_fails(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        # dry-run falla; el real NUNCA debe correrse
        mocked_ads["update_campaign_budget"].side_effect = [
            {"status": "error", "validate_only": True, "message": "INVALID_BUDGET_AMOUNT"},
        ]
        decision_id = _insert_scale(isolated_db)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]}, headers=HEADERS_OK)
        body = r.json()
        assert body["status"] == "error"
        assert body["failed"][0]["reason"] == "dry_run_failed"
        assert "INVALID_BUDGET_AMOUNT" in body["failed"][0]["detail"]
        # Solo 1 llamada (la del dry-run)
        assert mocked_ads["update_campaign_budget"].call_count == 1
        call_kwargs = mocked_ads["update_campaign_budget"].call_args.kwargs
        assert call_kwargs["validate_only"] is True
        log_call = mocked_ads["log_agent_action"].call_args
        assert log_call.kwargs["status"] == "dry_run_failed"


class TestHappyPath:
    def test_apply_succeeds_happy_path(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        decision_id = _insert_scale(isolated_db, new_budget_mxn=150.0)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]}, headers=HEADERS_OK)
        body = r.json()
        assert body["status"] == "success"
        assert len(body["applied"]) == 1
        a = body["applied"][0]
        assert a["decision_id"] == decision_id
        assert a["action_type"] == "scale"
        assert a["new_budget_mxn"] == 150.0
        assert a["old_budget_mxn"] == 100.0

        # Verificar que se ejecutaron dry-run + real en orden
        assert mocked_ads["update_campaign_budget"].call_count == 2
        c1, c2 = mocked_ads["update_campaign_budget"].call_args_list
        assert c1.kwargs["validate_only"] is True
        assert c2.kwargs["validate_only"] is False
        # budget_micros = 150 * 1_000_000 = 150_000_000
        assert c1.args[3] == 150_000_000
        assert c2.args[3] == 150_000_000

        # executed=1 en DB
        import sqlite3
        with sqlite3.connect(isolated_db.db_path) as conn:
            executed = conn.execute(
                "SELECT executed, approved_at FROM autonomous_decisions WHERE id=?",
                (decision_id,)
            ).fetchone()
        assert executed[0] == 1
        assert executed[1] is not None


class TestAntiTampering:
    def test_ignores_client_supplied_budget_in_body(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        """El handler NO debe respetar new_budget_mxn enviado en el body.
        Solo lee el valor de autonomous_decisions.evidence_json."""
        decision_id = _insert_scale(isolated_db, new_budget_mxn=150.0)
        # Cliente intenta inflar el budget a 999 via body
        r = client.post(
            "/apply-budget-changes",
            json={"decision_ids": [decision_id], "new_budget_mxn": 999.0},
            headers=HEADERS_OK,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        # El budget aplicado debe ser 150 (de DB), no 999 (del cliente)
        assert body["applied"][0]["new_budget_mxn"] == 150.0
        # Confirmar que el budget_micros que llegó al service fue 150_000_000
        c2 = mocked_ads["update_campaign_budget"].call_args_list[1]
        assert c2.args[3] == 150_000_000


class TestBatchMixedOutcomes:
    def test_partial_when_one_succeeds_and_one_blocked(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        id_ok = _insert_scale(isolated_db, campaign_id="22612348265", campaign_name="Local")
        id_blocked = _insert_scale(isolated_db, campaign_id="22839241090", campaign_name="Delivery")

        # Primera llamada al guardrail OK, segunda bloquea
        mocked_ads["verify_budget_still_actionable"].side_effect = [
            {"ok": True, "guard": "", "reason": "", "current_budget_mxn": 100.0,
             "campaign_status": "ENABLED", "budget_explicitly_shared": False},
            {"ok": False, "guard": "G_max_cut", "reason": "reducción supera 60%",
             "current_budget_mxn": 100.0},
        ]
        # update_campaign_budget se llama 2 veces (dry+real) para id_ok
        mocked_ads["update_campaign_budget"].side_effect = [
            {"status": "success", "validate_only": True, "resource_name": "r"},
            {"status": "success", "validate_only": False, "resource_name": "r"},
        ]

        r = client.post(
            "/apply-budget-changes",
            json={"decision_ids": [id_ok, id_blocked]},
            headers=HEADERS_OK,
        )
        body = r.json()
        assert body["status"] == "partial"
        assert len(body["applied"]) == 1
        assert len(body["blocked_by_guardrail"]) == 1
        assert body["applied"][0]["decision_id"] == id_ok
        assert body["blocked_by_guardrail"][0]["decision_id"] == id_blocked
        assert body["summary"] == {"requested": 2, "applied": 1, "failed": 0, "blocked": 1}

    def test_error_when_nothing_succeeds(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        id1 = _insert_scale(isolated_db, campaign_id="A", campaign_name="A")
        id2 = _insert_scale(isolated_db, campaign_id="B", campaign_name="B")
        # Ambas bloqueadas
        mocked_ads["verify_budget_still_actionable"].return_value = {
            "ok": False, "guard": "G_campaign", "reason": "campaign PAUSED",
            "current_budget_mxn": 100.0,
        }
        r = client.post(
            "/apply-budget-changes",
            json={"decision_ids": [id1, id2]},
            headers=HEADERS_OK,
        )
        body = r.json()
        assert body["status"] == "error"
        assert len(body["applied"]) == 0
        assert len(body["blocked_by_guardrail"]) == 2
