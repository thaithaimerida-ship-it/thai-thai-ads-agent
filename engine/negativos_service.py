"""Orquestación de la página de bloqueo de negativos — Fase B1.

Construye el contexto de un término (variantes, campañas, gasto, qué se aplicará), re-valida
server-side que el término sea una decisión real (jamás arbitrario), aplica (gated DRY_RUN),
registra en el log inmutable y manda correo. "Dejar" lo marca válido en el diccionario.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from engine import acciones_email, acciones_log, ads_client, negative_matcher, negativos_apply

_DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "term_dictionary.json")

# Fuente de verdad del dedupe: los negativos REALES de Google Ads (no el log efímero, que se
# borra en cada deploy). Caché en memoria con TTL corto para no re-pegar a la API en cada carga.
_NEG_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}


def _negativos_cuenta(ttl: float = 120.0) -> dict[str, Any]:
    """Negativos a nivel campaña de la cuenta (read-only, cacheado). {} ante error de API
    (fail-open: si no podemos leer Ads, NO ocultamos candidatos en silencio)."""
    now = time.time()
    if _NEG_CACHE["data"] is not None and (now - _NEG_CACHE["ts"]) < ttl:
        return _NEG_CACHE["data"]
    try:
        data = ads_client.fetch_negative_keywords(ads_client.get_ads_client(), negativos_apply._CID)
    except Exception:
        return _NEG_CACHE["data"] or {}
    _NEG_CACHE["data"], _NEG_CACHE["ts"] = data, now
    return data


def _cobertura(term: str, campanas: list[dict[str, Any]], negs: dict[str, Any]) -> tuple[str | None, dict | None]:
    """Cobertura del término por negativos REALES en sus campañas SEARCH (conservador):
    'exact'  → existe un negativo EXACT idéntico (cero duda → ocultar);
    'amplio' → solo lo cubre un PHRASE/BROAD preexistente (mostrar con nota → Hugo decide);
    None     → no está cubierto. Devuelve (estado, negativo_que_cubre)."""
    tnorm = negative_matcher._normalize(term)
    amplio = None
    for c in campanas or []:
        if c.get("channel") != "SEARCH":
            continue
        for n in (negs.get(str(c.get("id"))) or {}).get("negatives", []):
            nnorm = negative_matcher._normalize(n.get("text", ""))
            mt = (n.get("match_type") or "").upper()
            if mt == "EXACT" and nnorm == tnorm:
                return "exact", n
            if negative_matcher._blocks(tnorm, nnorm, mt):
                amplio = n  # seguimos buscando por si hay un EXACT idéntico más adelante
    return ("amplio", amplio) if amplio else (None, None)


def _humaniza_ads_error(msg: str) -> str:
    m = (msg or "").lower()
    if "80 char" in m or "less than 80" in m:
        return "El término supera 80 caracteres y Google Ads lo rechaza."
    if "10 word" in m:
        return "El término supera 10 palabras y Google Ads lo rechaza."
    return (msg or "Google Ads no aplicó el negativo.").strip()[:160]


def _cargar_diccionario() -> dict[str, Any]:
    with open(_DICT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _group_key(term: str, dictionary: dict[str, Any]) -> str:
    from engine.monitor_digest_v3 import _decision_group_key
    return _decision_group_key(term, dictionary)


def _channel(campaign_name: str) -> str:
    """'SEARCH' o 'SMART' según el tipo de campaña."""
    from engine.monitor_sections import classify_campaign
    return "SMART" if classify_campaign(campaign_name or "")["tipo"] == "smart" else "SEARCH"


def _payload_busqueda(date_range: str = "LAST_7_DAYS") -> dict[str, Any]:
    from routes.analysis import _build_search_terms_payload
    return _build_search_terms_payload(date_range)


def _decisiones(payload: dict[str, Any]) -> list[dict[str, Any]]:
    from engine.monitor_digest_v3 import build_monitor_digest
    return build_monitor_digest(payload).get("decisions", []) or []


def es_bloqueable(term: str, decisiones: list[dict[str, Any]], dictionary: dict[str, Any]) -> bool:
    """El término es bloqueable SOLO si es una decisión del digest o un candidato del
    diccionario (competitor_roots). Jamás términos arbitrarios."""
    gk = _group_key(term, dictionary)
    if any(_group_key(d.get("term", ""), dictionary) == gk for d in decisiones):
        return True
    tnorm = negativos_apply._norm(term)
    return any(negativos_apply._norm(r) in tnorm for r in (dictionary.get("competitor_roots") or []))


def contexto_bloqueo(term: str, payload: dict[str, Any] | None = None,
                     negativos: dict[str, Any] | None = None) -> dict[str, Any]:
    """Contexto para la UI: variantes agrupadas, campañas (con canal/gasto), qué se aplicará.
    `negativos` (negativos reales de Ads) lo pasa la bandeja para un solo fetch; si es None se lee."""
    payload = payload or _payload_busqueda()
    dictionary = _cargar_diccionario()
    decisiones = _decisiones(payload)
    gk = _group_key(term, dictionary)

    rows = [r for r in (payload.get("search_terms") or []) if _group_key(r.get("query", ""), dictionary) == gk]
    variantes = sorted({r.get("query", "") for r in rows if r.get("query")})
    marca = negativos_apply.contiene_marca(term)

    por_camp: dict[str, dict[str, Any]] = {}
    for r in rows:
        nombre = r.get("campaign_name", "")
        c = por_camp.setdefault(nombre, {"name": nombre, "id": str(r.get("campaign_id") or ""),
                                         "channel": _channel(nombre), "gasto": 0.0})
        c["gasto"] += float(r.get("cost") or 0)

    campanas = []
    for c in por_camp.values():
        if c["channel"] == "SEARCH":
            campanas.append({**c, "match_type": "EXACT", "permitido": True, "premarcado": True, "nota": ""})
        else:  # SMART
            permitido = not marca
            campanas.append({**c, "match_type": "THEME", "permitido": permitido, "premarcado": False,
                             "manual": permitido,  # Smart permitido → se aplica a mano en Google Ads
                             "nota": ("Contiene marca/categoría: el theme de Smart podría bloquear "
                                      "búsquedas legítimas." if not permitido else
                                      "Este se aplica manualmente en Google Ads (te enviaré las instrucciones por correo).")})

    negs = negativos if negativos is not None else _negativos_cuenta()
    estado, neg_cubre = _cobertura(term, campanas, negs)
    motivo_invalido = negativos_apply.motivo_keyword_invalido(term)
    nota_cob = ""
    if estado == "amplio" and neg_cubre:
        nota_cob = (f"Ya cubierto por un negativo {neg_cubre.get('match_type')} existente "
                    f"(«{neg_cubre.get('text')}») — revisar.")

    return {
        "term": term, "bloqueable": es_bloqueable(term, decisiones, dictionary),
        "variantes": variantes, "variantes_count": len(variantes),
        "gasto_total": round(sum(c["gasto"] for c in campanas), 2),
        "contiene_marca": marca, "campanas": campanas,
        # Fuente de verdad = Ads real (no el log efímero):
        "ya_bloqueado": estado == "exact",        # EXACT idéntico ya en Ads → no reaparece
        "ya_bloqueado_ts": "en Google Ads" if estado == "exact" else None,  # compat
        "cobertura_amplia": estado == "amplio",   # solo PHRASE/BROAD → mostrar con nota
        "cobertura_nota": nota_cob,
        "aplicable": motivo_invalido is None,      # cumple reglas de keyword de Google (≤80/≤10)
        "motivo_no_aplicable": motivo_invalido or "",
        "dry_run": negativos_apply.dry_run_negativos(),
    }


def confirmar_bloqueo(term: str, campaign_ids: list[str], payload: dict[str, Any] | None = None,
                      enviar_correo: bool = True, negativos: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirma el bloqueo de UN término en las campañas marcadas. Re-valida server-side.
    El status refleja el `applied` REAL: si Google Ads no aplica, status='error' (no 'ok'),
    sin correo de éxito. `enviar_correo=False` lo usa el lote (un solo correo al final)."""
    dry = negativos_apply.dry_run_negativos()
    ctx = contexto_bloqueo(term, payload, negativos=negativos)
    if not ctx["bloqueable"]:
        return {"status": "rechazada", "motivo": "termino_no_valido", "term": term}
    if not ctx["aplicable"]:  # candado nuevo: keyword inválida (>80 chars / >10 palabras)
        return {"status": "error", "motivo": "keyword_invalido", "mensaje": ctx["motivo_no_aplicable"], "term": term}
    if ctx.get("ya_bloqueado"):  # EXACT idéntico ya en Ads (fuente de verdad, no el log)
        return {"status": "rechazada", "motivo": "ya_bloqueado", "term": term}

    ids = set(str(i) for i in (campaign_ids or []))
    marcadas = []
    for c in ctx["campanas"]:
        if c["id"] not in ids:
            continue
        if not c["permitido"]:  # guarda server-side: Smart con marca jamás
            continue
        marcadas.append(c)
    if not marcadas:
        return {"status": "rechazada", "motivo": "sin_campanas_validas", "term": term}

    resultados = negativos_apply.aplicar_bloqueo(term, marcadas)
    manuales = [r for r in resultados if r.get("status") == "manual_required"]
    aplicadas = [r for r in resultados if r.get("applied")]
    fallidas = [r for r in resultados if not r.get("applied") and r.get("status") != "manual_required"]
    applied = bool(aplicadas)
    # Éxito REAL: dry-run (ensayo), o algún negativo aplicado, o solo manuales (Smart pendiente).
    if dry:
        exito, motivo_fallo = True, ""
    elif fallidas and not aplicadas:
        det = fallidas[0].get("detalle") or {}
        exito, motivo_fallo = False, _humaniza_ads_error(det.get("message") or fallidas[0].get("message") or "")
    else:
        exito, motivo_fallo = True, ""

    entry = {
        "accion": "bloquear", "term": term, "variantes_count": ctx["variantes_count"],
        "campanas": [r["campaign"] for r in resultados],
        "match_types": [r["match_type"] for r in resultados],
        "dry_run": dry, "applied": applied, "resultado": "dry_run" if dry else ("ok" if exito else "error"),
        "pending_manual": [r["campaign"] for r in manuales], "detalle": resultados,
    }
    registrado = acciones_log.registrar(entry)  # auditoría (refleja applied real)

    base = {"dry_run": dry, "resultados": resultados, "term": term,
            "campanas": entry["campanas"], "match_types": entry["match_types"],
            "pending_manual": entry["pending_manual"], "registro": registrado}
    if not exito:  # NO se aplicó → status error, sin correo de éxito
        return {**base, "status": "error", "motivo": "no_aplicado",
                "mensaje": motivo_fallo or "Google Ads no aplicó el negativo."}

    nombres = ", ".join(r["campaign"] for r in resultados)
    n = ctx["variantes_count"]
    var_txt = f"{n} variante" if n == 1 else f"{n} variantes"
    asunto = f"🚫 Bloqueado '{term}' ({var_txt})"
    cuerpo = (f"Se {'simuló' if dry else 'aplicó'} el bloqueo de '{term}' "
              f"({var_txt}) en [{nombres}], por tu instrucción de hoy.\n\n"
              f"Match types: {', '.join(entry['match_types'])}.\n")
    if manuales:
        cuerpo += ("\n⚠ PASO MANUAL en Smart (la API no permite negativos en Smart de forma confiable):\n")
        for r in manuales:
            cuerpo += (f"\n• Campaña «{r['campaign']}»:\n"
                       f"  Theme negativo a pegar: {term}\n"
                       f"  Ruta: Campaña → Palabras clave → Temas de palabras clave negativas → Agregar.\n")
    correo = acciones_email.enviar(asunto, cuerpo) if enviar_correo else {"enviado": False, "motivo": "lote"}
    return {**base, "status": "ok", "correo": correo}


def contextos_bandeja(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bandeja: contexto de TODOS los términos candidatos a bloqueo (decisiones del digest),
    construidos de UN solo fetch de search terms. Cada uno como en la página individual."""
    payload = payload or _payload_busqueda()
    dictionary = _cargar_diccionario()
    decisiones = _decisiones(payload)
    negs = _negativos_cuenta()  # negativos REALES de Ads (un solo fetch para toda la bandeja)
    items, vistos = [], set()
    for d in decisiones:
        term = d.get("term")
        if not term:
            continue
        gk = _group_key(term, dictionary)
        if gk in vistos:
            continue
        vistos.add(gk)
        ctx = contexto_bloqueo(term, payload, negativos=negs)
        if not ctx.get("bloqueable"):
            continue
        if ctx.get("ya_bloqueado"):  # EXACT idéntico ya en Ads → JAMÁS reaparece (sin importar deploys)
            continue
        items.append(ctx)
    items.sort(key=lambda c: c.get("gasto_total", 0), reverse=True)
    return {"total": len(items), "dry_run": negativos_apply.dry_run_negativos(), "items": items}


def confirmar_lote(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Bloquea una SELECCIÓN, UNO POR UNO (mismo confirmar_bloqueo: re-validación + log por
    término). Tope 10. Fallo parcial no detiene. UN solo correo con el resumen."""
    items = (items or [])[:10]
    payload = _payload_busqueda()  # un fetch de search terms para todo el lote
    negs = _negativos_cuenta()     # un fetch de negativos reales para todo el lote
    resultados = []
    for it in items:
        term = it.get("term", "")
        ids = it.get("campaign_ids") or []
        res = confirmar_bloqueo(term, ids, payload=payload, enviar_correo=False, negativos=negs)
        resultados.append({
            "term": term, "status": res.get("status"), "motivo": res.get("motivo", ""),
            "mensaje": res.get("mensaje", ""),
            "campanas": res.get("campanas", []), "match_types": res.get("match_types", []),
            "pending_manual": res.get("pending_manual", []),
        })

    ok = [r for r in resultados if r["status"] == "ok"]        # aplicados de verdad (o dry-run)
    fail = [r for r in resultados if r["status"] != "ok"]      # rechazados / no aplicados
    dry = negativos_apply.dry_run_negativos()
    verbo = "simulados" if dry else "bloqueados"
    asunto = f"🚫 {len(ok)} {verbo}" + (f" · {len(fail)} no se pudieron" if fail else "")
    lineas = [f"{len(ok)} {verbo} · {len(fail)} no se pudieron." if fail else f"{len(ok)} {verbo}.", ""]
    for r in ok:
        lineas.append(f"✓ '{r['term']}' → {', '.join(r['campanas'])} ({', '.join(r['match_types'])})")
    if fail:
        lineas += ["", "No se pudieron:"]
        for r in fail:
            lineas.append(f"✗ '{r['term']}': {r.get('mensaje') or r['motivo']}")
    correo = acciones_email.enviar(asunto, "\n".join(lineas))
    return {"bloqueados": len(ok), "fallidos": len(fail), "dry_run": dry,
            "resultados": resultados, "correo": correo}


def dejar(term: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Marca el término como búsqueda válida en el diccionario (no se vuelve a preguntar).
    NO toca Google Ads."""
    dictionary = _cargar_diccionario()
    tnorm = negativos_apply._norm(term).strip()
    lista = dictionary.setdefault("acknowledged_external_roots", [])
    agregado = False
    if tnorm and tnorm not in [negativos_apply._norm(x) for x in lista]:
        lista.append(term.strip())
        agregado = True
        with open(_DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(dictionary, f, ensure_ascii=False, indent=2)
    acciones_log.registrar({"accion": "dejar", "term": term, "resultado": "ok", "agregado": agregado})
    return {"status": "ok", "agregado": agregado, "toca_ads": False}
