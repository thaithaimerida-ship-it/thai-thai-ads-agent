import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def _slice_between(start, end):
    return _PAGE.split(start, 1)[1].split(end, 1)[0]


def test_decision_section_contains_ready_and_external_review_states_only():
    decision_section = _slice_between(
        'var decisionItems = items.filter(function (item) {',
        'var cautionItems = items.filter(function (item) {',
    )

    assert 'item.state === "listo_para_bloquear"' in decision_section
    assert 'item.state === "competidor_por_confirmar"' in decision_section
    assert 'item.state === "revisar_con_cuidado"' not in decision_section
    assert 'item.state === "protegido"' not in decision_section


def test_caution_section_contains_mixed_signal_states():
    caution_section = _slice_between(
        'var cautionItems = items.filter(function (item) {',
        'var protectedItems = items.filter(function (item) {',
    )

    assert 'item.state === "revisar_con_cuidado"' in caution_section
    assert 'item.state === "datos_insuficientes"' in caution_section


def test_protected_section_contains_non_actionable_states():
    protected_section = _slice_between(
        'var protectedItems = items.filter(function (item) {',
        "renderSection(",
    )

    assert 'item.state === "protegido"' in protected_section
    assert 'item.state === "bloqueado"' in protected_section
    assert 'item.state === "monitoreo"' in protected_section


def test_external_entity_review_language_is_human_and_not_accusatory():
    assert "Restaurante o negocio externo por confirmar" in _PAGE
    assert "Parece otro restaurante o negocio en Mérida. Hugo debe decidir si conviene bloquearlo." in _PAGE
    assert "competidor directo" not in _PAGE
    assert "basura" not in _PAGE


def test_read_only_detail_does_not_persist_or_fetch():
    detail_fn = _slice_between(
        "function openDetail(item)",
        "function closeDetail()",
    )

    assert "Ver detalle" in _PAGE
    assert "fetch(" not in detail_fn
    assert "POST" not in detail_fn
    assert "localStorage" not in detail_fn
    assert "indexedDB" not in detail_fn
    assert "writeFile" not in detail_fn
    assert "block_keyword" not in detail_fn
