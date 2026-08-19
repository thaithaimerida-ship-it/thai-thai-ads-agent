"""Tests del cartero nuevo POST /monitor/send (reemplazo del Apps Script).

El renderer v6.2 NO se toca: aquí se mockea build_monitor_digest, así que los snapshots del
renderer (test_monitor_renderer_v2) quedan intactos.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.monitor as M
from engine import acciones_log


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(M.router)
    return TestClient(app)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("MONITOR_SEND_TOKEN", "sec")
    monkeypatch.delenv("MONITOR_SCHEDULER_SA", raising=False)
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    cap = {"sent": 0, "mode": None, "subject": None}
    monkeypatch.setattr(M, "_build_search_terms_payload",
                        lambda dr: {"status": "success", "date_range": dr, "search_terms": []})
    monkeypatch.setattr(M, "_build_context", lambda dr, mode: cap.update(mode=mode) or {"mode": mode})
    monkeypatch.setattr(M, "build_monitor_digest",
                        lambda p, c: {"subject_email": "S", "html_email": "<html>H", "text_email": "T"})
    monkeypatch.setattr(M.monitor_mailer, "enviar_digest",
                        lambda s, h, t, destinatario=None: cap.update(sent=cap["sent"] + 1, subject=s) or {"enviado": True})
    return cap


def test_send_sin_token_403(client, setup):
    assert client.post("/monitor/send").status_code == 403          # sin token ni OIDC
    assert client.post("/monitor/send?token=malo").status_code == 403


def test_send_envia_y_es_idempotente(client, setup):
    r1 = client.post("/monitor/send?token=sec")
    assert r1.status_code == 200 and r1.json()["status"] == "sent"
    assert setup["sent"] == 1
    r2 = client.post("/monitor/send?token=sec")                     # mismo día
    assert r2.json()["status"] == "already_sent" and setup["sent"] == 1  # no reenvía


def test_send_force_reenvia(client, setup):
    client.post("/monitor/send?token=sec")
    r = client.post("/monitor/send?token=sec&force=true")
    assert r.json()["status"] == "sent" and setup["sent"] == 2


def test_send_tipo_solo_rotula(client, setup):
    # Contrato v6.2: `tipo` ya no cambia el formato (siempre el completo); solo rotula el envío.
    client.post("/monitor/send?token=sec&tipo=viernes&force=true")
    assert setup["mode"] == "viernes"
    client.post("/monitor/send?token=sec&tipo=lunes&force=true")
    assert setup["mode"] == "lunes"


def test_send_marca_sufijo_asunto(client, setup):
    client.post("/monitor/send?token=sec&force=true")
    assert setup["subject"] == "S"                                  # sin marca → asunto tal cual
    client.post("/monitor/send?token=sec&force=true&marca=prueba%2014:32")
    assert setup["subject"] == "S · prueba 14:32"                   # marca → sufijo al asunto


def test_send_degradado_cuando_ads_falla(client, setup, monkeypatch):
    # Token de Google Ads muerto → el endpoint NO da 500: manda reporte degradado con ads_error.
    cap = {}
    def _raise(dr):
        raise RuntimeError("No hay credenciales de Google Ads disponibles (env vars ni yaml)")
    monkeypatch.setattr(M, "_build_search_terms_payload", _raise)
    monkeypatch.setattr(M, "build_monitor_digest",
                        lambda p, c: cap.update(c) or {"subject_email": "S", "html_email": "H", "text_email": "T"})
    r = client.post("/monitor/send?token=sec&force=true")
    assert r.status_code == 200 and r.json()["status"] == "sent"   # correo sale igual
    assert cap.get("ads_error") == {"kind": "ads", "exc_type": "RuntimeError"}


def test_send_degradado_excepcion_inesperada(client, setup, monkeypatch):
    # Excepción NO de Ads (bug) → también degrada, pero marcada 'unexpected' (banner distinto).
    cap = {}
    def _raise(dr):
        raise TypeError("boom: bug interno no relacionado con Ads")
    monkeypatch.setattr(M, "_build_search_terms_payload", _raise)
    monkeypatch.setattr(M, "build_monitor_digest",
                        lambda p, c: cap.update(c) or {"subject_email": "S", "html_email": "H", "text_email": "T"})
    r = client.post("/monitor/send?token=sec&force=true")
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert cap.get("ads_error") == {"kind": "unexpected", "exc_type": "TypeError"}
