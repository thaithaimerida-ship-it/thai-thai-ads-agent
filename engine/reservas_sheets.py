"""
Persistencia de reservas en Google Sheets (pestaña `Reservas`).
Regla de oro: un fallo aquí NUNCA rompe la reserva — se marca en GCS y el
monitor (lunes/viernes) alerta. Python puro + gspread (service account).

LIBRO DEDICADO: las reservas viven en un spreadsheet PROPIO (RESERVAS_SHEET_ID),
separado del de contabilidad (GOOGLE_SHEETS_SPREADSHEET_ID). La service account
tiene Editor solo en este libro; en el de contabilidad sigue read-only. Aun así,
este módulo escribe EXCLUSIVAMENTE con worksheet.append_row (spreadsheets.values.
append) sobre el worksheet `Reservas`; PROHIBIDO values.update / rangos absolutos.

FAIL-LOUD: el path de escritura NUNCA crea estado nuevo desde un except. Si la
pestaña `Reservas` no existe, o el spreadsheet ID / la credencial son inválidos,
se LANZA (el llamador lo marca en GCS y el monitor alerta). La pestaña se crea
UNA sola vez, explícita, en la migración (ensure_reservas_worksheet).
"""
import hashlib
import json
import logging
import os
import re
import unicodedata
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
_FAILURES_BLOB = "reservas/persist_failures.json"      # reserva NO guardada en Sheets
_UNCONFIRMED_BLOB = "reservas/unconfirmed.json"        # reserva guardada, cliente SIN confirmar
_POSIBLE_DUP_BLOB = "reservas/posible_duplicado.json"  # mismo id/slot, distinto nombre → alerta
_OCCASION_BLOB = "reservas/cambios_ocasion.json"       # mismo id+nombre, distinta ocasión → registro (sin alerta)
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


def _norm(s) -> str:
    """Normaliza texto para COMPARAR (no para el id): NFC (unifica acentos) +
    colapsa espacios internos + trim + casefold. Así 'Hugo', 'Hugo ' y 'HUGO'
    se consideran iguales, pero 'Hugo' vs 'Hugo G' NO."""
    s = unicodedata.normalize("NFC", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


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
    # Libro DEDICADO de reservas — separado del de contabilidad. La SA tiene Editor solo aquí;
    # en el libro de contabilidad (GOOGLE_SHEETS_SPREADSHEET_ID) sigue read-only.
    spreadsheet_id = os.getenv("RESERVAS_SHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("RESERVAS_SHEET_ID no configurado")
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


def _rows_for_id(ws, reservation_id: str) -> list:
    """Filas existentes con ese id → [{'nombre','ocasion'}]. Lee la hoja (get_all_values).
    Trade-off aceptado: O(n) en nº de reservas; al volumen de Thai Thai es despreciable
    años. Si el volumen se dispara, cambiar por un índice."""
    try:
        values = ws.get_all_values()
    except Exception:
        return []
    if len(values) < 2:
        return []
    header = values[0]
    try:
        i_id, i_nom, i_occ = header.index("id"), header.index("nombre"), header.index("ocasion")
    except ValueError:
        return []
    out = []
    for r in values[1:]:
        if len(r) > i_id and r[i_id] == reservation_id:
            out.append({"nombre": r[i_nom] if len(r) > i_nom else "",
                        "ocasion": r[i_occ] if len(r) > i_occ else ""})
    return out


def _classify_dup(existing: list, data: dict) -> tuple:
    """Decide qué hacer cuando el id (5 campos) ya existe. Compara nombre/ocasión
    NORMALIZADOS. Retorna (status, extra):
      'new'                -> id no existe → append
      'possible_duplicate' -> mismo id, distinto nombre → append + marca + ALERTA
      'occasion_change'    -> mismo id+nombre, distinta ocasión → corrige in-place + bitácora (sin alerta)
      'duplicate_ignored'  -> mismo id+nombre+ocasión → skip silencioso (doble-clic real)"""
    if not existing:
        return "new", {}
    norm_name = _norm(data.get("name"))
    same_name = [r for r in existing if _norm(r["nombre"]) == norm_name]
    if not same_name:
        return "possible_duplicate", {"nombres_existentes": [r["nombre"] for r in existing]}
    norm_occ = _norm(data.get("occasion"))
    if any(_norm(r["ocasion"]) == norm_occ for r in same_name):
        return "duplicate_ignored", {}
    return "occasion_change", {"ocasion_anterior": same_name[0]["ocasion"]}


def _mark(fn, *args) -> None:
    """Ejecuta un record_* de GCS sin dejar que su fallo rompa la reserva."""
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo marcar incidente: %s", e)


def _ws_spreadsheet_id(ws) -> str | None:
    sid = getattr(ws, "spreadsheet_id", None)
    if sid:
        return sid
    sp = getattr(ws, "spreadsheet", None)
    return getattr(sp, "id", None)


def _assert_reservas_book(ws) -> None:
    """HARD GUARD del único values.update del módulo: la celda SOLO se toca en el libro
    DEDICADO de reservas (RESERVAS_SHEET_ID). Si el ws apunta al libro de CONTABILIDAD
    (GOOGLE_SHEETS_SPREADSHEET_ID) o a cualquier otro, LANZA y no escribe nada. Esto impide
    que un values.update toque contabilidad aunque en el futuro alguien confunda env vars."""
    reservas_id = os.getenv("RESERVAS_SHEET_ID")
    conta_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    ws_id = _ws_spreadsheet_id(ws)
    if not reservas_id:
        raise RuntimeError("update abortado: RESERVAS_SHEET_ID no configurado")
    if ws_id != reservas_id:
        raise RuntimeError("update abortado: el worksheet no pertenece a RESERVAS_SHEET_ID")
    if conta_id and ws_id == conta_id:
        raise RuntimeError("update abortado: el target es el libro de CONTABILIDAD")


def _update_occasion_cell(ws, reservation_id: str, data: dict) -> None:
    """Actualiza SOLO la celda `ocasion` de la ÚNICA fila que hace match por id + nombre
    normalizado. Guardas: (1) hard guard de libro; (2) match exacto — si hay 0 o >1 filas,
    LANZA (nunca 'la fila que creo'). Escribe una sola celda de una sola fila."""
    _assert_reservas_book(ws)
    values = ws.get_all_values()
    header = values[0]
    i_id, i_nom, i_occ = header.index("id"), header.index("nombre"), header.index("ocasion")
    norm_name = _norm(data.get("name"))
    matches = [n for n, r in enumerate(values[1:], start=2)  # fila 1-based; header es la fila 1
               if len(r) > i_id and r[i_id] == reservation_id
               and len(r) > i_nom and _norm(r[i_nom]) == norm_name]
    if len(matches) != 1:
        raise RuntimeError(f"update_occasion abortado: se esperaba 1 fila match, hay {len(matches)}")
    ws.update_cell(matches[0], i_occ + 1, str(data.get("occasion") or ""))  # 1 celda, 1 fila
    logger.info("[reservas_sheets] ocasión corregida in-place id=%s fila=%d", reservation_id, matches[0])


def append_reservation(data: dict, notif_result: str, *, now=None, _ws=None, _sleep=None) -> dict:
    """Persiste UNA reserva con dedup-CON-ALERTA (id determinístico de 5 campos):
      - doble-clic idéntico (nombre+ocasión iguales, normalizados) → skip silencioso;
      - mismo id, distinto nombre (cuenta compartida / re-tecleo) → append + marca posible_duplicado;
      - mismo id+nombre, distinta ocasión → corrige la ocasión in-place (1 celda) + bitácora cambio_ocasion;
      - id nuevo → append.
    3 reintentos backoff. Retorna {ok, id, row, error, status}. NUNCA lanza."""
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
            existing = _rows_for_id(ws, reservation_id)
            status, extra = _classify_dup(existing, data)
            if status in ("new", "possible_duplicate"):
                # append_row → spreadsheets.values.append sobre ESTE worksheet (Reservas).
                # Sin rango absoluto: append puro, imposible pisar otras pestañas.
                ws.append_row(row, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            elif status == "occasion_change":
                # Corrige la ocasión in-place (única celda, guardas duras). Va en el flujo
                # principal: si falla, reintenta; si agota, se reporta (no se pierde en silencio).
                _update_occasion_cell(ws, reservation_id, data)
            # Side-effects durables (best-effort, tras éxito en la hoja):
            if status == "possible_duplicate":
                _mark(record_posible_duplicado, reservation_id, data, extra)
            elif status == "occasion_change":
                _mark(record_cambio_ocasion, reservation_id, data, extra)  # bitácora, sin alerta
            logger.info("[reservas_sheets] id=%s status=%s", reservation_id, status)
            return {"ok": True, "id": reservation_id, "row": row, "error": None, "status": status}
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            logger.warning("[reservas_sheets] intento %d/%d falló: %s", attempt, _MAX_ATTEMPTS, last_err)
            if attempt < _MAX_ATTEMPTS:
                sleep(2 ** (attempt - 1))  # 1, 2

    return {"ok": False, "id": reservation_id, "row": row, "error": last_err, "status": "error"}


def list_reservations(limit: int = 50, *, _ws=None) -> list:
    ws = _ws or _get_worksheet()
    values = ws.get_all_values()
    if len(values) < 2:
        return []
    header, rows = values[0], values[1:]
    dicts = [dict(zip(header, r)) for r in rows if any(r)]
    return list(reversed(dicts))[:limit]


# ── Marcadores durables en GCS (sobreviven reinicios/deploys) ───────────────
# Dos tipos de incidente, cada uno en su blob:
#   _FAILURES_BLOB   → reserva NO guardada en Sheets (red de seguridad = correo dueño)
#   _UNCONFIRMED_BLOB → reserva SÍ guardada pero cliente sin confirmación (hay que contactarlo)

def _get_bucket(_bucket=None):
    if _bucket is not None:
        return _bucket
    try:
        from google.cloud import storage
        return storage.Client().bucket(_GCS_BUCKET)
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] GCS no disponible: %s", e)
        return None


def _read_issues(blob_name: str, *, _bucket=None) -> list:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        return []
    try:
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text() or "[]")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo leer %s: %s", blob_name, e)
        return []


def _record_issue(blob_name: str, reservation_id: str, data: dict, extra: dict, *, _bucket=None) -> None:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        logger.error("[reservas_sheets] incidente no persistido (sin GCS) blob=%s id=%s data=%s",
                     blob_name, reservation_id, data)
        return
    try:
        issues = _read_issues(blob_name, _bucket=bucket)
        entry = {"id": reservation_id, "when": _now_merida().strftime("%Y-%m-%d %H:%M:%S"), "data": data}
        entry.update(extra)
        issues.append(entry)
        bucket.blob(blob_name).upload_from_string(
            json.dumps(issues, ensure_ascii=False), content_type="application/json")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo marcar %s id=%s: %s", blob_name, reservation_id, e)


def _clear_issues(blob_name: str, *, _bucket=None) -> None:
    bucket = _get_bucket(_bucket)
    if bucket is None:
        return
    try:
        bucket.blob(blob_name).upload_from_string("[]", content_type="application/json")
    except Exception as e:  # noqa: BLE001
        logger.error("[reservas_sheets] no se pudo limpiar %s: %s", blob_name, e)


# Reserva NO guardada en Sheets
def read_persist_failures(*, _bucket=None) -> list:
    return _read_issues(_FAILURES_BLOB, _bucket=_bucket)


def record_persist_failure(reservation_id: str, data: dict, error: str, *, _bucket=None) -> None:
    _record_issue(_FAILURES_BLOB, reservation_id, data, {"error": error}, _bucket=_bucket)


def clear_persist_failures(*, _bucket=None) -> None:
    _clear_issues(_FAILURES_BLOB, _bucket=_bucket)


# Reserva guardada pero cliente SIN confirmación (todas las notificaciones fallaron)
def read_unconfirmed(*, _bucket=None) -> list:
    return _read_issues(_UNCONFIRMED_BLOB, _bucket=_bucket)


def record_unconfirmed(reservation_id: str, data: dict, notif_result: str, *, _bucket=None) -> None:
    _record_issue(_UNCONFIRMED_BLOB, reservation_id, data, {"notif": notif_result}, _bucket=_bucket)


def clear_unconfirmed(*, _bucket=None) -> None:
    _clear_issues(_UNCONFIRMED_BLOB, _bucket=_bucket)


# Mismo id/slot, distinto nombre → posible duplicado (cuenta compartida) → ALERTA en monitor
def read_posible_duplicados(*, _bucket=None) -> list:
    return _read_issues(_POSIBLE_DUP_BLOB, _bucket=_bucket)


def record_posible_duplicado(reservation_id: str, data: dict, extra: dict, *, _bucket=None) -> None:
    _record_issue(_POSIBLE_DUP_BLOB, reservation_id, data,
                  {"nombre_nuevo": str(data.get("name", "")),
                   "nombres_existentes": extra.get("nombres_existentes", [])}, _bucket=_bucket)


def clear_posible_duplicados(*, _bucket=None) -> None:
    _clear_issues(_POSIBLE_DUP_BLOB, _bucket=_bucket)


# Mismo id+nombre, distinta ocasión → registro durable (SIN alerta) para no perder el cambio
def read_cambios_ocasion(*, _bucket=None) -> list:
    return _read_issues(_OCCASION_BLOB, _bucket=_bucket)


def record_cambio_ocasion(reservation_id: str, data: dict, extra: dict, *, _bucket=None) -> None:
    _record_issue(_OCCASION_BLOB, reservation_id, data,
                  {"ocasion_anterior": str(extra.get("ocasion_anterior", "")),
                   "ocasion_nueva": str(data.get("occasion") or "")}, _bucket=_bucket)


def clear_cambios_ocasion(*, _bucket=None) -> None:
    _clear_issues(_OCCASION_BLOB, _bucket=_bucket)
