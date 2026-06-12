"""Caché en disco de borradores de reseñas por review_id — Fase G.

Recargar la página NO regenera: un borrador ya generado se sirve instantáneo. Se invalida
solo si cambia la voz (data/voz_resenas.md). En Cloud Run el disco es efímero (se pierde en
cold start), pero una instancia tibia reutiliza la caché — suficiente para no regenerar en
cada recarga.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

_BASE = os.path.dirname(os.path.dirname(__file__))
CACHE_PATH = os.path.join(_BASE, "data", "borradores_cache.json")
_VOZ_PATH = os.path.join(_BASE, "data", "voz_resenas.md")


# Bump para invalidar TODOS los borradores cacheados (p. ej. al cambiar la rotación del banco).
_CACHE_VERSION = "2"


def voz_hash(path: str | None = None) -> str:
    try:
        with open(path or _VOZ_PATH, "rb") as f:
            data = f.read()
    except OSError:
        data = b""
    return hashlib.sha256(_CACHE_VERSION.encode("utf-8") + data).hexdigest()[:16]


def _leer(path: str | None = None) -> dict[str, Any]:
    path = path or CACHE_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def get(review_id: str, path: str | None = None) -> dict[str, Any] | None:
    """Devuelve el item cacheado si existe y la voz no cambió; si no, None."""
    e = _leer(path).get(review_id)
    if e and e.get("voz_hash") == voz_hash():
        return e.get("item")
    return None


def set(review_id: str, item: dict[str, Any], path: str | None = None) -> None:
    path = path or CACHE_PATH
    data = _leer(path)
    data[review_id] = {"voz_hash": voz_hash(), "item": item}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
