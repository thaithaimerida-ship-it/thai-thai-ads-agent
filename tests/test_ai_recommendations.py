"""
Tests para engine.ai_recommendations + schema + prompt + dedup.

NO toca el LLM real — todos los tests que necesitan respuesta del modelo la
mockean via patch en engine.ai_recommendations.llm_client.generate_text.

Aisla SQLite usando tmp_path por test (pytest fixture).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from engine.ai_recommendations import generate_recommendations
from engine.ai_recommendations_prompt import build_user_prompt
from engine.ai_recommendations_schema import (
    NegativeRecommendation,
    QualityAlertRecommendation,
    RecommendationsResponse,
    ScaleRecommendation,
)
from engine.memory import MemorySystem


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def isolated_memory(tmp_path, monkeypatch):
    """Crea un MemorySystem aislado en tmp_path y parchea el generador
    para que use esa instancia cuando haga MemorySystem()."""
    db_path = str(tmp_path / "test_ai_recs.db")

    def _factory():
        return MemorySystem(db_path=db_path)

    monkeypatch.setattr("engine.ai_recommendations.MemorySystem", _factory)
    return _factory()


@pytest.fixture
def llm_env(monkeypatch):
    """Habilita OPENAI_API_KEY para los tests que pasan el gate del cliente."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


@pytest.fixture
def payload_one_campaign():
    return {
        "campaigns": [{"id": "12345", "name": "Local"}],
        "search_terms": [],
    }


def _scale_json(campaign_id: str, name: str, budget: float, reason: str = "diez chars") -> dict:
    return {
        "action_type": "scale",
        "campaign_id": campaign_id,
        "campaign_name": name,
        "reason": reason,
        "urgency": "normal",
        "risk_level": 2,
        "new_budget_mxn": budget,
    }


def _llm_response(*recs) -> str:
    import json as _json
    return _json.dumps({"recommendations": list(recs)})


# ============================================================================
# Schema validation
# ============================================================================


class TestSchemaValidation:
    def test_rejects_invalid_action_type(self):
        bad = '{"recommendations":[{"action_type":"delete","campaign_id":"1","campaign_name":"A","reason":"diez chars","urgency":"normal","risk_level":2}]}'
        with pytest.raises(ValidationError):
            RecommendationsResponse.model_validate_json(bad)

    def test_rejects_budget_above_cap(self):
        with pytest.raises(ValidationError):
            ScaleRecommendation(
                action_type="scale", campaign_id="1", campaign_name="A",
                reason="diez chars", new_budget_mxn=600.0,
            )

    def test_accepts_budget_at_boundary(self):
        r = ScaleRecommendation(
            action_type="scale", campaign_id="1", campaign_name="A",
            reason="diez chars", new_budget_mxn=500.0,
        )
        assert r.new_budget_mxn == 500.0

    def test_rejects_keyword_above_80_chars(self):
        with pytest.raises(ValidationError):
            NegativeRecommendation(
                action_type="negative", campaign_id="1", campaign_name="A",
                reason="diez chars", keyword="x" * 81,
            )

    def test_accepts_keyword_at_boundary(self):
        r = NegativeRecommendation(
            action_type="negative", campaign_id="1", campaign_name="A",
            reason="diez chars", keyword="x" * 80,
        )
        assert len(r.keyword) == 80

    def test_rejects_invalid_alert_type(self):
        with pytest.raises(ValidationError):
            QualityAlertRecommendation(
                action_type="quality_alert", campaign_id="1", campaign_name="A",
                reason="diez chars", alert_type="wat", alert_text="texto suficiente",
            )

    def test_response_caps_at_five_recommendations(self):
        recs = [_scale_json("1", "A", 100.0) for _ in range(6)]
        bad = '{"recommendations":' + str(recs).replace("'", '"') + '}'
        with pytest.raises(ValidationError):
            RecommendationsResponse.model_validate_json(bad)


# ============================================================================
# Prompt sanitization
# ============================================================================


class TestPromptSanitization:
    def test_strips_control_chars(self):
        payload = {
            "campaigns": [{"id": "1", "name": "A"}],
            "search_terms": [{"term": "pad thai\x00\x01\x1f hostile", "cost": 5}],
        }
        up = build_user_prompt(payload)
        assert "\x00" not in up
        assert "\x01" not in up
        assert "pad thai hostile" in up

    def test_truncates_long_search_terms(self):
        payload = {
            "campaigns": [{"id": "1", "name": "A"}],
            "search_terms": [{"term": "x" * 500, "cost": 1}],
        }
        up = build_user_prompt(payload)
        assert "x" * 200 in up
        assert "x" * 201 not in up

    def test_handles_missing_search_terms(self):
        payload = {"campaigns": [{"id": "1", "name": "A"}]}
        up = build_user_prompt(payload)
        assert "INPUT:" in up
        assert '"campaigns"' in up

    def test_non_dict_search_term_is_filtered(self):
        payload = {
            "campaigns": [{"id": "1", "name": "A"}],
            "search_terms": [{"term": "ok"}, "not_a_dict", None, 42],
        }
        up = build_user_prompt(payload)
        # solo el dict válido sobrevive
        assert '"ok"' in up
        assert "not_a_dict" not in up


# ============================================================================
# generate_recommendations — happy path + variantes de output del LLM
# ============================================================================


class TestGenerateHappyPath:
    def test_persists_three_recs(self, isolated_memory, llm_env, payload_one_campaign):
        raw = _llm_response(
            _scale_json("12345", "Local", 100.0, "razon uno con metrica"),
            _scale_json("12345", "Local", 120.0, "razon dos con metrica"),  # mismo (action,campaign) — el segundo debe ser dedup-suprimido
            _scale_json("12345", "Local", 150.0, "razon tres con metrica"),  # idem
        )
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload_one_campaign)

        # solo uno persiste; los otros 2 dedup-suprimidos por (scale, 12345) repetido
        assert result["status"] == "success"
        assert len(result["recommendations"]) == 1
        assert len(result["suppressed_actions"]) == 2
        assert all(s["reason"].startswith("pending") for s in result["suppressed_actions"])

    def test_handles_markdown_fence(self, isolated_memory, llm_env, payload_one_campaign):
        raw = "```json\n" + _llm_response(_scale_json("12345", "Local", 100.0)) + "\n```"
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload_one_campaign)
        assert result["status"] == "success"
        assert len(result["recommendations"]) == 1

    def test_persist_false_returns_summary_without_id_or_token(self, llm_env, payload_one_campaign):
        raw = _llm_response(_scale_json("12345", "Local", 100.0))
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload_one_campaign, persist=False)
        assert result["status"] == "success"
        assert len(result["recommendations"]) == 1
        rec = result["recommendations"][0]
        assert rec["id"] is None
        assert rec["approval_token"] is None
        assert rec["new_budget_mxn"] == 100.0

    def test_three_distinct_categories_all_persist(self, isolated_memory, llm_env):
        payload = {
            "campaigns": [
                {"id": "11", "name": "Local"},
                {"id": "22", "name": "Delivery"},
            ],
            "search_terms": [],
        }
        raw = _llm_response(
            {"action_type": "scale", "campaign_id": "11", "campaign_name": "Local",
             "reason": "diez chars", "urgency": "normal", "risk_level": 2, "new_budget_mxn": 150.0},
            {"action_type": "negative", "campaign_id": "22", "campaign_name": "Delivery",
             "reason": "diez chars", "urgency": "normal", "risk_level": 2, "keyword": "sushi"},
            {"action_type": "quality_alert", "campaign_id": "11", "campaign_name": "Local",
             "reason": "diez chars", "urgency": "urgent", "risk_level": 2,
             "alert_type": "low_ctr", "alert_text": "ctr 0.5% bajo umbral"},
        )
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload)
        assert result["status"] == "success"
        assert len(result["recommendations"]) == 3
        assert {r["action_type"] for r in result["recommendations"]} == {"scale", "negative", "quality_alert"}
        # quality_alert + negative también reciben approval_token (decisión #4 + #2)
        assert all(r["approval_token"] for r in result["recommendations"])


# ============================================================================
# generate_recommendations — error paths
# ============================================================================


class TestGenerateErrorPaths:
    def test_empty_payload_returns_error(self):
        result = generate_recommendations({"campaigns": []})
        assert result["status"] == "error"
        assert result["reason"] == "no_campaigns_in_payload"

    def test_missing_api_key_returns_error(self, monkeypatch, payload_one_campaign):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = generate_recommendations(payload_one_campaign)
        assert result["status"] == "error"
        assert result["reason"] == "no_api_key"

    def test_llm_exception_returns_error(self, isolated_memory, llm_env, payload_one_campaign):
        with patch(
            "engine.ai_recommendations.llm_client.generate_text",
            side_effect=RuntimeError("connection refused"),
        ):
            result = generate_recommendations(payload_one_campaign)
        assert result["status"] == "error"
        assert result["reason"] == "llm_call_failed"
        assert "connection refused" in result["detail"]

    def test_invalid_json_returns_error_with_preview(self, isolated_memory, llm_env, payload_one_campaign):
        raw = "esto no es json en absoluto, solo texto suelto"
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload_one_campaign)
        assert result["status"] == "error"
        # pydantic envuelve el JSON decode error — chequeo flexible
        assert result["reason"] in ("invalid_json", "schema_validation")
        assert "raw_preview" in result
        assert len(result["raw_preview"]) <= 300

    def test_schema_incompatible_returns_error(self, isolated_memory, llm_env, payload_one_campaign):
        # action_type válido pero falta new_budget_mxn requerido
        raw = '{"recommendations":[{"action_type":"scale","campaign_id":"12345","campaign_name":"Local","reason":"diez chars","urgency":"normal","risk_level":2}]}'
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload_one_campaign)
        assert result["status"] == "error"
        assert result["reason"] == "schema_validation"
        assert "raw_preview" in result


# ============================================================================
# generate_recommendations — hallucinations y dedup
# ============================================================================


class TestGenerateHallucinations:
    def test_filters_unknown_campaign_id(self, isolated_memory, llm_env):
        payload = {"campaigns": [{"id": "REAL", "name": "Real"}], "search_terms": []}
        raw = _llm_response(
            _scale_json("REAL", "Real", 100.0),
            _scale_json("GHOST", "Inventada", 80.0),
        )
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload)
        assert result["status"] == "success"
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["campaign_id"] == "REAL"
        assert len(result["hallucinated"]) == 1
        assert result["hallucinated"][0]["campaign_id"] == "GHOST"


class TestGenerateDedupFullFlow:
    def test_second_call_with_same_scale_is_suppressed(
        self, isolated_memory, llm_env, payload_one_campaign,
    ):
        raw = _llm_response(_scale_json("12345", "Local", 100.0))
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            first = generate_recommendations(payload_one_campaign)
            second = generate_recommendations(payload_one_campaign)

        assert len(first["recommendations"]) == 1
        assert len(second["recommendations"]) == 0
        assert len(second["suppressed_actions"]) == 1
        suppressed = second["suppressed_actions"][0]
        assert suppressed["action_type"] == "scale"
        assert suppressed["campaign_id"] == "12345"
        assert suppressed["existing_id"] == first["recommendations"][0]["id"]
        assert suppressed["reason"].startswith("pending")

    def test_two_different_negatives_same_campaign_both_persist(
        self, isolated_memory, llm_env,
    ):
        payload = {"campaigns": [{"id": "X", "name": "X"}], "search_terms": []}
        raw = _llm_response(
            {"action_type": "negative", "campaign_id": "X", "campaign_name": "X",
             "reason": "diez chars", "urgency": "normal", "risk_level": 2, "keyword": "sushi"},
            {"action_type": "negative", "campaign_id": "X", "campaign_name": "X",
             "reason": "diez chars", "urgency": "normal", "risk_level": 2, "keyword": "ramen"},
        )
        with patch("engine.ai_recommendations.llm_client.generate_text", return_value=raw):
            result = generate_recommendations(payload)
        assert len(result["recommendations"]) == 2
        keywords = {r["keyword"] for r in result["recommendations"]}
        assert keywords == {"sushi", "ramen"}
