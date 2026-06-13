"""Envío del digest del monitor por SMTP (reemplaza al Apps Script viejo).

NO está gated: el endpoint que lo llama (POST /monitor/send) ya está protegido por token +
idempotencia. Reutiliza la config SMTP de los correos de confirmación (config.agent_config).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def enviar_digest(subject: str, html: str, text: str, destinatario: str | None = None) -> dict:
    """Envía el correo del monitor (multipart text+html) a MONITOR_EMAIL_TO
    (default thaithaimerida@gmail.com). Devuelve {enviado, ...}."""
    to = destinatario or os.getenv("MONITOR_EMAIL_TO", "thaithaimerida@gmail.com")
    try:
        from config.agent_config import (
            EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_FROM, EMAIL_FROM_NAME, GMAIL_APP_PASSWORD,
        )
        if not GMAIL_APP_PASSWORD:
            return {"enviado": False, "motivo": "GMAIL_APP_PASSWORD no configurado"}
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject or "Thai Thai Monitor"
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"] = to
        msg.attach(MIMEText(text or "", "plain", "utf-8"))
        msg.attach(MIMEText(html or "", "html", "utf-8"))
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to], msg.as_string())
        return {"enviado": True, "destinatario": to}
    except Exception as exc:  # pragma: no cover - SMTP no se ejercita en tests
        logger.error("monitor_mailer.enviar_digest: error SMTP — %s", exc)
        return {"enviado": False, "motivo": str(exc)}
