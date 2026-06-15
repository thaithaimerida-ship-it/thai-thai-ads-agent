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


def _negs(cid, text, match_type="EXACT", name="Thai Merida - Delivery Search"):
    """Shape de fetch_negative_keywords: {campaign_id: {campaign_name, channel_type, negatives:[...]}}"""
    return {cid: {"campaign_name": name, "channel_type": "SEARCH",
                  "negatives": [{"text": text, "match_type": match_type, "resource_name": "x"}]}}


@pytest.fixture(autouse=True)
def _sin_lectura_ads(monkeypatch):
    """Por defecto los tests NO leen negativos de Ads (fail-open: cuenta sin negativos).
    Los tests de dedupe (B) sobreescriben _negativos_cuenta con datos controlados."""
    monkeypatch.setattr(negativos_service, "_negativos_cuenta", lambda *a, **k: {})


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


def test_lote_endpoint_desglose_por_termino(client, monkeypatch):
    # El JS necesita por término {term, ok, dry_run, mensaje} para actualizar cada tarjeta.
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_lote",
                        lambda items: {"bloqueados": 2, "fallidos": 0, "dry_run": True, "correo": {"enviado": True},
                                       "resultados": [{"term": "a", "status": "ok", "motivo": ""},
                                                      {"term": "b", "status": "ok", "motivo": ""}]})
    j = client.post("/acciones/bloqueos/lote?token=secreto",
                    json={"items": [{"term": "a"}, {"term": "b"}]}).json()
    assert j["ok"] is True and len(j["resultados"]) == 2
    for res in j["resultados"]:
        assert res["ok"] is True and res["dry_run"] is True and "Simulado (dry-run)" in res["mensaje"]
    # un fallo en el lote → ese término trae ok False + mensaje humano (sin romper el resto)
    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_lote",
                        lambda items: {"bloqueados": 1, "fallidos": 1, "dry_run": True, "correo": {"enviado": True},
                                       "resultados": [{"term": "a", "status": "ok", "motivo": ""},
                                                      {"term": "b", "status": "rechazada", "motivo": "ya_bloqueado"}]})
    j2 = client.post("/acciones/bloqueos/lote?token=secreto",
                     json={"items": [{"term": "a"}, {"term": "b"}]}).json()
    fb = [x for x in j2["resultados"] if x["term"] == "b"][0]
    assert fb["ok"] is False and "Ya estaba bloqueado" in fb["mensaje"]


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


def test_dry_run_repetible_y_dedupe_por_ads(monkeypatch, tmp_path):
    # Simulacros repetibles; bloqueo REAL aplica; el dedupe ahora es por ADS (no el log efímero).
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    p = _payload()
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "true")
    assert negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)["status"] == "ok"
    assert negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)["status"] == "ok"
    # bloqueo REAL → aplica (Ads aún sin el negativo, por el fixture autouse)
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(negativos_apply, "_client", lambda: object())
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: {"status": "success", "match_type": "EXACT"})
    real = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert real["status"] == "ok" and real["dry_run"] is False
    # ahora Ads YA tiene el negativo EXACT → segundo intento rechazado por la fuente de verdad
    monkeypatch.setattr(negativos_service, "_negativos_cuenta", lambda *a, **k: _negs("111", "bankok casa thai"))
    seg = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=p)
    assert seg["status"] == "rechazada" and seg["motivo"] == "ya_bloqueado"


def test_termino_ya_en_ads_exact_muestra_estado_no_boton(monkeypatch):
    # B: un término ya bloqueado EXACT en Ads → la página individual lo muestra como ESTADO, sin botón.
    monkeypatch.setattr(negativos_service, "_negativos_cuenta", lambda *a, **k: _negs("111", "bankok casa thai"))
    ctx = negativos_service.contexto_bloqueo("bankok casa thai", payload=_payload())
    assert ctx["ya_bloqueado"] is True
    html = acciones_bloqueo.render_bloqueo(ctx, "TOK")
    assert "Ya bloqueado en Google Ads" in html and "disabled" in html


# ── BUG A: nunca éxito falso ──────────────────────────────────────────────────
def test_keyword_muy_larga_no_aplicable_valida_antes_de_api(monkeypatch, tmp_path):
    # >80 chars → status error keyword_invalido ANTES de pegar a la API (caso plaza luxury).
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(negativos_service, "es_bloqueable", lambda *a, **k: True)
    largo = ("plaza luxury local 11 av andres garcia lavin 349 lunes a domingo 12 00 pm 10 30 "
             "cocina cierra oriental city merida")
    p = {"status": "success", "date_range": "LAST_7_DAYS",
         "search_terms": [_row(largo, "Thai Merida - Delivery Search", "111")]}
    called = {"add": 0}
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: called.__setitem__("add", called["add"] + 1) or {"status": "success"})
    res = negativos_service.confirmar_bloqueo(largo, ["111"], payload=p)
    assert res["status"] == "error" and res["motivo"] == "keyword_invalido"
    assert "80 caracteres" in res["mensaje"]
    assert called["add"] == 0  # se validó ANTES de llamar a Google Ads


def test_apply_falla_no_da_falso_exito(monkeypatch, tmp_path):
    # Si Google Ads rechaza en la mutación → status error (no 'ok'), sin correo de éxito.
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(negativos_apply, "_client", lambda: object())
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword",
                        lambda *a, **k: {"status": "error", "message": "Keyword text should be less than 80 chars."})
    correos = {"n": 0}
    monkeypatch.setattr(negativos_service.acciones_email, "enviar",
                        lambda *a, **k: correos.__setitem__("n", correos["n"] + 1) or {"enviado": True})
    res = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=_payload())
    assert res["status"] == "error" and res["motivo"] == "no_aplicado"
    assert "80 caracteres" in res["mensaje"]
    assert correos["n"] == 0  # NO se manda correo de éxito en un fallo


def test_lote_distingue_bloqueados_de_fallidos_en_correo(monkeypatch):
    # El lote cuenta el applied REAL y el correo dice "N bloqueados · M no se pudieron".
    def fake_confirmar(term, ids, payload=None, enviar_correo=False, negativos=None):
        if "plaza luxury" in term:
            return {"status": "error", "motivo": "keyword_invalido",
                    "mensaje": "El término supera 80 caracteres y Google Ads lo rechaza.", "term": term}
        return {"status": "ok", "dry_run": False, "campanas": ["Thai Merida - Delivery Search"],
                "match_types": ["EXACT"], "term": term}
    monkeypatch.setattr(negativos_service, "confirmar_bloqueo", fake_confirmar)
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: {})
    monkeypatch.setattr(negativos_apply, "dry_run_negativos", lambda: False)
    cap = {}
    monkeypatch.setattr(negativos_service.acciones_email, "enviar",
                        lambda asunto, cuerpo: cap.update(asunto=asunto, cuerpo=cuerpo) or {"enviado": True})
    terms = ["win chang caucel", "los habaneros merida", "restaurante siqueff", "restaurante trompos merida",
             "plaza luxury local 11 ..."]
    res = negativos_service.confirmar_lote([{"term": t, "campaign_ids": ["111"]} for t in terms])
    assert res["bloqueados"] == 4 and res["fallidos"] == 1
    assert "4 bloqueados · 1 no se pudieron" in cap["asunto"]
    assert "plaza luxury" in cap["cuerpo"] and "80 caracteres" in cap["cuerpo"]


# ── BUG B: dedupe por Ads (fuente de verdad) ──────────────────────────────────
def test_contextos_bandeja_excluye_exact_en_ads(monkeypatch):
    # Un EXACT idéntico en Ads → NO se ofrece como candidato (jamás reaparece, sin importar deploys).
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    monkeypatch.setattr(negativos_service, "_decisiones", lambda payload: [{"term": "bankok casa thai"}])
    monkeypatch.setattr(negativos_service, "_negativos_cuenta", lambda *a, **k: _negs("111", "bankok casa thai"))
    data = negativos_service.contextos_bandeja()
    assert "bankok casa thai" not in [i["term"] for i in data["items"]]


def test_contextos_bandeja_broad_se_muestra_con_nota(monkeypatch):
    # Cubierto solo por un BROAD preexistente → se MUESTRA con nota (no se oculta; Hugo decide).
    monkeypatch.setattr(negativos_service, "_payload_busqueda", lambda *a, **k: _payload())
    monkeypatch.setattr(negativos_service, "_decisiones", lambda payload: [{"term": "bankok casa thai"}])
    monkeypatch.setattr(negativos_service, "_negativos_cuenta",
                        lambda *a, **k: _negs("111", "casa thai", match_type="BROAD"))
    data = negativos_service.contextos_bandeja()
    item = next(i for i in data["items"] if i["term"] == "bankok casa thai")
    assert item["ya_bloqueado"] is False          # NO se oculta
    assert item["cobertura_amplia"] is True and "BROAD" in item["cobertura_nota"]


def test_cosmetico_variante_singular_plural():
    assert acciones_bloqueo._variantes(1) == "1 variante"
    assert acciones_bloqueo._variantes(2) == "2 variantes"
    assert acciones_bloqueo._variantes(0) == "0 variantes"


def test_bloqueo_real_usa_get_ads_client_no_yaml(monkeypatch, tmp_path):
    # Modo REAL (DRY_RUN=false): la escritura construye el cliente con ads_client.get_ads_client()
    # (env vars), JAMÁS load_from_storage("google-ads.yaml") — ese archivo no existe en Cloud Run.
    monkeypatch.setenv("DRY_RUN_NEGATIVOS", "false")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(negativos_service.acciones_email, "enviar", lambda *a, **k: {"enviado": False})
    calls = {"get_client": 0, "add": None}

    def _fake_client():
        calls["get_client"] += 1
        return object()

    def _fake_add(client, customer_id, campaign_id, keyword_text, match_type="BROAD"):
        calls["add"] = (keyword_text, match_type, campaign_id)
        return {"status": "success"}

    monkeypatch.setattr(negativos_apply.ads_client, "get_ads_client", _fake_client)
    monkeypatch.setattr(negativos_apply.ads_client, "add_negative_keyword", _fake_add)
    res = negativos_service.confirmar_bloqueo("bankok casa thai", ["111"], payload=_payload())
    assert res["status"] == "ok"
    assert any(r.get("applied") for r in res["resultados"])   # aplicado de verdad en Ads
    assert calls["get_client"] >= 1                            # cliente vía env vars (no yaml)
    assert calls["add"][1] == "EXACT"                          # jamás BROAD


def test_confirmar_500_devuelve_json_con_mensaje(client, monkeypatch):
    # Si la escritura revienta, el endpoint devuelve JSON {ok:false, mensaje} (nunca 500 sin body).
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")

    def _boom(term, ids):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'google-ads.yaml'")

    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_bloqueo", _boom)
    r = client.post("/acciones/bloqueo/confirmar?token=secreto", json={"term": "x", "campaign_ids": ["111"]})
    assert r.status_code == 500
    j = r.json()
    assert j["ok"] is False and "Error del servidor" in j["mensaje"]


def test_lote_500_devuelve_json_con_mensaje(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")

    def _boom(items):
        raise RuntimeError("falla interna")

    monkeypatch.setattr(acciones_bloqueo.negativos_service, "confirmar_lote", _boom)
    r = client.post("/acciones/bloqueos/lote?token=secreto", json={"items": [{"term": "x"}]})
    assert r.status_code == 500
    j = r.json()
    assert j["ok"] is False and "Error del servidor" in j["mensaje"] and j["resultados"] == []
