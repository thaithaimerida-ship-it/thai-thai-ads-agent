"""
Centralized Google Service Account Credentials Loader.
Works in two modes:
1. LOCAL: Reads from ga4-credentials.json file
2. CLOUD RUN: Reads from GOOGLE_CREDENTIALS_JSON env var (JSON string)
"""
import os
import json
import logging
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)
_cached_info: dict | None = None


def _load_service_account_info() -> dict:
    global _cached_info
    if _cached_info is not None:
        return _cached_info
    json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if json_str:
        try:
            _cached_info = json.loads(json_str)
            logger.info("Credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
            return _cached_info
        except json.JSONDecodeError:
            logger.error("GOOGLE_CREDENTIALS_JSON has invalid JSON")
    for env_key in ("GA4_CREDENTIALS_PATH", "GOOGLE_SHEETS_CREDENTIALS_PATH"):
        path = os.getenv(env_key)
        if path and os.path.exists(path):
            with open(path, "r") as f:
                _cached_info = json.load(f)
            logger.info("Credentials loaded from configured file")
            return _cached_info
    default_path = "./ga4-credentials.json"
    if os.path.exists(default_path):
        with open(default_path, "r") as f:
            _cached_info = json.load(f)
        logger.info("Credentials loaded from default credentials path")
        return _cached_info
    return {}


def get_credentials(scopes: list[str]) -> Credentials | None:
    info = _load_service_account_info()
    if not info:
        logger.warning("No service account credentials available")
        return None
    try:
        return Credentials.from_service_account_info(info, scopes=scopes)
    except Exception as e:
        logger.error("Service account auth initialization failed: %s", type(e).__name__)
        return None


def is_available() -> bool:
    return bool(_load_service_account_info())
