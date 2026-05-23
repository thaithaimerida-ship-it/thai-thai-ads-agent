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
  tr.comp { background: #fef3c7; }
  tr.blocked { background: #fff1f1; }
  tr.review { background: #fff7d6; }
  tr.protected { background: #e9f7ee; }
  tr.ready { background: #e8f8e8; }
  h2.sec { font-size: 1.05rem; margin: 1.4rem 0 .4rem; }
  p.help { color: #666; font-size: .85rem; margin: 0 0 .5rem; }
  #meta { color: #666; font-size: .85rem; }
  #confirm { background: #fff8e1; border: 1px solid #f0d000; padding: .8rem; border-radius: 6px; margin: 1rem 0; }
  .warn { color: #b30000; font-weight: 600; }
  .ok { color: #0a7a0a; } .err { color: #b30000; }
  #results div { padding: .25rem 0; font-size: .9rem; }
  #banner { background: #e0f5e0; border: 2px solid #1f9d1f; color: #0a5a0a;
            padding: 1rem 1.2rem; border-radius: 8px; margin: 1rem 0;
            font-size: 1.05rem; line-height: 1.5; }
  #banner.partial { background: #fff8e1; border-color: #f0c000; color: #7a5a00; }
  tr.done { opacity: .5; }
  tr.done td { text-decoration: line-through; }
  .mt { display: inline-block; font-size: .7rem; font-weight: 700;
        padding: .05rem .35rem; border-radius: 4px; background: #eef;
        color: #225; border: 1px solid #ccd; vertical-align: middle; }
  .badge { display: inline-block; font-size: .7rem; font-weight: 700;
        padding: .05rem .35rem; border-radius: 4px; background: #f5f5f5;
        color: #333; border: 1px solid #ddd; vertical-align: middle; }
  .reason { color: #666; font-size: .8rem; }
</style>
</head>
<body>
<h1>Search Terms &rarr; Negativos (match type por termino: EXACT / PHRASE)</h1>

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
  <div id="banner" hidden></div>
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

// Match type aplicable que envia el clasificador (suggested_match_type).
// Solo EXACT/PHRASE son negativizables desde /negativos; BROAD/None => null
// (no seleccionable). El servidor /execute-optimization fail-closea igual.
function applyMt(t) {
  var m = String(t.suggested_match_type || "").toUpperCase();
  return (m === "EXACT" || m === "PHRASE") ? m : null;
}

function canPick(t) {
  return t.negative_allowed === true &&
    !!applyMt(t) &&
    t.already_negative === false &&
    !!t.campaign_id;
}

function blockReason(t) {
  if (t.already_negative === true) return "Ya negativo";
  if (t.negative_allowed === true && !applyMt(t)) return "Match type no permitido";
  if (t.negative_allowed === true && !t.campaign_id) return "Falta campaign_id";
  if (t.negative_allowed === true && t.already_negative !== false) return "Estado de negativo no confiable";
  if (t.conversion_quality === "unknown") return "Conversion no identificada";
  if (t.conversion_quality === "money_action") return "Tuvo accion de dinero";
  if (!t.campaign_id) return "Falta campaign_id";
  if (!applyMt(t) && t.semantic_class === "red_safe") return "Match type no permitido";
  if (t.base_negative_eligible !== true && t.semantic_class === "red_safe") return "No cumple elegibilidad base";
  if (t.semantic_class === "external_entity_review") return "Entidad ajena no curada: revisar";
  if (t.semantic_class === "ambiguous_useful") return "Puede traer clientes";
  if (t.semantic_class === "brand_protected" || t.semantic_class === "thai_intent") return "Protegido";
  return "Monitoreo";
}

function sectionFor(t) {
  if (t.already_negative === true) return "already";
  if (canPick(t)) return "ready";
  if (t.semantic_class === "red_safe") return "blocked";
  if (t.semantic_class === "external_entity_review") return "review";
  if (t.semantic_class === "ambiguous_useful") return "ambiguous";
  if (t.semantic_class === "brand_protected" || t.semantic_class === "thai_intent") return "protected";
  return "monitoring";
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
      el("meta").textContent = data.total + " terminos - " + data.negative_candidates +
        " candidatos a negativo - " + (data.competitor_terms || 0) + " de competidores";
      renderTable();
    })
    .catch(function (e) { el("meta").textContent = "Error de red: " + e; });
}

var HEAD = "<table><thead><tr><th></th><th>Query</th><th>Campana</th>" +
           "<th>Clics</th><th>Impr.</th><th>Costo</th><th>Conv.</th><th>Estado</th></tr></thead><tbody>";

function legacyRowHtml(t, i, cls) {
  if (t.already_negative) {
    var note = t.negative_smart_uncertain ? " (Smart: efectividad incierta)" : "";
    var bb = t.blocked_by ? (esc(t.blocked_by.text) + " " + esc(t.blocked_by.match_type)) : "";
    return "<tr class='" + cls + " done' title='ya negativo: " + bb + note + "'>" +
      "<td>✅</td>" +
      "<td>" + esc(t.query) + " <small>✅ ya negativo" + note + "</small></td>" +
      "<td>" + esc(t.campaign_name) + "</td>" +
      "<td class='num'>" + t.clicks + "</td>" +
      "<td class='num'>" + t.impressions + "</td>" +
      "<td class='num'>$" + Number(t.cost).toFixed(2) + "</td>" +
      "<td class='num'>" + t.conversions + "</td></tr>";
  }
  var amt = applyMt(t);
  var disabled, badge;
  if (!t.campaign_id) {
    disabled = "disabled title='sin campaign_id'"; badge = "";
  } else if (!amt) {
    disabled = "disabled title='sin match type sugerido — no negativizable'"; badge = "";
  } else {
    disabled = ""; badge = " <span class='mt'>" + amt + "</span>";
  }
  return "<tr class='" + cls + "'>" +
    "<td></td>" +
    "<td>" + esc(t.query) + badge + "</td>" +
    "<td>" + esc(t.campaign_name) + "</td>" +
    "<td class='num'>" + t.clicks + "</td>" +
    "<td class='num'>" + t.impressions + "</td>" +
    "<td class='num'>$" + Number(t.cost).toFixed(2) + "</td>" +
    "<td class='num'>" + t.conversions + "</td></tr>";
}

function sectionHtml(title, help, items, cls) {
  if (!items.length) return "";
  var body = "";
  items.forEach(function (entry) {
    body += rowHtml(entry.term, entry.index, cls);
  });
  return "<h2 class='sec'>" + esc(title) + " (" + items.length + ")</h2>" +
    "<p class='help'>" + esc(help) + "</p>" +
    HEAD + body + "</tbody></table>";
}

function rowHtml(t, i, cls) {
  var amt = applyMt(t);
  var badge = amt ? " <span class='mt'>" + amt + "</span>" : "";
  var state = "<span class='badge'>" + esc(t.semantic_class || "sin clase") + "</span> " +
              "<span class='badge'>" + esc(t.conversion_quality || "sin conversion") + "</span><br>" +
              "<span class='reason'>" + esc(blockReason(t)) + "</span>";
  if (t.already_negative) {
    var note = t.negative_smart_uncertain ? " (Smart: efectividad incierta)" : "";
    var bb = t.blocked_by ? (esc(t.blocked_by.text) + " " + esc(t.blocked_by.match_type)) : "";
    return "<tr class='" + cls + " done' title='ya negativo: " + bb + note + "'>" +
      "<td></td>" +
      "<td>" + esc(t.query) + badge + " <small>Ya negativo" + note + "</small></td>" +
      "<td>" + esc(t.campaign_name) + "</td>" +
      "<td class='num'>" + t.clicks + "</td>" +
      "<td class='num'>" + t.impressions + "</td>" +
      "<td class='num'>$" + Number(t.cost).toFixed(2) + "</td>" +
      "<td class='num'>" + t.conversions + "</td>" +
      "<td>" + state + "</td></tr>";
  }
  var pick = canPick(t)
    ? "<input type='checkbox' class='pick' data-i='" + i + "'>"
    : "";
  return "<tr class='" + cls + "'>" +
    "<td>" + pick + "</td>" +
    "<td>" + esc(t.query) + badge + "</td>" +
    "<td>" + esc(t.campaign_name) + "</td>" +
    "<td class='num'>" + t.clicks + "</td>" +
    "<td class='num'>" + t.impressions + "</td>" +
    "<td class='num'>$" + Number(t.cost).toFixed(2) + "</td>" +
    "<td class='num'>" + t.conversions + "</td>" +
    "<td>" + state + "</td></tr>";
}

function renderTable() {
  if (!rows.length) {
    el("tableWrap").innerHTML = "<p>Sin search terms en este rango.</p>";
    el("addBtn").hidden = true;
    return;
  }
  var sections = {
    ready: [], blocked: [], review: [], ambiguous: [],
    protected: [], monitoring: [], already: []
  };
  rows.forEach(function (t, i) {
    sections[sectionFor(t)].push({ term: t, index: i });
  });
  el("tableWrap").innerHTML =
    sectionHtml("Listos para aplicar", "Unica seccion seleccionable. Requiere negative_allowed=true, EXACT/PHRASE, campaign_id y already_negative=false.", sections.ready, "ready") +
    sectionHtml("Rojo bloqueado", "Terminos rojos que no pasan alguna guarda de seguridad.", sections.blocked, "blocked") +
    sectionHtml("Ya negativos", "Terminos que ya tienen un negativo bloqueandolos.", sections.already, "done") +
    sectionHtml("Revisar entidad ajena", "Posibles restaurantes, negocios o lugares externos no curados. Sin checkbox.", sections.review, "review") +
    sectionHtml("Ambiguos / pueden traer clientes", "Genericos u otras cocinas que pueden representar demanda util. Sin checkbox.", sections.ambiguous, "comp") +
    sectionHtml("Protegidos", "Marca propia o intencion Thai clara. Sin checkbox.", sections.protected, "protected") +
    sectionHtml("Monitoreo", "Terminos neutrales. Sin checkbox.", sections.monitoring, "");
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

  // Google Ads: keyword maximo 80 caracteres. Los que excedan se EXCLUYEN
  // del envio a /execute-optimization; se avisa antes de confirmar.
  var tooLong = sel.filter(function (t) { return String(t.query).length > 80; });
  sel = sel.filter(function (t) { return String(t.query).length <= 80; });

  var warnHtml = "";
  if (tooLong.length) {
    warnHtml = "<p class='warn'>\\u26A0\\uFE0F " + tooLong.length +
      " termino(s) excluido(s) por ser demasiado largo(s) para Google Ads " +
      "(max. 80 caracteres):</p><ul>";
    tooLong.forEach(function (t) {
      warnHtml += "<li>" + esc(t.query) + " <em>(" + String(t.query).length +
        " car.)</em></li>";
    });
    warnHtml += "</ul>";
  }

  if (!sel.length) {
    var cw = el("confirm");
    cw.innerHTML = warnHtml +
      "<p>No queda ningun termino valido para enviar.</p>" +
      "<button id='cancel' class='secondary'>Cerrar</button>";
    cw.hidden = false;
    el("cancel").onclick = function () { cw.hidden = true; };
    return;
  }

  var brand = sel.filter(function (t) { return /thai/i.test(t.query); });
  var html = warnHtml +
    "<strong>Vas a agregar " + sel.length + " negativo(s):</strong><ul>";
  sel.forEach(function (t) {
    html += "<li>" + esc(t.query) + " &rarr; " + esc(t.campaign_name) +
            " <span class='mt'>" + (applyMt(t) || "?") + "</span></li>";
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
             campaign_name: t.campaign_name, match_type: applyMt(t),
             reason: "manual UI negativos" };
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
    var res = data.results || [];
    var okList = res.filter(function (x) { return x.status === "executed"; });
    var failList = res.filter(function (x) { return x.status !== "executed"; });

    // Banner prominente de exito (visible y claro, no solo filas OK)
    var b = el("banner");
    if (okList.length) {
      b.className = failList.length ? "partial" : "";
      b.innerHTML =
        "\\u2705 <strong>" + okList.length + " palabra(s) negativa(s) agregada(s) " +
        "exitosamente a Google Ads.</strong> Estas busquedas ya no activaran tus " +
        "anuncios en el futuro. Los terminos seguiran apareciendo en el historial " +
        "de los proximos 7 dias \\u2014 eso es normal." +
        (failList.length ? "<br><span class='warn'>" + failList.length +
          " no se pudo(eron) agregar (ver detalle abajo).</span>" : "");
      b.hidden = false;
      b.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      b.hidden = true;
    }

    // Detalle por termino
    var out = "<h3>Detalle</h3>";
    res.forEach(function (x) {
      var ok = x.status === "executed";
      out += "<div class='" + (ok ? "ok" : "err") + "'>" +
        (ok ? "OK" : "FALLO") + " - " + esc(x.target || "") +
        (x.message ? " (" + esc(x.message) + ")" : "") + "</div>";
    });
    r.innerHTML = out;

    // Marcar filas ya bloqueadas. NO se recarga la tabla: el historico no
    // cambia al instante y recargar borraria este feedback (bug anterior).
    var blocked = {};
    okList.forEach(function (x) { blocked[x.target] = true; });
    document.querySelectorAll(".pick").forEach(function (cb) {
      var t = rows[parseInt(cb.getAttribute("data-i"), 10)];
      if (t && blocked[t.query]) {
        var tr = cb.closest("tr");
        tr.className = "done";
        cb.checked = false;
        cb.disabled = true;
        cb.parentNode.textContent = "\\u2713";
      }
    });
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
