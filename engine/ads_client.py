import os
import sqlite3
import json
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.api_core.exceptions import GoogleAPIError

# Nombres exactos de conversiones reales — NUNCA desactivar
PROTECTED_CONVERSIONS = {
    "Pedido completado Gloria Food",
    "Thai Thai Merida (web) reserva_completada",
    "Thai Thai Merida (web) click_pedir_online",
}
# Substrings de respaldo — si el nombre contiene alguno de estos, también está protegido
PROTECTED_SUBSTRINGS = ["reserva_completada", "click_pedir_online", "pedido completado gloria"]


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
        
        campaign_criterion_service.mutate_campaign_criteria(
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

        customer_operation.update_mask.paths[:] = ["auto_tagging_enabled"]

        customer_service.mutate_customer(
            customer_id=customer_id,
            operation=customer_operation
        )
        return {"status": "success", "customer_id": customer_id}
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

        _remove_existing_geo_criteria(client, customer_id, campaign_id)

        criterion = criterion_operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.location.geo_target_constant = geo_target_service.geo_target_constant_path(location_id)

        criterion_service.mutate_campaign_criteria(
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
    Si no se puede eliminar el criterio existente, lo actualiza en lugar.
    """
    criterion_service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")

    def _build_proximity(op_field):
        op_field.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        op_field.proximity.address.city_name = "Merida"
        op_field.proximity.address.country_code = "MX"
        op_field.proximity.geo_point.longitude_in_micro_degrees = int(lng * 1_000_000)
        op_field.proximity.geo_point.latitude_in_micro_degrees = int(lat * 1_000_000)
        op_field.proximity.radius = radius_km
        op_field.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS

    try:
        _, failed = _remove_existing_geo_criteria(client, customer_id, campaign_id)

        if failed:
            # Remove failed — try in-place update of the existing PROXIMITY criterion
            existing = _fetch_geo_criteria(client, customer_id, campaign_id)
            existing_proximity = [c for c in existing if c["type"] == "PROXIMITY"]
            if existing_proximity:
                update_op = client.get_type("CampaignCriterionOperation")
                upd = update_op.update
                upd.resource_name = existing_proximity[0]["resource_name"]
                upd.proximity.geo_point.longitude_in_micro_degrees = int(lng * 1_000_000)
                upd.proximity.geo_point.latitude_in_micro_degrees = int(lat * 1_000_000)
                upd.proximity.radius = radius_km
                upd.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS
                update_op.update_mask.paths[:] = [
                    "proximity.geo_point.longitude_in_micro_degrees",
                    "proximity.geo_point.latitude_in_micro_degrees",
                    "proximity.radius",
                ]
                criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id, operations=[update_op]
                )
                return {"status": "success", "radius_km": radius_km, "method": "updated_in_place"}

        create_op = client.get_type("CampaignCriterionOperation")
        _build_proximity(create_op.create)
        criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=[create_op]
        )
        return {"status": "success", "radius_km": radius_km}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _fetch_geo_criteria(client, customer_id: str, campaign_id: str) -> list:
    """Retorna lista de dicts con resource_name y tipo para criterios LOCATION/PROXIMITY de la campaña."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign_criterion.resource_name, campaign_criterion.type
        FROM campaign_criterion
        WHERE campaign.id = {campaign_id}
          AND campaign_criterion.type IN ('LOCATION', 'PROXIMITY')
    """
    results = []
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            results.append({
                "resource_name": row.campaign_criterion.resource_name,
                "type": row.campaign_criterion.type.name,
            })
    except Exception:
        pass
    return results


def _remove_existing_geo_criteria(client, customer_id: str, campaign_id: str) -> tuple[list, list]:
    """Elimina criterios LOCATION/PROXIMITY existentes. Retorna (removed, failed)."""
    criterion_service = client.get_service("CampaignCriterionService")
    existing = _fetch_geo_criteria(client, customer_id, campaign_id)
    removed, failed = [], []
    for item in existing:
        rn = item["resource_name"]
        op = client.get_type("CampaignCriterionOperation")
        op.remove = rn
        try:
            criterion_service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
            removed.append(rn)
        except Exception as exc:
            failed.append({"resource_name": rn, "error": str(exc)[:120]})
    return removed, failed


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
                 "protected": row.conversion_action.name in PROTECTED_CONVERSIONS or
                              any(s in row.conversion_action.name.lower() for s in PROTECTED_SUBSTRINGS)}
                for row in response]
    except Exception:
        return []


def disable_conversion_action(client, customer_id: str, conversion_action_id: str, conversion_name: str) -> dict:
    """Desactiva una conversion. RECHAZA si el nombre esta en PROTECTED_CONVERSIONS."""
    if conversion_name in PROTECTED_CONVERSIONS or any(s in conversion_name.lower() for s in PROTECTED_SUBSTRINGS):
        return {"status": "rejected", "reason": f"'{conversion_name}' esta protegida y no puede desactivarse"}
    try:
        ca_service = client.get_service("ConversionActionService")
        ca_operation = client.get_type("ConversionActionOperation")

        ca = ca_operation.update
        ca.resource_name = ca_service.conversion_action_path(customer_id, conversion_action_id)
        ca.status = client.enums.ConversionActionStatusEnum.HIDDEN

        ca_operation.update_mask.paths.append("status")

        ca_service.mutate_conversion_actions(
            customer_id=customer_id,
            operations=[ca_operation]
        )
        return {"status": "success", "conversion_action_id": conversion_action_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── TASK 7 ──────────────────────────────────────────────────────────────────

def create_search_campaign(client, customer_id: str, name: str,
                            budget_micros: int) -> dict:
    """
    Crea campaña Search en 2 pasos:
    1) CampaignBudget, 2) Campaign con Target CPA.
    La campaña se crea en estado PAUSED para revisión antes de activar.
    budget_micros = MXN × 1,000,000
    """
    try:
        # Paso 1: Crear budget
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")

        budget = budget_operation.create
        budget.name = f"Budget - {name} {datetime.now().strftime('%m%d%H%M')}"
        budget.amount_micros = budget_micros
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

        budget_response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        budget_resource = budget_response.results[0].resource_name

        # Paso 2: Crear campaign
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")

        campaign = campaign_operation.create
        campaign.name = name
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        campaign.campaign_budget = budget_resource
        campaign.manual_cpc.enhanced_cpc_enabled = False
        campaign.network_settings.target_google_search = True
        campaign.network_settings.target_search_network = True
        campaign.network_settings.target_content_network = False
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )
        campaign_resource = campaign_response.results[0].resource_name

        return {
            "status": "success",
            "budget_resource": budget_resource,
            "campaign_resource": campaign_resource
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── TASK 8 ──────────────────────────────────────────────────────────────────

def create_ad_group(client, customer_id: str, campaign_resource_name: str,
                    name: str, cpc_bid_micros: int = 20_000_000) -> dict:
    """Crea ad group dentro de una campaña. cpc_bid_micros default = $20 MXN"""
    try:
        ad_group_service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")

        ad_group = operation.create
        ad_group.name = name
        ad_group.campaign = campaign_resource_name
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        ad_group.cpc_bid_micros = cpc_bid_micros

        response = ad_group_service.mutate_ad_groups(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_rsa(client, customer_id: str, ad_group_resource_name: str,
               headlines: list, descriptions: list,
               final_url: str = "https://www.thaithaimerida.com") -> dict:
    """
    Crea Responsive Search Ad.
    Requiere mínimo 3 headlines (max 30 chars cada uno) y 2 descriptions (max 90 chars).
    """
    if len(headlines) < 3 or len(descriptions) < 2:
        return {"status": "error", "message": "RSA requiere mínimo 3 headlines y 2 descriptions"}
    try:
        ad_group_ad_service = client.get_service("AdGroupAdService")
        operation = client.get_type("AdGroupAdOperation")

        ad_group_ad = operation.create
        ad_group_ad.ad_group = ad_group_resource_name
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

        rsa = ad_group_ad.ad.responsive_search_ad
        for text in headlines[:15]:
            asset = client.get_type("AdTextAsset")
            asset.text = text[:30]
            rsa.headlines.append(asset)
        for text in descriptions[:4]:
            asset = client.get_type("AdTextAsset")
            asset.text = text[:90]
            rsa.descriptions.append(asset)

        ad_group_ad.ad.final_urls.append(final_url)

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def add_keyword_to_ad_group(client, customer_id: str, ad_group_resource_name: str,
                             keyword_text: str, match_type: str = "EXACT") -> dict:
    """Agrega keyword a un ad group. match_type: 'EXACT' o 'BROAD'"""
    try:
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")

        criterion = operation.create
        criterion.ad_group = ad_group_resource_name
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match_type)

        ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "keyword": keyword_text, "match_type": match_type}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear_ad_schedules(client, customer_id: str, campaign_id: str) -> int:
    """Elimina todos los criterios AD_SCHEDULE existentes de una campaña. Retorna cantidad eliminada."""
    ga_service = client.get_service("GoogleAdsService")
    criterion_service = client.get_service("CampaignCriterionService")
    query = f"""
        SELECT campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.id = {campaign_id}
          AND campaign_criterion.type = 'AD_SCHEDULE'
    """
    removed = 0
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            op = client.get_type("CampaignCriterionOperation")
            op.remove = row.campaign_criterion.resource_name
            try:
                criterion_service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


# ── TASK 9 ──────────────────────────────────────────────────────────────────

def update_ad_schedule(client, customer_id: str, campaign_id: str,
                       day_of_week: str, start_hour: int, end_hour: int,
                       bid_modifier: float = 0.0) -> dict:
    """
    Configura horario de anuncios para un día/hora específico.
    day_of_week: 'MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY','SUNDAY'
    bid_modifier: 0.0 = normal, 0.20 = +20%, -1.0 = pausar
    IMPORTANTE: start_hour debe ser < end_hour (no puede cruzar medianoche).
    Para pausa nocturna usar dos llamadas: 23-24 y 0-6.
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")

        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.bid_modifier = 1.0 + bid_modifier
        criterion.ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, day_of_week)
        criterion.ad_schedule.start_hour = start_hour
        criterion.ad_schedule.end_hour = end_hour
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO

        criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "day": day_of_week, "hours": f"{start_hour}-{end_hour}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}