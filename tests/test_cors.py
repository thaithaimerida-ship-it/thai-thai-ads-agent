from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def _cors_kwargs(app):
    middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)
    return middleware.kwargs


def test_default_cors_origins_are_explicit(monkeypatch):
    import main

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ALLOW_LOCALHOST_CORS", raising=False)

    origins = main.resolve_cors_origins()

    assert "*" not in origins
    assert "https://thai-thai-ads-agent-624172071613.us-central1.run.app" in origins
    assert "https://thaithaimerida.com" in origins


def test_allowed_origins_env_parses_comma_separated_list(monkeypatch):
    import main

    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://one.example.com, https://two.example.com,,https://one.example.com",
    )
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ALLOW_LOCALHOST_CORS", raising=False)

    assert main.resolve_cors_origins() == [
        "https://one.example.com",
        "https://two.example.com",
    ]


def test_allowed_origin_receives_cors_header():
    from main import app

    response = TestClient(app).get(
        "/health",
        headers={"Origin": "https://thai-thai-ads-agent-624172071613.us-central1.run.app"},
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://thai-thai-ads-agent-624172071613.us-central1.run.app"
    )


def test_disallowed_origin_does_not_receive_cors_header():
    from main import app

    response = TestClient(app).get(
        "/health",
        headers={"Origin": "https://evil.example.com"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_localhost_is_not_allowed_by_default(monkeypatch):
    import main

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ALLOW_LOCALHOST_CORS", raising=False)

    origins = main.resolve_cors_origins()

    assert "http://localhost:8080" not in origins
    assert "http://127.0.0.1:5173" not in origins


def test_localhost_is_allowed_in_development(monkeypatch):
    import main

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ALLOW_LOCALHOST_CORS", raising=False)

    origins = main.resolve_cors_origins()

    assert "http://localhost:8080" in origins
    assert "http://127.0.0.1:5173" in origins


def test_localhost_is_allowed_with_explicit_flag(monkeypatch):
    import main

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("ALLOW_LOCALHOST_CORS", "true")

    origins = main.resolve_cors_origins()

    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:8080" in origins


def test_cors_credentials_are_disabled():
    from main import app

    kwargs = _cors_kwargs(app)

    assert kwargs["allow_credentials"] is False
    assert kwargs["allow_origins"] != ["*"]


def test_presupuestos_routes_still_respond():
    from main import app

    client = TestClient(app)

    assert client.get("/presupuestos").status_code == 200
    assert client.get("/presupuestos/data").status_code == 200
