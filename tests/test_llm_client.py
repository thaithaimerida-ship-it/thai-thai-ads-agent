import pytest
from unittest.mock import MagicMock, patch


def test_model_aliases_default_to_required_openai_models(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL_HAIKU", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_SONNET", raising=False)

    from engine.llm_client import get_model_for_role

    assert get_model_for_role("haiku") == "gpt-5-mini"
    assert get_model_for_role("sonnet") == "gpt-5"


def test_model_aliases_allow_explicit_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_HAIKU", "gpt-5-mini-custom")
    monkeypatch.setenv("OPENAI_MODEL_SONNET", "gpt-5-custom")

    from engine.llm_client import get_model_for_role

    assert get_model_for_role("haiku") == "gpt-5-mini-custom"
    assert get_model_for_role("sonnet") == "gpt-5-custom"


def test_generate_text_uses_openai_client_and_returns_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    mock_client.chat.completions.create.return_value = mock_response

    with patch("engine.llm_client.OpenAI", return_value=mock_client):
        from engine.llm_client import generate_text

        result = generate_text(
            model_role="haiku",
            user_prompt="Devuelve JSON",
            system_prompt="Sistema",
            max_tokens=123,
        )

    assert result == '{"ok": true}'
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5-mini"
    assert kwargs["max_completion_tokens"] == 123
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"


def test_generate_text_requires_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from engine.llm_client import generate_text

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        generate_text(model_role="haiku", user_prompt="hola")
