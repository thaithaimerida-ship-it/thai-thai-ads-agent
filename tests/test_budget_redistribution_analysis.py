import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.budget_optimizer import run_budget_optimization
from engine.email_sender import _build_daily_summary_html


def _campaign(
    *,
    campaign_id: str,
    name: str,
    cost_mxn: float,
    conversions: float,
    daily_budget_mxn: float,
    lost_budget: float = 0.0,
    status: str = "ENABLED",
    channel_type: str = "SEARCH",
):
    return {
        "id": campaign_id,
        "name": name,
        "status": status,
        "channel_type": channel_type,
        "cost_mxn": cost_mxn,
        "conversions": conversions,
        "daily_budget_mxn": daily_budget_mxn,
        "search_budget_lost_impression_share": lost_budget,
    }


def test_run_budget_optimization_returns_analysis_only_redistribution():
    campaigns = [
        _campaign(
            campaign_id="src-1",
            name="Thai Merida - Reservaciones Norte",
            cost_mxn=400.0,
            conversions=2.0,
            daily_budget_mxn=100.0,
        ),
        _campaign(
            campaign_id="dst-1",
            name="Thai Merida - Reservaciones Centro",
            cost_mxn=80.0,
            conversions=4.0,
            daily_budget_mxn=100.0,
            lost_budget=0.40,
        ),
    ]
    audit_result = SimpleNamespace(score=82.0, category_scores={"KW": 82.0})

    result = run_budget_optimization(
        campaigns,
        audit_result=audit_result,
        negocio_data={"comensales_total": 40, "venta_local_total": 6000},
        pedidos_gloriafood_24h=8,
        recent_actions=[],
        monthly_budget_status=None,
    )

    analysis = result["redistribution_analysis"]
    assert analysis["potential_freed_daily_mxn"] == 20.0
    assert analysis["potential_freed_monthly_mxn"] == 600.0
    assert len(analysis["fund_sources"]) == 1
    assert len(analysis["receiver_candidates"]) == 1
    assert len(analysis["allocation_matrix"]) == 1
    assert analysis["fund_sources"][0]["source_action"] == "reduce"
    assert analysis["receiver_candidates"][0]["eligibility_action"] == "scale"
    assert analysis["allocation_matrix"][0]["amount_daily_mxn"] == 20.0
    assert analysis["net_daily_mxn"] == 0.0
    assert "No execution: analysis only" in analysis["guardrails"]


def test_daily_summary_marks_redistribution_analysis_as_non_executable():
    html = _build_daily_summary_html(
        {
            "audit_result": {"score": 80, "grade": "B", "category_scores": {}},
            "ventas_ayer": {},
            "ads_24h": {},
            "monthly_budget_status": {},
            "creative_actions": [],
            "keyword_proposals": [],
            "budget_optimizer": {
                "decisions": [],
                "redistribution": {},
                "redistribution_analysis": {
                    "potential_freed_daily_mxn": 20.0,
                    "potential_freed_monthly_mxn": 600.0,
                    "fund_sources": [
                        {
                            "campaign_name": "Thai Merida - Reservaciones Norte",
                            "freed_daily_mxn": 20.0,
                            "source_action": "reduce",
                        }
                    ],
                    "receiver_candidates": [
                        {
                            "campaign_name": "Thai Merida - Reservaciones Centro",
                            "eligibility_action": "scale",
                            "max_receivable_daily_mxn": 20.0,
                        }
                    ],
                    "allocation_matrix": [
                        {
                            "from_campaign_name": "Thai Merida - Reservaciones Norte",
                            "to_campaign_name": "Thai Merida - Reservaciones Centro",
                            "amount_daily_mxn": 20.0,
                        }
                    ],
                    "net_daily_mxn": 0.0,
                    "notes": ["Propuesta analitica sin mutacion"],
                    "guardrails": ["No execution: analysis only"],
                },
                "executed": [],
                "pedidos_gloriafood_24h": 0,
                "pedidos_gloriafood_detalle": [],
            },
        }
    )

    assert "Redistribucion potencial analizada" in html
    assert "Sin ejecucion automatica" in html
    assert "No cambia presupuestos todavia" in html
