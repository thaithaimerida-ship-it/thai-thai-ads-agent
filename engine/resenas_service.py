"""Orquestación del módulo de reseñas 5★ — Fase G.

Une GBP (lectura/publicación) + generador de borradores + log + correo. La UI consume
`cargar_borradores_tanda`; el POST de publicación usa `publicar` (una reseña por llamada,
re-validación server-side, log inmutable, correo de confirmación).
"""
from __future__ import annotations

from typing import Any

from engine import acciones_email, acciones_log, borradores_cache, gbp_reviews, resenas_ai, resenas_email


def cargar_resenas_tanda(offset: int = 0, limit: int = 10) -> dict[str, Any]:
    """SOLO el contenido de las reseñas (estrellas, autor, texto) — RÁPIDO, sin IA. Lee la
    FUENTE ÚNICA en vivo (fetch_reviews_full): escaneo completo al abrir → refleja las ya
    contestadas y NO oculta pendientes 2025+ dispersas. `scan_completo` avisa si el escaneo
    quedó a medias (la bandeja muestra un aviso y no presenta la lista corta como completa)."""
    full = gbp_reviews.fetch_reviews_full()
    pendientes = full["pendientes"]
    tanda = pendientes[offset:offset + limit]
    return {
        "total": len(pendientes), "offset": offset, "limit": limit,
        "hay_mas": offset + limit < len(pendientes), "dry_run": gbp_reviews.dry_run_activo(),
        "scan_completo": full["completo"],
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
        # Generación IA per-card: aquí SÍ usamos caché (su propósito real) para no re-paginar
        # GBP en cada tarjeta. La corrección de "ya contestada" vive en la LISTA (en vivo) +
        # en el candado de publicación (es_publicable en vivo). La tarjeta solo se pide para
        # reseñas que la lista en vivo ya mostró como pendientes.
        reviews = gbp_reviews.fetch_reviews_cached()
        pendientes = gbp_reviews.pendientes_5_estrellas(reviews)
        idx = next((i for i, r in enumerate(pendientes) if r["review_id"] == review_id), None)
        if idx is None:
            return {"review_id": review_id, "error": "Reseña no encontrada o ya respondida."}
        resena = pendientes[idx]
        if resenas_ai.sin_texto(resena):
            # Banco verbatim ROTADO por hash(review_id), evitando las últimas 10 publicaciones REALES.
            recientes = acciones_log.textos_publicados_reales(10)
            sel = resenas_ai.seleccionar_banco_por_review(resenas_ai.cargar_banco_sin_texto(), review_id, recientes)
            item = {"energia": "agradecimiento", "borrador": sel, "cuerpo": "", "cierre": "",
                    "grupo_cierre": "", "emoji_apertura": resenas_ai.apertura_emoji(sel),
                    "fuente": "banco", "revisar_manual": False, "motivo_revision": ""}
        else:
            publicadas = gbp_reviews.respuestas_publicadas(reviews, 6)
            item = resenas_ai.generar_uno(resena, indice=idx, respuestas_previas=publicadas,
                                          cierres_recientes=publicadas, banco_recientes=publicadas)
        borradores_cache.set(review_id, item)
        return {**item, "review_id": review_id, "cache": False}
    except Exception as exc:  # nunca 500 → el front muestra el error
        return {"review_id": review_id, "error": f"No se pudo generar: {exc}"}


def cargar_borradores_tanda(offset: int = 0, limit: int = 10) -> dict[str, Any]:
    """Trae las pendientes 5★, toma la tanda [offset:offset+limit] y genera sus borradores.
    Las CON texto → generador + cierre del pool; las SIN texto → banco verbatim.
    FUENTE ÚNICA en vivo (fetch_reviews_full) para no ofrecer borrador de reseñas ya contestadas."""
    full = gbp_reviews.fetch_reviews_full()
    pendientes = full["pendientes"]
    publicadas = gbp_reviews.respuestas_publicadas(full["reviews"], 15)
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
        "dry_run": gbp_reviews.dry_run_activo(), "scan_completo": full["completo"], "items": items,
    }


def publicar(review_id: str, texto: str, reviewer: str = "", comment: str = "",
             energia: str = "", fuente: str = "generado", enviar_correo: bool = True) -> dict[str, Any]:
    """Publica UNA respuesta. Re-valida server-side (5★ + sin respuesta previa + no repetida),
    publica (gated por DRY_RUN), registra en el log inmutable y manda correo de confirmación.
    `enviar_correo=False` lo usa el lote (un solo correo al final, no uno por reseña)."""
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
    correo = resenas_email.enviar_confirmacion(registrado) if enviar_correo else {"enviado": False, "motivo": "lote"}
    return {"status": "ok", "dry_run": res["dry_run"], "correo": correo, "registro": registrado}


def publicar_lote(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Publica una SELECCIÓN, UNA POR UNA (mismos candados que `publicar`: re-validación 5★ +
    sin respuesta + log por reseña). Tope 10. Si una falla, las demás continúan. UN solo correo
    de confirmación al final con el resumen."""
    items = (items or [])[:10]  # tope: máximo 10 por lote
    resultados = []
    for it in items:
        rid = it.get("review_id", "")
        texto = it.get("texto", "")
        res = publicar(rid, texto, enviar_correo=False)  # sin correo individual; el lote manda uno
        reg = res.get("registro") or {}
        resultados.append({
            "review_id": rid, "status": res.get("status"), "motivo": res.get("motivo", ""),
            "reviewer": reg.get("reviewer", ""), "texto": texto,
        })

    ok = [r for r in resultados if r["status"] == "ok"]
    fail = [r for r in resultados if r["status"] != "ok"]
    dry = gbp_reviews.dry_run_activo()
    verbo = "simuladas" if dry else "publicadas"
    asunto = f"🍜 {len(ok)} respuesta{'s' if len(ok) != 1 else ''} {verbo}"
    if fail:
        asunto += f" · {len(fail)} falló" if len(fail) == 1 else f" · {len(fail)} fallaron"
    lineas = [f"{len(ok)} respuesta(s) {verbo}" + (f", {len(fail)} fallaron." if fail else ".") , ""]
    for r in ok:
        lineas.append(f"✓ {r['reviewer'] or r['review_id']}: {r['texto']}")
    if fail:
        lineas += ["", "Fallaron:"]
        for r in fail:
            lineas.append(f"✗ {r['reviewer'] or r['review_id']}: {r['motivo']}")
    correo = acciones_email.enviar(asunto, "\n".join(lineas))
    return {"publicadas": len(ok), "fallidas": len(fail), "dry_run": dry,
            "resultados": resultados, "correo": correo}
