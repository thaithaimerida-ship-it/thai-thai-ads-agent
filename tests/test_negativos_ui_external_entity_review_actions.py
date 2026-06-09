import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def _slice_between(start, end):
    return _PAGE.split(start, 1)[1].split(end, 1)[0]


def test_only_read_only_operator_actions_are_present():
    assert "Ver detalle" in _PAGE
    assert "Actualizar" in _PAGE
    assert "Próxima fase: confirmar decisión" in _PAGE
    assert "disabled" in _PAGE

    for forbidden in [
        "Aplicar",
        "Aplicar todos",
        "Confirmar bloqueo",
        "Confirmar competidor",
        "Copiar propuesta JSON",
        "Generar propuestas",
    ]:
        assert forbidden not in _PAGE


def test_state_labels_are_human_readable():
    state_label_fn = _slice_between(
        "function stateLabel(state)",
        "function stateClass(state)",
    )

    for label in [
        "Listo para revisar bloqueo",
        "Restaurante o negocio externo por confirmar",
        "Revisar con cuidado",
        "Datos insuficientes",
        "Protegido",
        "Ya bloqueado",
        "Monitoreo",
    ]:
        assert label in state_label_fn


def test_weak_local_action_is_explained_without_raw_code():
    assert "Algunas personas pidieron cómo llegar, llamaron o interactuaron en Maps." in _PAGE
    assert "Puede ser un cliente real comparando opciones." in _PAGE
    assert "Restaurante externo con señales locales. Requiere revisión humana." in _PAGE


def test_footer_explains_safe_read_only_policy():
    assert (
        "Solo bloqueamos términos sin pedidos y con suficientes clics. Tu marca, comida tailandesa "
        "y búsquedas útiles están protegidas. Todo se aplicará uno por uno en una fase posterior."
    ) in _PAGE


def test_load_terms_makes_get_request_without_write_options():
    load_fn = _slice_between(
        "function loadTerms()",
        'el("refresh").addEventListener("click", loadTerms);',
    )

    assert "/negativos/preview-v2?date_range=" in load_fn
    assert "fetch(url)" in load_fn
    assert "method" not in load_fn
    assert "headers" not in load_fn
    assert "body" not in load_fn
