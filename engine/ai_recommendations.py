"""
Generador de recomendaciones AI para Thai Thai Ads.

Flujo:
1. Construye prompt user con payload sanitizado (engine.ai_recommendations_prompt).
2. Llama al LLM via engine.llm_client.generate_text(model_role="sonnet", ...).
3. Parsea response con engine.ai_recommendations_schema.RecommendationsResponse.
4. Filtra hallucinations (campaign_id que NO está en payload.campaigns).
5. Aplica dedup vía engine.memory.MemorySystem.check_decision_dedup → arma suppressed_actions.
6. Persiste sobrevivientes via engine.memory.MemorySystem.record_autonomous_decision con
   decision="proposed" + approval_token nuevo (compatible con /approve-legacy).
7. Devuelve dict estructurado para el caller (endpoint en routes/presupuestos).

NO fetcha datos de Google Ads ni GA4. El caller arma el payload. Esto permite:
- Mockeo trivial en tests.
- Reuso desde múltiples endpoints (mission-control, presupuestos, ad-hoc).
- Iterar el prompt con .claude/skills/ai-prompt-iterate usando fixture local.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any

from pydantic import ValidationError

from engine import llm_client
from engine.ai_recommendations_prompt import SYSTEM_PROMPT, build_user_prompt
from engine.ai_recommendations_schema import (
    NegativeRecommendation,
    QualityAlertRecommendation,
    RecommendationsResponse,
)
from engine.memory import MemorySystem

logger = logging.getLogger(__name__)

# Strip markdown fences si el LLM los incluye a pesar del prompt.
_MD_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

_MAX_TOKENS = 2000
_RAW_PREVIEW_CHARS = 300


def generate_recommendations(
    payload: dict[str, Any],
    *,
    persist: bool = True,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Genera recomendaciones AI y opcionalmente las persiste en autonomous_decisions.

    Args:
        payload: dict con campaigns/search_terms/ga4_funnel/landing_health.
                 La lista `campaigns` DEBE contener {"id": str, "name": str, ...}
                 — usada para validar campaign_id contra hallucinations.
        persist: si False, NO escribe a SQLite. Útil para dry-run e iteración.
        session_id: opcional, se guarda en cada fila para trazabilidad.

    Returns:
        {
          "status": "success" | "error",
          "recommendations": [{"id": int, "action_type": str, "campaign_id": str, ...}],
          "suppressed_actions": [{"action_type": str, "campaign_id": str, "key": str|None, "reason": str, "existing_id": int}],
          "hallucinated": [{"action_type": str, "campaign_id": str, "reason": "campaign_id_not_in_payload"}],
          "llm_raw_chars": int,
          ...error fields when status=="error"...
        }
    """
    valid_campaign_ids = _valid_campaign_ids(payload)
    if not valid_campaign_ids:
        return _error("no_campaigns_in_payload", "payload.campaigns vacío o sin ids")

    if not llm_client.has_llm_api_key():
        return _error("no_api_key", "OPENAI_API_KEY no configurada")

    user_prompt = build_user_prompt(payload)

    try:
        raw = llm_client.generate_text(
            model_role="sonnet",
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:
        logger.exception("ai_recommendations: LLM call failed")
        return _error("llm_call_failed", str(exc))

    cleaned = _MD_FENCE_RE.sub("", raw or "").strip()
    try:
        parsed = RecommendationsResponse.model_validate_json(cleaned)
    except ValidationError as exc:
        logger.warning("ai_recommendations: schema validation failed: %s", exc.errors()[:3])
        return _error(
            "schema_validation",
            str(exc.errors()[:3]),
            extra={
                "llm_raw_chars": len(raw or ""),
                "raw_preview": cleaned[:_RAW_PREVIEW_CHARS],
            },
        )
    except json.JSONDecodeError as exc:
        logger.warning("ai_recommendations: invalid JSON from LLM: %s", exc)
        return _error(
            "invalid_json",
            str(exc),
            extra={
                "llm_raw_chars": len(raw or ""),
                "raw_preview": cleaned[:_RAW_PREVIEW_CHARS],
            },
        )

    persisted: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    hallucinated: list[dict[str, Any]] = []
    store = MemorySystem() if persist else None

    for rec in parsed.recommendations:
        if rec.campaign_id not in valid_campaign_ids:
            hallucinated.append({
                "action_type": rec.action_type,
                "campaign_id": rec.campaign_id,
                "reason": "campaign_id_not_in_payload",
            })
            logger.warning(
                "ai_recommendations: LLM hallucinated campaign_id=%s (action=%s)",
                rec.campaign_id, rec.action_type,
            )
            continue

        dedup_key = _dedup_key_for(rec)
        if persist:
            should_insert, existing_id, dedup_reason = store.check_decision_dedup(
                rec.action_type, rec.campaign_id, key=dedup_key,
            )
        else:
            should_insert, existing_id, dedup_reason = True, None, "persist_disabled"

        if not should_insert:
            suppressed.append({
                "action_type": rec.action_type,
                "campaign_id": rec.campaign_id,
                "key": dedup_key,
                "reason": dedup_reason,
                "existing_id": existing_id,
            })
            logger.info(
                "ai_recommendations: dedup SUPPRESS %s/%s key=%s reason=%s existing_id=%s",
                rec.action_type, rec.campaign_id, dedup_key, dedup_reason, existing_id,
            )
            continue

        if not persist:
            persisted.append(_rec_summary(rec, decision_id=None, approval_token=None))
            continue

        approval_token = secrets.token_urlsafe(16)
        decision_id = store.record_autonomous_decision(
            action_type=rec.action_type,
            risk_level=rec.risk_level,
            urgency=rec.urgency,
            decision="proposed",
            campaign_id=rec.campaign_id,
            campaign_name=rec.campaign_name,
            keyword=rec.keyword if isinstance(rec, NegativeRecommendation) else None,
            evidence=_evidence_payload(rec),
            session_id=session_id,
            approval_token=approval_token,
        )
        persisted.append(_rec_summary(rec, decision_id=decision_id, approval_token=approval_token))
        logger.info(
            "ai_recommendations: persisted %s/%s id=%d urgency=%s",
            rec.action_type, rec.campaign_id, decision_id, rec.urgency,
        )

    return {
        "status": "success",
        "recommendations": persisted,
        "suppressed_actions": suppressed,
        "hallucinated": hallucinated,
        "llm_raw_chars": len(raw or ""),
    }


# ---------------------------- helpers internos -------------------------------


def _valid_campaign_ids(payload: dict[str, Any]) -> set[str]:
    campaigns = payload.get("campaigns") or []
    return {str(c["id"]) for c in campaigns if isinstance(c, dict) and c.get("id") is not None}


def _dedup_key_for(rec: Any) -> str | None:
    if isinstance(rec, NegativeRecommendation):
        return rec.keyword
    if isinstance(rec, QualityAlertRecommendation):
        return rec.alert_type
    return None


def _evidence_payload(rec: Any) -> dict[str, Any]:
    """Serializa los campos específicos por action_type para guardar en evidence_json."""
    base = {
        "reason": rec.reason,
        "urgency": rec.urgency,
        "risk_level": rec.risk_level,
    }
    extra = rec.model_dump(exclude={
        "action_type", "campaign_id", "campaign_name",
        "reason", "urgency", "risk_level",
    })
    base.update(extra)
    return base


def _rec_summary(rec: Any, *, decision_id: int | None, approval_token: str | None) -> dict[str, Any]:
    summary = {
        "id": decision_id,
        "action_type": rec.action_type,
        "campaign_id": rec.campaign_id,
        "campaign_name": rec.campaign_name,
        "urgency": rec.urgency,
        "approval_token": approval_token,
    }
    if isinstance(rec, NegativeRecommendation):
        summary["keyword"] = rec.keyword
    elif isinstance(rec, QualityAlertRecommendation):
        summary["alert_type"] = rec.alert_type
    elif hasattr(rec, "new_budget_mxn"):
        summary["new_budget_mxn"] = rec.new_budget_mxn
    return summary


def _error(reason: str, detail: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "status": "error",
        "reason": reason,
        "detail": detail,
        "recommendations": [],
        "suppressed_actions": [],
        "hallucinated": [],
    }
    if extra:
        out.update(extra)
    return out
