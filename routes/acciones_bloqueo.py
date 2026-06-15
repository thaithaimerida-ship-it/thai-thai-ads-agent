"""Página de bloqueo de negativos confirmados — Fase B1.

GET  /acciones/bloqueo?term=X&token=Y     → UI (token-gated; sin token → 403).
POST /acciones/bloqueo/confirmar?token=Y  → bloquea UN término (DRY_RUN default).
POST /acciones/bloqueo/dejar?token=Y      → marca el término como válido (no toca Ads).

JAMÁS BROAD, JAMÁS batch, jamás campañas no marcadas. Re-validación server-side.
"""
from __future__ import annotations

import html
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from engine import negativos_apply, negativos_service
from routes.acciones_resenas import _require_token

logger = logging.getLogger(__name__)


def _error_mensaje(exc: Exception) -> str:
    """Mensaje corto y seguro para la UI (sin secretos). Ej.: 'Error del servidor: [Errno 2]…'."""
    detalle = (str(exc).strip().splitlines() or [""])[0][:120] or type(exc).__name__
    return f"Error del servidor: {detalle}"

router = APIRouter(tags=["acciones-bloqueo"])


class ConfirmarBody(BaseModel):
    term: str
    campaign_ids: list[str] = []


class DejarBody(BaseModel):
    term: str


class ItemLoteBloqueo(BaseModel):
    term: str
    campaign_ids: list[str] = []


class LoteBloqueoBody(BaseModel):
    items: list[ItemLoteBloqueo] = []


@router.get("/acciones/bloqueo", response_class=HTMLResponse)
async def bloqueo_ui(term: str = "", token: str = ""):
    _require_token(token)
    ctx = negativos_service.contexto_bloqueo(term)
    return HTMLResponse(content=render_bloqueo(ctx, token))


_MOTIVO_MSG = {
    "termino_no_valido": "Término no válido (no es una decisión real)",
    "ya_bloqueado": "Ya estaba bloqueado",
    "sin_campanas_validas": "Sin campañas válidas para bloquear",
}


@router.post("/acciones/bloqueo/confirmar")
async def bloqueo_confirmar(body: ConfirmarBody, token: str = ""):
    """Bloquea UN término (re-validación server-side, DRY_RUN default). Devuelve SIEMPRE JSON con
    {ok, dry_run, mensaje, ...}. Lo consumen la bandeja (botón individual in-place) y la página
    individual; ambas leen el mismo JSON."""
    _require_token(token)
    try:
        res = negativos_service.confirmar_bloqueo(body.term, body.campaign_ids)
    except Exception as exc:  # NUNCA un 500 sin body JSON → el JS muestra el motivo real
        logger.exception("bloqueo_confirmar: fallo aplicando '%s'", body.term)
        return JSONResponse(content={"ok": False, "dry_run": negativos_apply.dry_run_negativos(),
                                     "mensaje": _error_mensaje(exc)}, status_code=500)
    ok = res.get("status") == "ok"
    dry = bool(res.get("dry_run", True))
    if ok:
        mensaje = "Simulado (dry-run) — no se bloqueó de verdad" if dry else "Bloqueado"
    else:
        motivo = res.get("motivo", "")
        mensaje = _MOTIVO_MSG.get(motivo, motivo or "No se pudo bloquear")
    return JSONResponse(content={**res, "ok": ok, "dry_run": dry, "mensaje": mensaje},
                        status_code=200 if ok else 409)


@router.post("/acciones/bloqueo/dejar")
async def bloqueo_dejar(body: DejarBody, token: str = ""):
    _require_token(token)
    return JSONResponse(content=negativos_service.dejar(body.term))


@router.get("/acciones/bloqueos", response_class=HTMLResponse)
async def bloqueos_bandeja(token: str = ""):
    """Bandeja: TODOS los candidatos a bloqueo, cada uno como tarjeta (igual que reseñas)."""
    _require_token(token)
    data = negativos_service.contextos_bandeja()
    return HTMLResponse(content=render_bandeja(data, token))


def _mensaje_resultado(ok: bool, dry: bool, motivo: str) -> str:
    if ok:
        return "Simulado (dry-run) — no se bloqueó de verdad" if dry else "Bloqueado"
    return _MOTIVO_MSG.get(motivo, motivo or "No se pudo bloquear")


@router.post("/acciones/bloqueos/lote")
async def bloqueos_lote(body: LoteBloqueoBody, token: str = ""):
    """Lote: bloquea la selección UNO POR UNO (mismas guardas), UN solo correo. Enriquece cada
    resultado con {ok, dry_run, mensaje} (aditivo) para que el JS actualice cada tarjeta al MISMO
    estado final que el flujo individual. No toca el correo único ni los candados del service."""
    _require_token(token)
    items = [{"term": i.term, "campaign_ids": i.campaign_ids} for i in body.items]
    try:
        res = negativos_service.confirmar_lote(items)
    except Exception as exc:  # NUNCA un 500 sin body JSON
        logger.exception("bloqueos_lote: fallo en el lote")
        return JSONResponse(content={"ok": False, "dry_run": negativos_apply.dry_run_negativos(),
                                     "mensaje": _error_mensaje(exc), "resultados": []}, status_code=500)
    dry = bool(res.get("dry_run", True))
    for r in res.get("resultados", []):
        r_ok = r.get("status") == "ok"
        r["ok"] = r_ok
        r["dry_run"] = dry
        r["mensaje"] = _mensaje_resultado(r_ok, dry, r.get("motivo", ""))
    res["ok"] = True  # la petición se procesó; el desglose va por término en `resultados`
    return JSONResponse(content=res)


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _variantes(n: int) -> str:
    n = int(n or 0)
    return f"{n} variante" if n == 1 else f"{n} variantes"


def render_bloqueo(ctx: dict, token: str) -> str:
    term = _esc(ctx.get("term"))
    variantes = ctx.get("variantes") or []
    var_html = " · ".join(f"<code>{_esc(v)}</code>" for v in variantes) or "<i>(sin variantes)</i>"
    filas = []
    for c in ctx.get("campanas") or []:
        cid = _esc(c.get("id"))
        disabled = "disabled" if not c.get("permitido") else ""
        checked = "checked" if c.get("premarcado") and c.get("permitido") else ""
        tipo = "EXACT (búsqueda)" if c.get("match_type") == "EXACT" else "theme (Smart)"
        nota = f"<div class='nota'>{_esc(c.get('nota'))}</div>" if c.get("nota") else ""
        filas.append(
            f"<label class='camp {'off' if not c.get('permitido') else ''}'>"
            f"<input type='checkbox' class='chk' value='{cid}' {checked} {disabled}> "
            f"<b>{_esc(c.get('name'))}</b> <span class='pill'>{_esc(tipo)}</span> "
            f"<span class='gasto'>${_esc(round(float(c.get('gasto') or 0)))}</span>{nota}</label>"
        )
    campos = "".join(filas) or "<div class='nota'>No se encontraron campañas para este término.</div>"
    dry = ctx.get("dry_run")
    dry_badge = "<span class='pill dry'>DRY-RUN: nada se aplica de verdad</span>" if dry else ""

    ya_ts = ctx.get("ya_bloqueado_ts")
    if ya_ts:
        fecha = _esc(str(ya_ts)[:10])
        estado = f"<div class='estado'>✓ Ya bloqueado el {fecha}. No es necesario volver a aplicarlo.</div>"
        confirm_dis = "disabled"
    else:
        estado = ""
        confirm_dis = ""

    return _PAGE.replace("__TERM__", term).replace("__TOKEN__", _esc(token)) \
        .replace("__VARS__", var_html).replace("__VARTXT__", _esc(_variantes(ctx.get("variantes_count", 0)))) \
        .replace("__GASTO__", str(round(float(ctx.get("gasto_total") or 0)))) \
        .replace("__CAMPOS__", campos).replace("__DRY__", dry_badge) \
        .replace("__ESTADO__", estado).replace("__CONFIRMDIS__", confirm_dis)


_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bloquear término — Thai Thai</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;background:#f0ede6;color:#1a1a1a;margin:0;padding:14px 8px;}
  .box{max-width:600px;margin:0 auto;}
  .card{background:#fff;border:1px solid #ddd6c8;border-radius:10px;padding:16px;margin-bottom:12px;}
  h1{font-size:18px;margin:0 0 4px;font-weight:600;}
  .muted{color:#777;font-size:12px;line-height:1.5;}
  code{background:#f6f3ec;border-radius:4px;padding:1px 5px;font-size:12px;}
  .pill{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:bold;background:#EAF3DE;color:#27500A;}
  .dry{background:#E7F0FA;color:#114277;}
  .term{font-size:20px;font-weight:bold;}
  .kpi{font-size:13px;color:#444;margin:8px 0;}
  .camp{display:block;border:1px solid #e2dccf;border-radius:8px;padding:11px 12px;margin:8px 0;font-size:13px;cursor:pointer;}
  .camp.off{opacity:.6;background:#faf7f2;cursor:not-allowed;}
  .gasto{float:right;color:#777;font-weight:bold;}
  .nota{color:#8a5a1f;font-size:11px;margin-top:5px;}
  .row{display:flex;gap:8px;margin-top:12px;}
  .btn{flex:1.4;background:#9b2f2f;color:#fff;border:none;border-radius:8px;padding:11px;font-size:14px;cursor:pointer;font-weight:bold;}
  .btn-sec{flex:1;background:#fff;color:#2d2a26;border:1px solid #ccc;border-radius:8px;padding:11px;font-size:14px;cursor:pointer;font-weight:bold;}
  .btn[disabled]{opacity:.5;cursor:not-allowed;}
  #msg{margin-top:10px;font-size:13px;font-weight:bold;}
  .ok{color:#1a7f37;} .err{color:#9b2f2f;}
  .estado{background:#EAF3DE;color:#27500A;border-radius:8px;padding:11px 12px;font-size:13px;font-weight:bold;margin-bottom:10px;}
  .footer{font-size:10.5px;color:#999;text-align:center;padding:12px;}
</style></head><body><div class="box">
<div class="card">
  <h1>🚫 Revisar y bloquear</h1>
  <p class="muted">Bloquear es la excepción. Revisa exactamente qué se aplicará antes de confirmar. __DRY__</p>
  <div class="term">"__TERM__"</div>
  <div class="kpi">__VARTXT__ · gasto acumulado <b>$__GASTO__</b></div>
  <div class="muted">Variantes: __VARS__</div>
</div>
<div class="card">
  __ESTADO__
  <p class="muted"><b>Qué se aplicará</b> (marca las campañas):</p>
  __CAMPOS__
  <div class="row">
    <button class="btn" id="confirmar" onclick="confirmar()" __CONFIRMDIS__>Confirmar bloqueo</button>
    <button class="btn-sec" onclick="dejar()">Dejar (es búsqueda válida)</button>
  </div>
  <div id="msg"></div>
</div>
<div class="footer">🔒 Nada se aplica sin tu confirmación · jamás BROAD, jamás en lote · marca protegida en Smart.</div>
</div>
<script>
"use strict";
var TERM="__TERM__", TOKEN="__TOKEN__";
function ids(){return Array.prototype.slice.call(document.querySelectorAll(".chk:checked")).map(function(c){return c.value;});}
function confirmar(){
  var b=document.getElementById("confirmar"), m=document.getElementById("msg");
  var sel=ids(); if(!sel.length){m.className="err";m.textContent="Marca al menos una campaña.";return;}
  b.disabled=true; m.className=""; m.textContent="Aplicando…";
  fetch("/acciones/bloqueo/confirmar?token="+encodeURIComponent(TOKEN),{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({term:TERM,campaign_ids:sel})})
   .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
   .then(function(res){ if(res.ok){m.className="ok";m.textContent="✓ "+(res.j.dry_run?"Simulado (dry-run)":"Bloqueado");}
     else{b.disabled=false;m.className="err";m.textContent="No se pudo: "+(res.j.motivo||"error");} })
   .catch(function(){b.disabled=false;m.className="err";m.textContent="Error de red";});
}
function dejar(){
  var m=document.getElementById("msg"); m.className=""; m.textContent="Guardando…";
  fetch("/acciones/bloqueo/dejar?token="+encodeURIComponent(TOKEN),{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({term:TERM})})
   .then(function(r){return r.json();}).then(function(j){m.className="ok";m.textContent="✓ Marcado como búsqueda válida. No se volverá a preguntar.";})
   .catch(function(){m.className="err";m.textContent="Error de red";});
}
</script></body></html>"""


# ── Bandeja (plural) ──────────────────────────────────────────────────────────
def _bandeja_card(ctx: dict, token: str) -> str:
    term_raw = ctx.get("term") or ""
    term = _esc(term_raw)
    n = ctx.get("variantes_count", 0)
    gasto = round(float(ctx.get("gasto_total") or 0))
    filas, search_ids = [], []
    for c in ctx.get("campanas") or []:
        nombre = _esc(c.get("name"))
        g = _esc(round(float(c.get("gasto") or 0)))
        if c.get("channel") == "SEARCH" and c.get("permitido"):
            search_ids.append(str(c.get("id")))
            filas.append(f"<div class='camp'>✓ <b>{nombre}</b> <span class='pill'>EXACT</span> <span class='gasto'>${g}</span></div>")
        else:
            nota = f"<div class='nota'>{_esc(c.get('nota'))}</div>" if c.get("nota") else ""
            filas.append(f"<div class='camp off'>{nombre} <span class='pill'>theme (Smart)</span> · individual <span class='gasto'>${g}</span>{nota}</div>")
    ya = ctx.get("ya_bloqueado_ts")
    estado = f"<div class='estado'>✓ Ya bloqueado el {_esc(str(ya)[:10])}</div>" if ya else ""
    ids_attr = _esc(",".join(search_ids))
    if ya:
        chk, row = "", ""  # ya bloqueado: nada que hacer
    elif search_ids:
        chk = (f"<label class='selrow'><input type='checkbox' class='sel' data-ids='{ids_attr}' onchange='upd()'> "
               "seleccionar para el lote (EXACT en búsqueda)</label>")
        # Botón individual: bloquea EN EL ACTO (fetch), sin navegar. Mismo término, EXACT en búsqueda.
        row = (f"<div class='row'><button class='btn' data-ids='{ids_attr}' onclick='bloquear(this)'>Bloquear</button>"
               f"<button class='btn-sec' onclick='dejar(this)'>Dejar</button></div>")
    else:
        chk = "<div class='nota'>Solo Smart — se aplica a mano en Google Ads (no hay negativo EXACT que aplicar aquí).</div>"
        row = f"<div class='row'><button class='btn-sec' onclick='dejar(this)'>Dejar</button></div>"
    return (f"<div class='card' data-term=\"{term}\">{chk}"
            f"<div class='term'>\"{term}\"</div>"
            f"<div class='kpi'>{_esc(_variantes(n))} · gasto <b>${gasto}</b></div>{estado}"
            f"<div class='camps'>{''.join(filas)}</div>"
            f"{row}"
            f"<div class='msg'></div></div>")


def render_bandeja(data: dict, token: str) -> str:
    items = data.get("items") or []
    cards = "".join(_bandeja_card(c, token) for c in items) or \
        "<div class='empty'>No hay candidatos a bloqueo ahora mismo. 🎉</div>"
    dry = "<span class='pill dry'>DRY-RUN: nada se aplica de verdad</span>" if data.get("dry_run") else ""
    return _BANDEJA.replace("__TOKEN__", _esc(token)).replace("__CARDS__", cards).replace("__DRY__", dry)


_BANDEJA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bandeja de bloqueos — Thai Thai</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;background:#f0ede6;color:#1a1a1a;margin:0;padding:14px 8px;}
  .box{max-width:600px;margin:0 auto;}
  .head{background:#fff;border:1px solid #ddd6c8;border-radius:10px;padding:14px 16px;margin-bottom:12px;}
  h1{font-size:18px;margin:0 0 4px;font-weight:600;} .muted{color:#777;font-size:12px;line-height:1.5;}
  .pill{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:bold;background:#EAF3DE;color:#27500A;}
  .dry{background:#E7F0FA;color:#114277;}
  .card{background:#fff;border:1px solid #e2dccf;border-radius:10px;padding:14px;margin-bottom:12px;}
  .selrow{display:block;font-size:11px;color:#555;margin-bottom:8px;cursor:pointer;} .selrow input{margin-right:5px;vertical-align:middle;}
  .term{font-size:17px;font-weight:bold;} .kpi{font-size:12.5px;color:#444;margin:5px 0;}
  .camp{border:1px solid #e2dccf;border-radius:8px;padding:9px 11px;margin:6px 0;font-size:12.5px;}
  .camp.off{opacity:.75;background:#faf7f2;} .gasto{float:right;color:#777;font-weight:bold;} .nota{color:#8a5a1f;font-size:11px;margin-top:4px;}
  .estado{background:#EAF3DE;color:#27500A;border-radius:8px;padding:9px 11px;font-size:12.5px;font-weight:bold;margin:6px 0;}
  .row{display:flex;gap:8px;margin-top:10px;}
  .btn{flex:1.5;background:#9b2f2f;color:#fff;text-decoration:none;text-align:center;border:none;border-radius:8px;padding:10px;font-size:13px;font-weight:bold;cursor:pointer;}
  .btn:disabled{background:#c2b8b0;color:#fff;cursor:not-allowed;}
  .btn-sec{flex:1;background:#fff;color:#2d2a26;border:1px solid #ccc;border-radius:8px;padding:10px;font-size:13px;cursor:pointer;font-weight:bold;}
  .msg{font-size:12px;margin-top:7px;font-weight:bold;} .ok{color:#1a7f37;} .err{color:#9b2f2f;}
  #lote{display:none;position:sticky;bottom:8px;width:100%;background:#9b2f2f;color:#fff;border:none;border-radius:8px;padding:13px;font-size:14px;cursor:pointer;font-weight:bold;margin:10px 0 4px;box-shadow:0 6px 16px rgba(0,0,0,.2);}
  #lote[disabled]{background:#c89b9b;cursor:not-allowed;} #loteMsg{font-size:12px;margin:4px 0 8px;font-weight:bold;}
  .empty{background:#fff;border:1px solid #e2dccf;border-radius:10px;padding:20px;text-align:center;color:#777;}
  .footer{font-size:10.5px;color:#999;text-align:center;padding:12px;}
</style></head><body><div class="box">
<div class="head"><h1>🚫 Bandeja de bloqueos</h1>
<p class="muted">Todos los candidatos a bloqueo. Marca varios y usa el botón, o revisa uno por uno. El negativo EXACT (búsqueda) va en el lote; el Smart se aplica a mano (individual). __DRY__</p></div>
<div id="list">__CARDS__</div>
<button id="lote" disabled onclick="bloquearLote()">Bloquear seleccionados (0)</button>
<div id="loteMsg"></div>
<div class="footer">🔒 Nada se aplica sin tu confirmación · jamás BROAD, jamás campañas no marcadas · Smart a mano · marca protegida.</div>
</div>
<script>
"use strict";
var T="__TOKEN__", MAXSEL=10;
function el(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function cssesc(s){return String(s).replace(/["\\]/g,"\\$&");}
function _checks(){return Array.prototype.slice.call(document.querySelectorAll(".sel"));}
function _sel(){return _checks().filter(function(c){return c.checked && !c.disabled;});}
// Estado final de una tarjeta bloqueada (individual o lote): checkbox off+disabled+data-done,
// botón gris. data-done evita que upd() lo rehabilite por la lógica de MAXSEL.
function _hecho(card){ var cb=card.querySelector(".sel"), btn=card.querySelector("button.btn");
  if(cb){cb.checked=false;cb.disabled=true;cb.setAttribute("data-done","1");} if(btn){btn.disabled=true;} }
function upd(){
  var sel=_sel();
  _checks().forEach(function(c){ if(!c.checked && !c.hasAttribute("data-done")) c.disabled=(sel.length>=MAXSEL); });
  var b=el("lote"); b.textContent="Bloquear seleccionados ("+sel.length+")"; b.disabled=sel.length===0; b.style.display=sel.length>0?"block":"none";
  el("loteMsg").innerHTML = sel.length>=MAXSEL ? "<span style='color:#8b5e14'>Máximo 10 por lote.</span>":"";
}
function bloquearLote(){
  var sel=_sel(); if(!sel.length) return;
  var items=sel.map(function(c){ var card=c.closest(".card"); return {term:card.getAttribute("data-term"), campaign_ids:(c.getAttribute("data-ids")||"").split(",").filter(Boolean)}; });
  var b=el("lote"); b.disabled=true; b.textContent="Aplicando…"; el("loteMsg").textContent="Aplicando "+items.length+"…";
  fetch("/acciones/bloqueos/lote?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:items})})
   .then(function(r){return r.json();})
   .then(function(d){
     if(d.ok===false){ el("loteMsg").innerHTML="<span class='err'>"+esc(d.mensaje||"No se pudo aplicar el lote")+"</span>"; upd(); return; }
     (d.resultados||[]).forEach(function(r){ var card=document.querySelector('.card[data-term="'+cssesc(r.term)+'"]'); if(!card) return;
       var msg=card.querySelector(".msg");
       if(r.ok){ // MISMO estado final que el flujo individual: botón gris + leyenda + checkbox off
         msg.innerHTML="<span class='ok'>✓ "+esc(r.mensaje||(r.dry_run?"Simulado (dry-run) — no se bloqueó de verdad":"Bloqueado"))+"</span>";
         _hecho(card); }
       else { msg.innerHTML="<span class='err'>No se pudo: "+esc(r.mensaje||r.motivo||"error")+"</span>"; } });
     el("loteMsg").innerHTML="<span class='ok'>"+d.bloqueados+" "+(d.dry_run?"simulados":"bloqueados")+(d.fallidos?(" · "+d.fallidos+" fallaron"):"")+"</span>";
     upd();
   })
   .catch(function(){ el("loteMsg").innerHTML="<span class='err'>Error de red</span>"; upd(); });
}
function dejar(btn){ var card=btn.closest(".card"); var term=card.getAttribute("data-term"); var msg=card.querySelector(".msg"); msg.className="msg"; msg.textContent="Guardando…";
  fetch("/acciones/bloqueo/dejar?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({term:term})})
   .then(function(r){return r.json();}).then(function(j){ msg.innerHTML="<span class='ok'>✓ Marcado como válido. No se vuelve a preguntar.</span>"; var cb=card.querySelector(".sel"); if(cb){cb.checked=false;cb.disabled=true;cb.setAttribute("data-done","1");} upd(); })
   .catch(function(){ msg.innerHTML="<span class='err'>Error de red</span>"; }); }
function bloquear(btn){
  var card=btn.closest(".card"); var term=card.getAttribute("data-term"); var msg=card.querySelector(".msg");
  var idsAttr=btn.getAttribute("data-ids")||""; var ids=idsAttr.split(",").filter(Boolean);
  btn.disabled=true; btn.textContent="Bloqueando…"; msg.className="msg"; msg.textContent="";
  fetch("/acciones/bloqueo/confirmar?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({term:term,campaign_ids:ids})})
   .then(function(r){ return r.json().then(function(j){ return {http:r.status, j:j}; }); })
   .then(function(res){
     var j=res.j||{};
     if(j.ok){
       btn.textContent="Bloquear";
       msg.innerHTML="<span class='ok'>✓ "+esc(j.mensaje||(j.dry_run?"Simulado (dry-run) — no se bloqueó de verdad":"Bloqueado"))+"</span>";
       _hecho(card); upd();  // botón gris + checkbox off/disabled (estado final único)
     } else {
       var motivo=j.motivo||"", txt=j.mensaje||j.detail||("HTTP "+res.http);
       msg.innerHTML="<span class='err'>No se pudo: "+esc(txt)+"</span>";
       if(motivo==="ya_bloqueado"){ btn.textContent="Bloquear"; _hecho(card); upd(); }  // ya bloqueado → estado final
       else { btn.disabled=false; btn.textContent="Bloquear"; }                          // rehabilita
     }
   })
   .catch(function(){ msg.innerHTML="<span class='err'>Error de red</span>"; btn.disabled=false; btn.textContent="Bloquear"; });
}
</script></body></html>"""
