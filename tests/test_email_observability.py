import json
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from engine.email_observability import get_last_email_preview, save_last_email_preview
from engine.email_sender import _build_daily_subject_from_contract, _derive_report_contract, send_daily_summary_email
from engine.report_contract import build_report_contract_v1
from main import app


class _DummySMTP:
    def __init__(self, *_args, **_kwargs):
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        return None

    def starttls(self):
        return None

    def login(self, *_args, **_kwargs):
        return None

    def sendmail(self, *_args, **_kwargs):
        return None


class _FailingSMTP(_DummySMTP):
    def sendmail(self, *_args, **_kwargs):
        raise RuntimeError("smtp boom")


def _run_payload():
    return {
        "run_id": "audit_test_001",
        "timestamp_merida": "2026-04-16 23:55",
        "result_class": "con_cambios",
        "is_real_audit": True,
        "campaigns_reviewed": 1,
        "audit_result": {"score": 82, "grade": "B", "category_scores": {}, "quick_wins": [], "checks_by_category": {}},
        "budget_optimizer": {"decisions": [], "redistribution": {}, "redistribution_analysis": {}, "executed": []},
        "ventas_ayer": {},
        "ads_24h": {},
        "monthly_budget_status": {},
        "keyword_proposals": [],
        "creative_actions": [],
        "ai_keyword_decisions": [],
        "builder_executed": [],
        "paused_campaigns": [],
        "executed_budget": [],
    }


def test_save_and_get_last_email_preview_roundtrip(tmp_path, monkeypatch):
    preview_path = tmp_path / "last_email_preview.json"
    monkeypatch.setenv("EMAIL_PREVIEW_PATH", str(preview_path))

    saved = save_last_email_preview(
        session_id="audit_test_001",
        subject="[Thai Thai Agente] Actividad diaria — Sin cambios · 2026-04-16 23:55",
        result_class="con_cambios",
        is_real_audit=True,
        html_body="<html><body><h1>Hola</h1><p>Contenido</p></body></html>",
        report_contract={"meta": {"result_class": "con_cambios"}},
    )

    loaded = get_last_email_preview()

    assert saved["session_id"] == "audit_test_001"
    assert saved["send_status"] == "sent"
    assert saved["subject"].startswith("[Thai Thai Agente]")
    assert "Hola" in saved["text_preview"]
    assert saved["report_contract"]["meta"]["result_class"] == "con_cambios"
    assert loaded == saved
    assert preview_path.exists()


def test_send_daily_summary_email_persists_preview_only_after_success(tmp_path, monkeypatch):
    preview_path = tmp_path / "last_email_preview.json"
    monkeypatch.setenv("EMAIL_PREVIEW_PATH", str(preview_path))

    import config.agent_config as cfg
    monkeypatch.setattr(cfg, "EMAIL_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(cfg, "EMAIL_SMTP_PORT", 587)
    monkeypatch.setattr(cfg, "EMAIL_FROM", "administracion@thaithaimerida.com.mx")
    monkeypatch.setattr(cfg, "EMAIL_FROM_NAME", "Thai Thai Ads Agent")
    monkeypatch.setattr(cfg, "EMAIL_TO", "administracion@thaithaimerida.com.mx")
    monkeypatch.setattr(cfg, "GMAIL_APP_PASSWORD", "fake-app-password")

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", _DummySMTP)

    ok = send_daily_summary_email(_run_payload(), "audit_test_001")

    assert ok is True
    loaded = get_last_email_preview()
    assert loaded["session_id"] == "audit_test_001"
    assert loaded["send_status"] == "sent"
    assert "html_body" in loaded
    assert "report_contract" in loaded
    assert loaded["subject"] == _build_daily_subject_from_contract(build_report_contract_v1(_run_payload()))
    assert "summary" in loaded["report_contract"]
    assert "daily_reviews" in loaded["report_contract"]
    assert "Resumen Ejecutivo" in loaded["html_body"]
    assert "Contexto de Cuenta" in loaded["html_body"]
    assert "Revisiones del Día" in loaded["html_body"]


def test_send_daily_summary_email_does_not_persist_preview_on_failure(tmp_path, monkeypatch):
    preview_path = tmp_path / "last_email_preview.json"
    monkeypatch.setenv("EMAIL_PREVIEW_PATH", str(preview_path))

    import config.agent_config as cfg
    monkeypatch.setattr(cfg, "EMAIL_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(cfg, "EMAIL_SMTP_PORT", 587)
    monkeypatch.setattr(cfg, "EMAIL_FROM", "administracion@thaithaimerida.com.mx")
    monkeypatch.setattr(cfg, "EMAIL_FROM_NAME", "Thai Thai Ads Agent")
    monkeypatch.setattr(cfg, "EMAIL_TO", "administracion@thaithaimerida.com.mx")
    monkeypatch.setattr(cfg, "GMAIL_APP_PASSWORD", "fake-app-password")

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", _FailingSMTP)

    ok = send_daily_summary_email(_run_payload(), "audit_test_002")

    assert ok is False
    assert not preview_path.exists()
    assert get_last_email_preview() is None


def test_last_email_preview_endpoint_returns_saved_preview(tmp_path, monkeypatch):
    preview_path = tmp_path / "last_email_preview.json"
    monkeypatch.setenv("EMAIL_PREVIEW_PATH", str(preview_path))
    save_last_email_preview(
        session_id="audit_test_003",
        subject="[Thai Thai Agente] Actividad diaria — Con cambios · 2026-04-16 23:59",
        result_class="con_cambios",
        is_real_audit=True,
        html_body="<html><body><p>Preview payload</p></body></html>",
        report_contract={"meta": {"result_class": "con_cambios"}},
    )

    client = TestClient(app)
    response = client.get("/last-email-preview")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["preview"]["session_id"] == "audit_test_003"
    assert data["preview"]["send_status"] == "sent"
    assert "Preview payload" in data["preview"]["text_preview"]
    assert data["preview"]["report_contract"]["meta"]["result_class"] == "con_cambios"
