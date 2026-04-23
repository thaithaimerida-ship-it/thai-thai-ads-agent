from __future__ import annotations

from typing import Any


# ============================================================================
# Schema and taxonomies
# ============================================================================

DOMAIN_STATUS_VALUES = {
    "executed",
    "proposed",
    "analyzed",
    "blocked",
    "not_applicable",
    "not_observable",
}

PRIMARY_BLOCK_ORDER = ("executed", "blocked", "proposed", "analyzed")
PRIMARY_BLOCK_PRIORITY = {name: index for index, name in enumerate(PRIMARY_BLOCK_ORDER)}

CORE_DOMAINS = ("keywords", "ad_groups", "budget", "redistribution")

NO_ACTION_REASON_VALUES = {
    "no_actionable_opportunities",
    "no_valid_adjustment_case",
    "no_eligible_entities",
    "insufficient_signal",
    "not_applicable",
    "already_in_good_state",
    "not_observable_from_run",
}

BLOCK_REASON_VALUES = {
    "risk_guard",
    "insufficient_signal",
    "not_eligible",
    "policy_guard",
    "execution_guard",
    "not_observable_from_run",
}

CATEGORY_LABELS = (
    ("CT", "Conversion Tracking"),
    ("Wasted", "Wasted Spend"),
    ("Structure", "Account Structure"),
    ("KW", "Keywords & QS"),
    ("Ads", "Ads & Assets"),
    ("Settings", "Settings & Targeting"),
)


# ============================================================================
# Normalization from raw run
# ============================================================================

def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_run(run: dict[str, Any]) -> dict[str, Any]:
    budget_optimizer = _as_dict(run.get("budget_optimizer"))
    audit_result = _as_dict(run.get("audit_result"))

    return {
        "run": run,
        "audit_result": audit_result,
        "budget_optimizer": budget_optimizer,
        "keyword_proposals": _as_list(run.get("keyword_proposals")),
        "budget_proposals": _as_list(run.get("budget_proposals")),
        "ba2_proposals": _as_list(run.get("ba2_proposals")),
        "ai_keyword_decisions": _as_list(run.get("ai_keyword_decisions")),
        "builder_executed": _as_list(run.get("builder_executed")),
        "creative_actions": _as_list(run.get("creative_actions")),
        "blocked": _as_list(run.get("blocked")),
        "blocked_budget_auto": _as_list(run.get("blocked_budget_auto")),
        "blocked_budget_scale_auto": _as_list(run.get("blocked_budget_scale_auto")),
        "executed_budget": _as_list(run.get("executed_budget")),
        "ads_24h": _as_dict(run.get("ads_24h")),
        "monthly_budget_status": _as_dict(run.get("monthly_budget_status")),
        "ventas_ayer": _as_dict(run.get("ventas_ayer")),
    }


# ============================================================================
# Minimal helpers
# ============================================================================

def _fact_id(*parts: Any) -> str:
    normalized = []
    for part in parts:
        text = str(part or "").strip().lower()
        normalized.append(text.replace("|", "/"))
    return "|".join(normalized)


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _mxn_int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except Exception:
        return None


def _campaign_snapshot_rows(ads_24h: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _as_list(ads_24h.get("por_campana")):
        spend = row.get("spend_mxn")
        conversions = row.get("conversions")
        cpa_ads = None
        try:
            spend_value = float(spend or 0)
            conversions_value = float(conversions or 0)
            if conversions_value > 0:
                cpa_ads = round(spend_value / conversions_value, 2)
        except Exception:
            cpa_ads = None

        rows.append(
            {
                "campaign_name": row.get("name") or "",
                "campaign_type": row.get("tipo") or "",
                "spend_mxn": spend,
                "clicks": row.get("clicks"),
                "conversions_ads": conversions,
                "cpa_ads": cpa_ads,
                "status": row.get("status") or "Activa",
            }
        )
    return rows


# ============================================================================
# Editorial classification
# ============================================================================

def _build_executed_facts(nr: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    for item in nr["executed_budget"]:
        result = _as_dict(item.get("result"))
        status = result.get("status") or ("executed" if item.get("action") else "")
        if status not in ("executed", "paused"):
            continue
        campaign_name = item.get("campaign_name") or item.get("campaign") or ""
        action = item.get("action") or ""
        facts.append(
            {
                "fact_id": _fact_id("budget", campaign_name, action, item.get("new_daily_budget_mxn")),
                "primary_block": "executed",
                "domain": "budget",
                "kind": "budget_action_executed",
                "subject": campaign_name,
                "target": None,
                "action_label": action or "budget_change",
                "evidence": item.get("reason") or "Executed budget action visible in raw run.",
            }
        )

    for item in nr["ai_keyword_decisions"]:
        exec_result = _as_dict(item.get("exec_result"))
        if exec_result.get("status") != "executed":
            continue
        keyword_text = item.get("keyword_text") or ""
        campaign_name = exec_result.get("campaign_name") or item.get("campaign_name") or ""
        facts.append(
            {
                "fact_id": _fact_id("keywords", "ai_keyword", keyword_text, campaign_name),
                "primary_block": "executed",
                "domain": "keywords",
                "kind": "ai_keyword_executed",
                "subject": keyword_text,
                "target": campaign_name,
                "action_label": "keyword_added",
                "evidence": "AI keyword executed in raw run.",
            }
        )

    for item in nr["keyword_proposals"]:
        result = _as_dict(item.get("result"))
        if result.get("status") != "executed":
            continue
        action = item.get("action") or "keyword_change"
        keyword_text = item.get("keyword_text") or item.get("term") or ""
        campaign_name = item.get("campaign_name") or ""
        facts.append(
            {
                "fact_id": _fact_id("keywords", action, keyword_text, campaign_name),
                "primary_block": "executed",
                "domain": "keywords",
                "kind": action,
                "subject": keyword_text,
                "target": campaign_name,
                "action_label": action,
                "evidence": item.get("reason") or "Executed keyword action visible in raw run.",
            }
        )

    for item in nr["builder_executed"]:
        result = _as_dict(item.get("result"))
        if result.get("status") != "success":
            continue
        ad_group_name = item.get("ad_group_name") or ""
        campaign_name = item.get("campaign_name") or ""
        facts.append(
            {
                "fact_id": _fact_id("ad_groups", "builder_success", ad_group_name, campaign_name),
                "primary_block": "executed",
                "domain": "ad_groups",
                "kind": "ad_group_created",
                "subject": ad_group_name,
                "target": campaign_name,
                "action_label": "ad_group_created",
                "evidence": "Builder executed ad group successfully.",
            }
        )

    return facts


def _build_blocked_facts(nr: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    for item in nr["blocked"]:
        keyword_text = item.get("keyword") or item.get("keyword_text") or ""
        campaign_name = item.get("campaign") or item.get("campaign_name") or ""
        facts.append(
            {
                "fact_id": _fact_id("keywords", "blocked", keyword_text, campaign_name),
                "primary_block": "blocked",
                "domain": "keywords",
                "kind": "keyword_blocked",
                "review_scope": "keywords",
                "finding": item.get("reason") or "Keyword action blocked in raw run.",
                "block_reason": item.get("block_reason") or "not_observable_from_run",
                "next_step": None,
                "severity": item.get("urgency") or item.get("risk_level") or "unknown",
            }
        )

    for item in nr["blocked_budget_auto"] + nr["blocked_budget_scale_auto"]:
        campaign_name = item.get("campaign_name") or item.get("campaign") or ""
        facts.append(
            {
                "fact_id": _fact_id("budget", "blocked", campaign_name, item.get("reason")),
                "primary_block": "blocked",
                "domain": "budget",
                "kind": "budget_blocked",
                "review_scope": "budget",
                "finding": item.get("guardrail_msg") or item.get("reason") or "Budget action blocked in raw run.",
                "block_reason": item.get("reason") or "not_observable_from_run",
                "next_step": None,
                "severity": "high",
            }
        )

    return facts


def _build_proposed_facts(nr: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    quick_wins: list[dict[str, Any]] = []

    for item in nr["keyword_proposals"]:
        result = _as_dict(item.get("result"))
        if result.get("status") == "executed":
            continue
        keyword_text = item.get("keyword_text") or item.get("keyword") or item.get("text") or ""
        campaign_name = item.get("campaign_name") or item.get("campaign") or ""
        facts.append(
            {
                "fact_id": _fact_id("keywords", "proposal", keyword_text, campaign_name),
                "primary_block": "proposed",
                "domain": "keywords",
                "kind": "keyword_proposal",
                "subject": keyword_text,
                "target": campaign_name,
                "proposal_label": "keyword_proposal",
                "reason": item.get("reason") or "Keyword proposal visible in raw run.",
                "next_step": "human_review",
            }
        )

    for item in nr["budget_proposals"]:
        campaign_name = item.get("campaign_name") or ""
        facts.append(
            {
                "fact_id": _fact_id("budget", "proposal", campaign_name, item.get("suggested_daily_budget")),
                "primary_block": "proposed",
                "domain": "budget",
                "kind": "budget_proposal",
                "subject": campaign_name,
                "target": None,
                "proposal_label": "budget_proposal",
                "reason": item.get("reason") or "Budget proposal visible in raw run.",
                "next_step": "human_review",
            }
        )

    for item in nr["ba2_proposals"]:
        campaign_name = item.get("campaign_name") or ""
        signal = item.get("signal") or "BA2_SCALE"
        domain = "redistribution" if signal == "BA2_REALLOC" else "budget"
        facts.append(
            {
                "fact_id": _fact_id(domain, "proposal", campaign_name, signal),
                "primary_block": "proposed",
                "domain": domain,
                "kind": signal.lower(),
                "subject": campaign_name,
                "target": None,
                "proposal_label": signal.lower(),
                "reason": item.get("fund_source") or "Scale or reallocation proposal visible in raw run.",
                "next_step": "human_review",
            }
        )

    for item in _as_list(nr["audit_result"].get("quick_wins")):
        quick_wins.append(
            {
                "fact_id": _fact_id("quick_win", item.get("id"), item.get("description")),
                "primary_block": "proposed",
                "label": item.get("description") or "",
                "severity": item.get("severity") or "",
                "eta_minutes": item.get("fix_minutes"),
            }
        )

    return facts, quick_wins


def _build_analyzed_facts(nr: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    bo = nr["budget_optimizer"]
    redistribution_analysis = _as_dict(bo.get("redistribution_analysis"))
    has_budget_module = bool(bo) or bool(nr["monthly_budget_status"])

    if redistribution_analysis:
        fund_sources = _as_list(redistribution_analysis.get("fund_sources"))
        receiver_candidates = _as_list(redistribution_analysis.get("receiver_candidates"))
        allocation_matrix = _as_list(redistribution_analysis.get("allocation_matrix"))
        if not fund_sources and not receiver_candidates:
            finding = "No eligible source or receiver campaigns in redistribution analysis."
            reason = "no_eligible_entities"
        elif not allocation_matrix:
            finding = "Redistribution was analyzed without an executable allocation."
            reason = "no_valid_adjustment_case"
        else:
            finding = "Redistribution was analyzed, but no automatic execution is visible in the raw run."
            reason = "no_valid_adjustment_case"

        facts.append(
            {
                "fact_id": _fact_id("redistribution", "analysis", redistribution_analysis.get("net_daily_mxn")),
                "primary_block": "analyzed",
                "domain": "redistribution",
                "kind": "reviewed_no_action",
                "review_scope": "redistribution",
                "finding": finding,
                "no_action_reason": reason,
                "next_step": "monitor_next_runs",
            }
        )

    if has_budget_module:
        facts.append(
            {
                "fact_id": _fact_id("budget", "analysis", len(_as_list(bo.get("decisions")))),
                "primary_block": "analyzed",
                "domain": "budget",
                "kind": "reviewed_no_action",
                "review_scope": "budget",
                "finding": "Budget module is present, but the raw run does not expose a specific no-action reason.",
                "no_action_reason": "not_observable_from_run",
                "next_step": None,
            }
        )

    return facts


# ============================================================================
# Deduplication by fact_id + primary_block
# ============================================================================

def _deduplicate_primary_facts(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    for fact in candidates:
        fact_id = fact["fact_id"]
        current = selected.get(fact_id)
        if current is None:
            selected[fact_id] = fact
            continue
        current_priority = PRIMARY_BLOCK_PRIORITY[current["primary_block"]]
        candidate_priority = PRIMARY_BLOCK_PRIORITY[fact["primary_block"]]
        if candidate_priority < current_priority:
            selected[fact_id] = fact

    return list(selected.values())


# ============================================================================
# Contract builders
# ============================================================================

def _build_meta(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version": "v1",
        "run_id": run.get("run_id") or "",
        "timestamp_merida": run.get("timestamp_merida") or "",
        "result_class": run.get("result_class") or "sin_acciones",
        "requires_human_attention": bool(run.get("human_pending") or False),
        "has_real_audit": bool(run.get("is_real_audit") or False),
        "campaigns_reviewed": int(run.get("campaigns_reviewed") or 0),
    }


def _build_summary(
    facts_by_block: dict[str, list[dict[str, Any]]],
    quick_wins: list[dict[str, Any]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    domain_status = {domain: "not_observable" for domain in CORE_DOMAINS}

    for domain in CORE_DOMAINS:
        for primary_block in PRIMARY_BLOCK_ORDER:
            if any(item.get("domain") == domain for item in facts_by_block[primary_block]):
                domain_status[domain] = primary_block
                break

    return {
        "execution_count": len(facts_by_block["executed"]),
        "proposal_count": len(facts_by_block["proposed"]) + len(quick_wins),
        "analysis_present": bool(facts_by_block["analyzed"]),
        "requires_human_attention": bool(
            meta["requires_human_attention"]
            or facts_by_block["proposed"]
            or facts_by_block["blocked"]
            or quick_wins
        ),
        "domain_status": domain_status,
    }


def _build_executed_block(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"present": bool(items), "items": items}


def _build_proposed_block(items: list[dict[str, Any]], quick_wins: list[dict[str, Any]]) -> dict[str, Any]:
    return {"present": bool(items or quick_wins), "items": items, "quick_wins": quick_wins}


def _build_analyzed_block(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"present": bool(items), "items": items}


def _build_blocked_block(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"present": bool(items), "items": items}


def _build_account_context(nr: dict[str, Any]) -> dict[str, Any]:
    audit_result = nr["audit_result"]
    monthly_status = nr["monthly_budget_status"]
    ventas_ayer = nr["ventas_ayer"]

    sales_total = _mxn_int(ventas_ayer.get("venta_total_dia"))
    diners_total = ventas_ayer.get("comensales_total")
    business_text = None
    if sales_total is not None:
        business_text = f"Negocio ayer: venta total ${sales_total:,}"
        if diners_total is not None:
            business_text += f" · comensales {int(diners_total)}"

    return {
        "present": True,
        "scorecard": {
            "score": audit_result.get("score"),
            "grade": audit_result.get("grade"),
            "period_label": "Ultimos 30 dias",
        },
        "spend_context": {
            "ads_spend_24h_mxn": nr["ads_24h"].get("spend_mxn"),
            "month_spend_mxn": monthly_status.get("spend_so_far"),
            "month_cap_mxn": monthly_status.get("monthly_cap"),
            "month_pct": monthly_status.get("pct_used"),
        },
        "campaign_snapshot": {
            "period_label": "24h",
            "rows": _campaign_snapshot_rows(nr["ads_24h"]),
            "footnote": (
                "SMART does not share the same conversion semantics as SEARCH; "
                "\"Conv (Ads)\" and \"CPA (Ads)\" may not reflect reservations, orders, "
                "or micro-actions visible in this email."
            ),
        },
        "business_yesterday": {
            "present": business_text is not None,
            "text": business_text,
        },
    }


def _build_daily_reviews(nr: dict[str, Any]) -> dict[str, Any]:
    audit_result = nr["audit_result"]
    has_audit = audit_result.get("score") is not None
    category_scores = _as_dict(audit_result.get("category_scores"))
    checks_by_category = _as_dict(audit_result.get("checks_by_category"))

    categories = []
    for key, label in CATEGORY_LABELS:
        score = category_scores.get(key)
        items = []
        for item in _as_list(checks_by_category.get(key)):
            items.append(
                {
                    "result": item.get("result") or "",
                    "detail": item.get("detail") or item.get("description") or item.get("message") or "",
                    "severity": item.get("severity") or "",
                }
            )
        if score is None and not items:
            continue
        categories.append({"label": label, "score": score, "items": items})

    fallback_message = None
    if has_audit and not categories:
        fallback_message = "Audit is available in this run, but no category breakdown is visible."

    return {
        "present": bool(has_audit),
        "has_audit": bool(has_audit),
        "categories": categories,
        "fallback_message": fallback_message,
    }


def build_report_contract_v1(run: dict[str, Any]) -> dict[str, Any]:
    nr = _normalize_run(run)
    meta = _build_meta(nr["run"])

    executed_facts = _build_executed_facts(nr)
    blocked_facts = _build_blocked_facts(nr)
    proposed_facts, quick_wins = _build_proposed_facts(nr)
    analyzed_facts = _build_analyzed_facts(nr)

    deduped_facts = _deduplicate_primary_facts(
        executed_facts + blocked_facts + proposed_facts + analyzed_facts
    )

    facts_by_block = {name: [] for name in PRIMARY_BLOCK_ORDER}
    for fact in deduped_facts:
        facts_by_block[fact["primary_block"]].append(fact)

    contract = {
        "meta": meta,
        "summary": _build_summary(facts_by_block, quick_wins, meta),
        "executed": _build_executed_block(facts_by_block["executed"]),
        "proposed": _build_proposed_block(facts_by_block["proposed"], quick_wins),
        "analyzed": _build_analyzed_block(facts_by_block["analyzed"]),
        "blocked": _build_blocked_block(facts_by_block["blocked"]),
        "account_context": _build_account_context(nr),
        "daily_reviews": _build_daily_reviews(nr),
    }
    return contract
