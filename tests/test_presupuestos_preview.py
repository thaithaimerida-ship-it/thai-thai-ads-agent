from __future__ import annotations

import json
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


def _mark_saved_preview_validated(memory, decision_id: int, *, applied=False) -> None:
    with sqlite3.connect(memory.db_path) as conn:
        row = conn.execute(
            "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        evidence = json.loads(row[0])
        evidence["approval_validation"] = {
            "validated": True,
            "validated_at": "2026-05-28T21:30:56+00:00",
            "current_budget_verified_mxn": evidence["current_budget_mxn"],
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


def test_presupuestos_page_has_read_only_budget_history_section():
    from routes.presupuestos import _PAGE

    assert "Historial de presupuestos" in _PAGE
    assert 'fetch("/presupuestos/history?status=all&amp;limit=20")' not in _PAGE
    assert 'fetch("/presupuestos/history?status=all&limit=20")' in _PAGE
    assert "function loadHistory()" in _PAGE
    assert "function renderHistory(history)" in _PAGE
    assert "Sin historial de presupuestos." in _PAGE
    assert "No se pudo cargar el historial de presupuestos." in _PAGE


def test_presupuestos_history_render_shows_expected_budget_audit_copy():
    from routes.presupuestos import _PAGE

    history_block = _PAGE.split("function renderHistory(history)", 1)[1]
    history_block = history_block.split("function historyResultLabel", 1)[0]

    assert "Thai Mérida - Delivery" not in history_block
    assert "Fecha" in history_block
    assert "Campaña" in history_block
    assert "Estado" in history_block
    assert "Presupuesto anterior" in history_block
    assert "Presupuesto nuevo" in history_block
    assert "Resultado" in history_block
    assert "Detalle" in history_block
    assert "review_status_label" in history_block
    assert "previous_budget_mxn" in history_block
    assert "applied_budget_mxn" in history_block
    assert "historyResultLabel" in history_block
    assert "historyDetailText" in history_block
    assert "$\" + Number(h.previous_budget_mxn).toFixed(2)" in history_block
    assert "$\" + Number(h.applied_budget_mxn).toFixed(2)" in history_block


def test_presupuestos_history_labels_google_ads_success_and_validate_apply_ok():
    from routes.presupuestos import _PAGE

    assert "Google Ads OK" in _PAGE
    assert "validate_only OK / apply OK" in _PAGE
    result_block = _PAGE.split("function historyResultLabel", 1)[1]
    result_block = result_block.split("function historyDetailText", 1)[0]
    detail_block = _PAGE.split("function historyDetailText", 1)[1]
    detail_block = detail_block.split("function render()", 1)[0]

    assert "apply_status === \"success\"" in result_block
    assert "Google Ads OK" in result_block
    assert "validate_only_status === \"success\"" in detail_block
    assert "apply_status === \"success\"" in detail_block
    assert "validate_only OK / apply OK" in detail_block


def test_presupuestos_history_block_has_no_mutating_controls_or_calls():
    from routes.presupuestos import _PAGE

    history_section = _PAGE.split("<section id=\"historySection\"", 1)[1]
    history_section = history_section.split("<div id=\"banner\"", 1)[0]
    history_block = _PAGE.split("function renderHistory(history)", 1)[1]
    history_block = history_block.split("function historyResultLabel", 1)[0]

    combined = history_section + history_block
    assert "Aplicar presupuesto" not in combined
    assert "class='pick'" not in combined
    assert 'class="pick"' not in combined
    assert "/budget-recommendations/apply-approved" not in combined
    assert "/apply-budget-changes" not in combined
    assert "decision_ids" not in combined
    assert "<button" not in history_section


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


def test_manual_preview_ui_has_apply_approved_button_with_confirmation_gate():
    from routes.presupuestos import _PAGE

    assert "Aplicar presupuesto" in _PAGE
    assert "Esto cambiar\u00e1 el presupuesto real en Google Ads." in _PAGE
    assert "cancelada." in _PAGE
    assert "Presupuesto aplicado correctamente." in _PAGE
    assert "function applyApproved(" in _PAGE
    assert 'prompt("Escribe APLICAR para cambiar el presupuesto real en Google Ads.")' in _PAGE
    assert 'confirmation !== "APLICAR"' in _PAGE
    assert "/budget-recommendations/apply-approved" in _PAGE
    apply_block = _PAGE.split("function applyApproved(", 1)[1]
    apply_block = apply_block.split("function updateApplyState", 1)[0]
    assert "/budget-recommendations/apply-approved" in apply_block
    assert "/apply-budget-changes" not in apply_block
    assert "decision_ids" not in apply_block
    assert "new_budget_mxn" not in apply_block


def test_manual_preview_render_only_shows_apply_button_when_can_apply_approved():
    from routes.presupuestos import _PAGE

    render_block = _PAGE.split("function render()", 1)[1]
    render_block = render_block.split("function savePreview", 1)[0]
    assert "r.can_apply_approved === true" in render_block
    assert 'r.can_apply_approved === true\n      ? "Lista para aplicación final"' in render_block
    assert "var validateApprovalButton = r.approval_validated === true" in render_block
    assert "data-action='apply_approved'" in render_block
    assert "Aplicar presupuesto" in render_block
    manual_preview_row_block = render_block.split("var reviewButtons = r.is_manual_preview", 1)[1]
    manual_preview_row_block = manual_preview_row_block.split("var actionLabel", 1)[0]
    assert "class='pick'" not in manual_preview_row_block
    assert "validateApprovalButton +" in manual_preview_row_block


def test_manual_preview_validated_applyable_copy_is_final_apply_only():
    from routes.presupuestos import _PAGE

    render_block = _PAGE.split("function render()", 1)[1]
    render_block = render_block.split("function savePreview", 1)[0]
    status_block = render_block.split("var disabledLabel =", 1)[1]
    status_block = status_block.split("var applyApprovedButton", 1)[0]
    validate_block = render_block.split("var validateApprovalButton =", 1)[1]
    validate_block = validate_block.split("var reviewButtons", 1)[0]

    assert "Lista para aplicación final" in status_block
    assert "Aplicación pendiente de habilitar" not in status_block
    assert 'r.approval_validated === true\n      ? ""' in validate_block
    assert "Validar aplicación" in validate_block
    assert "Aplicar presupuesto" in render_block
    assert "Esto cambiará el presupuesto real en Google Ads." in render_block
    assert "/apply-budget-changes" not in validate_block
    apply_block = _PAGE.split("function applyApproved(", 1)[1]
    apply_block = apply_block.split("function updateApplyState", 1)[0]
    assert "decision_ids" not in apply_block


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


def test_presupuestos_data_exposes_manual_approval_flags(
    client, isolated_db, admin_token, customer_id_env, monkeypatch,
):
    monkeypatch.setattr("main.get_engine_modules", MagicMock(side_effect=RuntimeError("no live ads")))
    client.post("/budget-preview/save", json=_save_payload(campaign_id="22839241090"), headers=HEADERS_OK)

    rec = client.get("/presupuestos/data").json()["recommendations"][0]

    assert rec["approval_validated"] is False
    assert rec["approval_applied"] is False
    assert rec["executed"] == 0
    assert rec["approved_at"] is None
    assert rec["rejected_at"] is None
    assert rec["postponed_at"] is None
    assert rec["can_apply_approved"] is False


def test_presupuestos_data_can_apply_approved_for_validated_manual_preview(
    client, isolated_db, admin_token, customer_id_env, monkeypatch,
):
    monkeypatch.setattr("main.get_engine_modules", MagicMock(return_value={
        "get_ads_client": MagicMock(),
        "fetch_campaign_data": MagicMock(return_value=[_campaign("22839241090", budget=158.0)]),
    }))
    response = client.post(
        "/budget-preview/save",
        json=_save_payload(campaign_id="22839241090", current_budget_mxn=158.0),
        headers=HEADERS_OK,
    )
    decision_id = response.json()["decision_id"]
    _mark_saved_preview_validated(isolated_db, decision_id, applied=False)

    rec = client.get("/presupuestos/data").json()["recommendations"][0]

    assert rec["approval_validated"] is True
    assert rec["approval_applied"] is False
    assert rec["current_budget_mxn"] == 158.0
    assert rec["new_budget_mxn"] == 173.8
    assert rec["can_apply_approved"] is True


@pytest.mark.parametrize(
    "mutation",
    ["not_validated", "applied", "executed", "approved", "rejected", "postponed"],
)
def test_presupuestos_data_can_apply_approved_false_for_blocked_states(
    mutation, client, isolated_db, admin_token, customer_id_env, monkeypatch,
):
    monkeypatch.setattr("main.get_engine_modules", MagicMock(return_value={
        "get_ads_client": MagicMock(),
        "fetch_campaign_data": MagicMock(return_value=[_campaign("22839241090", budget=158.0)]),
    }))
    response = client.post(
        "/budget-preview/save",
        json=_save_payload(campaign_id="22839241090", current_budget_mxn=158.0),
        headers=HEADERS_OK,
    )
    decision_id = response.json()["decision_id"]
    if mutation != "not_validated":
        _mark_saved_preview_validated(isolated_db, decision_id, applied=(mutation == "applied"))
    with sqlite3.connect(isolated_db.db_path) as conn:
        if mutation == "executed":
            conn.execute("UPDATE autonomous_decisions SET executed = 1 WHERE id = ?", (decision_id,))
        elif mutation == "approved":
            conn.execute("UPDATE autonomous_decisions SET approved_at = datetime('now') WHERE id = ?", (decision_id,))
        elif mutation == "rejected":
            conn.execute("UPDATE autonomous_decisions SET rejected_at = datetime('now') WHERE id = ?", (decision_id,))
        elif mutation == "postponed":
            conn.execute("UPDATE autonomous_decisions SET postponed_at = datetime('now') WHERE id = ?", (decision_id,))

    body = client.get("/presupuestos/data").json()

    if mutation in {"executed", "approved", "rejected", "postponed"}:
        assert body["recommendations"] == []
    else:
        rec = body["recommendations"][0]
        assert rec["can_apply_approved"] is False


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
