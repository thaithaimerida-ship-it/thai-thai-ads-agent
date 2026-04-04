"""
Routes de Keyword Planner — consulta volúmenes y sugiere keywords.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter(tags=["keywords"])


class KeywordResearchRequest(BaseModel):
    keywords: List[str]
    location_id: str = "1010043"  # Mérida, Yucatán
    language_id: str = "1003"     # Español
    min_searches: int = 50
    max_suggestions: int = 20


@router.post("/keyword-research")
async def keyword_research(request: KeywordResearchRequest):
    """
    Consulta Google Ads Keyword Planner y retorna:
    1. Datos de las keywords proporcionadas (volumen, CPC, competencia)
    2. Keywords adicionales sugeridas con volumen > min_searches

    Ejemplo:
    POST /keyword-research
    {"keywords": ["pad thai mérida", "comida tailandesa delivery"]}

    Nota: requiere Developer Token con acceso Basic o Standard.
    Si el token es Test, retorna listas vacías (no rompe el flujo).
    """
    from engine.keyword_planner import get_keyword_ideas, suggest_additional_keywords

    keyword_data = get_keyword_ideas(
        request.keywords,
        location_id=request.location_id,
        language_id=request.language_id,
    )

    suggestions = suggest_additional_keywords(
        request.keywords,
        min_searches=request.min_searches,
        max_results=request.max_suggestions,
        location_id=request.location_id,
        language_id=request.language_id,
    )

    return {
        "status": "success",
        "seed_keywords": len(request.keywords),
        "keyword_data": keyword_data,
        "suggestions": suggestions,
        "total_results": len(keyword_data) + len(suggestions),
    }
