"""Orquestación de la página de bloqueo de negativos — Fase B1.

Construye el contexto de un término (variantes, campañas, gasto, qué se aplicará), re-valida
server-side que el término sea una decisión real (jamás arbitrario), aplica (gated DRY_RUN),
registra en el log inmutable y manda correo. "Dejar" lo marca válido en el diccionario.
"""
from __future__ import annotations

import json
import os
from typing import Any

from engine import acciones_email, acciones_log, negativos_apply

_DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "term_dictionary.json")


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


def contexto_bloqueo(term: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Contexto para la UI: variantes agrupadas, campañas (con canal/gasto), qué se aplicará."""
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

    return {
        "term": term, "bloqueable": es_bloqueable(term, decisiones, dictionary),
        "variantes": variantes, "variantes_count": len(variantes),
        "gasto_total": round(sum(c["gasto"] for c in campanas), 2),
        "contiene_marca": marca, "campanas": campanas,
        "dry_run": negativos_apply.dry_run_negativos(),
    }


def confirmar_bloqueo(term: str, campaign_ids: list[str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirma el bloqueo de UN término en las campañas marcadas. Re-valida server-side."""
    ctx = contexto_bloqueo(term, payload)
    if not ctx["bloqueable"]:
        return {"status": "rechazada", "motivo": "termino_no_valido"}
    if acciones_log.termino_ya_bloqueado(term):
        return {"status": "rechazada", "motivo": "ya_bloqueado"}

    ids = set(str(i) for i in (campaign_ids or []))
    marcadas = []
    for c in ctx["campanas"]:
        if c["id"] not in ids:
            continue
        if not c["permitido"]:  # guarda server-side: Smart con marca jamás
            continue
        marcadas.append(c)
    if not marcadas:
        return {"status": "rechazada", "motivo": "sin_campanas_validas"}

    resultados = negativos_apply.aplicar_bloqueo(term, marcadas)
    dry = negativos_apply.dry_run_negativos()
    manuales = [r for r in resultados if r.get("status") == "manual_required"]
    entry = {
        "accion": "bloquear", "term": term, "variantes_count": ctx["variantes_count"],
        "campanas": [r["campaign"] for r in resultados],
        "match_types": [r["match_type"] for r in resultados],
        "dry_run": dry, "resultado": "dry_run" if dry else "ok",
        "pending_manual": [r["campaign"] for r in manuales], "detalle": resultados,
    }
    registrado = acciones_log.registrar(entry)

    nombres = ", ".join(r["campaign"] for r in resultados)
    asunto = f"🚫 Bloqueado '{term}' ({ctx['variantes_count']} variantes)"
    cuerpo = (f"Se {'simuló' if dry else 'aplicó'} el bloqueo de '{term}' "
              f"({ctx['variantes_count']} variantes) en [{nombres}], por tu instrucción de hoy.\n\n"
              f"Match types: {', '.join(entry['match_types'])}.\n")
    if manuales:
        cuerpo += ("\n⚠ PASO MANUAL en Smart (la API no permite negativos en Smart de forma confiable):\n")
        for r in manuales:
            cuerpo += (f"\n• Campaña «{r['campaign']}»:\n"
                       f"  Theme negativo a pegar: {term}\n"
                       f"  Ruta: Campaña → Palabras clave → Temas de palabras clave negativas → Agregar.\n")
    correo = acciones_email.enviar(asunto, cuerpo)
    return {"status": "ok", "dry_run": dry, "resultados": resultados,
            "pending_manual": entry["pending_manual"], "correo": correo, "registro": registrado}


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
