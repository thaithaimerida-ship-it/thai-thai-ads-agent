"""
Routes del Builder — Crea campañas desde lenguaje natural.
POST /build-campaign → genera config
POST /deploy-campaign → ejecuta el deploy aprobado
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["builder"])


class BuildRequest(BaseModel):
    prompt: str
    auto_deploy: bool = False  # Si True, despliega sin esperar aprobación


class DeployRequest(BaseModel):
    config: dict


# ── Almacenamiento temporal del último config (en memoria) ──────────────
_pending_configs = {}


@router.post("/build-campaign")
async def build_campaign(request: BuildRequest):
    """
    Genera un config de campaña completo desde un prompt en lenguaje natural.

    Ejemplo de prompt:
    "Crea una campaña de delivery para la zona norte de Mérida,
     presupuesto $80/día, enfocada en pad thai y curry verde"

    Retorna el config para revisión. Si auto_deploy=True, despliega directamente.
    """
    from agents.builder import Builder

    builder = Builder()
    result = builder.build_config(request.prompt)

    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)

    config = result["config"]
    validation = result["validation"]

    # Guardar config pendiente para deploy posterior
    import hashlib
    config_id = hashlib.md5(
        f"{config.get('campaign_name', '')}_{request.prompt[:50]}".encode()
    ).hexdigest()[:12]
    _pending_configs[config_id] = config

    response = {
        "status": "config_ready",
        "config_id": config_id,
        "config": config,
        "validation": validation,
        "message": "Revisa el config. Si está correcto, llama POST /deploy-campaign con el config_id."
    }

    # Auto-deploy si se pidió y el config es válido
    if request.auto_deploy and validation.get("valid"):
        receipt = builder.deploy()
        response["status"] = "deployed"
        response["receipt"] = receipt
        response["message"] = "Campaña desplegada en modo PAUSED."

    return response


@router.post("/deploy-campaign")
async def deploy_campaign_endpoint(request: DeployRequest):
    """
    Despliega un config de campaña previamente generado.
    Acepta el config completo directamente.
    """
    from agents.builder import Builder, validate_config

    validation = validate_config(request.config)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail={
            "status": "validation_failed",
            "errors": validation["errors"],
        })

    builder = Builder()
    builder.config = request.config
    builder.validation = validation
    receipt = builder.deploy()

    if receipt.get("status") == "error":
        raise HTTPException(status_code=500, detail=receipt)

    return receipt


@router.get("/pending-configs")
async def get_pending_configs():
    """Lista configs pendientes de deploy."""
    return {
        "count": len(_pending_configs),
        "configs": {k: {"campaign_name": v.get("campaign_name"), "budget": v.get("daily_budget_mxn")}
                    for k, v in _pending_configs.items()}
    }


@router.post("/deploy-pending/{config_id}")
async def deploy_pending(config_id: str):
    """Despliega un config pendiente por su ID."""
    config = _pending_configs.get(config_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config '{config_id}' no encontrado. Usa GET /pending-configs.")

    from agents.builder import Builder, validate_config

    validation = validate_config(config)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail={"errors": validation["errors"]})

    builder = Builder()
    builder.config = config
    builder.validation = validation
    receipt = builder.deploy()

    if receipt.get("status") != "error":
        del _pending_configs[config_id]

    return receipt
