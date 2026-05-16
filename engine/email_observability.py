"""
Persistencia durable del ultimo correo diario enviado exitosamente.

Objetivo:
  - inspeccionar subject y html final sin depender de IMAP
  - guardar solo el ultimo snapshot enviado con exito
  - persistir de forma estable entre instancias de Cloud Run usando GCS
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape

logger = logging.getLogger(__name__)

_PREVIEW_GCS_BUCKET = os.getenv("AGENT_GCS_BUCKET") or os.getenv("GCS_BUCKET") or "thai-thai-agent-data"
_PREVIEW_GCS_BLOB = os.getenv("EMAIL_PREVIEW_GCS_BLOB", "observability/last_email_preview.json")

_gcs_client = None


def _get_gcs_client():
    global _gcs_client
    if _gcs_client is None:
        try:
            from google.cloud import storage

            _gcs_client = storage.Client()
        except ImportError as exc:
            logger.error("email_observability: google-cloud-storage no instalado")
            raise RuntimeError("google-cloud-storage no instalado") from exc
        except Exception as exc:
            logger.error("email_observability: no se pudo inicializar GCS client: %s", exc)
            raise RuntimeError("no se pudo inicializar GCS client") from exc
    return _gcs_client


def _get_preview_blob():
    if not _PREVIEW_GCS_BUCKET:
        logger.error("email_observability: bucket GCS no configurado para last_email_preview")
        raise RuntimeError("bucket GCS no configurado para last_email_preview")
    client = _get_gcs_client()
    return client.bucket(_PREVIEW_GCS_BUCKET).blob(_PREVIEW_GCS_BLOB)


def _html_to_text_preview(html_body: str, max_chars: int = 600) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\\1>", " ", html_body, flags=re.I | re.S)
    text = re.sub(r"<br\\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</div\\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</tr\\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > max_chars:
        return text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text


def save_last_email_preview(
    *,
    session_id: str,
    subject: str,
    result_class: str,
    is_real_audit: bool,
    html_body: str,
    report_contract: dict | None = None,
) -> dict:
    saved_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "session_id": session_id,
        "timestamp": saved_at,
        "saved_at": saved_at,
        "storage_backend": "gcs",
        "subject": subject,
        "result_class": result_class,
        "is_real_audit": bool(is_real_audit),
        "send_status": "sent",
        "html_body": html_body,
        "text_preview": _html_to_text_preview(html_body),
        "report_contract": report_contract or {},
    }

    try:
        blob = _get_preview_blob()
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        return payload
    except Exception as exc:
        logger.error(
            "email_observability.save_last_email_preview: fallo guardando gs://%s/%s: %s",
            _PREVIEW_GCS_BUCKET,
            _PREVIEW_GCS_BLOB,
            exc,
        )
        raise RuntimeError("fallo guardando last_email_preview en GCS") from exc


def get_last_email_preview() -> dict | None:
    try:
        blob = _get_preview_blob()
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error(
            "email_observability.get_last_email_preview: fallo leyendo gs://%s/%s: %s",
            _PREVIEW_GCS_BUCKET,
            _PREVIEW_GCS_BLOB,
            exc,
        )
        raise RuntimeError("fallo leyendo last_email_preview en GCS") from exc
