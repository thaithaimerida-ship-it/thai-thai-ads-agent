import asyncio
import json

import main


def test_gbp_aggregate_performance_sums_metrics():
    payload = {
        "multiDailyMetricTimeSeries": [
            {
                "dailyMetricTimeSeries": [
                    {
                        "dailyMetric": "CALL_CLICKS",
                        "timeSeries": {
                            "datedValues": [
                                {"value": "2"},
                                {"value": "3"},
                            ]
                        },
                    },
                    {
                        "dailyMetric": "WEBSITE_CLICKS",
                        "timeSeries": {
                            "datedValues": [
                                {"value": "10"},
                                {"value": "5"},
                            ]
                        },
                    },
                ]
            }
        ]
    }

    assert main._gbp_aggregate_performance(payload) == {
        "CALL_CLICKS": 5,
        "WEBSITE_CLICKS": 15,
    }


def test_gbp_performance_success_read_only(monkeypatch):
    monkeypatch.setenv("GBP_LOCATION_ID", "17757029602072738121")
    monkeypatch.setenv("GBP_ACCOUNT_ID", "116182531567733744541")
    monkeypatch.setenv("GBP_LOCATION_TITLE", "Thai Thai")

    monkeypatch.setattr(main, "_gbp_access_token", lambda: "fake-token")

    def fake_get_json(url, token, params=None):
        assert token == "fake-token"
        assert "businessprofileperformance.googleapis.com" in url
        assert "fetchMultiDailyMetricsTimeSeries" in url
        assert "mybusiness.googleapis.com" not in url
        assert "reviews" not in url
        assert "localPosts" not in url
        assert "media" not in url

        param_names = [p[0] for p in (params or [])]
        assert "dailyMetrics" in param_names
        assert "dailyRange.start_date.year" in param_names
        assert "dailyRange.end_date.year" in param_names

        return 200, {
            "multiDailyMetricTimeSeries": [
                {
                    "dailyMetricTimeSeries": [
                        {
                            "dailyMetric": "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
                            "timeSeries": {
                                "datedValues": [
                                    {"value": "100"},
                                    {"value": "50"},
                                ]
                            },
                        },
                        {
                            "dailyMetric": "BUSINESS_DIRECTION_REQUESTS",
                            "timeSeries": {
                                "datedValues": [
                                    {"value": "7"},
                                    {"value": "8"},
                                ]
                            },
                        },
                    ]
                }
            ]
        }

    monkeypatch.setattr(main, "_gbp_get_json", fake_get_json)

    result = asyncio.run(main.gbp_performance(days=30))

    assert result["status"] == "success"
    assert result["source"] == "google_business_profile"
    assert result["read_only"] is True
    assert result["account_id"] == "116182531567733744541"
    assert result["location_id"] == "17757029602072738121"
    assert result["location_title"] == "Thai Thai"
    assert result["metrics"]["BUSINESS_IMPRESSIONS_MOBILE_MAPS"] == 150
    assert result["metrics"]["BUSINESS_DIRECTION_REQUESTS"] == 15

    body = json.dumps(result).lower()
    assert "reviews" not in body
    assert "localposts" not in body
    assert "media" not in body
