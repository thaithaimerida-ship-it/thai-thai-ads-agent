import sys
sys.path.insert(0, ".")
from unittest.mock import patch, MagicMock
from engine.analyzer import _call_claude_analysis, analyze_campaign_data

def _make_mock_response(json_str):
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json_str
    mock_response.content = [mock_content]
    return mock_response

def test_claude_analysis_returns_dict():
    json_str = '{"summary": {"spend": 100.0, "conversions": 10, "cpa": 10.0, "cpa_real": 12.0, "ctr": 1.5, "conversion_rate": 0.5, "success_index": 80, "success_label": "Bueno", "estimated_waste": 0.0, "alerts_count": 0, "recommended_actions_count": 1}, "executive_summary": {"headline": "Test", "bullets": [], "recommended_focus_today": "Test"}, "business_data": {}, "landing_page": {}, "campaigns": [], "proposals": [], "market_opportunities": [], "alerts": []}'

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        mock_instance.messages.create.return_value = _make_mock_response(json_str)

        data = {
            "campaign_data": [],
            "totals": {
                "calculated_total_spend": 100.0,
                "calculated_total_conversions": 10,
                "calculated_global_cpa": 10.0,
                "calculated_total_ctr": 1.5,
                "calculated_total_conversion_rate": 0.5,
                "calculated_success_index": 80,
                "calculated_success_label": "Bueno"
            }
        }
        result = _call_claude_analysis(data)
        assert isinstance(result, dict)
        assert "summary" in result
        assert result["summary"]["spend"] == 100.0

def test_fallback_when_no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = analyze_campaign_data({"campaign_data": [], "totals": {}})
    assert isinstance(result, dict)
    assert "summary" in result
