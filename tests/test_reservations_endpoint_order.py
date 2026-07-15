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


def test_all_notifications_fail_but_sheets_ok_returns_200_and_marks_unconfirmed(monkeypatch):
    """Caso realista: Gmail rate-limited + CallMeBot caído, Sheets vivo. La reserva EXISTE
    → 200 (NO 502), se marca como 'sin confirmación' y se le da el WhatsApp al cliente."""
    marks = {"unconfirmed": 0, "persist_fail": 0}
    monkeypatch.setattr(R, "send_email_to_customer", lambda r: (_ for _ in ()).throw(RuntimeError("gmail rate-limited")))
    monkeypatch.setattr(R, "send_email_to_owner", lambda r: (_ for _ in ()).throw(RuntimeError("gmail rate-limited")))
    monkeypatch.setattr(R, "send_whatsapp_restaurant", lambda r: (_ for _ in ()).throw(RuntimeError("callmebot down")))
    monkeypatch.setattr(R.reservas_sheets, "append_reservation",
                        lambda *a, **k: {"ok": True, "id": "abc123", "row": [], "error": None})
    monkeypatch.setattr(R.reservas_sheets, "record_unconfirmed", lambda *a, **k: marks.__setitem__("unconfirmed", 1))
    monkeypatch.setattr(R.reservas_sheets, "record_persist_failure", lambda *a, **k: marks.__setitem__("persist_fail", 1))

    out = asyncio.run(R.create_reservation(_payload()))
    assert out["status"] == "success"                       # 200, NO 502
    assert out["persisted"] is True and out["notified"] is False
    assert "WhatsApp" in out["message"]                     # se le da el WhatsApp al cliente
    assert marks == {"unconfirmed": 1, "persist_fail": 0}   # marcada 'sin confirmar', no persist-fail


def test_502_only_when_no_trace_anywhere(monkeypatch):
    """502 SOLO si no hay rastro: ni en Sheets ni ninguna notificación."""
    marks = {"persist_fail": 0}
    monkeypatch.setattr(R, "send_email_to_customer", lambda r: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(R, "send_email_to_owner", lambda r: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(R, "send_whatsapp_restaurant", lambda r: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(R.reservas_sheets, "append_reservation",
                        lambda *a, **k: {"ok": False, "id": "abc", "row": [], "error": "cred inválida"})
    monkeypatch.setattr(R.reservas_sheets, "record_persist_failure", lambda *a, **k: marks.__setitem__("persist_fail", 1))

    import fastapi
    try:
        asyncio.run(R.create_reservation(_payload()))
        assert False, "debió lanzar 502"
    except fastapi.HTTPException as e:
        assert e.status_code == 502
    assert marks["persist_fail"] == 1  # marcó el fallo con el payload (única traza durable)
