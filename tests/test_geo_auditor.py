"""
Thai Thai Ads Agent — Tests de Fase GEO: Auditoría de Geotargeting

Bloque 1 — Modelo de tres estados (detect_geo_issues):
  api_state   — lectura de campaign_criterion
  ui_state    — siempre "unknown" (solo un humano puede confirmar)
  final_operational_state — "verified" | "unverified" | "geo_issue"

Bloque 2 — Auditoría por política de objetivo (detect_geo_issues_by_policy):
  Cada campaña se evalúa contra su política esperada por objetivo de negocio.
  Señales adicionales:
    WRONG_TYPE_LOC_FOR_PROX  — tiene LOCATION pero política esperaba PROXIMITY
    WRONG_TYPE_PROX_FOR_LOC  — tiene PROXIMITY pero política esperaba LOCATION
    PROX_RADIUS_EXCEEDED     — PROXIMITY con radio > max_radius_km
    POLICY_UNDEFINED         — campaña sin política asignada

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_geo_auditor.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.geo_auditor import detect_geo_issues, detect_geo_issues_by_policy

MERIDA_ID = "1010205"
ALLOWED   = {MERIDA_ID}

MERIDA_LAT = 20.9674
MERIDA_LNG = -89.5926

DELIVERY_POLICY = {
    "objective_type":          "DELIVERY",
    "expected_targeting_type": "PROXIMITY",
    "max_radius_km":           8.0,
    "expected_center_lat":     MERIDA_LAT,
    "expected_center_lng":     MERIDA_LNG,
    "allowed_location_ids":    set(),
    "ui_validation_required":  False,
    "autofix_allowed":         True,
}

RESERVACIONES_POLICY = {
    "objective_type":          "RESERVACIONES",
    "expected_targeting_type": "LOCATION",
    "max_radius_km":           None,
    "expected_center_lat":     None,
    "expected_center_lng":     None,
    "allowed_location_ids":    {"1010205"},
    "ui_validation_required":  False,
    "autofix_allowed":         True,
}

LOCAL_POLICY = {
    "objective_type":          "LOCAL_DISCOVERY",
    "expected_targeting_type": None,
    "max_radius_km":           None,
    "expected_center_lat":     None,
    "expected_center_lng":     None,
    "allowed_location_ids":    set(),
    "ui_validation_required":  True,
    "autofix_allowed":         False,
}


def _entry(campaign_id="111", campaign_name="Thai Test", channel_type="SEARCH",
           location_ids=None, has_proximity=False,
           proximity_radius_km=None, proximity_center_lat=None, proximity_center_lng=None):
    return {
        campaign_id: {
            "campaign_id":              campaign_id,
            "campaign_name":            campaign_name,
            "advertising_channel_type": channel_type,
            "location_ids":             location_ids if location_ids is not None else [],
            "criteria_resource_names":  [],
            "has_proximity":            has_proximity,
            "proximity_radius_km":      proximity_radius_km,
            "proximity_center_lat":     proximity_center_lat,
            "proximity_center_lng":     proximity_center_lng,
        }
    }


# ── Estructura del retorno ────────────────────────────────────────────────────

def test_return_has_issues_and_correct_keys():
    result = detect_geo_issues({}, ALLOWED)
    assert "issues"  in result
    assert "correct" in result
    assert isinstance(result["issues"],  list)
    assert isinstance(result["correct"], list)


# ── Campañas SEARCH ───────────────────────────────────────────────────────────

def test_search_merida_verified():
    """SEARCH con Mérida → correct, api_state=correct, final=verified."""
    result = detect_geo_issues(_entry(location_ids=[MERIDA_ID]), ALLOWED)
    assert result["issues"] == []
    c = result["correct"][0]
    assert c["signal"]                  == "OK"
    assert c["api_state"]               == "correct"
    assert c["ui_state"]                == "unknown"
    assert c["final_operational_state"] == "verified"


def test_search_wrong_location_geo1():
    """SEARCH con ubicación incorrecta → GEO1, final=geo_issue."""
    result = detect_geo_issues(_entry(location_ids=["9999"]), ALLOWED)
    i = result["issues"][0]
    assert i["signal"]                  == "GEO1"
    assert i["api_state"]               == "geo1_incorrect"
    assert i["final_operational_state"] == "geo_issue"
    assert "9999" in i["disallowed_location_ids"]


def test_search_no_geo_geo0():
    """SEARCH sin ubicación → GEO0, final=geo_issue."""
    result = detect_geo_issues(_entry(location_ids=[]), ALLOWED)
    i = result["issues"][0]
    assert i["signal"]                  == "GEO0"
    assert i["api_state"]               == "geo0_no_restriction"
    assert i["final_operational_state"] == "geo_issue"


def test_merida_plus_wrong_is_geo1():
    """Mérida + incorrecto → GEO1 (no GEO0)."""
    result = detect_geo_issues(_entry(location_ids=[MERIDA_ID, "8888"]), ALLOWED)
    i = result["issues"][0]
    assert i["signal"] == "GEO1"
    assert "8888" in i["disallowed_location_ids"]


# ── Campañas SMART ────────────────────────────────────────────────────────────

def test_smart_correct_api_unverified():
    """SMART con Mérida por API → correct pero final=unverified (no verified)."""
    result = detect_geo_issues(_entry(channel_type="SMART", location_ids=[MERIDA_ID]), ALLOWED)
    assert result["issues"] == []
    c = result["correct"][0]
    assert c["signal"]                  == "OK"
    assert c["api_state"]               == "correct"
    assert c["ui_state"]                == "unknown"
    assert c["final_operational_state"] == "unverified"   # NUNCA "verified" para SMART
    assert "unverified" in c["reason"]


def test_smart_no_location_geo0_geo_issue():
    """SMART sin location_id → GEO0, final=geo_issue."""
    result = detect_geo_issues(_entry(channel_type="SMART", location_ids=[]), ALLOWED)
    i = result["issues"][0]
    assert i["signal"]                  == "GEO0"
    assert i["final_operational_state"] == "geo_issue"


def test_smart_proximity_only_geo0():
    """SMART con solo PROXIMITY → GEO0, has_proximity=True."""
    result = detect_geo_issues(_entry(channel_type="SMART", location_ids=[], has_proximity=True), ALLOWED)
    i = result["issues"][0]
    assert i["signal"]       == "GEO0"
    assert i["has_proximity"] is True
    assert "PROXIMITY" in i["reason"]


def test_smart_geo1_has_smart_note():
    """SMART con GEO1 → reason debe mencionar UI Express."""
    result = detect_geo_issues(_entry(channel_type="SMART", location_ids=["9999"]), ALLOWED)
    i = result["issues"][0]
    assert i["signal"] == "GEO1"
    assert "Express" in i["reason"] or "SMART" in i["reason"]


# ── Tipos excluidos ───────────────────────────────────────────────────────────

def test_performance_max_excluded():
    result = detect_geo_issues(_entry(channel_type="PERFORMANCE_MAX", location_ids=["9999"]), ALLOWED)
    assert result["issues"]  == []
    assert result["correct"] == []


def test_local_services_excluded():
    result = detect_geo_issues(_entry(channel_type="LOCAL_SERVICES", location_ids=[]), ALLOWED)
    assert result["issues"]  == []
    assert result["correct"] == []


# ── ui_state siempre "unknown" desde la función pura ─────────────────────────

def test_ui_state_always_unknown_from_pure_function():
    """ui_state nunca puede ser 'correct' o 'incorrect' desde detect_geo_issues solo."""
    data = {
        "1": {**_entry("1", channel_type="SEARCH", location_ids=[MERIDA_ID])["1"]},
        "2": {**_entry("2", channel_type="SMART",  location_ids=[MERIDA_ID])["2"]},
        "3": {**_entry("3", channel_type="SEARCH", location_ids=["9999"])["3"]},
    }
    result = detect_geo_issues(data, ALLOWED)
    all_entries = result["issues"] + result["correct"]
    for e in all_entries:
        assert e["ui_state"] == "unknown", (
            f"ui_state debe ser siempre 'unknown' en la funcion pura, "
            f"campana {e['campaign_id']} devolvio '{e['ui_state']}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — Auditoría por política de objetivo (detect_geo_issues_by_policy)
# ═══════════════════════════════════════════════════════════════════════════════

def _policy_entry(campaign_id, objective, channel_type="SEARCH", location_ids=None,
                  has_proximity=False, radius_km=None, lat=None, lng=None):
    """Entrada sintética con campos de proximidad para tests de política."""
    return {
        campaign_id: {
            "campaign_id":              campaign_id,
            "campaign_name":            f"Thai Test {objective}",
            "advertising_channel_type": channel_type,
            "location_ids":             location_ids if location_ids is not None else [],
            "criteria_resource_names":  [],
            "has_proximity":            has_proximity,
            "proximity_radius_km":      radius_km,
            "proximity_center_lat":     lat,
            "proximity_center_lng":     lng,
        }
    }


# ── DELIVERY ──────────────────────────────────────────────────────────────────

def test_delivery_proximity_8km_ok():
    """DELIVERY con PROXIMITY 8 km → OK, compliant=True."""
    data = _policy_entry("111", "DELIVERY", channel_type="SMART",
                         has_proximity=True, radius_km=8.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"111": "DELIVERY"}, {"DELIVERY": DELIVERY_POLICY}
    )
    e = result["correct"][0]
    assert e["signal"]    == "OK"
    assert e["compliant"] is True
    assert result["issues"] == []


def test_delivery_proximity_radius_exceeded():
    """DELIVERY con PROXIMITY 30 km → PROX_RADIUS_EXCEEDED, compliant=False."""
    data = _policy_entry("111", "DELIVERY", channel_type="SMART",
                         has_proximity=True, radius_km=30.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"111": "DELIVERY"}, {"DELIVERY": DELIVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "PROX_RADIUS_EXCEEDED"
    assert i["compliant"] is False
    assert "30" in i["reason"] or "8" in i["reason"]


def test_delivery_with_location_wrong_type():
    """DELIVERY con LOCATION → WRONG_TYPE_LOC_FOR_PROX (no debe usar location_id)."""
    data = _policy_entry("111", "DELIVERY", channel_type="SMART",
                         location_ids=["1010205"])
    result = detect_geo_issues_by_policy(
        data, {"111": "DELIVERY"}, {"DELIVERY": DELIVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "WRONG_TYPE_LOC_FOR_PROX"
    assert i["compliant"] is False


def test_delivery_no_geo_geo0():
    """DELIVERY sin PROXIMITY ni LOCATION → GEO0, compliant=False."""
    data = _policy_entry("111", "DELIVERY", channel_type="SMART")
    result = detect_geo_issues_by_policy(
        data, {"111": "DELIVERY"}, {"DELIVERY": DELIVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "GEO0"
    assert i["compliant"] is False


# ── RESERVACIONES ─────────────────────────────────────────────────────────────

def test_reservaciones_location_1010205_ok():
    """RESERVACIONES con LOCATION 1010205 → OK, compliant=True."""
    data = _policy_entry("222", "RESERVACIONES", channel_type="SEARCH",
                         location_ids=["1010205"])
    result = detect_geo_issues_by_policy(
        data, {"222": "RESERVACIONES"}, {"RESERVACIONES": RESERVACIONES_POLICY}
    )
    e = result["correct"][0]
    assert e["signal"]    == "OK"
    assert e["compliant"] is True
    assert result["issues"] == []


def test_reservaciones_wrong_location_geo1():
    """RESERVACIONES con location incorrecto → GEO1, compliant=False."""
    data = _policy_entry("222", "RESERVACIONES", channel_type="SEARCH",
                         location_ids=["9999"])
    result = detect_geo_issues_by_policy(
        data, {"222": "RESERVACIONES"}, {"RESERVACIONES": RESERVACIONES_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "GEO1"
    assert i["compliant"] is False


def test_reservaciones_proximity_wrong_type():
    """RESERVACIONES con solo PROXIMITY → WRONG_TYPE_PROX_FOR_LOC, compliant=False."""
    data = _policy_entry("222", "RESERVACIONES", channel_type="SEARCH",
                         has_proximity=True, radius_km=30.0)
    result = detect_geo_issues_by_policy(
        data, {"222": "RESERVACIONES"}, {"RESERVACIONES": RESERVACIONES_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "WRONG_TYPE_PROX_FOR_LOC"
    assert i["compliant"] is False


def test_reservaciones_no_geo_geo0():
    """RESERVACIONES sin ningún geo → GEO0, compliant=False."""
    data = _policy_entry("222", "RESERVACIONES", channel_type="SEARCH")
    result = detect_geo_issues_by_policy(
        data, {"222": "RESERVACIONES"}, {"RESERVACIONES": RESERVACIONES_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "GEO0"
    assert i["compliant"] is False


# ── POLICY_UNDEFINED ──────────────────────────────────────────────────────────

def test_campaign_without_policy_undefined():
    """Campaña sin política asignada → POLICY_UNDEFINED, autofix_allowed=False."""
    data = _policy_entry("333", "OTRO", channel_type="SEARCH", location_ids=["1010205"])
    result = detect_geo_issues_by_policy(
        data, {},   # sin mapeo de objetivo
        {"DELIVERY": DELIVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]         == "POLICY_UNDEFINED"
    assert i["compliant"]      is False
    assert i["autofix_allowed"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — Política LOCATION_OR_PROXIMITY (LOCAL_DISCOVERY)
# ═══════════════════════════════════════════════════════════════════════════════

LOCAL_DISCOVERY_POLICY = {
    "objective_type":          "LOCAL_DISCOVERY",
    "expected_targeting_type": "LOCATION_OR_PROXIMITY",
    "max_radius_km":           50.0,
    "min_radius_km":           10.0,
    "expected_center_lat":     MERIDA_LAT,
    "expected_center_lng":     MERIDA_LNG,
    "allowed_location_ids":    {"1010205"},
    "ui_validation_required":  True,
    "autofix_allowed":         False,
}


def test_local_discovery_location_ok():
    """LOCAL_DISCOVERY con LOCATION 1010205 → OK, compliant=True."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART",
                         location_ids=["1010205"])
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    e = result["correct"][0]
    assert e["signal"]    == "OK"
    assert e["compliant"] is True
    assert result["issues"] == []


def test_local_discovery_proximity_in_range_ok():
    """LOCAL_DISCOVERY con PROXIMITY 25 km (dentro de 10–50 km) → OK, compliant=True."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART",
                         has_proximity=True, radius_km=25.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    e = result["correct"][0]
    assert e["signal"]    == "OK"
    assert e["compliant"] is True
    assert "Equivalencia funcional" in e["reason"]
    assert result["issues"] == []


def test_local_discovery_proximity_radius_too_small():
    """LOCAL_DISCOVERY con PROXIMITY 5 km (< min 10 km) → PROX_RADIUS_INSUFFICIENT."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART",
                         has_proximity=True, radius_km=5.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "PROX_RADIUS_INSUFFICIENT"
    assert i["compliant"] is False


def test_local_discovery_proximity_radius_exceeded():
    """LOCAL_DISCOVERY con PROXIMITY 60 km (> max 50 km) → PROX_RADIUS_EXCEEDED."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART",
                         has_proximity=True, radius_km=60.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "PROX_RADIUS_EXCEEDED"
    assert i["compliant"] is False


def test_local_discovery_wrong_location_geo1():
    """LOCAL_DISCOVERY con LOCATION incorrecta → GEO1, compliant=False."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SEARCH",
                         location_ids=["9999"])
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "GEO1"
    assert i["compliant"] is False


def test_local_discovery_no_geo_geo0():
    """LOCAL_DISCOVERY sin ningún geo → GEO0, compliant=False."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART")
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    i = result["issues"][0]
    assert i["signal"]    == "GEO0"
    assert i["compliant"] is False


def test_local_discovery_smart_ok_is_unverified_not_verified():
    """LOCAL_DISCOVERY SMART con PROXIMITY OK → final_operational_state='unverified', no 'verified'."""
    data = _policy_entry("333", "LOCAL_DISCOVERY", channel_type="SMART",
                         has_proximity=True, radius_km=25.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"333": "LOCAL_DISCOVERY"}, {"LOCAL_DISCOVERY": LOCAL_DISCOVERY_POLICY}
    )
    e = result["correct"][0]
    assert e["final_operational_state"] == "unverified"
    assert e["ui_state"]                == "unknown"


# ── Estructura del retorno ────────────────────────────────────────────────────

def test_policy_result_has_required_keys():
    """Cada entrada del resultado por política debe tener los campos obligatorios."""
    data = _policy_entry("111", "DELIVERY", channel_type="SMART",
                         has_proximity=True, radius_km=8.0, lat=MERIDA_LAT, lng=MERIDA_LNG)
    result = detect_geo_issues_by_policy(
        data, {"111": "DELIVERY"}, {"DELIVERY": DELIVERY_POLICY}
    )
    e = result["correct"][0]
    for key in ("signal", "compliant", "campaign_id", "campaign_name",
                "advertising_channel_type", "objective_type",
                "api_state", "ui_state", "final_operational_state",
                "autofix_allowed", "ui_validation_required", "reason"):
        assert key in e, f"Falta campo '{key}' en resultado de política"
