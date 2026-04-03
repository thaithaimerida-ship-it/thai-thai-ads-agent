"""
Thai Thai Ads Agent — Módulo GEO: Auditoría de Geotargeting

Módulo oficial del MVP. Dos capas de auditoría:

Capa 1 — detect_geo_issues (por location_id):
  GEO1 — campaña tiene al menos una ubicación NO permitida por location_id.
  GEO0 — campaña no tiene ninguna restricción geográfica explícita por location_id.
         Incluye campañas con solo PROXIMITY (has_proximity=True).

  Si una campaña tiene Mérida + otra ubicación no permitida → GEO1 (no GEO0).

Capa 2 — detect_geo_issues_by_policy (por política de objetivo):
  Evalúa cada campaña contra su política de objetivo de negocio definida en
  GEO_OBJECTIVE_POLICIES (agent_config.py).
  Señales adicionales:
    WRONG_TYPE_LOC_FOR_PROX  — tiene LOCATION pero política esperaba PROXIMITY
    WRONG_TYPE_PROX_FOR_LOC  — tiene PROXIMITY pero política esperaba LOCATION
    PROX_RADIUS_EXCEEDED     — PROXIMITY con radio > max_radius_km
    POLICY_UNDEFINED         — campaña sin política asignada

Función pura — no realiza llamadas a la API de Google Ads ni a SQLite.
Testeable con datos sintéticos, sin dependencias externas.

Tipos excluidos (la API no permite mutar sus criterios geo):
  PERFORMANCE_MAX, LOCAL_SERVICES

─────────────────────────────────────────────────────────────────────
MODELO DE TRES ESTADOS PARA CAMPAÑAS SMART
─────────────────────────────────────────────────────────────────────
Las campañas SMART ("Campañas inteligentes") tienen una UI Express
(express/settings?tab=geo) que NO lee directamente de campaign_criterion.
La fuente interna de la UI no es accesible vía GAQL estándar.

Por eso, para campañas SMART cada entrada reporta tres campos:

  api_state   — lo que devuelve campaign_criterion (lo que el agente puede leer)
                "correct" | "geo1_incorrect" | "geo0_no_restriction"

  ui_state    — lo que muestra la UI Express de Google Ads
                "unknown"              — nunca validado manualmente
                "correct"              — confirmado correcto por humano
                "incorrect:<ciudad>"   — confirmado incorrecto por humano
                (este campo NUNCA puede resolverse solo con datos de API)

  final_operational_state — estado real del negocio:
                "verified"             — api_state=correct Y ui_state=correct
                "inconsistent"         — api_state=correct Y ui_state=incorrect
                "unverified"           — api_state=correct Y ui_state=unknown
                "geo_issue"            — api_state=geo1/geo0 (independiente de UI)

REGLA: Una campaña SMART solo se considera "resuelta" cuando
final_operational_state == "verified".

Para campañas no-SMART (SEARCH, DISPLAY, etc.):
  api_state == "correct"  →  final_operational_state = "verified" directamente.
  La UI de Google Ads para campañas estándar sí refleja campaign_criterion.
─────────────────────────────────────────────────────────────────────

Input esperado de `geo_criteria_by_campaign` (de fetch_campaign_geo_criteria()):
  dict keyed by campaign_id:
  {
    "campaign_id":              str,
    "campaign_name":            str,
    "advertising_channel_type": str,   # "SEARCH", "SMART", etc.
    "location_ids":             list,  # ["1010205", ...] — vacío si sin location_id
    "criteria_resource_names":  list,
    "has_proximity":            bool,  # True si tiene criterio PROXIMITY positivo
  }
"""

from config.agent_config import GEO_EXCLUDED_CHANNEL_TYPES

SMART_TYPES = {"SMART"}


def _build_geo_entry(
    signal: str,
    cid: str,
    campaign_name: str,
    channel_type: str,
    location_ids: list,
    allowed_location_ids: set,
    disallowed: list,
    has_proximity: bool,
    severity: str,
    reason: str,
) -> dict:
    """Construye el dict completo de un candidato con los tres estados."""
    is_smart = channel_type in SMART_TYPES

    if signal == "GEO1":
        api_state = "geo1_incorrect"
    elif signal == "GEO0":
        api_state = "geo0_no_restriction"
    else:
        api_state = "correct"

    if api_state in ("geo1_incorrect", "geo0_no_restriction"):
        final_operational_state = "geo_issue"
    elif is_smart:
        # SMART con API correcta: no podemos afirmar que la UI esté bien
        final_operational_state = "unverified"
    else:
        final_operational_state = "verified"

    return {
        "signal":                   signal,
        "campaign_id":              cid,
        "campaign_name":            campaign_name,
        "advertising_channel_type": channel_type,
        "detected_location_ids":    list(location_ids),
        "disallowed_location_ids":  disallowed,
        "allowed_location_ids":     sorted(allowed_location_ids),
        "has_proximity":            has_proximity,
        # ── Tres estados ──────────────────────────────────────────────────
        "api_state":                api_state,
        "ui_state":                 "unknown",   # solo un humano puede confirmar
        "final_operational_state":  final_operational_state,
        # ── Metadatos de resolución ───────────────────────────────────────
        "severity":                 severity,
        "reason":                   reason,
    }


def detect_geo_issues(
    geo_criteria_by_campaign: dict,
    allowed_location_ids: set,
) -> dict:
    """
    Detecta señales GEO1 y GEO0 en campañas activas.

    Solo evalúa campañas elegibles (excluye PERFORMANCE_MAX, LOCAL_SERVICES).

    Args:
        geo_criteria_by_campaign : dict de fetch_campaign_geo_criteria()
        allowed_location_ids     : set de location_ids permitidos (ej. {"1010205"})

    Returns:
      dict con:
        'issues'   — GEO1 y GEO0. GEO1 primero. final_operational_state = "geo_issue".
        'correct'  — Sin señal. Para SMART: final_operational_state = "unverified".
                     Para no-SMART: final_operational_state = "verified".

    Para campañas SMART con api_state="correct":
      - final_operational_state = "unverified" (nunca "verified" sin confirmación humana)
      - ui_state = "unknown"
      Para marcar una SMART como resuelta, un humano debe confirmar la UI
      y actualizar ui_state a "correct" externamente.
    """
    geo1_candidates   = []
    geo0_candidates   = []
    correct_campaigns = []

    for cid, entry in geo_criteria_by_campaign.items():
        channel_type  = entry.get("advertising_channel_type", "")
        campaign_name = entry.get("campaign_name", "")
        location_ids  = entry.get("location_ids", [])
        has_proximity = entry.get("has_proximity", False)
        is_smart      = channel_type in SMART_TYPES

        if channel_type in GEO_EXCLUDED_CHANNEL_TYPES:
            continue

        disallowed = [lid for lid in location_ids if lid not in allowed_location_ids]

        if disallowed:
            smart_note = " SMART: la UI Express requiere correccion manual adicional." if is_smart else ""
            reason = (
                f"Campana '{campaign_name}' tiene ubicaciones no permitidas: {disallowed}. "
                f"Permitidas: {sorted(allowed_location_ids)}." + smart_note
            )
            geo1_candidates.append(_build_geo_entry(
                "GEO1", cid, campaign_name, channel_type,
                location_ids, allowed_location_ids, disallowed,
                has_proximity, "high", reason,
            ))

        elif not location_ids:
            if has_proximity:
                # PROXIMITY es un mecanismo geo válido — no generar GEO0.
                # Capa 2 (detect_geo_issues_by_policy) evalúa el radio contra la política.
                smart_note = " SMART: validar adicionalmente en UI Express." if is_smart else ""
                reason = (
                    f"Campana '{campaign_name}' usa PROXIMITY (sin location_id). "
                    f"Capa 1 no evalua radio — validacion completa en Capa 2 por politica."
                    + smart_note
                )
                correct_campaigns.append(_build_geo_entry(
                    "OK", cid, campaign_name, channel_type,
                    [], allowed_location_ids, [],
                    has_proximity, "none", reason,
                ))
            else:
                smart_note = " SMART: validar adicionalmente en UI Express." if is_smart else ""
                reason = (
                    f"Campana '{campaign_name}' no tiene location_id ni PROXIMITY. "
                    f"El anuncio puede aparecer en cualquier lugar." + smart_note
                )
                geo0_candidates.append(_build_geo_entry(
                    "GEO0", cid, campaign_name, channel_type,
                    [], allowed_location_ids, [],
                    has_proximity, "low", reason,
                ))

        else:
            # location_ids correctos por API
            if is_smart:
                reason = (
                    f"Campana '{campaign_name}' tiene location_ids correctos por API: {location_ids}. "
                    f"AVISO SMART: la UI Express opera sobre una capa distinta. "
                    f"api_state=correct no implica ui_state=correct. "
                    f"final_operational_state='unverified' hasta confirmacion manual de UI."
                )
            else:
                reason = (
                    f"Campana '{campaign_name}' tiene location_ids correctos: {location_ids}."
                )
            correct_campaigns.append(_build_geo_entry(
                "OK", cid, campaign_name, channel_type,
                location_ids, allowed_location_ids, [],
                has_proximity, "none", reason,
            ))

    return {
        "issues":  geo1_candidates + geo0_candidates,
        "correct": correct_campaigns,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auditoría por política de objetivo (Bloque 2)
# ─────────────────────────────────────────────────────────────────────────────

def _build_policy_entry(
    signal: str,
    compliant: bool,
    cid: str,
    campaign_name: str,
    channel_type: str,
    objective_type: str,
    autofix_allowed: bool,
    ui_validation_required: bool,
    reason: str,
) -> dict:
    """Construye el dict completo de una evaluación por política."""
    is_smart = channel_type in SMART_TYPES

    _issue_signals = {
        "GEO1", "GEO0",
        "PROX_RADIUS_EXCEEDED", "PROX_RADIUS_INSUFFICIENT",
        "WRONG_TYPE_LOC_FOR_PROX", "WRONG_TYPE_PROX_FOR_LOC",
        "POLICY_UNDEFINED",
    }
    if signal in _issue_signals:
        api_state = "geo_issue" if signal in ("GEO1", "GEO0") else signal.lower()
        final_operational_state = "geo_issue"
    else:
        # OK
        api_state = "correct"
        if is_smart:
            final_operational_state = "unverified"
        else:
            final_operational_state = "verified"

    return {
        "signal":                   signal,
        "compliant":                compliant,
        "campaign_id":              cid,
        "campaign_name":            campaign_name,
        "advertising_channel_type": channel_type,
        "objective_type":           objective_type,
        "api_state":                api_state,
        "ui_state":                 "unknown",
        "final_operational_state":  final_operational_state,
        "autofix_allowed":          autofix_allowed,
        "ui_validation_required":   ui_validation_required,
        "reason":                   reason,
    }


def detect_geo_issues_by_policy(
    geo_criteria_by_campaign: dict,
    campaign_objectives: dict,
    objective_policies: dict,
) -> dict:
    """
    Audita cada campaña contra su política de objetivo de negocio.

    Args:
        geo_criteria_by_campaign : dict de fetch_campaign_geo_criteria()
        campaign_objectives      : {campaign_id: objective_type}
        objective_policies       : {objective_type: policy_dict}
                                   (ver GEO_OBJECTIVE_POLICIES en agent_config.py)

    Returns:
        dict con:
          'issues'   — campañas no conformes con su política.
          'correct'  — campañas conformes con su política.

    Señales posibles:
      OK                      — cumple la política
      GEO0                    — sin criterio geográfico (PROXIMITY ni LOCATION)
      GEO1                    — tiene LOCATION pero con IDs no permitidos
      WRONG_TYPE_LOC_FOR_PROX — tiene LOCATION pero la política exige PROXIMITY
      WRONG_TYPE_PROX_FOR_LOC — tiene PROXIMITY pero la política exige LOCATION estricta
      PROX_RADIUS_EXCEEDED    — tiene PROXIMITY pero radio > max_radius_km
      PROX_RADIUS_INSUFFICIENT — tiene PROXIMITY pero radio < min_radius_km
      POLICY_UNDEFINED        — campaña sin política asignada

    Targeting type "LOCATION_OR_PROXIMITY":
      Acepta LOCATION con IDs permitidos O PROXIMITY dentro del rango de radio
      [min_radius_km, max_radius_km]. Diseñado para objetivos de descubrimiento
      local donde la equivalencia funcional entre mecanismos es aceptable.
    """
    issues  = []
    correct = []

    for cid, entry in geo_criteria_by_campaign.items():
        channel_type  = entry.get("advertising_channel_type", "")
        campaign_name = entry.get("campaign_name", "")
        location_ids  = entry.get("location_ids", [])
        has_proximity = entry.get("has_proximity", False)
        radius_km     = entry.get("proximity_radius_km")

        # ── Sin política asignada ─────────────────────────────────────────
        objective_type = campaign_objectives.get(cid)
        if not objective_type or objective_type not in objective_policies:
            e = _build_policy_entry(
                signal="POLICY_UNDEFINED",
                compliant=False,
                cid=cid,
                campaign_name=campaign_name,
                channel_type=channel_type,
                objective_type=objective_type or "UNDEFINED",
                autofix_allowed=False,
                ui_validation_required=True,
                reason=(
                    f"Campaña '{campaign_name}' no tiene política GEO asignada. "
                    f"Definir objetivo antes de cualquier acción automática."
                ),
            )
            issues.append(e)
            continue

        policy              = objective_policies[objective_type]
        expected_type       = policy.get("expected_targeting_type")   # "PROXIMITY" | "LOCATION" | None
        max_radius          = policy.get("max_radius_km")
        allowed_locs        = policy.get("allowed_location_ids", set())
        autofix_allowed     = policy.get("autofix_allowed", False)
        ui_val_required     = policy.get("ui_validation_required", False)

        # ── Sin geo en absoluto ───────────────────────────────────────────
        if not location_ids and not has_proximity:
            e = _build_policy_entry(
                signal="GEO0",
                compliant=False,
                cid=cid,
                campaign_name=campaign_name,
                channel_type=channel_type,
                objective_type=objective_type,
                autofix_allowed=autofix_allowed,
                ui_validation_required=ui_val_required,
                reason=(
                    f"Campaña '{campaign_name}' no tiene criterio geográfico "
                    f"(ni LOCATION ni PROXIMITY). Política '{objective_type}' requiere "
                    f"{expected_type or 'geo definido'}."
                ),
            )
            issues.append(e)
            continue

        # ── Política exige PROXIMITY ──────────────────────────────────────
        if expected_type == "PROXIMITY":
            if location_ids and not has_proximity:
                # Tiene LOCATION en vez de PROXIMITY
                e = _build_policy_entry(
                    signal="WRONG_TYPE_LOC_FOR_PROX",
                    compliant=False,
                    cid=cid,
                    campaign_name=campaign_name,
                    channel_type=channel_type,
                    objective_type=objective_type,
                    autofix_allowed=autofix_allowed,
                    ui_validation_required=ui_val_required,
                    reason=(
                        f"Campaña '{campaign_name}' usa LOCATION {location_ids} "
                        f"pero la política '{objective_type}' exige PROXIMITY "
                        f"(radio ≤{max_radius} km)."
                    ),
                )
                issues.append(e)
                continue

            if has_proximity:
                # Verificar radio
                if max_radius is not None and radius_km is not None and radius_km > max_radius:
                    e = _build_policy_entry(
                        signal="PROX_RADIUS_EXCEEDED",
                        compliant=False,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' tiene PROXIMITY de {radius_km} km "
                            f"pero la política '{objective_type}' permite máximo {max_radius} km."
                        ),
                    )
                    issues.append(e)
                    continue

                # PROXIMITY con radio OK
                e = _build_policy_entry(
                    signal="OK",
                    compliant=True,
                    cid=cid,
                    campaign_name=campaign_name,
                    channel_type=channel_type,
                    objective_type=objective_type,
                    autofix_allowed=autofix_allowed,
                    ui_validation_required=ui_val_required,
                    reason=(
                        f"Campaña '{campaign_name}' cumple política '{objective_type}': "
                        f"PROXIMITY {radius_km} km ≤ {max_radius} km."
                    ),
                )
                correct.append(e)
                continue

        # ── Política exige LOCATION ───────────────────────────────────────
        if expected_type == "LOCATION":
            if has_proximity and not location_ids:
                # Tiene solo PROXIMITY en vez de LOCATION
                e = _build_policy_entry(
                    signal="WRONG_TYPE_PROX_FOR_LOC",
                    compliant=False,
                    cid=cid,
                    campaign_name=campaign_name,
                    channel_type=channel_type,
                    objective_type=objective_type,
                    autofix_allowed=autofix_allowed,
                    ui_validation_required=ui_val_required,
                    reason=(
                        f"Campaña '{campaign_name}' usa solo PROXIMITY "
                        f"pero la política '{objective_type}' exige LOCATION "
                        f"en IDs permitidos: {sorted(allowed_locs)}."
                    ),
                )
                issues.append(e)
                continue

            if location_ids:
                disallowed = [lid for lid in location_ids if lid not in allowed_locs]
                if disallowed:
                    e = _build_policy_entry(
                        signal="GEO1",
                        compliant=False,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' tiene LOCATION con IDs no permitidos: "
                            f"{disallowed}. Política '{objective_type}' permite: {sorted(allowed_locs)}."
                        ),
                    )
                    issues.append(e)
                    continue

                # LOCATION OK
                e = _build_policy_entry(
                    signal="OK",
                    compliant=True,
                    cid=cid,
                    campaign_name=campaign_name,
                    channel_type=channel_type,
                    objective_type=objective_type,
                    autofix_allowed=autofix_allowed,
                    ui_validation_required=ui_val_required,
                    reason=(
                        f"Campaña '{campaign_name}' cumple política '{objective_type}': "
                        f"LOCATION {location_ids}."
                    ),
                )
                correct.append(e)
                continue

        # ── Política acepta LOCATION o PROXIMITY (equivalencia funcional) ──
        if expected_type == "LOCATION_OR_PROXIMITY":
            min_radius = policy.get("min_radius_km")

            # Caso 1: tiene LOCATION — validar IDs
            if location_ids:
                disallowed = [lid for lid in location_ids if lid not in allowed_locs]
                if disallowed:
                    e = _build_policy_entry(
                        signal="GEO1",
                        compliant=False,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' tiene LOCATION con IDs no permitidos: "
                            f"{disallowed}. Política '{objective_type}' permite: {sorted(allowed_locs)}."
                        ),
                    )
                    issues.append(e)
                else:
                    e = _build_policy_entry(
                        signal="OK",
                        compliant=True,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' cumple política '{objective_type}': "
                            f"LOCATION {location_ids} en IDs permitidos."
                        ),
                    )
                    correct.append(e)
                continue

            # Caso 2: tiene solo PROXIMITY — validar rango de radio
            if has_proximity:
                if min_radius is not None and radius_km is not None and radius_km < min_radius:
                    e = _build_policy_entry(
                        signal="PROX_RADIUS_INSUFFICIENT",
                        compliant=False,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' tiene PROXIMITY de {radius_km} km "
                            f"pero la política '{objective_type}' requiere mínimo {min_radius} km "
                            f"para cobertura funcional de Mérida."
                        ),
                    )
                    issues.append(e)
                elif max_radius is not None and radius_km is not None and radius_km > max_radius:
                    e = _build_policy_entry(
                        signal="PROX_RADIUS_EXCEEDED",
                        compliant=False,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' tiene PROXIMITY de {radius_km} km "
                            f"pero la política '{objective_type}' permite máximo {max_radius} km."
                        ),
                    )
                    issues.append(e)
                else:
                    e = _build_policy_entry(
                        signal="OK",
                        compliant=True,
                        cid=cid,
                        campaign_name=campaign_name,
                        channel_type=channel_type,
                        objective_type=objective_type,
                        autofix_allowed=autofix_allowed,
                        ui_validation_required=ui_val_required,
                        reason=(
                            f"Campaña '{campaign_name}' cumple política '{objective_type}': "
                            f"PROXIMITY {radius_km} km dentro del rango permitido "
                            f"[{min_radius}–{max_radius} km]. Equivalencia funcional con LOCATION aceptada."
                        ),
                    )
                    correct.append(e)
                continue

    return {"issues": issues, "correct": correct}
