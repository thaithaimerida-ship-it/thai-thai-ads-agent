"""El bloque '🛒 Ventas de la tienda' (WooCommerce) reemplaza al de GloriaFood en el correo."""
from engine.monitor_digest_v3 import build_monitor_digest
from routes.monitor import _degraded_search_terms_payload

VENTAS = {
    "semana_actual": {"pedidos": 6, "total_mxn": 3734.0, "ticket_mxn": 622.33, "cancelados": 0,
                      "pago": [{"label": "Efectivo", "n": 5, "total": 3266.0},
                               {"label": "PayPal", "n": 1, "total": 468.0}],
                      "tipo": [{"label": "Domicilio", "n": 4, "total": 2283.0},
                               {"label": "Recoger", "n": 2, "total": 1451.0}]},
    "semana_previa": {"pedidos": 4, "total_mxn": 3632.0},
    "semaforo": "🔴", "meta_semana": 21, "rango": {"desde": "13/08", "hasta": "19/08"},
}


def _ctx(ventas):
    return {
        "mode": "monday",
        "links": {"ads": "x", "bloqueos": "x", "resenas": "x", "revision": "x", "token": "t", "bloqueo_base": "x"},
        "gbp": {"data_broken": True}, "reviews": {"data_broken": True}, "seo": {"data_broken": True},
        "search_console": {"data_broken": True}, "reservas": {"data_broken": True, "items": []},
        "reservas_persist": {"checked": False, "persist_failures": {"count": 0, "ids": []},
                             "unconfirmed": {"count": 0, "items": []}},
        "generated_date": "lunes 24 de agosto de 2026", "ventas_woocommerce": ventas,
    }


def _render(ventas):
    return build_monitor_digest(_degraded_search_terms_payload("LAST_7_DAYS"), _ctx(ventas))


def test_bloque_ventas_presente():
    d = _render(VENTAS)
    h = d["html_email"]
    assert "🛒 Ventas de la tienda" in h
    assert "6 pedidos" in h and "🔴" in h
    assert "ticket" in h.lower()
    assert "Efectivo 5" in h and "PayPal 1" in h
    assert "Domicilio 4" in h and "Recoger 2" in h
    assert "vs. semana previa: 4 pedidos" in h
    # jubilado: ya no debe mencionar GloriaFood
    assert "GloriaFood" not in h and "gloriafood" not in h.lower()
    # en texto plano tambien
    assert "Ventas de la tienda" in d["text_email"]


def test_bloque_cancelados_solo_si_hay():
    d0 = _render(VENTAS)
    assert "Cancelados" not in d0["html_email"]                 # cancelados=0 -> no aparece
    v2 = {**VENTAS, "semana_actual": {**VENTAS["semana_actual"], "cancelados": 2}}
    d1 = _render(v2)
    assert "Cancelados/reembolsados: 2" in d1["html_email"]


def test_bloque_data_broken():
    d = _render({"data_broken": True})
    assert "no disponible" in d["html_email"]
    assert d["status"] == "success"          # no rompe el correo


def test_sin_ventas_no_bloque():
    d = _render(None)
    assert "🛒 Ventas de la tienda" not in d["html_email"]
    assert "GloriaFood" not in d["html_email"]
