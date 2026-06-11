"""Tests de la página de bloqueo de negativos — Fase B1 (candados, sin red, sin Ads)."""
import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine import acciones_log, negativos_apply, negativos_service
from routes import acciones_bloqueo


def _row(query, campaign_name, campaign_id, cost=30.0, clicks=20):
    return {"query": query, "campaign_name": campaign_name, "campaign_id": campaign_id,
            "clicks": clicks, "cost": cost, "conversions": 0.0, "all_conversions": 0.0,
            "conversion_quality": "none", "semantic_class": "neutral",
            "already_negative": False, "suggested_match_type": "EXACT"}


def _payload():
    # "casa thai" es competitor_root → bloqueable. Aparece en una SEARCH y una SMART.
    return {"status": "success", "date_range": "LAST_7_DAYS", "search_terms": [
        _row("bankok casa thai", "Thai Merida - Delivery Search", "111"),
        _row("casa thai bangkok", "Thai Merida - Local", "22612348265", cost=10.0),
    ]}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(acciones_bloqueo.router)
    return TestClient(app)


def test_sin_token_403(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    assert client.get("/acciones/bloqueo?term=casa+thai").status_code == 403
    r = client.post("/acciones/bloqueo/confirmar", json={"term": "casa thai", "campaign_ids": ["111"]})
    assert r.status_code == 403


def test_term_arbitrario_rechazado(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    res = negativos_service.confirmar_bloqueo("pizzeria random xyz", ["111"], payload=_payload())
    assert res["status"] == "rechazada" and res["motivo"] == "termino_no_valido"


def test_jamas_broad():
    src = inspect.getsource(negativos_apply) + inspect.getsource(negativos_service)
    # BROAD nunca como VALOR (string literal) — los comentarios "JAMÁS BROAD" no cuentan.
    assert '"BROAD"' not in src and "'BROAD'" not in src
    # funcional: ningún canal produce un match_type BROAD.
    for ch in ("SEARCH", "SMART"):
        r = negativos_apply.aplicar_en_campana("x", {"channel": ch, "name": "c", "id": "1"})
        assert r["match_type"] in ("EXACT", "THEME")


def test_un_termino_por_request():
    campos = acciones_bloqueo.ConfirmarBody.model_fields
    assert "term" in campos and "terms" not in campos  # una, no lista de términos


def test_smart_theme_bloqueado_si_contiene_marca(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    assert negativos_apply.contiene_marca("bankok casa thai")  # contiene "thai"
    ctx = negativos_service.contexto_bloqueo("bankok casa thai", payload=_payload())
    smart = [c for c in ctx["campanas"] if c["channel"] == "SMART"][0]
    assert smart["permitido"] is False and "marca" in smart["nota"].lower()
    # POST que solo marca la Smart → rechazado (guarda server-side)
    res = negativos_service.confirmar_bloqueo("bankok casa thai", ["22612348265"], payload=_payload())
    assert res["status"] == "rechazada" and res["motivo"] == "sin_campanas_validas"


def test_exact_solo_en_campanas_de_busqueda():
    s = negativos_apply.aplicar_en_campana("x", {"channel": "SEARCH", "name": "DS", "id": "1"})
    m = negativos_apply.aplicar_en_campana("hacienda teya", {"channel": "SMART", "name": "Local", "id": "2"})
    assert s["match_type"] == "EXACT"
    assert m["match_type"] == "THEME"  # Smart nunca EXACT


def test_dry_run_no_llama_ads_api(monkeypatch):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no Ads en dry-run")))
    r = negativos_apply.aplicar_en_campana("casa thai", {"channel": "SEARCH", "name": "DS", "id": "111"})
    assert r["status"] == "dry_run" and r["applied"] is False


def test_dejar_actualiza_diccionario_sin_tocar_ads(monkeypatch, tmp_path):
    dict_path = tmp_path / "dict.json"
    dict_path.write_text('{"acknowledged_external_roots": [], "competitor_roots": ["casa thai"]}', encoding="utf-8")
    monkeypatch.setattr(negativos_service, "_DICT_PATH", str(dict_path))
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dejar no toca Ads")))
    res = negativos_service.dejar("la rueda")
    assert res["toca_ads"] is False and res["agregado"] is True
    import json
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    assert "la rueda" in data["acknowledged_external_roots"]


def test_smart_manual_required_pending_y_receta(monkeypatch, tmp_path):
    # Smart habilitado (sin marca) en modo REAL → manual_required, sin tocar Ads,
    # log marca pending_manual y el correo trae la receta exacta.
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    dpath = tmp_path / "dict.json"
    dpath.write_text('{"acknowledged_external_roots": [], "competitor_roots": ["la rueda"]}', encoding="utf-8")
    monkeypatch.setattr(negativos_service, "_DICT_PATH", str(dpath))
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Smart no toca Ads")))
    captura = {}
    monkeypatch.setattr(negativos_service.acciones_email, "enviar",
                        lambda asunto, cuerpo: captura.update(asunto=asunto, cuerpo=cuerpo) or {"enviado": False})
    payload = {"status": "success", "date_range": "LAST_7_DAYS",
               "search_terms": [_row("la rueda restaurante", "Thai Merida - Local", "22612348265", cost=15.0)]}
    res = negativos_service.confirmar_bloqueo("la rueda restaurante", ["22612348265"], payload=payload)
    assert res["status"] == "ok"
    assert res["pending_manual"] == ["Thai Merida - Local"]
    assert "Theme negativo a pegar: la rueda restaurante" in captura["cuerpo"]
    assert "Temas de palabras clave negativas" in captura["cuerpo"]
    import json
    registro = json.loads((tmp_path / "log.jsonl").read_text(encoding="utf-8").strip())
    assert registro["pending_manual"] == ["Thai Merida - Local"]


def test_no_bloquear_dos_veces_mismo_termino(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    p = _payload()
    primera = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert primera["status"] == "ok" and primera["dry_run"] is True
    segunda = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert segunda["status"] == "rechazada" and segunda["motivo"] == "ya_bloqueado"
