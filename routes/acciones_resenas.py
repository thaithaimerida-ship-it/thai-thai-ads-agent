"""Acciones de reseñas 5★ — Fase G.

GET  /acciones/resenas?token=X            → UI (token-gated; sin token → 403).
GET  /acciones/resenas/data?token=X&...   → JSON: tanda de pendientes 5★ con su borrador IA.
POST /acciones/resenas/publicar?token=X   → publica UNA respuesta (DRY_RUN default).

Las reseñas ≤4★ JAMÁS aparecen. Re-validación server-side en el POST. Sin batch.
"""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from engine import resenas_service

router = APIRouter(tags=["acciones-resenas"])


def _require_token(token: str) -> None:
    """Fail-closed: sin ACCIONES_TOKEN en el entorno o token que no coincide → 403."""
    expected = os.getenv("ACCIONES_TOKEN", "")
    if not expected or not secrets.compare_digest(token or "", expected):
        raise HTTPException(status_code=403, detail="Token inválido o ausente")


class PublicarBody(BaseModel):
    review_id: str
    texto: str
    reviewer: str = ""
    comment: str = ""
    energia: str = ""
    fuente: str = "generado"


@router.get("/acciones/resenas", response_class=HTMLResponse)
async def resenas_ui(token: str = ""):
    _require_token(token)
    return HTMLResponse(content=_PAGE.replace("__TOKEN__", token))


@router.get("/acciones/resenas/data")
async def resenas_data(token: str = "", offset: int = 0, limit: int = 10):
    _require_token(token)
    limit = max(1, min(int(limit or 10), 10))   # tandas de 10
    data = resenas_service.cargar_borradores_tanda(offset=max(0, int(offset or 0)), limit=limit)
    return JSONResponse(content=data)


@router.post("/acciones/resenas/publicar")
async def resenas_publicar(body: PublicarBody, token: str = ""):
    _require_token(token)
    res = resenas_service.publicar(
        review_id=body.review_id, texto=body.texto, reviewer=body.reviewer,
        comment=body.comment, energia=body.energia, fuente=body.fuente,
    )
    code = 200 if res.get("status") == "ok" else 409
    return JSONResponse(content=res, status_code=code)


_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reseñas 5★ — Responder</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;background:#f0ede6;color:#1a1a1a;margin:0;padding:14px 8px;}
  .box{max-width:640px;margin:0 auto;}
  .head{background:#fff;border:1px solid #ddd6c8;border-radius:10px;padding:14px 16px;margin-bottom:12px;}
  h1{font-size:18px;margin:0;font-weight:600;}
  .muted{color:#777;font-size:12px;}
  .pill{display:inline-block;font-size:11px;padding:2px 9px;border-radius:10px;font-weight:bold;}
  .dry{background:#E7F0FA;color:#114277;}
  .card{background:#fff;border:1px solid #e2dccf;border-radius:10px;padding:14px;margin-bottom:12px;}
  .stars{color:#b8860b;font-size:14px;} .rev{font-weight:bold;font-size:13px;}
  .comment{font-size:12.5px;color:#444;margin:6px 0;line-height:1.5;}
  .badges{margin:6px 0;}
  .b-ene{background:#EEEDFE;color:#534AB7;} .b-cie{background:#EAF3DE;color:#27500A;}
  .b-rev{background:#FCEBEB;color:#791F1F;}
  textarea{width:100%;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;padding:10px;font:13px Arial;min-height:80px;}
  .btn{display:inline-block;background:#2d2a26;color:#fff;border:none;border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer;font-weight:bold;margin-top:8px;}
  .btn[disabled]{opacity:.5;cursor:not-allowed;}
  .ok{color:#1a7f37;font-size:12px;font-weight:bold;margin-top:8px;}
  .err{color:#A32D2D;font-size:12px;margin-top:8px;}
  #more{display:block;width:100%;background:#fff;color:#2d2a26;border:1px solid #ccc;border-radius:8px;padding:11px;font-size:13px;cursor:pointer;font-weight:bold;}
  .footer{font-size:10.5px;color:#999;text-align:center;padding:12px;}
</style></head><body><div class="box">
<div class="head">
  <h1>⭐ Reseñas 5★ — responder con tu voz</h1>
  <p class="muted">Solo reseñas de 5 estrellas sin responder. Cada respuesta se publica una por una, tú la revisas antes. <span id="mode"></span></p>
</div>
<div id="list"></div>
<button id="more" style="display:none">Cargar 10 más</button>
<div class="footer">🔒 Nada se publica sin tu confirmación · las ≤4★ nunca aparecen aquí.</div>
</div>
<script>
"use strict";
var TOKEN="__TOKEN__", offset=0, total=0;
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function eneLabel(e){return {explosiva:"🔥 Explosiva",zen:"😊 Zen",vibrante:"😄 Vibrante",agradecimiento:"⭐ Agradecimiento"}[e]||e;}
function cardHtml(it){
  var rev = it.revisar_manual ? "<span class='pill b-rev'>⚠ revisar manualmente</span> " : "";
  var cie = it.grupo_cierre ? "<span class='pill b-cie'>cierre: "+esc(it.grupo_cierre)+"</span> " : "";
  var src = it.fuente==="banco" ? "<span class='pill b-cie'>banco</span> " : "";
  return "<div class='card' id='c-"+esc(it.review_id)+"'>"+
    "<div class='stars'>★★★★★</div><div class='rev'>"+esc(it.reviewer||"Cliente")+"</div>"+
    "<div class='comment'>"+(it.comment?esc(it.comment):"<i>(sin texto)</i>")+"</div>"+
    "<div class='badges'><span class='pill b-ene'>"+esc(eneLabel(it.energia))+"</span> "+cie+src+rev+"</div>"+
    "<textarea id='t-"+esc(it.review_id)+"'>"+esc(it.borrador)+"</textarea>"+
    "<button class='btn' onclick='pub(\""+esc(it.review_id)+"\")'>Publicar respuesta</button>"+
    "<div id='m-"+esc(it.review_id)+"'></div></div>";
}
function load(){
  fetch("/acciones/resenas/data?token="+encodeURIComponent(TOKEN)+"&offset="+offset+"&limit=10")
    .then(function(r){return r.json();}).then(function(d){
      total=d.total;
      document.getElementById("mode").innerHTML = d.dry_run ? "<span class='pill dry'>DRY-RUN: nada se publica de verdad</span>" : "";
      var list=document.getElementById("list");
      (d.items||[]).forEach(function(it){ list.insertAdjacentHTML("beforeend",cardHtml(it)); });
      offset += (d.items||[]).length;
      document.getElementById("more").style.display = d.hay_mas ? "block" : "none";
    });
}
function pub(id){
  var btn=document.querySelector("#c-"+CSS.escape(id)+" .btn");
  var ta=document.getElementById("t-"+id), msg=document.getElementById("m-"+id);
  btn.disabled=true; msg.innerHTML="Publicando…";
  fetch("/acciones/resenas/publicar?token="+encodeURIComponent(TOKEN),{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({review_id:id,texto:ta.value})
  }).then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
    .then(function(res){
      if(res.ok){ msg.innerHTML="<div class='ok'>✓ "+(res.j.dry_run?"Simulado (dry-run)":"Publicado")+"</div>"; ta.disabled=true; }
      else { btn.disabled=false; msg.innerHTML="<div class='err'>No se pudo: "+esc(res.j.motivo||"error")+"</div>"; }
    }).catch(function(){ btn.disabled=false; msg.innerHTML="<div class='err'>Error de red</div>"; });
}
document.getElementById("more").addEventListener("click",load);
load();
</script></body></html>"""
