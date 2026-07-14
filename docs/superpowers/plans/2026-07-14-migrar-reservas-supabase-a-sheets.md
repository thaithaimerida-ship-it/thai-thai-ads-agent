# Migrar reservas de Supabase a Google Sheets — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una reserva NUNCA se pierda por un problema de almacenamiento: notificar primero, persistir en Google Sheets después, y eliminar Supabase por completo.

**Architecture:** El endpoint `POST /reservations` cambia su orden de ejecución a validar → notificar (3 canales independientes) → persistir en la pestaña `Reservas` de un spreadsheet existente → responder 200 si al menos una notificación salió. La persistencia usa `gspread` (ya en el repo) con `spreadsheets.values.append` + INSERT_ROWS. Los fallos de persistencia se marcan en un blob de GCS durable que el monitor (lunes/viernes) lee para alertar. Un script de una corrida migra el histórico de Supabase Postgres a Sheets, y luego se elimina todo rastro de Supabase/Postgres del código y de Cloud Run.

**Tech Stack:** Python 3 puro, FastAPI, `gspread` + `google-auth` (service account ya configurada vía `engine.credentials`), `google-cloud-storage` (ya en el repo), `psycopg2` SOLO en el script de migración de una corrida. Sin ORM, sin LangChain/CrewAI/AutoGen.

## Global Constraints

- **Spreadsheet destino:** `17LNxz8jXPWF9G2d0Rwa1Mzw-6s1brtJzYufnyOI42FI` (env `GOOGLE_SHEETS_SPREADSHEET_ID`), pestaña nueva `Reservas`.
- **Zona horaria de `fecha_creacion`:** `America/Merida` (usar `zoneinfo.ZoneInfo("America/Merida")`), NUNCA UTC.
- **Una reserva NUNCA se pierde por almacenamiento:** un fallo de Sheets se loguea a ERROR con el payload completo y se marca en GCS, pero NO rompe la respuesta ni devuelve 500.
- **Responder 200 si al menos una notificación salió.** Nunca 500 por fallo de persistencia.
- **Cada canal de notificación en su propio `try/except`.** Si uno falla, los otros siguen.
- **Correo a Hugo (`thaithaimerida@gmail.com`) es la red de seguridad final:** debe incluir TODOS los datos de la reserva.
- **NO tocar `ReservationModal.jsx` ni nada de `thai-thai-web`.** El contrato del frontend no cambia. Campos nuevos (`notas`, `origen`) se agregan como OPCIONALES al modelo Pydantic (retrocompatible).
- **NO tocar** lógica de Google Ads ni Meta CAPI.
- **Cloud Run — `--set-env-vars` PROHIBIDO en cualquier comando gcloud, con o sin otros flags.** Solo `--update-env-vars` o `--remove-secrets`. `--set-env-vars` borra TODAS las env vars del servicio (Google Ads, Meta CAPI, GloriaFood, GBP) → es un incidente, no un bug.
- **UN SOLO DEPLOY, al final, y SOLO después de que la Task 5 pase su verificación de conteos.** Entre Task 3 y Task 5 el sistema lee de un Sheet vacío: aceptable en local, NUNCA en producción. Ningún `gcloud run deploy` ni `services update` ocurre antes de que los conteos cuadren. Todos los commits hasta entonces son locales (sin push, sin deploy).
- **No hay dashboard.** La salida es por correo.
- **No reactivar el agente autónomo viejo** (apagado a propósito).
- **No desplegar ni commitear sin aprobación de Hugo.**
- **PII NUNCA en git.** El backup CSV (nombres, correos, teléfonos de clientes) se guarda FUERA del repo (`C:\proyectos\thai-thai\backups\`), nunca se commitea. `.gitignore` bloquea `*.csv`, `backups/` y `docs/superpowers/backups/`. Verificar `git status` + `git ls-files "*.csv"` (vacío) antes de CUALQUIER commit. El repo ya tuvo incidente de GitGuardian; PII en el historial es peor e irreversible tras push.
- Persistencia (`spreadsheets.values.append`) con INSERT_ROWS: append atómico, sin leer-última-fila.
- 3 reintentos con backoff exponencial ante error de la API de Sheets. Idempotencia por `id` antes de escribir.

## File Structure

- **Create `engine/reservas_sheets.py`** — módulo de persistencia de reservas. Responsabilidad única: mapear una reserva al esquema de 13 columnas, escribir en la pestaña `Reservas` con reintentos + idempotencia, leer reservas, y marcar/leer/limpiar fallos de persistencia en GCS. Python puro + gspread + google-cloud-storage.
- **Create `migrar_reservas_a_sheets.py`** (raíz) — script de UNA corrida: lee Supabase Postgres y escribe el histórico en `Reservas`, imprimiendo `COUNT(*)` vs filas escritas.
- **Create `tests/test_reservas_sheets.py`** — tests de mapeo de fila, `id` idempotente, reintentos, marca de fallo GCS (todo con I/O mockeado).
- **Create `tests/test_reservations_endpoint_order.py`** — test de la "prueba de fuego": notificar-antes-de-persistir, 200 aunque Sheets truene.
- **Modify `routes/reservations.py`** — reescribir `create_reservation` (orden nuevo) y `get_reservations` (leer de Sheets); eliminar `_get_supabase_conn` y la rama SQLite.
- **Modify `engine/monitor_sources.py`** — eliminar `build_keepalive_db`; agregar `build_reservas_persist_status()` (lee marca GCS).
- **Modify `routes/monitor.py`** — `_ctx_keepalive` → `_ctx_reservas_persist`; key de contexto `keepalive_db` → `reservas_persist`.
- **Modify `engine/monitor_email_renderer.py`** — `_keepalive_alert` → `_reservas_persist_alert` (nueva copia).
- **Modify `engine/monitor_digest_v3.py`** — key `keepalive_db` → `reservas_persist`.
- **Modify `main.py`** — eliminar la creación de la tabla SQLite `reservations`.
- **Modify `requirements.txt`** — quitar `psycopg2-binary` (solo lo usará el script de migración, que se corre una vez con instalación temporal).
- **Delete/replace `tests/test_keepalive.py`** — reemplazar por tests de la alerta nueva.

---

### Task 1: `engine/reservas_sheets.py` — persistencia en Sheets (append + idempotencia + reintentos)

**Files:**
- Create: `engine/reservas_sheets.py`
- Test: `tests/test_reservas_sheets.py`

**Interfaces:**
- Produces:
  - `RESERVAS_TAB = "Reservas"`
  - `RESERVAS_HEADER: list[str]` — las 13 columnas en orden.
  - `build_reservation_id(data: dict, now_merida: datetime) -> str` — `"YYYYMMDDHHMMSS-<hash6>"`.
  - `reservation_row(reservation_id: str, fecha_creacion: str, data: dict, notif_result: str) -> list[str]` — 13 celdas en el orden de `RESERVAS_HEADER`.
  - `append_reservation(data: dict, notif_result: str, *, now: datetime | None = None, _ws=None, _sleep=None) -> dict` — retorna `{"ok": bool, "id": str, "row": list, "error": str | None}`. Idempotente por `id`. 3 reintentos backoff.
  - `list_reservations(limit: int = 50, *, _ws=None) -> list[dict]` — lee la pestaña, devuelve las más recientes primero.
  - `record_persist_failure(reservation_id: str, data: dict, error: str, *, _bucket=None) -> None` — agrega a `reservas/persist_failures.json` en GCS.
  - `read_persist_failures(*, _bucket=None) -> list[dict]` — lee el blob (o `[]`).
  - `clear_persist_failures(*, _bucket=None) -> None` — vacía el blob.

- [ ] **Step 1: Escribir tests que fallan (mapeo de fila + id + idempotencia + reintentos)**

```python
# tests/test_reservas_sheets.py
import itertools
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from engine import reservas_sheets as rs


def _data():
    return {
        "name": "Ana López", "email": "ana@x.com", "phone": "+52 999 111 2222",
        "date": "2026-07-20", "time": "20:30", "guests": "4",
        "occasion": "Cumpleaños", "notas": "junto a la ventana", "origen": "landing",
    }


def test_header_has_13_columns_in_order():
    assert rs.RESERVAS_HEADER == [
        "id", "fecha_creacion", "nombre", "telefono", "email", "fecha_reserva",
        "hora_reserva", "personas", "ocasion", "notas", "origen", "estado", "notificaciones",
    ]


def test_build_reservation_id_is_timestamp_plus_hash():
    now = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    rid = rs.build_reservation_id(_data(), now)
    assert rid.startswith("20260714210509-")
    assert len(rid.split("-")[1]) == 6


def test_reservation_row_maps_schema():
    now = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    rid = rs.build_reservation_id(_data(), now)
    row = rs.reservation_row(rid, "2026-07-14 21:05:09", _data(), "email_cliente:ok, email_dueño:ok, whatsapp:error")
    assert row == [
        rid, "2026-07-14 21:05:09", "Ana López", "+52 999 111 2222", "ana@x.com",
        "2026-07-20", "20:30", "4", "Cumpleaños", "junto a la ventana", "landing",
        "confirmada", "email_cliente:ok, email_dueño:ok, whatsapp:error",
    ]


def test_origen_defaults_to_landing_when_missing():
    d = _data(); d.pop("origen")
    now = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    row = rs.reservation_row("x", "t", d, "")
    assert row[10] == "landing"


class _FakeWS:
    def __init__(self, ids=()):
        self._ids = list(ids)
        self.appended = []
        self.fail_times = 0

    def col_values(self, n):
        return ["id"] + self._ids

    def append_row(self, row, **kw):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("Sheets API 503")
        self.appended.append(row)


def test_append_is_idempotent_by_id():
    ws = _FakeWS()
    d = _data()
    now = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    rid = rs.build_reservation_id(d, now)
    ws._ids.append(rid)  # ya existe
    out = rs.append_reservation(d, "email_cliente:ok", now=now, _ws=ws)
    assert out["ok"] is True and out["id"] == rid
    assert ws.appended == []  # NO duplica


def test_append_retries_then_succeeds():
    ws = _FakeWS(); ws.fail_times = 2
    sleeps = []
    out = rs.append_reservation(_data(), "email_cliente:ok", _ws=ws, _sleep=sleeps.append)
    assert out["ok"] is True
    assert len(ws.appended) == 1
    assert sleeps == [1, 2]  # backoff exponencial 1,2 (tras fallos 1 y 2)


def test_append_gives_up_after_3_attempts():
    ws = _FakeWS(); ws.fail_times = 99
    out = rs.append_reservation(_data(), "email_cliente:ok", _ws=ws, _sleep=lambda *_: None)
    assert out["ok"] is False and "Sheets API 503" in out["error"]
    assert ws.appended == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -m pytest tests/test_reservas_sheets.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'engine.reservas_sheets'`.

- [ ] **Step 3: Implementar `engine/reservas_sheets.py`**

```python
"""
Persistencia de reservas en Google Sheets (pestaña `Reservas`).
Regla de oro: un fallo aquí NUNCA rompe la reserva — se marca en GCS y el
monitor (lunes/viernes) alerta. Python puro + gspread (service account).

SEGURIDAD DE ESCRITURA: el spreadsheet también contiene la contabilidad
(Cortes_de_Caja, Ingresos_BD, ...). Este módulo escribe EXCLUSIVAMENTE con
worksheet.append_row (spreadsheets.values.append) sobre el objeto worksheet
`Reservas`, que gspread scope por sheetId. PROHIBIDO usar values.update o
rangos absolutos: pisarían otras pestañas.
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


def build_reservation_id(data: dict, now_merida: datetime) -> str:
    ts = now_merida.strftime("%Y%m%d%H%M%S")
    raw = f"{data.get('name','')}|{data.get('email','')}|{data.get('phone','')}|" \
          f"{data.get('date','')}|{data.get('time','')}|{ts}"
    short = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return f"{ts}-{short}"


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


def _get_worksheet():
    """Abre (o crea) la pestaña `Reservas` con su header. Requiere scope de escritura."""
    import gspread
    from engine.credentials import get_credentials
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID no configurado")
    creds = get_credentials(scopes=SHEETS_RW_SCOPES)
    if creds is None:
        raise RuntimeError("Credenciales de service account no disponibles")
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(RESERVAS_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=RESERVAS_TAB, rows=2000, cols=len(RESERVAS_HEADER))
        ws.append_row(RESERVAS_HEADER, value_input_option="USER_ENTERED")
    return ws


def id_exists(ws, reservation_id: str) -> bool:
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
    reservation_id = build_reservation_id(data, now)
    fecha_creacion = now.strftime("%Y-%m-%d %H:%M:%S")
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
```

- [ ] **Step 4: Correr los tests hasta verde**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -m pytest tests/test_reservas_sheets.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Agregar test de la marca GCS (fallo) y correr**

```python
# añadir a tests/test_reservas_sheets.py
class _FakeBlob:
    def __init__(self, store, key):
        self.store, self.key = store, key
    def exists(self):
        return self.key in self.store
    def download_as_text(self):
        return self.store.get(self.key, "")
    def upload_from_string(self, s, content_type=None):
        self.store[self.key] = s


class _FakeBucket:
    def __init__(self):
        self.store = {}
    def blob(self, key):
        return _FakeBlob(self.store, key)


def test_record_and_read_persist_failure_roundtrip():
    b = _FakeBucket()
    rs.record_persist_failure("id-1", _data(), "Sheets 503", _bucket=b)
    rs.record_persist_failure("id-2", _data(), "Sheets 500", _bucket=b)
    fails = rs.read_persist_failures(_bucket=b)
    assert [f["id"] for f in fails] == ["id-1", "id-2"]
    rs.clear_persist_failures(_bucket=b)
    assert rs.read_persist_failures(_bucket=b) == []
```

Run: `... -m pytest tests/test_reservas_sheets.py -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add engine/reservas_sheets.py tests/test_reservas_sheets.py
git commit -m "feat(reservas): módulo reservas_sheets (append idempotente + retry + marca GCS)"
```

---

### Task 2: Reescribir `POST /reservations` — notificar primero, persistir después

**Files:**
- Modify: `routes/reservations.py:21-29` (modelo), `routes/reservations.py:181-228` (owner email con TODOS los campos), `routes/reservations.py:231-279` (handler)
- Test: `tests/test_reservations_endpoint_order.py`

**Interfaces:**
- Consumes: `engine.reservas_sheets.append_reservation`, `record_persist_failure` (Task 1).
- Produces: `create_reservation` responde `{"status","reservation_id","message","persisted": bool}`; helper `_notify_all(reservation) -> tuple[str, bool]` que retorna (`"email_cliente:ok, email_dueño:ok, whatsapp:error"`, `alguna_ok`).

- [ ] **Step 1: Escribir el test de la prueba de fuego**

```python
# tests/test_reservations_endpoint_order.py
import asyncio
from routes import reservations as R


def _payload():
    return R.ReservationRequest(
        name="Ana", email="ana@x.com", phone="+529990001122",
        date="2026-07-20", time="20:30", guests="4", occasion="Cumple",
    )


def test_returns_200_even_if_sheets_fails(monkeypatch):
    calls = {"cliente": 0, "owner": 0, "wa": 0, "failure_marked": 0}
    monkeypatch.setattr(R, "send_email_to_customer", lambda r: calls.__setitem__("cliente", 1))
    monkeypatch.setattr(R, "send_email_to_owner", lambda r: calls.__setitem__("owner", 1))
    monkeypatch.setattr(R, "send_whatsapp_restaurant", lambda r: calls.__setitem__("wa", 1))
    # Sheets truena:
    monkeypatch.setattr(R.reservas_sheets, "append_reservation",
                        lambda *a, **k: {"ok": False, "id": "x", "row": [], "error": "cred inválida"})
    monkeypatch.setattr(R.reservas_sheets, "record_persist_failure",
                        lambda *a, **k: calls.__setitem__("failure_marked", 1))

    out = asyncio.run(R.create_reservation(_payload()))
    assert out["status"] == "success"       # NO 500
    assert out["persisted"] is False
    assert calls == {"cliente": 1, "owner": 1, "wa": 1, "failure_marked": 1}


def test_notify_all_isolates_channel_failures(monkeypatch):
    monkeypatch.setattr(R, "send_email_to_customer", lambda r: (_ for _ in ()).throw(RuntimeError("smtp down")))
    monkeypatch.setattr(R, "send_email_to_owner", lambda r: None)
    monkeypatch.setattr(R, "send_whatsapp_restaurant", lambda r: None)
    result, any_ok = R._notify_all(_payload())
    assert "email_cliente:error" in result
    assert "email_dueño:ok" in result and "whatsapp:ok" in result
    assert any_ok is True
```

- [ ] **Step 2: Correr para ver fallar**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -m pytest tests/test_reservations_endpoint_order.py -v`
Expected: FAIL (`AttributeError: module has no attribute 'reservas_sheets'` / `_notify_all`).

- [ ] **Step 3: Agregar campos opcionales al modelo**

En `routes/reservations.py`, reemplazar el modelo (líneas 21-29):

```python
class ReservationRequest(BaseModel):
    name: str
    email: str
    phone: str
    date: str
    time: str
    guests: str
    occasion: Optional[str] = None
    notas: Optional[str] = None
    origen: Optional[str] = "landing"
```

- [ ] **Step 4: Añadir import y helper `_notify_all`**

Cerca de los imports de `routes/reservations.py` añadir:

```python
from engine import reservas_sheets
```

Antes de `create_reservation` añadir el helper (cada canal aislado):

```python
def _notify_all(reservation: "ReservationRequest") -> tuple[str, bool]:
    """Dispara los 3 canales, cada uno aislado. Retorna (resumen, alguna_ok)."""
    resultados = []
    any_ok = False
    for etiqueta, fn in (
        ("email_cliente", send_email_to_customer),
        ("email_dueño", send_email_to_owner),
        ("whatsapp", send_whatsapp_restaurant),
    ):
        try:
            fn(reservation)
            resultados.append(f"{etiqueta}:ok")
            any_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"[notify_failed] canal={etiqueta} error={e}")
            resultados.append(f"{etiqueta}:error")
    return ", ".join(resultados), any_ok
```

- [ ] **Step 5: Reescribir el handler `create_reservation`**

Reemplazar `create_reservation` (líneas 231-279) por:

```python
@router.post("/reservations")
async def create_reservation(reservation: ReservationRequest):
    """Orden nuevo: validar → notificar (independiente) → persistir en Sheets.
    Una reserva NUNCA se pierde por almacenamiento. 200 si al menos una notificación salió."""
    # 1) Validación: Pydantic ya validó el payload al entrar.

    # 2) Notificar — cada canal aislado. El correo al dueño es la red de seguridad final.
    notif_result, any_ok = _notify_all(reservation)
    print(f"[reservation_notified] name={reservation.name} date={reservation.date} -> {notif_result}")

    # 3) Persistir en Google Sheets — su fallo NO rompe la respuesta.
    data = reservation.model_dump()
    persist = reservas_sheets.append_reservation(data, notif_result)
    if not persist["ok"]:
        print(f"[reservation_persist_FAILED] id={persist['id']} error={persist['error']} data={data}")
        try:
            reservas_sheets.record_persist_failure(persist["id"], data, persist["error"] or "desconocido")
        except Exception as e:  # noqa: BLE001
            print(f"[reservation_persist_mark_failed] error={e}")

    # 4) Responder 200 si al menos una notificación salió.
    if not any_ok:
        raise HTTPException(status_code=502, detail="No se pudo notificar la reserva por ningún canal")

    return {
        "status": "success",
        "reservation_id": persist["id"],
        "persisted": persist["ok"],
        "message": f"Reserva confirmada para {reservation.name} el {reservation.date} a las {reservation.time}",
    }
```

- [ ] **Step 6: Incluir TODOS los campos en el correo al dueño**

En `send_email_to_owner` (bloque `restaurant_html`, ~línea 197), añadir `notas` y `origen` al detalle. Después de la línea de `Email:` agregar:

```python
        notas_line = f"<p style='margin:6px 0;color:#a1a1aa'><b>Notas:</b> {reservation.notas}</p>" if reservation.notas else ""
```

E insertar `{notas_line}` en el HTML tras la línea de Email, y añadir el origen al subject:

```python
    msg["Subject"] = f"[RESERVA] {reservation.name} — {reservation.date} {reservation.time} ({reservation.guests} pers.)"
```

(El correo ya incluye nombre, fecha, hora, personas, ocasión, teléfono, email; con notas queda completo — red de seguridad total.)

- [ ] **Step 7: Correr tests hasta verde**

Run: `... -m pytest tests/test_reservations_endpoint_order.py -v`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add routes/reservations.py tests/test_reservations_endpoint_order.py
git commit -m "feat(reservas): notificar antes de persistir; 200 aunque Sheets falle; correo dueño con todos los datos"
```

---

### Task 3: `GET /reservations` lee de Sheets; eliminar Supabase/SQLite del endpoint

**Files:**
- Modify: `routes/reservations.py:31-40` (borrar `_get_supabase_conn`), `routes/reservations.py:282-316` (reescribir GET)
- Modify: `routes/reservations.py:13` (quitar import `get_db_path` si ya no se usa)

**Interfaces:**
- Consumes: `engine.reservas_sheets.list_reservations` (Task 1).

- [ ] **Step 1: Reescribir `get_reservations` para leer de Sheets**

Reemplazar `get_reservations` (líneas 282-316) por:

```python
@router.get("/reservations")
async def get_reservations(limit: int = 50):
    """Lee las reservas más recientes de la pestaña `Reservas` (Google Sheets)."""
    try:
        reservas = reservas_sheets.list_reservations(limit=limit)
        return {"status": "success", "total": len(reservas), "reservations": reservas}
    except Exception as e:  # noqa: BLE001
        print(f"[get_reservations_error] {e}")
        return {"status": "error", "message": str(e), "reservations": []}
```

- [ ] **Step 2: Borrar `_get_supabase_conn` (líneas 31-40) y el import de `get_db_path`**

Eliminar la función `_get_supabase_conn` completa. Quitar `from engine.db_sync import get_db_path` (línea 13) si ninguna otra parte del archivo lo usa (tras esta tarea, no lo usa).

- [ ] **Step 3: Verificar que el módulo importa y no quedan referencias a Supabase/SQLite**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -c "import routes.reservations"`
Expected: sin error.
Run: `grep -ni "supabase\|psycopg2\|sqlite\|get_db_path" routes/reservations.py`
Expected: sin resultados.

- [ ] **Step 4: Correr toda la suite de reservas**

Run: `... -m pytest tests/test_reservas_sheets.py tests/test_reservations_endpoint_order.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add routes/reservations.py
git commit -m "refactor(reservas): GET lee de Sheets; eliminar Supabase/SQLite del endpoint"
```

---

### Task 4: Monitor — reemplazar keepalive por DOS alertas de reservas

> **AJUSTE (post Task 2):** el monitor renderea DOS alertas independientes, ambas leyendo GCS:
> 1. **persist_failure** (`read_persist_failures`) → "N reservas no se guardaron en el libro — están en tu correo". Un conteo basta: esas reservas están en el correo del dueño con todos los datos.
> 2. **unconfirmed** (`read_unconfirmed`) → "N reservas guardadas SIN confirmación al cliente — contáctalos". Estas SÍ están en Sheets (persisted=True) pero el cliente no recibió aviso. La alerta DEBE listar, por cada una, **nombre + teléfono + fecha/hora de la reserva** (de `entry["data"]`) para que Hugo pueda llamarles sin ir a buscar al Sheet. Un conteo suelto NO sirve aquí.



**Files:**
- Modify: `engine/monitor_sources.py:45-` (borrar `build_keepalive_db`; añadir `build_reservas_persist_status`)
- Modify: `routes/monitor.py:16-20` (imports), `routes/monitor.py:124-129` (`_ctx_keepalive`→`_ctx_reservas_persist`), `routes/monitor.py:144` (lista de tareas)
- Modify: `engine/monitor_digest_v3.py:475` (key)
- Modify: `engine/monitor_email_renderer.py:547-560` (`_keepalive_alert`→`_reservas_persist_alert`), `:565` (llamada)
- Replace: `tests/test_keepalive.py` → `tests/test_reservas_persist_alert.py`

**Interfaces:**
- Consumes: `engine.reservas_sheets.read_persist_failures` (Task 1).
- Produces: `build_reservas_persist_status() -> {"failed_count": int, "checked": bool, "ids": list[str]}`. Digest key `reservas_persist`.

- [ ] **Step 1: Escribir tests de la alerta nueva (reemplazo de test_keepalive.py)**

```python
# tests/test_reservas_persist_alert.py
from engine import monitor_sources
from engine.monitor_email_renderer import render_monitor_email
from tests.test_monitor_email_renderer import _digest


def test_status_cuenta_fallos(monkeypatch):
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_persist_failures",
                        lambda: [{"id": "a"}, {"id": "b"}])
    r = monitor_sources.build_reservas_persist_status()
    assert r["failed_count"] == 2 and r["checked"] is True


def test_sin_fallos_no_alerta():
    d = _digest()
    d["reservas_persist"] = {"failed_count": 0, "checked": True, "ids": []}
    out = render_monitor_email(d)
    assert "no se guardaron en el libro" not in out["html_email"]


def test_con_fallos_alerta():
    d = _digest()
    d["reservas_persist"] = {"failed_count": 3, "checked": True, "ids": ["a", "b", "c"]}
    out = render_monitor_email(d)
    assert "3 reservas no se guardaron en el libro" in out["html_email"]
    assert "están en tu correo" in out["text_email"]
```

- [ ] **Step 2: Correr para ver fallar**

Run: `... -m pytest tests/test_reservas_persist_alert.py -v`
Expected: FAIL (`build_reservas_persist_status` no existe).

- [ ] **Step 3: En `engine/monitor_sources.py` borrar `build_keepalive_db` y añadir el nuevo source**

Eliminar la función `build_keepalive_db` completa (y el `import psycopg2` dentro de ella). Añadir arriba `from engine import reservas_sheets` y:

```python
def build_reservas_persist_status() -> dict:
    """Cuenta reservas que fallaron al guardarse en Sheets (marca durable en GCS).
    READ-ONLY. Devuelve {failed_count, checked, ids}."""
    try:
        fails = reservas_sheets.read_persist_failures()
        return {"failed_count": len(fails), "checked": True, "ids": [f.get("id") for f in fails]}
    except Exception as e:  # noqa: BLE001
        print(f"[reservas_persist_status] error: {e}")
        return {"failed_count": 0, "checked": False, "ids": []}
```

- [ ] **Step 4: En `routes/monitor.py` cambiar el import y el context builder**

Import (líneas 16-20): quitar `build_keepalive_db`, añadir `build_reservas_persist_status`.
Reemplazar `_ctx_keepalive` (124-129):

```python
def _ctx_reservas_persist() -> dict:
    # Reservas que no se guardaron en Sheets (marca durable en GCS).
    try:
        return {"reservas_persist": build_reservas_persist_status()}
    except Exception:
        return {"reservas_persist": {"failed_count": 0, "checked": False, "ids": []}}
```

En la lista `tareas` (línea 144) reemplazar `_ctx_keepalive` por `_ctx_reservas_persist`.

- [ ] **Step 5: En `engine/monitor_digest_v3.py` cambiar la key (línea 475)**

```python
        "reservas_persist": context.get("reservas_persist"),
```

- [ ] **Step 6: En `engine/monitor_email_renderer.py` reemplazar el renderer**

Reemplazar `_keepalive_alert` (547-560) por:

```python
def _reservas_persist_alert(digest: dict[str, Any], text: list[str]) -> str:
    """Alerta SOLO si hubo reservas que no se guardaron en Sheets (están en el correo del dueño)."""
    k = digest.get("reservas_persist") or {}
    n = k.get("failed_count", 0)
    if not k.get("checked") or not n:
        return ""
    text.append(f"⚠ ALERTA: {n} reservas no se guardaron en el libro (Google Sheets) — "
                "están en tu correo. Revísalas y captúralas a mano.")
    return (
        "<div style=\"border:2px solid #A32D2D;background:#fbe9e7;border-radius:8px;padding:12px;margin-bottom:12px;\">"
        f"<p style=\"font-size:13px;font-weight:bold;color:#A32D2D;margin:0 0 4px;\">⚠ {n} reservas no se guardaron en el libro</p>"
        "<p style=\"font-size:11.5px;color:#5a1f1f;margin:0;line-height:1.5;\">Estas reservas SÍ te llegaron por correo "
        "(la notificación nunca se pierde), pero no pudieron escribirse en Google Sheets. Captúralas a mano en la pestaña "
        "<b>Reservas</b>.</p></div>"
    )
```

En `_render_full_html` (línea 565) reemplazar `_keepalive_alert(digest, text)` por `_reservas_persist_alert(digest, text)`.

- [ ] **Step 7: Borrar `tests/test_keepalive.py` y correr la suite del monitor**

```bash
git rm tests/test_keepalive.py
```
Run: `... -m pytest tests/test_reservas_persist_alert.py tests/test_monitor_email_renderer.py tests/test_monitor_renderer_v2.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add engine/monitor_sources.py routes/monitor.py engine/monitor_digest_v3.py engine/monitor_email_renderer.py tests/test_reservas_persist_alert.py
git commit -m "feat(monitor): reemplazar keepalive Supabase por alerta de reservas no guardadas en Sheets"
```

---

### Task 5: Script de migración de una corrida `migrar_reservas_a_sheets.py`

**Files:**
- Create: `migrar_reservas_a_sheets.py` (raíz)

**Interfaces:**
- Consumes: `engine.reservas_sheets.RESERVAS_HEADER`, `_get_worksheet`, `build_reservation_id`, `reservation_row`; `DATABASE_URL` (Supabase, aún activo).

- [ ] **Step 1: Implementar el script (lee Supabase, escribe a Sheets, cuenta y compara)**

```python
"""
Migración de UNA corrida: Supabase Postgres -> pestaña `Reservas` en Google Sheets.
Uso:
  $env:DATABASE_URL='...'; python migrar_reservas_a_sheets.py
Imprime COUNT(*) de Supabase y filas escritas en Sheets. DEBEN coincidir.
NO se ejecuta en producción; es un script manual de una sola vez.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

from engine import reservas_sheets as rs

_MERIDA = ZoneInfo("America/Merida")


def _fmt_creacion(created_at) -> str:
    if isinstance(created_at, datetime):
        dt = created_at.astimezone(_MERIDA) if created_at.tzinfo else created_at
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(created_at or "")


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL no configurada — apúntala a Supabase antes de correr.")

    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reservations")
    total_supabase = cur.fetchone()[0]

    cur.execute("""
        SELECT name, email, phone, date::text, time::text, guests, occasion, status, created_at
        FROM reservations ORDER BY created_at ASC
    """)
    filas = cur.fetchall()
    conn.close()

    ws = rs.ensure_reservas_worksheet()  # ÚNICO lugar que crea la pestaña Reservas (explícito)
    existentes = set(ws.col_values(1))
    escritas = 0

    for (name, email, phone, date_, time_, guests, occasion, status, created_at) in filas:
        data = {
            "name": name, "email": email, "phone": phone, "date": date_, "time": time_,
            "guests": guests, "occasion": occasion or "", "notas": "", "origen": "migracion_supabase",
        }
        rid = rs.build_reservation_id(data)  # determinístico por contenido, sin timestamp
        if rid in existentes:
            continue
        row = rs.reservation_row(rid, _fmt_creacion(created_at), data, "")
        row[11] = status or "confirmada"  # respetar estado histórico
        # append puro sobre la pestaña Reservas — nunca values.update ni rango absoluto.
        ws.append_row(row, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
        existentes.add(rid)
        escritas += 1

    filas_en_sheets = len(ws.col_values(1)) - 1  # menos header
    print("======================================")
    print(f"COUNT(*) Supabase : {total_supabase}")
    print(f"Filas escritas    : {escritas}")
    print(f"Filas en Sheets   : {filas_en_sheets}")
    print(f"CUADRA            : {filas_en_sheets >= total_supabase}")
    print("======================================")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verificar que importa sin correr la migración**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -c "import migrar_reservas_a_sheets"`
Expected: sin error.

- [ ] **Step 3: Commit (script listo, corrida real es un paso manual con aprobación)**

```bash
git add migrar_reservas_a_sheets.py
git commit -m "feat(reservas): script de migración una-corrida Supabase -> Sheets con verificación de conteo"
```

- [ ] **Step 4: BACKUP CSV de Supabase (RED DE SEGURIDAD — CONTIENE PII, NUNCA SE COMMITEA)**

⚠️ **El CSV tiene PII de clientes (nombres, correos, teléfonos). JAMÁS se commitea al repo.** Este repo ya tuvo un incidente de GitGuardian; PII en el historial de git es peor e irreversible tras push. El backup vive **FUERA del repo**: `C:\proyectos\thai-thai\backups\` (el repo es `C:\proyectos\thai-thai\thai-thai-ads-agent\`, un nivel adentro).

Primero blindar `.gitignore` (por si algún CSV termina dentro del repo por accidente):

```bash
printf '\n# Backups con PII de clientes — NUNCA commitear\n*.csv\nbackups/\ndocs/superpowers/backups/\n' >> .gitignore
git add .gitignore
git commit -m "chore: gitignore para backups con PII (nunca commitear CSV)"
```

Generar el backup FUERA del repo (requiere `psycopg2` local, confirmado 2.9.12):

```powershell
New-Item -ItemType Directory -Force 'C:\proyectos\thai-thai\backups' | Out-Null
$env:DATABASE_URL='<url supabase>'
& 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -c @'
import os, csv, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
cur = conn.cursor()
cur.execute("SELECT * FROM reservations ORDER BY created_at ASC")
cols = [d[0] for d in cur.description]
with open(r"C:\proyectos\thai-thai\backups\reservas_supabase_2026-07-14.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(cols); w.writerows(cur.fetchall())
print("Backup filas:", cur.rowcount)
conn.close()
'@
```

Verificar que el archivo `C:\proyectos\thai-thai\backups\reservas_supabase_2026-07-14.csv` existe con todas las filas. **NO se commitea.** Confirmar que git NO lo ve:

```bash
git status --short          # el CSV NO debe aparecer
git ls-files "*.csv"        # debe salir vacío
```

Solo si ambos salen limpios, continuar.

- [ ] **Step 5: CORRIDA REAL de migración (manual, requiere aprobación de Hugo)**

Con Supabase despausado y el backup ya guardado:
`$env:DATABASE_URL='<url supabase>'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' migrar_reservas_a_sheets.py`
Pegar la salida (COUNT Supabase vs filas en Sheets). **Solo avanzar a Task 6 si cuadran.** Ningún deploy ocurre antes de este punto.

---

### Task 6: Eliminar Supabase del código y limpiar Cloud Run

**Files:**
- Modify: `main.py` (eliminar creación de tabla SQLite `reservations`)
- Modify: `requirements.txt:16` (quitar `psycopg2-binary`)

**Precondición:** Task 5 Step 5 verificado (los conteos cuadran) y backup CSV guardado (Task 5 Step 4).

- [ ] **Step 1: Localizar y eliminar la creación de la tabla `reservations` en `main.py`**

Run: `grep -n "reservations" main.py`
Eliminar el bloque `CREATE TABLE ... reservations ...` (creación de tabla SQLite de reservas) y cualquier `DATABASE_URL` residual en `main.py` ligado a reservas.

- [ ] **Step 2: Quitar `psycopg2-binary` de `requirements.txt`**

Eliminar la línea `psycopg2-binary>=2.9` (ya no hay código de producción que use psycopg2; solo el script de migración de una corrida, que se ejecuta con instalación temporal `pip install psycopg2-binary` en la sesión).

- [ ] **Step 3: Verificación de cero referencias a Supabase en el código**

Run: `grep -ri "supabase" . --include=*.py`
Expected: sin resultados (o solo en el script de migración y comentarios que nombran el origen histórico — el criterio de aceptación #5 es "cero referencias en el código" de producción; el script de migración de una corrida es aceptable pero puede borrarse tras migrar si se prefiere cero absoluto).
Run: `grep -rni "psycopg2\|DATABASE_URL" engine routes main.py`
Expected: sin resultados en código de producción.

- [ ] **Step 4: Correr la suite completa**

Run: `$env:PYTHONPATH='c:\proyectos\thai-thai\thai-thai-ads-agent'; & 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -m pytest tests/ -q`
Expected: PASS (sin regresiones; los tests de keepalive fueron reemplazados).

- [ ] **Step 5: Commit**

```bash
git add main.py requirements.txt
git commit -m "chore(reservas): eliminar Supabase/psycopg2/SQLite de reservas del código"
```

- [ ] **Step 6: DEPLOY ÚNICO del código nuevo (manual, requiere aprobación de Hugo)**

**Precondición dura:** Task 5 Step 5 verificado (conteos cuadran). Este es el ÚNICO deploy de toda la migración. Antes de este punto nada se desplegó.

```bash
gcloud run deploy thai-thai-ads-agent --source . --region=us-central1
```

- [ ] **Step 7: Quitar `DATABASE_URL` del servicio (manual, tras el deploy — `--set-env-vars` PROHIBIDO)**

`DATABASE_URL` es un secreto (`database-url`) montado en el servicio. Quitarlo SOLO con `--remove-secrets`:

```bash
gcloud run services update thai-thai-ads-agent --region=us-central1 \
  --remove-secrets=DATABASE_URL
```

(Opcional, tras confirmar que nada más lo usa: `gcloud secrets delete database-url`.)
Hugo pausa/elimina el proyecto de Supabase por su cuenta. El código ya no toca Supabase.

---

### Task 7: Verificación end-to-end y criterios de aceptación

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Prueba de fuego (criterio #1) — automatizada**

Run: `... -m pytest tests/test_reservations_endpoint_order.py::test_returns_200_even_if_sheets_fails -v`
Expected: PASS — cliente, dueño y WhatsApp llamados; 200; fallo marcado.

- [ ] **Step 2: Prueba de fuego (criterio #1) — manual con Sheets roto (requiere despliegue de staging o corrida local)**

Con una credencial de Sheets inválida a propósito (p. ej. `GOOGLE_SHEETS_SPREADSHEET_ID` a un id inexistente en un entorno local), hacer un `POST /reservations` real. Verificar: el cliente recibe correo, Hugo recibe correo + WhatsApp, respuesta 200, y `[reservation_persist_FAILED]` en logs. Pegar evidencia.

- [ ] **Step 3: Reserva real end-to-end (criterio #2)**

`POST /reservations` con datos reales → verificar fila nueva y correcta en la pestaña `Reservas`, con `fecha_creacion` en hora de Mérida.

- [ ] **Step 4: Idempotencia (criterio #4)**

Repetir el mismo payload dos veces en el mismo segundo (mismo `id`) → verificar que NO hay fila duplicada en `Reservas`.

- [ ] **Step 5: Confirmar criterios #3, #5, #6**

- #3: pegar COUNT(*) Supabase = filas en Sheets (de Task 5).
- #5: `grep -ri supabase . --include=*.py` → cero en producción.
- #6: keepalive ya no existe (`grep -rni "build_keepalive_db\|SELECT 1" engine routes` → cero).

- [ ] **Step 6: Commit + push (criterio #7 — requiere aprobación de Hugo)**

```bash
git push origin <rama>
```

---

## Notas de decisiones (no forman parte de los pasos)

- **Marca de fallos en GCS** (`reservas/persist_failures.json` en `thai-thai-agent-data`): durable entre reinicios/deploys de Cloud Run; imprescindible porque la alerta corre lunes/viernes. El monitor la lee; NO se limpia automáticamente (Hugo la limpia tras capturar a mano, o se añade un endpoint de limpieza en una iteración futura — YAGNI por ahora).
- **`notas`/`origen`** son opcionales en el modelo → retrocompatibles con el frontend actual sin tocarlo.
- **Tests:** aunque el CLAUDE.md limita tests a dinero/Google Ads, los criterios de aceptación del brief exigen evidencia; por eso hay tests de orden de notificación, idempotencia y mapeo (I/O mockeado).
