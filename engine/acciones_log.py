"""Log inmutable (append-only JSONL) de acciones de reseñas — Fase G.

Cada publicación (real o dry-run) deja un registro. Sirve también para evitar publicar dos
veces la misma reseña.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "acciones_log.jsonl")


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def registrar(entry: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    """Agrega una línea JSON al log (append-only). Nunca reescribe ni borra."""
    path = path or LOG_PATH
    record = {"ts": _ahora_iso(), **entry}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _leer(path: str | None = None) -> list[dict[str, Any]]:
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                try:
                    out.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    return out


def ya_registrada(review_id: str, path: str | None = None) -> bool:
    """True si ya hubo una publicación aceptada (real o dry-run) para esa reseña —
    evita publicar/registrar dos veces la misma."""
    return any(
        r.get("review_id") == review_id and r.get("accion") == "publicar"
        and r.get("resultado") in ("ok", "dry_run")
        for r in _leer(path)
    )


def termino_ya_bloqueado(term: str, path: str | None = None) -> bool:
    """True si ya hubo un bloqueo aceptado (real o dry-run) para ese término —
    evita bloquear dos veces el mismo."""
    return any(
        r.get("term") == term and r.get("accion") == "bloquear"
        and r.get("resultado") in ("ok", "dry_run")
        for r in _leer(path)
    )
