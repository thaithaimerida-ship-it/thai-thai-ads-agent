"""
Sub-agente Auditor — Solo lectura.
Recopila datos de Google Ads, GA4, Sheets, y landing page.
Genera un diagnóstico completo del estado actual.
"""
import os
from datetime import datetime


class Auditor:
    """Lee todas las fuentes de datos y genera un snapshot."""

    def __init__(self):
        self.customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")

    def run_full_audit(self) -> dict:
        """Ejecuta auditoría completa. Retorna dict con todos los datos."""
        from engine.ads_client import get_ads_client, fetch_campaign_data, fetch_keyword_data, fetch_search_term_data
        from engine.normalizer import normalize_google_ads_data

        client = get_ads_client()
        campaigns = fetch_campaign_data(client, self.customer_id)
        keywords = fetch_keyword_data(client, self.customer_id)
        search_terms = fetch_search_term_data(client, self.customer_id)
        normalized = normalize_google_ads_data(campaigns, keywords, search_terms)

        ga4_data = self._fetch_ga4()
        sheets_data = self._fetch_sheets()
        landing_audit = self._fetch_landing_audit(ga4_data)

        return {
            "timestamp": datetime.now().isoformat(),
            "campaigns": campaigns,
            "keywords": keywords,
            "search_terms": search_terms,
            "normalized": normalized,
            "ga4_data": ga4_data,
            "sheets_data": sheets_data,
            "landing_audit": landing_audit,
        }

    def _fetch_ga4(self) -> dict:
        try:
            from engine.ga4_client import fetch_ga4_events_detailed
            return fetch_ga4_events_detailed(days=7)
        except Exception as e:
            print(f"[WARN] GA4 fetch failed: {e}")
            return {}

    def _fetch_sheets(self) -> dict:
        try:
            from engine.sheets_client import fetch_sheets_data
            return fetch_sheets_data(days=7)
        except Exception as e:
            print(f"[WARN] Sheets fetch failed: {e}")
            return {}

    def _fetch_landing_audit(self, ga4_data: dict) -> dict:
        try:
            from engine.landing_page_auditor import get_full_landing_audit
            return get_full_landing_audit(ga4_data)
        except Exception as e:
            print(f"[WARN] Landing audit failed: {e}")
            return {}
