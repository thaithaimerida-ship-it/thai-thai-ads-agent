from __future__ import annotations

import pytest


THAI_THAI_HOSTS = {"thaithaimerida.com", "www.thaithaimerida.com"}


@pytest.mark.parametrize(
    "url",
    [
        "https://www.thaithaimerida.com",
        "https://thaithaimerida.com",
    ],
)
def test_validate_external_http_url_accepts_allowed_https_hosts(url):
    from engine.url_safety import validate_external_http_url

    assert validate_external_http_url(url, allowed_hosts=THAI_THAI_HOSTS) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.thaithaimerida.com",
        "file:///etc/passwd",
        "ftp://example.com/file.txt",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://[::1]",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "www.thaithaimerida.com",
        "://bad-url",
        "https://evil.example.com",
    ],
)
def test_validate_external_http_url_rejects_unsafe_urls(url):
    from engine.url_safety import UnsafeUrlError, validate_external_http_url

    with pytest.raises(UnsafeUrlError):
        validate_external_http_url(url, allowed_hosts=THAI_THAI_HOSTS)


def test_validate_external_http_url_can_allow_http_explicitly():
    from engine.url_safety import validate_external_http_url

    url = "http://example.com"

    assert validate_external_http_url(url, allowed_hosts={"example.com"}, allow_http=True) == url


def test_landing_auditor_valid_url_reaches_urlopen(monkeypatch):
    import engine.landing_page_auditor as auditor

    called = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"<html><head><title>Thai Thai</title><meta name='viewport'><meta name='description'><script>gtag</script></head><body>AW-123 reserva</body></html>"

    def fake_safe_urlopen(url, *, allowed_hosts, timeout, headers):
        called["url"] = url
        called["allowed_hosts"] = allowed_hosts
        called["timeout"] = timeout
        called["headers"] = headers
        return _Response()

    monkeypatch.setattr(auditor, "safe_urlopen", fake_safe_urlopen)

    result = auditor._audit_live_url("https://www.thaithaimerida.com")

    assert called["url"] == "https://www.thaithaimerida.com"
    assert called["allowed_hosts"] == {"thaithaimerida.com", "www.thaithaimerida.com"}
    assert called["timeout"] == 10
    assert "User-Agent" in called["headers"]
    assert result["mode"] == "live_url_audit"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_landing_auditor_rejects_unsafe_url_before_urlopen(monkeypatch, url):
    import engine.landing_page_auditor as auditor
    from engine.url_safety import UnsafeUrlError

    def fake_safe_urlopen(*args, **kwargs):
        raise UnsafeUrlError("blocked")

    monkeypatch.setattr(auditor, "safe_urlopen", fake_safe_urlopen)

    result = auditor._audit_live_url(url)

    assert result["status"] == "warning"
    assert result["mode"] == "live_url_audit_rejected"


def test_reservations_callmebot_valid_host_reaches_urlopen(monkeypatch):
    import routes.reservations as reservations

    called = {}
    reservation = reservations.ReservationRequest(
        name="Hugo",
        email="hugo@example.com",
        phone="9991234567",
        date="2026-05-29",
        time="19:00",
        guests="2",
    )

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_safe_urlopen(url, *, allowed_hosts, timeout):
        called["url"] = url
        called["allowed_hosts"] = allowed_hosts
        called["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("CALLMEBOT_PHONE", "5219999317457")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "secret")
    monkeypatch.setattr(reservations, "safe_urlopen", fake_safe_urlopen)

    reservations.send_whatsapp_restaurant(reservation)

    assert called["url"].startswith("https://api.callmebot.com/whatsapp.php?")
    assert called["allowed_hosts"] == {"api.callmebot.com"}
    assert called["timeout"] == 10


def test_reservations_rejects_non_allowlisted_host_before_urlopen(monkeypatch):
    import routes.reservations as reservations
    from engine.url_safety import UnsafeUrlError

    def fake_safe_urlopen(*args, **kwargs):
        raise UnsafeUrlError("blocked")

    monkeypatch.setenv("CALLMEBOT_PHONE", "5219999317457")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "secret")
    monkeypatch.setattr(reservations, "CALLMEBOT_BASE_URL", "https://evil.example.com/whatsapp.php")
    monkeypatch.setattr(reservations, "safe_urlopen", fake_safe_urlopen)

    reservation = reservations.ReservationRequest(
        name="Hugo",
        email="hugo@example.com",
        phone="9991234567",
        date="2026-05-29",
        time="19:00",
        guests="2",
    )

    reservations.send_whatsapp_restaurant(reservation)
