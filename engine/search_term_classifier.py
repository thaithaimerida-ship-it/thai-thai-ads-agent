"""
Clasificador de search terms — Fase 1 (alta precisión, basada en contenido).

Clasifica cada término en: rojo | amarillo | verde | blanco.
- rojo:     candidato a negativo de ALTA confianza (patrón irrelevante o entidad ajena).
            NO se aplica automáticamente — auto_apply siempre False.
- amarillo: ambiguo — revisar, NO negativizar en Fase 1.
- verde:    intención Thai clara CON conversión.
- blanco:   marca propia protegida, intención Thai sin conversión, o neutro monitoreado.

Orden de evaluación (ver classify_search_term):
  1) normalizar  2) marca propia  3) patrones rojos  4) entidades curadas
  5) intención Thai útil  6) ambiguos  7) resto -> blanco

Reglas duras Fase 1:
  - El gasto NO es gatillo de clasificación (solo señal secundaria para reporte).
  - NO se protege un término solo por contener thai/tailandés/tailandia.
    Solo se protege la marca propia Thai Thai. Por eso 'muay thai',
    'masaje tailandés', 'viaje a tailandia' caen rojo aunque contengan 'thai'.
  - Matching por límite de palabra (\\b) tras normalizar: evita docena->cena,
    concurso->curso, etc.
  - suggested_match_type ∈ {EXACT, PHRASE, None} — nunca BROAD.
  - auto_apply siempre False (rojo = candidato a revisión, no aplicación).

NOTA Fase 1: este módulo solo CLASIFICA. La aplicación de negativos sigue
siendo manual vía la UI /negativos. Ver Fase 2 para acumulación histórica.
"""
import json
import os
import re
import unicodedata

_ENTITIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "irrelevant_entities.json"
)


def _normalize(s) -> str:
    """lowercase + quitar acentos (NFD/Mn) + colapsar espacios + trim."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


# ── Listas (en forma ya normalizada) ─────────────────────────────────────────
BRAND_PROTECT = (
    "thai thai", "thaithai", "thai thai merida",
    "thai thai menu", "thai thai reservas",
)

# (patrón_normalizado, categoría)
RED_PATTERNS = [
    ("muay thai", "muay_thai"),
    ("masaje tailandes", "masaje"),
    ("idioma tailandes", "idioma"),
    ("viaje a tailandia", "viaje"),
    ("receta", "receta"),
    ("curso", "curso"),
    ("empleo", "empleo"),
    ("trabajo", "empleo"),
    ("proveedor", "proveedor"),
    ("franquicia", "franquicia"),
    ("ropa thai", "producto"),
    ("productos tailandeses", "producto"),
]

GREEN_PATTERNS = (
    "restaurante tailandes", "comida tailandesa", "comida thai", "pad thai",
    "curry tailandes", "thai food", "delivery comida tailandesa",
    "menu restaurante tailandes", "reservar restaurante tailandes",
)

AMBIGUOUS_PATTERNS = (
    "comida asiatica", "comida oriental", "curry", "noodles",
    "restaurante cerca", "restaurantes en merida", "cena",
    "comida picante", "comida diferente",
)

# Ambiguos de FP alto: jamás se sugiere negativo en Fase 1 (p.ej. curry es Thai real).
GENERIC_RESTAURANT_PATTERNS = (
    "restaurants near me", "restaurant near me", "restaurante cerca",
    "restaurantes cerca", "comida cerca",
)

SUSPECTED_EXTERNAL_ENTITY_PATTERNS = (
    "el texano",
)

_HIGH_FP_AMBIGUOUS = ("curry",)


def _wb(norm: str, pattern: str) -> bool:
    """Match por límite de palabra del patrón (ya normalizado) en la query normalizada."""
    return re.search(r"\b" + re.escape(pattern) + r"\b", norm) is not None


def _first_match(norm: str, patterns):
    """Devuelve el primer elemento cuyo patrón matchea. patterns puede ser
    tupla de strings o lista de tuplas (pattern, category)."""
    for p in patterns:
        pat = p[0] if isinstance(p, tuple) else p
        if _wb(norm, pat):
            return p
    return None


def _load_entities():
    """Carga config/irrelevant_entities.json. Si falla, devuelve [] (no crashea
    el endpoint) — las entidades simplemente no se matchean."""
    try:
        with open(_ENTITIES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    out = []
    for e in raw:
        out.append({**e, "_norm_aliases": [_normalize(a) for a in e.get("aliases", [])]})
    return out


_ENTITIES = _load_entities()


def _match_entity(norm: str):
    for e in _ENTITIES:
        for alias in e["_norm_aliases"]:
            if alias and _wb(norm, alias):
                return e
    return None


def _phase1_multi_axis_defaults() -> dict:
    return {
        "semantic_class": "neutral",
        "business_intent": "unknown",
        "entity_status": "unknown",
        "conversion_quality": "unknown",
        "recommended_action": "observe",
        "negative_allowed": False,
    }


def _is_suspected_external_entity(norm: str) -> bool:
    return _first_match(norm, SUSPECTED_EXTERNAL_ENTITY_PATTERNS) is not None


def classify_search_term(query: str, cost: float = 0.0, conversions: float = 0.0) -> dict:
    """Clasifica un search term. Devuelve el objeto JSON de Fase 1.

    cost/conversions son señales SECUNDARIAS: cost nunca clasifica; conversions
    solo distingue verde (>=1) de blanco en intención Thai.
    """
    norm = _normalize(query)
    result = {
        "query": query,
        "classification": "blanco",
        "confidence": "n/a",
        "false_positive_risk": "n/a",
        "reason": "",
        "suggested_negative": None,
        "suggested_match_type": None,
        "auto_apply": False,
        **_phase1_multi_axis_defaults(),
    }

    # 1) Marca propia (lo ÚNICO que se protege automáticamente)
    if _first_match(norm, BRAND_PROTECT):
        result.update(classification="blanco", confidence="alta", false_positive_risk="bajo",
                      reason="marca propia protegida (Thai Thai)",
                      semantic_class="brand_protected", business_intent="own_brand",
                      entity_status="own_brand", recommended_action="protect")
        return result

    # 2) Patrones rojos de alta confianza (ANTES que intención Thai)
    m = _first_match(norm, RED_PATTERNS)
    if m:
        pat, category = m
        result.update(classification="rojo", confidence="alta", false_positive_risk="bajo",
                      reason=f"patron irrelevante de alta confianza ('{pat}', categoria {category})",
                      suggested_negative=pat, suggested_match_type="PHRASE",
                      semantic_class="red_safe", business_intent="out_of_scope",
                      entity_status="pattern_red_clear",
                      recommended_action="candidate_negative")
        return result

    # 3) Entidades curadas (restaurantes/marcas ajenas)
    e = _match_entity(norm)
    if e:
        result.update(classification="rojo", confidence=e.get("confidence", "alta"),
                      false_positive_risk="bajo",
                      reason=f"entidad ajena curada ('{e['canonical']}', categoria {e.get('category', '')})",
                      suggested_negative=e["canonical"],
                      suggested_match_type=e.get("suggested_match_type", "EXACT"),
                      semantic_class="red_safe", business_intent="external_business",
                      entity_status="curated",
                      recommended_action="candidate_negative")
        return result

    # 4) Intención Thai útil (nunca rojo)
    if _first_match(norm, GREEN_PATTERNS):
        if float(conversions or 0) >= 1:
            result.update(classification="verde", confidence="alta", false_positive_risk="bajo",
                          reason="intencion Thai clara con conversion",
                          semantic_class="thai_intent", business_intent="thai_food",
                          entity_status="none", recommended_action="protect")
        else:
            result.update(classification="blanco", confidence="alta", false_positive_risk="bajo",
                          reason="intencion Thai clara sin conversion (relevante, monitoreado)",
                          semantic_class="thai_intent", business_intent="thai_food",
                          entity_status="none", recommended_action="protect")
        return result

    # 5) Ambiguos (revisar, no negativizar)
    a = _first_match(norm, AMBIGUOUS_PATTERNS)
    if a:
        fp = "alto" if a in _HIGH_FP_AMBIGUOUS else "medio"
        result.update(classification="amarillo", confidence="media", false_positive_risk=fp,
                      reason=f"termino ambiguo ('{a}') — revisar, no negativizar en Fase 1")
        result.update(semantic_class="ambiguous_useful",
                      business_intent="generic_restaurant",
                      entity_status="none", recommended_action="observe")
        return result

    if _first_match(norm, GENERIC_RESTAURANT_PATTERNS):
        result.update(semantic_class="ambiguous_useful", business_intent="generic_restaurant",
                      entity_status="none", recommended_action="observe")
        return result

    if _is_suspected_external_entity(norm):
        result.update(semantic_class="external_entity_review",
                      business_intent="external_business",
                      entity_status="suspected_external",
                      recommended_action="review")
        return result

    # 6) Resto -> blanco / monitoreado
    result.update(classification="blanco", confidence="baja", false_positive_risk="bajo",
                  reason="neutro sin patron — monitoreado")
    return result
