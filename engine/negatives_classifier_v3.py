"""Read-only V3 classifier contract for /negativos.

V3 separates each search term into three axes:
- identity_axis: what the term appears to be
- behavior_axis: what the user did
- data_axis: whether clicks are enough to judge

This module does not call Google Ads and does not write anything.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from typing import Any


CLICKS_MIN = 35

IDENTITIES = {
    "marca_propia",
    "intencion_thai",
    "categoria_asiatica",
    "generico_util",
    "restaurante_externo",
    "negocio_no_relacionado",
    "basura",
    "desconocido",
}

BEHAVIORS = {"senal_dinero", "senal_local", "sin_conversion", "desconocida"}
DATA_STATES = {"suficiente", "insuficiente"}

BRAND_PATTERNS = (
    "thai thai",
    "thaithai",
    "thai thai merida",
    "restaurante thai thai",
)

THAI_INTENT_PATTERNS = (
    "comida tailandesa",
    "comida thai",
    "thai food",
    "restaurante tailandes",
    "restaurante thai",
    "delivery comida tailandesa",
    "curry tailandes",
    "tom yum",
)

JUNK_PATTERNS = (
    "receta",
    "curso",
    "empleo",
    "trabajo",
    "proveedor",
    "franquicia",
    "idioma tailandes",
    "masaje tailandes",
    "muay thai",
    "viaje a tailandia",
)

ASIAN_CATEGORY_PATTERNS = (
    "comida oriental",
    "comida japonesa",
    "comida china",
    "chinese food",
    "japanese food",
    "sushi",
    "ramen",
    "korean food",
    "comida coreana",
    "vietnamita",
    "wok",
    "dumpling",
    "bao",
)

GENERIC_USEFUL_PATTERNS = (
    "comida asiatica",
    "restaurante cerca de mi",
    "restaurantes cerca de mi",
    "restaurantes near me",
    "restaurant near me",
    "restaurants near me",
    "comida cerca de mi",
    "food near me",
    "lugares comida cerca de mi",
    "lugares para comer",
    "donde comer",
    "restaurante cercano para comer",
)

EXTERNAL_RESTAURANT_PATTERNS = (
    "hacienda teya",
    "tabom",
    "taboom",
    "tábom",
    "yakuza",
    "casa chaya",
    "chaya maya",
    "lians",
    "lian's",
    "vips",
    "vip's",
    "gio restaurante",
    "fiesta brava",
    "toks",
    "wayane",
    "sensei",
    "konsushi",
    "taro",
    "almar restaurante",
    "la rueda",
    "restaurante la rueda",
    "restaurante yucateco",
    "habaneros",
    "win chang",
    "amada mia bistro cafe",
    "amada mía bistro café",
    "lucero del alba",
    "tocho morocho",
    "restaurante marquesita",
    "casa thai",
    "bangkok casa thai",
    "bankok casa thai",
)

CONFIRMED_HIGH_PRIORITY_EXTERNAL_PATTERNS = (
    "casa thai",
    "casa thai merida",
    "bangkok casa thai",
    "bangkok casa thai merida",
    "bankok casa thai",
    "bankok casa thai merida",
)

BUSINESS_WORDS = (
    "restaurante",
    "restaurant",
    "cafe",
    "cafeteria",
    "taqueria",
    "tacos",
    "bar",
    "cantina",
    "hacienda",
    "bistro",
)

GENERIC_EXTERNAL_STOPWORDS = {
    "restaurante",
    "restaurantes",
    "restaurant",
    "restaurants",
    "cerca",
    "near",
    "me",
    "mi",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "para",
    "comer",
    "comida",
    "food",
    "merida",
    "yucatan",
    "en",
    "in",
    "open",
    "now",
}

ENTITIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "irrelevant_entities.json",
)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


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


def _word_match(norm: str, pattern: str) -> bool:
    return re.search(r"\b" + re.escape(_normalize(pattern)) + r"\b", norm) is not None


def _matches_any(norm: str, patterns: tuple[str, ...]) -> bool:
    return any(_word_match(norm, pattern) for pattern in patterns)


def _tokens(norm: str) -> list[str]:
    return re.findall(r"\b[a-z0-9]+\b", norm)


def _load_curated_external_aliases() -> tuple[str, ...]:
    try:
        with open(ENTITIES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return ()

    aliases: list[str] = []
    for entity in raw or []:
        aliases.append(entity.get("canonical", ""))
        aliases.extend(entity.get("aliases", []))
    return tuple(alias for alias in aliases if alias)


CURATED_EXTERNAL_ALIASES = _load_curated_external_aliases()


def identify_term(query: str, semantic_class: str | None = None) -> str:
    norm = _normalize(query)

    if _matches_any(norm, BRAND_PATTERNS):
        return "marca_propia"

    # Clear junk must stay junk even if it contains a Thai food token, e.g.
    # "receta pad thai".
    if _matches_any(norm, JUNK_PATTERNS):
        return "basura"

    if (
        _matches_any(norm, CURATED_EXTERNAL_ALIASES)
        or _matches_any(norm, EXTERNAL_RESTAURANT_PATTERNS)
        or semantic_class == "external_entity_review"
    ):
        return "restaurante_externo"

    tokens = _tokens(norm)
    if any(token.isdigit() for token in tokens) and _matches_any(norm, BUSINESS_WORDS):
        return "restaurante_externo"

    if _matches_any(norm, ASIAN_CATEGORY_PATTERNS):
        return "categoria_asiatica"

    if _matches_any(norm, GENERIC_USEFUL_PATTERNS):
        return "generico_util"

    if _matches_any(norm, THAI_INTENT_PATTERNS):
        return "intencion_thai"

    if _matches_any(norm, BUSINESS_WORDS):
        distinctive = [
            token for token in tokens
            if token not in GENERIC_EXTERNAL_STOPWORDS and not token.isdigit()
        ]
        if distinctive:
            return "restaurante_externo"

    if semantic_class == "brand_protected":
        return "marca_propia"
    if semantic_class == "thai_intent":
        return "intencion_thai"
    if semantic_class == "ambiguous_useful":
        return "generico_util"
    if semantic_class == "red_safe":
        return "basura"

    return "desconocido"


def _is_confirmed_high_priority_external(query: str) -> bool:
    return _matches_any(_normalize(query), CONFIRMED_HIGH_PRIORITY_EXTERNAL_PATTERNS)


def behavior_from_term(term: dict[str, Any]) -> str:
    conversion_quality = term.get("conversion_quality")
    if conversion_quality == "money_action":
        return "senal_dinero"
    if conversion_quality == "weak_local_action":
        return "senal_local"
    if conversion_quality == "none":
        return "sin_conversion"
    return "desconocida"


def data_axis_from_clicks(clicks: int) -> str:
    return "suficiente" if clicks >= CLICKS_MIN else "insuficiente"


def _campaign_context(campaign: str) -> str:
    norm = _normalize(campaign)
    if "delivery" in norm:
        return "delivery"
    if "experiencia" in norm or "reserva" in norm:
        return "experiencia"
    if "local" in norm or "maps" in norm:
        return "local"
    return "general"


def _base_reason(identity: str, behavior: str, data_axis: str, campaign: str) -> str:
    campaign_context = _campaign_context(campaign)
    if behavior == "senal_dinero":
        return (
            "Este término tuvo una señal de valor para la campaña. "
            f"Contexto detectado: {campaign_context}. Si hay dinero o intención comercial, no se bloquea."
        )
    if behavior == "senal_local":
        return (
            "Hubo señales locales como rutas, llamadas o interacciones en Maps. "
            "Puede ser un cliente real comparando opciones; requiere revisión humana."
        )
    if identity == "marca_propia":
        return "Es marca propia de Thai Thai. Se protege siempre."
    if identity == "intencion_thai":
        return "Es una búsqueda de comida tailandesa o intención Thai. Se protege."
    if identity == "generico_util":
        return "Es una búsqueda genérica útil para descubrir restaurantes. No se bloquea."
    if identity == "categoria_asiatica":
        return "Es una categoría asiática relacionada. Puede traer clientes relevantes."
    if identity == "restaurante_externo" and data_axis == "insuficiente":
        return (
            "Parece otro restaurante o negocio. "
            "Aún no hay datos suficientes para decidir bloqueo."
        )
    if data_axis == "insuficiente":
        return f"Tiene menos de {CLICKS_MIN} clics. Todavía no hay datos suficientes."
    if identity == "restaurante_externo":
        return "Parece otro restaurante o negocio externo. Hugo debe confirmarlo antes de cualquier acción."
    if identity == "basura":
        return "Parece una búsqueda fuera de alcance y ya tiene suficientes clics para revisarse en una fase futura."
    return "No hay suficiente certeza sobre la intención. Si hay duda, no se bloquea."


def _decision(
    identity: str,
    behavior: str,
    data_axis: str,
    suggested_match_type: str,
    confirmed_external: bool,
) -> tuple[str, str, bool]:
    # Cascada V3.
    if behavior == "senal_dinero":
        return "No bloquear por duda", "no_action", False
    if identity in {"marca_propia", "intencion_thai"}:
        return "Marca protegida", "no_action", False
    if behavior == "senal_local":
        return "Señal local: revisar con cuidado", "no_action", False
    if identity == "generico_util":
        return "Búsqueda útil", "no_action", False
    if identity == "categoria_asiatica":
        return "Búsqueda relacionada", "no_action", False
    if identity == "restaurante_externo":
        return "Restaurante externo por confirmar", "no_action", False
    if data_axis == "insuficiente":
        return "Datos insuficientes", "no_action", False
    if identity == "basura":
        allowed = suggested_match_type in {"EXACT", "PHRASE"}
        return "Basura clara", "future_review_candidate" if allowed else "no_action", allowed
    return "No bloquear por duda", "no_action", False


def classify_negative_v3(term: dict[str, Any]) -> dict[str, Any]:
    query = term.get("query") or ""
    campaign = term.get("campaign_name") or ""
    clicks = _int(term.get("clicks"))
    cost_mxn = round(_number(term.get("cost")), 2)
    conversions = _number(term.get("conversions"))
    confirmed_high_priority_external = _is_confirmed_high_priority_external(query)
    suggested_match_type = str(term.get("suggested_match_type") or "").upper() or None
    if confirmed_high_priority_external:
        suggested_match_type = "EXACT"
    already_negative = term.get("already_negative")

    identity = identify_term(query, term.get("semantic_class"))
    behavior = behavior_from_term(term)
    data_axis = data_axis_from_clicks(clicks)
    confirmed_external = (
        term.get("hugo_confirmed_identity") == "restaurante_externo"
        or confirmed_high_priority_external
    )
    confirmado_por_hugo = bool(confirmed_high_priority_external)
    alta_prioridad = bool(confirmed_high_priority_external)

    state_ui, recommended_action, block_allowed = _decision(
        identity,
        behavior,
        data_axis,
        suggested_match_type or "",
        confirmed_external,
    )

    if already_negative is True:
        state_ui = "Ya bloqueado"
        recommended_action = "no_action"
        block_allowed = False

    reason_human = _base_reason(identity, behavior, data_axis, campaign)
    priority_score = round((clicks * 10) + cost_mxn, 2)
    if confirmed_high_priority_external:
        priority_score += 10000

    return {
        "term": query,
        "campaign": campaign,
        "clicks": clicks,
        "cost_mxn": cost_mxn,
        "conversions": conversions,
        "identity_axis": identity,
        "behavior_axis": behavior,
        "data_axis": data_axis,
        "state_ui": state_ui,
        "reason_human": reason_human,
        "recommended_action": recommended_action,
        "block_allowed": block_allowed,
        "priority_score": priority_score,
        "suggested_match_type": suggested_match_type,
        "already_negative": already_negative,
        "confirmado_por_hugo": confirmado_por_hugo,
        "alta_prioridad": alta_prioridad,
        "auto_apply": False,
    }


def build_negatives_preview_v3_payload(search_terms_payload: dict[str, Any]) -> dict[str, Any]:
    if search_terms_payload.get("status") != "success":
        return search_terms_payload

    items = [
        classify_negative_v3(term)
        for term in search_terms_payload.get("search_terms", [])
    ]
    state_counts = Counter(item["state_ui"] for item in items)
    identity_counts = Counter(item["identity_axis"] for item in items)
    behavior_counts = Counter(item["behavior_axis"] for item in items)
    action_counts = Counter(item["recommended_action"] for item in items)

    return {
        "status": "success",
        "date_range": search_terms_payload.get("date_range"),
        "total": len(items),
        "data_floor": {"clicks_min": CLICKS_MIN},
        "state_counts": dict(state_counts),
        "identity_counts": dict(identity_counts),
        "behavior_counts": dict(behavior_counts),
        "recommended_action_counts": dict(action_counts),
        "items": items,
    }
