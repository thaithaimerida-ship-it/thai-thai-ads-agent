import os
import re
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def test_negativos_ui_route_serves_page():
    from main import app

    response = TestClient(app).get("/negativos")

    assert response.status_code == 200
    assert "Listos para aplicar" in response.text


def test_checkbox_guard_uses_negative_allowed_and_visual_fail_closed_conditions():
    assert "function canPick(t)" in _PAGE
    assert "t.negative_allowed === true" in _PAGE
    assert "!!applyMt(t)" in _PAGE
    assert "t.already_negative === false" in _PAGE
    assert "!!t.campaign_id" in _PAGE


def test_checkbox_is_only_rendered_through_can_pick():
    assert '? "<input type=\'checkbox\' class=\'pick\'' in _PAGE
    assert ": \"\";" in _PAGE

    checkbox_occurrences = re.findall(r"<input type='checkbox' class='pick'", _PAGE)
    assert len(checkbox_occurrences) == 1


def test_sections_required_by_phase_4_exist():
    for title in [
        "Listos para aplicar",
        "Rojo bloqueado",
        "Revisar entidad ajena",
        "Ambiguos / pueden traer clientes",
        "Protegidos",
        "Monitoreo",
        "Ya negativos",
    ]:
        assert title in _PAGE


def test_sectioning_does_not_decide_by_legacy_classification():
    section_for = _PAGE.split("function sectionFor(t)", 1)[1].split("el(\"load\").onclick", 1)[0]

    assert "classification" not in section_for
    assert "base_negative_eligible" not in section_for
    assert "recommended_action" not in section_for
    assert "canPick(t)" in section_for


def test_block_reasons_cover_required_fail_closed_cases():
    for reason in [
        "Ya negativo",
        "Match type no permitido",
        "Falta campaign_id",
        "Estado de negativo no confiable",
        "Conversion no identificada",
        "Tuvo accion de dinero",
        "No cumple elegibilidad base",
    ]:
        assert reason in _PAGE


def test_payload_contract_still_sends_keyword_campaign_and_match_type():
    assert 'keyword: t.query' in _PAGE
    assert 'campaign_id: String(t.campaign_id)' in _PAGE
    assert 'match_type: applyMt(t)' in _PAGE
    assert 'fetch("/execute-optimization"' in _PAGE


def test_execute_optimization_is_not_changed_by_ui_contract():
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "routes", "analysis.py"), encoding="utf-8") as f:
        analysis = f.read()

    assert 'mt = (action.match_type or "").strip().upper()' in analysis
    assert 'mt == "BROAD"' in analysis
    assert 'match_type=mt' in analysis
