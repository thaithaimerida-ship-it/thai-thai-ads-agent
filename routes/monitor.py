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
    build_reservas_persist_status,
    build_search_console_context,
    build_seo_context,
    load_gbp_context_live,
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
        "bloqueos": f"{_BASE_URL}/acciones/bloqueos?token={_ACTIONS_TOKEN}",  # bandeja (checkboxes)
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


def _ctx_gbp() -> dict:
    """Reseñas + Maps 30d EN VIVO (read-only). Cada slice ya degrada por su cuenta."""
    try:
        return load_gbp_context_live()
    except Exception:
        return {"gbp": {"data_broken": True}, "reviews": {"data_broken": True}}


def _ctx_woocommerce() -> dict:
    """Ventas reales de la tienda WooCommerce (read-only). Degrada con gracia: token/red caído
    → data_broken y la sección sale 'no disponible' sin tumbar el correo. NUNCA loguea creds."""
    try:
        from engine.woocommerce_sales import build_weekly_sales
        return {"ventas_woocommerce": build_weekly_sales()}
    except Exception as exc:
        logger.warning("monitor context: ventas WooCommerce no disponibles — %s", type(exc).__name__)
        return {"ventas_woocommerce": {"data_broken": True}}


def _ctx_seo() -> dict:
    # PageSpeed solo con key configurada (PSI sin key se rate-limita / 429).
    if not os.getenv("PAGESPEED_API_KEY"):
        return {"seo": {"data_broken": True}}
    try:
        return build_seo_context()
    except Exception:
        return {"seo": {"data_broken": True}}


def _ctx_search_console() -> dict:
    try:
        return build_search_console_context()
    except Exception:
        return {"search_console": {"data_broken": True}}


def _ctx_ads(date_range: str) -> dict:
    """Google Ads (read-only). Token caído → secciones caen a su fallback."""
    try:
        from engine.ads_client import fetch_campaign_conversion_breakdown, fetch_campaign_data, get_ads_client
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = get_ads_client()
        campaigns = fetch_campaign_data(client, target_id, date_range)
        breakdown = fetch_campaign_conversion_breakdown(client, target_id, date_range)
        # 30d window for the 'provisional' health (señales + CTR vs propio promedio 30d).
        campaigns_30d = fetch_campaign_data(client, target_id, "LAST_30_DAYS")
        breakdown_30d = fetch_campaign_conversion_breakdown(client, target_id, "LAST_30_DAYS")
        out: dict = {}
        if campaigns:
            out["campaign_metrics"] = build_campaign_metrics(campaigns, breakdown, campaigns_30d, breakdown_30d)
        out["ads_quality"] = _ads_quality(client, target_id, date_range)
        return out
    except Exception as exc:
        logger.warning("monitor context: Google Ads sources unavailable — %s", exc)
        return {}


def _ctx_reservas_persist() -> dict:
    # Incidentes de reservas (marcas durables en GCS): no guardadas en Sheets + guardadas sin confirmar.
    try:
        return {"reservas_persist": build_reservas_persist_status()}
    except Exception:
        return {"reservas_persist": {"checked": False,
                                     "persist_failures": {"count": 0, "ids": []},
                                     "unconfirmed": {"count": 0, "items": []}}}


def _ctx_reservas() -> dict:
    # Reservas del libro (server-side, por list_reservations) para el resumen "hechas esta semana".
    # Degrada con gracia: si Sheets falla → data_broken=True y la sección sale "no disponible".
    try:
        from engine import reservas_sheets
        return {"reservas": {"data_broken": False, "items": reservas_sheets.list_reservations(limit=1000)}}
    except Exception:
        return {"reservas": {"data_broken": True, "items": []}}


def _build_context(date_range: str, mode: str) -> dict:
    """Assemble the read-only enrichment context. Never raises — missing sources degrade
    to data_broken / search-term fallback. Las 6 fuentes (GBP, GloriaFood, SEO, Search
    Console, Ads, keepalive) son llamadas I/O independientes → se corren EN PARALELO para
    bajar el tiempo total de /monitor/send (cada bloque trae su propio try/except, así que
    una fuente caída nunca tumba el correo ni bloquea a las demás)."""
    import concurrent.futures as _cf

    context: dict = {
        "mode": "friday" if str(mode).strip().lower() == "friday" else "monday",
        "links": _links(),
    }
    tareas = [_ctx_gbp, _ctx_woocommerce, _ctx_seo, _ctx_search_console, _ctx_reservas_persist,
              _ctx_reservas, lambda: _ctx_ads(date_range)]
    with _cf.ThreadPoolExecutor(max_workers=len(tareas)) as ex:
        for fut in [ex.submit(t) for t in tareas]:
            try:
                context.update(fut.result())
            except Exception:
                pass  # ya cubierto dentro de cada bloque; red extra
    return context


def _degraded_search_terms_payload(date_range: str) -> dict:
    """Payload 'success' vacío para cuando Google Ads no responde (token revocado, timeout, etc.).
    Mantiene status='success' para que build_monitor_digest arme un correo VÁLIDO con las
    secciones NO-Ads; el banner de aviso lo dispara aparte context['ads_error']. Misma forma
    que el payload real de _build_search_terms_payload pero con 0 términos."""
    return {
        "status": "success",
        "date_range": _normalize_date_range(date_range),
        "total": 0,
        "counts": {"rojo": 0, "amarillo": 0, "verde": 0, "blanco": 0},
        "negative_candidates": 0,
        "competitor_terms": 0,
        "search_terms": [],
        "accumulated_reds": [],
    }


def _is_ads_failure(exc: Exception) -> bool:
    """True si la excepción es un fallo IDENTIFICABLE de Google Ads/auth/red (token revocado,
    timeout, cuota, error de la API) — vs. un bug inesperado. Decide qué banner mostrar."""
    from engine.ads_auth_alert import es_fallo_auth
    if es_fallo_auth(str(exc)):
        return True
    return type(exc).__name__ in {
        "GoogleAdsException", "RefreshError", "TransportError", "HttpError",
        "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout", "GatewayTimeout",
    }


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
async def monitor_send(token: str = "", tipo: str = "", force: bool = False, marca: str = "",
                       date_range: str = "LAST_7_DAYS", authorization: str = Header(default="")):
    """Genera el digest, lo renderiza (formato completo — el MISMO para lunes y viernes, contrato
    v6.2) y lo envía por SMTP a thaithaimerida@gmail.com. Idempotente por día (force=true reenvía).
    Reemplaza al Apps Script. `tipo` (lunes|viernes) solo rotula el envío; ya no cambia el formato.
    `marca` (opcional) agrega un sufijo al asunto — útil para envíos de prueba que no deben
    agruparse en el mismo hilo de Gmail que los reales."""
    _auth_monitor_send(token, authorization)
    date_range = _normalize_date_range(date_range)
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(status_code=400, detail=f"date_range invalido: '{date_range}'.")
    fecha, dia = _hoy_merida()
    modo = tipo if tipo in ("lunes", "viernes") else dia  # etiqueta para el log/respuesta

    if not force and acciones_log.monitor_ya_enviado_hoy(fecha):
        return JSONResponse({"status": "already_sent", "fecha": fecha, "modo": modo})

    try:
        payload = _build_search_terms_payload(date_range)
        ads_error = None
    except Exception as exc:
        # Google Ads caído NO debe dejar sin correo → reporte degradado + banner arriba.
        # Se distingue un fallo IDENTIFICABLE de Ads/auth/red (token revocado, timeout, cuota)
        # de una excepción INESPERADA (probable bug): el banner y el asunto cambian, para no
        # enmascarar un bug de código como si fuera un token muerto.
        exc_type = type(exc).__name__
        if _is_ads_failure(exc):
            logger.warning("monitor_send: Google Ads no disponible (%s), reporte degradado — %s", exc_type, exc)
            ads_error = {"kind": "ads", "exc_type": exc_type}
        else:
            logger.warning("monitor_send: excepción INESPERADA (%s) al construir search terms, reporte degradado — %s", exc_type, exc)
            ads_error = {"kind": "unexpected", "exc_type": exc_type}
        payload = _degraded_search_terms_payload(date_range)
    context = _build_context(date_range, modo)
    context["generated_date"] = _fecha_humana()  # fecha de envío → asunto y encabezado
    if ads_error:
        context["ads_error"] = ads_error
    digest = build_monitor_digest(payload, context)
    subject = digest.get("subject_email")
    if marca.strip():
        subject = f"{subject} · {marca.strip()[:40]}"  # sufijo de prueba (acotado)
    res = monitor_mailer.enviar_digest(subject, digest.get("html_email"), digest.get("text_email"))
    acciones_log.registrar({"accion": "monitor_send", "fecha": fecha, "modo": modo,
                            "resultado": "ok" if res.get("enviado") else "error", "force": bool(force), "correo": res})
    ok = bool(res.get("enviado"))
    return JSONResponse({"status": "sent" if ok else "error", "fecha": fecha, "modo": modo, "correo": res},
                        status_code=200 if ok else 502)
