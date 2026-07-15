"""Acceso a reseñas de Google Business Profile (GBP v4) — Fase G.

Lectura (pendientes 5★, respuestas publicadas) y publicación de respuesta (updateReply),
esta última GATED por DRY_RUN_RESENAS (default true → no llama a la API de escritura).
Las credenciales viven en .env (GBP_CLIENT_ID/SECRET/REFRESH_TOKEN). Read-only por defecto.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta
from typing import Any

import requests

# Caché en memoria del ESCANEO COMPLETO (fuente única). La bandeja, el borrador per-card y el
# correo comparten ESTE escaneo → nunca se paginan las 1,205 dos veces por apertura (mata el
# doble escaneo). El uptime-check /health lo recalienta (warm_reviews_cache) para que la página
# abra en ~1-2s con el escaneo ya fresco. Es en memoria: se pierde en cada reinicio de instancia
# (scale-to-zero) — el primer acceso tras el arranque paga UN escaneo y repobla; nada se corrompe.
_FULL_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
REVIEWS_TTL = 600.0          # 10 min: ventana en que se sirve el escaneo cacheado
REVIEWS_WARM_AFTER = 300.0   # el warmer refresca al pasar de 5 min (antes de que expire el TTL)
# SINGLE-FLIGHT: un solo escaneo de 1,205 en vuelo a la vez. Si dos accesos (p.ej. /health y
# abrir la bandeja) piden el escaneo simultáneamente, UNO escanea y el resto ESPERA su resultado
# (no se re-pagina 1,205 dos/tres veces por concurrencia). Es un Lock de proceso: dentro de una
# instancia basta; entre procesos worker cada uno tiene su propia caché (no comparten memoria).
_scan_lock = threading.Lock()
PENDIENTES_CUTOFF = "2025-01-01"  # regla de negocio: solo se responden 5★ de 2025 en adelante


def fetch_reviews_cached(ttl: float = REVIEWS_TTL) -> list[dict[str, Any]]:
    """Reseñas crudas desde la FUENTE ÚNICA cacheada (fetch_reviews_full). SOLO para la
    generación IA per-card (borrador_para): comparte el MISMO escaneo que la lista y el correo,
    así no se pagina 1,205 dos veces por apertura. `ttl` queda por compat; la frescura la gobierna
    REVIEWS_TTL en fetch_reviews_full. La LISTA de pendientes sale de fetch_reviews_full directo."""
    return fetch_reviews_full()["reviews"]

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


def fetch_reviews_full(token: str | None = None, max_age: float = REVIEWS_TTL) -> dict[str, Any]:
    """FUENTE ÚNICA de verdad. Escaneo COMPLETO (sin tope) de TODAS las reseñas, CACHEADO en
    memoria y con SINGLE-FLIGHT: un solo escaneo de 1,205 en vuelo a la vez (los accesos
    concurrentes esperan su resultado, no re-paginan). Sirve la caché si es más joven que
    `max_age` (default 10 min; el warmer pasa 5 min para refrescar antes de que expire).
    Devuelve dict con:
      reviews         — todas las reseñas crudas
      average_rating  — averageRating de la API TAL CUAL (sin round/cálculo); el correo lo formatea
                        a 1 decimal SOLO al mostrar (para verse "4.7" como el perfil, no 4.6999…)
      total_reviews   — totalReviewCount de la API (~1204); NO se cuenta a mano
      distribucion    — {5..1: int} conteo histórico real por estrella
      pendientes      — 5★ + sin reviewReply + createTime >= 2025-01-01 (normalizadas)
      completo        — True si paginó todo; False si falló a la mitad
    Usada por la bandeja (al abrir), el borrador per-card y el correo (2x/semana): el MISMO
    escaneo, el MISMO conteo de pendientes. Solo se CACHEA un escaneo completo (completo=True):
    un escaneo a medias jamás envenena la caché ni oculta pendientes.
    Fallo a mitad: 'completo'=False; average_rating/total vienen de la página 1 (ya presentes)."""
    now = time.time()
    if _FULL_CACHE["data"] is not None and (now - _FULL_CACHE["ts"]) < max_age:
        return _FULL_CACHE["data"]                       # camino rápido: caché fresca, sin lock
    with _scan_lock:                                     # single-flight: un solo escaneo a la vez
        # Doble-chequeo: otra hebra pudo haber refrescado mientras esperábamos el lock → no re-escanear.
        now = time.time()
        if _FULL_CACHE["data"] is not None and (now - _FULL_CACHE["ts"]) < max_age:
            return _FULL_CACHE["data"]
        token = token or get_access_token()
        url = _reviews_url()
        reviews: list[dict[str, Any]] = []
        page, completo, avg, total = None, True, None, None
        try:
            while True:
                params = {"pageSize": 50}
                if page:
                    params["pageToken"] = page
                resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
                resp.raise_for_status()
                j = resp.json()
                if avg is None:
                    avg, total = j.get("averageRating"), j.get("totalReviewCount")
                reviews.extend(j.get("reviews", []))
                page = j.get("nextPageToken")
                if not page:
                    break
        except Exception as e:  # noqa: BLE001
            completo = False
            print(f"[gbp] fetch_reviews_full incompleto: {e}")
        dist = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for r in reviews:
            s = _stars(r)
            if s in dist:
                dist[s] += 1
        result = {
            "reviews": reviews,
            "average_rating": avg,   # TAL CUAL de la API (sin round/int); se formatea solo al mostrar
            "total_reviews": total,
            "distribucion": dist,
            "pendientes": pendientes_5_estrellas(reviews),
            "completo": completo,
        }
        if completo:                 # nunca cachear un escaneo incompleto (no oculta pendientes)
            _FULL_CACHE["data"] = result
            _FULL_CACHE["ts"] = now
        return result


def invalidate_review_cache(review_id: str) -> None:
    """Tras una publicación REAL, marca esa reseña como respondida en la caché y recomputa los
    pendientes → DESAPARECE de la lista al instante (no espera el TTL de 10 min ni re-escanea).
    Sin esto, la caché podría seguir sirviendo una reseña ya contestada durante 10 min (bug #1 en
    versión chica). No-op si la caché está vacía."""
    data = _FULL_CACHE["data"]
    if not data:
        return
    for r in data["reviews"]:
        rid = r.get("reviewId") or (r.get("name") or "").split("/")[-1]
        if rid == review_id:
            r["reviewReply"] = r.get("reviewReply") or {"comment": "(respondida)"}
    data["pendientes"] = pendientes_5_estrellas(data["reviews"])


def clear_reviews_cache() -> None:
    """Vacía la caché del escaneo completo (el próximo acceso re-escanea). Tests / refresco manual."""
    _FULL_CACHE["data"] = None
    _FULL_CACHE["ts"] = 0.0


def warm_reviews_cache() -> None:
    """Recalienta la caché del escaneo completo si pasa de REVIEWS_WARM_AFTER (5 min), antes de que
    expire el TTL de servicio (10 min). Lo llama el uptime-check /health (~cada 5 min) para que la
    bandeja/correo abran con el escaneo ya fresco (~1-2s en vez de ~34s). Garantías:
    - No-op si faltan credenciales GBP (tests / entorno sin secretos): no toca la red.
    - SINGLE-FLIGHT (el lock vive en fetch_reviews_full): si ya hay un escaneo en vuelo, este
      espera su resultado en vez de lanzar otro → nunca dos escaneos de 1,205 en paralelo.
    - Nunca lanza: si el escaneo falla, la caché previa queda intacta y /health sigue respondiendo."""
    if not os.getenv("GBP_CLIENT_ID"):   # sin credenciales → no intentar red (p.ej. en tests)
        return
    try:
        fetch_reviews_full(max_age=REVIEWS_WARM_AFTER)   # refresca si > 5 min; single-flight compartido
    except Exception as e:  # noqa: BLE001 — caché previa intacta; /health no debe caerse por esto
        print(f"[gbp] warm_reviews_cache falló (se conserva la caché previa): {e}")


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
    """5★ + sin respuesta previa + createTime >= 2025-01-01 (regla de negocio), de más reciente
    a más antigua. Las ≤4★ JAMÁS entran. Sin filtro de texto: las de solo estrellas SÍ entran."""
    pend = [r for r in reviews
            if _stars(r) == 5 and not r.get("reviewReply")
            and (r.get("createTime") or "") >= PENDIENTES_CUTOFF]
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
    (default), NO llama a la API y devuelve dry_run=True. Tras una publicación REAL invalida la
    caché de esa reseña (invalidate_review_cache) → desaparece de la lista al instante, sin esperar
    el TTL: evita reintroducir el bug #1 (lista mostrando una reseña ya contestada). El dry-run NO
    invalida: el simulacro no consume la reseña (sigue siendo un ensayo repetible)."""
    if dry_run_activo():
        return {"status": "dry_run", "dry_run": True, "published": False}
    token = token or get_access_token()
    url = f"{_reviews_url()}/{review_id}/reply"
    r = requests.put(url, headers={"Authorization": f"Bearer {token}"},
                     json={"comment": comentario}, timeout=20)
    r.raise_for_status()
    invalidate_review_cache(review_id)  # publicación REAL → fuera de la lista al instante
    return {"status": "ok", "dry_run": False, "published": True}
