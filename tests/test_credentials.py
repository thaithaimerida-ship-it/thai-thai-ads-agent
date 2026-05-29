from __future__ import annotations

import json
import logging


def _reset_credentials_cache(monkeypatch):
    import engine.credentials as credentials

    monkeypatch.setattr(credentials, "_cached_info", None)
    return credentials


def test_invalid_google_credentials_json_log_is_sanitized(monkeypatch, tmp_path, caplog):
    credentials = _reset_credentials_cache(monkeypatch)
    secret_json_value = '{"private_key":"SUPER-SECRET-KEY"'
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", secret_json_value)
    monkeypatch.delenv("GA4_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_PATH", raising=False)

    with caplog.at_level(logging.ERROR, logger="engine.credentials"):
        assert credentials._load_service_account_info() == {}

    logs = caplog.text
    assert "GOOGLE_CREDENTIALS_JSON has invalid JSON" in logs
    assert secret_json_value not in logs
    assert "SUPER-SECRET-KEY" not in logs
    assert "Expecting" not in logs


def test_credentials_file_load_log_does_not_include_full_path(monkeypatch, tmp_path, caplog):
    credentials = _reset_credentials_cache(monkeypatch)
    sensitive_dir = tmp_path / "secret-client-folder"
    sensitive_dir.mkdir()
    credentials_path = sensitive_dir / "prod-service-account.json"
    credentials_path.write_text(json.dumps({"client_email": "svc@example.com"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.setenv("GA4_CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_PATH", raising=False)

    with caplog.at_level(logging.INFO, logger="engine.credentials"):
        assert credentials._load_service_account_info() == {"client_email": "svc@example.com"}

    logs = caplog.text
    assert "Credentials loaded from configured file" in logs
    assert str(credentials_path) not in logs
    assert "secret-client-folder" not in logs
    assert "prod-service-account.json" not in logs


def test_create_credentials_failure_log_uses_exception_type_only(monkeypatch, tmp_path, caplog):
    credentials = _reset_credentials_cache(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", json.dumps({"client_email": "svc@example.com"}))

    def _raise_sensitive_error(*args, **kwargs):
        raise ValueError("private_key=SUPER-SECRET-KEY")

    monkeypatch.setattr(
        credentials.Credentials,
        "from_service_account_info",
        _raise_sensitive_error,
    )

    with caplog.at_level(logging.ERROR, logger="engine.credentials"):
        assert credentials.get_credentials(scopes=["scope"]) is None

    logs = caplog.text
    assert "Service account auth initialization failed" in logs
    assert "ValueError" in logs
    assert "private_key" not in logs
    assert "SUPER-SECRET-KEY" not in logs
