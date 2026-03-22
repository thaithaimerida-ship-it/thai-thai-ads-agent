import os
import sqlite3
import json
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.api_core.exceptions import GoogleAPIError

PROTECTED_CONVERSIONS = {"reserva_completada", "pedido_completado_gloria_food", "click_pedir_online"}


def get_date_range(days: int = 30):
    """Retorna fechas en formato YYYY-MM-DD para filtrar queries."""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_ads_client() -> GoogleAdsClient:
    """
    Inicializa y retorna el cliente de Google Ads.
    Intenta primero google-ads.yaml, luego variables de entorno.
    """
    # Intentar cargar desde google-ads.yaml primero
    yaml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "google-ads.yaml")
    if os.path.exists(yaml_path):
        try:
            return GoogleAdsClient.load_from_storage(yaml_path)
        except Exception as e:
            print(f"⚠️ No se pudo cargar yaml: {e}, intentando env vars...")

    # Fallback: variables de entorno
    credentials = {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "use_proto_plus": True
    }

    if os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        credentials["login_customer_id"] = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

    try:
        return GoogleAdsClient.load_from_dict(credentials)
    except Exception as e:
        print(f"❌ Error creando cliente: {e}")
        raise

def fetch_campaign_data(client: GoogleAdsClient, customer_id: str, days: int = 30):
    """
    Obtiene datos de campañas de los últimos N días.
    """
    ga_service = client.get_service("GoogleAdsService")
    start_date, end_date = get_date_range(days)

    query = f"""
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
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
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

def fetch_keyword_data(client: GoogleAdsClient, customer_id: str, days: int = 30):
    """
    Obtiene datos de keywords de los últimos N días.
    """
    ga_service = client.get_service("GoogleAdsService")
    start_date, end_date = get_date_range(days)

    query = f"""
        SELECT
          ad_group_criterion.keyword.text,
          campaign.id,
          campaign.name,
          metrics.cost_micros,
          metrics.conversions,
          metrics.clicks,
          metrics.impressions
        FROM keyword_view
        WHERE campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
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

def fetch_search_term_data(client: GoogleAdsClient, customer_id: str, days: int = 30):
    """
    Obtiene datos de search terms de los últimos N días.
    """
    ga_service = client.get_service("GoogleAdsService")
    start_date, end_date = get_date_range(days)

    query = f"""
        SELECT
          search_term_view.search_term,
          campaign.id,
          campaign.name,
          metrics.cost_micros,
          metrics.conversions,
          metrics.clicks,
          metrics.impressions
        FROM search_term_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        search_terms = []
        for row in response:
            search_terms.append({
                "query": row.search_term_view.search_term,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions
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


# ── TASK 3 ──────────────────────────────────────────────────────────────────

def log_agent_action(action_type: str, target: str, details_before: dict,
                     details_after: dict, status: str, google_ads_response: dict = None,
                     db_path: str = "thai_thai_memory.db"):
    """Registra toda acción ejecutada en Google Ads en el audit log."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO agent_actions (timestamp, action_type, target, details_before, details_after, status, google_ads_response)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        action_type,
        target,
        json.dumps(details_before, ensure_ascii=False),
        json.dumps(details_after, ensure_ascii=False),
        status,
        json.dumps(google_ads_response, ensure_ascii=False) if google_ads_response else None
    ))
    conn.commit()
    conn.close()


def enable_auto_tagging(client, customer_id: str) -> dict:
    """Activa auto-tagging en la cuenta para que GA4 atribuya clics correctamente."""
    try:
        customer_service = client.get_service("CustomerService")
        customer_operation = client.get_type("CustomerOperation")

        customer = customer_operation.update
        customer.resource_name = customer_service.customer_path(customer_id)
        customer.auto_tagging_enabled = True

        field_mask = client.get_type("FieldMask")
        field_mask.paths.append("auto_tagging_enabled")
        customer_operation.update_mask.CopyFrom(field_mask)

        response = customer_service.mutate_customer(
            customer_id=customer_id,
            operation=customer_operation
        )
        return {"status": "success", "resource_name": response.resource_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── TASK 4 ──────────────────────────────────────────────────────────────────

def update_campaign_name(client, customer_id: str, campaign_id: str, new_name: str) -> dict:
    """Renombra una campaña existente."""
    try:
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")

        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        campaign.name = new_name

        campaign_operation.update_mask.paths.append("name")

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_campaign_budget(client, customer_id: str, budget_resource_name: str, budget_micros: int) -> dict:
    """Actualiza el presupuesto diario de una campaña. budget_micros = MXN x 1,000,000"""
    try:
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")

        budget = budget_operation.update
        budget.resource_name = budget_resource_name
        budget.amount_micros = budget_micros

        budget_operation.update_mask.paths.append("amount_micros")

        response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── TASK 5 ──────────────────────────────────────────────────────────────────

def update_campaign_location(client, customer_id: str, campaign_id: str, location_id: str) -> dict:
    """Restringe campaña a una ciudad/region por location_id (criterion type: LOCATION).
    Merida, Yucatan location_id: '1010182'
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        criterion_operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")
        geo_target_service = client.get_service("GeoTargetConstantService")

        criterion = criterion_operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.location.geo_target_constant = geo_target_service.geo_target_constant_path(location_id)

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[criterion_operation]
        )
        return {"status": "success", "location_id": location_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_campaign_proximity(client, customer_id: str, campaign_id: str,
                               lat: float, lng: float, radius_km: float) -> dict:
    """Restringe campaña por radio desde coordenadas (criterion type: PROXIMITY).
    Centro Merida: lat=20.9674, lng=-89.5926
    Delivery: radius_km=8, Reservaciones: radius_km=30
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        criterion_operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")

        criterion = criterion_operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.proximity.address.city_name = "Merida"
        criterion.proximity.address.country_code = "MX"
        criterion.proximity.geo_point.longitude_in_micro_degrees = int(lng * 1_000_000)
        criterion.proximity.geo_point.latitude_in_micro_degrees = int(lat * 1_000_000)
        criterion.proximity.radius = radius_km
        criterion.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[criterion_operation]
        )
        return {"status": "success", "radius_km": radius_km}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── TASK 6 ──────────────────────────────────────────────────────────────────

def fetch_conversion_actions(client, customer_id: str) -> list:
    """Lista todas las conversiones activas con sus IDs y nombres."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT conversion_action.id, conversion_action.name, conversion_action.status
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        return [{"id": str(row.conversion_action.id),
                 "name": row.conversion_action.name,
                 "status": row.conversion_action.status.name,
                 "protected": row.conversion_action.name in PROTECTED_CONVERSIONS}
                for row in response]
    except Exception as e:
        return []


def disable_conversion_action(client, customer_id: str, conversion_action_id: str, conversion_name: str) -> dict:
    """Desactiva una conversion. RECHAZA si el nombre esta en PROTECTED_CONVERSIONS."""
    if conversion_name in PROTECTED_CONVERSIONS:
        return {"status": "rejected", "reason": f"'{conversion_name}' esta protegida y no puede desactivarse"}
    try:
        ca_service = client.get_service("ConversionActionService")
        ca_operation = client.get_type("ConversionActionOperation")

        ca = ca_operation.update
        ca.resource_name = ca_service.conversion_action_path(customer_id, conversion_action_id)
        ca.status = client.enums.ConversionActionStatusEnum.HIDDEN

        ca_operation.update_mask.paths.append("status")

        response = ca_service.mutate_conversion_actions(
            customer_id=customer_id,
            operations=[ca_operation]
        )
        return {"status": "success", "conversion_action_id": conversion_action_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}