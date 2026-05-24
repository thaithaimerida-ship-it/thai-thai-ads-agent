import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.negativos_ui import _PAGE


def _slice_between(start, end):
    return _PAGE.split(start, 1)[1].split(end, 1)[0]


def test_external_entity_review_shows_human_review_actions():
    assert "Confirmar competidor" in _PAGE
    assert "Marcar como genérico útil" in _PAGE
    assert "Mantener en revisión" in _PAGE
    assert "Esto genera una propuesta. No aplica negativos." in _PAGE
    assert "Copiar propuesta JSON" in _PAGE


def test_external_entity_review_does_not_render_negative_checkbox():
    review_row_branch = _slice_between(
        'if (t.semantic_class === "external_entity_review")',
        'var pick = canPick(t)',
    )

    assert "reviewActions(t, i)" in review_row_branch
    assert "type='checkbox'" not in review_row_branch
    assert "class='pick'" not in review_row_branch


def test_confirm_competitor_generates_irrelevant_entity_proposal_with_auto_apply_false():
    proposal_fn = _slice_between(
        "function competitorProposal(t)",
        "function usefulGenericProposal(t)",
    )
    review_meta_fn = _slice_between(
        "function reviewMeta(t, decision)",
        "function competitorProposal(t)",
    )

    for field in [
        "canonical",
        "aliases",
        "category",
        "confidence",
        "suggested_match_type",
        "auto_apply: false",
        "review",
        'reviewMeta(t, "confirmar_competidor")',
    ]:
        assert field in proposal_fn

    for field in [
        "source_query",
        "decision",
        "confirmed_by",
        "confirmed_at",
        "notes",
    ]:
        assert field in review_meta_fn


def test_confirm_competitor_does_not_generate_block_keyword_payload():
    proposal_fn = _slice_between(
        "function competitorProposal(t)",
        "function usefulGenericProposal(t)",
    )

    assert "block_keyword" not in proposal_fn
    assert "execute-optimization" not in proposal_fn
    assert "fetch(" not in proposal_fn


def test_mark_as_useful_generic_generates_separate_pattern_proposal():
    proposal_fn = _slice_between(
        "function usefulGenericProposal(t)",
        "function showReviewProposal(kind, index)",
    )

    assert "useful_generic_patterns.json" in _PAGE
    assert "irrelevant_entities.json" not in proposal_fn
    assert "pattern" in proposal_fn
    assert "normalized_pattern" in proposal_fn
    assert 'classification_target: "ambiguous_useful"' in proposal_fn
    assert 'reviewMeta(t, "marcar_generico_util")' in proposal_fn


def test_keep_in_review_does_not_create_payload_or_mutation():
    handler = _slice_between(
        'if (kind === "keep")',
        "var proposal",
    )

    assert "Mantener en revisión" in handler
    assert "fetch(" not in handler
    assert "block_keyword" not in handler
    assert "execute-optimization" not in handler


def test_review_actions_do_not_call_execute_optimization_or_google_ads():
    review_helpers = _slice_between(
        "function reviewActions(t, i)",
        "function selected()",
    )

    assert 'fetch("/execute-optimization"' not in review_helpers
    assert "block_keyword" not in review_helpers
    assert "add_negative_keyword" not in review_helpers


def test_negative_allowed_checkboxes_continue_to_use_existing_payload():
    checkbox_occurrences = re.findall(r"<input type='checkbox' class='pick'", _PAGE)
    assert len(checkbox_occurrences) == 1
    assert "function canPick(t)" in _PAGE
    assert "t.negative_allowed === true" in _PAGE
    assert 'keyword: t.query' in _PAGE
    assert 'campaign_id: String(t.campaign_id)' in _PAGE
    assert 'match_type: applyMt(t)' in _PAGE
