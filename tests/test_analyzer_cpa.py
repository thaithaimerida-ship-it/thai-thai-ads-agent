import sys
sys.path.insert(0, ".")
from engine.analyzer import _get_cpa_targets, _calculate_success_score_v2

def test_delivery_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Delivery")
    assert targets["ideal"] == 25
    assert targets["max"] == 45
    assert targets["critical"] == 80

def test_reservaciones_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Reservaciones")
    assert targets["ideal"] == 50
    assert targets["max"] == 85
    assert targets["critical"] == 120

def test_local_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Local")
    assert targets["ideal"] == 35
    assert targets["max"] == 60
    assert targets["critical"] == 100

def test_delivery_score_excellent():
    score = _calculate_success_score_v2(cpa=20, has_conversions=True, campaign_name="Thai Mérida - Delivery")
    assert score >= 90

def test_reservaciones_score_critical():
    score = _calculate_success_score_v2(cpa=130, has_conversions=True, campaign_name="Thai Mérida - Reservaciones")
    assert score <= 25
