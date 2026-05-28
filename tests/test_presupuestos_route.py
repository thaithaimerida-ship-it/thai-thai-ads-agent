"""
Tests para routes/presupuestos.py — POST /apply-budget-changes (Fase 5b).

NO toca Google Ads real — patches engine.ads_client.{get_ads_client,
fetch_campaign_budget_info, verify_budget_still_actionable,
update_campaign_budget, log_agent_action}.

Aisla SQLite usando tmp_path y patcheando routes.presupuestos.get_db_path.
"""
from __future__ import annotations

import json
import sqlite3
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


def _insert_manual_preview_scale(memory, *, campaign_id="22839241090",
                                 campaign_name="Thai Mérida - Delivery",
                                 new_budget_mxn=55.0) -> int:
    return memory.record_autonomous_decision(
        action_type="scale", risk_level=2, urgency="normal",
        decision="proposed",
        campaign_id=campaign_id, campaign_name=campaign_name,
        evidence={
            "source": "manual_preview",
            "reason": "Tendencia con conversiones primarias; aumento conservador de preview.",
            "current_budget_mxn": 50.0,
            "new_budget_mxn": new_budget_mxn,
            "suggested_budget_mxn": new_budget_mxn,
            "direction": "increase",
        },
        executed=False,
    )


def _mark_manual_preview_validated(memory, decision_id: int, *, applied=False) -> None:
    with sqlite3.connect(memory.db_path) as conn:
        row = conn.execute(
            "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        evidence = json.loads(row[0])
        evidence["approval_validation"] = {
            "validated": True,
            "validated_at": "2026-05-28T21:30:56+00:00",
            "current_budget_verified_mxn": 50.0,
            "requested_budget_mxn": evidence["new_budget_mxn"],
            "validate_only_result": {
                "success": True,
                "status": "success",
                "message": "validate_only_ok",
                "resource_name": None,
            },
            "applied": applied,
        }
        conn.execute(
            "UPDATE autonomous_decisions SET evidence_json = ? WHERE id = ?",
            (json.dumps(evidence), decision_id),
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


def _insert_budget_decision(
    memory, *, action_type, evidence, campaign_id="22612348265",
    campaign_name="Local", decision="proposed", executed=False,
) -> int:
    return memory.record_autonomous_decision(
        action_type=action_type, risk_level=2, urgency="normal",
        decision=decision,
        campaign_id=campaign_id, campaign_name=campaign_name,
        evidence=evidence,
        executed=executed,
    )


def conn_record_count(db_path: str, decision_id: int) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM autonomous_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()[0]


HEADERS_OK = {"X-API-Token": "test-token-123"}


# ============================================================================
# Tests
# ============================================================================


class TestAuth:
    def test_apply_without_token_returns_401(self, client, customer_id_env, admin_token, isolated_db):
        decision_id = _insert_scale(isolated_db)
        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]})
        assert r.status_code == 401

    def test_validate_approval_without_token_returns_401(self, client, customer_id_env, admin_token, isolated_db):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/validate-approval",
            json={"decision_id": decision_id, "source": "manual_review"},
        )
        assert r.status_code == 401

    def test_review_action_without_token_returns_401(self, client, customer_id_env, admin_token, isolated_db):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/review-action",
            json={"decision_id": decision_id, "action": "reject", "source": "manual_review"},
        )
        assert r.status_code == 401

    def test_apply_approved_without_token_returns_401(self, client, customer_id_env, admin_token, isolated_db):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/apply-approved",
            json={"decision_id": decision_id, "source": "manual_review", "confirmation": "APLICAR"},
        )
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

    def test_review_action_invalid_action_returns_422(self, client, admin_token, isolated_db, customer_id_env):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/review-action",
            json={"decision_id": decision_id, "action": "approve", "source": "manual_review"},
            headers=HEADERS_OK,
        )
        assert r.status_code == 422

    def test_review_action_invalid_source_returns_422(self, client, admin_token, isolated_db, customer_id_env):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/review-action",
            json={"decision_id": decision_id, "action": "reject", "source": "ui"},
            headers=HEADERS_OK,
        )
        assert r.status_code == 422

    def test_apply_approved_invalid_source_returns_422(self, client, admin_token, isolated_db, customer_id_env):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/apply-approved",
            json={"decision_id": decision_id, "source": "ui", "confirmation": "APLICAR"},
            headers=HEADERS_OK,
        )
        assert r.status_code == 422

    def test_apply_approved_rejects_batch_shape(self, client, admin_token, isolated_db, customer_id_env):
        decision_id = _insert_manual_preview_scale(isolated_db)
        r = client.post(
            "/budget-recommendations/apply-approved",
            json={"decision_ids": [decision_id], "source": "manual_review", "confirmation": "APLICAR"},
            headers=HEADERS_OK,
        )
        assert r.status_code == 422


class TestBudgetReviewAction:
    def test_reject_manual_preview_marks_rejected_and_hides_pending_without_ads_calls(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/review-action",
            json={
                "decision_id": decision_id,
                "action": "reject",
                "reason": "No subir delivery esta semana.",
                "source": "manual_review",
            },
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["decision_id"] == decision_id
        assert body["action"] == "reject"
        assert body["message"] == "Propuesta rechazada. No se aplicó ningún cambio."
        assert body["gcs_synced"] is True
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT rejected_at, postponed_at, approved_at, executed, evidence_json "
                "FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] is not None
        assert row[1] is None
        assert row[2] is None
        assert row[3] == 0
        evidence = json.loads(row[4])
        assert evidence["review_actions"][-1]["action"] == "reject"
        assert evidence["review_actions"][-1]["reason"] == "No subir delivery esta semana."
        assert evidence["review_actions"][-1]["actor"] == "admin_api_token"
        assert client.get("/presupuestos/data").json()["count"] == 0
        assert conn_record_count(isolated_db.db_path, decision_id) == 1
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_called_once_with()

    def test_postpone_manual_preview_marks_postponed_and_hides_pending_without_ads_calls(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/review-action",
            json={
                "decision_id": decision_id,
                "action": "postpone",
                "reason": "Revisar la proxima semana.",
                "postpone_until": "2026-06-03",
                "source": "manual_review",
            },
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["message"] == "Propuesta pospuesta. No se aplicó ningún cambio."
        assert body["gcs_synced"] is True
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT rejected_at, postponed_at, approved_at, executed, evidence_json "
                "FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] is None
        assert row[1] is not None
        assert row[2] is None
        assert row[3] == 0
        evidence = json.loads(row[4])
        assert evidence["review_actions"][-1]["action"] == "postpone"
        assert evidence["review_actions"][-1]["postpone_until"] == "2026-06-03"
        assert evidence["review_actions"][-1]["reason"] == "Revisar la proxima semana."
        assert client.get("/presupuestos/data").json()["count"] == 0
        assert conn_record_count(isolated_db.db_path, decision_id) == 1
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_called_once_with()

    def test_keep_review_manual_preview_stays_visible_and_only_audits(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/review-action",
            json={
                "decision_id": decision_id,
                "action": "keep_review",
                "reason": "Quiero pensarlo.",
                "source": "manual_review",
            },
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["message"] == "Propuesta mantenida en revisión. No se aplicó ningún cambio."
        assert body["gcs_synced"] is True
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT rejected_at, postponed_at, approved_at, executed, evidence_json "
                "FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None
        assert row[3] == 0
        evidence = json.loads(row[4])
        assert evidence["review_actions"][-1]["action"] == "keep_review"
        data = client.get("/presupuestos/data").json()
        assert data["count"] == 1
        assert data["recommendations"][0]["id"] == decision_id
        assert conn_record_count(isolated_db.db_path, decision_id) == 1
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_called_once_with()

    @pytest.mark.parametrize("sync_result", [False, RuntimeError("gcs unavailable")])
    def test_review_action_success_continues_when_gcs_sync_fails(
        self, sync_result, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(side_effect=sync_result if isinstance(sync_result, Exception) else None)
        if not isinstance(sync_result, Exception):
            sync.return_value = sync_result
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/review-action",
            json={"decision_id": decision_id, "action": "keep_review", "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["gcs_synced"] is False
        assert body["warning"] == "review_saved_locally_but_gcs_sync_failed"
        sync.assert_called_once_with()
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()

    @pytest.mark.parametrize(
        ("setup", "reason"),
        [
            (lambda mem: 99999, "not_found"),
            (lambda mem: _insert_manual_preview_scale(mem, new_budget_mxn=55.0), "already_executed"),
            (lambda mem: _insert_manual_preview_scale(mem, new_budget_mxn=56.0), "rejected"),
            (lambda mem: _insert_manual_preview_scale(mem, new_budget_mxn=57.0), "postponed"),
            (lambda mem: _insert_scale(mem), "not_manual_preview"),
        ],
    )
    def test_review_action_rejects_invalid_state_without_ads_calls(
        self, setup, reason, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = setup(isolated_db)
        if reason == "already_executed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET executed = 1 WHERE id = ?", (decision_id,))
        elif reason == "rejected":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET rejected_at = datetime('now') WHERE id = ?", (decision_id,))
        elif reason == "postponed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET postponed_at = datetime('now') WHERE id = ?", (decision_id,))

        r = client.post(
            "/budget-recommendations/review-action",
            json={"decision_id": decision_id, "action": "reject", "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        assert r.json()["status"] == "error"
        assert r.json()["reason"] == reason
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()


class TestBudgetValidateApproval:
    def test_validate_approval_runs_validate_only_and_audits_without_applying(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        mocked_ads["fetch_campaign_budget_info"].return_value = {
            "budget_resource_name": "customers/4021070209/campaignBudgets/999",
            "current_daily_budget_mxn": 50.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }
        mocked_ads["verify_budget_still_actionable"].return_value = {
            "ok": True,
            "reason": "",
            "guard": "",
            "current_budget_mxn": 50.0,
            "suggested_budget_mxn": 55.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }
        mocked_ads["update_campaign_budget"].side_effect = None
        mocked_ads["update_campaign_budget"].return_value = {
            "status": "success",
            "validate_only": True,
            "resource_name": "customers/4021070209/campaignBudgets/999",
        }
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/validate-approval",
            json={
                "decision_id": decision_id,
                "source": "manual_review",
                "reason": "Aprobar para validacion segura antes de aplicar.",
            },
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["decision_id"] == decision_id
        assert body["action"] == "approve_validate"
        assert body["validated"] is True
        assert body["applied"] is False
        assert body["gcs_synced"] is True
        mocked_ads["fetch_campaign_budget_info"].assert_called_once()
        mocked_ads["verify_budget_still_actionable"].assert_called_once()
        mocked_ads["update_campaign_budget"].assert_called_once()
        assert mocked_ads["update_campaign_budget"].call_args.kwargs["validate_only"] is True
        assert mocked_ads["update_campaign_budget"].call_args.args[3] == 55_000_000
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT executed, approved_at, rejected_at, postponed_at, evidence_json "
                "FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None
        evidence = json.loads(row[4])
        action = evidence["review_actions"][-1]
        assert action["action"] == "approve_validate"
        assert action["actor"] == "admin_api_token"
        assert action["source"] == "manual_review"
        assert action["current_budget_verified_mxn"] == 50.0
        assert action["requested_budget_mxn"] == 55.0
        assert action["validate_only_result"]["success"] is True
        assert action["applied"] is False
        assert evidence["approval_validation"]["validated"] is True
        sync.assert_called_once_with()

    @pytest.mark.parametrize(
        ("setup", "reason"),
        [
            (lambda mem: 99999, "not_found"),
            (lambda mem: _insert_scale(mem), "not_manual_preview"),
            (lambda mem: _insert_manual_preview_scale(mem), "already_executed"),
            (lambda mem: _insert_manual_preview_scale(mem), "rejected"),
            (lambda mem: _insert_manual_preview_scale(mem), "postponed"),
            (lambda mem: _insert_manual_preview_scale(mem), "approved"),
            (lambda mem: _insert_budget_decision(
                mem,
                action_type="scale",
                decision="accepted",
                evidence={
                    "source": "manual_preview",
                    "current_budget_mxn": 50.0,
                    "new_budget_mxn": 55.0,
                },
            ), "wrong_decision_state"),
            (lambda mem: _insert_budget_decision(
                mem,
                action_type="hold",
                evidence={
                    "source": "manual_preview",
                    "current_budget_mxn": 50.0,
                    "new_budget_mxn": 55.0,
                },
            ), "wrong_action_type"),
            (lambda mem: _insert_manual_preview_scale(mem, new_budget_mxn=0), "invalid_new_budget_mxn"),
        ],
    )
    def test_validate_approval_rejects_invalid_state_before_ads_or_gcs(
        self, setup, reason, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = setup(isolated_db)
        if reason == "already_executed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET executed = 1 WHERE id = ?", (decision_id,))
        elif reason == "rejected":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET rejected_at = datetime('now') WHERE id = ?", (decision_id,))
        elif reason == "postponed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET postponed_at = datetime('now') WHERE id = ?", (decision_id,))
        elif reason == "approved":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET approved_at = datetime('now') WHERE id = ?", (decision_id,))

        r = client.post(
            "/budget-recommendations/validate-approval",
            json={"decision_id": decision_id, "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == reason
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()

    @pytest.mark.parametrize(
        ("fetch_result", "guard_result", "reason"),
        [
            ({"error": "api unavailable"}, None, "budget_fetch_failed"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "PAUSED",
                "budget_explicitly_shared": False,
            }, None, "campaign_not_enabled"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": True,
            }, None, "shared_budget"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 80.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": False,
            }, None, "budget_drift"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": False,
            }, {"ok": False, "guard": "G_shared", "reason": "budget compartido"}, "guardrail_blocked"),
        ],
    )
    def test_validate_approval_rejects_budget_verification_failures_without_validate_only(
        self, fetch_result, guard_result, reason,
        client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        mocked_ads["fetch_campaign_budget_info"].return_value = fetch_result
        if guard_result is not None:
            mocked_ads["verify_budget_still_actionable"].return_value = guard_result
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/validate-approval",
            json={"decision_id": decision_id, "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == reason
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()

    def test_validate_approval_validate_only_failure_audits_without_executing(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        mocked_ads["fetch_campaign_budget_info"].return_value = {
            "budget_resource_name": "customers/4021070209/campaignBudgets/999",
            "current_daily_budget_mxn": 50.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }
        mocked_ads["verify_budget_still_actionable"].return_value = {"ok": True}
        mocked_ads["update_campaign_budget"].side_effect = None
        mocked_ads["update_campaign_budget"].return_value = {
            "status": "error",
            "validate_only": True,
            "message": "INVALID_BUDGET_AMOUNT",
        }
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/validate-approval",
            json={"decision_id": decision_id, "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == "validate_only_failed"
        assert body["applied"] is False
        assert body["gcs_synced"] is True
        mocked_ads["update_campaign_budget"].assert_called_once()
        assert mocked_ads["update_campaign_budget"].call_args.kwargs["validate_only"] is True
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT executed, approved_at, evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        evidence = json.loads(row[2])
        action = evidence["review_actions"][-1]
        assert action["action"] == "approve_validate"
        assert action["validate_only_result"]["success"] is False
        assert action["applied"] is False
        sync.assert_called_once_with()

    @pytest.mark.parametrize("sync_result", [False, RuntimeError("gcs unavailable")])
    def test_validate_approval_success_continues_when_gcs_sync_fails(
        self, sync_result, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(side_effect=sync_result if isinstance(sync_result, Exception) else None)
        if not isinstance(sync_result, Exception):
            sync.return_value = sync_result
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        mocked_ads["fetch_campaign_budget_info"].return_value = {
            "budget_resource_name": "customers/4021070209/campaignBudgets/999",
            "current_daily_budget_mxn": 50.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }
        mocked_ads["verify_budget_still_actionable"].return_value = {"ok": True}
        mocked_ads["update_campaign_budget"].side_effect = None
        mocked_ads["update_campaign_budget"].return_value = {"status": "success", "validate_only": True}
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post(
            "/budget-recommendations/validate-approval",
            json={"decision_id": decision_id, "source": "manual_review"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["gcs_synced"] is False
        assert body["warning"] == "approval_validation_saved_locally_but_gcs_sync_failed"
        sync.assert_called_once_with()


class TestBudgetApplyApproved:
    def _valid_payload(self, decision_id: int) -> dict:
        return {
            "decision_id": decision_id,
            "source": "manual_review",
            "confirmation": "APLICAR",
            "reason": "Aplicacion final controlada 8B.4B.",
        }

    def _setup_ads_happy_path(self, mocked_ads):
        mocked_ads["fetch_campaign_budget_info"].return_value = {
            "budget_resource_name": "customers/4021070209/campaignBudgets/999",
            "current_daily_budget_mxn": 50.0,
            "campaign_status": "ENABLED",
            "budget_explicitly_shared": False,
        }
        mocked_ads["verify_budget_still_actionable"].return_value = {"ok": True}
        mocked_ads["update_campaign_budget"].side_effect = [
            {"status": "success", "validate_only": True, "message": "validate_only_ok", "resource_name": None},
            {"status": "success", "validate_only": False, "resource_name": "customers/4021070209/campaignBudgets/999"},
        ]

    def test_apply_approved_rejects_wrong_confirmation_before_ads(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)

        r = client.post(
            "/budget-recommendations/apply-approved",
            json={**self._valid_payload(decision_id), "confirmation": "SI"},
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        assert r.json()["reason"] == "confirmation_required"
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()

    def test_apply_approved_rejects_missing_applied_flag_before_ads_or_gcs(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
            evidence = json.loads(row[0])
            evidence["approval_validation"].pop("applied")
            conn.execute(
                "UPDATE autonomous_decisions SET evidence_json = ? WHERE id = ?",
                (json.dumps(evidence), decision_id),
            )

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == "approval_validation_applied_required_false"
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()

    @pytest.mark.parametrize(
        ("setup", "reason"),
        [
            (lambda mem: 99999, "not_found"),
            (lambda mem: _insert_scale(mem), "not_manual_preview"),
            (lambda mem: _insert_manual_preview_scale(mem), "approval_validation_required"),
            (lambda mem: _insert_manual_preview_scale(mem), "approval_validation_applied_required_false"),
            (lambda mem: _insert_manual_preview_scale(mem), "already_executed"),
            (lambda mem: _insert_manual_preview_scale(mem), "approved"),
            (lambda mem: _insert_manual_preview_scale(mem), "rejected"),
            (lambda mem: _insert_manual_preview_scale(mem), "postponed"),
            (lambda mem: _insert_budget_decision(
                mem,
                action_type="hold",
                evidence={
                    "source": "manual_preview",
                    "current_budget_mxn": 50.0,
                    "new_budget_mxn": 55.0,
                    "approval_validation": {"validated": True, "applied": False},
                },
            ), "wrong_action_type"),
            (lambda mem: _insert_manual_preview_scale(mem, new_budget_mxn=0), "invalid_new_budget_mxn"),
        ],
    )
    def test_apply_approved_rejects_invalid_state_before_ads_or_gcs(
        self, setup, reason, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        decision_id = setup(isolated_db)
        if reason in {"approval_validation_applied_required_false", "already_executed", "approved", "rejected", "postponed"}:
            _mark_manual_preview_validated(
                isolated_db,
                decision_id,
                applied=(reason == "approval_validation_applied_required_false"),
            )
        if reason == "already_executed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET executed = 1 WHERE id = ?", (decision_id,))
        elif reason == "approved":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET approved_at = datetime('now') WHERE id = ?", (decision_id,))
        elif reason == "rejected":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET rejected_at = datetime('now') WHERE id = ?", (decision_id,))
        elif reason == "postponed":
            with sqlite3.connect(isolated_db.db_path) as conn:
                conn.execute("UPDATE autonomous_decisions SET postponed_at = datetime('now') WHERE id = ?", (decision_id,))

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == reason
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()

    @pytest.mark.parametrize(
        ("fetch_result", "guard_result", "reason"),
        [
            ({"error": "api unavailable"}, None, "budget_fetch_failed"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "PAUSED",
                "budget_explicitly_shared": False,
            }, None, "campaign_not_enabled"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": True,
            }, None, "shared_budget"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 60.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": False,
            }, None, "budget_drift"),
            ({
                "budget_resource_name": "customers/4021070209/campaignBudgets/999",
                "current_daily_budget_mxn": 50.0,
                "campaign_status": "ENABLED",
                "budget_explicitly_shared": False,
            }, {"ok": False, "guard": "G_max", "reason": "blocked"}, "guardrail_blocked"),
        ],
    )
    def test_apply_approved_rejects_budget_verification_failures_without_mutating(
        self, fetch_result, guard_result, reason,
        client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        mocked_ads["fetch_campaign_budget_info"].return_value = fetch_result
        if guard_result is not None:
            mocked_ads["verify_budget_still_actionable"].return_value = guard_result
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        assert r.json()["reason"] == reason
        mocked_ads["update_campaign_budget"].assert_not_called()
        sync.assert_not_called()

    def test_apply_approved_fresh_validate_only_failure_audits_without_real_apply(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        self._setup_ads_happy_path(mocked_ads)
        mocked_ads["update_campaign_budget"].side_effect = None
        mocked_ads["update_campaign_budget"].return_value = {
            "status": "error",
            "validate_only": True,
            "message": "INVALID_BUDGET_AMOUNT",
        }
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == "fresh_validate_only_failed"
        mocked_ads["update_campaign_budget"].assert_called_once()
        assert mocked_ads["update_campaign_budget"].call_args.kwargs["validate_only"] is True
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT executed, approved_at, evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        evidence = json.loads(row[2])
        assert evidence["review_actions"][-1]["action"] == "apply_approved_failed"
        assert evidence["review_actions"][-1]["stage"] == "fresh_validate_only"
        sync.assert_called_once_with()

    def test_apply_approved_real_apply_failure_audits_without_marking_approved(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=True)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        self._setup_ads_happy_path(mocked_ads)
        mocked_ads["update_campaign_budget"].side_effect = [
            {"status": "success", "validate_only": True, "message": "validate_only_ok"},
            {"status": "error", "validate_only": False, "message": "quota"},
        ]
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["reason"] == "apply_failed"
        assert mocked_ads["update_campaign_budget"].call_count == 2
        assert mocked_ads["update_campaign_budget"].call_args_list[0].kwargs["validate_only"] is True
        assert mocked_ads["update_campaign_budget"].call_args_list[1].kwargs["validate_only"] is False
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT executed, approved_at, evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        evidence = json.loads(row[2])
        assert evidence["review_actions"][-1]["action"] == "apply_approved_failed"
        assert evidence["review_actions"][-1]["stage"] == "apply_real"
        sync.assert_called_once_with()

    @pytest.mark.parametrize("sync_result", [True, False])
    def test_apply_approved_success_marks_executed_and_syncs_gcs(
        self, sync_result, client, admin_token, customer_id_env, isolated_db, mocked_ads, monkeypatch,
    ):
        sync = MagicMock(return_value=sync_result)
        monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
        self._setup_ads_happy_path(mocked_ads)
        decision_id = _insert_manual_preview_scale(isolated_db)
        _mark_manual_preview_validated(isolated_db, decision_id)

        r = client.post(
            "/budget-recommendations/apply-approved",
            json=self._valid_payload(decision_id),
            headers=HEADERS_OK,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["action"] == "apply_approved"
        assert body["applied"] is True
        assert body["previous_budget_mxn"] == 50.0
        assert body["applied_budget_mxn"] == 55.0
        assert body["gcs_synced"] is sync_result
        if not sync_result:
            assert body["warning"] == "applied_but_gcs_sync_failed"
        assert mocked_ads["update_campaign_budget"].call_count == 2
        assert mocked_ads["update_campaign_budget"].call_args_list[0].kwargs["validate_only"] is True
        assert mocked_ads["update_campaign_budget"].call_args_list[1].kwargs["validate_only"] is False
        assert mocked_ads["update_campaign_budget"].call_args_list[0].args[3] == 55_000_000
        assert mocked_ads["update_campaign_budget"].call_args_list[1].args[3] == 55_000_000
        with sqlite3.connect(isolated_db.db_path) as conn:
            row = conn.execute(
                "SELECT decision, executed, approved_at, evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        assert row[0] == "proposed"
        assert row[1] == 1
        assert row[2] is not None
        evidence = json.loads(row[3])
        assert evidence["review_actions"][-1]["action"] == "apply_approved"
        assert evidence["approval_validation"]["validated"] is True
        assert evidence["approval_validation"]["applied"] is True
        assert evidence["approval_validation"]["previous_budget_mxn"] == 50.0
        assert evidence["approval_validation"]["applied_budget_mxn"] == 55.0
        sync.assert_called_once_with()


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

    def test_manual_preview_is_blocked_before_any_ads_budget_call(
        self, client, admin_token, customer_id_env, isolated_db, mocked_ads,
    ):
        decision_id = _insert_manual_preview_scale(isolated_db)

        r = client.post("/apply-budget-changes", json={"decision_ids": [decision_id]}, headers=HEADERS_OK)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["blocked_by_guardrail"] == [{
            "decision_id": decision_id,
            "reason": "manual_preview_not_applyable_yet",
            "message": "Esta propuesta fue guardada para revisión y todavía no está habilitada para aplicación.",
        }]
        mocked_ads["fetch_campaign_budget_info"].assert_not_called()
        mocked_ads["verify_budget_still_actionable"].assert_not_called()
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


class TestDataEndpointEnrichment:
    """Tests del GET /presupuestos/data con enrichment de current_budget_mxn.

    Mitigación intermedia mientras G_drift queda desactivado por TODO drift-guard.
    El operador ve drift al aprobar en /presupuestos UI.
    """

    def test_includes_current_budget_when_engine_available(
        self, client, isolated_db, customer_id_env, monkeypatch,
    ):
        decision_id = _insert_scale(
            isolated_db, campaign_id="22612348265", new_budget_mxn=150.0,
        )
        # Mock get_engine_modules para devolver current=$100 para esa campaña.
        engine_stub = {
            "get_ads_client": MagicMock(return_value=MagicMock()),
            "fetch_campaign_data": MagicMock(return_value=[
                {"id": 22612348265, "daily_budget_mxn": 100.0},
                {"id": 99999, "daily_budget_mxn": 999.0},  # ruido: no relacionada
            ]),
        }
        monkeypatch.setattr("main.get_engine_modules", lambda: engine_stub)

        r = client.get("/presupuestos/data")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["count"] == 1
        rec = body["recommendations"][0]
        assert rec["id"] == decision_id
        assert rec["new_budget_mxn"] == 150.0
        assert rec["current_budget_mxn"] == 100.0
        # fetch_campaign_data debió haberse llamado solo una vez
        assert engine_stub["fetch_campaign_data"].call_count == 1

    def test_returns_null_current_when_engine_fails(
        self, client, isolated_db, customer_id_env, monkeypatch,
    ):
        """Si get_engine_modules / get_ads_client / fetch lanza excepción,
        current queda null pero el endpoint sigue devolviendo success y la
        rec se muestra (UI renderiza 'n/d')."""
        _insert_scale(isolated_db, campaign_id="22612348265", new_budget_mxn=150.0)
        monkeypatch.setattr(
            "main.get_engine_modules",
            MagicMock(side_effect=RuntimeError("google.analytics not installed")),
        )

        r = client.get("/presupuestos/data")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["count"] == 1
        rec = body["recommendations"][0]
        assert rec["new_budget_mxn"] == 150.0
        assert rec["current_budget_mxn"] is None


class TestDataEndpointContract:
    def test_includes_scale_reduce_budget_action_and_budget_scale(
        self, client, isolated_db, customer_id_env, monkeypatch,
    ):
        monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
        ids = {
            "scale": _insert_budget_decision(
                isolated_db, action_type="scale",
                evidence={"reason": "scale reason", "new_budget_mxn": 150.0},
                campaign_id="1", campaign_name="Scale",
            ),
            "reduce": _insert_budget_decision(
                isolated_db, action_type="reduce",
                evidence={"reason": "reduce reason", "new_budget_mxn": 80.0},
                campaign_id="2", campaign_name="Reduce",
            ),
            "budget_action": _insert_budget_decision(
                isolated_db, action_type="budget_action",
                evidence={"reason": "ba1 reason", "suggested_daily_budget": 90.0},
                campaign_id="3", campaign_name="BA1",
            ),
            "budget_scale": _insert_budget_decision(
                isolated_db, action_type="budget_scale",
                evidence={"reason": "ba2 reason", "suggested_daily_budget_mxn": 180.0},
                campaign_id="4", campaign_name="BA2",
            ),
        }

        r = client.get("/presupuestos/data")

        assert r.status_code == 200
        body = r.json()
        by_id = {rec["id"]: rec for rec in body["recommendations"]}
        assert set(ids.values()) == set(by_id)
        assert by_id[ids["scale"]]["action_type_original"] == "scale"
        assert by_id[ids["scale"]]["display_action_type"] == "scale"
        assert by_id[ids["scale"]]["new_budget_mxn"] == 150.0
        assert by_id[ids["scale"]]["suggested_budget_mxn"] == 150.0
        assert by_id[ids["scale"]]["apply_enabled"] is True
        assert by_id[ids["reduce"]]["display_action_type"] == "reduce"
        assert by_id[ids["reduce"]]["apply_enabled"] is True
        assert by_id[ids["budget_action"]]["action_type_original"] == "budget_action"
        assert by_id[ids["budget_action"]]["display_action_type"] == "reduce"
        assert by_id[ids["budget_action"]]["new_budget_mxn"] == 90.0
        assert by_id[ids["budget_action"]]["suggested_budget_mxn"] == 90.0
        assert by_id[ids["budget_action"]]["apply_enabled"] is False
        assert by_id[ids["budget_action"]]["apply_disabled_reason"] == "Pendiente de compatibilidad de aplicacion"
        assert by_id[ids["budget_scale"]]["action_type_original"] == "budget_scale"
        assert by_id[ids["budget_scale"]]["display_action_type"] == "scale"
        assert by_id[ids["budget_scale"]]["new_budget_mxn"] == 180.0
        assert by_id[ids["budget_scale"]]["suggested_budget_mxn"] == 180.0
        assert by_id[ids["budget_scale"]]["apply_enabled"] is False

    def test_data_omits_non_budget_terminal_and_invalid_rows(
        self, client, isolated_db, customer_id_env, monkeypatch,
    ):
        monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
        valid_id = _insert_budget_decision(
            isolated_db, action_type="budget_action",
            evidence={"reason": "valid ba1", "suggested_daily_budget": 90.0},
            campaign_id="1",
        )
        _insert_negative(isolated_db)
        _insert_budget_decision(
            isolated_db, action_type="scale",
            evidence={"reason": "executed", "new_budget_mxn": 120.0},
            campaign_id="2", executed=True,
        )
        _insert_budget_decision(
            isolated_db, action_type="reduce",
            evidence={"reason": "wrong decision", "new_budget_mxn": 70.0},
            campaign_id="3", decision="observe",
        )
        _insert_budget_decision(
            isolated_db, action_type="budget_scale",
            evidence={"reason": "missing amount"},
            campaign_id="4",
        )
        _insert_budget_decision(
            isolated_db, action_type="budget_action",
            evidence={"suggested_daily_budget": 70.0},
            campaign_id="5",
        )

        r = client.get("/presupuestos/data")

        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["recommendations"][0]["id"] == valid_id

    def test_data_contract_does_not_call_budget_mutation(
        self, client, isolated_db, customer_id_env, monkeypatch,
    ):
        monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
        update = MagicMock()
        monkeypatch.setattr("engine.ads_client.update_campaign_budget", update)
        _insert_budget_decision(
            isolated_db, action_type="budget_scale",
            evidence={"reason": "ba2 reason", "suggested_daily_budget_mxn": 180.0},
            campaign_id="4", campaign_name="BA2",
        )

        r = client.get("/presupuestos/data")

        assert r.status_code == 200
        update.assert_not_called()


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
