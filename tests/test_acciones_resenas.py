"""Tests de los endpoints de acciones de reseñas — Fase G (sin red, sin LLM).

Los 8 del plan: solo 5★ listadas, ≤4★ no publicable, una por request, sin token → 403,
dry-run no llama a la API, no publicar dos veces.
"""
import time

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


def _full(reviews, completo=True):
    """Simula la salida de la FUENTE ÚNICA fetch_reviews_full."""
    return {"reviews": reviews, "pendientes": gbp_reviews.pendientes_5_estrellas(reviews),
            "average_rating": 4.7, "total_reviews": 100,
            "distribucion": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}, "completo": completo}


def test_lista_lee_en_vivo_no_cache(monkeypatch):
    """REGRESIÓN del bug de reseñas ya contestadas: la LISTA sale de la FUENTE ÚNICA en vivo
    (fetch_reviews_full), NO de la caché. Una reseña contestada no aparece aunque la caché la muestre."""
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_full",
                        lambda *a, **k: _full([_raw("r1"), _raw("r2", reply=True)]))
    # La caché (para generación) mostraría r2 pendiente — NO se usa para la LISTA:
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_cached", lambda *a, **k: [_raw("r1"), _raw("r2", reply=False)])
    out = resenas_service.cargar_resenas_tanda()
    ids = {it["review_id"] for it in out["items"]}
    assert "r1" in ids and "r2" not in ids
    assert out["total"] == 1 and out["scan_completo"] is True


def test_bandeja_avisa_si_escaneo_incompleto(client, monkeypatch):
    """Fallo del escaneo completo: la bandeja NUNCA presenta la lista corta como completa —
    muestra un aviso visible arriba."""
    monkeypatch.setenv("ACCIONES_TOKEN", "secreto")
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_full", lambda *a, **k: _full([_raw("r1")], completo=False))
    r = client.get("/acciones/resenas?token=secreto")
    assert r.status_code == 200
    assert "no se completó" in r.text and "recarga" in r.text.lower()


def test_pendientes_filtra_por_fecha_2025(monkeypatch):
    """Regla de negocio: solo 5★ sin reply con createTime >= 2025-01-01. Las viejas NO entran."""
    reviews = [_raw("nueva"),  # createTime 2026 → entra
               {"reviewId": "vieja", "starRating": "FIVE", "comment": "buena", "reviewer": {"displayName": "V"},
                "createTime": "2024-12-31T00:00:00Z"}]  # 2024 → NO entra
    pend = gbp_reviews.pendientes_5_estrellas(reviews)
    assert [p["review_id"] for p in pend] == ["nueva"]


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
    ct = "2026-06-01T00:00:00Z"
    reviews = [
        {"reviewId": "a", "starRating": "FIVE", "comment": "rico", "createTime": ct, "reviewer": {"displayName": "A"}},
        {"reviewId": "b", "starRating": "FOUR", "comment": "ok", "createTime": ct, "reviewer": {"displayName": "B"}},
        {"reviewId": "c", "starRating": "FIVE", "reviewReply": {"comment": "ya"}, "createTime": ct, "reviewer": {"displayName": "C"}},
        {"reviewId": "d", "starRating": "ONE", "comment": "malo", "createTime": ct, "reviewer": {"displayName": "D"}},
    ]
    pend = gbp_reviews.pendientes_5_estrellas(reviews)
    ids = [p["review_id"] for p in pend]
    assert ids == ["a"]  # solo 5★ sin respuesta, >=2025; ≤4★ jamás


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
    revs = [{"reviewId": "a", "starRating": "FIVE", "comment": "rico", "createTime": "2026-06-01T00:00:00Z", "reviewer": {"displayName": "Ana"}}]
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
    revs = [{"reviewId": "zzz-9", "starRating": "FIVE", "comment": "", "createTime": "2026-06-01T00:00:00Z", "reviewer": {"displayName": "A"}}]
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


# ── caché del escaneo completo (Opción 0+B: mata el doble escaneo, warmer, invalidación) ──
def _sembrar_cache(reviews):
    """Siembra _FULL_CACHE con un escaneo 'completo' fresco (como si fetch_reviews_full lo hubiera hecho)."""
    gbp_reviews._FULL_CACHE["data"] = {
        "reviews": reviews, "average_rating": 4.7, "total_reviews": len(reviews),
        "distribucion": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
        "pendientes": gbp_reviews.pendientes_5_estrellas(reviews), "completo": True}
    gbp_reviews._FULL_CACHE["ts"] = time.time()


def _fake_page(reviews):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"reviews": reviews, "averageRating": 4.7, "totalReviewCount": len(reviews)}
    return _R()


def test_full_cachea_un_solo_escaneo(monkeypatch):
    """Opción 0: la lista, el borrador per-card y una 2ª lectura comparten UN escaneo — no se
    pagina 1,205 dos veces por apertura (mata el doble escaneo)."""
    gbp_reviews.clear_reviews_cache()
    monkeypatch.setattr(gbp_reviews, "get_access_token", lambda: "t")
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _fake_page([_raw("a")])  # una sola página (sin nextPageToken)
    monkeypatch.setattr(gbp_reviews.requests, "get", fake_get)

    a = gbp_reviews.fetch_reviews_full()          # 1er escaneo (paga red)
    _ = gbp_reviews.fetch_reviews_full()          # caché
    revs = gbp_reviews.fetch_reviews_cached()     # borrador_para comparte el MISMO escaneo
    assert calls["n"] == 1                         # UN solo escaneo pese a 3 lecturas
    assert a["total_reviews"] == 1 and len(revs) == 1
    gbp_reviews.clear_reviews_cache()


def test_escaneo_incompleto_no_se_cachea(monkeypatch):
    """Un escaneo a medias (completo=False) NUNCA envenena la caché ni oculta pendientes."""
    gbp_reviews.clear_reviews_cache()
    monkeypatch.setattr(gbp_reviews, "get_access_token", lambda: "t")

    def boom(*a, **k):
        raise RuntimeError("red caída a mitad")
    monkeypatch.setattr(gbp_reviews.requests, "get", boom)

    out = gbp_reviews.fetch_reviews_full()
    assert out["completo"] is False
    assert gbp_reviews._FULL_CACHE["data"] is None  # no se guardó el parcial
    gbp_reviews.clear_reviews_cache()


def test_publicacion_real_invalida_cache(monkeypatch):
    """Bug #1 en versión caché: publicar REAL saca la reseña de la caché al instante (sin re-escanear)."""
    gbp_reviews.clear_reviews_cache()
    _sembrar_cache([_raw("r1"), _raw("r2")])
    assert {p["review_id"] for p in gbp_reviews._FULL_CACHE["data"]["pendientes"]} == {"r1", "r2"}

    monkeypatch.setenv("DRY_RUN_RESENAS", "false")           # publicación REAL
    monkeypatch.setattr(gbp_reviews, "get_access_token", lambda: "t")

    class _R:
        def raise_for_status(self):
            pass
    monkeypatch.setattr(gbp_reviews.requests, "put", lambda *a, **k: _R())

    res = gbp_reviews.publicar_respuesta("r1", "gracias", token="t")
    assert res["published"] is True
    pend = {p["review_id"] for p in gbp_reviews.fetch_reviews_full()["pendientes"]}
    assert pend == {"r2"}                                     # r1 desapareció al instante
    gbp_reviews.clear_reviews_cache()


def test_dry_run_no_invalida_cache(monkeypatch):
    """El simulacro (dry-run) NO consume ni saca la reseña de la caché — sigue pendiente (ensayo repetible)."""
    gbp_reviews.clear_reviews_cache()
    _sembrar_cache([_raw("r1")])
    monkeypatch.setenv("DRY_RUN_RESENAS", "true")
    res = gbp_reviews.publicar_respuesta("r1", "ensayo", token="t")
    assert res["dry_run"] is True
    assert {p["review_id"] for p in gbp_reviews._FULL_CACHE["data"]["pendientes"]} == {"r1"}
    gbp_reviews.clear_reviews_cache()


def test_warm_no_op_sin_credenciales(monkeypatch):
    """El warmer de /health NO toca la red si faltan credenciales GBP (seguro en tests/entornos sin secretos)."""
    monkeypatch.delenv("GBP_CLIENT_ID", raising=False)
    gbp_reviews.clear_reviews_cache()
    gbp_reviews.warm_reviews_cache()
    assert gbp_reviews._FULL_CACHE["data"] is None


def test_warm_puebla_cache_con_credenciales(monkeypatch):
    """Con credenciales presentes, el warmer puebla la caché (lo que hace /health cada ~5 min)."""
    gbp_reviews.clear_reviews_cache()
    monkeypatch.setenv("GBP_CLIENT_ID", "x")
    monkeypatch.setattr(gbp_reviews, "get_access_token", lambda: "t")
    monkeypatch.setattr(gbp_reviews.requests, "get", lambda *a, **k: _fake_page([_raw("a")]))
    gbp_reviews.warm_reviews_cache()
    assert gbp_reviews._FULL_CACHE["data"] is not None
    assert gbp_reviews._FULL_CACHE["data"]["total_reviews"] == 1
    gbp_reviews.clear_reviews_cache()


def test_dos_accesos_concurrentes_un_solo_escaneo(monkeypatch):
    """SINGLE-FLIGHT: si dos accesos piden el escaneo A LA VEZ (p.ej. /health recalentando y abrir
    la bandeja), UNO escanea y el otro ESPERA su resultado — nunca se pagina 1,205 dos veces por
    concurrencia. Regresión del doble escaneo reintroducido por carreras (no por el bug de código)."""
    import threading

    gbp_reviews.clear_reviews_cache()
    monkeypatch.setattr(gbp_reviews, "get_access_token", lambda: "t")
    calls = {"n": 0}
    en_vuelo = threading.Event()   # avisa que el 1er escaneo ya empezó (tiene el lock)
    soltar = threading.Event()     # mantiene ese escaneo "en vuelo" para forzar el solape

    def fake_get(*a, **k):
        calls["n"] += 1
        en_vuelo.set()
        soltar.wait(3)             # el 1er escaneo se queda dentro del lock hasta que lo soltemos
        return _fake_page([_raw("a")])
    monkeypatch.setattr(gbp_reviews.requests, "get", fake_get)

    resultados = []

    def acceso():
        resultados.append(gbp_reviews.fetch_reviews_full())

    t1 = threading.Thread(target=acceso)
    t2 = threading.Thread(target=acceso)
    t1.start()
    assert en_vuelo.wait(3)        # espera a que t1 tenga el lock y esté escaneando
    t2.start()                     # t2 llega mientras t1 escanea → debe BLOQUEARSE en el lock
    time.sleep(0.2)                # dale tiempo a t2 de chocar con el lock (no de re-escanear)
    soltar.set()                   # libera el escaneo de t1
    t1.join(5)
    t2.join(5)

    assert calls["n"] == 1                         # UN solo escaneo pese a 2 accesos simultáneos
    assert len(resultados) == 2
    assert all(r["total_reviews"] == 1 for r in resultados)  # ambos reciben el MISMO resultado
    gbp_reviews.clear_reviews_cache()
