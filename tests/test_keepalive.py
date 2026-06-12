"""Tests del keepalive de la DB de reservas (monitor) — Fase keepalive.

NO toca el código de reservas; solo el monitor hace SELECT 1 (lunes/viernes) + alerta si falla.
"""
import psycopg2

from engine import monitor_sources


class _FakeCur:
    def execute(self, q):
        self.q = q

    def fetchone(self):
        return (1,)


class _FakeConn:
    def cursor(self):
        return _FakeCur()

    def close(self):
        pass


def test_keepalive_ok(monkeypatch):
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: _FakeConn())
    r = monitor_sources.build_keepalive_db(database_url="postgresql://u:p@h:5432/db")
    assert r["ok"] is True and r["error"] is None and r["checked"] is True


def test_keepalive_falla_y_sanitiza_credenciales(monkeypatch):
    def _boom(*a, **k):
        raise psycopg2.OperationalError(
            "password authentication failed at postgresql://postgres:SUPER_SECRETO@db.x.supabase.co:5432/postgres")
    monkeypatch.setattr(psycopg2, "connect", _boom)
    r = monitor_sources.build_keepalive_db(database_url="postgresql://postgres:SUPER_SECRETO@db.x.supabase.co:5432/postgres")
    assert r["ok"] is False
    assert "SUPER_SECRETO" not in r["error"] and "***" in r["error"]  # credencial nunca filtrada


def test_keepalive_sin_database_url():
    r = monitor_sources.build_keepalive_db(database_url="")
    assert r["ok"] is False and "DATABASE_URL" in r["error"]


def test_alerta_correo_solo_si_keepalive_falla():
    from engine.monitor_email_renderer import render_monitor_email
    from tests.test_monitor_email_renderer import _digest

    ok = _digest()
    ok["keepalive_db"] = {"ok": True, "checked": True, "error": None}
    assert "reservas no respondió" not in render_monitor_email(ok)["html_email"]

    fail = _digest()
    fail["keepalive_db"] = {"ok": False, "checked": True, "error": "OperationalError: connection timed out"}
    out = render_monitor_email(fail)
    assert "reservas no respondió" in out["html_email"]
    assert "no respondió" in out["text_email"]
