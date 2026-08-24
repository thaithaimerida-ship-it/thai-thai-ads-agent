"""Tests de la lógica de ventas WooCommerce (engine/woocommerce_sales). Sin red: fixtures."""
from datetime import datetime
from zoneinfo import ZoneInfo

import engine.woocommerce_sales as W

MERIDA = ZoneInfo("America/Merida")


def O(**kw):
    base = {"id": 1, "number": 1, "status": "completed", "total": "100.00",
            "date_created_gmt": "2026-08-14T18:00:00", "payment_method": "cod",
            "shipping_lines": [{"method_id": "flat_rate"}], "created_via": "checkout"}
    base.update(kw)
    return base


def test_semaforo_cortes():
    assert W.semaforo(21) == "🟢" and W.semaforo(30) == "🟢"
    assert W.semaforo(20) == "🟡" and W.semaforo(14) == "🟡"
    assert W.semaforo(13) == "🔴" and W.semaforo(0) == "🔴"


def test_exclusiones():
    assert W._is_excluded(O(id=480))                       # pedido de prueba por id
    assert W._is_excluded(O(id=9, number="483"))           # por number
    assert W._is_excluded(O(total="0", created_via="admin"))   # total 0 no-checkout = basura
    assert not W._is_excluded(O(total="0", created_via="checkout"))  # total 0 pero checkout: no excluir
    assert not W._is_excluded(O(id=500, total="120.00"))   # pedido normal


def test_conversion_zona_horaria_borde():
    # 05:59 GMT del 13 = 23:59 del 12 en Mérida (fuera de la ventana [13,20))
    assert W._merida_dt(O(date_created_gmt="2026-08-13T05:59:00")).date().isoformat() == "2026-08-12"
    # 06:00 GMT del 13 = 00:00 del 13 en Mérida (dentro)
    assert W._merida_dt(O(date_created_gmt="2026-08-13T06:00:00")).date().isoformat() == "2026-08-13"


def test_mapeos():
    assert W._payment_label(O(payment_method="woo-mercado-pago-custom")) == "Tarjeta (Mercado Pago)"
    assert W._payment_label(O(payment_method="woo-mercado-pago-basic")) == "Mercado Pago cuenta"
    assert W._payment_label(O(payment_method="ppcp-gateway")) == "PayPal"
    assert W._payment_label(O(payment_method="raro")) == "Otro (raro)"
    assert W._shipping_label(O(shipping_lines=[])) == "Sin dato"
    assert W._shipping_label(O(shipping_lines=[{"method_id": "local_pickup"}])) == "Recoger"


def test_aggregate_week():
    lo, hi = datetime(2026, 8, 13, tzinfo=MERIDA), datetime(2026, 8, 20, tzinfo=MERIDA)
    orders = [
        O(id=1, status="completed", total="622.00", payment_method="cod",
          shipping_lines=[{"method_id": "flat_rate"}], date_created_gmt="2026-08-14T18:00:00"),
        O(id=2, status="processing", total="500.00", payment_method="ppcp-gateway",
          shipping_lines=[{"method_id": "local_pickup"}], date_created_gmt="2026-08-15T02:00:00"),
        O(id=3, status="pending", total="300.00", date_created_gmt="2026-08-16T18:00:00"),   # no real
        O(id=4, status="cancelled", total="200.00", date_created_gmt="2026-08-16T19:00:00"),  # cancelado
        O(id=480, status="completed", total="999.00", date_created_gmt="2026-08-16T18:00:00"),  # excluido
        O(id=6, status="completed", total="0", created_via="admin", date_created_gmt="2026-08-16T18:00:00"),  # basura
        O(id=7, status="completed", total="10.00", date_created_gmt="2026-08-08T18:00:00"),   # semana previa
    ]
    r = W.aggregate_week(orders, lo, hi)
    assert r["pedidos"] == 2
    assert r["total_mxn"] == 1122.00
    assert r["ticket_mxn"] == 561.00
    assert r["cancelados"] == 1
    assert {b["label"]: b["n"] for b in r["pago"]} == {"Efectivo": 1, "PayPal": 1}
    assert {b["label"]: b["n"] for b in r["tipo"]} == {"Domicilio": 1, "Recoger": 1}


def test_aggregate_week_vacia():
    lo, hi = datetime(2026, 8, 13, tzinfo=MERIDA), datetime(2026, 8, 20, tzinfo=MERIDA)
    r = W.aggregate_week([], lo, hi)
    assert r == {"pedidos": 0, "total_mxn": 0.0, "ticket_mxn": 0.0, "cancelados": 0, "pago": [], "tipo": []}


class _FakeResp:
    def __init__(self, data, pages):
        self._d = data
        self.headers = {"X-WP-TotalPages": str(pages)}

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def test_fetch_orders_paginacion(monkeypatch):
    monkeypatch.setenv("WC_KEY", "ck_test:cs_test")
    paginas = {1: ([{"id": i} for i in range(100)], 2), 2: ([{"id": 100}], 2)}
    calls = {"n": 0}

    def fake_get(url, auth=None, params=None, timeout=None):
        calls["n"] += 1
        assert auth == ("ck_test", "cs_test")   # credencial va en Basic Auth
        data, pages = paginas[params["page"]]
        return _FakeResp(data, pages)

    monkeypatch.setattr(W.requests, "get", fake_get)
    orders = W._fetch_orders("2026-08-05T00:00:00", "2026-08-21T00:00:00")
    assert len(orders) == 101 and calls["n"] == 2   # siguió las 2 páginas


def test_build_weekly_sales_ventana(monkeypatch):
    # 2 reales en la semana actual [13,20), 1 real en la previa [6,13); _fetch_orders mockeado.
    orders = [
        O(id=1, status="completed", total="100.00", date_created_gmt="2026-08-14T18:00:00"),
        O(id=2, status="processing", total="50.00", date_created_gmt="2026-08-18T18:00:00"),
        O(id=3, status="completed", total="30.00", date_created_gmt="2026-08-08T18:00:00"),
    ]
    monkeypatch.setattr(W, "_fetch_orders", lambda a, b: orders)
    r = W.build_weekly_sales(end_merida=datetime(2026, 8, 20, tzinfo=MERIDA))
    assert r["semana_actual"]["pedidos"] == 2 and r["semana_actual"]["total_mxn"] == 150.0
    assert r["semana_previa"] == {"pedidos": 1, "total_mxn": 30.0}
    assert r["semaforo"] == "🔴"                       # 2 < 14
    assert r["rango"] == {"desde": "13/08", "hasta": "19/08"}
