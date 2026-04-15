"""
Keyword Planner — Google Ads API
Consulta volúmenes de búsqueda, CPC estimado y competencia para keywords.
Usado por el Builder para validar y enriquecer keywords antes de deployar.
"""
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def get_keyword_ideas(
    keywords: List[str],
    location_id: str = "1010043",  # Mérida, Yucatán, México
    language_id: str = "1003",     # Español
    page_size: int = 50,
) -> List[Dict]:
    """
    Consulta Google Ads Keyword Planner para obtener ideas de keywords
    con volúmenes de búsqueda, CPC estimado y nivel de competencia.

    Args:
        keywords: Lista de keywords semilla (ej: ["pad thai mérida", "comida tailandesa"])
        location_id: Geo target de Google Ads (1010043 = Mérida, Yucatán)
        language_id: Idioma (1003 = español)
        page_size: Máximo de resultados

    Returns:
        Lista de dicts con: keyword, avg_monthly_searches, competition,
        competition_index, low_bid_micros, high_bid_micros, low_bid_mxn, high_bid_mxn
    """
    from engine.ads_client import get_ads_client

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")

    try:
        client = get_ads_client()
        keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")
        ads_service = client.get_service("GoogleAdsService")

        request = client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = customer_id
        request.language = ads_service.language_constant_path(language_id)
        request.geo_target_constants.append(
            ads_service.geo_target_constant_path(location_id)
        )
        request.include_adult_keywords = False
        request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
        request.page_size = page_size

        request.keyword_seed.keywords.extend(keywords[:20])  # API limit: max 20 seeds

        response = keyword_plan_idea_service.generate_keyword_ideas(request=request)

        results = []
        for idea in response:
            metrics = idea.keyword_idea_metrics
            results.append({
                "keyword": idea.text,
                "avg_monthly_searches": metrics.avg_monthly_searches or 0,
                "competition": metrics.competition.name if metrics.competition else "UNSPECIFIED",
                "competition_index": metrics.competition_index or 0,
                "low_bid_micros": metrics.low_top_of_page_bid_micros or 0,
                "high_bid_micros": metrics.high_top_of_page_bid_micros or 0,
                "low_bid_mxn": round((metrics.low_top_of_page_bid_micros or 0) / 1_000_000, 2),
                "high_bid_mxn": round((metrics.high_top_of_page_bid_micros or 0) / 1_000_000, 2),
            })

        results.sort(key=lambda x: x["avg_monthly_searches"], reverse=True)
        logger.info("KeywordPlanner: %d ideas para %d semillas", len(results), len(keywords))
        return results

    except Exception as e:
        logger.error("KeywordPlanner.get_keyword_ideas error: %s", e)
        return []


def enrich_keywords_with_data(
    keywords: List[Dict],
    location_id: str = "1010043",
    language_id: str = "1003",
) -> List[Dict]:
    """
    Toma una lista de keywords del Builder (con text y match_type)
    y les agrega datos del Keyword Planner (volumen, CPC, competencia).

    Args:
        keywords: Lista de {"text": "keyword", "match_type": "PHRASE"}

    Returns:
        La misma lista con campos adicionales. Si la API falla, retorna
        los keywords originales con campos en 0 (graceful degradation).
    """
    if not keywords:
        return keywords

    seed_texts = [kw["text"] if isinstance(kw, dict) else kw for kw in keywords]
    ideas = get_keyword_ideas(seed_texts, location_id, language_id)
    ideas_map = {idea["keyword"].lower(): idea for idea in ideas}

    enriched = []
    for kw in keywords:
        text = kw["text"] if isinstance(kw, dict) else kw
        match_type = kw.get("match_type", "PHRASE") if isinstance(kw, dict) else "PHRASE"
        planner_data = ideas_map.get(text.lower(), {})
        enriched.append({
            "text": text,
            "match_type": match_type,
            "avg_monthly_searches": planner_data.get("avg_monthly_searches", 0),
            "competition": planner_data.get("competition", "UNKNOWN"),
            "competition_index": planner_data.get("competition_index", 0),
            "estimated_cpc_low": planner_data.get("low_bid_mxn", 0),
            "estimated_cpc_high": planner_data.get("high_bid_mxn", 0),
        })

    return enriched


def suggest_additional_keywords(
    seed_keywords: List[str],
    min_searches: int = 50,
    max_results: int = 20,
    location_id: str = "1010043",
    language_id: str = "1003",
) -> List[Dict]:
    """
    A partir de keywords semilla, sugiere keywords adicionales que
    el Builder no habría generado, con volumen mínimo de búsqueda.
    """
    ideas = get_keyword_ideas(seed_keywords, location_id, language_id, page_size=100)

    seed_lower = {s.lower() for s in seed_keywords}
    suggestions = [
        idea for idea in ideas
        if idea["keyword"].lower() not in seed_lower
        and idea["avg_monthly_searches"] >= min_searches
    ]

    return suggestions[:max_results]
