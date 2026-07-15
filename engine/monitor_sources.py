"""Read-only source adapters for the Monitor digest context.

This module parses already-fetched payloads into the small `context` shape that
`monitor_sections` consumes, and makes a few READ-ONLY API calls (PageSpeed, Search
Console, GBP live). It NEVER writes anything. When a source is missing, malformed or
its API fails it returns a `data_broken=true` marker so the renderer shows "en
reparación" instead of zeros pretending to be data.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from engine import reservas_sheets

LANDING_URL = "https://www.thaithaimerida.com/"
_PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
# Search Console: URL-prefix property (the domain property is UNVERIFIED — do not use it).
SC_SITE_URL = os.getenv("SEARCH_CONSOLE_SITE_URL", "https://thaithaimerida.com/")
_SC_BASE = "https://searchconsole.googleapis.com/webmasters/v3/sites/"

GBP_AUDIT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "gbp_audit_output.json",
)

_STAR_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_reservas_persist_status() -> dict[str, Any]:
    """Estado de incidentes de reservas — marcas durables en GCS. READ-ONLY, no toca reservas.
    Dos señales independientes:
      persist_failures: reservas que NO se guardaron en Sheets (están en el correo del dueño).
      unconfirmed: reservas guardadas pero SIN confirmación al cliente (hay que contactarlas) —
                   se incluye nombre/teléfono/fecha/hora para poder actuar sin ir al Sheet.
    """
    out: dict[str, Any] = {
        "checked": True,
        "persist_failures": {"count": 0, "ids": []},
        "unconfirmed": {"count": 0, "items": []},
        "posible_duplicado": {"count": 0, "items": []},
    }
    try:
        fails = reservas_sheets.read_persist_failures()
        out["persist_failures"] = {"count": len(fails), "ids": [f.get("id") for f in fails]}
    except Exception as e:  # noqa: BLE001
        print(f"[reservas_persist_status] persist_failures error: {e}")
        out["checked"] = False
    try:
        unconf = reservas_sheets.read_unconfirmed()
        items = []
        for u in unconf:
            d = u.get("data") or {}
            items.append({
                "nombre": d.get("name", ""),
                "telefono": d.get("phone", ""),
                "fecha": d.get("date", ""),
                "hora": d.get("time", ""),
            })
        out["unconfirmed"] = {"count": len(unconf), "items": items}
    except Exception as e:  # noqa: BLE001
        print(f"[reservas_persist_status] unconfirmed error: {e}")
        out["checked"] = False
    try:
        dups = reservas_sheets.read_posible_duplicados()
        items = []
        for u in dups:
            d = u.get("data") or {}
            items.append({
                "nombre_nuevo": u.get("nombre_nuevo", ""),
                "nombres_existentes": u.get("nombres_existentes", []),
                "fecha": d.get("date", ""),
                "hora": d.get("time", ""),
            })
        out["posible_duplicado"] = {"count": len(dups), "items": items}
    except Exception as e:  # noqa: BLE001
        print(f"[reservas_persist_status] posible_duplicado error: {e}")
        out["checked"] = False
    return out


def build_gbp_context(audit: dict[str, Any]) -> dict[str, Any]:
    """Map a GBP audit payload into {gbp, reviews} context slices.

    delta_pct is left None: a single 30-day snapshot has no reliable prior period
    (and its trailing days lag 3-5 days, so any within-window proxy is misleading).
    A real month-over-month delta needs a stored prior-period aggregate — pass it
    via `context['gbp']['metricas'][m]['delta_pct']` once that is wired.
    """
    aggregate = audit.get("performance_aggregate_30d") or {}

    if not aggregate:
        gbp = {"data_broken": True}
    else:
        def metric(key: str) -> dict[str, Any]:
            return {"valor": int(round(_num(aggregate.get(key)))), "delta_pct": None}

        gbp = {
            "data_broken": False,
            "periodo_dias": 30,
            "metricas": {
                "vistas_maps": metric("BUSINESS_IMPRESSIONS_MOBILE_MAPS"),
                "rutas": metric("BUSINESS_DIRECTION_REQUESTS"),
                "clics_menu": metric("BUSINESS_FOOD_MENU_CLICKS"),
                "llamadas": metric("CALL_CLICKS"),
                "clics_web": metric("WEBSITE_CLICKS"),
                "vistas_busqueda_movil": metric("BUSINESS_IMPRESSIONS_MOBILE_SEARCH"),
                "vistas_maps_desktop": metric("BUSINESS_IMPRESSIONS_DESKTOP_MAPS"),
                "vistas_busqueda_desktop": metric("BUSINESS_IMPRESSIONS_DESKTOP_SEARCH"),
            },
        }

    review_data = (audit.get("reviews") or {}).get("data") or {}
    reviews_raw = review_data.get("reviews")
    if not isinstance(reviews_raw, list):
        reviews = {"data_broken": True}
    else:
        # stats = salida de fetch_reviews_full (rating/total/distribución/pendientes/completo).
        # FUENTE ÚNICA: los pendientes del correo salen de aquí, igual que la bandeja.
        reviews = {"data_broken": False, "reviews": _normalize_reviews(reviews_raw),
                   "stats": review_data.get("stats")}

    return {"gbp": gbp, "reviews": reviews}


def _normalize_reviews(reviews_raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in reviews_raw:
        comment = r.get("comment") or ""
        # GBP appends an English machine translation after a marker; keep the original.
        comment = comment.split("\n\n(Translated by Google)")[0].strip()
        out.append({
            "stars": _STAR_MAP.get(r.get("starRating"), 0),
            "comment": comment,
            "create_time": r.get("createTime") or "",
            "has_reply": bool(r.get("reviewReply")),
            "reviewer": (r.get("reviewer") or {}).get("displayName") or "",
        })
    return out


def _fetch_pagespeed(url: str, strategy: str, timeout: int = 60) -> dict[str, Any] | None:
    """Read-only PageSpeed Insights call. Returns perf/lcp/cls/seo/a11y or None."""
    params = [("url", url), ("strategy", strategy),
              ("category", "performance"), ("category", "seo"), ("category", "accessibility")]
    key = os.getenv("PAGESPEED_API_KEY")
    if key:
        params.append(("key", key))
    query = urllib.parse.urlencode(params, doseq=True)
    request_url = f"{_PSI_ENDPOINT}?{query}"
    # Host is the fixed PageSpeed endpoint; only query params vary. Guard makes that explicit.
    if not request_url.startswith("https://www.googleapis.com/"):
        return None
    try:
        with urllib.request.urlopen(request_url, timeout=timeout) as resp:  # nosemgrep: dynamic-urllib-use-detected
            data = json.load(resp)
    except Exception:
        return None
    lh = data.get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    audits = lh.get("audits") or {}

    def _cat(name: str) -> int:
        score = (cats.get(name) or {}).get("score")
        return int(round(_num(score) * 100)) if score is not None else 0

    lcp = _num((audits.get("largest-contentful-paint") or {}).get("numericValue")) / 1000.0
    cls = _num((audits.get("cumulative-layout-shift") or {}).get("numericValue"))
    return {
        "perf": _cat("performance"),
        "seo": _cat("seo"),
        "accesibilidad": _cat("accessibility"),
        "lcp_s": round(lcp, 1),
        "cls": round(cls, 2),
    }


def _web_vitals_score(lcp_s: float, cls: float) -> int:
    lcp_score = 100 if lcp_s < 2.5 else (60 if lcp_s < 4 else 25)
    cls_score = 100 if cls < 0.1 else (60 if cls < 0.25 else 25)
    return int(round((lcp_score + cls_score) / 2))


def build_seo_context(url: str = LANDING_URL) -> dict[str, Any]:
    """F-2: real SEO via PageSpeed (mobile + desktop) + on-page checks. Read-only."""
    movil = _fetch_pagespeed(url, "mobile")
    escritorio = _fetch_pagespeed(url, "desktop")
    if not movil and not escritorio:
        return {"seo": {"data_broken": True}}
    movil = movil or escritorio
    escritorio = escritorio or movil

    on_page_score = 100
    checks = "10/10"
    try:
        from engine.landing_page_auditor import audit_landing_page_code
        audit = audit_landing_page_code() or {}
        on_page_score = int(_num(audit.get("score", 100)))
        issues = len(audit.get("issues", []) or [])
        checks = f"{max(0, 10 - issues)}/10"
    except Exception:
        pass

    web_vitals = _web_vitals_score(movil.get("lcp_s", 0), movil.get("cls", 0))
    componentes = {
        "performance": movil.get("perf", 0),
        "seo_tecnico": movil.get("seo", 0),
        "on_page": on_page_score,
        "web_vitals": web_vitals,
        "accesibilidad": movil.get("accesibilidad", 0),
    }
    score = int(round(sum(componentes.values()) / len(componentes)))
    worst = min(componentes, key=componentes.get)
    oportunidad = {
        "performance": "Mejorar la velocidad en móvil (comprimir imágenes y diferir JS).",
        "web_vitals": "Estabilizar la carga (reservar espacio para imágenes, reducir LCP).",
        "on_page": "Completar metadatos y encabezados de la página.",
        "seo_tecnico": "Revisar etiquetas SEO técnicas (títulos, descripciones, canonical).",
        "accesibilidad": "Mejorar contraste y etiquetas de accesibilidad.",
    }.get(worst, "Mantener el desempeño actual de la web.")

    return {"seo": {
        "data_broken": False,
        "score": score,
        "componentes": componentes,
        "movil": {"perf": movil.get("perf", 0), "lcp_s": movil.get("lcp_s", 0), "cls": movil.get("cls", 0)},
        "escritorio": {"perf": escritorio.get("perf", 0), "lcp_s": escritorio.get("lcp_s", 0), "cls": escritorio.get("cls", 0)},
        "checks_onpage": checks,
        "oportunidad_principal": oportunidad,
    }}


def _sc_post(url: str, body: dict[str, Any], token: str, timeout: int = 30) -> dict[str, Any]:
    if not url.startswith(_SC_BASE):
        raise ValueError("unexpected Search Console host")
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep: dynamic-urllib-use-detected
        return json.load(resp)


def build_search_console_context(site_url: str = SC_SITE_URL, days: int = 7, lag_days: int = 3) -> dict[str, Any]:
    """F-2/B6: real Search Console (Search Analytics) for the URL-prefix property.

    Read-only. Returns data_broken=True (never zeros) if the API errors or the
    property returns no rows. Search Console data lags ~2-3 days → window ends `lag_days` ago.
    """
    from datetime import datetime, timedelta
    try:
        from engine.credentials import get_credentials
        import google.auth.transport.requests
        creds = get_credentials(["https://www.googleapis.com/auth/webmasters.readonly"])
        if creds is None:
            return {"search_console": {"data_broken": True}}
        creds.refresh(google.auth.transport.requests.Request())
        token = creds.token
        end = (datetime.utcnow() - timedelta(days=lag_days)).strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=lag_days + days)).strftime("%Y-%m-%d")
        endpoint = _SC_BASE + urllib.parse.quote(site_url, safe="") + "/searchAnalytics/query"

        totals = _sc_post(endpoint, {"startDate": start, "endDate": end}, token)
        rows = totals.get("rows") or []
        if not rows:
            return {"search_console": {"data_broken": True}}
        t = rows[0]
        topq = _sc_post(endpoint, {"startDate": start, "endDate": end,
                                   "dimensions": ["query"], "rowLimit": 10}, token)
        top_queries = [
            {"query": (r.get("keys") or ["?"])[0], "clics": int(_num(r.get("clicks")))}
            for r in (topq.get("rows") or [])[:3]
        ]
        return {"search_console": {
            "data_broken": False,
            "dias": days,
            "start_date": start,
            "end_date": end,
            "impresiones": int(_num(t.get("impressions"))),
            "clics": int(_num(t.get("clicks"))),
            "ctr": round(_num(t.get("ctr")) * 100, 2),
            "posicion_promedio": round(_num(t.get("position")), 1),
            "top_queries": top_queries,
        }}
    except Exception:
        return {"search_console": {"data_broken": True}}


def load_gloriafood_internal(db_path: str | None = None, days: int = 7) -> dict[str, Any] | None:
    """Read-only internal order register from the webhook's SQLite table.

    This is the restaurant's OWN record of GloriaFood orders (count + amount),
    NOT a Google Ads attributed conversion. Returns None if the table is absent.
    """
    import sqlite3
    try:
        if db_path is None:
            from engine.db_sync import get_db_path
            db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gloriafood_orders'")
        if not cur.fetchone():
            conn.close()
            return None
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0) FROM gloriafood_orders "
            "WHERE received_at >= datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        n, total = cur.fetchone()
        conn.close()
        return {
            "pedidos_7d": int(n or 0),
            "monto_mxn_7d": round(float(total or 0), 2),
            "fuente": "registro interno (DB webhook)",
        }
    except Exception:
        return None


def load_gbp_context(path: str = GBP_AUDIT_PATH) -> dict[str, Any]:
    """Load the local GBP audit snapshot. Returns data_broken slices on failure.

    DEPRECADO para el monitor (el archivo es gitignored → ausente en Cloud Run). Se conserva
    para auditorías manuales con `_gbp_audit.py`. El monitor usa `load_gbp_context_live()`.
    """
    try:
        with open(path, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception:
        return {"gbp": {"data_broken": True}, "reviews": {"data_broken": True}}
    return build_gbp_context(audit)


def load_gbp_context_live() -> dict[str, Any]:
    """Contexto GBP EN VIVO para el monitor (read-only): reseñas por el mismo path que la
    bandeja (`fetch_reviews_cached`) + Maps 30d por la Performance API. Cada slice degrada
    de forma INDEPENDIENTE a data_broken: si una API falla, esa sección sale "en reparación"
    pero el correo se envía igual (jamás un correo a medias por una sección caída)."""
    from engine import gbp_reviews

    audit: dict[str, Any] = {}
    try:
        audit["performance_aggregate_30d"] = gbp_reviews.fetch_performance_30d_cached()
    except Exception:
        audit["performance_aggregate_30d"] = {}  # build_gbp_context → gbp data_broken
    try:
        full = gbp_reviews.fetch_reviews_full()  # FUENTE ÚNICA (escaneo completo, sin caché, 2x/sem)
        audit["reviews"] = {"data": {"reviews": full["reviews"], "stats": full}}
    except Exception:
        audit["reviews"] = {}  # build_gbp_context → reviews data_broken
    return build_gbp_context(audit)
