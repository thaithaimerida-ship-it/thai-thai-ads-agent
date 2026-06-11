"""Orquestación del módulo de reseñas 5★ — Fase G.

Une GBP (lectura/publicación) + generador de borradores + log + correo. La UI consume
`cargar_borradores_tanda`; el POST de publicación usa `publicar` (una reseña por llamada,
re-validación server-side, log inmutable, correo de confirmación).
"""
from __future__ import annotations

from typing import Any

from engine import acciones_log, borradores_cache, gbp_reviews, resenas_ai, resenas_email


def cargar_resenas_tanda(offset: int = 0, limit: int = 10) -> dict[str, Any]:
    """SOLO el contenido de las reseñas (estrellas, autor, texto) — RÁPIDO, sin IA, con caché
    de reviews. La página lo usa para render server-side inmediato; los borradores llegan aparte."""
    reviews = gbp_reviews.fetch_reviews_cached()
    pendientes = gbp_reviews.pendientes_5_estrellas(reviews)
    tanda = pendientes[offset:offset + limit]
    return {
        "total": len(pendientes), "offset": offset, "limit": limit,
        "hay_mas": offset + limit < len(pendientes), "dry_run": gbp_reviews.dry_run_activo(),
        "items": [{"review_id": r["review_id"], "reviewer": r["reviewer"],
                   "stars": r["stars"], "comment": r["comment"]} for r in tanda],
    }


def borrador_para(review_id: str) -> dict[str, Any]:
    """Genera (o sirve de caché) el borrador de UNA reseña. Variedad por su posición en la
    lista de pendientes. Nunca lanza: ante error devuelve {error}."""
    try:
        cacheado = borradores_cache.get(review_id)
        if cacheado is not None:
            return {**cacheado, "review_id": review_id, "cache": True}
        reviews = gbp_reviews.fetch_reviews_cached()
        pendientes = gbp_reviews.pendientes_5_estrellas(reviews)
        idx = next((i for i, r in enumerate(pendientes) if r["review_id"] == review_id), None)
        if idx is None:
            return {"review_id": review_id, "error": "Reseña no encontrada o ya respondida."}
        publicadas = gbp_reviews.respuestas_publicadas(reviews, 6)
        item = resenas_ai.generar_uno(pendientes[idx], indice=idx, respuestas_previas=publicadas,
                                      cierres_recientes=publicadas, banco_recientes=publicadas)
        borradores_cache.set(review_id, item)
        return {**item, "review_id": review_id, "cache": False}
    except Exception as exc:  # nunca 500 → el front muestra el error
        return {"review_id": review_id, "error": f"No se pudo generar: {exc}"}


def cargar_borradores_tanda(offset: int = 0, limit: int = 10) -> dict[str, Any]:
    """Trae las pendientes 5★, toma la tanda [offset:offset+limit] y genera sus borradores.
    Las CON texto → generador + cierre del pool; las SIN texto → banco verbatim."""
    reviews = gbp_reviews.fetch_reviews_cached()
    pendientes = gbp_reviews.pendientes_5_estrellas(reviews)
    publicadas = gbp_reviews.respuestas_publicadas(reviews, 15)
    tanda = pendientes[offset:offset + limit]
    drafts = resenas_ai.generar_borradores(
        tanda, respuestas_previas=publicadas,
        cierres_recientes=publicadas, banco_recientes=publicadas,
    )
    items = []
    for r, d in zip(tanda, drafts):
        items.append({
            "review_id": r["review_id"], "reviewer": r["reviewer"], "stars": r["stars"],
            "comment": r["comment"], "energia": d["energia"], "grupo_cierre": d.get("grupo_cierre", ""),
            "borrador": d["borrador"], "revisar_manual": d.get("revisar_manual", False),
            "fuente": d.get("fuente", "generado"),
        })
    return {
        "total": len(pendientes), "offset": offset, "limit": limit,
        "hay_mas": offset + limit < len(pendientes),
        "dry_run": gbp_reviews.dry_run_activo(), "items": items,
    }


def publicar(review_id: str, texto: str, reviewer: str = "", comment: str = "",
             energia: str = "", fuente: str = "generado") -> dict[str, Any]:
    """Publica UNA respuesta. Re-valida server-side (5★ + sin respuesta previa + no repetida),
    publica (gated por DRY_RUN), registra en el log inmutable y manda correo de confirmación."""
    texto = (texto or "").strip()
    if not texto:
        return {"status": "rechazada", "motivo": "texto_vacio"}
    if acciones_log.ya_registrada(review_id):
        return {"status": "rechazada", "motivo": "ya_publicada"}

    review = gbp_reviews.get_review(review_id)
    if not gbp_reviews.es_publicable(review):
        return {"status": "rechazada", "motivo": "no_publicable"}  # no es 5★ o ya tiene respuesta

    # El correo de confirmación SIEMPRE lleva los datos reales de la reseña.
    norm = gbp_reviews.to_resena(review)
    reviewer = reviewer or norm.get("reviewer", "")
    comment = comment or norm.get("comment", "")

    res = gbp_reviews.publicar_respuesta(review_id, texto)
    entry = {
        "accion": "publicar", "review_id": review_id, "reviewer": reviewer, "comment": comment,
        "texto": texto, "energia": energia, "fuente": fuente,
        "dry_run": res["dry_run"], "published": res.get("published", False),
        "resultado": "dry_run" if res["dry_run"] else "ok",
    }
    registrado = acciones_log.registrar(entry)
    correo = resenas_email.enviar_confirmacion(registrado)
    return {"status": "ok", "dry_run": res["dry_run"], "correo": correo, "registro": registrado}
