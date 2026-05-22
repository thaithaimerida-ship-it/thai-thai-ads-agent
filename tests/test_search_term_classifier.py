import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from engine.search_term_classifier import classify_search_term

# ── Casos obligatorios ────────────────────────────────────────────────────────
MUST_BE_RED = [
    "restaurante hacienda teya",
    "los motuleños y mas",
    "querreke",
    "masaje tailandés",
    "muay thai mérida",
    "receta pad thai",
    "trabajo restaurante tailandés",
]

MUST_NOT_BE_RED = [
    "restaurante tailandés mérida",
    "comida tailandesa mérida",
    "pad thai mérida",
    "curry tailandés",
    "thai thai merida",
    "comida asiática",
    "curry",
    "restaurante cerca de mí",
]


@pytest.mark.parametrize("q", MUST_BE_RED)
def test_must_be_red(q):
    r = classify_search_term(q)
    assert r["classification"] == "rojo", f"{q!r} -> {r['classification']} ({r['reason']})"


@pytest.mark.parametrize("q", MUST_NOT_BE_RED)
def test_must_not_be_red(q):
    r = classify_search_term(q)
    assert r["classification"] != "rojo", f"{q!r} -> rojo ({r['reason']})"


# ── Invariantes Fase 1 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", MUST_BE_RED + MUST_NOT_BE_RED)
def test_auto_apply_always_false(q):
    assert classify_search_term(q)["auto_apply"] is False


@pytest.mark.parametrize("q", MUST_BE_RED + MUST_NOT_BE_RED)
def test_never_broad(q):
    assert classify_search_term(q)["suggested_match_type"] != "BROAD"


@pytest.mark.parametrize("q", MUST_BE_RED + MUST_NOT_BE_RED)
def test_classification_is_valid(q):
    assert classify_search_term(q)["classification"] in ("rojo", "amarillo", "verde", "blanco")


# ── Clasificaciones específicas ───────────────────────────────────────────────
def test_comida_asiatica_amarillo():
    assert classify_search_term("comida asiática")["classification"] == "amarillo"


def test_curry_amarillo_high_fp_no_negative():
    r = classify_search_term("curry")
    assert r["classification"] == "amarillo"
    assert r["false_positive_risk"] == "alto"
    assert r["suggested_negative"] is None


def test_brand_protected_blanco():
    r = classify_search_term("thai thai merida")
    assert r["classification"] == "blanco"
    assert "marca propia" in r["reason"]


def test_thai_intent_not_red():
    assert classify_search_term("restaurante tailandés mérida")["classification"] in ("verde", "blanco")


def test_entity_uses_exact():
    r = classify_search_term("querreke")
    assert r["classification"] == "rojo"
    assert r["suggested_match_type"] == "EXACT"


def test_red_pattern_uses_phrase():
    r = classify_search_term("receta pad thai")
    assert r["classification"] == "rojo"
    assert r["suggested_match_type"] == "PHRASE"


def test_verde_requires_conversion():
    assert classify_search_term("comida tailandesa mérida", conversions=2)["classification"] == "verde"
    assert classify_search_term("comida tailandesa mérida", conversions=0)["classification"] == "blanco"


def test_word_boundary_no_false_match():
    # 'cena' no debe matchear 'docena'; 'curso' no debe matchear 'concurso'
    assert classify_search_term("media docena de tamales")["classification"] != "amarillo"
    assert classify_search_term("concurso de cocina")["classification"] != "rojo"
