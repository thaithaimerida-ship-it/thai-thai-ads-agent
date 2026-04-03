"""
Routes de Tracking — fix-tracking, fix-tracking/confirm, audit-log.
"""
import os
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.db_sync import get_db_path

router = APIRouter(tags=["tracking"])

CUSTOMER_ID = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")


class FixTrackingConfirmRequest(BaseModel):
    conversion_action_ids: List[str]


def _get_engine():
    from main import get_engine_modules
    return get_engine_modules()


@router.post("/fix-tracking")
async def fix_tracking():
    """
    Paso 1: Activa auto-tagging en la cuenta Google Ads.
    Paso 2: Lista todas las conversiones y propone cuáles desactivar.
    Requiere confirmación vía POST /fix-tracking/confirm antes de ejecutar.
    """
    modules = _get_engine()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import enable_auto_tagging, fetch_conversion_actions, log_agent_action

    auto_tag_result = enable_auto_tagging(client, customer_id)
    log_agent_action("enable_auto_tagging", f"cuenta {customer_id}", {},
                     {"auto_tagging_enabled": True}, auto_tag_result["status"], auto_tag_result)

    conversions = fetch_conversion_actions(client, customer_id)
    to_disable = [c for c in conversions if not c["protected"]]

    return {
        "auto_tagging": auto_tag_result,
        "conversions_found": conversions,
        "proposed_to_disable": to_disable,
        "protected": [c for c in conversions if c["protected"]],
        "next_step": "POST /fix-tracking/confirm con los IDs que apruebas desactivar"
    }


@router.post("/fix-tracking/confirm")
async def fix_tracking_confirm(request: FixTrackingConfirmRequest):
    """Desactiva las conversiones aprobadas. Las protegidas son rechazadas automáticamente."""
    modules = _get_engine()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import fetch_conversion_actions, disable_conversion_action, log_agent_action

    all_conversions = {c["id"]: c["name"] for c in fetch_conversion_actions(client, customer_id)}
    results = []

    for ca_id in request.conversion_action_ids:
        name = all_conversions.get(ca_id, "unknown")
        result = disable_conversion_action(client, customer_id, ca_id, name)
        log_agent_action("disable_conversion", name, {"status": "ENABLED"},
                         {"status": "HIDDEN"}, result["status"], result)
        results.append({"id": ca_id, "name": name, "result": result})

    return {"results": results}


@router.get("/audit-log")
async def get_audit_log(limit: int = 50, action_type: Optional[str] = None):
    """Retorna historial de acciones ejecutadas por el agente."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM agent_actions"
    params = []
    if action_type:
        query += " WHERE action_type = ?"
        params.append(action_type)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "total": len(rows),
        "actions": [dict(r) for r in rows]
    }
