"""
Matcher de negative keywords (#2/#3): determina si un search term ya está
cubierto por un negativo existente, según su match type (EXACT/PHRASE/BROAD).

Solo a nivel campaña (campaign_criterion). NO cubre listas compartidas (shared
sets). Reusa _normalize de Fase 1 (solo import; no modifica el clasificador).
"""
from engine.search_term_classifier import _normalize


def _blocks(query_norm: str, neg_norm: str, match_type: str) -> bool:
    """¿Un negativo (neg_norm, match_type) bloquea a query_norm? Ambos normalizados."""
    if not neg_norm:
        return False
    mt = (match_type or "").upper()
    if mt == "EXACT":
        return query_norm == neg_norm
    if mt == "PHRASE":
        # Frase contigua: las palabras del negativo aparecen en secuencia.
        return (" " + query_norm + " ").find(" " + neg_norm + " ") >= 0
    # BROAD (y default): todas las palabras del negativo presentes (cualquier orden).
    return set(neg_norm.split()).issubset(set(query_norm.split()))


def find_blocking_negative(query: str, negatives: list) -> dict | None:
    """Devuelve el primer negativo de la lista que bloquea `query`, o None.

    negatives: lista de dicts {"text", "match_type", ...} (de fetch_negative_keywords).
    """
    q = _normalize(query)
    for n in (negatives or []):
        if _blocks(q, _normalize(n.get("text", "")), n.get("match_type", "")):
            return n
    return None
