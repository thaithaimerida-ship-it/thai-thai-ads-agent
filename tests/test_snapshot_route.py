"""
Tests para POST /snapshot-search-terms (Fase 2.1) — snapshot read-only.

NO toca Google Ads real ni GCS: patchea routes.analysis._get_engine,
engine.search_term_history.{get_db_path, download_from_gcs, upload_to_gcs}.
Aisla SQLite en tmp_path.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-snap"


def _yesterday_merida():
    try:
        from zoneinfo import ZoneInfo
        return (datetime.now(ZoneInfo("America/Merida")) - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")


SAMPLE_TERMS = [
    {"query": "querreke", "campaign_id": "111", "campaign_name": "Thai Mérida - Local",
     "cost_micros": 5_000_000, "conversions": 0.0, "clicks": 3, "impressions": 40},
    {"query": "comida tailandesa merida", "campaign_id": "111", "campaign_name": "Thai Mérida - Local",
     "cost_micros": 2_000_000, "conversions": 1.0, "clicks": 2, "impressions": 20},
]


@pytest.fixture
def fetch_mock():
    return MagicMock(return_value=[dict(t) for t in SAMPLE_TERMS])


@pytest.fixture
def setup(tmp_path, monkeypatch, fetch_mock):
    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    db = str(tmp_path / "snap.db")
    import engine.search_term_history as hist
    monkeypatch.setattr(hist, "get_db_path", lambda: db)
    monkeypatch.setattr(hist, "download_from_gcs", lambda: False)
    monkeypatch.setattr(hist, "upload_to_gcs", lambda: True)
    import routes.analysis as analysis
    fake_engine = {"get_ads_client": lambda: MagicMock(), "fetch_search_term_data": fetch_mock}
    monkeypatch.setattr(analysis, "_get_engine", lambda: fake_engine)
    return db


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_401_sin_token(client, setup):
    assert client.post("/snapshot-search-terms").status_code == 401


def test_401_token_invalido(client, setup):
    assert client.post("/snapshot-search-terms", headers={"X-API-Token": "wrong"}).status_code == 401


def test_success_con_token(client, setup):
    r = client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "success"
    assert d["date_range"] == "YESTERDAY"
    assert d["inserted"] == 2
    for k in ("inserted", "ignored", "pruned", "gcs_synced", "skipped_reason", "snapshot_date"):
        assert k in d


def test_usa_yesterday(client, setup, fetch_mock):
    client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN})
    # fetch_search_term_data(client, customer_id, "YESTERDAY")
    assert fetch_mock.call_args[0][2] == "YESTERDAY"


def test_snapshot_date_es_ayer_merida(client, setup):
    r = client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN})
    assert r.json()["snapshot_date"] == _yesterday_merida()


def test_idempotencia_no_duplica(client, setup):
    r1 = client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN}).json()
    r2 = client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN}).json()
    assert r1["inserted"] == 2
    assert r2["inserted"] == 0 and r2["ignored"] == 2


def test_no_dinero_ni_audit_ni_email(client, setup, monkeypatch):
    import engine.ads_client as ac
    upd, neg = MagicMock(), MagicMock()
    monkeypatch.setattr(ac, "update_campaign_budget", upd, raising=False)
    monkeypatch.setattr(ac, "add_negative_keyword", neg, raising=False)
    import agents.auditor as aud
    raa = MagicMock()
    monkeypatch.setattr(aud.Auditor, "run_autonomous_audit", raa, raising=False)
    import engine.email_sender as es
    sent = MagicMock()
    for name in ("send_email", "send_daily_report", "send_report"):
        if hasattr(es, name):
            monkeypatch.setattr(es, name, sent, raising=False)
    r = client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN})
    assert r.status_code == 200
    upd.assert_not_called()
    neg.assert_not_called()
    raa.assert_not_called()
    sent.assert_not_called()


def test_clasifica_correcto(client, setup):
    # querreke (entidad) -> rojo; comida tailandesa merida -> verde/blanco. Verifica via DB.
    import sqlite3
    db = setup
    client.post("/snapshot-search-terms", headers={"X-API-Token": TOKEN})
    conn = sqlite3.connect(db)
    rows = dict(conn.execute(
        "SELECT query_raw, classification FROM search_term_snapshots").fetchall())
    assert rows.get("querreke") == "rojo"
