"""
Sub-agente Ejecutor — Escribe cambios.
Ejecuta acciones aprobadas en Google Ads API.
Requiere confirmación para acciones críticas.
"""
import os


class Executor:
    """Ejecuta acciones en Google Ads API."""

    def __init__(self):
        self.customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")

    def block_keyword(self, campaign_id: str, keyword: str) -> dict:
        """Agrega keyword negativa a una campaña."""
        from engine.ads_client import get_ads_client, add_negative_keyword
        client = get_ads_client()
        try:
            add_negative_keyword(client, self.customer_id, campaign_id, keyword)
            return {"status": "executed", "action": "block_keyword", "keyword": keyword}
        except Exception as e:
            return {"status": "error", "action": "block_keyword", "error": str(e)}

    def execute_approved(self, actions: list) -> list:
        """Ejecuta una lista de acciones aprobadas."""
        results = []
        for action in actions:
            if action.get("type") == "block_keyword":
                result = self.block_keyword(action["campaign_id"], action["keyword"])
            else:
                result = {"status": "pending", "action": action.get("type"), "manual_required": True}
            results.append(result)
        return results
