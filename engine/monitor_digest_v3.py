"""Read-only Monitor Digest V3.

This module summarizes the V3 negatives classifier into a small Monitor-facing
contract. It does not call Google Ads and does not write anything.
"""
from __future__ import annotations

import json
import os
import unicodedata
import urllib.parse
from collections import Counter
from typing import Any

from engine.monitor_email_renderer import render_monitor_email
from engine.monitor_sections import (
    build_ads_quality_summary,
    build_campaign_rows_from_context,
    build_gbp_summary,
    build_reviews_summary,
    build_search_console,
    build_search_terms_cards,
    build_seo_summary,
    enrich_campaign_rows,
)
from engine.negatives_classifier_v3 import build_negatives_preview_v3_payload
from engine.search_term_classifier import EXTERNAL_ENTITY_GENERIC_TOKENS


MAX_DECISIONS = 5
DICTIONARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "term_dictionary.json",
)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def load_term_dictionary(path: str = DICTIONARY_PATH) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "identity_labels": {},
            "behavior_labels": {},
            "decision_copy": {},
            "high_priority_entities": [],
        }


def _raw_index(search_terms_payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for term in search_terms_payload.get("search_terms", []) or []:
        key = (_normalize(term.get("query")), str(term.get("campaign_id") or term.get("campaign_name") or ""))
        out[key] = term
    return out


def _raw_for_item(
    item: dict[str, Any],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    search_terms_payload: dict[str, Any],
) -> dict[str, Any]:
    key = (_normalize(item.get("term")), str(item.get("campaign_id") or item.get("campaign") or ""))
    if key in raw_by_key:
        return raw_by_key[key]
    term_norm = _normalize(item.get("term"))
    for raw in search_terms_payload.get("search_terms", []) or []:
        if _normalize(raw.get("query")) == term_norm:
            return raw
    return {}


def _contains_high_priority_entity(term: str, dictionary: dict[str, Any]) -> bool:
    norm = _normalize(term)
    return any(entity in norm for entity in dictionary.get("high_priority_entities", []) or [])


def _is_acknowledged_external(term: str, dictionary: dict[str, Any]) -> bool:
    """Term already classified by Hugo (seeded in the dictionary) → never asked again."""
    tokens = set(_normalize(term).split())
    roots = dictionary.get("acknowledged_external_roots", []) or []
    return any(root in tokens for root in roots)


def _identity_label(identity: str, dictionary: dict[str, Any]) -> str:
    return (dictionary.get("identity_labels") or {}).get(identity, identity or "desconocido")


def _behavior_label(behavior: str, dictionary: dict[str, Any]) -> str:
    return (dictionary.get("behavior_labels") or {}).get(behavior, behavior or "desconocida")


def _decision_reason(decision_type: str, dictionary: dict[str, Any]) -> str:
    return (dictionary.get("decision_copy") or {}).get(decision_type, "Revisar manualmente.")


def _decision_type(item: dict[str, Any], raw: dict[str, Any], dictionary: dict[str, Any]) -> str | None:
    behavior = item.get("behavior_axis")
    identity = item.get("identity_axis")
    term = item.get("term") or ""
    already_negative = item.get("already_negative") is True

    # B-3: a term already classified by Hugo (seeded in the dictionary) is never asked again.
    if _is_acknowledged_external(term, dictionary):
        return None

    if identity in {"marca_propia", "intencion_thai", "generico_util", "categoria_asiatica"}:
        return None
    if behavior == "senal_dinero":
        return None
    if behavior == "senal_local":
        return None
    if behavior == "desconocida" and (
        _number(raw.get("conversions")) > 0 or _number(raw.get("all_conversions")) > 0
    ):
        return "tracking_review"
    if already_negative:
        return None
    if (
        item.get("alta_prioridad") is True
        or item.get("confirmado_por_hugo") is True
        or _contains_high_priority_entity(term, dictionary)
    ):
        return "negative_leak"
    if identity == "basura" and behavior == "sin_conversion":
        return "negative_leak"
    if identity == "restaurante_externo" and behavior == "sin_conversion":
        return "external_review"
    return None


def _decision_action(decision_type: str) -> str:
    if decision_type == "negative_leak":
        return "review_one_by_one"
    if decision_type == "external_review":
        return "confirm_identity"
    if decision_type == "tracking_review":
        return "review_tracking"
    if decision_type == "local_signal":
        return "review_local_signal"
    return "no_action"


def _decision_priority(item: dict[str, Any], raw: dict[str, Any], decision_type: str) -> float:
    base = _number(item.get("cost_mxn"))
    if item.get("alta_prioridad") is True or item.get("confirmado_por_hugo") is True:
        base += 10000
    if decision_type == "negative_leak":
        base += 1000
    elif decision_type == "external_review":
        base += 500
    elif decision_type == "tracking_review":
        base += 100
    if raw.get("already_negative") is True:
        base -= 10000
    return base


def _build_decision(
    item: dict[str, Any],
    raw: dict[str, Any],
    decision_type: str,
    dictionary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_type": decision_type,
        "term": item.get("term"),
        "campaign": item.get("campaign"),
        "clicks": _int(item.get("clicks")),
        "cost_mxn": round(_number(item.get("cost_mxn")), 2),
        "conversions": _number(item.get("conversions")),
        "all_conversions": _number(raw.get("all_conversions")),
        "identity_axis": item.get("identity_axis"),
        "identity_label": _identity_label(item.get("identity_axis"), dictionary),
        "behavior_axis": item.get("behavior_axis"),
        "behavior_label": _behavior_label(item.get("behavior_axis"), dictionary),
        "data_axis": item.get("data_axis"),
        "state_ui": item.get("state_ui"),
        "reason_human": item.get("reason_human"),
        "digest_reason": _decision_reason(decision_type, dictionary),
        "recommended_action": _decision_action(decision_type),
        "write_action": None,
        "block_allowed": False,
        "suggested_match_type": item.get("suggested_match_type"),
        "already_negative": item.get("already_negative"),
        "confirmado_por_hugo": item.get("confirmado_por_hugo") is True,
        "alta_prioridad": item.get("alta_prioridad") is True,
    }


def _decision_group_key(term: str, dictionary: dict[str, Any]) -> str:
    """Core-entity key so variants of the same place collapse into one decision."""
    norm = _normalize(term)
    for root in dictionary.get("competitor_roots", []) or []:
        if root in norm:
            return root
    distinctive = [t for t in norm.split() if t not in EXTERNAL_ENTITY_GENERIC_TOKENS]
    return " ".join(sorted(distinctive)) if distinctive else norm


def _group_decision_candidates(
    candidates: list[tuple[float, dict[str, Any]]],
    dictionary: dict[str, Any],
) -> list[tuple[float, dict[str, Any]]]:
    """Merge decisions whose normalized core entity matches into one decision
    carrying every variant (B-4). Cost and clicks are summed across variants."""
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for priority, decision in candidates:
        key = _decision_group_key(decision.get("term", ""), dictionary)
        if key not in groups:
            groups[key] = {"priority": priority, "decision": dict(decision), "cost": 0.0,
                           "clicks": 0, "variantes": [], "campaigns": []}
            order.append(key)
        group = groups[key]
        group["variantes"].append(decision.get("term"))
        camp = decision.get("campaign")
        if camp and camp not in group["campaigns"]:
            group["campaigns"].append(camp)
        group["cost"] += _number(decision.get("cost_mxn"))
        group["clicks"] += _int(decision.get("clicks"))
        if priority > group["priority"]:
            group["priority"] = priority
            group["decision"] = dict(decision)

    out = []
    for key in order:
        group = groups[key]
        decision = group["decision"]
        decision["cost_mxn"] = round(group["cost"], 2)
        decision["clicks"] = group["clicks"]
        decision["variantes"] = group["variantes"]
        decision["variantes_count"] = len(group["variantes"])
        decision["campaigns"] = group["campaigns"]
        out.append((group["priority"], decision))
    return out


def _attach_action_links(decisions: list[dict[str, Any]], links: dict[str, Any]) -> None:
    """A2: each decision gets two links to the protected Part-B page with the action
    preselected (Revisar y bloquear / Dejar). No execution happens in the email."""
    base = links.get("bloqueo_base")
    token = links.get("token", "")
    if not base:
        return
    for d in decisions:
        term_q = urllib.parse.quote(str(d.get("term") or ""))
        suffix = f"?term={term_q}&token={urllib.parse.quote(str(token))}"
        d["link_bloquear"] = f"{base}{suffix}&accion=bloquear"
        d["link_dejar"] = f"{base}{suffix}&accion=dejar"


def _campaign_status(row: dict[str, Any]) -> str:
    if row["money_conversions"] > 0:
        return "Tiene dinero real medible."
    if row["local_signals"] > 0:
        return "Solo señales locales. No calcular CPA de dinero."
    return "Sin dinero real medible."


def _build_campaign_rows(
    items: list[dict[str, Any]],
    raw_by_key: dict[tuple[str, str], dict[str, Any]],
    search_terms_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    campaigns: dict[str, dict[str, Any]] = {}

    for item in items:
        raw = _raw_for_item(item, raw_by_key, search_terms_payload)
        campaign_name = str(item.get("campaign") or raw.get("campaign_name") or "Sin campaña")
        row = campaigns.setdefault(campaign_name, {
            "campaign_name": campaign_name,
            "spend_mxn": 0.0,
            "money_conversions": 0.0,
            "money_cpa_mxn": None,
            "local_signals": 0.0,
            "local_signal_cost_mxn": None,
            "clicks": 0,
            "impressions": 0,
            "status_human": "",
            "recommendation_human": "Monitorear. No escalar automáticamente.",
        })

        cost = _number(item.get("cost_mxn"))
        conversions = _number(raw.get("conversions", item.get("conversions")))
        all_conversions = _number(raw.get("all_conversions", item.get("conversions")))
        behavior = item.get("behavior_axis")

        row["spend_mxn"] += cost
        row["clicks"] += _int(item.get("clicks", raw.get("clicks")))
        row["impressions"] += _int(raw.get("impressions", item.get("impressions")))
        if behavior == "senal_dinero":
            row["money_conversions"] += conversions or all_conversions
        elif behavior == "senal_local":
            row["local_signals"] += all_conversions or conversions
            row["local_signal_cost_mxn"] = _number(row["local_signal_cost_mxn"]) + cost

    rows = []
    for row in campaigns.values():
        row["spend_mxn"] = round(row["spend_mxn"], 2)
        row["money_conversions"] = round(row["money_conversions"], 2)
        row["local_signals"] = round(row["local_signals"], 2)
        if row["money_conversions"] > 0:
            row["money_cpa_mxn"] = round(row["spend_mxn"] / row["money_conversions"], 2)
        if row["local_signal_cost_mxn"] is not None:
            row["local_signal_cost_mxn"] = round(_number(row["local_signal_cost_mxn"]), 2)
        row["status_human"] = _campaign_status(row)
        rows.append(row)

    return sorted(rows, key=lambda row: row["spend_mxn"], reverse=True)


def _build_negative_leak_anomaly(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "negative_leak",
        "term": decision.get("term"),
        "spend_mxn": decision.get("cost_mxn"),
        "campaign": decision.get("campaign"),
        "reason_human": "Ya existe como negativo o variante relacionada, pero sigue gastando.",
    }


def _build_warnings(search_terms_payload: dict[str, Any]) -> list[dict[str, Any]]:
    search_terms = search_terms_payload.get("search_terms", [])
    data_broken = not isinstance(search_terms, list)
    return [
        {
            "type": "data_broken",
            "detected": data_broken,
            "reason_human": (
                "El payload de términos no tiene la estructura esperada."
                if data_broken
                else "No se detectaron datos rotos en el payload recibido."
            ),
        },
        {
            "type": "conversion_mapping_incomplete",
            "detected": True,
            "reason_human": (
                "El digest recibe conversion_quality ya calculado; el contrato todavía no expone "
                "el detalle por acción de conversión."
            ),
        },
    ]


def _build_search_terms_summary(
    items: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    desperdicio_confirmado = sum(
        _number(decision.get("cost_mxn"))
        for decision in decisions
        if decision.get("decision_type") == "negative_leak"
    )
    return {
        "terminos_revisados": len(items),
        "marca_intencion_thai_protegida": sum(
            1 for item in items if item.get("identity_axis") in {"marca_propia", "intencion_thai"}
        ),
        "busquedas_utiles": sum(1 for item in items if item.get("identity_axis") == "generico_util"),
        "busquedas_relacionadas": sum(1 for item in items if item.get("identity_axis") == "categoria_asiatica"),
        "restaurantes_externos_por_confirmar": sum(
            1 for item in items if item.get("state_ui") == "Restaurante externo por confirmar"
        ),
        "senales_locales": sum(1 for item in items if item.get("behavior_axis") == "senal_local"),
        "decisiones_pendientes": len(decisions),
        "desperdicio_confirmado_mxn": round(desperdicio_confirmado, 2),
    }


def build_monitor_digest(
    search_terms_payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if search_terms_payload.get("status") != "success":
        return search_terms_payload

    context = dict(context or {})
    context.setdefault("links", {})

    dictionary = load_term_dictionary()
    v3 = build_negatives_preview_v3_payload(search_terms_payload)
    raw_by_key = _raw_index(search_terms_payload)
    items = v3.get("items", []) or []

    summary = {
        "terms_reviewed": len(items),
        "money_signal_cost_mxn": 0.0,
        "local_signal_cost_mxn": 0.0,
        "negative_leak_cost_mxn": 0.0,
        "protected_cost_mxn": 0.0,
        "decisions_count": 0,
    }
    decision_candidates = []
    identity_counts = Counter()
    behavior_counts = Counter()

    for item in items:
        raw = _raw_for_item(item, raw_by_key, search_terms_payload)
        cost = _number(item.get("cost_mxn"))
        identity = item.get("identity_axis")
        behavior = item.get("behavior_axis")
        identity_counts[identity] += 1
        behavior_counts[behavior] += 1

        if behavior == "senal_dinero":
            summary["money_signal_cost_mxn"] += cost
        if behavior == "senal_local":
            summary["local_signal_cost_mxn"] += cost
        if identity in {"marca_propia", "intencion_thai", "generico_util", "categoria_asiatica"}:
            summary["protected_cost_mxn"] += cost

        decision_type = _decision_type(item, raw, dictionary)
        if decision_type == "negative_leak":
            summary["negative_leak_cost_mxn"] += cost
        if decision_type:
            decision_candidates.append((
                _decision_priority(item, raw, decision_type),
                _build_decision(item, raw, decision_type, dictionary),
            ))

    grouped_candidates = _group_decision_candidates(decision_candidates, dictionary)
    grouped_candidates.sort(key=lambda pair: pair[0], reverse=True)
    decisions = [decision for _, decision in grouped_candidates[:MAX_DECISIONS]]
    _attach_action_links(decisions, context.get("links") or {})
    summary["decisions_count"] = len(decisions)
    if context.get("campaign_metrics"):
        campaign_rows = build_campaign_rows_from_context(context)
    else:
        campaign_rows = enrich_campaign_rows(
            _build_campaign_rows(items, raw_by_key, search_terms_payload),
            context,
        )
    anomalies = [
        _build_negative_leak_anomaly(decision)
        for decision in decisions
        if decision.get("decision_type") == "negative_leak"
    ]
    search_terms_summary = _build_search_terms_summary(items, decisions)

    for key in list(summary.keys()):
        if key.endswith("_mxn"):
            summary[key] = round(summary[key], 2)

    digest = {
        "status": "success",
        "source": "monitor_digest_v3",
        "read_only": True,
        "date_range": search_terms_payload.get("date_range"),
        "generated_date": context.get("generated_date"),
        "links": context.get("links") or {},
        "pedidos_gloriafood_interno": context.get("pedidos_gloriafood_interno"),
        "reservas_persist": context.get("reservas_persist"),
        "max_decisions": MAX_DECISIONS,
        "summary": summary,
        "identity_counts": dict(identity_counts),
        "behavior_counts": dict(behavior_counts),
        "v3_state_counts": v3.get("state_counts", {}),
        "campaign_rows": campaign_rows,
        "search_terms_summary": search_terms_summary,
        "search_terms_cards": build_search_terms_cards(items, decisions, context),
        "gbp_summary": build_gbp_summary(context),
        "reviews_summary": build_reviews_summary(context, context.get("reviews_reference_date")),
        "ads_quality_summary": build_ads_quality_summary(context),
        "seo_summary": build_seo_summary(context),
        "search_console": build_search_console(context),
        "decisions": decisions,
        "anomalies": anomalies,
        "warnings": _build_warnings(search_terms_payload),
        "safety": {
            "writes_google_ads": False,
            "calls_execute_optimization": False,
            "touches_budgets": False,
            "post_required": False,
        },
    }
    digest.update(render_monitor_email(digest, mode=context.get("mode", "monday")))
    return digest
