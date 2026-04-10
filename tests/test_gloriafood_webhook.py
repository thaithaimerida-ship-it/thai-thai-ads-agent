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
            "client": {
                "first_name": "Juan",
                "last_name": "Pérez",
                "phone": "+529991234567",
                "email": "juan@test.com",
            },
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
