import os
from google.ads.googleads.client import GoogleAdsClient
from google.api_core.exceptions import GoogleAPIError

def get_ads_client() -> GoogleAdsClient:
    """
    Inicializa y retorna el cliente de Google Ads usando variables de entorno.
    """
    credentials = {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
        "use_proto_plus": True
    }
    
    if os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        credentials["login_customer_id"] = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    
    try:
        return GoogleAdsClient.load_from_dict(credentials)
    except Exception as e:
        print(f"❌ Error creando cliente: {e}")
        raise

def fetch_campaign_data(client: GoogleAdsClient, customer_id: str):
    """
    Obtiene datos de campañas
    """
    ga_service = client.get_service("GoogleAdsService")
    
    query = """
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.cost_micros,
          metrics.conversions,
          metrics.clicks,
          metrics.impressions
        FROM campaign
        WHERE campaign.status = 'ENABLED'
    """
    
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []
        for row in response:
            campaigns.append({
                "id": row.campaign.id,
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions
            })
        return campaigns
    except GoogleAPIError as e:
        print(f"Error fetching campaigns: {e}")
        return []

def fetch_keyword_data(client: GoogleAdsClient, customer_id: str):
    """
    Obtiene datos de keywords
    """
    ga_service = client.get_service("GoogleAdsService")
    
    query = """
        SELECT
          ad_group_criterion.keyword.text,
          campaign.id,
          campaign.name,
          metrics.cost_micros,
          metrics.conversions,
          metrics.clicks
        FROM keyword_view
        WHERE campaign.status = 'ENABLED'
    """
    
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        keywords = []
        for row in response:
            keywords.append({
                "text": row.ad_group_criterion.keyword.text,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "clicks": row.metrics.clicks
            })
        return keywords
    except GoogleAPIError as e:
        print(f"Error fetching keywords: {e}")
        return []

def fetch_search_term_data(client: GoogleAdsClient, customer_id: str):
    """
    Obtiene datos de search terms
    """
    ga_service = client.get_service("GoogleAdsService")
    
    query = """
        SELECT
          segments.search_term_match_type,
          segments.keyword.info.text,
          metrics.cost_micros,
          metrics.conversions
        FROM search_term_view
    """
    
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        search_terms = []
        for row in response:
            search_terms.append({
                "search_term": row.segments.keyword.info.text if hasattr(row.segments.keyword, 'info') else "",
                "match_type": row.segments.search_term_match_type.name,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions
            })
        return search_terms
    except GoogleAPIError as e:
        print(f"Error fetching search terms: {e}")
        return []

def add_negative_keyword(client: GoogleAdsClient, customer_id: str, campaign_id: str, keyword_text: str):
    """
    Agrega negative keyword a una campaña
    """
    try:
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_criterion_operation = client.get_type("CampaignCriterionOperation")
        
        campaign_criterion = campaign_criterion_operation.create
        campaign_criterion.campaign = client.get_service("CampaignService").campaign_path(customer_id, campaign_id)
        campaign_criterion.negative = True
        campaign_criterion.keyword.text = keyword_text
        campaign_criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD
        
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[campaign_criterion_operation]
        )
        
        return {"status": "success", "keyword": keyword_text}
    except GoogleAPIError as e:
        print(f"Error adding negative keyword: {e}")
        return {"status": "error", "message": str(e)}