def normalize_google_ads_data(campaigns, keywords, search_terms):
    """
    Normaliza los datos crudos de Google Ads al schema que espera /analyze.
    """
    
    # Estructura base
    normalized = {
        "account_name": "Cuenta Conectada via API",
        "date_range": {
            "label": "last_7_days",
            "start": "",
            "end": ""
        },
        "historical_data_available": False,
        "campaign_data": campaigns,
        "keyword_data": keywords,
        "search_term_data": search_terms,
        "ad_data": [] # No implementado en esta fase
    }
    
    return normalized