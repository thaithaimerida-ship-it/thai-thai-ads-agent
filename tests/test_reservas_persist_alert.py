"""Task 4 — el monitor renderea DOS alertas de reservas leyendo las marcas de GCS:
  1) persist_failures: reservas NO guardadas en Sheets (están en el correo del dueño).
  2) unconfirmed: reservas guardadas pero SIN confirmar al cliente → listar nombre/tel/fecha/hora.
Reemplaza al viejo keepalive de la base de datos de reservas.
"""
from engine import monitor_sources
from engine.monitor_email_renderer import render_monitor_email
from tests.test_monitor_email_renderer import _digest


def test_status_reads_both_signals(monkeypatch):
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_persist_failures",
                        lambda: [{"id": "a"}, {"id": "b"}])
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_unconfirmed",
                        lambda: [{"id": "u1", "data": {"name": "Ana", "phone": "+52999",
                                                       "date": "2026-07-20", "time": "20:30"}}])
    r = monitor_sources.build_reservas_persist_status()
    assert r["checked"] is True
    assert r["persist_failures"]["count"] == 2
    assert r["unconfirmed"]["count"] == 1
    assert r["unconfirmed"]["items"][0] == {
        "nombre": "Ana", "telefono": "+52999", "fecha": "2026-07-20", "hora": "20:30"}


def test_no_incidents_no_alert():
    d = _digest()
    d["reservas_persist"] = {"checked": True,
                             "persist_failures": {"count": 0, "ids": []},
                             "unconfirmed": {"count": 0, "items": []}}
    out = render_monitor_email(d)
    assert "no se guardaron en el libro" not in out["html_email"]
    assert "sin confirmación" not in out["html_email"]


def test_persist_failures_alert():
    d = _digest()
    d["reservas_persist"] = {"checked": True,
                             "persist_failures": {"count": 3, "ids": ["a", "b", "c"]},
                             "unconfirmed": {"count": 0, "items": []}}
    out = render_monitor_email(d)
    assert "3 reservas no se guardaron en el libro" in out["html_email"]
    assert "están en tu correo" in out["text_email"]


def test_status_reads_posible_duplicado(monkeypatch):
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_persist_failures", lambda: [])
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_unconfirmed", lambda: [])
    monkeypatch.setattr(monitor_sources.reservas_sheets, "read_posible_duplicados",
                        lambda: [{"id": "d1", "nombre_nuevo": "Luis", "nombres_existentes": ["Ana"],
                                  "data": {"date": "2026-07-20", "time": "20:30"}}])
    r = monitor_sources.build_reservas_persist_status()
    assert r["posible_duplicado"]["count"] == 1
    assert r["posible_duplicado"]["items"][0]["nombre_nuevo"] == "Luis"
    assert r["posible_duplicado"]["items"][0]["nombres_existentes"] == ["Ana"]


def test_posible_duplicado_alert_lists_both_names():
    d = _digest()
    d["reservas_persist"] = {
        "checked": True,
        "persist_failures": {"count": 0, "ids": []},
        "unconfirmed": {"count": 0, "items": []},
        "posible_duplicado": {"count": 1, "items": [
            {"nombre_nuevo": "Luis Pérez", "nombres_existentes": ["Ana López"],
             "fecha": "2026-07-20", "hora": "20:30"}]},
    }
    out = render_monitor_email(d)
    assert "distinto nombre" in out["html_email"]
    assert "Luis Pérez" in out["html_email"] and "Ana López" in out["html_email"]
    assert "Luis Pérez" in out["text_email"] and "Ana López" in out["text_email"]
    assert "2026-07-20" in out["html_email"]


def test_unconfirmed_alert_lists_contact_details():
    d = _digest()
    d["reservas_persist"] = {
        "checked": True,
        "persist_failures": {"count": 0, "ids": []},
        "unconfirmed": {"count": 1, "items": [
            {"nombre": "Ana López", "telefono": "+52 999 111 2222",
             "fecha": "2026-07-20", "hora": "20:30"}]},
    }
    out = render_monitor_email(d)
    assert "sin confirmación" in out["html_email"]
    assert "contáctalos" in (out["html_email"] + out["text_email"]).lower()
    # Datos accionables presentes para poder llamar sin ir al Sheet:
    assert "Ana López" in out["html_email"]
    assert "+52 999 111 2222" in out["html_email"]
    assert "2026-07-20" in out["html_email"] and "20:30" in out["html_email"]
    assert "Ana López" in out["text_email"] and "+52 999 111 2222" in out["text_email"]
