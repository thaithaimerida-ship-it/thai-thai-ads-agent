"""Read-only Monitor endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.monitor_digest_v3 import build_monitor_digest
from routes.analysis import VALID_DATE_RANGES, _build_search_terms_payload, _normalize_date_range


router = APIRouter(tags=["monitor"])


@router.get("/monitor/digest")
async def monitor_digest(date_range: str = "LAST_7_DAYS"):
    """Monitor Digest V3: read-only summary for the future daily email."""
    date_range = _normalize_date_range(date_range)
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"date_range invalido: '{date_range}'. Validos: {sorted(VALID_DATE_RANGES)}",
        )
    payload = _build_search_terms_payload(date_range)
    return build_monitor_digest(payload)
