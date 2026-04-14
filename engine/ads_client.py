import os
import sqlite3
import json
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.api_core.exceptions import GoogleAPIError

# Conversiones activas — NUNCA desactivar
PROTECTED_CONVERSIONS = {
    "reserva_completada_directa",
    "Pedido GloriaFood Online",
}
PROTECTED_SUBSTRINGS = ["reserva_completada_directa", "gloriafood online"]


def get_date_range(days: int = 30):
    """Retorna fechas en formato YYYY-MM-DD para filtrar queries."""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_ads_client() -> GoogleAdsClient:
    """
    Inicializa y retorna el cliente de Google Ads.
    Prioridad: env vars (siempre disponibles en Cloud Run) → yaml (solo local).

    El yaml en la imagen Docker puede tener un refresh token expirado; las env vars
    son la fuente canónica de credenciales en producción.
    """
    # Prioridad 1: env vars (producción — Cloud Run)
    _refresh = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
    _client_id = os.getenv("GOOGLE_ADS_CLIENT_ID")
    _client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    _dev_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")

    if _refresh and _client_id and _client_secret and _dev_token:
        credentials = {
            "developer_token": _dev_token,
            "client_id":       _client_id,
            "client_secret":   _client_secret,
            "refresh_token":   _refresh,
            "use_proto_plus":  True,
        }
        _login_cid = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        if _login_cid:
            credentials["login_customer_id"] = _login_cid
        try:
            return GoogleAdsClient.load_from_dict(credentials)
        except Exception as e:
            print(f"⚠️ Error con env vars: {e}, intentando yaml...")

    # Prioridad 2: google-ads.yaml (desarrollo local)
    yaml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "google-ads.yaml")
    if os.path.exists(yaml_path):
        try:
            return GoogleAdsClient.load_from_storage(yaml_path)
        except Exception as e:
            print(f"❌ No se pudo cargar yaml: {e}")
            raise

    raise RuntimeError("No hay credenciales de Google Ads disponibles (env vars ni yaml)")

def fetch_campaign_metrics_range(
    client: GoogleAdsClient,
    customer_id: str,
    start_date: str,
    end_date: str,
) -> list:
    """
    Obtiene métricas agregadas por campaña para un rango de fechas exacto.

    Usado por Fase 3A para comparación semana actual vs semana anterior.
    start_date / end_date en formato 'YYYY-MM-DD'.

    Retorna lista de dicts: {id, name, clicks, conversions, cost_mxn, cvr}
    """
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          metrics.clicks,
          metrics.conversions,
          metrics.cost_micros
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []
        for row in response:
            clicks = row.metrics.clicks
            conversions = row.metrics.conversions
            campaigns.append({
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "clicks": clicks,
                "conversions": conversions,
                "cost_mxn": round(row.metrics.cost_micros / 1_000_000, 2),
                "cvr": (conversions / clicks) if clicks > 0 else 0.0,
            })
        return campaigns
    except GoogleAPIError as e:
        print(f"Error fetching campaign metrics range ({start_date}→{end_date}): {e}")
        return []


def fetch_adgroup_metrics(
    client: GoogleAdsClient,
    customer_id: str,
    start_date: str,
    end_date: str,
) -> list:
    """
    Obtiene métricas agregadas por ad group para un rango de fechas exacto.

    Usado por Fase 4 para detectar grupos con gasto sin conversiones.
    start_date / end_date en formato 'YYYY-MM-DD'.

    Retorna lista de dicts: {
        adgroup_id, adgroup_name, campaign_id, campaign_name,
        status, clicks, conversions, cost_mxn, impressions
    }
    Solo incluye ad groups con status ENABLED en campañas ENABLED.
    """
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          ad_group.id,
          ad_group.name,
          ad_group.status,
          campaign.id,
          campaign.name,
          metrics.clicks,
          metrics.conversions,
          metrics.cost_micros,
          metrics.impressions
        FROM ad_group
        WHERE campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        adgroups = []
        for row in response:
            adgroups.append({
                "adgroup_id": str(row.ad_group.id),
                "adgroup_name": row.ad_group.name,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "status": row.ad_group.status.name,
                "clicks": row.metrics.clicks,
                "conversions": row.metrics.conversions,
                "cost_mxn": round(row.metrics.cost_micros / 1_000_000, 2),
                "impressions": row.metrics.impressions,
            })
        return adgroups
    except GoogleAPIError as e:
        print(f"Error fetching adgroup metrics ({start_date}→{end_date}): {e}")
        return []


def verify_adgroup_still_pausable(
    client: GoogleAdsClient,
    customer_id: str,
    adgroup_id: str,
    campaign_id: str,
) -> dict:
    """
    Verifica si un ad group sigue siendo pausable antes de ejecutar la mutación.

    Guardas de seguridad:
      G1 — el ad group sigue en estado ENABLED
      G2 — NO es el único ad group ENABLED en su campaña (evitar dejar campaña sin grupos)

    Retorna dict con:
      ok                           : bool — True si ambas guardas pasan
      reason                       : str  — causa del bloqueo (vacío si ok=True)
      guard                        : str  — código de guarda activada ('G1', 'G2', o '')
      verify_checked_at            : str  — ISO timestamp de la verificación (UTC)
      ad_group_status              : str  — estado actual del ad group
      enabled_adgroups_in_campaign : int  — cantidad de ad groups ENABLED en campaña
    """
    from datetime import datetime as _dt
    verify_checked_at = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    base = {
        "ok": False,
        "reason": "",
        "guard": "",
        "verify_checked_at": verify_checked_at,
        "ad_group_status": "UNKNOWN",
        "enabled_adgroups_in_campaign": 0,
    }

    try:
        ga_service = client.get_service("GoogleAdsService")

        # G1 — estado actual del ad group específico
        q1 = f"""
            SELECT ad_group.id, ad_group.status
            FROM ad_group
            WHERE ad_group.id = {adgroup_id}
        """
        rows1 = list(ga_service.search(customer_id=customer_id, query=q1))
        if not rows1:
            base["reason"] = "ad group no encontrado en la API"
            base["guard"] = "G1"
            return base

        ad_group_status = rows1[0].ad_group.status.name
        base["ad_group_status"] = ad_group_status

        if ad_group_status != "ENABLED":
            base["reason"] = f"ad group ya no está ENABLED (status={ad_group_status})"
            base["guard"] = "G1"
            return base

        # G2 — cuántos ad groups ENABLED tiene la campaña
        q2 = f"""
            SELECT ad_group.id
            FROM ad_group
            WHERE campaign.id = {campaign_id}
              AND ad_group.status = 'ENABLED'
        """
        rows2 = list(ga_service.search(customer_id=customer_id, query=q2))
        enabled_count = len(rows2)
        base["enabled_adgroups_in_campaign"] = enabled_count

        if enabled_count <= 1:
            base["reason"] = (
                f"es el único ad group ENABLED en la campaña "
                f"({enabled_count} ENABLED) — pausarlo dejaría la campaña sin grupos activos"
            )
            base["guard"] = "G2"
            return base

        base["ok"] = True
        return base

    except GoogleAPIError as e:
        base["reason"] = f"error de API al verificar: {str(e)[:120]}"
        base["guard"] = "G1"
        return base


def verify_budget_still_actionable(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    budget_at_proposal_mxn: float,
    suggested_budget_mxn: float,
) -> dict:
    """
    Verifica si el presupuesto de una campaña sigue siendo candidato a reducción.
    Se ejecuta justo antes de la mutación — siempre re-fetcha estado fresco de la API.

    Guardas de seguridad:
      G_campaign — la campaña sigue en estado ENABLED
      G_shared   — el presupuesto NO está marcado como explícitamente compartido
                   (explicitly_shared=True indica que múltiples campañas lo usan)
      G_drift    — el presupuesto actual no fue ya reducido >10% manualmente
                   respecto al presupuesto registrado en la propuesta
      G_direction— el presupuesto sugerido es menor que el actual
                   (BA1 solo reduce, nunca sube)
      G_min      — el presupuesto sugerido >= BUDGET_CHANGE_MIN_DAILY_MXN ($20 MXN)
      G_max_cut  — la reducción no supera BUDGET_CHANGE_MAX_REDUCTION_PCT (60%)

    Retorna dict con:
      ok                      : bool — True si todas las guardas pasan
      reason                  : str  — causa del bloqueo (vacío si ok=True)
      guard                   : str  — código de guarda activada ('' si ok=True)
      verify_checked_at       : str  — ISO timestamp UTC de la verificación
      current_budget_mxn      : float — presupuesto actual re-fetched
      budget_at_proposal_mxn  : float — presupuesto al momento de crear la propuesta
      suggested_budget_mxn    : float — presupuesto propuesto
      reduction_pct_actual    : float — reducción real vs presupuesto actual
      campaign_status         : str  — estado de la campaña al verificar
      budget_explicitly_shared: bool — si el presupuesto es compartido
    """
    from datetime import datetime as _dt
    from config.agent_config import (
        BUDGET_CHANGE_MIN_DAILY_MXN,
        BUDGET_CHANGE_MAX_REDUCTION_PCT,
        BUDGET_CHANGE_DRIFT_TOLERANCE_PCT,
    )
    verify_checked_at = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    base = {
        "ok": False,
        "reason": "",
        "guard": "",
        "verify_checked_at": verify_checked_at,
        "current_budget_mxn": 0.0,
        "budget_at_proposal_mxn": budget_at_proposal_mxn,
        "suggested_budget_mxn": suggested_budget_mxn,
        "reduction_pct_actual": 0.0,
        "campaign_status": "UNKNOWN",
        "budget_explicitly_shared": False,
    }

    try:
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
              campaign.id,
              campaign.status,
              campaign_budget.amount_micros,
              campaign_budget.explicitly_shared
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        rows = list(ga_service.search(customer_id=customer_id, query=query))
        if not rows:
            base["reason"] = "campaña no encontrada en la API"
            base["guard"] = "G_campaign"
            return base

        row = rows[0]
        campaign_status = row.campaign.status.name
        current_micros = row.campaign_budget.amount_micros
        explicitly_shared = bool(row.campaign_budget.explicitly_shared)
        current_budget_mxn = round(current_micros / 1_000_000, 2)

        base["campaign_status"] = campaign_status
        base["budget_explicitly_shared"] = explicitly_shared
        base["current_budget_mxn"] = current_budget_mxn

        # G_campaign: campaña sigue ENABLED
        if campaign_status != "ENABLED":
            base["reason"] = (
                f"la campaña ya no está ENABLED (status={campaign_status}) — "
                "no se modifica presupuesto de campaña inactiva"
            )
            base["guard"] = "G_campaign"
            return base

        # G_shared: presupuesto no es explícitamente compartido
        if explicitly_shared:
            base["reason"] = (
                "el presupuesto está marcado como explícitamente compartido "
                "(explicitly_shared=True) — modificarlo afectaría otras campañas"
            )
            base["guard"] = "G_shared"
            return base

        # G_drift: detectar si el operador ya redujo el presupuesto manualmente
        if budget_at_proposal_mxn > 0:
            drift = (budget_at_proposal_mxn - current_budget_mxn) / budget_at_proposal_mxn
            if drift > BUDGET_CHANGE_DRIFT_TOLERANCE_PCT:
                base["reason"] = (
                    f"el presupuesto ya fue reducido manualmente: "
                    f"${budget_at_proposal_mxn:.2f} → ${current_budget_mxn:.2f} MXN/día "
                    f"(caída {drift*100:.1f}% > tolerancia {BUDGET_CHANGE_DRIFT_TOLERANCE_PCT*100:.0f}%) — "
                    "se evita doble corte"
                )
                base["guard"] = "G_drift"
                return base

        # G_direction: solo reducimos presupuesto
        if suggested_budget_mxn >= current_budget_mxn:
            base["reason"] = (
                f"el presupuesto sugerido ${suggested_budget_mxn:.2f} >= actual ${current_budget_mxn:.2f} — "
                "BA1 solo propone reducciones, no aumentos"
            )
            base["guard"] = "G_direction"
            return base

        # G_min: piso absoluto
        if suggested_budget_mxn < BUDGET_CHANGE_MIN_DAILY_MXN:
            base["reason"] = (
                f"el presupuesto sugerido ${suggested_budget_mxn:.2f} MXN/día < "
                f"mínimo permitido ${BUDGET_CHANGE_MIN_DAILY_MXN:.2f} MXN/día"
            )
            base["guard"] = "G_min"
            return base

        # G_max_cut: reducción máxima en una sola ejecución
        reduction_pct = (current_budget_mxn - suggested_budget_mxn) / current_budget_mxn * 100.0
        base["reduction_pct_actual"] = round(reduction_pct, 1)
        if reduction_pct > BUDGET_CHANGE_MAX_REDUCTION_PCT:
            base["reason"] = (
                f"la reducción ({reduction_pct:.1f}%) supera el máximo permitido "
                f"en una sola ejecución ({BUDGET_CHANGE_MAX_REDUCTION_PCT:.0f}%)"
            )
            base["guard"] = "G_max_cut"
            return base

        base["ok"] = True
        return base

    except GoogleAPIError as e:
        base["reason"] = f"error de API al verificar: {str(e)[:120]}"
        base["guard"] = "G_campaign"
        return base


def pause_ad_group(
    client: GoogleAdsClient,
    customer_id: str,
    ad_group_id: str,
) -> dict:
    """
    Pausa un ad group vía Google Ads API (AdGroupService.mutate_ad_groups).

    Solo cambia el campo `status` — no toca ningún otro atributo.

    Retorna dict con:
      status        : 'success' o 'error'
      resource_name : resource_name retornado por la API (si ok)
      message       : descripción del error (si falla)
    """
    try:
        ad_group_service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")

        ag = operation.update
        ag.resource_name = ad_group_service.ad_group_path(customer_id, ad_group_id)
        ag.status = client.enums.AdGroupStatusEnum.PAUSED

        operation.update_mask.paths[:] = ["status"]

        response = ad_group_service.mutate_ad_groups(
            customer_id=customer_id,
            operations=[operation]
        )
        return {
            "status": "success",
            "resource_name": response.results[0].resource_name,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def fetch_campaign_data(client: GoogleAdsClient, customer_id: str, date_range: str = "YESTERDAY"):
    """
    Obtiene datos de campañas para el rango de fechas indicado.
    date_range acepta cualquier literal GAQL válido: YESTERDAY, LAST_7_DAYS,
    LAST_14_DAYS, LAST_30_DAYS, etc.
    Nota: campaign.start_date fue removido del SELECT — UNRECOGNIZED_FIELD en API v23 (google-ads==30).
    days_active queda como None hasta resolver compatibilidad de versión.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign_budget.resource_name,
          campaign_budget.amount_micros,
          campaign_budget.explicitly_shared,
          metrics.cost_micros,
          metrics.conversions,
          metrics.clicks,
          metrics.impressions
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date DURING {date_range}
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []
        for row in response:
            campaigns.append({
                "id": row.campaign.id,
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "start_date": None,
                "days_active": None,
                "budget_resource_name": row.campaign_budget.resource_name,
                "daily_budget_mxn": round(row.campaign_budget.amount_micros / 1_000_000, 2),
                "budget_explicitly_shared": bool(row.campaign_budget.explicitly_shared),
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions,
            })
        return campaigns
    except GoogleAPIError as e:
        print(f"Error fetching campaigns: {e}")
        return []

def fetch_keyword_data(client: GoogleAdsClient, customer_id: str, date_range: str = "YESTERDAY"):
    """
    Obtiene datos de keywords para el rango de fechas indicado.
    """
    ga_service = client.get_service("GoogleAdsService")

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
          AND segments.date DURING {date_range}
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
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions,
            })
        return keywords
    except GoogleAPIError as e:
        print(f"Error fetching keywords: {e}")
        return []

def fetch_search_ad_groups(client: GoogleAdsClient, customer_id: str) -> list:
    """
    Retorna ad groups activos de campañas Search (SEARCH channel) con su resource_name.
    Usado por el Keyword Decision Engine para saber dónde agregar keywords.

    Retorna lista de dicts:
        adgroup_id, adgroup_name, adgroup_resource, campaign_id, campaign_name
    """
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT
          ad_group.id,
          ad_group.name,
          ad_group.resource_name,
          campaign.id,
          campaign.name,
          campaign.advertising_channel_type
        FROM ad_group
        WHERE campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND campaign.advertising_channel_type = 'SEARCH'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        ad_groups = []
        for row in response:
            ad_groups.append({
                "adgroup_id":       str(row.ad_group.id),
                "adgroup_name":     row.ad_group.name,
                "adgroup_resource": row.ad_group.resource_name,
                "campaign_id":      str(row.campaign.id),
                "campaign_name":    row.campaign.name,
            })
        return ad_groups
    except Exception as e:
        print(f"fetch_search_ad_groups error: {e}")
        return []


def fetch_search_term_data(client: GoogleAdsClient, customer_id: str, date_range: str = "YESTERDAY"):
    """
    Obtiene datos de search terms para el rango de fechas indicado.
    """
    ga_service = client.get_service("GoogleAdsService")

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
        WHERE segments.date DURING {date_range}
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
                     details_after: dict, status: str = "executed",
                     google_ads_response: dict = None, db_path: str = None,
                     **kwargs):
    """Registra toda acción ejecutada en Google Ads en el audit log."""
    if db_path is None:
        from engine.db_sync import get_db_path
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT,
            details_before TEXT,
            details_after TEXT,
            status TEXT NOT NULL,
            google_ads_response TEXT
        )
    """)
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


def fetch_campaign_budget_info(client, customer_id: str, campaign_id: str) -> dict:
    """
    Fetches the budget resource name and current daily amount for a campaign.
    Returns: {budget_resource_name, current_daily_budget_mxn}
    """
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.campaign_budget,
          campaign_budget.amount_micros,
          campaign_budget.resource_name
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            return {
                "budget_resource_name": row.campaign_budget.resource_name,
                "current_daily_budget_mxn": round(row.campaign_budget.amount_micros / 1_000_000, 2),
            }
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Campaign not found"}


def separate_and_assign_budget(
    client, customer_id: str, campaign_id: str, budget_micros: int, campaign_name: str = ""
) -> dict:
    """
    Separa una campaña de su presupuesto compartido creando un presupuesto individual.

    Pasos:
      1. Crear un nuevo CampaignBudget individual (explicitly_shared=False) con budget_micros.
      2. Asignar ese nuevo presupuesto a la campaña vía CampaignOperation.

    Returns:
        {"status": "success", "new_budget_resource": str, "campaign_resource": str}
        {"status": "error", "message": str}
    """
    import time as _time
    try:
        budget_service   = client.get_service("CampaignBudgetService")
        campaign_service = client.get_service("CampaignService")

        # ── Paso 1: crear presupuesto individual ─────────────────────────────
        budget_op     = client.get_type("CampaignBudgetOperation")
        new_budget    = budget_op.create
        # Nombre único para evitar DUPLICATE_NAME
        new_budget.name             = f"Individual_{campaign_name or campaign_id}_{int(_time.time())}"
        new_budget.amount_micros    = budget_micros
        new_budget.delivery_method  = client.enums.BudgetDeliveryMethodEnum.STANDARD
        new_budget.explicitly_shared = False

        budget_response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_op]
        )
        new_budget_resource = budget_response.results[0].resource_name

        # ── Paso 2: vincular campaña al nuevo presupuesto ────────────────────
        campaign_op   = client.get_type("CampaignOperation")
        campaign      = campaign_op.update
        campaign.resource_name  = f"customers/{customer_id}/campaigns/{campaign_id}"
        campaign.campaign_budget = new_budget_resource
        campaign_op.update_mask.paths[:] = ["campaign_budget"]

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_op]
        )
        return {
            "status":               "success",
            "new_budget_resource":  new_budget_resource,
            "campaign_resource":    campaign_response.results[0].resource_name,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def add_smart_campaign_theme(client, customer_id: str, campaign_id: str, theme_text: str) -> dict:
    """
    Agrega un keyword theme libre a una Smart Campaign via CampaignCriterionService.

    Args:
        campaign_id:  ID numérico de la campaña (str).
        theme_text:   Texto del tema en formato free-form (ej: "comida tailandesa").

    Returns:
        {"status": "success", "theme": theme_text, "resource_name": str}
        {"status": "error",   "theme": theme_text, "message": str}
    """
    try:
        service = client.get_service("CampaignCriterionService")
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = client.get_service("GoogleAdsService").campaign_path(
            customer_id, campaign_id
        )
        criterion.keyword_theme.free_form_keyword_theme = theme_text
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        resource = response.results[0].resource_name if response.results else ""
        return {"status": "success", "theme": theme_text, "resource_name": resource}
    except Exception as e:
        return {"status": "error", "theme": theme_text, "message": str(e)}


def remove_smart_campaign_theme(client, customer_id: str, criterion_resource_name: str) -> dict:
    """
    Elimina un keyword theme de una Smart Campaign usando CampaignCriterionService.

    Args:
        criterion_resource_name: resource_name del campaign_criterion a eliminar.
            Formato: "customers/{cid}/campaignCriteria/{campaign_id}~{criterion_id}"

    Returns:
        {"status": "success", "removed": criterion_resource_name}
        {"status": "error",   "message": str(e)}

    Restricciones API:
      - Solo operación REMOVE — no hay UPDATE para keyword themes en Smart.
      - Google puede rechazar si la campaña queda con muy pocos temas (<3).
      - La guarda de SMART_THEME_MIN_REMAINING (5) está en config/agent_config.py
        y se evalúa ANTES de llamar esta función.
    """
    try:
        service = client.get_service("CampaignCriterionService")
        op = client.get_type("CampaignCriterionOperation")
        op.remove = criterion_resource_name
        service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"status": "success", "removed": criterion_resource_name}
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

def _verify_geo_id_is_allowed(client, customer_id: str, location_id: str) -> dict:
    """Verifica por API que un location_id resuelva a Mérida, Yucatán antes de mutar.

    Returns:
        {"allowed": True, "canonical": str}   — ID en whitelist y confirmado como Mérida
        {"allowed": False, "reason": str}     — ID no en whitelist o no resuelve a Mérida
    """
    from config.agent_config import DEFAULT_ALLOWED_LOCATION_IDS, MERIDA_LOCATION_CANONICAL_CONTAINS

    if location_id not in DEFAULT_ALLOWED_LOCATION_IDS:
        return {
            "allowed": False,
            "reason": (
                f"location_id '{location_id}' no está en DEFAULT_ALLOWED_LOCATION_IDS "
                f"{DEFAULT_ALLOWED_LOCATION_IDS}. Agregar solo IDs verificados como Mérida."
            ),
        }
    # Verificar contra la API que el ID realmente resuelve a Mérida
    try:
        ga = client.get_service("GoogleAdsService")
        q  = f"""
            SELECT geo_target_constant.id, geo_target_constant.canonical_name
            FROM geo_target_constant
            WHERE geo_target_constant.id = {location_id}
        """
        rows = list(ga.search(customer_id=customer_id, query=q))
        if not rows:
            return {"allowed": False, "reason": f"ID {location_id} no encontrado en geo_target_constant."}
        canonical = rows[0].geo_target_constant.canonical_name
        if MERIDA_LOCATION_CANONICAL_CONTAINS.lower() not in canonical.lower():
            return {
                "allowed": False,
                "reason": (
                    f"BLOQUEADO: ID {location_id} resuelve a '{canonical}', "
                    f"que no contiene '{MERIDA_LOCATION_CANONICAL_CONTAINS}'. "
                    f"Esto no es Mérida — mutación cancelada para prevenir configuración incorrecta."
                ),
            }
        return {"allowed": True, "canonical": canonical}
    except Exception as exc:
        return {"allowed": False, "reason": f"Error verificando ID {location_id} contra API: {exc}"}


def update_campaign_location(client, customer_id: str, campaign_id: str, location_id: str) -> dict:
    """Restringe campaña a una ciudad/region por location_id (criterion type: LOCATION).
    Merida, Yucatan location_id: '1010205'

    GUARDIA DE SEGURIDAD: verifica que location_id esté en DEFAULT_ALLOWED_LOCATION_IDS
    y que resuelva a Mérida, Yucatán via API antes de ejecutar la mutación.
    Si el ID no es Mérida, la función retorna error sin hacer ningún cambio.
    """
    # ── Guardia geo: verificar ID antes de cualquier mutación ──────────────
    guard = _verify_geo_id_is_allowed(client, customer_id, location_id)
    if not guard["allowed"]:
        return {"status": "error", "message": guard["reason"], "blocked_by": "geo_id_guard"}

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


def fetch_campaign_geo_criteria(client, customer_id: str) -> dict:
    """
    Retorna un dict keyed by campaign_id con los criterios de geotargeting de
    todas las campañas ENABLED y PAUSED (excluye REMOVED).

    Hace tres queries GAQL:
      1. Campañas ENABLED y PAUSED (id, name, advertising_channel_type).
      2. Criterios LOCATION positivos.
      3. Criterios PROXIMITY positivos — una campaña con solo PROXIMITY y sin
         LOCATION aparece con location_ids=[], señal GEO0 (sin restricción
         por location_id).  has_proximity=True permite al caller saber que
         existe restricción de otro tipo.

    Formato del dict retornado:
    {
      "123456": {
        "campaign_id":              "123456",
        "campaign_name":            "Thai Merida Delivery",
        "advertising_channel_type": "SMART",
        "location_ids":             ["1010205"],
        "criteria_resource_names":  ["customers/.../campaignCriteria/..."],
        "has_proximity":            False,
        "proximity_radius_km":      None,   # float si existe PROXIMITY, else None
        "proximity_center_lat":     None,   # float si existe PROXIMITY, else None
        "proximity_center_lng":     None,   # float si existe PROXIMITY, else None
      },
      ...
    }
    Campañas sin ningún criterio LOCATION aparecen con location_ids=[].
    """
    ga_service = client.get_service("GoogleAdsService")

    # ── Query 1: campañas ENABLED y PAUSED ───────────────────────────────────
    q_campaigns = """
        SELECT
          campaign.id,
          campaign.name,
          campaign.advertising_channel_type
        FROM campaign
        WHERE campaign.status IN ('ENABLED', 'PAUSED')
    """
    result: dict = {}
    try:
        for row in ga_service.search(customer_id=customer_id, query=q_campaigns):
            cid = str(row.campaign.id)
            result[cid] = {
                "campaign_id":              cid,
                "campaign_name":            row.campaign.name,
                "advertising_channel_type": row.campaign.advertising_channel_type.name,
                "location_ids":             [],
                "criteria_resource_names":  [],
                "has_proximity":            False,
                "proximity_radius_km":      None,
                "proximity_center_lat":     None,
                "proximity_center_lng":     None,
            }
    except Exception as e:
        print(f"fetch_campaign_geo_criteria: error en query campañas — {e}")
        return {}

    # ── Query 2: criterios LOCATION positivos ────────────────────────────────
    q_location = """
        SELECT
          campaign.id,
          campaign_criterion.location.geo_target_constant,
          campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.status IN ('ENABLED', 'PAUSED')
          AND campaign_criterion.type = 'LOCATION'
          AND campaign_criterion.negative = FALSE
    """
    try:
        for row in ga_service.search(customer_id=customer_id, query=q_location):
            cid = str(row.campaign.id)
            if cid not in result:
                continue
            geo_rn = row.campaign_criterion.location.geo_target_constant
            location_id = geo_rn.split("/")[-1] if geo_rn else ""
            if location_id:
                result[cid]["location_ids"].append(location_id)
                result[cid]["criteria_resource_names"].append(
                    row.campaign_criterion.resource_name
                )
    except Exception as e:
        print(f"fetch_campaign_geo_criteria: error en query LOCATION — {e}")

    # ── Query 3: criterios PROXIMITY positivos (incluye radio y centro) ─────
    q_proximity = """
        SELECT
          campaign.id,
          campaign_criterion.resource_name,
          campaign_criterion.proximity.radius,
          campaign_criterion.proximity.geo_point.latitude_in_micro_degrees,
          campaign_criterion.proximity.geo_point.longitude_in_micro_degrees
        FROM campaign_criterion
        WHERE campaign.status IN ('ENABLED', 'PAUSED')
          AND campaign_criterion.type = 'PROXIMITY'
          AND campaign_criterion.negative = FALSE
    """
    try:
        for row in ga_service.search(customer_id=customer_id, query=q_proximity):
            cid = str(row.campaign.id)
            if cid not in result:
                continue
            prox = row.campaign_criterion.proximity
            result[cid]["has_proximity"]       = True
            result[cid]["proximity_radius_km"] = prox.radius
            result[cid]["proximity_center_lat"] = (
                prox.geo_point.latitude_in_micro_degrees / 1_000_000
                if prox.geo_point.latitude_in_micro_degrees else None
            )
            result[cid]["proximity_center_lng"] = (
                prox.geo_point.longitude_in_micro_degrees / 1_000_000
                if prox.geo_point.longitude_in_micro_degrees else None
            )
    except Exception as e:
        print(f"fetch_campaign_geo_criteria: error en query PROXIMITY — {e}")

    return result


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


def update_bidding_strategy(client, customer_id: str, campaign_id: str, strategy: str) -> dict:
    """Cambia bidding strategy de campaña Search. NO usar en Smart Campaigns."""
    try:
        campaign_service = client.get_service("CampaignService")
        operation = client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        if strategy == "MAXIMIZE_CONVERSIONS":
            campaign.maximize_conversions.target_cpa_micros = 0
            operation.update_mask.paths[:] = ["maximize_conversions"]
        else:
            return {"status": "error", "message": f"Estrategia '{strategy}' no implementada"}
        campaign_service.mutate_campaigns(customer_id=customer_id, operations=[operation])
        return {"status": "success", "campaign_id": campaign_id, "strategy": strategy}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_network_settings(client, customer_id: str, campaign_id: str,
                             target_content_network: bool = False) -> dict:
    """Desactiva Display Network en campaña Search. NO usar en Smart Campaigns."""
    try:
        campaign_service = client.get_service("CampaignService")
        operation = client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        campaign.network_settings.target_content_network = target_content_network
        operation.update_mask.paths[:] = ["network_settings.target_content_network"]
        campaign_service.mutate_campaigns(customer_id=customer_id, operations=[operation])
        return {"status": "success", "campaign_id": campaign_id,
                "target_content_network": target_content_network}
    except Exception as e:
        return {"status": "error", "message": str(e)}


import logging as _logging
_ads_logger = _logging.getLogger(__name__)


# ── QUALITY SCORE / AD HEALTH / IMPRESSION SHARE (solo lectura) ───────────────

def fetch_keyword_quality_scores(client, customer_id: str) -> list:
    """
    Lee Quality Score y subcomponentes de keywords activas (últimos 30 días).
    Retorna lista vacía si la API falla — nunca lanza excepción.
    """
    _ENUM_STR = {0: None, 1: None, 2: "BELOW_AVERAGE", 3: "AVERAGE", 4: "ABOVE_AVERAGE"}

    def _enum_to_str(val):
        if val is None:
            return None
        v = int(val)
        return _ENUM_STR.get(v, str(val))

    query = """
        SELECT
          ad_group_criterion.keyword.text,
          ad_group_criterion.quality_info.quality_score,
          ad_group_criterion.quality_info.creative_quality_score,
          ad_group_criterion.quality_info.post_click_quality_score,
          ad_group_criterion.quality_info.search_predicted_ctr,
          campaign.id, campaign.name,
          ad_group.id, ad_group.name,
          metrics.cost_micros, metrics.conversions
        FROM keyword_view
        WHERE ad_group_criterion.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
          AND segments.date DURING LAST_30_DAYS
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        results = []
        for row in ga_service.search(customer_id=customer_id, query=query):
            agc = row.ad_group_criterion
            qi  = agc.quality_info
            qs  = qi.quality_score if qi.quality_score else None
            results.append({
                "keyword_text":            agc.keyword.text,
                "quality_score":           qs,
                "creative_quality_score":  _enum_to_str(qi.creative_quality_score),
                "post_click_quality_score": _enum_to_str(qi.post_click_quality_score),
                "search_predicted_ctr":    _enum_to_str(qi.search_predicted_ctr),
                "campaign_id":             str(row.campaign.id),
                "campaign_name":           row.campaign.name,
                "ad_group_id":             str(row.ad_group.id),
                "ad_group_name":           row.ad_group.name,
                "cost_micros":             row.metrics.cost_micros,
                "conversions":             row.metrics.conversions,
            })
        return results
    except Exception as e:
        _ads_logger.warning("fetch_keyword_quality_scores: %s", e)
        return []


def fetch_ad_health(client, customer_id: str) -> list:
    """
    Lee Ad Strength, estado y política de anuncios de todas las campañas activas.
    Para Smart Campaigns sin RSA, ad_strength = None. Nunca lanza excepción.
    """
    _STRENGTH_MAP = {0: None, 1: "POOR", 2: "AVERAGE", 3: "GOOD", 4: "EXCELLENT", 5: "NO_ADS"}

    query = """
        SELECT
          ad_group_ad.ad.id,
          ad_group_ad.ad_strength,
          ad_group_ad.status,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.ad.responsive_search_ad.headlines,
          ad_group_ad.ad.responsive_search_ad.descriptions,
          ad_group_ad.ad.final_urls,
          campaign.id, campaign.name,
          ad_group.id, ad_group.name
        FROM ad_group_ad
        WHERE ad_group_ad.status IN ('ENABLED', 'PAUSED')
          AND campaign.status = 'ENABLED'
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        results = []
        for row in ga_service.search(customer_id=customer_id, query=query):
            aga = row.ad_group_ad
            ad  = aga.ad
            strength_val = int(aga.ad_strength) if aga.ad_strength else 0
            ad_strength  = _STRENGTH_MAP.get(strength_val)
            try:
                rsa          = ad.responsive_search_ad
                headlines    = [h.text for h in rsa.headlines if h.text]
                descriptions = [d.text for d in rsa.descriptions if d.text]
            except Exception:
                headlines    = []
                descriptions = []

            results.append({
                "ad_id":           str(ad.id),
                "ad_strength":     ad_strength,
                "ad_status":       str(aga.status.name) if aga.status else None,
                "approval_status": str(aga.policy_summary.approval_status.name)
                                   if aga.policy_summary and aga.policy_summary.approval_status else None,
                "headlines":       headlines,
                "descriptions":    descriptions,
                "final_urls":      list(ad.final_urls) if ad.final_urls else [],
                "campaign_id":     str(row.campaign.id),
                "campaign_name":   row.campaign.name,
                "ad_group_id":     str(row.ad_group.id),
                "ad_group_name":   row.ad_group.name,
                "ad_group_resource": row.ad_group.resource_name,
            })
        return results
    except Exception as e:
        _ads_logger.warning("fetch_ad_health: %s", e)
        return []


def fetch_impression_share(client, customer_id: str) -> list:
    """
    Lee métricas de Impression Share por campaña activa (últimos 7 días).
    Los valores son fracción 0-1. Retorna [] si falla.
    """
    query = """
        SELECT
          campaign.id, campaign.name,
          metrics.search_impression_share,
          metrics.search_rank_lost_impression_share,
          metrics.search_budget_lost_impression_share
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND campaign.advertising_channel_type = 'SEARCH'
          AND segments.date DURING LAST_7_DAYS
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        results = []
        for row in ga_service.search(customer_id=customer_id, query=query):
            m = row.metrics
            results.append({
                "campaign_id":   str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "search_impression_share":             m.search_impression_share,
                "search_rank_lost_impression_share":   m.search_rank_lost_impression_share,
                "search_budget_lost_impression_share": m.search_budget_lost_impression_share,
            })
        return results
    except Exception as e:
        _ads_logger.warning("fetch_impression_share: %s", e)
        return []


def fetch_monthly_spend(client, customer_id: str) -> float:
    """
    Retorna el gasto total acumulado del mes en curso en MXN.
    Suma cost_micros de todas las campañas activas en THIS_MONTH.
    Retorna 0.0 si falla — nunca lanza excepción.
    """
    query = """
        SELECT metrics.cost_micros
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        total_micros = 0
        for row in ga_service.search(customer_id=customer_id, query=query):
            total_micros += row.metrics.cost_micros
        return round(total_micros / 1_000_000, 2)
    except Exception as e:
        _ads_logger.warning("fetch_monthly_spend: %s", e)
        return 0.0


def update_rsa_headlines(client, customer_id: str, ad_group_resource: str,
                         ad_id: str, new_headlines: list) -> dict:
    """
    Agrega headlines a un RSA existente. Valida max 30 chars. No duplica.
    Retorna dict con status y resultado.
    """
    try:
        ga_service   = client.get_service("GoogleAdsService")
        ad_service   = client.get_service("AdGroupAdService")
        # Leer RSA actual
        query = f"""
            SELECT ad_group_ad.ad.id,
                   ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.resource_name
            FROM ad_group_ad
            WHERE ad_group_ad.ad.id = {ad_id}
        """
        current_headlines = []
        resource_name     = None
        for row in ga_service.search(customer_id=customer_id, query=query):
            resource_name = row.ad_group_ad.resource_name
            current_headlines = [h.text for h in row.ad_group_ad.ad.responsive_search_ad.headlines if h.text]
            break
        if not resource_name:
            return {"status": "error", "message": f"Ad {ad_id} no encontrado"}

        # Filtrar: max 30 chars, sin duplicar
        to_add = [h for h in new_headlines if len(h) <= 30 and h not in current_headlines]
        if not to_add:
            return {"status": "skipped", "reason": "no headlines nuevos válidos"}

        # Build operation
        operation = client.get_type("AdGroupAdOperation")
        aga       = operation.update
        aga.resource_name = resource_name
        combined = current_headlines + to_add
        for h_text in combined:
            h = aga.ad.responsive_search_ad.headlines.add()
            h.text = h_text
        client.copy_from(
            operation.update_mask,
            protobuf_helpers.field_mask(None, aga._pb)
        )
        operation.update_mask.paths[:] = ["ad.responsive_search_ad.headlines"]
        ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"status": "success", "added": to_add}
    except Exception as e:
        _ads_logger.warning("update_rsa_headlines: %s", e)
        return {"status": "error", "message": str(e)}


def replace_rsa_headlines(client, customer_id: str, ad_group_resource: str,
                          ad_id: str, new_headlines: list) -> dict:
    """
    Reemplaza los headlines de un RSA con la lista exacta proporcionada.
    NO concatena con los headlines actuales — envía new_headlines como lista final.
    Valida: max 30 chars, no vacíos, deduplicados, máximo 15 headlines.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        ad_service = client.get_service("AdGroupAdService")
        # Obtener resource_name del ad
        query = f"""
            SELECT ad_group_ad.ad.id,
                   ad_group_ad.resource_name
            FROM ad_group_ad
            WHERE ad_group_ad.ad.id = {ad_id}
        """
        resource_name = None
        for row in ga_service.search(customer_id=customer_id, query=query):
            resource_name = row.ad_group_ad.resource_name
            break
        if not resource_name:
            return {"status": "error", "message": f"Ad {ad_id} no encontrado"}

        # Construir lista final: deduplicar, filtrar vacíos y > 30 chars, truncar a 15
        seen = set()
        final_headlines = []
        for h in new_headlines:
            if not h or not isinstance(h, str):
                continue
            h = h.strip()
            if len(h) > 30 or h in seen:
                continue
            seen.add(h)
            final_headlines.append(h)
            if len(final_headlines) >= 15:
                break

        if not final_headlines:
            return {"status": "skipped", "reason": "no headlines válidos tras filtros"}

        if len(final_headlines) < 3:
            return {"status": "skipped_insufficient_headlines", "reason": f"solo {len(final_headlines)} headline(s) válido(s) — mínimo 3 requeridos por Google Ads"}

        # Build operation — enviar SOLO final_headlines (replace real)
        operation = client.get_type("AdGroupAdOperation")
        aga = operation.update
        aga.resource_name = resource_name
        for h_text in final_headlines:
            h = aga.ad.responsive_search_ad.headlines.add()
            h.text = h_text
        operation.update_mask.paths[:] = ["ad.responsive_search_ad.headlines"]
        ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"status": "success", "replaced_with": final_headlines}
    except Exception as e:
        import traceback
        _ads_logger.error("replace_rsa_headlines ERROR — traceback completo:\n%s", traceback.format_exc())
        return {"status": "error", "message": str(e)}


def add_ad_group_to_existing_campaign(
    client, customer_id: str, campaign_id: str,
    ag_name: str, headlines: list, descriptions: list, keywords: list,
    cpc_bid_micros: int = 20_000_000,
    final_url: str = "https://www.thaithaimerida.com",
) -> dict:
    """
    Crea un ad group + RSA + keywords dentro de una campaña existente.
    No crea ni modifica la campaña — solo agrega un ad group.

    Args:
        campaign_id: ID numérico de la campaña (sin resource path)
        keywords:    lista de strings con los textos de keywords (PHRASE match)
    """
    try:
        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        ag_result = create_ad_group(client, customer_id, campaign_resource, ag_name, cpc_bid_micros)
        if ag_result.get("status") != "success":
            return {"status": "error", "step": "create_ad_group", "message": ag_result.get("message")}
        ag_resource = ag_result["resource_name"]

        rsa_result = create_rsa(client, customer_id, ag_resource, headlines, descriptions, final_url)

        kw_results = []
        for kw_text in keywords:
            kw_r = add_keyword_to_ad_group(client, customer_id, ag_resource, kw_text, "PHRASE")
            kw_results.append({"keyword": kw_text, "status": kw_r.get("status")})

        _ads_logger.info(
            "add_ad_group_to_existing_campaign: ad group '%s' creado en campaña %s — RSA=%s, keywords=%d",
            ag_name, campaign_id, rsa_result.get("status"), len(kw_results),
        )
        return {
            "status": "success",
            "ad_group_resource": ag_resource,
            "ad_group_name": ag_name,
            "rsa_status": rsa_result.get("status"),
            "keywords": kw_results,
        }
    except Exception as e:
        import traceback
        _ads_logger.error("add_ad_group_to_existing_campaign ERROR:\n%s", traceback.format_exc())
        return {"status": "error", "message": str(e)}


def update_rsa_descriptions(client, customer_id: str, ad_group_resource: str,
                            ad_id: str, new_descriptions: list) -> dict:
    """
    Agrega descriptions a un RSA existente. Valida max 90 chars. No duplica.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        ad_service = client.get_service("AdGroupAdService")
        query = f"""
            SELECT ad_group_ad.ad.id,
                   ad_group_ad.ad.responsive_search_ad.descriptions,
                   ad_group_ad.resource_name
            FROM ad_group_ad
            WHERE ad_group_ad.ad.id = {ad_id}
        """
        current_descs = []
        resource_name = None
        for row in ga_service.search(customer_id=customer_id, query=query):
            resource_name = row.ad_group_ad.resource_name
            current_descs = [d.text for d in row.ad_group_ad.ad.responsive_search_ad.descriptions if d.text]
            break
        if not resource_name:
            return {"status": "error", "message": f"Ad {ad_id} no encontrado"}

        to_add = [d for d in new_descriptions if len(d) <= 90 and d not in current_descs]
        if not to_add:
            return {"status": "skipped", "reason": "no descriptions nuevas válidas"}

        operation = client.get_type("AdGroupAdOperation")
        aga = operation.update
        aga.resource_name = resource_name
        combined = current_descs + to_add
        for d_text in combined:
            d = aga.ad.responsive_search_ad.descriptions.add()
            d.text = d_text
        operation.update_mask.paths[:] = ["ad.responsive_search_ad.descriptions"]
        ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"status": "success", "added": to_add}
    except Exception as e:
        _ads_logger.warning("update_rsa_descriptions: %s", e)
        return {"status": "error", "message": str(e)}


def remove_rsa_asset(client, customer_id: str, ad_group_resource: str,
                     ad_id: str, asset_text: str, asset_type: str) -> dict:
    """
    Elimina un headline o description específico de un RSA.
    asset_type: "headline" | "description"
    Guardrail: mínimo 3 headlines / 2 descriptions después de eliminar.
    """
    try:
        ga_service = client.get_service("GoogleAdsService")
        ad_service = client.get_service("AdGroupAdService")
        query = f"""
            SELECT ad_group_ad.ad.id,
                   ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.ad.responsive_search_ad.descriptions,
                   ad_group_ad.resource_name
            FROM ad_group_ad
            WHERE ad_group_ad.ad.id = {ad_id}
        """
        resource_name = None
        current_heads = []
        current_descs = []
        for row in ga_service.search(customer_id=customer_id, query=query):
            resource_name = row.ad_group_ad.resource_name
            current_heads = [h.text for h in row.ad_group_ad.ad.responsive_search_ad.headlines if h.text]
            current_descs = [d.text for d in row.ad_group_ad.ad.responsive_search_ad.descriptions if d.text]
            break
        if not resource_name:
            return {"status": "error", "message": f"Ad {ad_id} no encontrado"}

        if asset_type == "headline":
            new_list = [h for h in current_heads if h != asset_text]
            if len(new_list) < 3:
                return {"status": "blocked", "reason": "quedarían menos de 3 headlines"}
            operation = client.get_type("AdGroupAdOperation")
            aga = operation.update
            aga.resource_name = resource_name
            for h_text in new_list:
                h = aga.ad.responsive_search_ad.headlines.add()
                h.text = h_text
            operation.update_mask.paths[:] = ["ad.responsive_search_ad.headlines"]
        else:
            new_list = [d for d in current_descs if d != asset_text]
            if len(new_list) < 2:
                return {"status": "blocked", "reason": "quedarían menos de 2 descriptions"}
            operation = client.get_type("AdGroupAdOperation")
            aga = operation.update
            aga.resource_name = resource_name
            for d_text in new_list:
                d = aga.ad.responsive_search_ad.descriptions.add()
                d.text = d_text
            operation.update_mask.paths[:] = ["ad.responsive_search_ad.descriptions"]

        ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"status": "success", "removed": asset_text}
    except Exception as e:
        _ads_logger.warning("remove_rsa_asset: %s", e)
        return {"status": "error", "message": str(e)}