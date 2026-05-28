from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from engine.memory import MemorySystem


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def customer_id_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_presupuestos_preview.db")
    mem = MemorySystem(db_path=db_path)
    monkeypatch.setattr("routes.presupuestos.get_db_path", lambda: db_path)
    return mem


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-123")
    return "test-token-123"


HEADERS_OK = {"X-API-Token": "test-token-123"}


def _campaign(
    campaign_id,
    *,
    name="Delivery",
    status="ENABLED",
    budget=100.0,
    shared=False,
    spend=300.0,
    conversions=10.0,
    all_conversions=10.0,
    ctr=8.0,
    conversion_quality="money_action",
    weak_local_actions=0.0,
):
    return {
        "id": campaign_id,
        "name": name,
        "status": status,
        "daily_budget_mxn": budget,
        "budget_explicitly_shared": shared,
        "spend": spend,
        "conversions": conversions,
        "all_conversions": all_conversions,
        "ctr": ctr,
        "conversion_quality": conversion_quality,
        "weak_local_actions": weak_local_actions,
    }


def _install_engine(monkeypatch, *, primary, trend=None, yesterday=None):
    calls = []

    def fetch_campaign_data(_client, _customer_id, date_range="YESTERDAY"):
        calls.append(date_range)
        if date_range == "LAST_7_DAYS":
            return primary
        if date_range == "LAST_30_DAYS":
            return trend if trend is not None else primary
        if date_range == "YESTERDAY":
            return yesterday if yesterday is not None else []
        return []

    engine = {
        "get_ads_client": MagicMock(return_value=MagicMock(name="ads_client")),
        "fetch_campaign_data": MagicMock(side_effect=fetch_campaign_data),
    }
    monkeypatch.setattr("main.get_engine_modules", lambda: engine)
    return engine, calls


def _save_payload(**overrides):
    payload = {
        "campaign_id": "22612348265",
        "campaign_name": "Thai Mérida - Local",
        "current_budget_mxn": 158.0,
        "suggested_budget_mxn": 173.8,
        "change_mxn": 15.8,
        "change_pct": 10.0,
        "direction": "increase",
        "reason": "Tendencia con conversiones primarias; aumento conservador de preview.",
        "evidence": {"primary_range": "LAST_7_DAYS", "money_actions_primary": 144.0},
        "warnings": [],
        "guardrails": ["preview_only", "no_apply_budget_changes"],
        "source": "manual_preview",
    }
    payload.update(overrides)
    return payload


def test_preview_opens_without_token_and_returns_read_only_contract(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[_campaign("1", budget=200.0, conversions=12.0)],
        trend=[_campaign("1", budget=200.0, conversions=40.0)],
    )

    response = client.get("/presupuestos/preview?date_range=LAST_7_DAYS")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["mode"] == "preview"
    assert body["persisted"] is False
    assert body["applies_changes"] is False
    assert body["generated_at"]
    assert body["count"] == 1
    proposal = body["proposals"][0]
    assert proposal["campaign_id"] == "1"
    assert proposal["campaign_status"] == "ENABLED"
    assert proposal["current_budget_mxn"] == 200.0
    assert proposal["suggested_budget_mxn"] == 220.0
    assert proposal["change_mxn"] == 20.0
    assert proposal["change_pct"] == 10.0
    assert proposal["direction"] == "increase"
    assert proposal["reason"]
    assert proposal["evidence"]["primary_range"] == "LAST_7_DAYS"
    assert proposal["evidence"]["trend_range"] == "LAST_30_DAYS"
    assert "max_increase_pct_10" in proposal["guardrails"]
    assert proposal["apply_enabled"] is False


def test_preview_does_not_write_db_or_call_budget_mutation(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[_campaign("1", budget=200.0, conversions=12.0)],
        trend=[_campaign("1", budget=200.0, conversions=40.0)],
    )
    connect = MagicMock(side_effect=AssertionError("preview must not touch sqlite"))
    update = MagicMock()
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr("engine.ads_client.update_campaign_budget", update)

    response = client.get("/presupuestos/preview")

    assert response.status_code == 200
    connect.assert_not_called()
    update.assert_not_called()


def test_preview_increase_respects_max_percent_and_absolute_caps(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[
            _campaign("large", name="Large", budget=1000.0, conversions=30.0),
            _campaign("small", name="Small", budget=80.0, conversions=8.0),
        ],
        trend=[
            _campaign("large", name="Large", budget=1000.0, conversions=90.0),
            _campaign("small", name="Small", budget=80.0, conversions=20.0),
        ],
    )

    body = client.get("/presupuestos/preview").json()

    by_id = {p["campaign_id"]: p for p in body["proposals"]}
    assert by_id["large"]["suggested_budget_mxn"] == 1050.0
    assert by_id["large"]["change_mxn"] == 50.0
    assert by_id["small"]["suggested_budget_mxn"] == 88.0
    assert by_id["small"]["change_mxn"] == 8.0


def test_preview_excludes_uncertain_tracking_disabled_and_invalid_budget(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[
            _campaign("unknown", conversion_quality="unknown"),
            _campaign("paused", status="PAUSED"),
            _campaign("nobudget", budget=0),
            _campaign("ok", conversions=5.0),
        ],
        trend=[
            _campaign("unknown", conversion_quality="unknown"),
            _campaign("paused", status="PAUSED"),
            _campaign("nobudget", budget=0),
            _campaign("ok", conversions=15.0),
        ],
    )

    body = client.get("/presupuestos/preview").json()

    assert [p["campaign_id"] for p in body["proposals"]] == ["ok"]


def test_preview_includes_good_shared_budget_as_review_only_hold(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[_campaign("shared", name="Experiencia", shared=True, budget=200.0, conversions=20.0)],
        trend=[_campaign("shared", name="Experiencia", shared=True, budget=200.0, conversions=60.0)],
    )

    body = client.get("/presupuestos/preview").json()

    assert body["status"] == "success"
    assert body["mode"] == "preview"
    assert body["persisted"] is False
    assert body["applies_changes"] is False
    assert body["count"] == 1
    proposal = body["proposals"][0]
    assert proposal["campaign_id"] == "shared"
    assert proposal["direction"] == "hold"
    assert proposal["suggested_budget_mxn"] == proposal["current_budget_mxn"]
    assert proposal["change_mxn"] == 0
    assert proposal["change_pct"] == 0
    assert proposal["reason"] == "Health bueno, pero no aplicable por guardrail."
    assert proposal["warnings"] == ["La campaña usa presupuesto compartido."]
    assert proposal["guardrails"] == ["no_apply_budget_changes", "shared_budget"]
    assert proposal["apply_enabled"] is False
    assert proposal["is_review_only"] is True


def test_preview_weak_local_only_is_not_treated_as_money_action(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[
            _campaign(
                "weak",
                conversions=0.0,
                all_conversions=6.0,
                conversion_quality="weak_local_action",
                weak_local_actions=6.0,
            )
        ],
        trend=[
            _campaign(
                "weak",
                conversions=0.0,
                all_conversions=18.0,
                conversion_quality="weak_local_action",
                weak_local_actions=18.0,
            )
        ],
    )

    body = client.get("/presupuestos/preview").json()

    assert body["count"] == 1
    proposal = body["proposals"][0]
    assert proposal["direction"] == "hold"
    assert proposal["suggested_budget_mxn"] == proposal["current_budget_mxn"]
    assert any("weak_local_action" in warning for warning in proposal["warnings"])


def test_preview_does_not_reduce_for_one_bad_day(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[_campaign("1", budget=100.0, conversions=8.0)],
        trend=[_campaign("1", budget=100.0, conversions=30.0)],
        yesterday=[_campaign("1", budget=100.0, spend=80.0, conversions=0.0)],
    )

    body = client.get("/presupuestos/preview").json()

    assert body["count"] == 1
    assert body["proposals"][0]["direction"] != "decrease"


def test_preview_handles_no_eligible_campaigns_without_breaking(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[_campaign("paused", status="PAUSED")],
        trend=[_campaign("paused", status="PAUSED")],
    )

    response = client.get("/presupuestos/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["count"] == 0
    assert body["proposals"] == []


def test_presupuestos_page_has_separate_preview_ui_without_apply_call():
    from routes.presupuestos import _PAGE

    assert "Generar preview de propuestas" in _PAGE
    assert "Preview, no guardado" in _PAGE
    assert "No aplica cambios" in _PAGE
    assert 'fetch("/presupuestos/preview' in _PAGE
    preview_block = _PAGE.split("function loadPreview()", 1)[1]
    preview_block = preview_block.split("function renderPreview", 1)[0]
    assert "/apply-budget-changes" not in preview_block
    assert "class='pick'" not in preview_block


def test_manual_preview_ui_has_review_buttons_without_apply_language():
    from routes.presupuestos import _PAGE

    assert "Rechazar" in _PAGE
    assert "Posponer" in _PAGE
    assert "Mantener en revisión" in _PAGE
    assert "/budget-recommendations/review-action" in _PAGE
    review_block = _PAGE.split("function reviewAction(", 1)[1]
    review_block = review_block.split("function updateApplyState", 1)[0]
    assert "/apply-budget-changes" not in review_block
    assert "update_campaign_budget" not in review_block
    assert "validate_only" not in review_block


def test_presupuestos_preview_uses_human_copy_for_security_rules():
    from routes.presupuestos import _PAGE

    assert "Presupuestos AI &mdash; Revisión manual" in _PAGE
    assert "Campaña" in _PAGE
    assert "Sin propuestas guardadas pendientes." in _PAGE
    assert "Propuestas guardadas:" in _PAGE
    assert "Preview actual:" in _PAGE
    assert "Dirección" in _PAGE
    assert "Razón" in _PAGE
    assert "7 días:" in _PAGE
    assert "30 días:" in _PAGE
    assert "Reglas de seguridad" in _PAGE
    assert "Solo vista previa" in _PAGE
    assert "No se guardó ninguna propuesta" in _PAGE
    assert "No se aplican cambios de presupuesto" in _PAGE
    assert "Aumentar" in _PAGE
    assert "Reducir" in _PAGE
    assert "Revisar" in _PAGE
    assert "Aumento máximo: 10%" in _PAGE
    assert "Aumento máximo: $50 MXN/día" in _PAGE
    assert "Aumento máximo: $30 MXN/día" in _PAGE
    assert "Hay señales útiles, pero no son pedidos o reservas confirmadas." in _PAGE
    assert "La campaña usa presupuesto compartido." in _PAGE


def test_presupuestos_preview_human_copy_keeps_apply_flow_out_of_preview_block():
    from routes.presupuestos import _PAGE

    assert "Preview, no guardado" in _PAGE
    assert "No aplica cambios" in _PAGE
    preview_block = _PAGE.split("function loadPreview()", 1)[1]
    preview_block = preview_block.split("function render()", 1)[0]
    assert "Preview, no guardado · No aplica cambios" not in preview_block
    assert "/apply-budget-changes" not in preview_block
    assert "class='pick'" not in preview_block
    assert "X-API-Token" not in preview_block


def test_save_preview_requires_token(client, isolated_db, admin_token):
    response = client.post("/budget-preview/save", json=_save_payload())

    assert response.status_code == 401


def test_save_preview_increase_creates_scale_pending_decision(
    client, isolated_db, admin_token, monkeypatch,
):
    sync = MagicMock(return_value=True)
    monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)

    response = client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Propuesta guardada para revisión manual."
    assert body["applied"] is False
    assert body["executed"] is False
    assert body["gcs_synced"] is True

    with sqlite3.connect(isolated_db.db_path) as conn:
        row = conn.execute(
            "SELECT action_type, decision, executed, campaign_id, campaign_name, evidence_json "
            "FROM autonomous_decisions WHERE id = ?",
            (body["decision_id"],),
        ).fetchone()
    assert row[0] == "scale"
    assert row[1] == "proposed"
    assert row[2] == 0
    assert row[3] == "22612348265"
    assert row[4] == "Thai Mérida - Local"
    assert '"source": "manual_preview"' in row[5]
    assert '"new_budget_mxn": 173.8' in row[5]
    assert '"saved_by": "admin_token_user"' in row[5]
    sync.assert_called_once_with()


def test_save_preview_decrease_creates_reduce_pending_decision(
    client, isolated_db, admin_token,
):
    payload = _save_payload(direction="decrease", suggested_budget_mxn=140.0, change_mxn=-18.0)

    response = client.post("/budget-preview/save", json=payload, headers=HEADERS_OK)

    assert response.status_code == 200
    body = response.json()
    with sqlite3.connect(isolated_db.db_path) as conn:
        action_type = conn.execute(
            "SELECT action_type FROM autonomous_decisions WHERE id = ?",
            (body["decision_id"],),
        ).fetchone()[0]
    assert action_type == "reduce"


@pytest.mark.parametrize(
    "payload,reason",
    [
        (_save_payload(direction="hold"), "review_only_not_saveable"),
        (_save_payload(campaign_id=""), "missing_campaign_id"),
        (_save_payload(suggested_budget_mxn=None), "missing_suggested_budget_mxn"),
        (_save_payload(suggested_budget_mxn=0), "invalid_suggested_budget_mxn"),
        (_save_payload(current_budget_mxn=0), "invalid_current_budget_mxn"),
        (_save_payload(direction="optimize"), "invalid_direction"),
    ],
)
def test_save_preview_rejects_invalid_payloads(
    client, isolated_db, admin_token, payload, reason, monkeypatch,
):
    sync = MagicMock(return_value=True)
    monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)

    response = client.post("/budget-preview/save", json=payload, headers=HEADERS_OK)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["reason"] == reason
    with sqlite3.connect(isolated_db.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM autonomous_decisions").fetchone()[0]
    assert count == 0
    sync.assert_not_called()


def test_save_preview_prevents_duplicate_pending_campaign(
    client, isolated_db, admin_token, monkeypatch,
):
    sync = MagicMock(return_value=True)
    monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)
    first = client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK).json()
    sync.reset_mock()
    second = client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK).json()

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert second["existing_decision_id"] == first["decision_id"]
    assert second["message"] == "Ya existe una propuesta pendiente para esta campaña."
    assert second["applied"] is False
    with sqlite3.connect(isolated_db.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM autonomous_decisions").fetchone()[0]
    assert count == 1
    sync.assert_not_called()


@pytest.mark.parametrize("sync_result", [False, RuntimeError("gcs unavailable")])
def test_save_preview_success_continues_when_gcs_sync_fails(
    client, isolated_db, admin_token, monkeypatch, sync_result,
):
    sync = MagicMock(side_effect=sync_result if isinstance(sync_result, Exception) else None)
    if not isinstance(sync_result, Exception):
        sync.return_value = sync_result
    monkeypatch.setattr("engine.db_sync.upload_to_gcs", sync)

    response = client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["gcs_synced"] is False
    assert body["warning"] == "preview_saved_locally_but_gcs_sync_failed"
    sync.assert_called_once_with()


def test_saved_preview_appears_in_presupuestos_data(
    client, isolated_db, admin_token, customer_id_env, monkeypatch,
):
    monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
    client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK)

    response = client.get("/presupuestos/data")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    rec = body["recommendations"][0]
    assert rec["action_type_original"] == "scale"
    assert rec["campaign_id"] == "22612348265"
    assert rec["new_budget_mxn"] == 173.8
    assert rec["apply_enabled"] is False
    assert rec["apply_disabled_reason"] == "Pendiente de fase de aprobación"
    assert rec["review_status"] == "Guardada para revisión"


def test_presupuestos_data_keeps_manual_preview_visible_but_not_applyable(
    client, isolated_db, admin_token, customer_id_env, monkeypatch,
):
    monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
    client.post("/budget-preview/save", json=_save_payload(campaign_id="22839241090"), headers=HEADERS_OK)

    body = client.get("/presupuestos/data").json()

    assert body["count"] == 1
    rec = body["recommendations"][0]
    assert rec["campaign_id"] == "22839241090"
    assert rec["apply_enabled"] is False
    assert rec["apply_disabled_reason"] == "Pendiente de fase de aprobación"
    assert rec["review_status"] == "Guardada para revisión"


def test_save_preview_does_not_call_budget_mutation(
    client, isolated_db, admin_token, monkeypatch,
):
    update = MagicMock()
    monkeypatch.setattr("engine.ads_client.update_campaign_budget", update)

    response = client.post("/budget-preview/save", json=_save_payload(), headers=HEADERS_OK)

    assert response.status_code == 200
    update.assert_not_called()


def test_preview_ui_has_save_button_only_for_actionable_rows():
    from routes.presupuestos import _PAGE

    assert "Guardar para revisión" in _PAGE
    assert "Solo revisión. No se puede guardar como cambio de presupuesto." in _PAGE
    assert "Guardada para revisión" in _PAGE
    assert "Aplicación pendiente de habilitar" in _PAGE
    preview_block = _PAGE.split("function loadPreview()", 1)[1]
    preview_block = preview_block.split("function render()", 1)[0]
    assert "/budget-preview/save" in preview_block
    assert "/apply-budget-changes" not in preview_block
    assert "class='pick'" not in preview_block
