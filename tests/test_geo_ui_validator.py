"""
Thai Thai Ads Agent — Tests de geo_ui_validator

Bloque 1 — apply_ui_validations (sin snapshot):
  - Eleva "unverified" → "verified" cuando corresponde
  - No eleva si ui_validated_by_human=False
  - No eleva si ui_state != "correct"
  - No modifica entradas en "issues"
  - No modifica si no hay validación para la campaña
  - Función pura (no altera dicts originales)
  - Múltiples campañas, solo la validada se eleva

Bloque 2 — Detección de validaciones stale:
  - Stale cuando cambia targeting_type
  - Stale cuando cambian location_ids
  - Stale cuando el radio excede la tolerancia (0.5 km)
  - Stale cuando el centro se desplaza más de la tolerancia (~111m)
  - Stale cuando cambia objective_type
  - No stale cuando la diferencia está dentro de tolerancia
  - Sin geo_criteria → sin verificación de staleness (backward compat)
  - Entrada stale marcada con ui_validation_stale=True y permanece unverified

Bloque 3 — Helpers internos:
  - _build_geo_snapshot
  - _snapshot_matches con varios escenarios

Bloque 4 — load/save:
  - load devuelve {} si no existe
  - save con geo_snapshot + round-trip
  - save actualiza registro existente

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_geo_ui_validator.py -v
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.geo_ui_validator import (
    apply_ui_validations,
    load_ui_validations,
    save_ui_validation,
    _build_geo_snapshot,
    _snapshot_matches,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_correct_entry(campaign_id: str, final_state: str, channel_type: str = "SMART") -> dict:
    return {
        "signal": "OK",
        "compliant": True,
        "campaign_id": campaign_id,
        "campaign_name": f"Campaña {campaign_id}",
        "advertising_channel_type": channel_type,
        "objective_type": "LOCAL_DISCOVERY",
        "api_state": "correct",
        "ui_state": "unknown",
        "final_operational_state": final_state,
        "autofix_allowed": False,
        "ui_validation_required": True,
        "reason": "OK",
    }


def _make_issue_entry(campaign_id: str) -> dict:
    return {
        "signal": "GEO1",
        "compliant": False,
        "campaign_id": campaign_id,
        "campaign_name": f"Campaña {campaign_id}",
        "advertising_channel_type": "SMART",
        "objective_type": "LOCAL_DISCOVERY",
        "api_state": "geo_issue",
        "ui_state": "unknown",
        "final_operational_state": "geo_issue",
        "autofix_allowed": False,
        "ui_validation_required": True,
        "reason": "GEO1 error",
    }


def _make_validation(
    campaign_id: str,
    ui_state: str = "correct",
    validated: bool = True,
    geo_snapshot: dict | None = None,
) -> dict:
    v = {
        "campaign_id": campaign_id,
        "campaign_name": f"Campaña {campaign_id}",
        "ui_state": ui_state,
        "ui_validated_by_human": validated,
        "ui_validated_at": "2026-03-27T00:00:00",
        "ui_validation_source": "manual_session_confirmation",
        "notes": "",
    }
    if geo_snapshot is not None:
        v["geo_snapshot"] = geo_snapshot
    return v


def _make_geo_criteria_entry(
    campaign_id: str,
    location_ids: list | None = None,
    has_proximity: bool = True,
    proximity_radius_km: float = 25.0,
    proximity_center_lat: float = 21.008851,
    proximity_center_lng: float = -89.612562,
) -> dict:
    """Simula una entrada de fetch_campaign_geo_criteria()."""
    return {
        "campaign_id": campaign_id,
        "campaign_name": f"Campaña {campaign_id}",
        "advertising_channel_type": "SMART",
        "location_ids": location_ids or [],
        "criteria_resource_names": [],
        "has_proximity": has_proximity,
        "proximity_radius_km": proximity_radius_km if has_proximity else None,
        "proximity_center_lat": proximity_center_lat if has_proximity else None,
        "proximity_center_lng": proximity_center_lng if has_proximity else None,
    }


# Snapshot base de referencia para "Thai Mérida - Local" tal como fue validado
_SNAPSHOT_PROX_25 = {
    "targeting_type": "PROXIMITY",
    "location_ids": [],
    "proximity_radius_km": 25.0,
    "proximity_center_lat": 21.008851,
    "proximity_center_lng": -89.612562,
    "objective_type": "LOCAL_DISCOVERY",
}


# ─── Tests: apply_ui_validations ─────────────────────────────────────────────

def test_unverified_smart_con_validacion_correcta_se_eleva_a_verified():
    """SMART unverified + validación human=True/correct → verified."""
    entry = _make_correct_entry("111", "unverified")
    validations = {"111": _make_validation("111")}

    result = apply_ui_validations({"correct": [entry], "issues": []}, validations)

    assert result["correct"][0]["final_operational_state"] == "verified"
    assert result["correct"][0]["ui_state"] == "correct"
    assert result["correct"][0]["ui_validated_by_human"] is True


def test_unverified_sin_validacion_permanece_unverified():
    """SMART unverified sin entrada en ui_validations → no cambia."""
    entry = _make_correct_entry("222", "unverified")

    result = apply_ui_validations({"correct": [entry], "issues": []}, {})

    assert result["correct"][0]["final_operational_state"] == "unverified"
    assert result["correct"][0]["ui_state"] == "unknown"


def test_validacion_no_humana_no_eleva():
    """ui_validated_by_human=False → no eleva."""
    entry = _make_correct_entry("333", "unverified")
    validations = {"333": _make_validation("333", validated=False)}

    result = apply_ui_validations({"correct": [entry], "issues": []}, validations)

    assert result["correct"][0]["final_operational_state"] == "unverified"


def test_validacion_ui_state_incorrecto_no_eleva():
    """ui_state='incorrect:Cancún' → no eleva aunque validated=True."""
    entry = _make_correct_entry("444", "unverified")
    validations = {"444": _make_validation("444", ui_state="incorrect:Cancún")}

    result = apply_ui_validations({"correct": [entry], "issues": []}, validations)

    assert result["correct"][0]["final_operational_state"] == "unverified"


def test_issues_nunca_se_modifican():
    """Entradas en 'issues' no se tocan, aunque haya validación para ese campaign_id."""
    issue = _make_issue_entry("555")
    validations = {"555": _make_validation("555")}

    result = apply_ui_validations({"correct": [], "issues": [issue]}, validations)

    assert result["issues"][0]["final_operational_state"] == "geo_issue"
    assert result["issues"][0]["ui_state"] == "unknown"


def test_ya_verified_no_se_modifica():
    """Entrada ya verified (no-SMART) no debe cambiar."""
    entry = _make_correct_entry("666", "verified", channel_type="SEARCH")

    result = apply_ui_validations({"correct": [entry], "issues": []}, {})

    assert result["correct"][0]["final_operational_state"] == "verified"
    # No debe tener campos de validación inyectados
    assert "ui_validated_by_human" not in result["correct"][0]


def test_no_modifica_dict_original():
    """Función pura: el dict original no debe mutar."""
    entry = _make_correct_entry("777", "unverified")
    original_state = entry["final_operational_state"]
    policy_result = {"correct": [entry], "issues": []}
    validations = {"777": _make_validation("777")}

    apply_ui_validations(policy_result, validations)

    # El entry original no debe haberse modificado
    assert entry["final_operational_state"] == original_state
    assert entry["ui_state"] == "unknown"


def test_multiples_campanas_solo_validada_se_eleva():
    """Con dos SMART, solo la que tiene validación humana se eleva."""
    e1 = _make_correct_entry("AAA", "unverified")
    e2 = _make_correct_entry("BBB", "unverified")
    validations = {"AAA": _make_validation("AAA")}  # solo AAA

    result = apply_ui_validations({"correct": [e1, e2], "issues": []}, validations)

    states = {e["campaign_id"]: e["final_operational_state"] for e in result["correct"]}
    assert states["AAA"] == "verified"
    assert states["BBB"] == "unverified"


def test_resultado_contiene_claves_issues_y_correct():
    """El resultado siempre tiene las claves 'issues' y 'correct'."""
    result = apply_ui_validations({"correct": [], "issues": []}, {})

    assert "issues" in result
    assert "correct" in result


# ─── Tests: load_ui_validations ──────────────────────────────────────────────

def test_load_devuelve_vacio_si_archivo_no_existe():
    resultado = load_ui_validations("/ruta/inexistente/geo_ui_validations.json")
    assert resultado == {}


# ─── Tests: save_ui_validation + load round-trip ─────────────────────────────

def test_save_y_load_round_trip():
    """Guardar una validación y leerla de vuelta produce los mismos campos clave."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
        tf.write("{}")
        tmppath = tf.name

    try:
        save_ui_validation(
            campaign_id="99999",
            campaign_name="Test Camp",
            ui_state="correct",
            source="test_suite",
            notes="Nota de prueba",
            path=tmppath,
        )

        loaded = load_ui_validations(tmppath)

        assert "99999" in loaded
        v = loaded["99999"]
        assert v["ui_state"] == "correct"
        assert v["ui_validated_by_human"] is True
        assert v["ui_validation_source"] == "test_suite"
        assert v["notes"] == "Nota de prueba"
        assert "ui_validated_at" in v
    finally:
        os.unlink(tmppath)


def test_save_actualiza_registro_existente():
    """save_ui_validation sobre un campaign_id ya existente lo sobreescribe."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
        json.dump({"99999": {"ui_state": "incorrect:Cancún", "ui_validated_by_human": True,
                              "ui_validated_at": "2026-01-01T00:00:00",
                              "ui_validation_source": "old_source", "notes": "",
                              "campaign_id": "99999", "campaign_name": "Test"}}, tf)
        tmppath = tf.name

    try:
        save_ui_validation(
            campaign_id="99999",
            campaign_name="Test Camp",
            ui_state="correct",
            source="corrected_source",
            path=tmppath,
        )

        loaded = load_ui_validations(tmppath)
        assert loaded["99999"]["ui_state"] == "correct"
        assert loaded["99999"]["ui_validation_source"] == "corrected_source"
    finally:
        os.unlink(tmppath)


def test_save_persiste_geo_snapshot():
    """save_ui_validation guarda geo_snapshot y se recupera en load."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tf:
        tf.write("{}")
        tmppath = tf.name

    snap = _SNAPSHOT_PROX_25.copy()
    try:
        save_ui_validation(
            campaign_id="88888",
            campaign_name="Test Snap",
            ui_state="correct",
            source="test",
            geo_snapshot=snap,
            path=tmppath,
        )
        loaded = load_ui_validations(tmppath)
        assert loaded["88888"]["geo_snapshot"] == snap
    finally:
        os.unlink(tmppath)


# ─── Tests: _build_geo_snapshot ──────────────────────────────────────────────

def test_build_geo_snapshot_proximity():
    """Criteria con PROXIMITY → targeting_type='PROXIMITY', location_ids=[]."""
    criteria_entry = _make_geo_criteria_entry("X", location_ids=[], has_proximity=True,
                                              proximity_radius_km=25.0,
                                              proximity_center_lat=21.008851,
                                              proximity_center_lng=-89.612562)
    snap = _build_geo_snapshot(criteria_entry, "LOCAL_DISCOVERY")

    assert snap["targeting_type"] == "PROXIMITY"
    assert snap["location_ids"] == []
    assert snap["proximity_radius_km"] == 25.0
    assert snap["proximity_center_lat"] == 21.008851
    assert snap["objective_type"] == "LOCAL_DISCOVERY"


def test_build_geo_snapshot_location():
    """Criteria con LOCATION → targeting_type='LOCATION'."""
    criteria_entry = _make_geo_criteria_entry("X", location_ids=["1010205"], has_proximity=False)
    snap = _build_geo_snapshot(criteria_entry, "RESERVACIONES")

    assert snap["targeting_type"] == "LOCATION"
    assert snap["location_ids"] == ["1010205"]
    assert snap["proximity_radius_km"] is None


def test_build_geo_snapshot_none():
    """Sin geo → targeting_type='NONE'."""
    criteria_entry = _make_geo_criteria_entry("X", location_ids=[], has_proximity=False)
    snap = _build_geo_snapshot(criteria_entry, "DELIVERY")

    assert snap["targeting_type"] == "NONE"


# ─── Tests: _snapshot_matches ────────────────────────────────────────────────

def test_snapshot_matches_exact():
    """Snapshot idéntico → coincide."""
    assert _snapshot_matches(_SNAPSHOT_PROX_25, _SNAPSHOT_PROX_25) is True


def test_snapshot_not_matches_type_change():
    """Targeting type diferente → no coincide."""
    current = {**_SNAPSHOT_PROX_25, "targeting_type": "LOCATION", "location_ids": ["1010205"]}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is False


def test_snapshot_not_matches_location_ids_change():
    """Location IDs diferentes → no coincide."""
    stored = {**_SNAPSHOT_PROX_25, "targeting_type": "LOCATION", "location_ids": ["1010205"]}
    current = {**stored, "location_ids": ["9999999"]}
    assert _snapshot_matches(stored, current) is False


def test_snapshot_matches_within_radius_tolerance():
    """Radio difiere 0.3 km (< 0.5 tolerancia) → coincide."""
    current = {**_SNAPSHOT_PROX_25, "proximity_radius_km": 25.3}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is True


def test_snapshot_not_matches_radius_beyond_tolerance():
    """Radio difiere 5 km (> 0.5 tolerancia) → no coincide."""
    current = {**_SNAPSHOT_PROX_25, "proximity_radius_km": 30.0}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is False


def test_snapshot_matches_within_center_tolerance():
    """Centro desplazado 0.0001 grados (<0.001 tolerancia) → coincide."""
    current = {**_SNAPSHOT_PROX_25,
               "proximity_center_lat": 21.008851 + 0.0001,
               "proximity_center_lng": -89.612562 + 0.0001}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is True


def test_snapshot_not_matches_center_beyond_tolerance():
    """Centro desplazado 0.002 grados (>0.001 tolerancia) → no coincide."""
    current = {**_SNAPSHOT_PROX_25, "proximity_center_lat": 21.008851 + 0.002}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is False


def test_snapshot_not_matches_objective_type_change():
    """Objective type diferente → no coincide."""
    current = {**_SNAPSHOT_PROX_25, "objective_type": "DELIVERY"}
    assert _snapshot_matches(_SNAPSHOT_PROX_25, current) is False


# ─── Tests: staleness en apply_ui_validations ────────────────────────────────

def _make_geo_criteria_dict(campaign_id: str, **kwargs) -> dict:
    """Envuelve _make_geo_criteria_entry en un dict keyed by campaign_id."""
    return {campaign_id: _make_geo_criteria_entry(campaign_id, **kwargs)}


def test_stale_when_targeting_type_changes():
    """Validación guardada como PROXIMITY, actual es LOCATION → stale, unverified."""
    entry = _make_correct_entry("CID1", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()  # targeting_type=PROXIMITY
    val = _make_validation("CID1", geo_snapshot=snap)
    # geo_criteria actual: LOCATION en vez de PROXIMITY
    geo_criteria = {"CID1": _make_geo_criteria_entry("CID1", location_ids=["1010205"], has_proximity=False)}

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID1": val}, geo_criteria)

    e = result["correct"][0]
    assert e["final_operational_state"] == "unverified"
    assert e.get("ui_validation_stale") is True


def test_stale_when_radius_changes_beyond_tolerance():
    """Radio cambió de 25 → 35 km (>0.5 km tolerancia) → stale."""
    entry = _make_correct_entry("CID2", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()  # radius=25
    val = _make_validation("CID2", geo_snapshot=snap)
    geo_criteria = {"CID2": _make_geo_criteria_entry("CID2", proximity_radius_km=35.0)}

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID2": val}, geo_criteria)

    assert result["correct"][0]["final_operational_state"] == "unverified"
    assert result["correct"][0].get("ui_validation_stale") is True


def test_stale_when_center_moves_beyond_tolerance():
    """Centro desplazado >0.001 grados → stale."""
    entry = _make_correct_entry("CID3", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()
    val = _make_validation("CID3", geo_snapshot=snap)
    geo_criteria = {"CID3": _make_geo_criteria_entry("CID3", proximity_center_lat=21.015)}  # +0.006 grados

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID3": val}, geo_criteria)

    assert result["correct"][0]["final_operational_state"] == "unverified"
    assert result["correct"][0].get("ui_validation_stale") is True


def test_stale_when_objective_type_changes():
    """Policy cambió de LOCAL_DISCOVERY → DELIVERY → stale."""
    entry = _make_correct_entry("CID4", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()  # objective_type=LOCAL_DISCOVERY
    val = _make_validation("CID4", geo_snapshot=snap)
    geo_criteria = {"CID4": _make_geo_criteria_entry("CID4")}
    # El entry tiene objective_type LOCAL_DISCOVERY, snap tiene LOCAL_DISCOVERY → no stale por eso.
    # Para stale por objective: modificar el entry para que su objective no coincida con snap.
    entry["objective_type"] = "DELIVERY"

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID4": val}, geo_criteria)

    assert result["correct"][0]["final_operational_state"] == "unverified"
    assert result["correct"][0].get("ui_validation_stale") is True


def test_not_stale_when_geo_matches_snapshot():
    """Geo actual coincide exactamente con snapshot → se eleva a verified."""
    entry = _make_correct_entry("CID5", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()
    val = _make_validation("CID5", geo_snapshot=snap)
    # geo_criteria igual al snapshot
    geo_criteria = {"CID5": _make_geo_criteria_entry("CID5",
                    location_ids=[], has_proximity=True,
                    proximity_radius_km=25.0,
                    proximity_center_lat=21.008851,
                    proximity_center_lng=-89.612562)}

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID5": val}, geo_criteria)

    e = result["correct"][0]
    assert e["final_operational_state"] == "verified"
    assert e.get("ui_validation_stale") is None


def test_no_geo_criteria_skips_staleness_check():
    """Sin geo_criteria → no se evalúa staleness, se eleva normalmente."""
    entry = _make_correct_entry("CID6", "unverified")
    snap = _SNAPSHOT_PROX_25.copy()
    val = _make_validation("CID6", geo_snapshot=snap)

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID6": val}, geo_criteria=None)

    assert result["correct"][0]["final_operational_state"] == "verified"


def test_no_snapshot_in_validation_skips_staleness_check():
    """Validación sin geo_snapshot (registro antiguo) → se eleva sin verificar staleness."""
    entry = _make_correct_entry("CID7", "unverified")
    val = _make_validation("CID7")  # sin geo_snapshot
    geo_criteria = {"CID7": _make_geo_criteria_entry("CID7")}

    result = apply_ui_validations({"correct": [entry], "issues": []}, {"CID7": val}, geo_criteria)

    # Registro sin snapshot: se eleva (backward compat con validaciones antes de este cambio)
    assert result["correct"][0]["final_operational_state"] == "verified"
