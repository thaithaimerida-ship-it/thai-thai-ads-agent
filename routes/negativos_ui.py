"""UI read-only para revisar search terms antes de decidir negativos."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Negativos - Bandeja V2</title>
<style>
  :root {
    --ink: #17201b;
    --muted: #66736c;
    --line: #dfe7e2;
    --paper: #fbfcfa;
    --panel: #ffffff;
    --safe: #1d6f54;
    --safe-soft: #e7f4ee;
    --warn: #8b5e14;
    --warn-soft: #fff4d7;
    --danger: #9b2f2f;
    --danger-soft: #fbe7e5;
    --quiet: #eef2f0;
    --shadow: 0 16px 40px rgba(23, 32, 27, .08);
    font-family: Georgia, "Times New Roman", serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: linear-gradient(180deg, #f6f8f5 0%, #edf2ef 100%);
    color: var(--ink);
  }
  button, select { font: inherit; }
  .shell { max-width: 1180px; margin: 0 auto; padding: 28px 18px 96px; }
  .hero {
    display: grid;
    gap: 18px;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    border-bottom: 1px solid var(--line);
    padding-bottom: 22px;
  }
  h1 { margin: 0; font-size: clamp(2rem, 5vw, 4.2rem); line-height: .95; letter-spacing: 0; }
  .subtitle { margin: 12px 0 0; max-width: 760px; color: var(--muted); font: 1rem/1.55 system-ui, sans-serif; }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    border: 1px solid #b7d6c7;
    background: var(--safe-soft);
    color: #114d38;
    border-radius: 999px;
    padding: 7px 12px;
    font: 700 .82rem/1 system-ui, sans-serif;
    margin-bottom: 12px;
  }
  .controls {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
  }
  select {
    min-width: 128px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel);
    color: var(--ink);
    padding: 10px 12px;
  }
  button {
    border: 1px solid var(--ink);
    border-radius: 8px;
    background: var(--ink);
    color: white;
    padding: 10px 14px;
    cursor: pointer;
  }
  button.secondary {
    color: var(--ink);
    background: var(--panel);
    border-color: var(--line);
  }
  button[disabled] { opacity: .5; cursor: not-allowed; }
  .summary {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
    margin: 18px 0 20px;
  }
  .metric {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 13px 14px;
    box-shadow: var(--shadow);
  }
  .metric strong { display: block; font-size: 1.8rem; line-height: 1; }
  .metric span { display: block; color: var(--muted); font: 700 .72rem/1.2 system-ui, sans-serif; text-transform: uppercase; letter-spacing: .05em; margin-top: 7px; }
  .status-line { color: var(--muted); font: .92rem/1.45 system-ui, sans-serif; min-height: 1.4em; }
  .section {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    margin: 14px 0;
    overflow: hidden;
    box-shadow: var(--shadow);
  }
  details.section summary {
    list-style: none;
    cursor: pointer;
  }
  details.section summary::-webkit-details-marker { display: none; }
  .section-head {
    display: flex;
    gap: 12px;
    justify-content: space-between;
    align-items: center;
    padding: 16px 18px;
    border-bottom: 1px solid var(--line);
  }
  .section-head h2 { margin: 0; font-size: 1.12rem; letter-spacing: 0; }
  .section-head p { margin: 6px 0 0; color: var(--muted); font: .92rem/1.45 system-ui, sans-serif; }
  .count {
    min-width: 42px;
    text-align: center;
    border-radius: 999px;
    background: var(--quiet);
    padding: 6px 10px;
    font: 800 .9rem/1 system-ui, sans-serif;
  }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  th, td {
    border-bottom: 1px solid var(--line);
    padding: 12px 14px;
    vertical-align: top;
    text-align: left;
  }
  th {
    color: var(--muted);
    font: 800 .72rem/1.2 system-ui, sans-serif;
    text-transform: uppercase;
    letter-spacing: .05em;
    background: #f7f9f7;
  }
  td { font: .94rem/1.42 system-ui, sans-serif; }
  .term { font-weight: 800; color: var(--ink); overflow-wrap: anywhere; }
  .campaign { color: var(--muted); margin-top: 4px; font-size: .82rem; }
  .what { font-variant-numeric: tabular-nums; white-space: normal; }
  .reason { color: #334139; }
  .tag {
    display: inline-flex;
    border-radius: 999px;
    border: 1px solid var(--line);
    padding: 5px 8px;
    font: 800 .75rem/1.1 system-ui, sans-serif;
    background: var(--quiet);
  }
  .tag.ready { background: var(--danger-soft); color: var(--danger); border-color: #f1b8b2; }
  .tag.confirm { background: var(--warn-soft); color: var(--warn); border-color: #ecd38b; }
  .tag.caution { background: var(--warn-soft); color: var(--warn); border-color: #ecd38b; }
  .tag.protected { background: var(--safe-soft); color: var(--safe); border-color: #b7d6c7; }
  .tag.blocked { background: var(--quiet); color: #45524b; }
  .empty { padding: 18px; color: var(--muted); font: .95rem/1.45 system-ui, sans-serif; }
  .detail-row td { background: #f7f9f7; }
  .detail-box {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .detail-box div {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px;
    background: white;
  }
  .detail-box b { display: block; font-size: .76rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 5px; }
  .footer {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    border-top: 1px solid var(--line);
    background: rgba(255, 255, 255, .96);
    color: #314039;
    padding: 12px 18px;
    font: .88rem/1.45 system-ui, sans-serif;
    box-shadow: 0 -10px 30px rgba(23, 32, 27, .08);
  }
  .footer-inner { max-width: 1180px; margin: 0 auto; }
  @media (max-width: 860px) {
    .hero { grid-template-columns: 1fr; align-items: start; }
    .controls { justify-content: flex-start; }
    .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    table, thead, tbody, tr, th, td { display: block; }
    thead { display: none; }
    tr { border-bottom: 1px solid var(--line); padding: 10px 0; }
    td { border: 0; padding: 7px 14px; }
    td::before {
      content: attr(data-label);
      display: block;
      color: var(--muted);
      font: 800 .68rem/1.2 system-ui, sans-serif;
      text-transform: uppercase;
      letter-spacing: .05em;
      margin-bottom: 3px;
    }
    .detail-box { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<main class="shell">
  <section class="hero">
    <div>
      <div class="badge">Modo seguro - Solo lectura</div>
      <h1>Bandeja de revisión de términos</h1>
      <p class="subtitle">Revisa búsquedas antes de bloquearlas en Google Ads. Bloquear es la excepción, no la regla.</p>
    </div>
    <div class="controls">
      <label for="range">Rango</label>
      <select id="range">
        <option value="YESTERDAY">Ayer</option>
        <option value="LAST_7_DAYS" selected>7 días</option>
        <option value="LAST_14_DAYS">14 días</option>
        <option value="LAST_30_DAYS">30 días</option>
      </select>
      <button id="refresh">Actualizar</button>
      <button class="secondary" disabled>Próxima fase: confirmar decisión</button>
    </div>
  </section>

  <section class="summary" aria-label="Resumen">
    <div class="metric"><strong id="mTotal">0</strong><span>Términos revisados</span></div>
    <div class="metric"><strong id="mDecision">0</strong><span>Necesitan tu decisión</span></div>
    <div class="metric"><strong id="mCaution">0</strong><span>Revisar con cuidado</span></div>
    <div class="metric"><strong id="mProtected">0</strong><span>Protegidos</span></div>
    <div class="metric"><strong id="mBlocked">0</strong><span>Ya bloqueados</span></div>
  </section>

  <p id="status" class="status-line">Cargando bandeja...</p>

  <section class="section" id="decisionSection">
    <div class="section-head">
      <div>
        <h2>Necesitan tu decisión</h2>
        <p>Estos términos requieren revisión humana antes de cualquier acción.</p>
      </div>
      <span class="count" id="decisionCount">0</span>
    </div>
    <div id="decisionBody"></div>
  </section>

  <details class="section" id="cautionSection">
    <summary class="section-head">
      <div>
        <h2>Revisar con cuidado</h2>
        <p>Cuidado: aquí hay señales mixtas. Bloquear podría costarte clientes.</p>
      </div>
      <span class="count" id="cautionCount">0</span>
    </summary>
    <div id="cautionBody"></div>
  </details>

  <details class="section" id="protectedSection">
    <summary class="section-head">
      <div>
        <h2>Protegidos · no se tocan</h2>
        <p>Estos NO se tocan: son tu marca, comida tailandesa, búsquedas útiles o términos ya protegidos.</p>
      </div>
      <span class="count" id="protectedCount">0</span>
    </summary>
    <div id="protectedBody"></div>
  </details>
</main>

<footer class="footer">
  <div class="footer-inner">Solo bloqueamos términos sin pedidos y con suficientes clics. Tu marca, comida tailandesa y búsquedas útiles están protegidas. Todo se aplicará uno por uno en una fase posterior.</div>
</footer>

<script>
"use strict";

var expandedTerm = null;

function el(id) { return document.getElementById(id); }

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function money(value) {
  var amount = Number(value || 0);
  return "$" + amount.toLocaleString("es-MX", { maximumFractionDigits: 0 });
}

function number(value) {
  return Number(value || 0).toLocaleString("es-MX");
}

function stateLabel(state) {
  var labels = {
    listo_para_bloquear: "Listo para revisar bloqueo",
    competidor_por_confirmar: "Restaurante o negocio externo por confirmar",
    revisar_con_cuidado: "Revisar con cuidado",
    datos_insuficientes: "Datos insuficientes",
    protegido: "Protegido",
    bloqueado: "Ya bloqueado",
    monitoreo: "Monitoreo"
  };
  return labels[state] || "Monitoreo";
}

function stateClass(state) {
  var classes = {
    listo_para_bloquear: "ready",
    competidor_por_confirmar: "confirm",
    revisar_con_cuidado: "caution",
    datos_insuficientes: "caution",
    protegido: "protected",
    bloqueado: "blocked",
    monitoreo: "blocked"
  };
  return classes[state] || "blocked";
}

function humanReason(item) {
  if (item.state === "competidor_por_confirmar") {
    return "Parece otro restaurante o negocio en Mérida. Hugo debe decidir si conviene bloquearlo.";
  }
  if (item.state === "revisar_con_cuidado") {
    var text = "Algunas personas pidieron cómo llegar, llamaron o interactuaron en Maps. Puede ser un cliente real comparando opciones.";
    if (String(item.term || "").toLowerCase().indexOf("hacienda teya") >= 0) {
      return "Restaurante externo con señales locales. Requiere revisión humana. " + text;
    }
    return text;
  }
  return item.reason_human || "Sin nota adicional.";
}

function whatHappened(item) {
  return number(item.clicks) + " clics &middot; " + money(item.cost_mxn) + " &middot; " + number(item.conversions) + " pedidos";
}

function rowHtml(item) {
  var termKey = encodeURIComponent(String(item.term || ""));
  var open = expandedTerm === termKey;
  var label = stateLabel(item.state);
  var html = "<tr>" +
    "<td data-label='Término'><div class='term'>" + esc(item.term) + "</div><div class='campaign'>" + esc(item.campaign) + "</div></td>" +
    "<td data-label='Qué pasó' class='what'>" + whatHappened(item) + "</td>" +
    "<td data-label='Por qué aparece aquí' class='reason'>" + esc(humanReason(item)) + "</td>" +
    "<td data-label='Estado'><span class='tag " + stateClass(item.state) + "'>" + esc(label) + "</span><br><button class='secondary' data-detail='" + termKey + "'>Ver detalle</button></td>" +
    "</tr>";
  if (open) {
    html += detailRowHtml(item);
  }
  return html;
}

function detailRowHtml(item) {
  return "<tr class='detail-row'><td colspan='4'><div class='detail-box'>" +
    "<div><b>Lectura</b>" + esc(stateLabel(item.state)) + "</div>" +
    "<div><b>Piso de datos</b>" + (item.enough_data ? "Suficiente" : "Insuficiente") + "</div>" +
    "<div><b>Permiso visual</b>" + (item.block_allowed ? "Requiere revisión uno por uno en fase posterior" : "No se puede bloquear desde esta pantalla") + "</div>" +
    "</div></td></tr>";
}

function tableHtml(items, emptyText) {
  if (!items.length) return "<div class='empty'>" + esc(emptyText) + "</div>";
  return "<table><thead><tr><th>Término</th><th>Qué pasó</th><th>Por qué aparece aquí</th><th>Estado</th></tr></thead><tbody>" +
    items.map(rowHtml).join("") +
    "</tbody></table>";
}

function bindDetailButtons() {
  document.querySelectorAll("[data-detail]").forEach(function (button) {
    button.addEventListener("click", function () {
      openDetail({ key: button.getAttribute("data-detail") });
    });
  });
}

function openDetail(item) {
  expandedTerm = expandedTerm === item.key ? null : item.key;
  if (window.__lastPreviewData) render(window.__lastPreviewData);
}

function closeDetail() {
  expandedTerm = null;
  if (window.__lastPreviewData) render(window.__lastPreviewData);
}

function setMetric(id, value) {
  el(id).textContent = number(value);
}

function render(data) {
  window.__lastPreviewData = data;
  var items = data.items || [];
  var counts = data.state_counts || {};

  var decisionItems = items.filter(function (item) {
    return item.state === "listo_para_bloquear" || item.state === "competidor_por_confirmar";
  });
  var cautionItems = items.filter(function (item) {
    return item.state === "revisar_con_cuidado" || item.state === "datos_insuficientes";
  });
  var protectedItems = items.filter(function (item) {
    return item.state === "protegido" || item.state === "bloqueado" || item.state === "monitoreo";
  });

  setMetric("mTotal", data.total || items.length);
  setMetric("mDecision", decisionItems.length);
  setMetric("mCaution", cautionItems.length);
  setMetric("mProtected", counts.protegido || 0);
  setMetric("mBlocked", counts.bloqueado || 0);
  el("decisionCount").textContent = number(decisionItems.length);
  el("cautionCount").textContent = number(cautionItems.length);
  el("protectedCount").textContent = number(protectedItems.length);

  renderSection("decisionBody", decisionItems, "Hoy no hay términos seguros para bloquear.");
  renderSection("cautionBody", cautionItems, "No hay términos con señales mixtas en este rango.");
  renderSection("protectedBody", protectedItems, "No hay términos protegidos para mostrar.");

  var floor = data.data_floor || {};
  el("status").textContent = "Datos solo lectura. Piso: " + number(floor.clicks_min || 0) + " clics y " + money(floor.cost_min_mxn || 0) + ".";
  bindDetailButtons();
}

function renderSection(targetId, items, emptyText) {
  el(targetId).innerHTML = tableHtml(items, emptyText);
}

function loadTerms() {
  var range = el("range").value;
  var url = "/negativos/preview-v2?date_range=" + encodeURIComponent(range);
  el("status").textContent = "Cargando bandeja...";
  fetch(url)
    .then(function (response) { return response.json(); })
    .then(function (data) {
      if (data.status !== "success") {
        el("status").textContent = "No se pudo cargar la bandeja.";
        return;
      }
      expandedTerm = null;
      render(data);
    })
    .catch(function () {
      el("status").textContent = "Error de red al cargar la bandeja.";
    });
}

el("refresh").addEventListener("click", loadTerms);
el("range").addEventListener("change", loadTerms);
loadTerms();
</script>
</body>
</html>"""


@router.get("/negativos", response_class=HTMLResponse)
async def negativos_ui():
    """Sirve la bandeja read-only de revisión de términos."""
    return HTMLResponse(content=_PAGE)
