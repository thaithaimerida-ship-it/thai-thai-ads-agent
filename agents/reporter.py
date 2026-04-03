"""
Sub-agente Reportero — Genera reportes y dashboards.
Produce reportes diarios/semanales y alimenta Streamlit.
"""
from datetime import datetime


class Reporter:
    """Genera reportes y dashboards."""

    def generate_daily_summary(self, audit_data: dict, analysis: dict) -> dict:
        """Genera resumen diario."""
        campaigns = audit_data.get("campaigns", [])
        total_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns)
        total_conversions = sum(float(c.get("conversions", 0)) for c in campaigns)
        avg_cpa = total_spend / total_conversions if total_conversions > 0 else 0

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "metrics": {
                "spend": round(total_spend, 2),
                "conversions": round(total_conversions, 1),
                "cpa": round(avg_cpa, 2),
            },
            "analysis_summary": analysis.get("executive_summary", {}),
            "proposals": analysis.get("proposals", []),
        }

    def generate_weekly_report(self, daily_summaries: list) -> dict:
        """Genera reporte semanal a partir de resúmenes diarios."""
        # TODO: Implementar agregación semanal
        pass
