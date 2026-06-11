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
