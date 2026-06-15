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


def test_bandeja_lista_candidatos(monkeypatch):
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    data = negativos_service.contextos_bandeja()
    assert data["total"] >= 1
    assert any("casa thai" in c["term"] for c in data["items"])


def test_bandeja_card_smart_sin_checkbox():
    # Smart-only → SIN checkbox (solo flujo individual). SEARCH → checkbox con solo el id de búsqueda.
    smart_only = {"term": "bangkok casa thai", "variantes_count": 1, "gasto_total": 10, "ya_bloqueado_ts": None,
                  "campanas": [{"name": "Local (Smart)", "id": "22612348265", "channel": "SMART",
                                "gasto": 10, "permitido": False, "nota": "marca"}]}
    h = acciones_bloqueo._bandeja_card(smart_only, "TOK")
    assert "class='sel'" not in h and "Solo Smart" in h
    con_search = {"term": "almar restaurante merida", "variantes_count": 1, "gasto_total": 16, "ya_bloqueado_ts": None,
                  "campanas": [{"name": "Experiencia 2026", "id": "222", "channel": "SEARCH", "gasto": 16, "permitido": True}]}
    h2 = acciones_bloqueo._bandeja_card(con_search, "TOK")
    assert "class='sel'" in h2 and "data-ids='222'" in h2  # solo el id de búsqueda en el lote


def test_lote_bloqueo_tope_10_un_correo(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    correos = {"n": 0}
    monkeypatch.setattr(negativos_service.acciones_email, "enviar",
                        lambda a, c: correos.__setitem__("n", correos["n"] + 1) or {"enviado": False})
    items = [{"term": "bankok casa thai", "campaign_ids": ["111"]} for _ in range(12)]
    res = negativos_service.confirmar_lote(items)
    assert len(res["resultados"]) == 10 and res["bloqueados"] == 10   # tope 10
    assert correos["n"] == 1                                          # un solo correo


def test_lote_bloqueo_fallo_parcial_no_detiene(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    monkeypatch.setattr(negativos_service.acciones_email, "enviar", lambda a, c: {"enviado": False})
    res = negativos_service.confirmar_lote([
        {"term": "bankok casa thai", "campaign_ids": ["111"]},
        {"term": "pizzeria arbitraria inexistente", "campaign_ids": ["111"]}])
    assert res["bloqueados"] == 1 and res["fallidos"] == 1            # el fallo no detuvo al otro
    assert [r["motivo"] for r in res["resultados"] if r["status"] != "ok"] == ["termino_no_valido"]


def test_lote_bloqueo_ejecuta_per_termino_y_jamas_broad(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    monkeypatch.setattr(negativos_service.acciones_email, "enviar", lambda a, c: {"enviado": False})
    res = negativos_service.confirmar_lote([{"term": "bankok casa thai", "campaign_ids": ["111"]}])
    r = res["resultados"][0]
    assert r["status"] == "ok" and r["match_types"] == ["EXACT"]      # per-término, EXACT (jamás BROAD)


def test_bandeja_sin_token_403(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    assert client.get("/acciones/bloqueos").status_code == 403
    assert client.post("/acciones/bloqueos/lote", json={"items": []}).status_code == 403


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


def test_confirmar_devuelve_json_ok_dry_run_mensaje(client, monkeypatch):
    # El botón individual de la bandeja consume este JSON: {ok, dry_run, mensaje}.
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_bloqueo",
                        lambda term, ids: {"status": "ok", "dry_run": True, "term": term, "match_types": ["EXACT"]})
    r = client.post("/acciones/bloqueo/confirmar?token=secreto", json={"term": "casa thai", "campaign_ids": ["111"]})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["dry_run"] is True and "Simulado" in j["mensaje"]
    # rechazo → ok False + mensaje humano mapeado (y status 409)
    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_bloqueo",
                        lambda term, ids: {"status": "rechazada", "motivo": "ya_bloqueado"})
    r2 = client.post("/acciones/bloqueo/confirmar?token=secreto", json={"term": "x", "campaign_ids": ["1"]})
    assert r2.status_code == 409
    j2 = r2.json()
    assert j2["ok"] is False and j2["motivo"] == "ya_bloqueado" and "Ya estaba bloqueado" in j2["mensaje"]


def test_bandeja_card_boton_bloquear_inplace_sin_link():
    # El botón individual dispara in-place (onclick='bloquear') y YA NO enlaza la página individual.
    con_search = {"term": "almar restaurante merida", "variantes_count": 1, "gasto_total": 16, "ya_bloqueado_ts": None,
                  "campanas": [{"name": "Experiencia 2026", "id": "222", "channel": "SEARCH", "gasto": 16, "permitido": True}]}
    h = acciones_bloqueo._bandeja_card(con_search, "TOK")
    assert "onclick='bloquear(this)'" in h and ">Bloquear<" in h
    assert "/acciones/bloqueo?term=" not in h          # ya no navega a la individual
    assert "Revisar y bloquear" not in h               # botón renombrado


def test_pagina_individual_sigue_html(client, monkeypatch):
    # /acciones/bloqueo (singular) se queda viva en modo HTML para accesos directos.
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(acciones_bloqueo.negativos_service, "contexto_bloqueo",
                        lambda term, *a, **k: {"term": term, "variantes": [], "variantes_count": 0,
                                               "gasto_total": 0, "contiene_marca": False, "campanas": [],
                                               "ya_bloqueado_ts": None, "dry_run": True, "bloqueable": True})
    r = client.get("/acciones/bloqueo?term=casa+thai&token=secreto")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Revisar y bloquear" in r.text              # la página individual conserva su flujo


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


def test_dry_run_no_consume_termino_pero_real_si(monkeypatch, tmp_path):
    # BUG 1: simulacros repetibles; solo el bloqueo REAL (applied=True) consume el término.
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    p = _payload()
    # 1) dos simulacros → ambos proceden
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    assert negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)["status"] == "ok"
    assert negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)["status"] == "ok"
    # 2) bloqueo REAL → procede (no estaba consumido)
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(negativos_apply, "_client", lambda: object())
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: {"status": "success", "match_type": "EXACT"})
    real = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert real["status"] == "ok" and real["dry_run"] is False
    # 3) segundo bloqueo REAL → rechazado
    seg = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert seg["status"] == "rechazada" and seg["motivo"] == "ya_bloqueado"


def test_termino_bloqueado_real_muestra_estado_no_boton(monkeypatch, tmp_path):
    # BUG 1b: un término ya bloqueado de verdad llega a la página como ESTADO, no botón.
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    acciones_log.registrar({"accion": "bloquear", "term": "bankok casa thai", "applied": True, "resultado": "ok"})
    ctx = negativos_service.contexto_bloqueo("bankok casa thai", payload=_payload())
    assert ctx["ya_bloqueado_ts"] is not None
    html = acciones_bloqueo.render_bloqueo(ctx, "TOK")
    assert "Ya bloqueado el" in html and "disabled" in html


def test_cosmetico_variante_singular_plural():
    assert acciones_bloqueo._variantes(1) == "1 variante"
    assert acciones_bloqueo._variantes(2) == "2 variantes"
    assert acciones_bloqueo._variantes(0) == "0 variantes"
