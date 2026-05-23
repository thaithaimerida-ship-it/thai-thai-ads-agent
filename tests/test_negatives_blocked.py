"""
Tests (TDD RED primero) para #2/#3: detectar search terms ya bloqueados como
negativos en Google Ads.

Contratos que definen estos tests:
- engine/negative_matcher.py: find_blocking_negative(query, negatives) -> dict|None
  (match-type aware: EXACT/PHRASE/BROAD, normalizado).
- engine.ads_client.fetch_negative_keywords(client, customer_id) -> dict
  {campaign_id: {campaign_name, channel_type, negatives:[{text,match_type,resource_name}]}}
  (READ-ONLY: solo query GAQL a campaign_criterion, no muta).
- /search-terms enriquece cada término con:
    already_negative: bool
    blocked_by: {text, match_type} | None
    negative_smart_uncertain: bool  (already_negative AND campaña Smart)

Alcance: solo negativos a nivel campaña (campaign_criterion). NO cubre listas
compartidas (shared sets) — Thai Thai no usa listas compartidas conocidas.
"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock
import pytest


# ════════════════════════════════════════════════════════════════════════════
# 1. negative_matcher (puro, match-type aware)
# ════════════════════════════════════════════════════════════════════════════
from engine.negative_matcher import find_blocking_negative


def _neg(text, mt):
    return {"text": text, "match_type": mt, "resource_name": "rn/" + text}


class TestNegativeMatcher:
    def test_exact_bloquea_solo_exacto(self):
        negs = [_neg("querreke", "EXACT")]
        assert find_blocking_negative("querreke", negs)["text"] == "querreke"
        assert find_blocking_negative("querreke restaurante", negs) is None

    def test_phrase_bloquea_frase_contigua(self):
        negs = [_neg("comida tailandesa", "PHRASE")]
        assert find_blocking_negative("rica comida tailandesa merida", negs) is not None
        assert find_blocking_negative("comida rica tailandesa", negs) is None   # no contigua
        assert find_blocking_negative("comida", negs) is None

    def test_broad_bloquea_todas_las_palabras_cualquier_orden(self):
        negs = [_neg("receta thai", "BROAD")]
        assert find_blocking_negative("thai receta facil", negs) is not None
        assert find_blocking_negative("receta de curry", negs) is None          # falta 'thai'

    def test_broad_una_palabra(self):
        negs = [_neg("receta", "BROAD")]
        assert find_blocking_negative("receta pad thai", negs) is not None

    def test_normalizacion_acentos_y_mayusculas(self):
        negs = [_neg("Tailandés", "BROAD")]
        assert find_blocking_negative("comida TAILANDES merida", negs) is not None

    def test_devuelve_text_y_match_type(self):
        b = find_blocking_negative("receta pad thai", [_neg("receta", "BROAD")])
        assert b["text"] == "receta" and b["match_type"] == "BROAD"

    def test_sin_match_devuelve_none(self):
        assert find_blocking_negative("comida tailandesa", [_neg("sushi", "BROAD")]) is None

    def test_lista_vacia(self):
        assert find_blocking_negative("lo que sea", []) is None


# ════════════════════════════════════════════════════════════════════════════
# 2. fetch_negative_keywords (mock del cliente Google Ads — READ-ONLY)
# ════════════════════════════════════════════════════════════════════════════
from engine.ads_client import fetch_negative_keywords


class _Enum:
    def __init__(self, name): self.name = name


def _row(cid, cname, channel, kw, mt, rn):
    r = types.SimpleNamespace()
    r.campaign = types.SimpleNamespace(id=cid, name=cname, advertising_channel_type=_Enum(channel))
    cc = types.SimpleNamespace()
    cc.keyword = types.SimpleNamespace(text=kw, match_type=_Enum(mt))
    cc.resource_name = rn
    r.campaign_criterion = cc
    return r


def _client_with(rows):
    client = MagicMock()
    svc = MagicMock()
    svc.search.return_value = iter(rows)
    client.get_service.return_value = svc
    return client


class TestFetchNegatives:
    def test_agrupa_por_campana(self):
        rows = [
            _row(111, "Local", "SMART", "querreke", "BROAD", "rn1"),
            _row(111, "Local", "SMART", "receta", "PHRASE", "rn2"),
            _row(222, "Search", "SEARCH", "sushi", "EXACT", "rn3"),
        ]
        out = fetch_negative_keywords(_client_with(rows), "4021070209")
        assert set(out.keys()) == {"111", "222"}
        assert len(out["111"]["negatives"]) == 2
        assert out["222"]["negatives"][0]["text"] == "sushi"

    def test_incluye_channel_type(self):
        out = fetch_negative_keywords(_client_with([_row(111, "Local", "SMART", "x", "BROAD", "rn")]), "c")
        assert out["111"]["channel_type"] == "SMART"

    def test_campos_del_negativo(self):
        out = fetch_negative_keywords(_client_with([_row(111, "Local", "SMART", "querreke", "BROAD", "rn1")]), "c")
        n = out["111"]["negatives"][0]
        assert n["text"] == "querreke" and n["match_type"] == "BROAD" and n["resource_name"] == "rn1"

    def test_vacio(self):
        assert fetch_negative_keywords(_client_with([]), "c") == {}


# ════════════════════════════════════════════════════════════════════════════
# 3. Enriquecimiento del endpoint /search-terms
# ════════════════════════════════════════════════════════════════════════════
from fastapi.testclient import TestClient


def _setup_endpoint(monkeypatch, terms, negs):
    import routes.analysis as analysis
    engine = {"get_ads_client": lambda: MagicMock(),
              "fetch_search_term_data": MagicMock(return_value=terms)}
    monkeypatch.setattr(analysis, "_get_engine", lambda: engine)
    monkeypatch.setenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    monkeypatch.setattr(analysis, "fetch_negative_keywords", lambda c, cid: negs)


class TestEndpointEnrichment:
    def test_ya_negativo_en_smart_marca_incierto(self, monkeypatch):
        terms = [{"query": "querreke", "campaign_id": "111", "campaign_name": "Local",
                  "cost_micros": 5_000_000, "conversions": 0.0, "clicks": 3, "impressions": 40}]
        negs = {"111": {"campaign_name": "Local", "channel_type": "SMART",
                        "negatives": [{"text": "querreke", "match_type": "BROAD", "resource_name": "rn"}]}}
        _setup_endpoint(monkeypatch, terms, negs)
        from main import app
        t = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS").json()["search_terms"][0]
        assert t["already_negative"] is True
        assert t["blocked_by"]["text"] == "querreke" and t["blocked_by"]["match_type"] == "BROAD"
        assert t["negative_smart_uncertain"] is True

    def test_no_negativo_cuando_no_hay_match(self, monkeypatch):
        terms = [{"query": "comida tailandesa", "campaign_id": "222", "campaign_name": "Search",
                  "cost_micros": 1_000_000, "conversions": 1.0, "clicks": 2, "impressions": 20}]
        _setup_endpoint(monkeypatch, terms, {})
        from main import app
        t = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS").json()["search_terms"][0]
        assert t["already_negative"] is False
        assert t["blocked_by"] is None
        assert t["negative_smart_uncertain"] is False

    def test_search_no_marca_incierto(self, monkeypatch):
        terms = [{"query": "sushi barato", "campaign_id": "222", "campaign_name": "Search",
                  "cost_micros": 2_000_000, "conversions": 0.0, "clicks": 1, "impressions": 10}]
        negs = {"222": {"campaign_name": "Search", "channel_type": "SEARCH",
                        "negatives": [{"text": "sushi", "match_type": "BROAD", "resource_name": "rn"}]}}
        _setup_endpoint(monkeypatch, terms, negs)
        from main import app
        t = TestClient(app).get("/search-terms?date_range=LAST_7_DAYS").json()["search_terms"][0]
        assert t["already_negative"] is True
        assert t["negative_smart_uncertain"] is False   # SEARCH no es incierto
