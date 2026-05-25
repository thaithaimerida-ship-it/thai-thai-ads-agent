from agents.strategist import Strategist
from routes.analysis import (
    _campaign_effective_conversions,
    _campaign_review_recommendation,
)


def _campaign(
    campaign_id="111",
    name="Thai Merida - Test",
    cost=0.0,
    conversions=0.0,
    all_conversions=0.0,
    **extra,
):
    return {
        "id": campaign_id,
        "name": name,
        "cost_micros": int(cost * 1_000_000),
        "conversions": conversions,
        "all_conversions": all_conversions,
        "clicks": 10,
        "impressions": 100,
        **extra,
    }


def _keyword(
    text="keyword",
    campaign_id="111",
    campaign_name="Thai Merida - Test",
    cost=0.0,
    conversions=0.0,
    conversion_quality="none",
    **extra,
):
    return {
        "text": text,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "cost_micros": int(cost * 1_000_000),
        "conversions": conversions,
        "conversion_quality": conversion_quality,
        "clicks": 5,
        "impressions": 50,
        **extra,
    }


def test_review_spend_does_not_double_count_keyword_inside_campaign_review_item():
    result = Strategist().detect_waste(
        campaigns=[_campaign(cost=181.95, conversions=0)],
        keywords=[_keyword(text='"comida tailandesa merida"', cost=66.48, conversions=0)],
        search_terms=[],
    )

    assert result["summary"]["review_spend_total"] == 181.95
    assert result["summary"]["total_waste"] == 181.95
    assert result["summary"]["review_spend_excluded_nested"] == 1
    assert result["high_priority"][0]["excluded_from_total"] is True


def test_keyword_with_money_action_does_not_enter_review_spend():
    result = Strategist().detect_waste(
        campaigns=[],
        keywords=[
            _keyword(
                text="pedido thai",
                cost=120,
                conversions=1,
                conversion_quality="money_action",
            )
        ],
        search_terms=[],
    )

    assert result["summary"]["review_spend_total"] == 0
    assert result["critical_items"] == []
    assert result["high_priority"] == []
    assert result["moderate"] == []


def test_keyword_with_weak_local_action_enters_soft_review_not_critical():
    result = Strategist().detect_waste(
        campaigns=[],
        keywords=[
            _keyword(
                text="restaurante cerca",
                cost=80,
                conversions=0,
                all_conversions=2,
                conversion_quality="weak_local_action",
            )
        ],
        search_terms=[],
    )

    assert result["summary"]["review_spend_total"] == 80
    assert result["summary"]["high_waste"] == 0
    assert result["moderate"][0]["review_level"] == "soft"
    assert result["moderate"][0]["conversion_quality"] == "weak_local_action"


def test_unknown_marks_tracking_uncertain_and_never_pause_or_block():
    result = Strategist().detect_waste(
        campaigns=[],
        keywords=[
            _keyword(
                text="thai merida",
                cost=90,
                conversions=0,
                all_conversions=3,
                conversion_quality="unknown",
            )
        ],
        search_terms=[],
    )

    item = result["moderate"][0]
    assert result["summary"]["review_spend_total"] == 90
    assert item["review_level"] == "tracking_uncertain"
    assert item["action"] == "review_tracking"


def test_none_with_high_spend_enters_review_spend():
    result = Strategist().detect_waste(
        campaigns=[],
        keywords=[_keyword(text="menu competidor", cost=70, conversions=0, conversion_quality="none")],
        search_terms=[],
    )

    assert result["summary"]["review_spend_total"] == 70
    assert result["summary"]["keywords_to_block"] == 1
    assert result["high_priority"][0]["review_level"] == "no_signal"


def test_yesterday_bad_with_healthy_trends_does_not_recommend_pause():
    rec = _campaign_review_recommendation(
        date_range="YESTERDAY",
        effective_conversions=0,
        spend=76.69,
        min_spend=70,
        trend_7d_status="healthy",
        trend_30d_status="healthy",
    )

    assert "Pausar campaña" not in rec["actions"]
    assert rec["actions"] == ["Monitorear 48–72h", "Revisar términos de búsqueda"]


def test_bad_yesterday_and_bad_trends_recommends_manual_priority_not_auto_pause():
    rec = _campaign_review_recommendation(
        date_range="YESTERDAY",
        effective_conversions=0,
        spend=300,
        min_spend=70,
        trend_7d_status="bad",
        trend_30d_status="bad",
    )

    assert rec["actions"] == ["Revisión manual prioritaria", "Considerar pausa manual"]
    assert "Pausar campaña" not in rec["actions"]


def test_local_and_experiencia_use_all_conversions_where_applicable():
    local = _campaign(
        campaign_id="22612348265",
        name="Thai Merida - Local",
        cost=181.95,
        conversions=0,
        all_conversions=12,
    )
    exp = _campaign(
        campaign_id="23730364039",
        name="Thai Merida - Experiencia 2026",
        cost=165.10,
        conversions=0,
        all_conversions=8,
    )

    assert _campaign_effective_conversions(local) == 12
    assert _campaign_effective_conversions(exp) == 8


def test_delivery_search_prioritizes_money_signal_when_present():
    delivery_search = _campaign(
        campaign_id="23809395983",
        name="Thai Merida - Delivery Search",
        cost=76.69,
        conversions=0,
        all_conversions=5,
        money_action_conversions=1,
    )

    assert _campaign_effective_conversions(delivery_search) == 1


def test_campaign_review_items_do_not_generate_pause_campaign_proposals():
    strategist = Strategist()
    waste_data = strategist.detect_waste(
        campaigns=[_campaign(cost=181.95, conversions=0, all_conversions=0)],
        keywords=[],
        search_terms=[],
    )

    proposals = strategist.generate_proposals(
        campaigns=[],
        keywords=[],
        waste_data=waste_data,
        hour_data={},
        landing_page_data={},
        promotion_data={},
    )

    assert all(p["type"] != "pause_campaign" for p in proposals)
    assert any(p["type"] == "review_campaign" for p in proposals)
