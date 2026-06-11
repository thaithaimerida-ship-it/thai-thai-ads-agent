"""Acciones de reseñas 5★ — Fase G.

GET  /acciones/resenas?token=X            → UI. Las tarjetas (estrellas/autor/texto) se
                                            renderizan SERVER-SIDE (nunca página en blanco);
                                            el borrador IA llega después vía /data.
GET  /acciones/resenas/contenido?token=X  → JSON: contenido de reseñas (rápido, sin IA).
GET  /acciones/resenas/data?token=X       → JSON: borradores IA de la tanda (lento).
POST /acciones/resenas/publicar?token=X   → publica UNA respuesta (DRY_RUN default).

Las reseñas ≤4★ JAMÁS aparecen. Re-validación server-side en el POST. Sin batch.
"""
from __future__ import annotations

import html
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


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _clamp(offset, limit):
    return max(0, int(offset or 0)), max(1, min(int(limit or 10), 10))


class PublicarBody(BaseModel):
    review_id: str
    texto: str
    reviewer: str = ""
    comment: str = ""
    energia: str = ""
    fuente: str = "generado"


def _card_html(it: dict) -> str:
    rid = _esc(it.get("review_id"))
    comentario = _esc(it.get("comment")) if it.get("comment") else "<i>(sin texto)</i>"
    return (f"<div class='card' id='c-{rid}'>"
            f"<div class='stars'>★★★★★</div><div class='rev'>{_esc(it.get('reviewer') or 'Cliente')}</div>"
            f"<div class='comment'>{comentario}</div>"
            f"<div class='badges' id='b-{rid}'></div>"
            f"<textarea id='t-{rid}' disabled>generando borrador…</textarea>"
            f"<button class='btn' id='btn-{rid}' disabled onclick=\"pub('{rid}')\">Publicar respuesta</button>"
            f"<div class='msg' id='m-{rid}'></div></div>")


@router.get("/acciones/resenas", response_class=HTMLResponse)
async def resenas_ui(token: str = "", offset: int = 0, limit: int = 10):
    _require_token(token)
    off, lim = _clamp(offset, limit)
    data = resenas_service.cargar_resenas_tanda(offset=off, limit=lim)
    cards = "".join(_card_html(it) for it in data["items"]) or \
        "<div class='empty'>No hay reseñas 5★ sin responder ahora mismo. 🎉</div>"
    dry = "<span class='pill dry'>DRY-RUN: nada se publica de verdad</span>" if data["dry_run"] else ""
    return HTMLResponse(
        _PAGE.replace("__TOKEN__", _esc(token)).replace("__CARDS__", cards).replace("__DRY__", dry)
        .replace("__INITN__", str(len(data["items"]))).replace("__MORE__", "block" if data["hay_mas"] else "none")
    )


@router.get("/acciones/resenas/contenido")
async def resenas_contenido(token: str = "", offset: int = 0, limit: int = 10):
    _require_token(token)
    off, lim = _clamp(offset, limit)
    return JSONResponse(content=resenas_service.cargar_resenas_tanda(offset=off, limit=lim))


@router.get("/acciones/resenas/data")
async def resenas_data(token: str = "", offset: int = 0, limit: int = 10):
    _require_token(token)
    off, lim = _clamp(offset, limit)
    return JSONResponse(content=resenas_service.cargar_borradores_tanda(offset=off, limit=lim))


@router.post("/acciones/resenas/publicar")
async def resenas_publicar(body: PublicarBody, token: str = ""):
    _require_token(token)
    res = resenas_service.publicar(
        review_id=body.review_id, texto=body.texto, reviewer=body.reviewer,
        comment=body.comment, energia=body.energia, fuente=body.fuente,
    )
    return JSONResponse(content=res, status_code=200 if res.get("status") == "ok" else 409)


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
  .badges{margin:6px 0;min-height:1px;}
  .b-ene{background:#EEEDFE;color:#534AB7;} .b-cie{background:#EAF3DE;color:#27500A;}
  .b-rev{background:#FCEBEB;color:#791F1F;}
  textarea{width:100%;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;padding:10px;font:13px Arial;min-height:80px;}
  textarea[disabled]{color:#999;font-style:italic;background:#faf7f2;}
  .btn{display:inline-block;background:#2d2a26;color:#fff;border:none;border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer;font-weight:bold;margin-top:8px;}
  .btn[disabled]{opacity:.45;cursor:not-allowed;}
  .ok{color:#1a7f37;font-size:12px;font-weight:bold;margin-top:8px;}
  .err{color:#A32D2D;font-size:12px;margin-top:8px;}
  .empty{background:#fff;border:1px solid #e2dccf;border-radius:10px;padding:20px;text-align:center;color:#777;}
  #more{display:block;width:100%;background:#fff;color:#2d2a26;border:1px solid #ccc;border-radius:8px;padding:11px;font-size:13px;cursor:pointer;font-weight:bold;}
  .footer{font-size:10.5px;color:#999;text-align:center;padding:12px;}
</style></head><body><div class="box">
<div class="head">
  <h1>⭐ Reseñas 5★ — responder con tu voz</h1>
  <p class="muted">Solo reseñas de 5 estrellas sin responder. Cada respuesta se publica una por una, tú la revisas antes. <span id="mode">__DRY__</span></p>
</div>
<div id="list">__CARDS__</div>
<button id="more" style="display:__MORE__">Cargar 10 más</button>
<div class="footer">🔒 Nada se publica sin tu confirmación · las ≤4★ nunca aparecen aquí.</div>
</div>
<script>
"use strict";
var T="__TOKEN__", offset=__INITN__;
function el(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function eneLabel(e){return {explosiva:"🔥 Explosiva",zen:"😊 Zen",vibrante:"😄 Vibrante",agradecimiento:"⭐ Agradecimiento"}[e]||e;}
function badges(it){
  var rev=it.revisar_manual?"<span class='pill b-rev'>⚠ revisar manualmente</span> ":"";
  var cie=it.grupo_cierre?"<span class='pill b-cie'>cierre: "+esc(it.grupo_cierre)+"</span> ":"";
  var src=it.fuente==="banco"?"<span class='pill b-cie'>banco</span> ":"";
  return "<span class='pill b-ene'>"+esc(eneLabel(it.energia))+"</span> "+cie+src+rev;
}
function cardHtml(it){
  var rid=it.review_id;
  return "<div class='card' id='c-"+esc(rid)+"'>"+
    "<div class='stars'>★★★★★</div><div class='rev'>"+esc(it.reviewer||"Cliente")+"</div>"+
    "<div class='comment'>"+(it.comment?esc(it.comment):"<i>(sin texto)</i>")+"</div>"+
    "<div class='badges' id='b-"+esc(rid)+"'></div>"+
    "<textarea id='t-"+esc(rid)+"' disabled>generando borrador…</textarea>"+
    "<button class='btn' id='btn-"+esc(rid)+"' disabled onclick='pub(\""+esc(rid)+"\")'>Publicar respuesta</button>"+
    "<div class='msg' id='m-"+esc(rid)+"'></div></div>";
}
function fillDraft(it){
  var ta=el("t-"+it.review_id), b=el("b-"+it.review_id), btn=el("btn-"+it.review_id);
  if(!ta) return;
  ta.value=it.borrador; ta.disabled=false; ta.style.fontStyle="normal"; ta.style.color="#1a1a1a";
  if(btn) btn.disabled=false; if(b) b.innerHTML=badges(it);
}
function markLoadingError(reason){
  var tas=document.getElementsByTagName("textarea"); var i;
  for(i=0;i<tas.length;i++){ if(tas[i].disabled && tas[i].value==="generando borrador…"){ tas[i].value="Error cargando borrador: "+reason; tas[i].style.color="#A32D2D"; } }
}
function fetchDrafts(off,lim){
  if(lim<=0) return;
  var ctrl=new AbortController(); var to=setTimeout(function(){ctrl.abort();},120000);
  fetch("/acciones/resenas/data?token="+encodeURIComponent(T)+"&offset="+off+"&limit="+lim,{signal:ctrl.signal})
   .then(function(r){ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
   .then(function(d){ clearTimeout(to); (d.items||[]).forEach(fillDraft); })
   .catch(function(e){ clearTimeout(to); markLoadingError(e&&e.name==="AbortError"?"tardó demasiado, recarga la página":(e&&e.message)||"error de red"); });
}
function pub(id){
  var btn=el("btn-"+id), ta=el("t-"+id), msg=el("m-"+id);
  if(ta.disabled){ msg.className="err"; msg.textContent="Espera a que cargue el borrador."; return; }
  btn.disabled=true; msg.className=""; msg.textContent="Publicando…";
  fetch("/acciones/resenas/publicar?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({review_id:id,texto:ta.value})})
   .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
   .then(function(res){ if(res.ok){ msg.innerHTML="<div class='ok'>✓ "+(res.j.dry_run?"Simulado (dry-run)":"Publicado")+"</div>"; ta.disabled=true; }
     else { btn.disabled=false; msg.innerHTML="<div class='err'>No se pudo: "+esc(res.j.motivo||"error")+"</div>"; } })
   .catch(function(){ btn.disabled=false; msg.innerHTML="<div class='err'>Error de red</div>"; });
}
function loadMore(){
  var btn=el("more"); btn.disabled=true; btn.textContent="Cargando…";
  fetch("/acciones/resenas/contenido?token="+encodeURIComponent(T)+"&offset="+offset+"&limit=10")
   .then(function(r){return r.json();})
   .then(function(d){
     var items=d.items||[]; items.forEach(function(it){ el("list").insertAdjacentHTML("beforeend",cardHtml(it)); });
     var off=offset; offset+=items.length;
     btn.disabled=false; btn.textContent="Cargar 10 más"; btn.style.display=d.hay_mas?"block":"none";
     fetchDrafts(off, items.length);
   })
   .catch(function(){ btn.disabled=false; btn.textContent="Cargar 10 más"; });
}
el("more").addEventListener("click",loadMore);
fetchDrafts(0, __INITN__);
</script></body></html>"""
