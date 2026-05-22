"""
Regresion Fix #2: add_negative_keyword NUNCA debe propagar una excepcion
ni fallar en silencio. Si el mutate a Google Ads falla, debe devolver
{"status": "error", ...} para que execute_optimization lo reporte como
FALLO (antes: GoogleAdsException no se atrapaba y el endpoint lo marcaba
como "executed").

Justificacion (regla de testing del proyecto): add_negative_keyword
ESCRIBE en Google Ads.
"""
import sys
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from engine.ads_client import add_negative_keyword


def test_add_negative_keyword_exito():
    client = MagicMock()  # mutate no lanza -> exito
    r = add_negative_keyword(client, "4021070209", "23730364039", "pizza merida")
    assert r["status"] == "success"
    assert r["keyword"] == "pizza merida"


def test_add_negative_keyword_no_propaga_y_reporta_error():
    """El mutate falla -> NO propaga, devuelve status=error con el mensaje."""
    svc = MagicMock()
    svc.mutate_campaign_criteria.side_effect = Exception("INVALID_CAMPAIGN_ID")

    client = MagicMock()
    client.get_service.side_effect = (
        lambda name: svc if name == "CampaignCriterionService" else MagicMock()
    )

    r = add_negative_keyword(client, "4021070209", "999", "ramen")
    assert r["status"] == "error"
    assert "INVALID_CAMPAIGN_ID" in r["message"]
