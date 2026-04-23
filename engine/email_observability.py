"""
Persistencia mínima del último correo diario enviado exitosamente.

Objetivo:
  - inspeccionar subject y html final sin depender de IMAP
  - guardar solo el último snapshot enviado con éxito
"""

import json
import os
import re
from datetime import datetime, timezone
from html import unescape


def _get_preview_path() -> str:
    env_path = os.getenv("EMAIL_PREVIEW_PATH")
    if env_path:
        return env_path
    return os.path.join(os.path.dirname(__file__), "..", "data", "last_email_preview.json")


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
    payload = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "result_class": result_class,
        "is_real_audit": bool(is_real_audit),
        "send_status": "sent",
        "html_body": html_body,
        "text_preview": _html_to_text_preview(html_body),
        "report_contract": report_contract or {},
    }

    path = _get_preview_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def get_last_email_preview() -> dict | None:
    path = _get_preview_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
