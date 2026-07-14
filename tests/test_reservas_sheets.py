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
    """Simula la pestaña Reservas: header fijo + filas (mutables). Registra appends y update_cell."""
    def __init__(self, seed=None, spreadsheet_id="RID"):
        self.rows = [list(r) for r in (seed or [])]  # todas las filas de datos (mutables)
        self.appended = []                            # solo las agregadas vía append_row
        self.updated = []                             # (fila, col, valor) de cada update_cell
        self.fail_times = 0
        self.spreadsheet_id = spreadsheet_id

    def get_all_values(self):
        return [rs.RESERVAS_HEADER] + self.rows

    def col_values(self, n):
        return [rs.RESERVAS_HEADER[n - 1]] + [r[n - 1] for r in self.rows]

    def append_row(self, row, **kw):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("Sheets API 503")
        r = list(row)
        self.rows.append(r)
        self.appended.append(r)

    def update_cell(self, row, col, value):
        self.updated.append((row, col, value))
        self.rows[row - 2][col - 1] = value  # fila 1 = header


def _seed_row(data, **overrides):
    d = {**data, **overrides}
    rid = rs.build_reservation_id(d)  # id NO depende de name/occasion
    return rs.reservation_row(rid, "2026-01-01 00:00:00", d, "")


# ── Caso 4: id nuevo → append ────────────────────────────────────────────────
def test_new_id_appends():
    ws = _FakeWS()
    out = rs.append_reservation(_data(), "email_cliente:ok", _ws=ws)
    assert out["status"] == "new" and len(ws.appended) == 1


# ── Caso 1: doble-clic idéntico → skip silencioso (criterio #4) ──────────────
def test_two_identical_posts_5s_apart_do_not_duplicate():
    ws = _FakeWS()
    d = _data()
    t1 = datetime(2026, 7, 14, 21, 5, 9, tzinfo=ZoneInfo("America/Merida"))
    t2 = datetime(2026, 7, 14, 21, 5, 14, tzinfo=ZoneInfo("America/Merida"))  # 5s después
    out1 = rs.append_reservation(d, "email_cliente:ok", now=t1, _ws=ws)
    out2 = rs.append_reservation(d, "email_cliente:ok", now=t2, _ws=ws)
    assert out1["id"] == out2["id"]
    assert out2["status"] == "duplicate_ignored"
    assert len(ws.appended) == 1          # NO duplica


def test_trailing_space_and_case_still_dedup_silently():
    """Normalización: 'Ana López' vs '  ANA  LÓPEZ ' = mismo nombre → NO es posible_duplicado."""
    ws = _FakeWS()
    d = _data()
    rs.append_reservation(d, "x", _ws=ws)
    out = rs.append_reservation({**d, "name": "  ANA   LÓPEZ  "}, "x", _ws=ws)
    assert out["status"] == "duplicate_ignored"
    assert len(ws.appended) == 1


# ── Caso 2: mismo id, distinto nombre → append + marca posible_duplicado ─────
def test_same_id_diff_name_appends_and_marks_possible_duplicate(monkeypatch):
    d = _data()
    ws = _FakeWS(seed=[_seed_row(d, name="Pareja de Ana")])  # mismo email/tel/fecha/hora/personas
    marks = []
    monkeypatch.setattr(rs, "record_posible_duplicado", lambda *a, **k: marks.append(a))
    out = rs.append_reservation(d, "email_cliente:ok", _ws=ws)
    assert out["status"] == "possible_duplicate"
    assert len(ws.appended) == 1          # NO se pierde: se agrega igual
    assert len(marks) == 1                # marcada para alerta


# ── Caso 3: mismo id+nombre, distinta ocasión → corrige in-place + bitácora ──
def test_same_id_same_name_diff_occasion_updates_inplace(monkeypatch):
    monkeypatch.setenv("RESERVAS_SHEET_ID", "RID")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "CONTA")
    d = _data()  # occasion "Cumpleaños"
    seed = _seed_row(d, occasion="Aniversario")   # mismo id+nombre, otra ocasión
    ws = _FakeWS(seed=[seed], spreadsheet_id="RID")
    occ_i = rs.RESERVAS_HEADER.index("ocasion")
    marks, dupmarks = [], []
    monkeypatch.setattr(rs, "record_cambio_ocasion", lambda *a, **k: marks.append(a))
    monkeypatch.setattr(rs, "record_posible_duplicado", lambda *a, **k: dupmarks.append(a))
    out = rs.append_reservation(d, "email_cliente:ok", _ws=ws)
    assert out["status"] == "occasion_change"
    assert ws.appended == []                              # NO fila nueva
    assert ws.updated == [(2, occ_i + 1, "Cumpleaños")]   # UNA celda, fila 2, columna ocasion
    assert ws.rows[0][occ_i] == "Cumpleaños"              # corregida in-place (no se pierde)
    for i, col in enumerate(rs.RESERVAS_HEADER):          # ninguna otra columna cambió
        if col != "ocasion":
            assert ws.rows[0][i] == seed[i]
    assert len(marks) == 1                                # bitácora GCS cambio_ocasion
    assert dupmarks == []                                 # SIN alerta de posible_duplicado


# ── CRUCE possible_duplicate × occasion_change: aislar la fila correcta ──────
def test_occasion_change_isolates_correct_row_among_shared_id(monkeypatch):
    """Dos filas con el MISMO id, distinto nombre (cuenta compartida). Un occasion_change
    para UNO de esos nombres debe corregir SOLO su fila, no la del otro que comparte id."""
    monkeypatch.setenv("RESERVAS_SHEET_ID", "RID")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "CONTA")
    base = _data()
    row_hugo = _seed_row(base, name="Hugo", occasion="cita romántica")
    row_maria = _seed_row(base, name="Maria", occasion="cumpleaños")  # mismo id, otro nombre
    # mismo id en ambas (el id no depende de name/occasion):
    assert row_hugo[0] == row_maria[0]
    ws = _FakeWS(seed=[row_hugo, row_maria], spreadsheet_id="RID")
    occ_i = rs.RESERVAS_HEADER.index("ocasion")
    nom_i = rs.RESERVAS_HEADER.index("nombre")
    monkeypatch.setattr(rs, "record_cambio_ocasion", lambda *a, **k: None)

    incoming = {**base, "name": "Hugo", "occasion": "aniversario"}  # id=X, nombre Hugo
    out = rs.append_reservation(incoming, "x", _ws=ws)

    assert out["status"] == "occasion_change"
    assert ws.updated == [(2, occ_i + 1, "aniversario")]  # SOLO fila 2 (Hugo)
    assert ws.rows[0][nom_i] == "Hugo" and ws.rows[0][occ_i] == "aniversario"   # Hugo corregido
    assert ws.rows[1][nom_i] == "Maria" and ws.rows[1][occ_i] == "cumpleaños"   # Maria INTACTA


# ── Guardas del único values.update del módulo ───────────────────────────────
def test_update_occasion_refuses_accounting_book(monkeypatch):
    import pytest
    monkeypatch.setenv("RESERVAS_SHEET_ID", "RID")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "CONTA")
    d = _data()
    ws = _FakeWS(seed=[_seed_row(d, occasion="X")], spreadsheet_id="CONTA")  # apunta a CONTABILIDAD
    with pytest.raises(RuntimeError):
        rs._update_occasion_cell(ws, rs.build_reservation_id(d), d)
    assert ws.updated == []  # NO escribió nada


def test_update_occasion_refuses_when_reservas_id_equals_conta(monkeypatch):
    """Misconfig: RESERVAS_SHEET_ID accidentalmente == libro de contabilidad → LANZA."""
    import pytest
    monkeypatch.setenv("RESERVAS_SHEET_ID", "CONTA")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "CONTA")
    d = _data()
    ws = _FakeWS(seed=[_seed_row(d, occasion="X")], spreadsheet_id="CONTA")
    with pytest.raises(RuntimeError):
        rs._update_occasion_cell(ws, rs.build_reservation_id(d), d)
    assert ws.updated == []


def test_update_occasion_refuses_ambiguous_match(monkeypatch):
    """0 o >1 filas con id+nombre → NO escribe 'la fila que creo'."""
    import pytest
    monkeypatch.setenv("RESERVAS_SHEET_ID", "RID")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "CONTA")
    d = _data()
    ws = _FakeWS(seed=[_seed_row(d), _seed_row(d)], spreadsheet_id="RID")  # 2 filas mismo id+nombre
    with pytest.raises(RuntimeError):
        rs._update_occasion_cell(ws, rs.build_reservation_id(d), d)
    assert ws.updated == []


def test_update_cell_is_the_only_range_write_in_module():
    """Grep del código: update_cell aparece UNA sola vez y solo en _update_occasion_cell;
    ninguna otra escritura por rango (batch_update / values().update) en el módulo."""
    import inspect
    from engine import reservas_sheets as m
    src = inspect.getsource(m)
    assert src.count("update_cell(") == 1
    fn_src = inspect.getsource(m._update_occasion_cell)
    assert "update_cell(" in fn_src
    assert src.replace(fn_src, "").count("update_cell(") == 0  # ninguna otra función lo usa
    assert "batch_update(" not in src
    assert "values().update" not in src


def test_append_retries_then_succeeds():
    ws = _FakeWS(); ws.fail_times = 2
    sleeps = []
    out = rs.append_reservation(_data(), "email_cliente:ok", _ws=ws, _sleep=sleeps.append)
    assert out["ok"] is True and out["status"] == "new"
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
