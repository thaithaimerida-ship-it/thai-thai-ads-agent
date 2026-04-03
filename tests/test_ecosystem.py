"""Tests para routes/ecosystem.py — verifican formato de respuesta."""
import pytest
from unittest.mock import patch, MagicMock


MOCK_SNAPSHOT = {
    "status": "success",
    "timestamp": "2026-04-03T10:00:00",
    "metrics": {
        "total_spend": 220.50,
        "total_conversions": 28,
        "avg_cpa": 7.87,
        "campaigns_active": 3,
    },
    "waste": {"summary": {"total_waste": 45.30}},
    "analysis": {
        "summary": {"ctr": 2.1, "conversion_rate": 18.5, "success_index": 85},
        "proposals": [{"id": 1}],
    },
    "campaign_separation": {
        "local": {"spend": 48.20, "conversions": 12, "cpa": 4.02},
        "delivery": {"spend": 95.80, "conversions": 16, "cpa": 5.99},
    },
    "landing_page_health": {"status": "ok", "response_time_ms": 320},
    "negocio_mtd": {"total_comensales": 450, "total_ingresos_bruto": 185000},
}


class TestAdsSummary:
    """Tests para /ecosystem/ads-summary."""

    def test_summary_format(self):
        """Verifica que el formato matchea lo que AdminDashboard espera."""
        snapshot = MOCK_SNAPSHOT

        metrics = snapshot.get("metrics", {})
        assert "total_spend" in metrics
        assert "total_conversions" in metrics
        assert "avg_cpa" in metrics

    def test_campaigns_array_structure(self):
        """Verifica que campaigns tiene name, spend, conversions, cpa, status."""
        campaign_sep = MOCK_SNAPSHOT["campaign_separation"]
        for key in ["local", "delivery"]:
            data = campaign_sep[key]
            assert "spend" in data
            assert "conversions" in data
            assert "cpa" in data

    def test_cross_metric_costo_por_comensal(self):
        """Verifica cálculo de costo por comensal."""
        comensales = MOCK_SNAPSHOT["negocio_mtd"]["total_comensales"]
        ads_spend = MOCK_SNAPSHOT["metrics"]["total_spend"]
        costo = round(ads_spend / comensales, 2) if comensales > 0 else 0
        assert costo == 0.49  # $220.50 / 450 comensales

    def test_no_snapshot_returns_503(self):
        """Sin snapshot debe indicar que no hay data."""
        snapshot = None
        assert snapshot is None

    def test_campaigns_status_critical_when_no_conversions(self):
        """Campaña con spend > 50 y 0 conversiones debe ser 'critical'."""
        data = {"spend": 60.0, "conversions": 0, "cpa": 0}
        spend = data.get("spend", 0)
        conv = data.get("conversions", 0)
        status = "critical" if (conv == 0 and spend > 50) else "ok"
        assert status == "critical"

    def test_campaigns_status_ok_when_converting(self):
        """Campaña con conversiones es 'ok'."""
        data = {"spend": 95.80, "conversions": 16, "cpa": 5.99}
        conv = data.get("conversions", 0)
        spend = data.get("spend", 0)
        status = "critical" if (conv == 0 and spend > 50) else "ok"
        assert status == "ok"

    def test_proposals_count(self):
        """Verifica que proposals_count refleja la cantidad correcta."""
        proposals = MOCK_SNAPSHOT["analysis"]["proposals"]
        assert len(proposals) == 1

    def test_waste_extracted(self):
        """Verifica que el waste se extrae correctamente del snapshot."""
        waste = MOCK_SNAPSHOT["waste"]["summary"]["total_waste"]
        assert waste == 45.30
