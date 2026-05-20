"""
Mini-app web para revisar recomendaciones AI de scale/reduce de presupuesto
y aplicarlas con un clic (Fase 5b agregará el POST).

GET /presupuestos       → página HTML autocontenida (sin build, sin deps).
GET /presupuestos/data  → JSON con las recomendaciones pendientes (lectura abierta).

POST /apply-budget-changes (PENDIENTE Fase 5b) → aplicará las seleccionadas via
update_campaign_budget(validate_only=True → False) protegido por X-API-Token.

Solo muestra recomendaciones de las categorías `scale` y `reduce` (decisión #5
del operador: `negative` → /negativos, `quality_alert` → email).
"""
import json
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from engine.db_sync import get_db_path
from routes.auth_token import require_token

router = APIRouter(tags=["presupuestos"])


class ApplyBudgetChangesRequest(BaseModel):
    """Body del POST /apply-budget-changes. SOLO decision_ids — el new_budget_mxn
    vive en autonomous_decisions y el handler lo lee de ahí (anti-tampering)."""

    decision_ids: list[int] = Field(min_length=1, max_length=20)


_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Presupuestos AI - Thai Thai Ads</title>
<style>
  :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  body { margin: 0; padding: 1.2rem; background: #fafafa; color: #1a1a1a; }
  h1 { font-size: 1.25rem; margin: 0 0 1rem; }
  .bar { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap; margin-bottom: 1rem; }
  select, input, button { font: inherit; padding: .45rem .6rem; border: 1px solid #ccc; border-radius: 6px; }
  button { background: #1f7a1f; color: #fff; border: 0; cursor: pointer; }
  button.secondary { background: #555; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  a { color: #06c; cursor: pointer; }
  table { border-collapse: collapse; width: 100%; background: #fff; }
  th, td { padding: .5rem .7rem; border-bottom: 1px solid #eee; text-align: left; font-size: .9rem; vertical-align: top; }
  th { background: #f0f0f0; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td.reason { color: #444; max-width: 380px; }
  .action-scale { color: #0a7a0a; font-weight: 600; }
  .action-reduce { color: #b35900; font-weight: 600; }
  .urgency-critical { background: #fde0e0; }
  .urgency-urgent   { background: #fff3c0; }
  #meta { color: #666; font-size: .85rem; }
  #empty { padding: 2rem; text-align: center; color: #888; background: #fff; border-radius: 6px; }
  #banner { background: #e0f5e0; border: 2px solid #1f9d1f; color: #0a5a0a;
            padding: 1rem 1.2rem; border-radius: 8px; margin: 1rem 0;
            font-size: 1.05rem; line-height: 1.5; }
  #banner.warn { background: #fff8e1; border-color: #f0c000; color: #7a5a00; }
  #banner.err { background: #fde0e0; border-color: #b30000; color: #7a0000; }
</style>
</head>
<body>
<h1>Presupuestos AI &mdash; Recomendaciones pendientes (scale / reduce)</h1>

<div id="gate" hidden>
  <p>Pega tu token de acceso (necesario solo para aplicar cambios):</p>
  <input id="tokenInput" type="password" size="44" autocomplete="off">
  <button id="tokenSave" class="secondary">Guardar</button>
  <button id="skipToken">Solo ver</button>
</div>

<div id="app" hidden>
  <div class="bar">
    <button id="load" class="secondary">Recargar</button>
    <span id="meta"></span>
    <a id="logout">borrar token</a>
  </div>

  <div id="tableWrap"></div>

  <button id="applyBtn" hidden disabled title="Endpoint POST disponible en Fase 5b">
    Aplicar seleccionadas (pendiente Fase 5b)
  </button>
  <div id="banner" hidden></div>
</div>

<script>
"use strict";
var TOKEN_KEY = "tt_admin_token";
var rows = [];

function el(id) { return document.getElementById(id); }
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function showApp() { el("gate").hidden = true; el("app").hidden = false; }
function showGate() { el("gate").hidden = false; el("app").hidden = true; }

function init() {
  if (localStorage.getItem(TOKEN_KEY)) { showApp(); load(); }
  else { showGate(); }
}

el("tokenSave").addEventListener("click", function() {
  var v = el("tokenInput").value.trim();
  if (!v) return;
  localStorage.setItem(TOKEN_KEY, v);
  showApp(); load();
});
el("skipToken").addEventListener("click", function() { showApp(); load(); });
el("logout").addEventListener("click", function() {
  localStorage.removeItem(TOKEN_KEY); showGate();
});
el("load").addEventListener("click", load);

function load() {
  el("meta").textContent = "Cargando...";
  el("banner").hidden = true;
  fetch("/presupuestos/data")
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.status !== "success") {
        el("meta").textContent = "Error: " + (d.message || "desconocido");
        return;
      }
      rows = d.recommendations || [];
      el("meta").textContent = rows.length + " recomendaciones pendientes" +
        " · ultima: " + (d.latest_at || "n/a");
      render();
    })
    .catch(function(e) {
      el("meta").textContent = "Error de red: " + e.message;
    });
}

function render() {
  var wrap = el("tableWrap");
  if (!rows.length) {
    wrap.innerHTML = "<div id='empty'>Sin recomendaciones de presupuesto pendientes.</div>";
    el("applyBtn").hidden = true;
    return;
  }
  var html = "<table><thead><tr>" +
    "<th></th><th>Campana</th><th>Accion</th><th class='num'>Nuevo $MXN/dia</th>" +
    "<th>Urgencia</th><th>Razon</th><th>Creada</th></tr></thead><tbody>";
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var actionClass = r.action_type === "scale" ? "action-scale" : "action-reduce";
    var actionLabel = r.action_type === "scale" ? "scale ↑" : "reduce ↓";
    var rowClass = r.urgency === "critical" ? "urgency-critical" :
                   r.urgency === "urgent"   ? "urgency-urgent" : "";
    html += "<tr class='" + rowClass + "' data-id='" + r.id + "'>" +
      "<td><input type='checkbox' disabled title='Disponible en Fase 5b'></td>" +
      "<td>" + escapeHtml(r.campaign_name) + " <small>(" + escapeHtml(r.campaign_id) + ")</small></td>" +
      "<td class='" + actionClass + "'>" + actionLabel + "</td>" +
      "<td class='num'>$" + Number(r.new_budget_mxn).toFixed(2) + "</td>" +
      "<td>" + escapeHtml(r.urgency) + "</td>" +
      "<td class='reason' title='" + escapeHtml(r.reason) + "'>" + escapeHtml(r.reason) + "</td>" +
      "<td>" + escapeHtml(r.created_at || "") + "</td>" +
      "</tr>";
  }
  html += "</tbody></table>";
  wrap.innerHTML = html;
  el("applyBtn").hidden = false;
}

init();
</script>
</body>
</html>
"""


@router.get("/presupuestos", response_class=HTMLResponse)
async def presupuestos_page():
    """Página HTML autocontenida que renderiza /presupuestos/data."""
    return _PAGE


@router.get("/presupuestos/data")
async def presupuestos_data() -> dict[str, Any]:
    """Devuelve las recomendaciones AI de scale/reduce pendientes de aprobación.

    Filtro:
      - action_type IN ("scale", "reduce")
      - decision = "proposed"
      - executed = 0
      - approved_at IS NULL AND rejected_at IS NULL AND postponed_at IS NULL

    Lectura abierta (sin token) — consistente con /search-terms y /negativos.
    El POST /apply-budget-changes (Fase 5b) sí requerirá X-API-Token.

    approval_token NO se incluye en el response: vive solo en DB para el flujo
    de email /approve-legacy. La UI usa decision_id como identificador.

    Filas con evidence_json corrupto (falta new_budget_mxn o reason) se omiten
    silenciosamente — exponerlas a la UI sería peligroso (apply con valor null).
    """
    db_path = get_db_path()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, action_type, campaign_id, campaign_name, urgency,
                       evidence_json, created_at
                  FROM autonomous_decisions
                 WHERE action_type IN ('scale', 'reduce')
                   AND decision = 'proposed'
                   AND executed = 0
                   AND approved_at  IS NULL
                   AND rejected_at  IS NULL
                   AND postponed_at IS NULL
                 ORDER BY
                   CASE urgency WHEN 'critical' THEN 0
                                WHEN 'urgent'   THEN 1
                                ELSE 2 END,
                   created_at DESC
                """
            )
            rows = cursor.fetchall()
    except Exception as exc:
        return {"status": "error", "message": str(exc), "recommendations": []}

    recommendations = []
    latest_at = None
    for r in rows:
        evidence = _safe_json(r["evidence_json"])
        new_budget_mxn = evidence.get("new_budget_mxn") if isinstance(evidence, dict) else None
        reason = evidence.get("reason") if isinstance(evidence, dict) else None
        if new_budget_mxn is None or reason is None:
            continue
        recommendations.append({
            "id": r["id"],
            "action_type": r["action_type"],
            "campaign_id": r["campaign_id"],
            "campaign_name": r["campaign_name"],
            "urgency": r["urgency"],
            "new_budget_mxn": new_budget_mxn,
            "reason": reason,
            "created_at": r["created_at"],
        })
        if latest_at is None or (r["created_at"] and r["created_at"] > latest_at):
            latest_at = r["created_at"]

    return {
        "status": "success",
        "recommendations": recommendations,
        "latest_at": latest_at,
        "count": len(recommendations),
    }


def _safe_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


@router.post("/apply-budget-changes", dependencies=[Depends(require_token)])
async def apply_budget_changes(request: ApplyBudgetChangesRequest) -> dict:
    """Aplica recomendaciones AI de scale/reduce a Google Ads.

    Auth: header X-API-Token (require_token).
    Input: {decision_ids: [int]}. SOLO IDs — el new_budget_mxn se lee de DB
    (anti-tampering: cliente NUNCA dicta el valor del cambio).

    Por cada decision_id:
      1. SELECT fila completa de autonomous_decisions.
      2. Invariantes de estado: action_type ∈ {scale,reduce}, decision='proposed',
         executed=0, no rejected_at, no postponed_at.
      3. Lee new_budget_mxn de evidence_json (omite si corrupto).
      4. fetch_campaign_budget_info → obtiene budget_resource_name y current.
      5. verify_budget_still_actionable → guardrails G_campaign/G_shared/G_drift/
         G_min/G_max_cut (delegado a la función existente del repo).
      6. update_campaign_budget(validate_only=True) → dry-run.
      7. update_campaign_budget(validate_only=False) → apply real.
      8. UPDATE executed=1, approved_at=now + log_agent_action.

    Cualquier falla en cualquier paso de un decision_id va a failed[] o
    blocked_by_guardrail[]; los demás del batch siguen procesándose.

    TODO drift-guard: el generador (Fase 1-3) no guarda budget_at_proposal_mxn
    en evidence_json — usamos current como fallback, lo que efectivamente
    desactiva G_drift. Issue separado para que ai_recommendations.py capture
    y persista el budget actual al generar la propuesta.
    """
    from engine.ads_client import (
        fetch_campaign_budget_info,
        get_ads_client,
        log_agent_action,
        update_campaign_budget,
        verify_budget_still_actionable,
    )

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
    if not customer_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_ADS_TARGET_CUSTOMER_ID no configurado en el entorno",
        )

    try:
        client = get_ads_client()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo instanciar Google Ads client: {exc}",
        )

    applied: list[dict] = []
    failed: list[dict] = []
    blocked_by_guardrail: list[dict] = []
    db_path = get_db_path()

    for decision_id in request.decision_ids:
        # ── Paso 1: SELECT fila ───────────────────────────────────────────
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM autonomous_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()

        if not row:
            failed.append({"decision_id": decision_id, "reason": "not_found"})
            continue

        # ── Paso 2: Invariantes de estado ─────────────────────────────────
        if row["action_type"] not in ("scale", "reduce"):
            failed.append({
                "decision_id": decision_id,
                "reason": "wrong_action_type",
                "detail": row["action_type"],
            })
            continue
        if row["executed"] == 1:
            failed.append({"decision_id": decision_id, "reason": "already_executed"})
            continue
        if row["rejected_at"] is not None:
            failed.append({"decision_id": decision_id, "reason": "rejected"})
            continue
        if row["postponed_at"] is not None:
            failed.append({"decision_id": decision_id, "reason": "postponed"})
            continue
        if row["decision"] != "proposed":
            failed.append({
                "decision_id": decision_id,
                "reason": "wrong_decision_state",
                "detail": row["decision"],
            })
            continue

        # ── Paso 3: Extraer new_budget_mxn de evidence (DB es source-of-truth)
        evidence = _safe_json(row["evidence_json"])
        new_budget_mxn = evidence.get("new_budget_mxn") if isinstance(evidence, dict) else None
        if not isinstance(new_budget_mxn, (int, float)) or new_budget_mxn <= 0:
            failed.append({
                "decision_id": decision_id,
                "reason": "invalid_evidence",
                "detail": "missing or invalid new_budget_mxn in evidence_json",
            })
            continue

        # ── Paso 4: Fetch budget actual ───────────────────────────────────
        budget_info = fetch_campaign_budget_info(client, customer_id, row["campaign_id"])
        if "error" in budget_info:
            failed.append({
                "decision_id": decision_id,
                "reason": "budget_fetch_failed",
                "detail": budget_info["error"],
            })
            continue
        current_budget_mxn = budget_info["current_daily_budget_mxn"]
        budget_resource_name = budget_info["budget_resource_name"]

        # ── Paso 5: Guardrails (delegado a verify_budget_still_actionable) ─
        # FIXME drift-guard: ver TODO en docstring del endpoint.
        budget_at_proposal = evidence.get("budget_at_proposal_mxn", current_budget_mxn)
        guard_result = verify_budget_still_actionable(
            client,
            customer_id,
            row["campaign_id"],
            budget_at_proposal,
            new_budget_mxn,
        )
        if not guard_result.get("ok"):
            blocked_by_guardrail.append({
                "decision_id": decision_id,
                "guardrail": guard_result.get("guard", ""),
                "reason": guard_result.get("reason", ""),
                "current_budget_mxn": guard_result.get("current_budget_mxn"),
                "suggested_budget_mxn": new_budget_mxn,
            })
            log_agent_action(
                action_type=f"apply_budget_{row['action_type']}",
                target=row["campaign_name"] or row["campaign_id"],
                details_before={"current_budget_mxn": current_budget_mxn},
                details_after={"new_budget_mxn": new_budget_mxn},
                status="blocked",
                google_ads_response=guard_result,
                db_path=db_path,
            )
            continue

        # ── Paso 6: Dry-run (validate_only=True) ──────────────────────────
        budget_micros = int(new_budget_mxn * 1_000_000)
        dry_result = update_campaign_budget(
            client, customer_id, budget_resource_name, budget_micros,
            validate_only=True,
        )
        if dry_result.get("status") != "success":
            failed.append({
                "decision_id": decision_id,
                "reason": "dry_run_failed",
                "detail": dry_result.get("message", ""),
            })
            log_agent_action(
                action_type=f"apply_budget_{row['action_type']}",
                target=row["campaign_name"] or row["campaign_id"],
                details_before={"current_budget_mxn": current_budget_mxn},
                details_after={"new_budget_mxn": new_budget_mxn},
                status="dry_run_failed",
                google_ads_response=dry_result,
                db_path=db_path,
            )
            continue

        # ── Paso 7: Apply real (validate_only=False) ──────────────────────
        real_result = update_campaign_budget(
            client, customer_id, budget_resource_name, budget_micros,
            validate_only=False,
        )
        if real_result.get("status") != "success":
            failed.append({
                "decision_id": decision_id,
                "reason": "apply_failed",
                "detail": real_result.get("message", ""),
            })
            log_agent_action(
                action_type=f"apply_budget_{row['action_type']}",
                target=row["campaign_name"] or row["campaign_id"],
                details_before={"current_budget_mxn": current_budget_mxn},
                details_after={"new_budget_mxn": new_budget_mxn},
                status="apply_failed",
                google_ads_response=real_result,
                db_path=db_path,
            )
            continue

        # ── Paso 8: Marcar executed + log success ─────────────────────────
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE autonomous_decisions "
                "SET executed = 1, approved_at = datetime('now') WHERE id = ?",
                (decision_id,),
            )

        applied.append({
            "decision_id": decision_id,
            "campaign_id": row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "action_type": row["action_type"],
            "old_budget_mxn": current_budget_mxn,
            "new_budget_mxn": new_budget_mxn,
        })
        log_agent_action(
            action_type=f"apply_budget_{row['action_type']}",
            target=row["campaign_name"] or row["campaign_id"],
            details_before={"current_budget_mxn": current_budget_mxn},
            details_after={"new_budget_mxn": new_budget_mxn},
            status="success",
            google_ads_response=real_result,
            db_path=db_path,
        )

    if not failed and not blocked_by_guardrail:
        status = "success"
    elif applied:
        status = "partial"
    else:
        status = "error"

    return {
        "status": status,
        "applied": applied,
        "failed": failed,
        "blocked_by_guardrail": blocked_by_guardrail,
        "summary": {
            "requested": len(request.decision_ids),
            "applied": len(applied),
            "failed": len(failed),
            "blocked": len(blocked_by_guardrail),
        },
    }
