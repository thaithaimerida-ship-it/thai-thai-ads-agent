"""Tests de la alerta proactiva de auth de Google Ads (engine/ads_auth_alert).

No toca SMTP real: `_enviar` se mockea. Verifica clasificación de fallos de auth y el
dedupe de 1 aviso/día (para no spamear cuando el token está muerto varios días)."""
import engine.ads_auth_alert as A
from engine import acciones_log


def test_es_fallo_auth_reconoce_mensajes_reales():
    assert A.es_fallo_auth("('invalid_grant: Token has been expired or revoked.')")
    assert A.es_fallo_auth("RuntimeError: No hay credenciales de Google Ads disponibles (env vars ni yaml)")
    assert A.es_fallo_auth("Token has been expired or revoked")
    assert not A.es_fallo_auth("HTTPSConnectionPool: Read timed out")
    assert not A.es_fallo_auth("")


def test_no_alerta_si_no_es_auth(monkeypatch):
    llamado = {"n": 0}
    monkeypatch.setattr(A, "_enviar", lambda *a, **k: llamado.update(n=llamado["n"] + 1) or {"enviado": True})
    r = A.alertar_si_auth_fallo("500 timeout no relacionado con auth")
    assert r == {"alertado": False, "motivo": "no es fallo de auth"}
    assert llamado["n"] == 0  # nunca intentó enviar


def test_dedupe_un_aviso_por_dia(monkeypatch, tmp_path):
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    envios = {"n": 0}
    monkeypatch.setattr(A, "_enviar", lambda *a, **k: envios.update(n=envios["n"] + 1) or {"enviado": True})
    r1 = A.alertar_si_auth_fallo("invalid_grant: revoked")
    assert r1["alertado"] is True and envios["n"] == 1
    r2 = A.alertar_si_auth_fallo("invalid_grant: revoked")  # mismo día
    assert r2 == {"alertado": False, "motivo": "ya avisado hoy"} and envios["n"] == 1  # no reenvía


def test_reintenta_si_envio_previo_fallo(monkeypatch, tmp_path):
    # Si el SMTP falló (resultado != 'ok'), NO se marca enviado → se reintenta el mismo día.
    monkeypatch.setattr(acciones_log, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(A, "_enviar", lambda *a, **k: {"enviado": False, "motivo": "smtp caido"})
    assert A.alertar_si_auth_fallo("invalid_grant")["alertado"] is False
    envios = {"n": 0}
    monkeypatch.setattr(A, "_enviar", lambda *a, **k: envios.update(n=envios["n"] + 1) or {"enviado": True})
    r2 = A.alertar_si_auth_fallo("invalid_grant")  # el previo fue error → NO deduplicado
    assert r2["alertado"] is True and envios["n"] == 1
