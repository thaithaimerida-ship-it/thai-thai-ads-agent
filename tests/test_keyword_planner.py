"""
Tests para engine/keyword_planner.py - solo validaciones de estructura.
NO llama a Google Ads API (requiere credenciales reales).
Usa monkeypatch para simular respuesta vacia de la API.
"""
import pytest


class TestKeywordPlannerStructure:
    """Verifica que las funciones existen y tienen la firma correcta."""

    def test_imports(self):
        from engine.keyword_planner import (
            get_keyword_ideas,
            enrich_keywords_with_data,
            suggest_additional_keywords,
        )
        assert callable(get_keyword_ideas)
        assert callable(enrich_keywords_with_data)
        assert callable(suggest_additional_keywords)

    def test_enrich_empty_list(self):
        from engine.keyword_planner import enrich_keywords_with_data
        result = enrich_keywords_with_data([])
        assert result == []

    def test_enrich_preserves_structure(self, monkeypatch):
        """Sin API real, enrich debe retornar los keywords con campos extra en 0."""
        import engine.keyword_planner as kp
        monkeypatch.setattr(kp, "get_keyword_ideas", lambda *a, **kw: [])
        from engine.keyword_planner import enrich_keywords_with_data
        input_kws = [{"text": "pad thai merida", "match_type": "PHRASE"}]
        result = enrich_keywords_with_data(input_kws)
        assert len(result) == 1
        assert result[0]["text"] == "pad thai merida"
        assert result[0]["match_type"] == "PHRASE"
        assert "avg_monthly_searches" in result[0]
        assert result[0]["avg_monthly_searches"] == 0
        assert "competition" in result[0]
        assert result[0]["competition"] == "UNKNOWN"
        assert "estimated_cpc_low" in result[0]
        assert "estimated_cpc_high" in result[0]

    def test_enrich_string_keywords(self, monkeypatch):
        """Acepta lista de strings ademas de dicts."""
        import engine.keyword_planner as kp
        monkeypatch.setattr(kp, "get_keyword_ideas", lambda *a, **kw: [])
        from engine.keyword_planner import enrich_keywords_with_data
        result = enrich_keywords_with_data(["comida tailandesa"])
        assert len(result) == 1
        assert result[0]["text"] == "comida tailandesa"
        assert result[0]["match_type"] == "PHRASE"

    def test_suggest_returns_list(self, monkeypatch):
        """suggest_additional_keywords retorna lista (vacia si API no disponible)."""
        import engine.keyword_planner as kp
        monkeypatch.setattr(kp, "get_keyword_ideas", lambda *a, **kw: [])
        from engine.keyword_planner import suggest_additional_keywords
        result = suggest_additional_keywords(["pad thai"])
        assert isinstance(result, list)
        assert result == []
