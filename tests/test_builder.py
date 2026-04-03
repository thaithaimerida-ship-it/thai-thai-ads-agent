"""
Tests para agents/builder.py — validación de configs y flujo.
NO ejecuta llamadas a Google Ads API ni a Claude (todo mockeado).
"""
import pytest
from agents.builder import validate_config


class TestValidateConfig:
    """Tests de validación del JSON config."""

    def test_valid_config(self):
        config = {
            "campaign_name": "Thai Mérida - Promo Verano",
            "daily_budget_mxn": 80,
            "cpc_bid_mxn": 20,
            "landing_url": "https://www.thaithaimerida.com",
            "geo_targeting": {"lat": 20.9674, "lng": -89.5926, "radius_km": 15},
            "ad_groups": [
                {
                    "name": "Pad Thai Delivery",
                    "headlines": [
                        "Pad Thai a Domicilio",
                        "Pide Pad Thai Ahora",
                        "Thai Thai Delivery",
                        "El Mejor Pad Thai",
                        "Envío en 40 Minutos",
                        "Pad Thai Mérida",
                        "Cocina Thai Auténtica",
                        "Pide en Línea Hoy",
                    ],
                    "descriptions": [
                        "Pad thai artesanal con tamarindo. Pide a domicilio en Mérida.",
                        "Fideos de arroz salteados al wok. Entrega rápida en toda Mérida.",
                        "Cocina tailandesa auténtica. Pide ahora, recibe en 40 min.",
                    ],
                    "keywords": [
                        {"text": "pad thai delivery mérida", "match_type": "PHRASE"},
                        {"text": "comida tailandesa a domicilio", "match_type": "PHRASE"},
                    ],
                }
            ],
            "negative_keywords": ["receta", "chino", "sushi", "gratis", "empleo"],
        }
        result = validate_config(config)
        assert result["valid"] is True

    def test_missing_campaign_name(self):
        config = {"daily_budget_mxn": 50, "ad_groups": []}
        result = validate_config(config)
        assert result["valid"] is False
        assert any("campaign_name" in e for e in result["errors"])

    def test_budget_too_low(self):
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 5,
            "ad_groups": [{"name": "G1", "headlines": ["A","B","C"], "descriptions": ["D","E"], "keywords": [{"text":"k"}]}],
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
        }
        result = validate_config(config)
        assert result["valid"] is False
        assert any("mínimo" in e for e in result["errors"])

    def test_headline_too_long(self):
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 50,
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
            "ad_groups": [{
                "name": "G1",
                "headlines": [
                    "Este headline es demasiado largo y excede los treinta caracteres permitidos",
                    "Otro headline corto",
                    "Tercer headline ok",
                ],
                "descriptions": ["Desc 1 aquí que es válida.", "Desc 2 aquí."],
                "keywords": [{"text": "test"}],
            }],
            "negative_keywords": ["receta"],
        }
        result = validate_config(config)
        assert result["valid"] is False
        assert any("30 chars" in e for e in result["errors"])

    def test_description_too_long(self):
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 50,
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
            "ad_groups": [{
                "name": "G1",
                "headlines": ["H1 corto", "H2 corto", "H3 corto"],
                "descriptions": [
                    "A" * 91,  # 91 chars — excede 90
                    "Descripción válida.",
                ],
                "keywords": [{"text": "test"}],
            }],
            "negative_keywords": ["receta"],
        }
        result = validate_config(config)
        assert result["valid"] is False
        assert any("90 chars" in e for e in result["errors"])

    def test_no_ad_groups(self):
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 50,
            "ad_groups": [],
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
        }
        result = validate_config(config)
        assert result["valid"] is False
        assert any("al menos 1 ad group" in e for e in result["errors"])

    def test_no_keywords_in_ad_group(self):
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 50,
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
            "ad_groups": [{
                "name": "G1",
                "headlines": ["H1", "H2", "H3"],
                "descriptions": ["D1", "D2"],
                "keywords": [],
            }],
            "negative_keywords": ["receta"],
        }
        result = validate_config(config)
        assert result["valid"] is False
        assert any("al menos 1 keyword" in e for e in result["errors"])

    def test_warning_no_negative_keywords(self):
        """Sin negativas genera ADVERTENCIA pero sigue siendo válido."""
        config = {
            "campaign_name": "Test",
            "daily_budget_mxn": 50,
            "geo_targeting": {"lat": 20.97, "lng": -89.59, "radius_km": 10},
            "ad_groups": [{
                "name": "G1",
                "headlines": ["H1", "H2", "H3"],
                "descriptions": ["D1", "D2"],
                "keywords": [{"text": "test"}],
            }],
        }
        result = validate_config(config)
        assert result["valid"] is True  # Advertencia, no error
        assert any("ADVERTENCIA" in e for e in result["errors"])
