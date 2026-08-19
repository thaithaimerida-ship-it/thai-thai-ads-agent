"""Alerta proactiva: Google Ads sin credenciales (token revocado / caducado).

Se dispara desde el job diario `snapshot-search-terms` cuando `get_ads_client` falla por
auth. Manda UN aviso por día (dedupe vía acciones_log) a EMAIL_TO con un asunto inequívoco,
para enterarse en 1 día en vez de descubrirlo cuando no llega el correo del lunes.

No está detrás del gate ACCIONES_EMAIL_ENABLED (eso es para confirmaciones de acciones):
esta alerta debe salir siempre. Nunca lanza — si algo falla, se traga la excepción y loguea.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from engine import acciones_log

logger = logging.getLogger(__name__)

ACCION = "ads_auth_alert"


def _hoy_merida() -> str:
    try:
        return datetime.now(ZoneInfo("America/Merida")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def es_fallo_auth(error_msg: str) -> bool:
    """True si el mensaje de error corresponde a un fallo de credenciales de Google Ads."""
    m = (error_msg or "").lower()
    return (
        "invalid_grant" in m
        or "expired or revoked" in m
        or "no hay credenciales de google ads" in m
    )


def alertar_si_auth_fallo(error_msg: str) -> dict:
    """Si `error_msg` es un fallo de auth de Google Ads, manda UN aviso por día.
    Devuelve un dict con el resultado. NUNCA lanza (para no romper el endpoint que la llama)."""
    try:
        if not es_fallo_auth(error_msg):
            return {"alertado": False, "motivo": "no es fallo de auth"}
        fecha = _hoy_merida()
        if acciones_log.evento_ya_registrado_hoy(ACCION, fecha):
            return {"alertado": False, "motivo": "ya avisado hoy"}
        res = _enviar(error_msg, fecha)
        acciones_log.registrar({
            "accion": ACCION, "fecha": fecha,
            "resultado": "ok" if res.get("enviado") else "error", "detalle": res,
        })
        return {"alertado": bool(res.get("enviado")), "correo": res}
    except Exception as exc:  # pragma: no cover
        logger.error("ads_auth_alert.alertar_si_auth_fallo: fallo inesperado — %s", exc)
        return {"alertado": False, "motivo": str(exc)}


def _enviar(error_msg: str, fecha: str) -> dict:
    from config.agent_config import (
        EMAIL_FROM, EMAIL_FROM_NAME, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_TO,
        GMAIL_APP_PASSWORD,
    )
    if not GMAIL_APP_PASSWORD:
        return {"enviado": False, "motivo": "GMAIL_APP_PASSWORD no configurado"}
    asunto = "🔴 Google Ads sin credenciales — token posiblemente revocado"
    cuerpo = (
        "El agente Thai Thai no pudo autenticarse con Google Ads.\n\n"
        f"Fecha (Mérida): {fecha}\n"
        "Origen: job diario snapshot-search-terms.\n"
        "Efecto: los reportes del lunes/viernes saldrán SIN las secciones de Google Ads "
        "hasta renovar el token.\n\n"
        "Acción: renovar el refresh token de Google Ads y actualizar GOOGLE_ADS_REFRESH_TOKEN "
        "en Cloud Run (--update-env-vars, NUNCA --set-env-vars).\n\n"
        f"Detalle técnico: {(error_msg or '')[:300]}\n"
    )
    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"] = EMAIL_TO
    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return {"enviado": True}
    except Exception as exc:  # pragma: no cover
        logger.error("ads_auth_alert._enviar: error SMTP — %s", exc)
        return {"enviado": False, "motivo": str(exc)}
