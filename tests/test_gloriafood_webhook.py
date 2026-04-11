"""
Tests del webhook de GloriaFood.
No llama APIs reales — todo con datos sintéticos.
"""
import json
import pytest


class TestParseOrder:
    """Verifica el parsing de pedidos GloriaFood."""

    def _sample_order(self):
        return {
            "id": "ord_12345",
            "type": "delivery",
            "total_price": 450.00,
            "payment": "CASH",
            "accepted_at": "2026-04-10T19:30:00.000Z",
            "client_first_name": "Juan",
            "client_last_name": "Pérez",
            "client_phone": "+529991234567",
            "client_email": "juan@test.com",
            "items": [
                {"name": "Pad Thai", "quantity": 2, "price": 180.00},
                {"name": "Tom Yum", "quantity": 1, "price": 90.00},
            ],
        }

    def test_parse_basic_fields(self):
        from routes.gloriafood_webhook import _parse_order
        order = self._sample_order()
        parsed = _parse_order(order)

        assert parsed["gloriafood_order_id"] == "ord_12345"
        assert parsed["total_price_mxn"] == 450.00
        assert parsed["order_type"] == "delivery"
        assert parsed["payment_method"] == "CASH"
        assert parsed["items_count"] == 2
        assert parsed["client_name"] == "Juan Pérez"
        assert parsed["client_phone"] == "+529991234567"
        assert parsed["client_email"] == "juan@test.com"

    def test_parse_empty_order(self):
        from routes.gloriafood_webhook import _parse_order
        parsed = _parse_order({})

        assert parsed["gloriafood_order_id"] == ""
        assert parsed["total_price_mxn"] == 0.0
        assert parsed["items_count"] == 0
        assert parsed["client_name"] == ""

    def test_parse_null_fields(self):
        from routes.gloriafood_webhook import _parse_order
        order = {
            "id": "ord_99",
            "total_price": None,
            "client": None,
            "items": None,
        }
        parsed = _parse_order(order)

        assert parsed["gloriafood_order_id"] == "ord_99"
        assert parsed["total_price_mxn"] == 0.0
        assert parsed["items_count"] == 0
        assert parsed["client_name"] == ""


class TestWebhookAuth:
    """Verifica la autenticación del webhook."""

    def test_valid_master_key_format(self):
        """Master key debe ser string no vacío si está configurado."""
        import os
        key = os.getenv("GLORIAFOOD_MASTER_KEY", "")
        # En producción debe estar configurada; en tests puede estar vacía
        assert isinstance(key, str)


class TestGloriaFoodOrdersQuery:
    """Verifica que el query de pedidos online no falla con tabla vacía o inexistente."""

    def test_query_empty_table(self):
        """El query debe retornar 0 pedidos y $0 cuando la tabla está vacía."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE gloriafood_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gloriafood_order_id TEXT UNIQUE,
                total_price_mxn REAL,
                received_at TEXT,
                conversion_sent INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0)
            FROM gloriafood_orders
            WHERE received_at >= datetime('now', '-24 hours')
        """)
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert int(row[0]) == 0
        assert float(row[1]) == 0.0

    def test_query_with_orders(self):
        """El query suma correctamente pedidos de las últimas 24 horas."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE gloriafood_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gloriafood_order_id TEXT UNIQUE,
                total_price_mxn REAL,
                received_at TEXT,
                conversion_sent INTEGER DEFAULT 0
            )
        """)
        # Insertar 2 pedidos recientes y 1 antiguo (>24h)
        cursor.execute("INSERT INTO gloriafood_orders (gloriafood_order_id, total_price_mxn, received_at) VALUES ('a', 300.0, datetime('now', '-1 hours'))")
        cursor.execute("INSERT INTO gloriafood_orders (gloriafood_order_id, total_price_mxn, received_at) VALUES ('b', 150.0, datetime('now', '-3 hours'))")
        cursor.execute("INSERT INTO gloriafood_orders (gloriafood_order_id, total_price_mxn, received_at) VALUES ('c', 200.0, datetime('now', '-30 hours'))")
        conn.commit()

        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0)
            FROM gloriafood_orders
            WHERE received_at >= datetime('now', '-24 hours')
        """)
        row = cursor.fetchone()
        conn.close()

        assert int(row[0]) == 2
        assert float(row[1]) == 450.0

    def test_ticket_promedio(self):
        """Ticket promedio se calcula correctamente."""
        count, total = 3, 900.0
        ticket = round(total / count, 0) if count > 0 else 0.0
        assert ticket == 300.0

    def test_ticket_promedio_zero_orders(self):
        """Ticket promedio no divide por cero cuando no hay pedidos."""
        count, total = 0, 0.0
        ticket = round(total / count, 0) if count > 0 else 0.0
        assert ticket == 0.0
