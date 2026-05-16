"""
Tests de add_negative_keyword — manejo de errores.

Regresion (bug 16-may-2026): add_negative_keyword solo atrapaba
GoogleAPIError, pero la API de Google Ads lanza GoogleAdsException
(no es subclase). El error se escapaba sin loguear y execute_optimization
lo reportaba como "executed" -> fallos silenciosos. Estas pruebas fijan
el contrato: NUNCA propagar, SIEMPRE devolver dict con status.

Justificacion (regla de testing del proyecto): add_negative_keyword
ESCRIBE en Google Ads.
"""
import sys
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from engine.ads_client import add_negative_keyword


def test_exito_devuelve_status_success():
    client = MagicMock()  # mutate no lanza -> exito
    r = add_negative_keyword(client, "4021070209", "23730364039", "pizza merida")
    assert r["status"] == "success"
    assert r["keyword"] == "pizza merida"


def test_fallo_no_propaga_y_devuelve_status_error():
    """Si mutate falla, NO debe propagar la excepcion: devuelve status=error
    con el mensaje. Esto es lo que permite a execute_optimization NO marcar
    'executed' cuando en realidad fallo."""
    svc = MagicMock()
    svc.mutate_campaign_criteria.side_effect = Exception("INVALID_CAMPAIGN_ID")

    client = MagicMock()
    client.get_service.side_effect = (
        lambda name: svc if name == "CampaignCriterionService" else MagicMock()
    )

    r = add_negative_keyword(client, "4021070209", "999", "ramen merida")
    assert r["status"] == "error"
    assert "INVALID_CAMPAIGN_ID" in r["message"]
