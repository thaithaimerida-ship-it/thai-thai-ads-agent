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
  td.drift-medium  { background: #fff3c0; font-weight: 600; }
  td.drift-large   { background: #fde0e0; font-weight: 600; }
  .muted { color: #999; }
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

  <button id="applyBtn" hidden disabled title="Selecciona al menos una recomendacion">
    Aplicar seleccionadas
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
el("applyBtn").addEventListener("click", applySelected);
el("tableWrap").addEventListener("change", function(ev) {
  if (ev.target && ev.target.classList.contains("pick")) updateApplyState();
});

function selectedIds() {
  var checks = document.querySelectorAll("#tableWrap input.pick:checked");
  var ids = [];
  for (var i = 0; i < checks.length; i++) {
    var n = parseInt(checks[i].getAttribute("data-id"), 10);
    if (!isNaN(n)) ids.push(n);
  }
  return ids;
}

function updateApplyState() {
  var btn = el("applyBtn");
  if (btn.hidden) return;
  var ids = selectedIds();
  var token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    btn.disabled = true;
    btn.title = "Falta token: usa 'borrar token' y pega tu token para habilitar apply";
    btn.textContent = "Aplicar seleccionadas (sin token)";
    return;
  }
  if (ids.length === 0) {
    btn.disabled = true;
    btn.title = "Selecciona al menos una recomendacion";
    btn.textContent = "Aplicar seleccionadas";
    return;
  }
  if (ids.length > 20) {
    btn.disabled = true;
    btn.title = "Maximo 20 por lote";
    btn.textContent = "Aplicar " + ids.length + " (max 20)";
    return;
  }
  btn.disabled = false;
  btn.title = "";
  btn.textContent = "Aplicar " + ids.length + " seleccionada" + (ids.length === 1 ? "" : "s");
}

function showBanner(kind, html) {
  var b = el("banner");
  b.className = kind === "ok" ? "" : kind;
  b.innerHTML = html;
  b.hidden = false;
}

function applySelected() {
  var btn = el("applyBtn");
  var ids = selectedIds();
  var token = localStorage.getItem(TOKEN_KEY);
  if (!token || ids.length === 0 || ids.length > 20) { updateApplyState(); return; }

  btn.disabled = true;
  btn.textContent = "Aplicando...";
  el("banner").hidden = true;

  fetch("/apply-budget-changes", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Token": token },
    body: JSON.stringify({ decision_ids: ids }),
  })
    .then(function(r) {
      return r.json().then(function(d) { return { ok: r.ok, status: r.status, data: d }; });
    })
    .then(function(res) {
      if (!res.ok) {
        var msg = (res.data && (res.data.detail || res.data.message)) || ("HTTP " + res.status);
        showBanner("err", "Error: " + escapeHtml(msg));
        updateApplyState();
        return;
      }
      renderResult(res.data);
      load();
    })
    .catch(function(e) {
      showBanner("err", "Error de red: " + escapeHtml(e.message));
      updateApplyState();
    });
}

function renderResult(d) {
  var s = d.summary || {};
  var kind = d.status === "success" ? "ok" :
             d.status === "partial" ? "warn" : "err";
  var parts = ["<strong>" + escapeHtml(d.status || "?") + "</strong>" +
               " &mdash; solicitadas: " + (s.requested || 0) +
               ", aplicadas: " + (s.applied || 0) +
               ", fallidas: " + (s.failed || 0) +
               ", bloqueadas: " + (s.blocked || 0)];
  if (d.applied && d.applied.length) {
    var lines = d.applied.map(function(a) {
      return "✓ " + escapeHtml(a.campaign_name || a.campaign_id) +
             ": $" + Number(a.old_budget_mxn).toFixed(2) +
             " → $" + Number(a.new_budget_mxn).toFixed(2);
    });
    parts.push("<ul><li>" + lines.join("</li><li>") + "</li></ul>");
  }
  if (d.failed && d.failed.length) {
    var fl = d.failed.map(function(f) {
      return "id " + f.decision_id + ": " + escapeHtml(f.reason || "") +
             (f.detail ? " (" + escapeHtml(f.detail) + ")" : "");
    });
    parts.push("<div>Fallaron:<ul><li>" + fl.join("</li><li>") + "</li></ul></div>");
  }
  if (d.blocked_by_guardrail && d.blocked_by_guardrail.length) {
    var bl = d.blocked_by_guardrail.map(function(b) {
      return "id " + b.decision_id + ": " + escapeHtml(b.guardrail || "") +
             " — " + escapeHtml(b.reason || "");
    });
    parts.push("<div>Bloqueadas:<ul><li>" + bl.join("</li><li>") + "</li></ul></div>");
  }
  showBanner(kind, parts.join(""));
}

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
    "<th></th><th>Campana</th><th>Accion</th>" +
    "<th class='num'>Actual $/dia</th><th class='num'>Nuevo $/dia</th>" +
    "<th>Urgencia</th><th>Razon</th><th>Creada</th></tr></thead><tbody>";
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var actionClass = r.action_type === "scale" ? "action-scale" : "action-reduce";
    var actionLabel = r.action_type === "scale" ? "scale ↑" : "reduce ↓";
    var rowClass = r.urgency === "critical" ? "urgency-critical" :
                   r.urgency === "urgent"   ? "urgency-urgent" : "";
    var currentCell;
    if (r.current_budget_mxn == null) {
      currentCell = "<td class='num'><span class='muted'>n/d</span></td>";
    } else {
      var drift = Math.abs(r.new_budget_mxn - r.current_budget_mxn) / r.current_budget_mxn;
      var driftCls = drift > 0.5 ? "drift-large" : drift > 0.2 ? "drift-medium" : "";
      currentCell = "<td class='num " + driftCls + "'>$" + Number(r.current_budget_mxn).toFixed(2) + "</td>";
    }
    html += "<tr class='" + rowClass + "' data-id='" + r.id + "'>" +
      "<td>" + (r.apply_enabled === false
        ? "<span class='muted' title='" + escapeHtml(r.apply_disabled_reason || "") + "'>solo lectura</span>"
        : "<input type='checkbox' class='pick' data-id='" + r.id + "'>") + "</td>" +
      "<td>" + escapeHtml(r.campaign_name) + " <small>(" + escapeHtml(r.campaign_id) + ")</small></td>" +
      "<td class='" + actionClass + "'>" + actionLabel +
        (r.apply_enabled === false ? "<div class='muted'>" + escapeHtml(r.apply_disabled_reason || "") + "</div>" : "") +
      "</td>" +
      currentCell +
      "<td class='num'>$" + Number(r.new_budget_mxn).toFixed(2) + "</td>" +
      "<td>" + escapeHtml(r.urgency) + "</td>" +
      "<td class='reason' title='" + escapeHtml(r.reason) + "'>" + escapeHtml(r.reason) + "</td>" +
      "<td>" + escapeHtml(r.created_at || "") + "</td>" +
      "</tr>";
  }
  html += "</tbody></table>";
  wrap.innerHTML = html;
  el("applyBtn").hidden = false;
  updateApplyState();
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
      - action_type IN ("scale", "reduce", "budget_action", "budget_scale")
      - decision = "proposed"
      - executed = 0
      - approved_at IS NULL AND rejected_at IS NULL AND postponed_at IS NULL

    Lectura abierta (sin token) — consistente con /search-terms y /negativos.
    El POST /apply-budget-changes (Fase 5b) sí requerirá X-API-Token.

    approval_token NO se incluye en el response: vive solo en DB para el flujo
    de email /approve-legacy. La UI usa decision_id como identificador.

    Filas con evidence_json corrupto (falta new_budget_mxn o reason) se omiten
    silenciosamente — exponerlas a la UI sería peligroso (apply con valor null).

    Enriquece cada recomendación con `current_budget_mxn` (presupuesto actual
    real consultado a Google Ads) para que el operador vea drift al aprobar.
    Si Google Ads no responde, el campo es null y la UI muestra "n/d" — no
    bloquea apply (los guardrails de POST /apply-budget-changes siguen activos:
    verify_budget_still_actionable re-fetchea estado fresco antes de mutar).
    Mitigación intermedia mientras G_drift del POST queda desactivado por el
    TODO drift-guard (ai_recommendations.py no persiste budget_at_proposal_mxn).
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
                 WHERE action_type IN ('scale', 'reduce', 'budget_action', 'budget_scale')
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

    # Pre-filtra recs válidas para minimizar fetch a Google Ads.
    candidates = []
    for r in rows:
        evidence = _safe_json(r["evidence_json"])
        new_budget_mxn = _budget_suggestion_amount(evidence)
        reason = evidence.get("reason") if isinstance(evidence, dict) else None
        if new_budget_mxn is None or reason is None:
            continue
        candidates.append((r, new_budget_mxn, reason))

    # Fetch current budgets en una sola llamada para todos los campaign_ids.
    # Si falla, devuelve {} y current queda null en la UI ("n/d") — no bloquea.
    current_budgets = _fetch_current_budgets({c[0]["campaign_id"] for c in candidates})

    recommendations = []
    latest_at = None
    for r, new_budget_mxn, reason in candidates:
        action_type_original = r["action_type"]
        display_action_type = _display_budget_action_type(action_type_original)
        apply_enabled = action_type_original in {"scale", "reduce"}
        recommendations.append({
            "id": r["id"],
            "action_type": display_action_type,
            "action_type_original": action_type_original,
            "display_action_type": display_action_type,
            "campaign_id": r["campaign_id"],
            "campaign_name": r["campaign_name"],
            "urgency": r["urgency"],
            "new_budget_mxn": new_budget_mxn,
            "suggested_budget_mxn": new_budget_mxn,
            "current_budget_mxn": current_budgets.get(r["campaign_id"]),
            "reason": reason,
            "apply_enabled": apply_enabled,
            "apply_disabled_reason": "" if apply_enabled else "Pendiente de compatibilidad de aplicacion",
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


def _fetch_current_budgets(campaign_ids: set) -> dict:
    """Devuelve {campaign_id: daily_budget_mxn} para los IDs dados.

    Si get_engine_modules / get_ads_client / fetch_campaign_data falla, devuelve
    {} silenciosamente. NO es bloqueante para mostrar la UI — el operador puede
    aplicar igual y verify_budget_still_actionable re-validará en POST con
    fetch fresco a Google Ads.
    """
    if not campaign_ids:
        return {}
    try:
        from main import get_engine_modules
        engine = get_engine_modules()
        if not engine:
            return {}
        customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        if not customer_id:
            return {}
        client = engine["get_ads_client"]()
        # YESTERDAY es el rango más barato; solo nos interesa daily_budget_mxn.
        raw = engine["fetch_campaign_data"](client, customer_id, "YESTERDAY") or []
        return {
            str(c.get("id")): c.get("daily_budget_mxn")
            for c in raw
            if str(c.get("id")) in campaign_ids and c.get("daily_budget_mxn") is not None
        }
    except Exception:
        return {}


def _safe_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _budget_suggestion_amount(evidence):
    if not isinstance(evidence, dict):
        return None
    for key in ("new_budget_mxn", "suggested_daily_budget", "suggested_daily_budget_mxn"):
        value = evidence.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return value
    return None


def _display_budget_action_type(action_type):
    if action_type == "budget_action":
        return "reduce"
    if action_type == "budget_scale":
        return "scale"
    return action_type


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
