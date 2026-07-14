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


def test_build_reservation_id_is_deterministic_and_content_based():
    d = _data()
    id_a = rs.build_reservation_id(d)
    id_b = rs.build_reservation_id(dict(d))  # mismo contenido → mismo id
    assert id_a == id_b
    assert len(id_a) == 16 and all(c in "0123456789abcdef" for c in id_a)
    # otra hora → otro id
    d2 = dict(d); d2["time"] = "21:00"
    assert rs.build_reservation_id(d2) != id_a
    # NO depende de name/occasion/notas/origen (solo contacto + fecha/hora/personas)
    d3 = dict(d); d3["name"] = "Otro"; d3["occasion"] = "x"; d3["notas"] = "y"
    assert rs.build_reservation_id(d3) == id_a


def test_reservation_row_maps_schema():
    rid = rs.build_reservation_id(_data())
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
        self._ids.append(row[0])  # simula que la fila queda en la columna A


def test_two_identical_posts_5s_apart_do_not_duplicate():
    """Criterio de aceptación #4: doble clic / reenvío del navegador segundos después
    = mismo id determinístico = una sola fila."""
    ws = _FakeWS()
    d = _data()
    t1 = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    t2 = datetime(2026, 7, 14, 21, 5, 14, tzinfo=ZoneInfo("America/Merida"))  # 5s después
    out1 = rs.append_reservation(d, "email_cliente:ok", now=t1, _ws=ws)
    out2 = rs.append_reservation(d, "email_cliente:ok", now=t2, _ws=ws)
    assert out1["id"] == out2["id"]      # id independiente del reloj
    assert out1["ok"] and out2["ok"]
    assert len(ws.appended) == 1          # NO duplica pese a los 5s de diferencia


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
    assert fails[0]["error"] == "Sheets 503"
    rs.clear_persist_failures(_bucket=b)
    assert rs.read_persist_failures(_bucket=b) == []


def test_unconfirmed_roundtrip_and_separate_from_failures():
    b = _FakeBucket()
    rs.record_unconfirmed("u-1", _data(), "email_cliente:error, email_dueño:error, whatsapp:error", _bucket=b)
    rs.record_persist_failure("f-1", _data(), "Sheets 503", _bucket=b)
    unconf = rs.read_unconfirmed(_bucket=b)
    fails = rs.read_persist_failures(_bucket=b)
    assert [u["id"] for u in unconf] == ["u-1"] and "whatsapp:error" in unconf[0]["notif"]
    assert [f["id"] for f in fails] == ["f-1"]  # blobs separados, no se mezclan
    rs.clear_unconfirmed(_bucket=b)
    assert rs.read_unconfirmed(_bucket=b) == [] and rs.read_persist_failures(_bucket=b) == [f for f in fails]
