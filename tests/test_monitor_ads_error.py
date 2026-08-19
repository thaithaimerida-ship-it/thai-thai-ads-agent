"""Tests del reporte degradado (Google Ads caído) end-to-end: payload degradado -> digest ->
banner ARRIBA del correo. Cubre las 2 variantes (fallo de Ads vs excepción inesperada) y que
el caso normal (sin ads_error) no lleva banner."""
from engine.monitor_digest_v3 import build_monitor_digest
from routes.monitor import _degraded_search_terms_payload


def _degraded_context(ads_error):
    return {
        "mode": "monday",
        "links": {"ads": "x", "bloqueos": "x", "resenas": "x", "revision": "x",
                  "token": "t", "bloqueo_base": "x"},
        "gbp": {"data_broken": True},
        "reviews": {"data_broken": True},
        "seo": {"data_broken": True},
        "search_console": {"data_broken": True},
        "reservas": {"data_broken": True, "items": []},
        "reservas_persist": {"checked": False, "persist_failures": {"count": 0, "ids": []},
                             "unconfirmed": {"count": 0, "items": []}},
        "generated_date": "lunes 18 de agosto de 2026",
        "ads_error": ads_error,
    }


def _render(ads_error):
    return build_monitor_digest(_degraded_search_terms_payload("LAST_7_DAYS"),
                                _degraded_context(ads_error))


def test_banner_ads_down_arriba_y_asunto():
    d = _render({"kind": "ads", "exc_type": "RefreshError"})
    assert d["status"] == "success"  # no crashea, correo válido
    assert d["subject_email"].startswith("⚠️") and "Google Ads sin datos" in d["subject_email"]
    html = d["html_email"]
    assert "Google Ads no respondió" in html
    assert html.find("Google Ads no respondió") < len(html) * 0.5  # arriba del correo
    assert "revisar el token" in html.lower()
    assert "GOOGLE ADS NO RESPONDIÓ" in d["text_email"]


def test_banner_inesperado_distinto():
    d = _render({"kind": "unexpected", "exc_type": "TypeError"})
    assert "Error inesperado" in d["subject_email"]
    assert "Error inesperado al generar la sección de Ads: TypeError" in d["html_email"]
    assert "token caído" in d["html_email"]  # aclara que NO es token
    # no debe usar el banner de token muerto
    assert "revisar el token de Google Ads (posible credencial revocada)" not in d["html_email"]


def test_sin_ads_error_no_banner():
    d = _render(None)
    assert not d["subject_email"].startswith("⚠️")
    assert "Google Ads no respondió" not in d["html_email"]
    assert "Error inesperado al generar" not in d["html_email"]
