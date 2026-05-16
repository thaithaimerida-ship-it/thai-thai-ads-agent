"""
Tests del gate de autenticacion require_token.

Justificacion (regla de testing del proyecto): require_token es la puerta
que protege /execute-optimization, un endpoint que ESCRIBE en Google Ads
(agrega negative keywords). Por eso se testea aunque sea codigo simple.
"""
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from routes.auth_token import require_token
from main import app

client = TestClient(app)


# --- Unit: require_token ---

def test_acepta_token_correcto(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secreto-123")
    assert require_token(x_api_token="secreto-123") is None


def test_rechaza_token_incorrecto(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secreto-123")
    with pytest.raises(HTTPException) as exc:
        require_token(x_api_token="otro")
    assert exc.value.status_code == 401


def test_rechaza_token_ausente(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secreto-123")
    with pytest.raises(HTTPException) as exc:
        require_token(x_api_token="")
    assert exc.value.status_code == 401


def test_falla_cerrado_sin_env_var(monkeypatch):
    """Si ADMIN_API_TOKEN no esta seteada, rechaza TODO (fail closed)."""
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_token(x_api_token="loquesea")
    assert exc.value.status_code == 401


# --- Integracion: /execute-optimization queda protegido ---

def test_execute_optimization_sin_token_da_401(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secreto-123")
    resp = client.post("/execute-optimization", json={"actions": []})
    assert resp.status_code == 401


def test_execute_optimization_con_token_pasa_auth(monkeypatch):
    """actions=[] no toca Google Ads; solo verifica que el gate deja pasar."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "secreto-123")
    resp = client.post(
        "/execute-optimization",
        json={"actions": []},
        headers={"X-API-Token": "secreto-123"},
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "success"
