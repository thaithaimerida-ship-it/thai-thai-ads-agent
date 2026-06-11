"""Página de bloqueo de negativos confirmados — Fase B1.

GET  /acciones/bloqueo?term=X&token=Y     → UI (token-gated; sin token → 403).
POST /acciones/bloqueo/confirmar?token=Y  → bloquea UN término (DRY_RUN default).
POST /acciones/bloqueo/dejar?token=Y      → marca el término como válido (no toca Ads).

JAMÁS BROAD, JAMÁS batch, jamás campañas no marcadas. Re-validación server-side.
"""
from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from engine import negativos_service
from routes.acciones_resenas import _require_token

router = APIRouter(tags=["acciones-bloqueo"])


class ConfirmarBody(BaseModel):
    term: str
    campaign_ids: list[str] = []


class DejarBody(BaseModel):
    term: str


@router.get("/acciones/bloqueo", response_class=HTMLResponse)
async def bloqueo_ui(term: str = "", token: str = ""):
    _require_token(token)
    ctx = negativos_service.contexto_bloqueo(term)
    return HTMLResponse(content=render_bloqueo(ctx, token))


@router.post("/acciones/bloqueo/confirmar")
async def bloqueo_confirmar(body: ConfirmarBody, token: str = ""):
    _require_token(token)
    res = negativos_service.confirmar_bloqueo(body.term, body.campaign_ids)
    return JSONResponse(content=res, status_code=200 if res.get("status") == "ok" else 409)


@router.post("/acciones/bloqueo/dejar")
async def bloqueo_dejar(body: DejarBody, token: str = ""):
    _require_token(token)
    return JSONResponse(content=negativos_service.dejar(body.term))


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
