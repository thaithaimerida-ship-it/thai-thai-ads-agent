import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.search_term_classifier import classify_conversion_quality, classify_search_term


def test_no_conversions_maps_to_none():
    assert classify_conversion_quality([], conversions=0, all_conversions=0) == "none"


@pytest.mark.parametrize(
    "name",
    [
        "reserva_completada_directa",
        "Pedido GloriaFood Online",
    ],
)
def test_allowlisted_money_actions_map_to_money_action(name):
    actions = [{"name": name, "conversions": 1, "all_conversions": 1}]

    assert classify_conversion_quality(actions, conversions=1, all_conversions=1) == "money_action"


@pytest.mark.parametrize(
    "name",
    [
        "click_pedir_online",
        "click_whatsapp",
        "Local actions - Directions",
        "Store visits",
        "Local actions - Website visits",
        "Local actions - Phone calls",
        "Local actions - Menu views",
        "Local actions - Other engagements",
    ],
)
def test_weak_local_actions_map_to_weak_local_action(name):
    actions = [{"name": name, "conversions": 0, "all_conversions": 1}]

    assert classify_conversion_quality(actions, conversions=0, all_conversions=1) == "weak_local_action"


def test_money_action_wins_over_weak_local_action():
    actions = [
        {"name": "Local actions - Directions", "conversions": 0, "all_conversions": 1},
        {"name": "Pedido GloriaFood Online", "conversions": 1, "all_conversions": 1},
    ]

    assert classify_conversion_quality(actions, conversions=1, all_conversions=2) == "money_action"


def test_weak_plus_unknown_action_maps_to_unknown():
    actions = [
        {"name": "Local actions - Directions", "conversions": 0, "all_conversions": 1},
        {"name": "mystery conversion", "conversions": 0, "all_conversions": 1},
    ]

    assert classify_conversion_quality(actions, conversions=0, all_conversions=2) == "unknown"


@pytest.mark.parametrize("actions", [[{"name": "", "conversions": 1}], [{"conversions": 1}]])
def test_positive_conversions_without_reliable_name_map_to_unknown(actions):
    assert classify_conversion_quality(actions, conversions=1, all_conversions=1) == "unknown"


def test_positive_conversions_without_breakdown_map_to_unknown():
    assert classify_conversion_quality(None, conversions=1, all_conversions=1) == "unknown"


def test_classifier_accepts_conversion_quality_without_changing_legacy_classification():
    result = classify_search_term(
        "comida tailandesa merida",
        conversions=2,
        conversion_quality="money_action",
    )

    assert result["classification"] == "verde"
    assert result["conversion_quality"] == "money_action"
    assert result["negative_allowed"] is False
    assert result["suggested_match_type"] != "BROAD"


class _Enum:
    def __init__(self, name):
        self.name = name


def _breakdown_row(query, campaign_id, action_name, all_conversions=1, conversions=0):
    row = SimpleNamespace()
    row.search_term_view = SimpleNamespace(search_term=query)
    row.campaign = SimpleNamespace(id=campaign_id, name="Campaign")
    row.segments = SimpleNamespace(
        conversion_action_name=action_name,
        conversion_action=f"customers/4021070209/conversionActions/{campaign_id}",
    )
    row.metrics = SimpleNamespace(
        all_conversions=all_conversions,
        conversions=conversions,
    )
    return row


def test_fetch_search_term_conversion_breakdown_groups_by_query_and_campaign():
    from engine.ads_client import fetch_search_term_conversion_breakdown

    service = MagicMock()
    service.search.return_value = [
        _breakdown_row("el texano merida", 111, "Local actions - Directions", all_conversions=1),
        _breakdown_row("el texano merida", 111, "Store visits", all_conversions=2),
    ]
    client = MagicMock()
    client.get_service.return_value = service

    result = fetch_search_term_conversion_breakdown(client, "4021070209", "LAST_7_DAYS")

    key = ("el texano merida", "111")
    assert key in result
    assert len(result[key]["actions"]) == 2
    assert result[key]["all_conversions"] == 3
    assert "segments.conversion_action_name" in service.search.call_args.kwargs["query"]
    assert "segments.conversion_action" in service.search.call_args.kwargs["query"]
    assert "metrics.all_conversions" in service.search.call_args.kwargs["query"]
    assert "metrics.conversions" in service.search.call_args.kwargs["query"]


def test_fetch_search_term_conversion_breakdown_failure_returns_none():
    from engine.ads_client import fetch_search_term_conversion_breakdown

    service = MagicMock()
    service.search.side_effect = RuntimeError("unsupported segment")
    client = MagicMock()
    client.get_service.return_value = service

    assert fetch_search_term_conversion_breakdown(client, "4021070209", "LAST_7_DAYS") is None


def _setup_search_terms_endpoint(monkeypatch, terms, breakdown):
    import routes.analysis as analysis

    engine = {
        "get_ads_client": lambda: MagicMock(),
        "fetch_search_term_data": MagicMock(return_value=terms),
    }
    monkeypatch.setattr(analysis, "_get_engine", lambda: engine)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "fetch_negative_keywords", lambda c, cid: {})
    monkeypatch.setattr(analysis, "aggregate_windows", lambda norms: {})
    monkeypatch.setattr(analysis, "accumulated_reds", lambda today_top100_norms: [])
    monkeypatch.setattr(analysis, "fetch_search_term_conversion_breakdown", lambda c, cid, dr: breakdown)


def test_search_terms_uses_breakdown_for_conversion_quality(monkeypatch):
    terms = [
        {"query": "comida tailandesa merida", "campaign_id": "111", "campaign_name": "Search",
         "cost_micros": 5_000_000, "conversions": 1.0, "all_conversions": 1.0,
         "clicks": 5, "impressions": 50},
        {"query": "el texano merida", "campaign_id": "222", "campaign_name": "Local",
         "cost_micros": 4_000_000, "conversions": 0.0, "all_conversions": 1.0,
         "clicks": 4, "impressions": 40},
    ]
    breakdown = {
        ("comida tailandesa merida", "111"): {
            "actions": [{"name": "Pedido GloriaFood Online", "conversions": 1, "all_conversions": 1}],
            "conversions": 1,
            "all_conversions": 1,
        },
        ("el texano merida", "222"): {
            "actions": [{"name": "Local actions - Directions", "conversions": 0, "all_conversions": 1}],
            "conversions": 0,
            "all_conversions": 1,
        },
    }
    _setup_search_terms_endpoint(monkeypatch, terms, breakdown)

    from main import app
    response = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS")

    by_query = {t["query"]: t for t in response.json()["search_terms"]}
    assert by_query["comida tailandesa merida"]["conversion_quality"] == "money_action"
    assert by_query["el texano merida"]["conversion_quality"] == "weak_local_action"
    assert by_query["el texano merida"]["negative_allowed"] is False


def test_search_terms_degrades_to_unknown_when_segmented_query_fails(monkeypatch):
    terms = [
        {"query": "con conversion", "campaign_id": "111", "campaign_name": "Search",
         "cost_micros": 5_000_000, "conversions": 1.0, "all_conversions": 1.0,
         "clicks": 5, "impressions": 50},
        {"query": "sin conversion", "campaign_id": "222", "campaign_name": "Search",
         "cost_micros": 4_000_000, "conversions": 0.0, "all_conversions": 0.0,
         "clicks": 4, "impressions": 40},
    ]
    _setup_search_terms_endpoint(monkeypatch, terms, None)

    from main import app
    response = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS")

    by_query = {t["query"]: t for t in response.json()["search_terms"]}
    assert by_query["con conversion"]["conversion_quality"] == "unknown"
    assert by_query["sin conversion"]["conversion_quality"] == "none"
    assert all(t["negative_allowed"] is False for t in by_query.values())
