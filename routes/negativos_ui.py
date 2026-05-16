"""
Mini-app web de revision de search terms -> agregar negativos a Google Ads.

GET /negativos  -> pagina HTML autocontenida (sin build, sin dependencias).

La pagina es publica (no contiene secretos). El token de acceso lo escribe
el usuario en runtime y se guarda en localStorage del navegador; se manda
como header X-API-Token solo en la escritura (/execute-optimization).
Lectura (/search-terms) es abierta, consistente con el resto de endpoints.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Negativos - Thai Thai Ads</title>
<style>
  :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  body { margin: 0; padding: 1.2rem; background: #fafafa; color: #1a1a1a; }
  h1 { font-size: 1.25rem; margin: 0 0 1rem; }
  .bar { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap; margin-bottom: 1rem; }
  select, input, button { font: inherit; padding: .45rem .6rem; border: 1px solid #ccc; border-radius: 6px; }
  button { background: #d33; color: #fff; border: 0; cursor: pointer; }
  button.secondary { background: #555; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  a { color: #06c; cursor: pointer; }
  table { border-collapse: collapse; width: 100%; background: #fff; }
  th, td { padding: .45rem .6rem; border-bottom: 1px solid #eee; text-align: left; font-size: .9rem; }
  th { background: #f0f0f0; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.cand { background: #fde0e0; }
  tr.conv { background: #e0f0e0; }
  #meta { color: #666; font-size: .85rem; }
  #confirm { background: #fff8e1; border: 1px solid #f0d000; padding: .8rem; border-radius: 6px; margin: 1rem 0; }
  .warn { color: #b30000; font-weight: 600; }
  .ok { color: #0a7a0a; } .err { color: #b30000; }
  #results div { padding: .25rem 0; font-size: .9rem; }
</style>
</head>
<body>
<h1>Search Terms &rarr; Negativos (BROAD, nivel campana)</h1>

<div id="gate" hidden>
  <p>Pega tu token de acceso:</p>
  <input id="tokenInput" type="password" size="44" autocomplete="off">
  <button id="tokenSave">Guardar</button>
</div>

<div id="app" hidden>
  <div class="bar">
    <label>Rango:
      <select id="range">
        <option>LAST_7_DAYS</option>
        <option>TODAY</option>
        <option>YESTERDAY</option>
        <option>LAST_14_DAYS</option>
        <option>LAST_30_DAYS</option>
        <option>THIS_MONTH</option>
        <option>LAST_MONTH</option>
      </select>
    </label>
    <button id="load" class="secondary">Cargar</button>
    <span id="meta"></span>
    <a id="logout">borrar token</a>
  </div>

  <div id="tableWrap"></div>
  <button id="addBtn" hidden>Agregar como negativos</button>
  <div id="confirm" hidden></div>
  <div id="results"></div>
</div>

<script>
"use strict";
var TOKEN_KEY = "tt_admin_token";
var rows = [];

function el(id) { return document.getElementById(id); }
function token() { return localStorage.getItem(TOKEN_KEY) || ""; }

function showGate(msg) {
  el("app").hidden = true;
  el("gate").hidden = false;
  if (msg) alert(msg);
}
function showApp() {
  el("gate").hidden = true;
  el("app").hidden = false;
}

el("tokenSave").onclick = function () {
  var v = el("tokenInput").value.trim();
  if (!v) return;
  localStorage.setItem(TOKEN_KEY, v);
  el("tokenInput").value = "";
  showApp();
};
el("logout").onclick = function () {
  localStorage.removeItem(TOKEN_KEY);
  showGate();
};

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

el("load").onclick = loadTerms;

function loadTerms() {
  el("confirm").hidden = true;
  el("results").innerHTML = "";
  el("addBtn").hidden = true;
  el("meta").textContent = "Cargando...";
  var r = el("range").value;
  fetch("/search-terms?date_range=" + encodeURIComponent(r))
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.status !== "success") { el("meta").textContent = "Error: " + (data.message || data.status); return; }
      rows = data.search_terms || [];
      el("meta").textContent = data.total + " terminos - " + data.negative_candidates + " candidatos a negativo";
      renderTable();
    })
    .catch(function (e) { el("meta").textContent = "Error de red: " + e; });
}

function renderTable() {
  if (!rows.length) { el("tableWrap").innerHTML = "<p>Sin search terms en este rango.</p>"; return; }
  var h = "<table><thead><tr><th></th><th>Query</th><th>Campana</th>" +
          "<th>Clics</th><th>Impr.</th><th>Costo</th><th>Conv.</th></tr></thead><tbody>";
  rows.forEach(function (t, i) {
    var cls = t.negative_candidate ? "cand" : (t.conversions > 0 ? "conv" : "");
    var disabled = t.campaign_id ? "" : "disabled title='sin campaign_id'";
    h += "<tr class='" + cls + "'>" +
      "<td><input type='checkbox' class='pick' data-i='" + i + "' " + disabled + "></td>" +
      "<td>" + esc(t.query) + "</td>" +
      "<td>" + esc(t.campaign_name) + "</td>" +
      "<td class='num'>" + t.clicks + "</td>" +
      "<td class='num'>" + t.impressions + "</td>" +
      "<td class='num'>$" + Number(t.cost).toFixed(2) + "</td>" +
      "<td class='num'>" + t.conversions + "</td></tr>";
  });
  h += "</tbody></table>";
  el("tableWrap").innerHTML = h;
  el("addBtn").hidden = false;
}

function selected() {
  var out = [];
  document.querySelectorAll(".pick:checked").forEach(function (cb) {
    out.push(rows[parseInt(cb.getAttribute("data-i"), 10)]);
  });
  return out;
}

el("addBtn").onclick = function () {
  var sel = selected();
  if (!sel.length) { alert("No seleccionaste ningun termino."); return; }
  var brand = sel.filter(function (t) { return /thai/i.test(t.query); });
  var html = "<strong>Vas a agregar " + sel.length + " negativo(s) BROAD:</strong><ul>";
  sel.forEach(function (t) {
    html += "<li>" + esc(t.query) + " &rarr; " + esc(t.campaign_name) + "</li>";
  });
  html += "</ul>";
  if (brand.length) {
    html += "<p class='warn'>OJO: " + brand.length +
      " termino(s) contienen \\"thai\\" - parecen de marca. NO bloquees tu propia marca.</p>";
  }
  html += "<button id='go'>Confirmar y enviar</button> " +
          "<button id='cancel' class='secondary'>Cancelar</button>";
  var c = el("confirm");
  c.innerHTML = html;
  c.hidden = false;
  el("cancel").onclick = function () { c.hidden = true; };
  el("go").onclick = function () { submit(sel); };
};

function submit(sel) {
  el("go").disabled = true;
  var actions = sel.map(function (t) {
    return { type: "block_keyword", keyword: t.query, campaign_id: String(t.campaign_id),
             campaign_name: t.campaign_name, reason: "manual UI negativos" };
  });
  fetch("/execute-optimization", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Token": token() },
    body: JSON.stringify({ actions: actions })
  }).then(function (resp) {
    if (resp.status === 401) { showGate("Token invalido o ausente. Pega un token valido."); return null; }
    return resp.json();
  }).then(function (data) {
    if (!data) return;
    el("confirm").hidden = true;
    var r = el("results");
    if (data.status !== "success") { r.innerHTML = "<div class='err'>Error: " + esc(data.message || "") + "</div>"; return; }
    var out = "<h3>Resultado</h3>";
    (data.results || []).forEach(function (x) {
      var ok = x.status === "executed";
      out += "<div class='" + (ok ? "ok" : "err") + "'>" +
        (ok ? "OK" : "FALLO") + " - " + esc(x.target || "") +
        (x.message ? " (" + esc(x.message) + ")" : "") + "</div>";
    });
    r.innerHTML = out;
    loadTerms();
  }).catch(function (e) {
    el("confirm").hidden = true;
    el("results").innerHTML = "<div class='err'>Error de red: " + esc(e) + "</div>";
  });
}

if (token()) showApp(); else showGate();
</script>
</body>
</html>"""


@router.get("/negativos", response_class=HTMLResponse)
async def negativos_ui():
    """Sirve la mini-app de revision de search terms."""
    return HTMLResponse(content=_PAGE)
