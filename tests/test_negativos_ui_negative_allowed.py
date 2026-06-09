import os
import re
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def test_negativos_ui_route_serves_read_only_v2_page():
    from main import app

    response = TestClient(app).get("/negativos")

    assert response.status_code == 200
    assert "Bandeja de revisión de términos" in response.text
    assert "Modo seguro" in response.text
    assert "Solo lectura" in response.text
    assert "/negativos/preview-v2" in response.text


def test_negativos_ui_v2_header_summary_and_sections_exist():
    for text in [
        "Bandeja de revisión de términos",
        "Revisa búsquedas antes de bloquearlas en Google Ads",
        "Bloquear es la excepción, no la regla.",
        "Términos revisados",
        "Necesitan tu decisión",
        "Revisar con cuidado",
        "Protegidos",
        "Ya bloqueados",
        "Necesitan tu decisión",
        "Revisar con cuidado",
        "Protegidos · no se tocan",
        "Hoy no hay términos seguros para bloquear.",
    ]:
        assert text in _PAGE


def test_negativos_ui_v2_uses_only_preview_endpoint_for_data():
    fetch_calls = re.findall(r"fetch\(([^)]+)\)", _PAGE)

    assert fetch_calls
    assert fetch_calls == ["url"]
    assert "/negativos/preview-v2?date_range=" in _PAGE
    assert "/search-terms" not in _PAGE
    assert "/execute-optimization" not in _PAGE
    assert "/apply-budget-changes" not in _PAGE


def test_negativos_ui_v2_has_no_write_token_or_post_contract():
    for forbidden in [
        "X-API-Token",
        "localStorage",
        "tt_admin_token",
        "method: \"POST\"",
        "method: 'POST'",
        "block_keyword",
        "Aplicar todos",
        "Confirmar bloqueo",
        "Bloquear termino",
        "Confirmar competidor",
        "Agregar como negativos",
        "Confirmar y enviar",
    ]:
        assert forbidden not in _PAGE


def test_negativos_ui_v2_hides_raw_taxonomy_from_operator():
    for forbidden in [
        "semantic_class",
        "negative_allowed",
        "base_negative_eligible",
        "weak_local_action",
        "red_safe",
        "already_negative",
    ]:
        assert forbidden not in _PAGE


def test_negativos_ui_v2_shows_only_four_operator_columns():
    for column in [
        "<th>Término</th>",
        "<th>Qué pasó</th>",
        "<th>Por qué aparece aquí</th>",
        "<th>Estado</th>",
    ]:
        assert column in _PAGE

    assert "<th>Campana</th>" not in _PAGE
    assert "<th>Clics</th>" not in _PAGE
    assert "<th>Impr.</th>" not in _PAGE
    assert "<th>Conv.</th>" not in _PAGE


def test_execute_optimization_server_gate_remains_unchanged():
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "routes", "analysis.py"), encoding="utf-8") as f:
        analysis = f.read()

    assert "@router.post(\"/execute-optimization\"" in analysis
    assert 'mt == "BROAD"' in analysis
    assert "conversion_quality_weak_local_action" in analysis
