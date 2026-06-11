"""Correo de confirmación de acciones (reseñas + bloqueo) — Fase G / B1.

Gate único: ACCIONES_EMAIL_ENABLED (con RESENAS_EMAIL_ENABLED como alias legacy). Default off:
construye el mensaje pero NO envía a menos que esté habilitado. Reutiliza la config SMTP.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def email_habilitado() -> bool:
    for var in ("ACCIONES_EMAIL_ENABLED", "RESENAS_EMAIL_ENABLED"):
        if os.getenv(var, "").strip().lower() == "true":
            return True
    return False


def enviar(asunto: str, cuerpo: str) -> dict:
    """Envía el correo si el gate está activo; si no, no envía (modo seguro)."""
    if not email_habilitado():
        return {"enviado": False, "motivo": "deshabilitado (ACCIONES_EMAIL_ENABLED!=true)"}
    try:
        from config.agent_config import (
            EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_FROM, EMAIL_FROM_NAME, EMAIL_TO, GMAIL_APP_PASSWORD,
        )
        if not GMAIL_APP_PASSWORD:
            return {"enviado": False, "motivo": "GMAIL_APP_PASSWORD no configurado"}
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return {"enviado": True}
    except Exception as exc:  # pragma: no cover - no se ejercita en build/tests
        logger.error("acciones_email.enviar: error SMTP — %s", exc)
        return {"enviado": False, "motivo": str(exc)}
