"""
Thai Thai Ads Agent — Validación Manual de UI para Campañas SMART

Las campañas SMART tienen una capa Express UI que no es accesible por GAQL.
detect_geo_issues_by_policy() siempre devuelve ui_state="unknown" para estas
campañas. Este módulo permite persistir y aplicar confirmaciones humanas.

Flujo:
  1. Un humano inspecciona la UI Express (express/settings?tab=geo) y confirma
     que el geo está correcto.
  2. Se llama a save_ui_validation() para registrar esa confirmación en disco,
     incluyendo un geo_snapshot del estado validado.
  3. En cada ciclo de auditoría, se llama a apply_ui_validations() con el
     geo_criteria actual. La función compara el snapshot guardado contra el
     estado actual y eleva final_operational_state solo si coinciden.

Reglas de elevación:
  - Solo aplica a entradas con final_operational_state == "unverified".
  - Solo eleva si ui_validated_by_human == True Y ui_state == "correct".
  - Si la validación incluye geo_snapshot Y se pasa geo_criteria, se verifica
    que el estado geo actual coincida con el snapshot. Si no coincide, la
    validación se marca como stale y la entrada permanece "unverified".
  - Si la validación no tiene geo_snapshot (registro antiguo), se eleva sin
    verificación de staleness (backward compat).
  - Si geo_criteria no se pasa (None), se omite la verificación de staleness.
  - Las entradas en "issues" NUNCA se tocan.
  - Función pura: no modifica los dicts in-place, devuelve copias nuevas.

Tolerancias para comparación de snapshot:
  - Coordenadas lat/lng: ±0.001 grados (~111 m)
  - Radio de proximidad: ±0.5 km
"""

import copy
import json
import os
from datetime import datetime, timezone

_VALIDATIONS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "geo_ui_validations.json"
)

# Tolerancias de comparación de snapshot
_LAT_LNG_TOLERANCE = 0.001   # grados (~111 m)
_RADIUS_TOLERANCE_KM = 0.5   # km


# ─────────────────────────────────────────────────────────────────────────────
# Funciones de snapshot
# ─────────────────────────────────────────────────────────────────────────────

def _derive_targeting_type(location_ids: list, has_proximity: bool) -> str:
    """Devuelve el tipo de targeting activo según lo que tiene la campaña."""
    if location_ids and has_proximity:
        return "BOTH"
    if location_ids:
        return "LOCATION"
    if has_proximity:
        return "PROXIMITY"
    return "NONE"


def _build_geo_snapshot(criteria_entry: dict, objective_type: str) -> dict:
    """
    Construye un snapshot compacto y comparable del estado geo de una campaña.

    Args:
        criteria_entry : una entrada de fetch_campaign_geo_criteria()
        objective_type : str (ej. "LOCAL_DISCOVERY")

    Returns:
        dict con los campos relevantes para detectar cambios.
    """
    location_ids = sorted(criteria_entry.get("location_ids") or [])
    has_proximity = criteria_entry.get("has_proximity", False)
    return {
        "targeting_type":      _derive_targeting_type(location_ids, has_proximity),
        "location_ids":        location_ids,
        "proximity_radius_km": criteria_entry.get("proximity_radius_km"),
        "proximity_center_lat": criteria_entry.get("proximity_center_lat"),
        "proximity_center_lng": criteria_entry.get("proximity_center_lng"),
        "objective_type":      objective_type,
    }


def _snapshot_matches(stored: dict, current: dict) -> bool:
    """
    Compara un snapshot guardado con el estado geo actual.

    Returns:
        True si el estado actual es equivalente al snapshot (dentro de tolerancias).
        False si algún campo relevante cambió.
    """
    # Tipo de targeting
    if stored.get("targeting_type") != current.get("targeting_type"):
        return False

    # Location IDs (exacto — son strings, no hay tolerancia numérica)
    if sorted(stored.get("location_ids") or []) != sorted(current.get("location_ids") or []):
        return False

    # Objective type (política asignada a la campaña)
    if stored.get("objective_type") != current.get("objective_type"):
        return False

    # Campos PROXIMITY solo son relevantes cuando el tipo actual usa proximidad
    if current.get("targeting_type") in ("PROXIMITY", "BOTH"):
        # Radio
        s_r = stored.get("proximity_radius_km")
        c_r = current.get("proximity_radius_km")
        if s_r is not None and c_r is not None:
            if abs(s_r - c_r) > _RADIUS_TOLERANCE_KM:
                return False

        # Centro (lat)
        s_lat = stored.get("proximity_center_lat")
        c_lat = current.get("proximity_center_lat")
        if s_lat is not None and c_lat is not None:
            if abs(s_lat - c_lat) > _LAT_LNG_TOLERANCE:
                return False

        # Centro (lng)
        s_lng = stored.get("proximity_center_lng")
        c_lng = current.get("proximity_center_lng")
        if s_lng is not None and c_lng is not None:
            if abs(s_lng - c_lng) > _LAT_LNG_TOLERANCE:
                return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Funciones de persistencia
# ─────────────────────────────────────────────────────────────────────────────

def load_ui_validations(path: str | None = None) -> dict:
    """
    Carga las validaciones humanas de UI desde disco.

    Args:
        path: ruta al JSON (opcional, usa data/geo_ui_validations.json por defecto)

    Returns:
        dict keyed by campaign_id. Vacío si el archivo no existe.
    """
    target = path or _VALIDATIONS_PATH
    if not os.path.exists(target):
        return {}
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def save_ui_validation(
    campaign_id: str,
    campaign_name: str,
    ui_state: str,
    source: str,
    notes: str = "",
    geo_snapshot: dict | None = None,
    path: str | None = None,
) -> dict:
    """
    Registra o actualiza la validación humana de una campaña SMART.

    Args:
        campaign_id   : ID de la campaña (str)
        campaign_name : Nombre de la campaña
        ui_state      : "correct" | "incorrect:<ciudad>"
        source        : Quién/cómo validó (ej. "manual_session_confirmation")
        notes         : Descripción libre de lo que se observó en UI
        geo_snapshot  : snapshot del estado geo al momento de validar
                        (construir con _build_geo_snapshot). Recomendado
                        siempre que se disponga de geo_criteria.
        path          : ruta al JSON (opcional)

    Returns:
        El dict de la validación guardada.
    """
    target = path or _VALIDATIONS_PATH
    validations = load_ui_validations(target)

    record = {
        "campaign_id":         campaign_id,
        "campaign_name":       campaign_name,
        "ui_state":            ui_state,
        "ui_validated_by_human": True,
        "ui_validated_at":     datetime.now(timezone.utc).isoformat(),
        "ui_validation_source": source,
        "notes":               notes,
    }
    if geo_snapshot is not None:
        record["geo_snapshot"] = geo_snapshot

    validations[campaign_id] = record

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(validations, f, ensure_ascii=False, indent=2)

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Aplicación de validaciones al resultado de política
# ─────────────────────────────────────────────────────────────────────────────

def apply_ui_validations(
    policy_result: dict,
    ui_validations: dict,
    geo_criteria: dict | None = None,
) -> dict:
    """
    Aplica validaciones humanas sobre el resultado de detect_geo_issues_by_policy().

    Para cada entrada en "correct" con final_operational_state == "unverified":
      - Si existe una validación con ui_validated_by_human=True y ui_state="correct":
          - Si la validación tiene geo_snapshot Y se pasó geo_criteria:
              * Compara el snapshot guardado con el estado geo actual.
              * Si coinciden → eleva a "verified".
              * Si no coinciden → marca ui_validation_stale=True, permanece "unverified".
          - Si la validación no tiene geo_snapshot → eleva sin verificación (backward compat).
          - Si geo_criteria es None → eleva sin verificación (backward compat).
      - Si no hay validación para la campaña → sin cambios.

    Las entradas en "issues" no se modifican.

    Args:
        policy_result  : dict devuelto por detect_geo_issues_by_policy()
        ui_validations : dict de load_ui_validations()
        geo_criteria   : dict de fetch_campaign_geo_criteria() (opcional)
                         Si se pasa, activa la verificación de staleness.

    Returns:
        Nuevo dict con las claves ("issues", "correct") actualizadas.
        No modifica los dicts originales.
    """
    updated_correct = []

    for entry in policy_result.get("correct", []):
        e = copy.deepcopy(entry)
        cid = e.get("campaign_id")

        if e.get("final_operational_state") == "unverified" and cid in ui_validations:
            val = ui_validations[cid]

            if val.get("ui_validated_by_human") and val.get("ui_state") == "correct":
                # ── Verificación de staleness ─────────────────────────────
                is_stale = False
                stored_snap = val.get("geo_snapshot")

                if stored_snap is not None and geo_criteria is not None:
                    criteria_entry = geo_criteria.get(cid)
                    if criteria_entry is not None:
                        current_snap = _build_geo_snapshot(
                            criteria_entry,
                            e.get("objective_type", ""),
                        )
                        if not _snapshot_matches(stored_snap, current_snap):
                            is_stale = True

                if is_stale:
                    e["ui_validation_stale"] = True
                else:
                    e["ui_state"] = "correct"
                    e["ui_validated_by_human"] = True
                    e["ui_validated_at"] = val.get("ui_validated_at")
                    e["ui_validation_source"] = val.get("ui_validation_source")
                    e["final_operational_state"] = "verified"

        updated_correct.append(e)

    return {
        "issues":  copy.deepcopy(policy_result.get("issues", [])),
        "correct": updated_correct,
    }
