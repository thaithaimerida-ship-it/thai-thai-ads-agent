import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.search_term_classifier import _compute_base_negative_eligible, classify_search_term


_UNSET = object()


def _classifier_case(
    query,
    conversion_quality="none",
    suggested_match_type=_UNSET,
    entity_status=None,
):
    result = classify_search_term(query, conversion_quality=conversion_quality)
    if suggested_match_type is not _UNSET:
        result["suggested_match_type"] = suggested_match_type
    if entity_status is not None:
        result["entity_status"] = entity_status
    return result


@pytest.mark.parametrize(
    ("query", "conversion_quality", "expected_match_type"),
    [
        ("hacienda teya", "none", "EXACT"),
        ("hacienda teya", "weak_local_action", "EXACT"),
        ("casa thai merida", "none", "EXACT"),
        ("receta pad thai", "none", "PHRASE"),
    ],
)
def test_red_safe_terms_can_be_base_negative_eligible(query, conversion_quality, expected_match_type):
    result = classify_search_term(query, conversion_quality=conversion_quality)

    assert result["semantic_class"] == "red_safe"
    assert result["entity_status"] in {"curated", "clear_red_pattern"}
    assert result["suggested_match_type"] == expected_match_type
    assert result["base_negative_eligible"] is True
    assert result["negative_allowed"] is False


@pytest.mark.parametrize(
    ("query", "conversion_quality"),
    [
        ("hacienda teya", "unknown"),
        ("hacienda teya", "money_action"),
    ],
)
def test_red_safe_with_unsafe_conversion_quality_is_not_base_eligible(query, conversion_quality):
    result = classify_search_term(query, conversion_quality=conversion_quality)

    assert result["semantic_class"] == "red_safe"
    assert result["base_negative_eligible"] is False
    assert result["negative_allowed"] is False


@pytest.mark.parametrize("match_type", [None, "BROAD"])
def test_red_safe_with_unsafe_match_type_is_not_base_eligible(match_type):
    result = _classifier_case("hacienda teya", suggested_match_type=match_type)

    assert result["semantic_class"] == "red_safe"
    assert _compute_base_negative_eligible(result) is False
    assert result["negative_allowed"] is False


@pytest.mark.parametrize(
    ("query", "semantic_class"),
    [
        ("el texano merida", "external_entity_review"),
        ("restaurants near me", "ambiguous_useful"),
        ("comida thai merida", "thai_intent"),
        ("thai thai merida", "brand_protected"),
        ("media docena de tamales", "neutral"),
    ],
)
def test_non_red_safe_terms_are_not_base_negative_eligible(query, semantic_class):
    result = classify_search_term(query, conversion_quality="none")

    assert result["semantic_class"] == semantic_class
    assert result["base_negative_eligible"] is False
    assert result["negative_allowed"] is False


def test_legacy_classification_does_not_change_for_base_eligibility():
    cases = {
        "thai thai merida": "blanco",
        "comida thai merida": "blanco",
        "comida thai merida con conversion": "verde",
        "receta pad thai": "rojo",
        "hacienda teya": "rojo",
        "el texano merida": "blanco",
        "restaurants near me": "blanco",
        "media docena de tamales": "blanco",
    }

    for query, expected in cases.items():
        conversions = 1 if query == "comida thai merida con conversion" else 0
        source_query = "comida thai merida" if conversions else query
        result = classify_search_term(source_query, conversions=conversions, conversion_quality="none")
        assert result["classification"] == expected


def _setup_search_terms_endpoint(monkeypatch, terms, negatives=None):
    import routes.analysis as analysis

    engine = {
        "get_ads_client": lambda: MagicMock(),
        "fetch_search_term_data": MagicMock(return_value=terms),
    }
    monkeypatch.setattr(analysis, "_get_engine", lambda: engine)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "fetch_negative_keywords", lambda c, cid: negatives or {})
    monkeypatch.setattr(analysis, "aggregate_windows", lambda norms: {})
    monkeypatch.setattr(analysis, "accumulated_reds", lambda today_top100_norms: [])
    monkeypatch.setattr(analysis, "fetch_search_term_conversion_breakdown", lambda c, cid, dr: {})


def _term(query="hacienda teya", campaign_id="111", conversions=0, all_conversions=0):
    item = {
        "query": query,
        "campaign_name": "Search",
        "cost_micros": 5_000_000,
        "conversions": conversions,
        "all_conversions": all_conversions,
        "clicks": 5,
        "impressions": 50,
    }
    if campaign_id is not None:
        item["campaign_id"] = campaign_id
    return item


def _single_search_term(monkeypatch, terms, negatives=None):
    _setup_search_terms_endpoint(monkeypatch, terms, negatives=negatives)
    from main import app

    response = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS")
    assert response.status_code == 200
    return response.json()["search_terms"][0]


def test_search_terms_allows_negative_only_when_base_eligible_not_blocked_and_has_campaign(monkeypatch):
    t = _single_search_term(monkeypatch, [_term()])

    assert t["base_negative_eligible"] is True
    assert t["already_negative"] is False
    assert t["campaign_id"] == "111"
    assert t["negative_allowed"] is True


def test_search_terms_blocks_negative_allowed_when_already_negative_true(monkeypatch):
    negatives = {
        "111": {
            "campaign_name": "Search",
            "channel_type": "SEARCH",
            "negatives": [{"text": "hacienda teya", "match_type": "EXACT", "resource_name": "rn"}],
        }
    }

    t = _single_search_term(monkeypatch, [_term()], negatives=negatives)

    assert t["base_negative_eligible"] is True
    assert t["already_negative"] is True
    assert t["negative_allowed"] is False


def test_negative_allowed_helper_fails_closed_when_already_negative_missing():
    import routes.analysis as analysis

    assert analysis._compute_negative_allowed({
        "base_negative_eligible": True,
        "campaign_id": "111",
    }) is False


def test_negative_allowed_helper_fails_closed_when_already_negative_none():
    import routes.analysis as analysis

    assert analysis._compute_negative_allowed({
        "base_negative_eligible": True,
        "already_negative": None,
        "campaign_id": "111",
    }) is False


def test_negative_allowed_helper_fails_closed_when_already_negative_string():
    import routes.analysis as analysis

    assert analysis._compute_negative_allowed({
        "base_negative_eligible": True,
        "already_negative": "false",
        "campaign_id": "111",
    }) is False


def test_search_terms_blocks_negative_allowed_without_campaign_id(monkeypatch):
    t = _single_search_term(monkeypatch, [_term(campaign_id=None)])

    assert t["base_negative_eligible"] is True
    assert t["campaign_id"] == ""
    assert t["negative_allowed"] is False


def test_search_terms_blocks_negative_allowed_when_base_not_eligible(monkeypatch):
    t = _single_search_term(monkeypatch, [_term(query="restaurants near me")])

    assert t["base_negative_eligible"] is False
    assert t["already_negative"] is False
    assert t["campaign_id"] == "111"
    assert t["negative_allowed"] is False


def test_search_terms_fails_closed_when_negative_lookup_is_unreliable(monkeypatch):
    import routes.analysis as analysis

    engine = {
        "get_ads_client": lambda: MagicMock(),
        "fetch_search_term_data": MagicMock(return_value=[_term()]),
    }
    monkeypatch.setattr(analysis, "_get_engine", lambda: engine)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "fetch_negative_keywords", lambda c, cid: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(analysis, "aggregate_windows", lambda norms: {})
    monkeypatch.setattr(analysis, "accumulated_reds", lambda today_top100_norms: [])
    monkeypatch.setattr(analysis, "fetch_search_term_conversion_breakdown", lambda c, cid, dr: {})

    from main import app

    t = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS").json()["search_terms"][0]

    assert t["base_negative_eligible"] is True
    assert t["already_negative"] is None
    assert t["negative_allowed"] is False
