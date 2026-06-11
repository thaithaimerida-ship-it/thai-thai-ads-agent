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


def test_no_publicar_dos_veces_misma_resena(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(gbp_reviews, "get_review", lambda rid, token=None: _review())
    primera = resenas_service.publicar("r1", "¡Gracias!")
    assert primera["status"] == "ok"
    segunda = resenas_service.publicar("r1", "¡Gracias otra vez!")
    assert segunda["status"] == "rechazada" and segunda["motivo"] == "ya_publicada"
