"""Aplicación de negativos confirmados — Fase B1.

EXACT en campañas de búsqueda (Delivery Search / Experiencia 2026); en Smart (Local / Delivery)
el negativo se gestiona como theme y SOLO si el término no contiene marca/categoría (la guarda
de marca evita bloquear búsquedas legítimas por el matching temático). JAMÁS BROAD, JAMÁS batch
(una llamada por campaña). Gated por DRY_RUN_NEGATIVOS (default true → no llama a Google Ads).
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from engine import ads_client

_CID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "4021070209")

# Marca / categoría: si el término las contiene, el theme de Smart podría bloquear búsquedas
# legítimas → se prohíbe el negativo en Smart.
_BRAND_RE = re.compile(r"\b(thai|tailand\w*|bangkok|thaithai)\b")


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def dry_run_negativos() -> bool:
    """DRY_RUN_NEGATIVOS=true por default → todo menos la llamada de escritura a Google Ads."""
    return os.getenv("DRY_RUN_NEGATIVOS", "true").strip().lower() != "false"


def contiene_marca(term: str) -> bool:
    return bool(_BRAND_RE.search(_norm(term)))


def _client():
    # MISMO constructor que la ruta de lectura: env vars (canónicas en Cloud Run) → yaml solo
    # local. Antes usaba load_from_storage("google-ads.yaml"), un archivo ausente en Cloud Run
    # (gitignored) → FileNotFoundError al ejercer la escritura real. Mismo OAuth scope para R/W.
    return ads_client.get_ads_client()


def aplicar_en_campana(term: str, campana: dict[str, Any]) -> dict[str, Any]:
    """Aplica el negativo a UNA campaña. SEARCH → EXACT; SMART → theme (con guarda de marca)."""
    channel = str(campana.get("channel") or "").upper()
    nombre = campana.get("name", "")

    if channel == "SEARCH":
        match_type = "EXACT"  # JAMÁS BROAD
        if dry_run_negativos():
            return {"campaign": nombre, "match_type": match_type, "status": "dry_run", "applied": False}
        res = ads_client.add_negative_keyword(_client(), _CID, str(campana.get("id")), term, match_type=match_type)
        return {"campaign": nombre, "match_type": match_type, "status": res.get("status"),
                "applied": res.get("status") == "success", "detalle": res}

    # SMART → theme, con guarda de marca/categoría
    if contiene_marca(term):
        return {"campaign": nombre, "match_type": "THEME", "status": "rejected",
                "reason": "marca_categoria_smart", "applied": False,
                "message": "El término contiene marca/categoría; el theme de Smart podría bloquear búsquedas legítimas."}
    if dry_run_negativos():
        return {"campaign": nombre, "match_type": "THEME", "status": "dry_run", "applied": False}
    # Sin API confiable para negativos en Smart (add_smart_campaign_theme es POSITIVO) → manual.
    return {"campaign": nombre, "match_type": "THEME", "status": "manual_required", "applied": False,
            "message": "Negativo en Smart: aplicar en Google Ads UI (API no confiable para themes negativos)."}


def aplicar_bloqueo(term: str, campanas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Una llamada por campaña marcada (NO batch)."""
    return [aplicar_en_campana(term, c) for c in campanas]
