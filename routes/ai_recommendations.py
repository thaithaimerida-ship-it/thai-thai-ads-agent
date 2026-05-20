"""
Endpoint admin que dispara el generador engine.ai_recommendations con datos
frescos de Google Ads.

POST /run-ai-recommendations  (require_token)
  body opcional: {"date_range": "LAST_7_DAYS", "persist": true}

Flujo:
  1. Valida date_range contra VALID_DATE_RANGES.
  2. _build_payload: fetch_campaign_data + fetch_search_term_data (via
     get_engine_modules), transforma al shape esperado por el generador,
     enriquece search terms con competitor_term/negative_candidate
     (importados desde routes.analysis — coupling de underscore-private
     aceptado conscientemente; ver TODO al pie).
  3. generate_recommendations(payload, persist=, session_id=) — el generador
     valida schema, filtra hallucinations, deduplica, persiste con
     decision="proposed" + approval_token.
  4. Devuelve el resultado del generador + session_id + payload_size para debug.

NO toca Google Ads para mutar — eso lo hace POST /apply-budget-changes.

TODO refactor: _is_competitor_term/_is_negative_candidate viven como funciones
privadas en routes/analysis.py. Cuando aparezca un tercer consumidor de esa
lógica, moverlas a engine/search_terms_classifier.py.
"""
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from engine.ai_recommendations import generate_recommendations
from routes.auth_token import require_token
# Coupling consciente con routes/analysis.py — ver TODO en docstring.
from routes.analysis import (
    VALID_DATE_RANGES,
    _is_competitor_term,
    _is_negative_candidate,
)

router = APIRouter(tags=["ai_recommendations"])


class RunRecommendationsRequest(BaseModel):
    date_range: str = "LAST_7_DAYS"
    persist: bool = True


@router.post("/run-ai-recommendations", dependencies=[Depends(require_token)])
async def run_ai_recommendations(
    request: RunRecommendationsRequest = Body(default_factory=RunRecommendationsRequest),
) -> dict[str, Any]:
    """Dispara el generador con datos frescos. Auth: X-API-Token."""
    date_range = request.date_range.strip().upper()
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
        )

    payload = _build_payload(date_range)

    session_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    result = generate_recommendations(
        payload,
        persist=request.persist,
        session_id=session_id,
    )

    # Enriquecer la respuesta con metadata útil para debug/auditoría.
    result["session_id"] = session_id
    result["date_range"] = date_range
    result["payload_size"] = {
        "campaigns": len(payload["campaigns"]),
        "search_terms": len(payload["search_terms"]),
    }
    return result


def _build_payload(date_range: str) -> dict[str, Any]:
    """Construye el payload esperado por generate_recommendations.

    Lee de Google Ads usando los fetchers ya existentes (vía get_engine_modules),
    NO duplica lógica de SQL ni de auth. Transformaciones:
      - campaigns: agrega `spend` (cost/1M), `cpa` (spend/conv), incluye
        `daily_budget_mxn` para que el LLM proponga budgets coherentes con
        el presupuesto actual. Normaliza id a str.
      - search_terms: renombra `query`→`term`, agrega `cost` y los flags
        `competitor_term`/`negative_candidate` (heurísticas heredadas de
        /search-terms para que el LLM identifique candidatos sin re-derivarlos).
      - Cap mixto: 15 por cost desc + 15 por conversions desc (dedup por
        (term, campaign_id)) → hasta 30 terms. Razón: top-cost solo oculta
        search terms baratos con muchas conversiones que son señal de scale.
    """
    from main import get_engine_modules

    engine = get_engine_modules()
    if not engine:
        raise HTTPException(status_code=503, detail="Engine modules no disponibles")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
    if not customer_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_ADS_TARGET_CUSTOMER_ID no configurado en el entorno",
        )

    try:
        client = engine["get_ads_client"]()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo instanciar Google Ads client: {exc}",
        )

    raw_campaigns = engine["fetch_campaign_data"](client, customer_id, date_range) or []
    raw_search_terms = engine["fetch_search_term_data"](client, customer_id, date_range) or []

    campaigns = []
    for c in raw_campaigns:
        spend = round((c.get("cost_micros") or 0) / 1_000_000, 2)
        conversions = float(c.get("conversions") or 0)
        all_conversions = float(c.get("all_conversions") or 0)
        cpa = round(spend / conversions, 2) if conversions > 0 else 0.0
        campaigns.append({
            "id": str(c.get("id", "")),
            "name": c.get("name", ""),
            "status": c.get("status", ""),
            "advertising_channel_type": c.get("advertising_channel_type", ""),
            "daily_budget_mxn": c.get("daily_budget_mxn", 0.0),
            "spend": spend,
            "conversions": conversions,
            "all_conversions": all_conversions,
            "clicks": int(c.get("clicks") or 0),
            "impressions": int(c.get("impressions") or 0),
            "cpa": cpa,
        })

    all_search_terms = []
    for st in raw_search_terms:
        cost = round((st.get("cost_micros") or 0) / 1_000_000, 2)
        conversions = float(st.get("conversions") or 0)
        query = st.get("query", "")
        all_search_terms.append({
            "term": query,
            "campaign_id": str(st.get("campaign_id", "")),
            "campaign_name": st.get("campaign_name", ""),
            "cost": cost,
            "conversions": conversions,
            "clicks": int(st.get("clicks") or 0),
            "competitor_term": _is_competitor_term(query, conversions),
            "negative_candidate": _is_negative_candidate(query, cost, conversions),
        })

    # Cap mixto: 15 top-cost + 15 top-conversions (dedup por (term, campaign_id)).
    by_cost = sorted(all_search_terms, key=lambda t: t["cost"], reverse=True)[:15]
    seen_keys = {(t["term"], t["campaign_id"]) for t in by_cost}
    by_conv = [
        t for t in sorted(all_search_terms, key=lambda t: t["conversions"], reverse=True)
        if (t["term"], t["campaign_id"]) not in seen_keys
    ][:15]
    search_terms = by_cost + by_conv

    return {
        "campaigns": campaigns,
        "search_terms": search_terms,
    }
