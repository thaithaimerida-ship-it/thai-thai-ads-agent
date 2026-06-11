"""Correo de confirmación por publicación de reseña — Fase G.

GATED por RESENAS_EMAIL_ENABLED (default off): construye el mensaje pero NO envía a menos que
esté explícitamente habilitado. Reutiliza la config SMTP existente (config.agent_config).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


def email_habilitado() -> bool:
    # Gate compartido (ACCIONES_EMAIL_ENABLED), con RESENAS_EMAIL_ENABLED como alias legacy.
    from engine import acciones_email
    return acciones_email.email_habilitado()


def construir_confirmacion(entry: dict[str, Any]) -> tuple[str, str]:
    """(subject, body) del correo de confirmación de una publicación."""
    modo = "SIMULACRO (dry-run)" if entry.get("dry_run") else "PUBLICADA"
    asunto = f"🍜 Reseña respondida — {modo} · {entry.get('reviewer', '')}".strip()
    cuerpo = (
        f"Se {'simuló' if entry.get('dry_run') else 'publicó'} una respuesta a una reseña 5★.\n\n"
        f"Cliente: {entry.get('reviewer') or '(anónimo)'}\n"
        f"Reseña: {entry.get('comment') or '(sin texto)'}\n\n"
        f"Respuesta {'(no publicada, dry-run)' if entry.get('dry_run') else 'publicada'}:\n"
        f"{entry.get('texto', '')}\n\n"
        f"Energía: {entry.get('energia', '')} · Fuente: {entry.get('fuente', '')}\n"
        f"review_id: {entry.get('review_id', '')}\n"
    )
    return asunto, cuerpo


def enviar_confirmacion(entry: dict[str, Any]) -> dict[str, Any]:
    """Envía el correo si RESENAS_EMAIL_ENABLED=true; si no, no envía (modo seguro)."""
    asunto, cuerpo = construir_confirmacion(entry)
    if not email_habilitado():
        return {"enviado": False, "motivo": "deshabilitado (RESENAS_EMAIL_ENABLED!=true)"}
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
        logger.error("enviar_confirmacion: error SMTP — %s", exc)
        return {"enviado": False, "motivo": str(exc)}
