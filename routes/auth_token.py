"""
Dependencia de autenticacion por token compartido.
Protege endpoints de escritura a Google Ads.

Uso:
    from routes.auth_token import require_token
    @router.post("/algo", dependencies=[Depends(require_token)])
"""
import os
import secrets

from fastapi import Header, HTTPException


def require_token(x_api_token: str = Header(default="")) -> None:
    """
    Valida el header X-API-Token contra la env var ADMIN_API_TOKEN.

    Falla CERRADO: si ADMIN_API_TOKEN no esta seteada en el entorno, o el
    header no coincide exactamente, responde 401. Comparacion en tiempo
    constante para evitar timing attacks.
    """
    expected = os.getenv("ADMIN_API_TOKEN", "")
    if not expected or not secrets.compare_digest(x_api_token, expected):
        raise HTTPException(status_code=401, detail="Token invalido o ausente")
