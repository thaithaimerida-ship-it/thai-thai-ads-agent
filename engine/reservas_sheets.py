"""
Persistencia de reservas en Google Sheets (pestaña `Reservas`).
Regla de oro: un fallo aquí NUNCA rompe la reserva — se marca en GCS y el
monitor (lunes/viernes) alerta. Python puro + gspread (service account).

SEGURIDAD DE ESCRITURA: el spreadsheet también contiene la contabilidad
(Cortes_de_Caja, Ingresos_BD, ...). Este módulo escribe EXCLUSIVAMENTE con
worksheet.append_row (spreadsheets.values.append) sobre el worksheet `Reservas`.
La pestaña se resuelve POR NOMBRE; una vez resuelta, el append queda scoped al
sheetId de ese objeto, así que no puede tocar otras pestañas. PROHIBIDO
values.update / rangos absolutos.

FAIL-LOUD: el path de escritura NUNCA crea estado nuevo desde un except. Si la
pestaña `Reservas` no existe, o el spreadsheet ID / la credencial son inválidos,
se LANZA (el llamador lo marca en GCS y el monitor alerta). La pestaña se crea
UNA sola vez, explícita, en la migración (ensure_reservas_worksheet).
"""
import hashlib
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

RESERVAS_TAB = "Reservas"
RESERVAS_HEADER = [
    "id", "fecha_creacion", "nombre", "telefono", "email", "fecha_reserva",
    "hora_reserva", "personas", "ocasion", "notas", "origen", "estado", "notificaciones",
]
SHEETS_RW_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
_MERIDA = ZoneInfo("America/Merida")
_GCS_BUCKET = os.getenv("AGENT_GCS_BUCKET", "thai-thai-agent-data")
_FAILURES_BLOB = "reservas/persist_failures.json"
_MAX_ATTEMPTS = 3


def _now_merida() -> datetime:
    return datetime.now(_MERIDA)


def build_reservation_id(data: dict) -> str:
    """ID DETERMINÍSTICO por CONTENIDO de la reserva (SIN timestamp de creación).
    Dos envíos idénticos (doble clic, reenvío del navegador) → mismo id → no duplica,
    sin importar cuántos segundos pasen. Otra fecha/hora/persona/contacto → otro id.
    Separador '|' para evitar ambigüedad de fronteras entre campos.
    fecha_creacion es columna aparte y sí depende del reloj (America/Merida)."""
    raw = "|".join([
        str(data.get("email", "")).strip(),
        str(data.get("phone", "")).strip(),
        str(data.get("date", "")).strip(),   # fecha_reserva
        str(data.get("time", "")).strip(),   # hora_reserva
        str(data.get("guests", "")).strip(),  # personas
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def reservation_row(reservation_id: str, fecha_creacion: str, data: dict, notif_result: str) -> list:
    return [
        reservation_id,
        fecha_creacion,
        str(data.get("name", "")),
        str(data.get("phone", "")),
        str(data.get("email", "")),
        str(data.get("date", "")),
        str(data.get("time", "")),
        str(data.get("guests", "")),
        str(data.get("occasion") or ""),
        str(data.get("notas") or ""),
        str(data.get("origen") or "landing"),
        "confirmada",
        notif_result,
    ]


def _open_spreadsheet():
    """Abre el spreadsheet. LANZA si falta el ID, la credencial, o el SA no tiene
    acceso / el ID es inválido (gspread.open_by_key propaga la excepción)."""
    import gspread
    from engine.credentials import get_credentials
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID no configurado")
    creds = get_credentials(scopes=SHEETS_RW_SCOPES)
    if creds is None:
        raise RuntimeError("Credenciales de service account no disponibles")
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id)  # lanza si el ID es inválido o sin acceso


def _get_worksheet():
    """Resuelve la pestaña `Reservas` (por nombre). FAIL-LOUD: si no existe, o el
    spreadsheet/credencial es inválido, LANZA — NUNCA crea estado nuevo desde un except.
    La pestaña se crea UNA vez, explícita, en ensure_reservas_worksheet (migración)."""
    sh = _open_spreadsheet()
    return sh.worksheet(RESERVAS_TAB)  # gspread.WorksheetNotFound si falta → propaga


def ensure_reservas_worksheet():
    """SOLO para la migración (Task 5): crea la pestaña `Reservas` con su header si no
    existe, y la retorna. ÚNICO lugar que crea la pestaña, de forma explícita y una vez."""
    import gspread
    sh = _open_spreadsheet()
    try:
        return sh.worksheet(RESERVAS_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=RESERVAS_TAB, rows=2000, cols=len(RESERVAS_HEADER))
        ws.append_row(RESERVAS_HEADER, value_input_option="USER_ENTERED")
        return ws


def id_exists(ws, reservation_id: str) -> bool:
    # Trade-off aceptado: lee SOLO la columna A (1 request, no el sheet entero). Es O(n)
    # en nº de reservas, pero al volumen de Thai Thai (unas pocas/día) la columna A tarda
    # años en ser un problema. Si algún día el volumen se dispara, cambiar por un índice.
    try:
        return reservation_id in set(ws.col_values(1))
    except Exception:
        return False


def append_reservation(data: dict, notif_result: str, *, now=None, _ws=None, _sleep=None) -> dict:
    """Escribe UNA reserva. Idempotente por id. 3 reintentos backoff exponencial.
    Retorna {ok, id, row, error}. NUNCA lanza."""
    import time
    sleep = _sleep or time.sleep
    now = now or _now_merida()
    reservation_id = build_reservation_id(data)  # determinístico por contenido, sin reloj
    fecha_creacion = now.strftime("%Y-%m-%d %H:%M:%S")  # columna aparte, sí usa el reloj (Mérida)
    row = reservation_row(reservation_id, fecha_creacion, data, notif_result)

    last_err = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            ws = _ws or _get_worksheet()
            if id_exists(ws, reservation_id):
                logger.info("[reservas_sheets] id ya existe, no se duplica: %s", reservation_id)
                return {"ok": True, "id": reservation_id, "row": row, "error": None}
            # append_row → spreadsheets.values.append sobre ESTE worksheet (Reservas).
            # Sin table_range ni rango absoluto: append puro, imposible pisar otras pestañas.
            ws.append_row(
                row,
                value_input_option="USER_ENTERED",
                insert_data_option="INSERT_ROWS",
            )
            logger.info("[reservas_sheets] fila escrita id=%s", reservation_id)
            return {"ok": True, "id": reservation_id, "row": row, "error": None}
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            logger.warning("[reservas_sheets] intento %d/%d falló: %s", attempt, _MAX_ATTEMPTS, last_err)
            if attempt < _MAX_ATTEMPTS:
                sleep(2 ** (attempt - 1))  # 1, 2

    return {"ok": False, "id": reservation_id, "row": row, "error": last_err}


def list_reservations(limit: int = 50, *, _ws=None) -> list:
    ws = _ws or _get_worksheet()
    values = ws.get_all_values()
    if len(values) < 2:
        return []
    header, rows = values[0], values[1:]
    dicts = [dict(zip(header, r)) for r in rows if any(r)]
    return list(reversed(dicts))[:limit]


# ── Marca de fallos de persistencia en GCS (durable entre deploys) ──────────

def _get_bucket(_bucket=None):
    if _bucket is not None:
        return _bucket
    try:
        from google.cloud import storage
        return storage.Client().bucket(_GCS_BUCKET)
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] GCS no disponible: %s", e)
        return None


def read_persist_failures(*, _bucket=None) -> list:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        return []
    try:
        blob = bucket.blob(_FAILURES_BLOB)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text() or "[]")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo leer fallos GCS: %s", e)
        return []


def record_persist_failure(reservation_id: str, data: dict, error: str, *, _bucket=None) -> None:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        logger.error("[reservas_sheets] FALLO no persistido (sin GCS) id=%s data=%s", reservation_id, data)
        return
    try:
        failures = read_persist_failures(_bucket=bucket)
        failures.append({
            "id": reservation_id,
            "when": _now_merida().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
            "error": error,
        })
        bucket.blob(_FAILURES_BLOB).upload_from_string(
            json.dumps(failures, ensure_ascii=False), content_type="application/json")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo marcar fallo GCS id=%s: %s", reservation_id, e)


def clear_persist_failures(*, _bucket=None) -> None:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        return
    try:
        bucket.blob(_FAILURES_BLOB).upload_from_string("[]", content_type="application/json")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo limpiar fallos GCS: %s", e)
