import os
from typing import Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - handled at runtime if dependency is missing
    OpenAI = None


_DEFAULT_MODELS = {
    "haiku": "gpt-5-mini",
    "sonnet": "gpt-5",
}


def has_llm_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def get_model_for_role(model_role: str) -> str:
    normalized = (model_role or "").strip().lower()
    if normalized not in _DEFAULT_MODELS:
        raise ValueError(f"Unknown model_role: {model_role}")

    env_name = f"OPENAI_MODEL_{normalized.upper()}"
    return os.getenv(env_name, _DEFAULT_MODELS[normalized])


def _get_client() -> "OpenAI":
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    if OpenAI is None:
        raise RuntimeError("La dependencia 'openai' no está instalada")
    return OpenAI(api_key=api_key)


def _extract_message_text(message_content) -> str:
    if isinstance(message_content, str):
        return message_content

    if isinstance(message_content, list):
        text_parts = []
        for item in message_content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            else:
                text_value = getattr(item, "text", None)
                if text_value:
                    text_parts.append(text_value)
        return "".join(text_parts).strip()

    return str(message_content or "").strip()


def generate_text(
    model_role: str,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1000,
) -> str:
    client = _get_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=get_model_for_role(model_role),
        messages=messages,
        max_completion_tokens=max_tokens,
    )
    message = response.choices[0].message
    return _extract_message_text(message.content)
