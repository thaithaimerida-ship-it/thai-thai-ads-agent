"""
Tests para el desacople del warmer de reseñas de /health.

Contrato deseado:
- GET /health responde 200 al instante y NUNCA dispara warm_reviews_cache
  (un health check solo dice "estoy vivo"; no hace trabajo pesado de red).
- POST /cron/warm-reviews está protegido con require_token (X-API-Token) y,
  con token válido, dispara warm_reviews_cache exactamente una vez.

NO toca la red ni GBP: se espía engine.gbp_reviews.warm_reviews_cache con un mock.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-warm"


@pytest.fixture
def warm_spy(monkeypatch):
    """Reemplaza warm_reviews_cache por un espía; así verificamos quién lo llama."""
    import engine.gbp_reviews as gbp
    spy = MagicMock()
    monkeypatch.setattr(gbp, "warm_reviews_cache", spy)
    return spy


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    from main import app
    return TestClient(app)


# ---------- /health debe ser barato y NO calentar ----------

def test_health_200_y_status_ok(client, warm_spy):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_no_dispara_warm(client, warm_spy):
    client.get("/health")
    warm_spy.assert_not_called()


def test_health_conserva_contrato_version_y_skills(client, warm_spy):
    body = client.get("/health").json()
    assert body["version"] == "12.0.0"
    assert isinstance(body["skills"], list) and body["skills"]


# ---------- /cron/warm-reviews protegido y funcional ----------

def test_warm_401_sin_token(client, warm_spy):
    assert client.post("/cron/warm-reviews").status_code == 401
    warm_spy.assert_not_called()


def test_warm_401_token_invalido(client, warm_spy):
    r = client.post("/cron/warm-reviews", headers={"X-API-Token": "wrong"})
    assert r.status_code == 401
    warm_spy.assert_not_called()


def test_warm_200_con_token_llama_warm_una_vez(client, warm_spy):
    r = client.post("/cron/warm-reviews", headers={"X-API-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    warm_spy.assert_called_once()
