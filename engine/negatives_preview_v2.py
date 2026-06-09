"""Read-only presentation contract for the /negativos V2 review queue."""
from __future__ import annotations

import os
from collections import Counter
from typing import Any


DEFAULT_CLICKS_MIN = 12
DEFAULT_COST_MIN_MXN = 120.0

VALID_UI_STATES = {
    "nuevo",
    "protegido",
    "revisar_con_cuidado",
    "competidor_por_confirmar",
    "datos_insuficientes",
    "listo_para_bloquear",
    "bloqueado",
    "ignorado",
    "monitoreo",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_data_floor() -> dict[str, float | int]:
    return {
        "clicks_min": _env_int("NEGATIVES_CLICKS_MIN", DEFAULT_CLICKS_MIN),
        "cost_min_mxn": _env_float("NEGATIVES_COST_MIN_MXN", DEFAULT_COST_MIN_MXN),
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _enough_data(clicks: int, cost_mxn: float, clicks_min: int, cost_min_mxn: float) -> tuple[bool, str | None]:
    if clicks < clicks_min:
        return False, "No tiene suficientes clics para decidir."
    if cost_mxn < cost_min_mxn:
        return False, "No tiene suficiente gasto para decidir."
    return True, None


def _base_item(term: dict[str, Any], enough_data: bool, data_floor_reason: str | None) -> dict[str, Any]:
    return {
        "term": term.get("query") or "",
        "campaign": term.get("campaign_name") or "",
        "clicks": _int(term.get("clicks")),
        "cost_mxn": round(_number(term.get("cost")), 2),
        "conversions": _number(term.get("conversions")),
        "conversion_quality": term.get("conversion_quality") or "unknown",
        "enough_data": enough_data,
        "data_floor_reason": data_floor_reason,
        "state": "monitoreo",
        "recommended_action": "no_action",
        "reason_human": "No hay una razon clara para bloquear este termino. La accion por defecto es no hacer nada.",
        "block_allowed": False,
        "suggested_match_type": term.get("suggested_match_type"),
        "is_protected": False,
        "protected_reason": None,
        "source": {
            "campaign_id": term.get("campaign_id"),
            "suggested_negative": term.get("suggested_negative"),
            "semantic_class": term.get("semantic_class"),
            "already_negative": term.get("already_negative"),
            "negative_allowed": term.get("negative_allowed"),
            "base_negative_eligible": term.get("base_negative_eligible"),
        },
    }


def present_negative_term(term: dict[str, Any]) -> dict[str, Any]:
    floor = get_data_floor()
    clicks = _int(term.get("clicks"))
    cost_mxn = _number(term.get("cost"))
    enough_data, data_floor_reason = _enough_data(
        clicks,
        cost_mxn,
        int(floor["clicks_min"]),
        float(floor["cost_min_mxn"]),
    )
    item = _base_item(term, enough_data, data_floor_reason)

    semantic_class = term.get("semantic_class")
    conversion_quality = term.get("conversion_quality")
    suggested_match_type = str(term.get("suggested_match_type") or "").upper()

    if term.get("already_negative") is True:
        item.update(
            state="bloqueado",
            reason_human="Este termino ya esta bloqueado por un negativo existente.",
        )
        return item

    if semantic_class in {"brand_protected", "thai_intent"}:
        item.update(
            state="protegido",
            is_protected=True,
            protected_reason="marca_o_intencion_thai",
            reason_human="Esto parece tu marca o una busqueda directamente relacionada con Thai Thai. No se debe bloquear.",
        )
        return item

    if semantic_class == "ambiguous_useful":
        item.update(
            state="protegido",
            is_protected=True,
            protected_reason="generico_util",
            reason_human="Esta busqueda puede traer clientes nuevos. No se debe bloquear.",
        )
        return item

    if conversion_quality == "money_action":
        item.update(
            state="protegido",
            is_protected=True,
            protected_reason="money_action",
            reason_human="Este termino tuvo una accion de valor como pedido, reserva, WhatsApp o intencion comercial. No se debe bloquear.",
        )
        return item

    if conversion_quality == "unknown":
        item.update(
            state="protegido",
            is_protected=True,
            protected_reason="conversion_desconocida",
            reason_human="Hubo conversiones o senales que no se pudieron clasificar con seguridad. Si hay duda, no se bloquea.",
        )
        return item

    if conversion_quality == "weak_local_action":
        item.update(
            state="revisar_con_cuidado",
            reason_human="Algunas personas que buscaron esto pidieron como llegar o llamaron, pero no hicieron un pedido. Puede ser un cliente real comparando, asi que bloquearlo es arriesgado.",
        )
        return item

    if semantic_class == "external_entity_review":
        item.update(
            state="competidor_por_confirmar",
            recommended_action="needs_confirmation",
            reason_human="Parece otro restaurante, lugar o negocio. Confirmalo antes de decidir si debe bloquearse.",
        )
        return item

    if semantic_class == "red_safe" and conversion_quality == "none" and not enough_data:
        item.update(
            state="datos_insuficientes",
            reason_human="Todavia no hay suficientes datos para decidir. Esperemos a tener mas clics y gasto antes de bloquear.",
        )
        return item

    if semantic_class == "red_safe" and conversion_quality == "none" and enough_data:
        block_allowed = (
            term.get("negative_allowed") is True
            and term.get("base_negative_eligible") is True
            and suggested_match_type in {"EXACT", "PHRASE"}
        )
        item.update(
            state="listo_para_bloquear" if block_allowed else "monitoreo",
            recommended_action="propose_block" if block_allowed else "no_action",
            block_allowed=block_allowed,
            reason_human=f"Este termino gasto dinero suficiente sin generar senales utiles. Puede revisarse para bloqueo {suggested_match_type}.",
        )
        return item

    return item


def build_negatives_preview_payload(search_terms_payload: dict[str, Any]) -> dict[str, Any]:
    if search_terms_payload.get("status") != "success":
        return search_terms_payload

    items = [
        present_negative_term(term)
        for term in search_terms_payload.get("search_terms", [])
    ]
    state_counts = Counter(item["state"] for item in items)
    action_counts = Counter(item["recommended_action"] for item in items)

    return {
        "status": "success",
        "date_range": search_terms_payload.get("date_range"),
        "total": len(items),
        "data_floor": get_data_floor(),
        "state_counts": dict(state_counts),
        "recommended_action_counts": dict(action_counts),
        "items": items,
    }
