import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.search_term_classifier import classify_search_term


@pytest.mark.parametrize(
    "query",
    [
        "rancho da picanha churrascaria diaz bolio",
        "la barra kulichi",
        "restaurante hermana republica",
        "restaurant la chaya maya merida yucatan",
        "restaurant casa de los abuelos cerca de mi",
        "la rueda restaurante",
        "restaurante tokio 07 merida",
        "restaurante miyabi",
        "restaurante yakuza merida",
        "carlota caucel bistro cafe fotos",
        "restaurant el trapiche",
        "yuyas bar",
    ],
)
def test_specific_uncurated_businesses_are_external_entity_review(query):
    result = classify_search_term(query)

    assert result["semantic_class"] == "external_entity_review"
    assert result["business_intent"] == "possible_external_restaurant"
    assert result["entity_status"] == "suspected_external"
    assert result["recommended_action"] == "review"
    assert result["classification"] == "blanco"
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"


@pytest.mark.parametrize(
    "query",
    [
        "chinese restaurants near me",
        "restaurante coreano merida",
        "restaurante japones merida",
        "sushi merida",
        "ramen merida",
        "pizzeria merida",
    ],
)
def test_other_cuisine_is_ambiguous_useful_not_external_entity(query):
    result = classify_search_term(query)

    assert result["semantic_class"] == "ambiguous_useful"
    assert result["business_intent"] == "other_cuisine"
    assert result["entity_status"] == "none"
    assert result["recommended_action"] == "review"
    assert result["classification"] == "blanco"
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"


@pytest.mark.parametrize(
    ("query", "expected_classification"),
    [
        ("restaurants near me", "blanco"),
        ("restaurante cerca de mi", "amarillo"),
        ("restaurante cerca de mi ubicacion actual", "amarillo"),
        ("comida cerca de mi", "blanco"),
        ("restaurantes en merida", "amarillo"),
        ("food near me", "blanco"),
        ("cocina economica cerca de mi", "blanco"),
        ("plaza restaurantes merida", "blanco"),
    ],
)
def test_generic_restaurant_queries_stay_ambiguous_useful(query, expected_classification):
    result = classify_search_term(query)

    assert result["semantic_class"] == "ambiguous_useful"
    assert result["business_intent"] == "generic_restaurant"
    assert result["entity_status"] == "none"
    assert result["recommended_action"] == "observe"
    assert result["classification"] == expected_classification
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"


@pytest.mark.parametrize(
    ("query", "semantic_class", "classification"),
    [
        ("thai thai merida", "brand_protected", "blanco"),
        ("comida tailandesa merida", "thai_intent", "blanco"),
        ("receta pad thai", "red_safe", "rojo"),
        ("hacienda teya", "red_safe", "rojo"),
        ("el texano merida", "external_entity_review", "blanco"),
    ],
)
def test_phase_3a_regressions(query, semantic_class, classification):
    result = classify_search_term(query)

    assert result["semantic_class"] == semantic_class
    assert result["classification"] == classification
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"
