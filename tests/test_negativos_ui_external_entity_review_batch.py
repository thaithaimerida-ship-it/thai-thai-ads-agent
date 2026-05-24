import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def _slice_between(start, end):
    return _PAGE.split(start, 1)[1].split(end, 1)[0]


def test_review_pick_exists_and_external_entity_review_does_not_use_negative_pick():
    assert "class='review-pick'" in _PAGE
    assert 'data-review-i=' in _PAGE

    review_row_branch = _slice_between(
        'if (t.semantic_class === "external_entity_review")',
        'var pick = canPick(t)',
    )
    assert "reviewActions(t, i)" in review_row_branch
    assert "class='pick'" not in review_row_branch


def test_separate_selection_functions_exist():
    assert "function selectedForReview()" in _PAGE
    assert "function selectedForNegatives()" in _PAGE


def test_red_negative_button_uses_only_selected_for_negatives():
    add_handler = _slice_between(
        'el("addBtn").onclick = function ()',
        "function submit(sel)",
    )

    assert "selectedForNegatives()" in add_handler
    assert "selectedForReview()" not in add_handler
    assert 'document.querySelectorAll(".review-pick:checked")' not in add_handler


def test_batch_proposals_use_only_selected_for_review():
    batch_fn = _slice_between(
        "function showBatchReviewProposal(kind)",
        "function renderTable()",
    )

    assert "selectedForReview()" in batch_fn
    assert "selectedForNegatives()" not in batch_fn
    assert 'document.querySelectorAll(".pick:checked")' not in batch_fn


def test_batch_buttons_exist_in_external_entity_review_section():
    assert "Generar propuestas de competidores seleccionados" in _PAGE
    assert "Generar propuestas de genéricos útiles seleccionados" in _PAGE

    review_section = _slice_between(
        'sectionHtml("Revisar entidad ajena"',
        'sectionHtml("Ambiguos / pueden traer clientes"',
    )
    assert "reviewBatchHtml()" in review_section


def test_batch_competitors_generates_json_array_with_competitor_proposal():
    batch_fn = _slice_between(
        "function showBatchReviewProposal(kind)",
        "function renderTable()",
    )

    assert "items.map(function (t) { return competitorProposal(t); })" in batch_fn
    assert "JSON.stringify(proposals, null, 2)" in batch_fn
    assert "Esto genera propuestas. No aplica negativos." in _PAGE
    assert "irrelevant_entities.json" in batch_fn


def test_batch_useful_generics_generates_json_array_with_useful_generic_proposal():
    batch_fn = _slice_between(
        "function showBatchReviewProposal(kind)",
        "function renderTable()",
    )

    assert "items.map(function (t) { return usefulGenericProposal(t); })" in batch_fn
    assert "JSON.stringify(proposals, null, 2)" in batch_fn
    assert "useful_generic_patterns.json" in batch_fn


def test_batch_block_has_no_negative_execution_or_persistence():
    batch_fn = _slice_between(
        "function showBatchReviewProposal(kind)",
        "function renderTable()",
    )

    for forbidden in [
        "block_keyword",
        "/execute-optimization",
        "fetch(",
        "localStorage",
        "indexedDB",
        "sqlite",
        "gcs",
        "bucket",
        "writeFile",
        "save",
        "open(",
    ]:
        assert forbidden not in batch_fn


def test_no_new_endpoint_or_server_persistence_added():
    assert '@router.post' not in _PAGE
    assert '@router.get("/external' not in _PAGE

    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "routes", "negativos_ui.py"), encoding="utf-8") as f:
        source = f.read()

    assert "APIRouter" in source
    assert source.count("@router.get(\"/negativos\"") == 1
    assert "GCS" not in source
    assert "sqlite3" not in source
    assert "open(" not in source


def test_negative_and_review_checkboxes_are_distinct_selectors():
    assert 'querySelectorAll(".pick:checked")' in _PAGE
    assert 'querySelectorAll(".review-pick:checked")' in _PAGE
    assert "class='review-pick'" in _PAGE
    assert "<input type='checkbox' class='pick'" in _PAGE
