"""
Sub-agente Estratega — Analiza y decide.
Recibe datos del Auditor, usa Claude para análisis,
y genera propuestas de acciones.
"""


class Strategist:
    """Analiza datos y genera propuestas de optimización."""

    def analyze(self, audit_data: dict) -> dict:
        """Recibe output del Auditor, retorna análisis + propuestas."""
        from engine.analyzer import analyze_campaign_data
        return analyze_campaign_data(audit_data) or {}

    def detect_waste(self, campaigns, keywords, search_terms) -> dict:
        """Detecta gasto desperdiciado en keywords y campañas."""
        # TODO: Mover lógica de detect_waste() desde main.py aquí
        pass

    def generate_proposals(self, audit_data: dict, waste_data: dict) -> list:
        """Genera propuestas priorizadas de optimización."""
        # TODO: Mover lógica de generate_agent_proposals() desde main.py aquí
        pass
