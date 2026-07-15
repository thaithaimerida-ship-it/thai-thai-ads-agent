"""Tests de los endpoints de acciones de reseñas — Fase G (sin red, sin LLM).

Los 8 del plan: solo 5★ listadas, ≤4★ no publicable, una por request, sin token → 403,
dry-run no llama a la API, no publicar dos veces.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine import acciones_log, gbp_reviews, resenas_service
from routes import acciones_resenas


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(acciones_resenas.router)
    return TestClient(app)


def _raw(rid, reply=False):
    r = {"reviewId": rid, "starRating": "FIVE", "comment": "rico todo",
         "createTime": "2026-06-10T00:00:00Z", "reviewer": {"displayName": "Cliente " + rid}}
    if reply:
        r["reviewReply"] = {"comment": "¡gracias!", "updateTime": "2026-07-15T00:00:00Z"}
    return r


def test_lista_lee_en_vivo_no_cache(monkeypatch):
    """REGRESIÓN del bug de reseñas ya contestadas: la LISTA de pendientes se lee de
    fetch_reviews (EN VIVO), NO de fetch_reviews_cached. Una reseña contestada (excluida
    en vivo) NO debe aparecer aunque la caché stale la muestre como pendiente."""
    # EN VIVO: r1 pendiente, r2 YA contestada (tiene reviewReply)
    monkeypatch.setattr(gbp_reviews, "fetch_reviews", lambda *a, **k: [_raw("r1"), _raw("r2", reply=True)])
    # CACHÉ STALE: mostraría r2 como pendiente (sin reply) — NO debe usarse para la lista
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_cached", lambda *a, **k: [_raw("r1"), _raw("r2", reply=False)])

    out = resenas_service.cargar_resenas_tanda()
    ids = {it["review_id"] for it in out["items"]}
    assert "r1" in ids
    assert "r2" not in ids          # contestada en vivo → excluida (la caché stale la habría mostrado)
    assert out["total"] == 1
    # borrador_para SIGUE con caché (generación IA): ya cubierto por test_borrador_para_* (mockean
    # fetch_reviews_cached). El propósito de la caché — no re-paginar por tarjeta (OpenAI 431) — intacto.


# ── token ─────────────────────────────────────────────────────────────────────
def test_sin_token_403(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    assert client.get("/acciones/resenas").status_code == 403
    assert client.get("/acciones/resenas?token=malo").status_code == 403
    r = client.post("/acciones/resenas/publicar", json={"review_id": "r1", "texto": "hola"})
    assert r.status_code == 403


def test_token_no_seteado_falla_cerrado(client, monkeypatch):
    monkeypatch.delenv("ACCIONES_TOKEN", raising=False)
    assert client.get("/acciones/resenas?token=loquesea").status_code == 403


# ── solo 5★ ───────────────────────────────────────────────────────────────────
def test_solo_rating_5_listadas():
    reviews = [
        {"reviewId": "a", "starRating": "FIVE", "comment": "rico", "reviewer": {"displayName": "A"}},
        {"reviewId": "b", "starRating": "FOUR", "comment": "ok", "reviewer": {"displayName": "B"}},
        {"reviewId": "c", "starRating": "FIVE", "reviewReply": {"comment": "ya"}, "reviewer": {"displayName": "C"}},
        {"reviewId": "d", "starRating": "ONE", "comment": "malo", "reviewer": {"displayName": "D"}},
    ]
    pend = gbp_reviews.pendientes_5_estrellas(reviews)
    ids = [p["review_id"] for p in pend]
    assert ids == ["a"]  # solo 5★ sin respuesta; ≤4★ jamás


def test_pagina_renderiza_tarjetas_server_side(client, monkeypatch):
    # BUG 2: la página trae las tarjetas (contenido de reseñas) sin depender de JS.
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(resenas_service, "cargar_resenas_tanda", lambda offset=0, limit=10: {
        "total": 1, "offset": 0, "limit": 10, "hay_mas": False, "dry_run": True,
        "items": [{"review_id": "r1", "reviewer": "Ana López", "stars": 5, "comment": "La comida rica"}]})
    r = client.get("/acciones/resenas?token=secreto")
    assert r.status_code == 200
    assert "Ana López" in r.text and "La comida rica" in r.text  # contenido server-side
    assert "generando borrador" in r.text                        # placeholder, jamás vacío
    assert "DRY-RUN" in r.text


def test_data_con_token_lista_borradores(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(resenas_service, "cargar_borradores_tanda", lambda offset=0, limit=10: {
        "total": 1, "offset": 0, "limit": 10, "hay_mas": False, "dry_run": True,
        "items": [{"review_id": "a", "reviewer": "Ana", "stars": 5, "comment": "rico",
                   "energia": "explosiva", "grupo_cierre": "antojo", "borrador": "🔥 Gracias",
                   "revisar_manual": False, "fuente": "generado"}],
    })
    r = client.get("/acciones/resenas/data?token=secreto")
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["energia"] == "explosiva"
    assert body["dry_run"] is True


# ── publicación ───────────────────────────────────────────────────────────────
def _review(stars="FIVE", reply=None):
    r = {"reviewId": "r1", "name": "accounts/x/locations/y/reviews/r1", "starRating": stars}
    if reply:
        r["reviewReply"] = {"comment": reply}
    return r


def test_una_publicacion_por_request(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review())
    r = client.post("/acciones/resenas/publicar?token=secreto",
                    json={"review_id": "r1", "texto": "¡Gracias por tu visita!"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["dry_run"] is True


def test_rating_4_o_menos_no_publicable(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review(stars="FOUR"))
    res = resenas_service.publicar("r1", "texto")
    assert res["status"] == "rechazada" and res["motivo"] == "no_publicable"


def test_no_publicar_si_ya_tiene_respuesta(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review(reply="ya respondida"))
    res = resenas_service.publicar("r1", "texto")
    assert res["status"] == "rechazada" and res["motivo"] == "no_publicable"


def test_dry_run_no_llama_updatereply(monkeypatch):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    import requests
    monkeypatch.setattr(requests, "put", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no PUT en dry-run")))
    res = gbp_reviews.publicar_respuesta("r1", "hola", token="t")
    assert res["dry_run"] is True and res["published"] is False


def test_page_js_sin_escapes_colapsados(client, monkeypatch):
    # Regresión: _PAGE es raw string; \" NO debe colapsar (colapsado rompe TODO el script JS
    # y las tarjetas quedan en "generando…" eterno).
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(resenas_service, "cargar_resenas_tanda", lambda offset=0, limit=10: {
        "total": 0, "offset": 0, "limit": 10, "hay_mas": False, "dry_run": True, "items": []})
    html = client.get("/acciones/resenas?token=secreto").text
    assert 'pub("")' not in html and 'pub(""' not in html  # patrón colapsado/roto
    assert r'pub(\"' in html and r'retry(\"' in html        # escape correcto preservado


def test_borrador_endpoint_per_card(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(resenas_service, "borrador_para",
                        lambda rid: {"review_id": rid, "borrador": "🔥 Gracias", "energia": "explosiva", "cache": False})
    r = client.get("/acciones/resenas/borrador?token=secreto&review_id=a")
    assert r.status_code == 200 and r.json()["borrador"] == "🔥 Gracias"
    assert client.get("/acciones/resenas/borrador?review_id=a").status_code == 403  # sin token


def test_borrador_para_genera_y_cachea(monkeypatch, tmp_path):
    from engine import borradores_cache, resenas_ai
    monkeypatch.setattr(borradores_cache, "CACHE_PATH", str(tmp_path / "bc.json"))
    revs = [{"reviewId": "a", "starRating": "FIVE", "comment": "rico", "reviewer": {"displayName": "Ana"}}]
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_cached", lambda *a, **k: revs)
    calls = {"n": 0}

    def fake_uno(resena, indice=0, **k):
        calls["n"] += 1
        return {"energia": "explosiva", "borrador": "🔥 Gracias", "grupo_cierre": "antojo",
                "fuente": "generado", "revisar_manual": False, "emoji_apertura": "🔥",
                "cierre": "x", "cuerpo": "y", "motivo_revision": ""}

    monkeypatch.setattr(resenas_ai, "generar_uno", fake_uno)
    r1 = resenas_service.borrador_para("a")
    assert r1["borrador"] == "🔥 Gracias" and r1["cache"] is False
    r2 = resenas_service.borrador_para("a")
    assert r2["cache"] is True and calls["n"] == 1  # 2da vez: caché, no regenera


def test_borrador_para_error_no_lanza(monkeypatch, tmp_path):
    from engine import borradores_cache
    monkeypatch.setattr(borradores_cache, "CACHE_PATH", str(tmp_path / "bc.json"))
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_cached",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("GBP caído")))
    r = resenas_service.borrador_para("a")
    assert "error" in r and "GBP" in r["error"]  # nunca lanza → el front muestra el error


def test_borrador_para_sin_texto_usa_rotacion(monkeypatch, tmp_path):
    # BUG banco: reseña sin texto → respuesta del banco ROTADA por hash(review_id), no la primera.
    from engine import borradores_cache, resenas_ai
    monkeypatch.setattr(borradores_cache, "CACHE_PATH", str(tmp_path / "bc.json"))
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    revs = [{"reviewId": "zzz-9", "starRating": "FIVE", "comment": "", "reviewer": {"displayName": "A"}}]
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_cached", lambda *a, **k: revs)
    out = resenas_service.borrador_para("zzz-9")
    banco = resenas_ai.cargar_banco_sin_texto()
    assert out["fuente"] == "banco"
    assert out["borrador"] == resenas_ai.seleccionar_banco_por_review(banco, "zzz-9", [])


def test_textos_publicados_reales_solo_reales(tmp_path):
    p = str(tmp_path / "log.jsonl")
    acciones_log.registrar({"accion": "publicar", "review_id": "r1", "texto": "A", "published": True, "resultado": "ok"}, path=p)
    acciones_log.registrar({"accion": "publicar", "review_id": "r2", "texto": "B", "published": False, "resultado": "dry_run"}, path=p)
    acciones_log.registrar({"accion": "publicar", "review_id": "r3", "texto": "C", "published": True, "resultado": "ok"}, path=p)
    assert acciones_log.textos_publicados_reales(10, path=p) == ["C", "A"]  # solo reales, reciente primero


def test_lote_tope_10_y_un_solo_correo(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review())
    correos = {"n": 0}
    monkeypatch.setattr(resenas_service.acciones_email, "enviar",
                        lambda asunto, cuerpo: correos.__setitem__("n", correos["n"] + 1) or {"enviado": False})
    items = [{"review_id": f"r{i}", "texto": f"gracias {i}"} for i in range(12)]
    res = resenas_service.publicar_lote(items)
    assert len(res["resultados"]) == 10          # tope: máximo 10
    assert res["publicadas"] == 10
    assert correos["n"] == 1                      # UN solo correo por lote


def test_lote_fallo_parcial_no_detiene(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))

    def gr(rid, token=None):
        return _review(reply="ya respondida") if rid == "r-bad" else _review()
    monkeypatch.setattr(gbp_reviews, "get_review", gr)
    monkeypatch.setattr(resenas_service.acciones_email, "enviar", lambda a, c: {"enviado": False})
    res = resenas_service.publicar_lote([
        {"review_id": "r-ok", "texto": "a"}, {"review_id": "r-bad", "texto": "b"}, {"review_id": "r-ok2", "texto": "c"}])
    assert res["publicadas"] == 2 and res["fallidas"] == 1   # el fallo NO detuvo a los demás
    assert [r["motivo"] for r in res["resultados"] if r["status"] != "ok"] == ["no_publicable"]


def test_page_lote_excluye_flaggeadas_y_tope_10(client, monkeypatch):
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(resenas_service, "cargar_resenas_tanda", lambda offset=0, limit=10: {
        "total": 0, "offset": 0, "limit": 10, "hay_mas": False, "dry_run": False, "items": []})
    html = client.get("/acciones/resenas?token=secreto").text
    assert "Publicar seleccionadas" in html                 # botón del lote
    # Checkbox INMEDIATO: visible desde el render, sin esperar al borrador (P3).
    assert "style='display:block'><input type='checkbox' class='sel'" in html
    # Flaggeadas (borrador no natural) → se ocultan + desmarcan al llegar el borrador.
    assert "if(sr && d.revisar_manual)" in html
    assert "MAXSEL=10" in html                              # tope 10 en UI
    assert "/acciones/resenas/publicar-lote" in html        # endpoint del lote


def test_publicar_correo_lleva_datos_reales(monkeypatch, tmp_path):
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: {
        "reviewId": "r1", "starRating": "FIVE", "comment": "todo rico", "reviewer": {"displayName": "Ana López"}})
    cap = {}
    monkeypatch.setattr(resenas_service.resenas_email, "enviar_confirmacion",
                        lambda entry: cap.update(entry=entry) or {"enviado": False})
    res = resenas_service.publicar("r1", "gracias")
    assert res["status"] == "ok"
    assert cap["entry"]["reviewer"] == "Ana López" and cap["entry"]["comment"] == "todo rico"


def test_dry_run_no_consume_resena_pero_real_si(monkeypatch, tmp_path):
    # BUG 1: un simulacro (dry-run) NO consume la reseña; solo la publicación REAL la consume.
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review())
    # 1) dos simulacros (dry-run) → ambos proceden (ensayo repetible)
    monkeypatch.setattr(gbp_reviews, "publicar_respuesta",
                        lambda rid, txt, token=None: {"status": "dry_run", "dry_run": True, "published": False})
    assert resenas_service.publicar("r1", "ensayo 1")["status"] == "ok"
    assert resenas_service.publicar("r1", "ensayo 2")["status"] == "ok"
    # 2) acción REAL del mismo ítem → procede (no estaba consumido)
    monkeypatch.setattr(gbp_reviews, "publicar_respuesta",
                        lambda rid, txt, token=None: {"status": "ok", "dry_run": False, "published": True})
    assert resenas_service.publicar("r1", "real")["status"] == "ok"
    # 3) segunda acción REAL → rechazada
    seg = resenas_service.publicar("r1", "real otra vez")
    assert seg["status"] == "rechazada" and seg["motivo"] == "ya_publicada"
