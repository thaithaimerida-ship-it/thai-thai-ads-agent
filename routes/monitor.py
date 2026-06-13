"""Read-only Monitor endpoints."""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from engine import acciones_log, monitor_mailer
from engine.monitor_digest_v3 import build_monitor_digest
from engine.monitor_sections import build_ads_quality_from_list, build_campaign_metrics
from engine.monitor_sources import (
    build_keepalive_db,
    build_search_console_context,
    build_seo_context,
    load_gbp_context,
    load_gloriafood_internal,
)
from routes.analysis import VALID_DATE_RANGES, _build_search_terms_payload, _normalize_date_range


router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("MONITOR_BASE_URL", "https://thai-thai-ads-agent-624172071613.us-central1.run.app")
# Los links de acción del correo usan el MISMO token que protege las páginas (ACCIONES_TOKEN,
# en Secret Manager). ACTIONS_TOKEN queda como alias legacy.
_ACTIONS_TOKEN = os.getenv("ACCIONES_TOKEN") or os.getenv("ACTIONS_TOKEN", "PENDIENTE_PARTE_B")

_RANGE_DAYS = {"TODAY": 1, "YESTERDAY": 1, "LAST_7_DAYS": 7, "LAST_14_DAYS": 14,
               "LAST_30_DAYS": 30, "THIS_MONTH": 30, "LAST_MONTH": 30}


def _links() -> dict:
    return {
        "ads": "https://ads.google.com/aw/overview",
        "bloqueo_base": f"{_BASE_URL}/acciones/bloqueo",
        "resenas": f"{_BASE_URL}/acciones/resenas?token={_ACTIONS_TOKEN}",
        "revision": f"{_BASE_URL}/acciones/bloqueo?token={_ACTIONS_TOKEN}",
        "token": _ACTIONS_TOKEN,
    }


def _ads_quality(client, target_id: str, date_range: str) -> dict:
    """Merge ad health + metrics (same shape as /ads-report) into ads_quality."""
    from engine.ads_client import fetch_ad_health, fetch_ad_metrics
    health = {h.get("ad_id"): h for h in (fetch_ad_health(client, target_id) or [])}
    ads = []
    for m in fetch_ad_metrics(client, target_id, date_range) or []:
        h = health.get(m.get("ad_id"), {})
        ads.append({
            "ad_id": m.get("ad_id", ""),
            "campaign_name": h.get("campaign_name", ""),
            "ad_strength": h.get("ad_strength"),
            "approval_status": h.get("approval_status"),
            "headlines": h.get("headlines", []),
            "ctr_pct": round(float(m.get("ctr", 0)) * 100, 2),
            "clicks": int(m.get("clicks", 0)),
            "impressions": int(m.get("impressions", 0)),
            "conversions": round(float(m.get("conversions", 0)), 1),
        })
    return build_ads_quality_from_list(ads, _RANGE_DAYS.get(date_range, 7))


def _build_context(date_range: str, mode: str) -> dict:
    """Assemble the read-only enrichment context. Never raises — missing sources
    degrade to data_broken / search-term fallback."""
    context: dict = {
        "mode": "friday" if str(mode).strip().lower() == "friday" else "monday",
        "links": _links(),
    }
    try:
        context.update(load_gbp_context())
    except Exception:
        context["gbp"] = {"data_broken": True}
        context["reviews"] = {"data_broken": True}
    try:
        interno = load_gloriafood_internal()
        if interno:
            context["pedidos_gloriafood_interno"] = interno
    except Exception:
        pass
    # PageSpeed only when a key is configured (keyless PSI is rate-limited / 429).
    if os.getenv("PAGESPEED_API_KEY"):
        try:
            context.update(build_seo_context())
        except Exception:
            context["seo"] = {"data_broken": True}
    else:
        context["seo"] = {"data_broken": True}

    try:
        context.update(build_search_console_context())
    except Exception:
        context["search_console"] = {"data_broken": True}

    # Google Ads sources (read-only). Token may be down → leave sections to fall back.
    try:
        from engine.ads_client import fetch_campaign_conversion_breakdown, fetch_campaign_data, get_ads_client
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = get_ads_client()
        campaigns = fetch_campaign_data(client, target_id, date_range)
        breakdown = fetch_campaign_conversion_breakdown(client, target_id, date_range)
        # 30d window for the 'provisional' health (señales + CTR vs propio promedio 30d).
        campaigns_30d = fetch_campaign_data(client, target_id, "LAST_30_DAYS")
        breakdown_30d = fetch_campaign_conversion_breakdown(client, target_id, "LAST_30_DAYS")
        if campaigns:
            context["campaign_metrics"] = build_campaign_metrics(campaigns, breakdown, campaigns_30d, breakdown_30d)
        context["ads_quality"] = _ads_quality(client, target_id, date_range)
    except Exception as exc:
        logger.warning("monitor context: Google Ads sources unavailable — %s", exc)

    # Keepalive de la DB de reservas (Supabase free-tier se pausa a los 7 días sin actividad).
    try:
        context["keepalive_db"] = build_keepalive_db()
    except Exception:
        context["keepalive_db"] = {"ok": False, "checked": True, "error": "keepalive no ejecutado"}

    return context


@router.get("/monitor/digest")
async def monitor_digest(date_range: str = "LAST_7_DAYS", mode: str = "monday"):
    """Monitor Digest V3: read-only summary + rendered email for the weekly digest.

    Contrato v6.2: formato completo único (lunes y viernes idénticos). `mode` queda sin efecto.
    """
    date_range = _normalize_date_range(date_range)
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
        )
    payload = _build_search_terms_payload(date_range)
    return build_monitor_digest(payload, _build_context(date_range, mode))


_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]


def _hoy_merida() -> tuple[str, str]:
    """(fecha 'YYYY-MM-DD', etiqueta del día 'lunes'|'viernes') en hora de Mérida.
    La etiqueta solo rotula el envío en el log; ya NO cambia el formato (contrato v6.2)."""
    now = datetime.now(ZoneInfo("America/Merida"))
    return now.strftime("%Y-%m-%d"), ("viernes" if now.weekday() == 4 else "lunes")


def _fecha_humana() -> str:
    """Fecha de envío legible en español (hora de Mérida), p. ej. 'viernes 12 de junio de 2026'."""
    n = datetime.now(ZoneInfo("America/Merida"))
    return f"{_DIAS_ES[n.weekday()]} {n.day} de {_MESES_ES[n.month - 1]} de {n.year}"


def _auth_monitor_send(token: str, authorization: str) -> None:
    """Fail-closed. Acepta: (1) MONITOR_SEND_TOKEN compartido (disparo manual / tests), o
    (2) un OIDC ID token de Google del SA del Cloud Scheduler (sin secreto en el job)."""
    expected = os.getenv("MONITOR_SEND_TOKEN", "")
    if expected and token and secrets.compare_digest(token, expected):
        return
    sa = os.getenv("MONITOR_SCHEDULER_SA", "")
    if authorization.startswith("Bearer ") and sa:
        try:
            from google.auth.transport import requests as greq
            from google.oauth2 import id_token as gidt
            aud = os.getenv("MONITOR_OIDC_AUDIENCE") or None  # si se setea, se verifica el audience
            info = gidt.verify_oauth2_token(authorization.split(" ", 1)[1], greq.Request(), audience=aud)
            if info.get("email") == sa and info.get("email_verified"):
                return
        except Exception:
            pass
    raise HTTPException(status_code=403, detail="No autorizado")


@router.post("/monitor/send")
async def monitor_send(token: str = "", tipo: str = "", force: bool = False,
                       date_range: str = "LAST_7_DAYS", authorization: str = Header(default="")):
    """Genera el digest, lo renderiza (formato completo — el MISMO para lunes y viernes, contrato
    v6.2) y lo envía por SMTP a thaithaimerida@gmail.com. Idempotente por día (force=true reenvía).
    Reemplaza al Apps Script. `tipo` (lunes|viernes) solo rotula el envío; ya no cambia el formato."""
    _auth_monitor_send(token, authorization)
    date_range = _normalize_date_range(date_range)
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(status_code=400, detail=f"date_range invalido: '{date_range}'.")
    fecha, dia = _hoy_merida()
    modo = tipo if tipo in ("lunes", "viernes") else dia  # etiqueta para el log/respuesta

    if not force and acciones_log.monitor_ya_enviado_hoy(fecha):
        return JSONResponse({"status": "already_sent", "fecha": fecha, "modo": modo})

    payload = _build_search_terms_payload(date_range)
    context = _build_context(date_range, modo)
    context["generated_date"] = _fecha_humana()  # fecha de envío → asunto y encabezado
    digest = build_monitor_digest(payload, context)
    res = monitor_mailer.enviar_digest(digest.get("subject_email"), digest.get("html_email"), digest.get("text_email"))
    acciones_log.registrar({"accion": "monitor_send", "fecha": fecha, "modo": modo,
                            "resultado": "ok" if res.get("enviado") else "error", "force": bool(force), "correo": res})
    ok = bool(res.get("enviado"))
    return JSONResponse({"status": "sent" if ok else "error", "fecha": fecha, "modo": modo, "correo": res},
                        status_code=200 if ok else 502)
