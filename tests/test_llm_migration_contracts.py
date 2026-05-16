from unittest.mock import patch

from agents.builder import generate_campaign_config
from engine.creative_remediation import remediate_weak_ads
from engine.decision_engine import get_budget_decisions, get_keyword_decisions
from engine.email_sender import generate_daily_insight
from engine.smart_campaign_auditor import _evaluate_themes_with_llm


def test_budget_decisions_preserve_validated_output_shape(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    campaigns = [{
        "id": "123",
        "name": "Thai Mérida - Local",
        "cost_micros": 70000000,
        "conversions": 7,
        "daily_budget_mxn": 100,
    }]
    llm_json = """
    {
      "decisions": [
        {
          "action": "scale",
          "campaign_id": "123",
          "campaign_name": "Thai Mérida - Local",
          "new_budget_mxn": 120,
          "change_pct": 20,
          "reason": "Buen rendimiento sostenido",
          "confidence": 82
        }
      ]
    }
    """

    with patch("engine.decision_engine.generate_text", return_value=llm_json):
        result = get_budget_decisions(campaigns, negocio_data={}, ga4_data={})

    assert len(result) == 1
    assert result[0]["action"] == "scale"
    assert result[0]["campaign_id"] == "123"
    assert result[0]["campaign_name"] == "Thai Mérida - Local"
    assert result[0]["new_budget_mxn"] == 120.0
    assert result[0]["change_pct"] == 20.0
    assert result[0]["reason"] == "Buen rendimiento sostenido"
    assert result[0]["confidence"] == 82


def test_keyword_decisions_preserve_validated_output_shape(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    llm_json = """
    {
      "keyword_decisions": [
        {
          "action": "add",
          "campaign_id": "456",
          "ad_group_resource": "customers/1/adGroups/99",
          "keyword_text": "pad thai merida",
          "match_type": "PHRASE",
          "reason": "Alta intención local",
          "confidence": 88
        }
      ]
    }
    """

    with patch("engine.decision_engine.generate_text", return_value=llm_json):
        result = get_keyword_decisions(
            campaigns=[],
            current_keywords=[],
            suggested_keywords=[],
            negocio_data={},
            search_ad_groups=[{
                "campaign_id": "456",
                "campaign_name": "Thai Mérida - Reservaciones",
                "adgroup_resource": "customers/1/adGroups/99",
            }],
        )

    assert result == [{
        "action": "add",
        "campaign_id": "456",
        "ad_group_resource": "customers/1/adGroups/99",
        "keyword_text": "pad thai merida",
        "match_type": "PHRASE",
        "reason": "Alta intención local",
        "confidence": 88,
    }]


def test_creative_remediation_preserves_executor_action_shape(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    llm_json = """
    {
      "new_headlines": ["Pad Thai Mérida", "Reserva en Thai Thai"],
      "new_descriptions": ["Comida tailandesa auténtica en Calle 30 No. 351, Mérida."],
      "reasoning": "Mayor relevancia semántica"
    }
    """

    ad_health_data = [{
        "ad_id": "ad-1",
        "campaign_id": "123",
        "campaign_name": "Thai Mérida - Reservaciones",
        "ad_group_resource": "customers/1/adGroups/1",
        "headlines": ["Thai Thai Mérida"],
        "descriptions": ["Reserva comida thai"],
        "ad_strength": "POOR",
    }]

    with patch("engine.creative_remediation.generate_text", return_value=llm_json):
        result = remediate_weak_ads(ad_health_data, keyword_quality_data=[])

    assert result[0]["action"] == "add_headlines"
    assert result[0]["ad_id"] == "ad-1"
    assert "headlines" in result[0]
    assert result[1]["action"] == "add_descriptions"
    assert "descriptions" in result[1]


def test_daily_insight_returns_single_string_from_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("engine.email_sender.generate_text", return_value="Ayer Ads generó demanda web y apoyo físico con señal mixta de calidad."):
        result = generate_daily_insight(
            ads_data={"spend_mxn": 100, "conversions": 5},
            ga4_data={"click_pedir": 2, "click_reservar": 1, "page_views": 20},
            sheets_data={"comensales_total": 35, "venta_local_total": 5000},
        )

    assert isinstance(result, str)
    assert "Ads" in result


def test_builder_keeps_fallback_behavior_between_primary_and_fast_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    valid_json = """
    {
      "campaign_name": "Thai Mérida - Promo",
      "daily_budget_mxn": 80,
      "cpc_bid_mxn": 20,
      "landing_url": "https://www.thaithaimerida.com",
      "geo_targeting": {"lat": 20.9674, "lng": -89.5926, "radius_km": 15},
      "ad_groups": [
        {
          "name": "Promo",
          "headlines": ["Thai Thai Mérida", "Reserva Hoy", "Pad Thai Mérida"],
          "descriptions": ["Desc 1", "Desc 2"],
          "keywords": [{"text": "pad thai merida", "match_type": "PHRASE"}]
        }
      ],
      "negative_keywords": ["receta", "sushi", "gratis", "empleo", "china"]
    }
    """

    with patch("agents.builder.generate_text", side_effect=["{bad json", valid_json]):
        result = generate_campaign_config("Campaña para reservaciones")

    assert result["status"] == "success"
    assert result["config"]["_generated_by"] == "Haiku"


def test_smart_theme_evaluation_preserves_list_contract(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("engine.smart_campaign_auditor.generate_text", return_value='["trabajo restaurante", "receta pad thai"]'):
        result = _evaluate_themes_with_llm(["trabajo restaurante", "receta pad thai", "cenar merida"])

    assert result == ["trabajo restaurante", "receta pad thai"]
