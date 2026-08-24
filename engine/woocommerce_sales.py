"""Ventas de la tienda WooCommerce (pedidos.thaithaimerida.com) para el monitor semanal.

Reemplaza el viejo registro interno de GloriaFood. SOLO LECTURA: consulta el endpoint
`wc/v3/orders` con una llave de solo lectura (consumer key/secret) guardada en Secret Manager
y expuesta al contenedor como env var `WC_KEY` (formato "ck:cs"). NUNCA se imprime la
credencial ni datos de clientes (PII): este módulo solo devuelve AGREGADOS.

Definición de venta real (aprobada): status `completed` + `processing`.
Zona horaria: se usa `date_created_gmt` (UTC) y se convierte a America/Merida.
Exclusiones: pedidos de prueba #480-483, y pedidos con total 0 que no vengan de checkout.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

MERIDA = ZoneInfo("America/Merida")
UTC = ZoneInfo("UTC")

BASE_URL = os.getenv("WC_ORDERS_URL", "https://pedidos.thaithaimerida.com/wp-json/wc/v3/orders")
EXCLUDE_ORDER_IDS = {480, 481, 482, 483}
REAL_STATUSES = {"completed", "processing"}
CANCEL_STATUSES = {"cancelled", "refunded"}
META_SEMANA = 21  # meta de 3 pedidos/dia
# Semaforo: verde >=21, amarillo 14-20, rojo <14
SEMAFORO_VERDE, SEMAFORO_AMARILLO = 21, 14

PAYMENT_LABELS = {
    "cod": "Efectivo",
    "woo-mercado-pago-custom": "Tarjeta (Mercado Pago)",
    "woo-mercado-pago-basic": "Mercado Pago cuenta",
    "ppcp-gateway": "PayPal",
}
SHIPPING_LABELS = {"flat_rate": "Domicilio", "local_pickup": "Recoger"}


def _creds() -> tuple[str, str]:
    raw = os.getenv("WC_KEY", "")
    if ":" not in raw:
        raise RuntimeError("WC_KEY no configurada (se espera 'consumer_key:consumer_secret')")
    ck, cs = raw.split(":", 1)
    return ck, cs


def _fetch_orders(after_gmt: str, before_gmt: str) -> list[dict[str, Any]]:
    """GET paginado de /orders entre after y before (ambos en GMT). Solo lectura."""
    ck, cs = _creds()
    orders: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(BASE_URL, auth=(ck, cs), params={
            "per_page": 100, "page": page, "status": "any", "orderby": "date", "order": "asc",
            "dates_are_gmt": "true", "after": after_gmt, "before": before_gmt,
        }, timeout=40)
        resp.raise_for_status()
        batch = resp.json()
        orders.extend(batch)
        total_pages = int(resp.headers.get("X-WP-TotalPages", "1") or "1")
        if page >= total_pages or not batch:
            break
        page += 1
    return orders


def _merida_dt(order: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(order["date_created_gmt"]).replace(tzinfo=UTC).astimezone(MERIDA)


def _is_excluded(order: dict[str, Any]) -> bool:
    """Pedidos de prueba (#480-483) y basura (total 0 sin created_via=checkout)."""
    for key in ("id", "number"):
        try:
            if int(str(order.get(key))) in EXCLUDE_ORDER_IDS:
                return True
        except (ValueError, TypeError):
            pass
    total = float(order.get("total") or 0)
    if total == 0 and (order.get("created_via") or "") != "checkout":
        return True
    return False


def _payment_label(order: dict[str, Any]) -> str:
    slug = order.get("payment_method", "") or ""
    return PAYMENT_LABELS.get(slug, f"Otro ({slug})" if slug else "Otro")


def _shipping_label(order: dict[str, Any]) -> str:
    lines = order.get("shipping_lines") or []
    mid = lines[0].get("method_id", "") if lines else ""
    return SHIPPING_LABELS.get(mid, "Sin dato")


def semaforo(pedidos: int) -> str:
    if pedidos >= SEMAFORO_VERDE:
        return "🟢"
    if pedidos >= SEMAFORO_AMARILLO:
        return "🟡"
    return "🔴"


def aggregate_week(orders: list[dict[str, Any]], lo: datetime, hi: datetime) -> dict[str, Any]:
    """Agrega ventas reales en [lo, hi) (hora Merida). Función PURA (testeable sin red)."""
    reales: list[dict[str, Any]] = []
    cancelados = 0
    for o in orders:
        dt = _merida_dt(o)
        if not (lo <= dt < hi):
            continue
        status = o.get("status")
        if status in CANCEL_STATUSES:
            cancelados += 1
        if _is_excluded(o):
            continue
        if status in REAL_STATUSES:
            reales.append(o)

    n = len(reales)
    total = round(sum(float(o["total"]) for o in reales), 2)
    ticket = round(total / n, 2) if n else 0.0

    def _breakdown(label_fn) -> list[dict[str, Any]]:
        agg: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        for o in reales:
            k = label_fn(o)
            agg[k][0] += 1
            agg[k][1] += float(o["total"])
        return [{"label": k, "n": int(v[0]), "total": round(v[1], 2)}
                for k, v in sorted(agg.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))]

    return {
        "pedidos": n, "total_mxn": total, "ticket_mxn": ticket, "cancelados": cancelados,
        "pago": _breakdown(_payment_label), "tipo": _breakdown(_shipping_label),
    }


def build_weekly_sales(end_merida: datetime | None = None) -> dict[str, Any]:
    """Bloque de ventas para el monitor: últimos 7 días (Merida) + comparativa semana previa.

    `end_merida` = fin exclusivo de la ventana actual (default: medianoche de hoy en Merida).
    Puede lanzar excepción (p. ej. red/credencial) — el llamador la degrada con gracia.
    """
    if end_merida is None:
        now = datetime.now(MERIDA)
        end_merida = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cur_lo, cur_hi = end_merida - timedelta(days=7), end_merida
    prev_lo, prev_hi = end_merida - timedelta(days=14), end_merida - timedelta(days=7)

    after_gmt = prev_lo.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    before_gmt = cur_hi.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    orders = _fetch_orders(after_gmt, before_gmt)

    cur = aggregate_week(orders, cur_lo, cur_hi)
    prev = aggregate_week(orders, prev_lo, prev_hi)
    return {
        "semana_actual": cur,
        "semana_previa": {"pedidos": prev["pedidos"], "total_mxn": prev["total_mxn"]},
        "semaforo": semaforo(cur["pedidos"]),
        "meta_semana": META_SEMANA,
        "rango": {"desde": cur_lo.strftime("%d/%m"), "hasta": (cur_hi - timedelta(days=1)).strftime("%d/%m")},
    }
