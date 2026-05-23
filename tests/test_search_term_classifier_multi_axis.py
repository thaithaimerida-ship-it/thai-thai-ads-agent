import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.search_term_classifier import classify_search_term


EXPECTED_MULTI_AXIS_FIELDS = {
    "semantic_class",
    "business_intent",
    "entity_status",
    "conversion_quality",
    "recommended_action",
    "negative_allowed",
    "suggested_match_type",
    "classification",
}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "thai thai merida",
            {
                "semantic_class": "brand_protected",
                "business_intent": "own_brand",
                "entity_status": "own_brand",
                "recommended_action": "protect",
                "classification": "blanco",
            },
        ),
        (
            "comida tailandesa merida",
            {
                "semantic_class": "thai_intent",
                "business_intent": "thai_food",
                "entity_status": "none",
                "recommended_action": "protect",
                "classification": "blanco",
            },
        ),
        (
            "receta pad thai",
            {
                "semantic_class": "red_safe",
                "business_intent": "out_of_scope",
                "entity_status": "pattern_red_clear",
                "recommended_action": "candidate_negative",
                "classification": "rojo",
            },
        ),
        (
            "trabajo restaurante tailandes",
            {
                "semantic_class": "red_safe",
                "business_intent": "out_of_scope",
                "entity_status": "pattern_red_clear",
                "recommended_action": "candidate_negative",
                "classification": "rojo",
            },
        ),
        (
            "clases de muay thai merida",
            {
                "semantic_class": "red_safe",
                "business_intent": "out_of_scope",
                "entity_status": "pattern_red_clear",
                "recommended_action": "candidate_negative",
                "classification": "rojo",
            },
        ),
        (
            "masaje tailandes merida",
            {
                "semantic_class": "red_safe",
                "business_intent": "out_of_scope",
                "entity_status": "pattern_red_clear",
                "recommended_action": "candidate_negative",
                "classification": "rojo",
            },
        ),
        (
            "el texano merida",
            {
                "semantic_class": "external_entity_review",
                "business_intent": "external_business",
                "entity_status": "suspected_external",
                "recommended_action": "review",
                "classification": "blanco",
            },
        ),
        (
            "restaurants near me",
            {
                "semantic_class": "ambiguous_useful",
                "business_intent": "generic_restaurant",
                "entity_status": "none",
                "recommended_action": "observe",
                "classification": "blanco",
            },
        ),
        (
            "restaurante cerca de mi",
            {
                "semantic_class": "ambiguous_useful",
                "business_intent": "generic_restaurant",
                "entity_status": "none",
                "recommended_action": "observe",
                "classification": "amarillo",
            },
        ),
        (
            "media docena de tamales",
            {
                "semantic_class": "neutral",
                "business_intent": "unknown",
                "entity_status": "unknown",
                "recommended_action": "observe",
                "classification": "blanco",
            },
        ),
    ],
)
def test_multi_axis_contract_is_additive_and_conservative(query, expected):
    result = classify_search_term(query)

    assert EXPECTED_MULTI_AXIS_FIELDS.issubset(result.keys())
    for key, value in expected.items():
        assert result[key] == value
    assert result["conversion_quality"] == "unknown"
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"


@pytest.mark.parametrize(
    ("query", "conversions", "expected_classification"),
    [
        ("thai thai merida", 0, "blanco"),
        ("comida tailandesa merida", 0, "blanco"),
        ("comida tailandesa merida", 2, "verde"),
        ("receta pad thai", 0, "rojo"),
        ("querreke", 0, "rojo"),
        ("comida asiatica", 0, "amarillo"),
        ("curry", 0, "amarillo"),
        ("restaurante cerca de mi", 0, "amarillo"),
        ("media docena de tamales", 0, "blanco"),
        ("el texano merida", 0, "blanco"),
    ],
)
def test_legacy_classification_regression(query, conversions, expected_classification):
    result = classify_search_term(query, conversions=conversions)

    assert result["classification"] == expected_classification


@pytest.mark.parametrize(
    "query",
    [
        "thai thai merida",
        "comida tailandesa merida",
        "receta pad thai",
        "querreke",
        "restaurants near me",
        "restaurante cerca de mi",
        "el texano merida",
        "media docena de tamales",
    ],
)
def test_phase_1_never_allows_negative_or_broad(query):
    result = classify_search_term(query)

    assert result["conversion_quality"] == "unknown"
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"
