"""
Tests de POST /execute-optimization — propagación de match_type y fail-closed.

Justificación (regla de testing del proyecto): este endpoint dispara
add_negative_keyword contra Google Ads real. El match type viaja desde la
mini-app /negativos (suggested_match_type del clasificador) y NO debe terminar
nunca en BROAD por accidente. Tests obligatorios.

NO toca Google Ads ni la DB real: patchea routes.analysis._get_engine y
routes.analysis.get_db_path (SQLite a tmp_path).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-exec"


def _ank(client, customer_id, campaign_id, keyword_text, match_type=None):
    """Stub de add_negative_keyword que eco-devuelve el match_type recibido."""
    return {"status": "success", "keyword": keyword_text,
            "match_type": match_type, "channel": "SEARCH"}


@pytest.fixture
def captured():
    return MagicMock(side_effect=_ank)


@pytest.fixture
def setup(tmp_path, monkeypatch, captured):
    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    import routes.analysis as analysis
    db = str(tmp_path / "exec.db")
    monkeypatch.setattr(analysis, "get_db_path", lambda: db)
    fake_engine = {"get_ads_client": lambda: MagicMock(), "add_negative_keyword": captured}
    monkeypatch.setattr(analysis, "_get_engine", lambda: fake_engine)
    monkeypatch.setattr(analysis, "_build_search_terms_payload", lambda date_range="LAST_7_DAYS": {
        "status": "success",
        "date_range": date_range,
        "search_terms": [
            {
                "query": "querreke",
                "campaign_id": "111",
                "suggested_negative": "querreke",
                "suggested_match_type": "EXACT",
                "negative_allowed": True,
                "base_negative_eligible": True,
                "semantic_class": "red_safe",
                "conversion_quality": "none",
                "already_negative": False,
            },
            {
                "query": "muay thai",
                "campaign_id": "111",
                "suggested_negative": "muay thai",
                "suggested_match_type": "PHRASE",
                "negative_allowed": True,
                "base_negative_eligible": True,
                "semantic_class": "red_safe",
                "conversion_quality": "none",
                "already_negative": False,
            },
        ],
    })
    return captured


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def _post(client, actions):
    return client.post("/execute-optimization",
                       headers={"X-API-Token": TOKEN},
                       json={"actions": actions})


def test_401_sin_token(client, setup):
    assert client.post("/execute-optimization", json={"actions": []}).status_code == 401


def test_exact_propaga_exact(client, setup, captured):
    """suggested_match_type=EXACT (entidad curada) se respeta hasta add_negative_keyword."""
    r = _post(client, [{"type": "block_keyword", "keyword": "querreke",
                        "campaign_id": "111", "match_type": "EXACT"}])
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    captured.assert_called_once()
    assert captured.call_args.kwargs.get("match_type") == "EXACT"
    assert data["results"][0]["status"] == "executed"


def test_phrase_propaga_phrase(client, setup, captured):
    """suggested_match_type=PHRASE (patrón rojo) se respeta hasta add_negative_keyword."""
    r = _post(client, [{"type": "block_keyword", "keyword": "muay thai",
                        "campaign_id": "111", "match_type": "PHRASE"}])
    assert r.status_code == 200
    captured.assert_called_once()
    assert captured.call_args.kwargs.get("match_type") == "PHRASE"
    assert r.json()["results"][0]["status"] == "executed"


def test_sin_match_type_no_aplica_broad(client, setup, captured):
    """Acción sin match_type → fail-closed: NO se llama add_negative_keyword."""
    r = _post(client, [{"type": "block_keyword", "keyword": "comida asiatica",
                        "campaign_id": "111"}])
    assert r.status_code == 200
    captured.assert_not_called()
    res = r.json()["results"][0]
    assert res["status"] == "rejected"
    assert r.json()["executed"] == 0


def test_broad_desde_negativos_rechazado(client, setup, captured):
    """match_type=BROAD desde /negativos → rechazado, sin llamar a la mutación."""
    r = _post(client, [{"type": "block_keyword", "keyword": "sushi",
                        "campaign_id": "111", "match_type": "BROAD"}])
    assert r.status_code == 200
    captured.assert_not_called()
    assert r.json()["results"][0]["status"] == "rejected"


def test_match_type_invalido_rechazado(client, setup, captured):
    """match_type fuera de {EXACT,PHRASE} → rechazado, sin mutación."""
    r = _post(client, [{"type": "block_keyword", "keyword": "ramen",
                        "campaign_id": "111", "match_type": "FUZZY"}])
    assert r.status_code == 200
    captured.assert_not_called()
    assert r.json()["results"][0]["status"] == "rejected"


def test_accion_no_block_keyword_intacta(client, setup, captured):
    """Acciones no relacionadas siguen en 'recorded/manual_required' (retrocompat)."""
    r = _post(client, [{"type": "pause_campaign", "campaign_id": "111",
                        "reason": "test"}])
    assert r.status_code == 200
    captured.assert_not_called()
    res = r.json()["results"][0]
    assert res["status"] == "recorded"
    assert res["manual_required"] is True
