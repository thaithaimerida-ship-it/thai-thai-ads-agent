from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def customer_id_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")


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


def test_preview_excludes_uncertain_tracking_shared_disabled_and_invalid_budget(
    client, customer_id_env, monkeypatch,
):
    _install_engine(
        monkeypatch,
        primary=[
            _campaign("unknown", conversion_quality="unknown"),
            _campaign("shared", shared=True),
            _campaign("paused", status="PAUSED"),
            _campaign("nobudget", budget=0),
            _campaign("ok", conversions=5.0),
        ],
        trend=[
            _campaign("unknown", conversion_quality="unknown"),
            _campaign("shared", shared=True),
            _campaign("paused", status="PAUSED"),
            _campaign("nobudget", budget=0),
            _campaign("ok", conversions=15.0),
        ],
    )

    body = client.get("/presupuestos/preview").json()

    assert [p["campaign_id"] for p in body["proposals"]] == ["ok"]


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
