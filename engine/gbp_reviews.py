"""Acceso a reseñas de Google Business Profile (GBP v4) — Fase G.

Lectura (pendientes 5★, respuestas publicadas) y publicación de respuesta (updateReply),
esta última GATED por DRY_RUN_RESENAS (default true → no llama a la API de escritura).
Las credenciales viven en .env (GBP_CLIENT_ID/SECRET/REFRESH_TOKEN). Read-only por defecto.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import requests

# Caché en memoria de la lista de reseñas: evita paginar GBP (~10s, 8 páginas) en cada
# request de la página/borrador. TTL configurable (default 1h). Las publicadas/banco se
# derivan de aquí, así que no se paginan 1,144 reseñas por carga.
_REVIEWS_CACHE: dict[str, Any] = {"ts": 0.0, "reviews": None}


def fetch_reviews_cached(ttl: float = 3600.0, max_pages: int = 8) -> list[dict[str, Any]]:
    now = time.time()
    if _REVIEWS_CACHE["reviews"] is not None and (now - _REVIEWS_CACHE["ts"]) < ttl:
        return _REVIEWS_CACHE["reviews"]
    revs = fetch_reviews(max_pages=max_pages)
    _REVIEWS_CACHE["reviews"] = revs
    _REVIEWS_CACHE["ts"] = now
    return revs

_OAUTH = "https://oauth2.googleapis.com/token"
_BASE = "https://mybusiness.googleapis.com/v4"
_STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def dry_run_activo() -> bool:
    """DRY_RUN_RESENAS=true por default: NO se llama a la API de escritura."""
    return os.getenv("DRY_RUN_RESENAS", "true").strip().lower() != "false"


def _account_location() -> tuple[str, str]:
    acc = os.getenv("GBP_ACCOUNT_ID", "116182531567733744541")
    loc = os.getenv("GBP_LOCATION_ID", "17757029602072738121")
    return acc, loc


def get_access_token() -> str:
    resp = requests.post(_OAUTH, data={
        "client_id": os.environ["GBP_CLIENT_ID"],
        "client_secret": os.environ["GBP_CLIENT_SECRET"],
        "refresh_token": os.environ["GBP_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _reviews_url() -> str:
    acc, loc = _account_location()
    return f"{_BASE}/accounts/{acc}/locations/{loc}/reviews"


# ── Performance (Maps 30 días) — read-only, mismo OAuth que las reseñas ──────────
_PERF_BASE = "https://businessprofileperformance.googleapis.com/v1"
_PERF_METRICS = [
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS", "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS", "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    "BUSINESS_DIRECTION_REQUESTS", "CALL_CLICKS", "WEBSITE_CLICKS",
    "BUSINESS_FOOD_MENU_CLICKS",
]
_PERF_CACHE: dict[str, Any] = {"ts": 0.0, "agg": None}


def fetch_performance_30d(token: str | None = None, end_lag_days: int = 3) -> dict[str, int]:
    """Agregado de las métricas diarias de GBP Performance en una ventana de 30 días
    (read-only). Devuelve {METRIC: total_int}. La API rezaga 3-5 días, así que la ventana
    termina `end_lag_days` atrás. Una sola llamada HTTP (fetchMultiDailyMetricsTimeSeries)."""
    token = token or get_access_token()
    _, loc = _account_location()
    end = date.today() - timedelta(days=end_lag_days)
    start = end - timedelta(days=30)
    params = [("dailyMetrics", m) for m in _PERF_METRICS]
    params += [
        ("dailyRange.start_date.year", str(start.year)),
        ("dailyRange.start_date.month", str(start.month)),
        ("dailyRange.start_date.day", str(start.day)),
        ("dailyRange.end_date.year", str(end.year)),
        ("dailyRange.end_date.month", str(end.month)),
        ("dailyRange.end_date.day", str(end.day)),
    ]
    url = f"{_PERF_BASE}/locations/{loc}:fetchMultiDailyMetricsTimeSeries"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    resp.raise_for_status()
    j = resp.json()
    agg: dict[str, int] = {}
    for ts in j.get("multiDailyMetricTimeSeries", []):
        for dm in ts.get("dailyMetricTimeSeries", []):
            metric = dm.get("dailyMetric")
            total = sum(int(p.get("value", 0)) for p in dm.get("timeSeries", {}).get("datedValues", []))
            if metric:
                agg[metric] = total
    return agg


def fetch_performance_30d_cached(ttl: float = 3600.0) -> dict[str, int]:
    """Igual que fetch_performance_30d pero cacheado en memoria (TTL 1h) — evita re-pegar
    a la API en cargas repetidas del mismo proceso."""
    now = time.time()
    if _PERF_CACHE["agg"] is not None and (now - _PERF_CACHE["ts"]) < ttl:
        return _PERF_CACHE["agg"]
    agg = fetch_performance_30d()
    _PERF_CACHE["agg"] = agg
    _PERF_CACHE["ts"] = now
    return agg


def fetch_reviews(token: str | None = None, max_pages: int = 8) -> list[dict[str, Any]]:
    """Trae reseñas paginando (read-only). El snapshot del auditor solo trae página 1,
    por eso aquí paginamos para ver las respuestas en reseñas más viejas."""
    token = token or get_access_token()
    url = _reviews_url()
    out: list[dict[str, Any]] = []
    page = None
    for _ in range(max_pages):
        params = {"pageSize": 50}
        if page:
            params["pageToken"] = page
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        out.extend(j.get("reviews", []))
        page = j.get("nextPageToken")
        if not page:
            break
    return out


def _limpiar_comentario(review: dict[str, Any]) -> str:
    return (review.get("comment") or "").split("\n\n(Translated by Google)")[0].strip()


def _stars(review: dict[str, Any]) -> int:
    return _STARS.get(review.get("starRating"), 0)


def to_resena(review: dict[str, Any]) -> dict[str, Any]:
    """Normaliza un review GBP al shape que consume el generador/UI."""
    return {
        "review_id": review.get("reviewId") or (review.get("name") or "").split("/")[-1],
        "name": review.get("name"),
        "stars": _stars(review),
        "comment": _limpiar_comentario(review),
        "reviewer": (review.get("reviewer") or {}).get("displayName", ""),
        "create_time": review.get("createTime"),
    }


def pendientes_5_estrellas(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SOLO rating == 5 sin respuesta previa, de más reciente a más antigua. Las ≤4★
    JAMÁS entran."""
    pend = [r for r in reviews if _stars(r) == 5 and not r.get("reviewReply")]
    pend.sort(key=lambda r: r.get("createTime", ""), reverse=True)
    return [to_resena(r) for r in pend]


def respuestas_publicadas(reviews: list[dict[str, Any]], n: int = 15) -> list[str]:
    """Últimas n respuestas publicadas (texto), para la lista de prohibidos del generador."""
    con = [r for r in reviews if r.get("reviewReply")]
    con.sort(key=lambda r: (r["reviewReply"] or {}).get("updateTime", ""), reverse=True)
    return [(r["reviewReply"] or {}).get("comment", "") for r in con[:n]]


def get_review(review_id: str, token: str | None = None) -> dict[str, Any] | None:
    """Re-lee UNA reseña (para re-validar en el momento de publicar)."""
    token = token or get_access_token()
    url = f"{_reviews_url()}/{review_id}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    if r.status_code != 200:
        return None
    return r.json()


def es_publicable(review: dict[str, Any] | None) -> bool:
    """Re-validación server-side: 5★ y sin respuesta previa."""
    return bool(review) and _stars(review) == 5 and not review.get("reviewReply")


def publicar_respuesta(review_id: str, comentario: str, token: str | None = None) -> dict[str, Any]:
    """Publica la respuesta vía updateReply (PUT). GATED por DRY_RUN_RESENAS: si está activo
    (default), NO llama a la API y devuelve dry_run=True."""
    if dry_run_activo():
        return {"status": "dry_run", "dry_run": True, "published": False}
    token = token or get_access_token()
    url = f"{_reviews_url()}/{review_id}/reply"
    r = requests.put(url, headers={"Authorization": f"Bearer {token}"},
                     json={"comment": comentario}, timeout=20)
    r.raise_for_status()
    return {"status": "ok", "dry_run": False, "published": True}
