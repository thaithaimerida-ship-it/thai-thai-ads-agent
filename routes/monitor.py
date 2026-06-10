"""Read-only Monitor endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from engine.monitor_digest_v3 import build_monitor_digest
from routes.analysis import _build_search_terms_payload


router = APIRouter(tags=["monitor"])


@router.get("/monitor/digest")
async def monitor_digest(date_range: str = "LAST_7_DAYS"):
    """Monitor Digest V3: read-only summary for the future daily email."""
    payload = _build_search_terms_payload(date_range)
    return build_monitor_digest(payload)
