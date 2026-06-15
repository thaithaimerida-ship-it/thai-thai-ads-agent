"""Destinatario único de los correos: MONITOR_RECIPIENT para monitor Y confirmaciones.
El remitente (EMAIL_FROM = administracion@thaithaimerida.com.mx) NO cambia.
"""


def test_config_recipient_unificado_y_remitente_fijo():
    from config import agent_config
    # Confirmaciones (acciones/resenas) usan EMAIL_TO, que ahora es alias del destinatario único.
    assert agent_config.EMAIL_TO == agent_config.MONITOR_RECIPIENT
    # Remitente no cambia.
    assert agent_config.EMAIL_FROM == "administracion@thaithaimerida.com.mx"


def test_monitor_mailer_envia_a_monitor_recipient(monkeypatch):
    from config import agent_config
    from engine import monitor_mailer

    monkeypatch.setattr(agent_config, "GMAIL_APP_PASSWORD", "x")
    monkeypatch.setattr(agent_config, "MONITOR_RECIPIENT", "destino@thaithaimerida.com.mx")
    cap = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, frm, to, msg):
            cap["from"] = frm
            cap["to"] = to

    monkeypatch.setattr(monitor_mailer.smtplib, "SMTP", FakeSMTP)
    res = monitor_mailer.enviar_digest("S", "<html>h", "t")
    assert res["enviado"] is True
    assert res["destinatario"] == "destino@thaithaimerida.com.mx"     # monitor → MONITOR_RECIPIENT
    assert cap["to"] == ["destino@thaithaimerida.com.mx"]
    assert cap["from"] == agent_config.EMAIL_FROM                       # remitente no cambia
