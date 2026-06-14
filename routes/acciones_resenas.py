"""Acciones de reseñas 5★ — Fase G.

GET  /acciones/resenas?token=X            → UI. Tarjetas (estrellas/autor/texto) SERVER-SIDE.
GET  /acciones/resenas/contenido?token=X  → JSON: contenido de reseñas (rápido, con caché).
GET  /acciones/resenas/borrador?...&review_id=X → JSON: borrador IA de UNA reseña (per-card,
                                            con caché). Variedad por posición. Nunca 500.
GET  /acciones/resenas/data?token=X       → JSON: lote de borradores (compat; la UI usa /borrador).
POST /acciones/resenas/publicar?token=X   → publica UNA respuesta (DRY_RUN default).

Generación PROGRESIVA por tarjeta: cada textarea se llena cuando SU borrador está; si falla o
excede 30s, esa tarjeta muestra "No se pudo generar — Reintentar". El textarea siempre es
editable (puedes escribir tú). Las ≤4★ JAMÁS aparecen.
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


class ItemLote(BaseModel):
    review_id: str
    texto: str


class PublicarLoteBody(BaseModel):
    items: list[ItemLote] = []


def _card_html(it: dict) -> str:
    rid = _esc(it.get("review_id"))
    comentario = _esc(it.get("comment")) if it.get("comment") else "<i>(sin texto)</i>"
    return (f"<div class='card' id='c-{rid}' data-rid='{rid}'>"
            f"<label class='selrow' id='sel-{rid}' style='display:block'><input type='checkbox' class='sel' onchange='upd()'> seleccionar</label>"
            f"<div class='stars'>★★★★★</div><div class='rev'>{_esc(it.get('reviewer') or 'Cliente')}</div>"
            f"<div class='comment'>{comentario}</div>"
            f"<div class='badges' id='b-{rid}'></div>"
            f"<textarea id='t-{rid}' placeholder='Generando borrador… (o escribe tú)'></textarea>"
            f"<div class='status' id='s-{rid}'>⏳ generando borrador…</div>"
            f"<button class='btn' id='btn-{rid}' onclick=\"pub('{rid}')\">Publicar respuesta</button>"
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
        .replace("__NEXT__", str(data["offset"] + data["limit"])).replace("__MORE__", "block" if data["hay_mas"] else "none")
    )


@router.get("/acciones/resenas/contenido")
async def resenas_contenido(token: str = "", offset: int = 0, limit: int = 10):
    _require_token(token)
    off, lim = _clamp(offset, limit)
    return JSONResponse(content=resenas_service.cargar_resenas_tanda(offset=off, limit=lim))


@router.get("/acciones/resenas/borrador")
async def resenas_borrador(token: str = "", review_id: str = ""):
    _require_token(token)
    return JSONResponse(content=resenas_service.borrador_para(review_id))


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


@router.post("/acciones/resenas/publicar-lote")
async def resenas_publicar_lote(body: PublicarLoteBody, token: str = ""):
    _require_token(token)
    items = [{"review_id": i.review_id, "texto": i.texto} for i in body.items]
    return JSONResponse(content=resenas_service.publicar_lote(items))


_PAGE = r"""<!doctype html>
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
  textarea{width:100%;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;padding:10px;font:13px Arial;min-height:84px;}
  .status{font-size:11px;color:#888;margin-top:4px;min-height:14px;}
  .btn{display:inline-block;background:#2d2a26;color:#fff;border:none;border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer;font-weight:bold;margin-top:8px;}
  .btn[disabled]{opacity:.45;cursor:not-allowed;}
  .ok{color:#1a7f37;font-size:12px;font-weight:bold;margin-top:8px;}
  .err{color:#A32D2D;font-weight:bold;}
  .msg{font-size:12px;margin-top:6px;}
  .empty{background:#fff;border:1px solid #e2dccf;border-radius:10px;padding:20px;text-align:center;color:#777;}
  #more{display:block;width:100%;background:#fff;color:#2d2a26;border:1px solid #ccc;border-radius:8px;padding:11px;font-size:13px;cursor:pointer;font-weight:bold;}
  a{color:#1a5276;}
  .selrow{display:block;font-size:11px;color:#555;margin-bottom:6px;cursor:pointer;}
  .selrow input{vertical-align:middle;margin-right:5px;}
  #lote{display:none;position:sticky;bottom:8px;width:100%;background:#1a7f37;color:#fff;border:none;border-radius:8px;padding:13px;font-size:14px;cursor:pointer;font-weight:bold;margin:10px 0 4px;box-shadow:0 6px 16px rgba(0,0,0,.2);}
  #lote[disabled]{background:#9bbfa6;cursor:not-allowed;}
  #loteMsg{font-size:12px;margin:4px 0 8px;font-weight:bold;}
  .footer{font-size:10.5px;color:#999;text-align:center;padding:12px;}
</style></head><body><div class="box">
<div class="head">
  <h1>⭐ Reseñas 5★ — responder con tu voz</h1>
  <p class="muted">Solo reseñas de 5 estrellas sin responder. Publica una por una, o marca varias y usa el botón verde. Tú revisas antes. <span id="mode">__DRY__</span></p>
</div>
<div id="list">__CARDS__</div>
<button id="more" style="display:__MORE__">Cargar 10 más</button>
<button id="lote" disabled onclick="publicarLote()">Publicar seleccionadas (0)</button>
<div id="loteMsg"></div>
<div class="footer">🔒 Nada se publica sin tu confirmación · las ≤4★ nunca aparecen aquí · las marcadas "revisar manualmente" se publican una por una.</div>
</div>
<script>
"use strict";
var T="__TOKEN__", nextOffset=__NEXT__, queue=[], active=0, MAXC=3;
function el(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function eneLabel(e){return {explosiva:"🔥 Explosiva",zen:"😊 Zen",vibrante:"😄 Vibrante",agradecimiento:"⭐ Agradecimiento"}[e]||e;}
function badges(it){
  if(!it.energia) return "";
  var rev=it.revisar_manual?"<span class='pill b-rev'>⚠ revisar manualmente</span> ":"";
  var cie=it.grupo_cierre?"<span class='pill b-cie'>cierre: "+esc(it.grupo_cierre)+"</span> ":"";
  var src=it.fuente==="banco"?"<span class='pill b-cie'>banco</span> ":"";
  return "<span class='pill b-ene'>"+esc(eneLabel(it.energia))+"</span> "+cie+src+rev;
}
function cardHtml(it){
  var rid=it.review_id;
  return "<div class='card' id='c-"+esc(rid)+"' data-rid='"+esc(rid)+"'>"+
    "<label class='selrow' id='sel-"+esc(rid)+"' style='display:block'><input type='checkbox' class='sel' onchange='upd()'> seleccionar</label>"+
    "<div class='stars'>★★★★★</div><div class='rev'>"+esc(it.reviewer||"Cliente")+"</div>"+
    "<div class='comment'>"+(it.comment?esc(it.comment):"<i>(sin texto)</i>")+"</div>"+
    "<div class='badges' id='b-"+esc(rid)+"'></div>"+
    "<textarea id='t-"+esc(rid)+"' placeholder='Generando borrador… (o escribe tú)'></textarea>"+
    "<div class='status' id='s-"+esc(rid)+"'>⏳ generando borrador…</div>"+
    "<button class='btn' id='btn-"+esc(rid)+"' onclick='pub(\""+esc(rid)+"\")'>Publicar respuesta</button>"+
    "<div class='msg' id='m-"+esc(rid)+"'></div></div>";
}
function showError(rid,reason){
  var st=el("s-"+rid); if(!st) return;
  st.innerHTML="<span class='err'>No se pudo generar: "+esc(reason)+".</span> <a href='#' onclick='retry(\""+rid+"\");return false;'>Reintentar</a> · o escribe tú.";
}
function retry(rid){ var st=el("s-"+rid); if(st) st.innerHTML="⏳ generando borrador…"; queue.push(rid); pump(); }
function loadDraft(rid){
  var ctrl=new AbortController(); var to=setTimeout(function(){ctrl.abort();},30000);
  return fetch("/acciones/resenas/borrador?token="+encodeURIComponent(T)+"&review_id="+encodeURIComponent(rid),{signal:ctrl.signal})
   .then(function(r){ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
   .then(function(d){ clearTimeout(to);
     if(d.error){ showError(rid,d.error); return; }
     var ta=el("t-"+rid); if(ta && !ta.value.trim()){ ta.value=d.borrador; }
     var b=el("b-"+rid); if(b) b.innerHTML=badges(d);
     var st=el("s-"+rid); if(st) st.innerHTML="";
     // El checkbox ya está visible desde el render. Solo si el borrador sale flaggeado
     // (no natural) lo ocultamos + desmarcamos: esa se revisa a mano, no entra al lote.
     var sr=el("sel-"+rid); if(sr && d.revisar_manual){ var cb=sr.querySelector(".sel"); if(cb) cb.checked=false; sr.style.display="none"; upd(); }
   })
   .catch(function(e){ clearTimeout(to); showError(rid, e&&e.name==="AbortError"?"tardó demasiado":((e&&e.message)||"error de red")); });
}
function pump(){
  while(active<MAXC && queue.length){
    var rid=queue.shift(); active++;
    loadDraft(rid).then(function(){ active--; pump(); });
  }
}
function pub(id){
  var btn=el("btn-"+id), ta=el("t-"+id), msg=el("m-"+id);
  if(!ta.value.trim()){ msg.className="msg"; msg.innerHTML="<span class='err'>Escribe o espera el borrador antes de publicar.</span>"; return; }
  btn.disabled=true; msg.className="msg"; msg.textContent="Publicando…";
  fetch("/acciones/resenas/publicar?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({review_id:id,texto:ta.value})})
   .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
   .then(function(res){ if(res.ok){ msg.innerHTML="<div class='ok'>✓ "+(res.j.dry_run?"Simulado (dry-run)":"Publicado")+"</div>"; ta.disabled=true; _quitarSel(id); }
     else { btn.disabled=false; msg.innerHTML="<div class='err'>No se pudo: "+esc(res.j.motivo||"error")+"</div>"; } })
   .catch(function(){ btn.disabled=false; msg.innerHTML="<div class='err'>Error de red</div>"; });
}
function _quitarSel(rid){ var sr=el("sel-"+rid); if(sr){ var cb=sr.querySelector(".sel"); if(cb) cb.checked=false; sr.style.display="none"; } upd(); }
var MAXSEL=10;
function _checks(){ return Array.prototype.slice.call(document.querySelectorAll(".sel")); }
function _seleccionadas(){ return _checks().filter(function(c){ return c.checked && !c.disabled; }); }
function upd(){
  var sel=_seleccionadas();
  _checks().forEach(function(c){ if(!c.checked) c.disabled = (sel.length>=MAXSEL); });  // tope 10
  var b=el("lote");
  b.textContent="Publicar seleccionadas ("+sel.length+")";
  b.disabled = sel.length===0;
  b.style.display = sel.length>0 ? "block" : "none";
  el("loteMsg").innerHTML = sel.length>=MAXSEL ? "<span style='color:#8b5e14'>Máximo 10 por lote.</span>" : "";
}
function publicarLote(){
  var sel=_seleccionadas(); if(!sel.length) return;
  var items=[];
  sel.forEach(function(c){ var card=c.closest(".card"); if(!card) return; var rid=card.getAttribute("data-rid"); var ta=el("t-"+rid);
    if(ta && ta.value.trim()) items.push({review_id:rid, texto:ta.value}); });
  if(!items.length){ el("loteMsg").innerHTML="<span class='err'>Las seleccionadas no tienen texto.</span>"; return; }
  var b=el("lote"); b.disabled=true; b.textContent="Publicando…"; el("loteMsg").textContent="Publicando "+items.length+"…";
  fetch("/acciones/resenas/publicar-lote?token="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({items:items})})
   .then(function(r){ return r.json(); })
   .then(function(d){
     (d.resultados||[]).forEach(function(r){ var msg=el("m-"+r.review_id), ta=el("t-"+r.review_id);
       if(!msg) return;
       if(r.status==="ok"){ msg.innerHTML="<div class='ok'>✓ "+(d.dry_run?"Simulado":"Publicado")+"</div>"; if(ta) ta.disabled=true; _quitarSel(r.review_id); }
       else { msg.innerHTML="<div class='err'>No se pudo: "+esc(r.motivo||"error")+"</div>"; }
     });
     el("loteMsg").innerHTML="<span class='ok'>"+d.publicadas+" "+(d.dry_run?"simuladas":"publicadas")+(d.fallidas?(" · "+d.fallidas+" fallaron"):"")+"</span>";
     upd();
   })
   .catch(function(){ el("loteMsg").innerHTML="<span class='err'>Error de red en el lote</span>"; upd(); });
}
function enqueueVisible(){
  var nodes=document.querySelectorAll(".card[data-rid]");
  for(var i=0;i<nodes.length;i++){ var rid=nodes[i].getAttribute("data-rid"); if(nodes[i].getAttribute("data-q")!=="1"){ nodes[i].setAttribute("data-q","1"); queue.push(rid); } }
  pump();
}
function loadMore(){
  var btn=el("more"); btn.disabled=true; btn.textContent="Cargando…";
  fetch("/acciones/resenas/contenido?token="+encodeURIComponent(T)+"&offset="+nextOffset+"&limit=10")
   .then(function(r){return r.json();})
   .then(function(d){
     var items=d.items||[]; items.forEach(function(it){ el("list").insertAdjacentHTML("beforeend",cardHtml(it)); });
     nextOffset+=items.length;
     btn.disabled=false; btn.textContent="Cargar 10 más"; btn.style.display=d.hay_mas?"block":"none";
     enqueueVisible();
   })
   .catch(function(){ btn.disabled=false; btn.textContent="Cargar 10 más"; });
}
el("more").addEventListener("click",loadMore);
enqueueVisible();
</script></body></html>"""
