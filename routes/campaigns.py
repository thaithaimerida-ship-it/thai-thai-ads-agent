"""
Routes de Campañas — /restructure-campaigns, /create-reservations-campaign, /update-ad-schedule
"""
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["campaigns"])

CUSTOMER_ID = "4021070209"


def _get_client():
    from engine.ads_client import get_ads_client
    return get_ads_client()


@router.post("/restructure-campaigns")
async def restructure_campaigns():
    """
    Reestructura las 2 campañas existentes:
    - Thai Mérida → Thai Mérida - Local (geo: Mérida, $50/día)
    - Restaurant Thai On Line → Thai Mérida - Delivery (geo: 8km radio, $100/día)
    """
    try:
        client = _get_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine no disponible: {e}")

    from engine.ads_client import (update_campaign_name, update_campaign_location,
                                    update_campaign_proximity, update_campaign_budget,
                                    log_agent_action)

    ga_service = client.get_service("GoogleAdsService")
    budget_query = """
        SELECT campaign.id, campaign.campaign_budget FROM campaign
        WHERE campaign.id IN (22612348265, 22839241090)
    """
    budget_map = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=budget_query):
        budget_map[str(row.campaign.id)] = row.campaign.campaign_budget

    results = []

    r1 = update_campaign_name(client, CUSTOMER_ID, "22612348265", "Thai Mérida - Local")
    log_agent_action("rename_campaign", "Thai Mérida", {"name": "Thai Mérida"}, {"name": "Thai Mérida - Local"}, r1["status"], r1)

    r2 = update_campaign_location(client, CUSTOMER_ID, "22612348265", "1010205")
    log_agent_action("update_geo", "Thai Mérida - Local", {}, {"location": "Mérida, Yucatán (1010205)"}, r2["status"], r2)

    r3 = update_campaign_budget(client, CUSTOMER_ID, budget_map.get("22612348265", ""), 50_000_000)
    log_agent_action("update_budget", "Thai Mérida - Local", {}, {"budget_day_mxn": 50}, r3["status"], r3)

    results.append({"campaign": "Thai Mérida - Local", "rename": r1, "geo": r2, "budget": r3})

    r4 = update_campaign_name(client, CUSTOMER_ID, "22839241090", "Thai Mérida - Delivery")
    log_agent_action("rename_campaign", "Restaurant Thai On Line", {"name": "Restaurant Thai On Line"}, {"name": "Thai Mérida - Delivery"}, r4["status"], r4)

    r5 = update_campaign_proximity(client, CUSTOMER_ID, "22839241090", lat=20.9674, lng=-89.5926, radius_km=8.0)
    log_agent_action("update_geo", "Thai Mérida - Delivery", {}, {"proximity_km": 8, "center": "Mérida"}, r5["status"], r5)

    r6 = update_campaign_budget(client, CUSTOMER_ID, budget_map.get("22839241090", ""), 100_000_000)
    log_agent_action("update_budget", "Thai Mérida - Delivery", {}, {"budget_day_mxn": 100}, r6["status"], r6)

    results.append({"campaign": "Thai Mérida - Delivery", "rename": r4, "geo": r5, "budget": r6})

    return {"status": "success", "results": results}


@router.post("/create-reservations-campaign")
async def create_reservations_campaign():
    """
    Crea campaña Search 'Thai Mérida - Reservaciones' en estado PAUSED.
    Budget: $70 MXN/día | Geo: 30km desde Mérida.
    """
    try:
        client = _get_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine no disponible: {e}")

    from engine.ads_client import (create_search_campaign, create_ad_group, create_rsa,
                                    add_keyword_to_ad_group, update_campaign_proximity,
                                    add_negative_keyword, log_agent_action)

    campaign_result = create_search_campaign(client, CUSTOMER_ID, name="Thai Mérida - Reservaciones", budget_micros=70_000_000)
    if campaign_result["status"] != "success":
        raise HTTPException(status_code=500, detail=campaign_result)

    campaign_resource = campaign_result["campaign_resource"]
    campaign_id = campaign_resource.split("/")[-1]
    log_agent_action("create_campaign", "Thai Mérida - Reservaciones", {}, {"budget_day": 70, "target_cpa": 65, "status": "PAUSED"}, "success", campaign_result)

    update_campaign_proximity(client, CUSTOMER_ID, campaign_id, lat=20.9674, lng=-89.5926, radius_km=30.0)

    ad_group_result = create_ad_group(client, CUSTOMER_ID, campaign_resource, "Reservaciones - General", cpc_bid_micros=20_000_000)
    if ad_group_result["status"] != "success":
        raise HTTPException(status_code=500, detail=ad_group_result)
    ad_group_resource = ad_group_result["resource_name"]

    headlines = [
        "Restaurante Thai en Mérida", "Reserva tu Mesa Hoy", "Cocina Artesanal Tailandesa",
        "Thai Thai Mérida", "Sabor Auténtico de Tailandia", "Cena Especial en Mérida",
        "El Mejor Thai de Yucatán", "Reservaciones en Línea", "Ingredientes Frescos y Auténticos",
        "Experiencia Culinaria Única"
    ]
    descriptions = [
        "Experimenta la cocina tailandesa artesanal. Reserva tu mesa en línea fácil y rápido.",
        "Ingredientes frescos, recetas auténticas. Tu mesa te espera en Thai Thai Mérida.",
        "Del wok a tu mesa. Sabores tailandeses únicos en el corazón de Mérida.",
        "Reserva ahora y vive una experiencia culinaria tailandesa inigualable."
    ]
    create_rsa(client, CUSTOMER_ID, ad_group_resource, headlines, descriptions)

    keywords = [
        ("restaurante thai mérida", "EXACT"), ("thai thai mérida", "EXACT"),
        ("reservar restaurante mérida", "BROAD"), ("cena romántica mérida", "BROAD"),
        ("restaurante tailandés mérida", "EXACT"), ("mejor restaurante thai mérida", "EXACT"),
    ]
    for kw_text, match_type in keywords:
        add_keyword_to_ad_group(client, CUSTOMER_ID, ad_group_resource, kw_text, match_type)

    for nkw in ["a domicilio", "delivery", "receta", "masaje", "spa", "gratis", "rappi", "uber eats"]:
        add_negative_keyword(client, CUSTOMER_ID, campaign_id, nkw)

    return {
        "status": "success",
        "campaign": "Thai Mérida - Reservaciones",
        "campaign_resource": campaign_resource,
        "campaign_id": campaign_id,
        "note": "Campaña creada en PAUSED. Revisar en Google Ads UI y activar manualmente."
    }


@router.post("/update-ad-schedule")
async def update_ad_schedule_all():
    """Aplica programación horaria basada en heatmap a las 3 campañas."""
    try:
        client = _get_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Engine no disponible: {e}")

    from engine.ads_client import update_ad_schedule, clear_ad_schedules, log_agent_action

    ga_service = client.get_service("GoogleAdsService")
    campaign_query = """
        SELECT campaign.id, campaign.name FROM campaign
        WHERE campaign.status IN ('ENABLED', 'PAUSED')
    """
    campaign_ids = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=campaign_query):
        name = row.campaign.name.lower()
        if "local" in name:
            campaign_ids["local"] = str(row.campaign.id)
        elif "delivery" in name:
            campaign_ids["delivery"] = str(row.campaign.id)
        elif "reserva" in name:
            campaign_ids["reservaciones"] = str(row.campaign.id)

    results = []
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    for campaign_key, campaign_id in campaign_ids.items():
        clear_ad_schedules(client, CUSTOMER_ID, campaign_id)
        is_smart = campaign_key in ("local", "delivery")
        lunch_mod = 0.0 if is_smart else 0.20
        dinner_mod = 0.0 if is_smart else 0.15
        for day in days:
            r1 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 12, 14, lunch_mod)
            r2 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 18, 21, dinner_mod)
            r3 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 6, 12, 0.0)
            r4 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 14, 18, 0.0)
            r5 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 21, 23, 0.0)
            r6 = update_ad_schedule(client, CUSTOMER_ID, campaign_id, day, 23, 24, 0.0)
            results.append({
                "campaign": campaign_key, "day": day,
                "morning": r3, "lunch_peak": r1, "afternoon": r4,
                "dinner_peak": r2, "evening": r5, "late_night": r6
            })
        log_agent_action("update_ad_schedule", campaign_key, {}, {"schedule": "heatmap-based", "is_smart": is_smart}, "success")

    return {"status": "success", "campaigns_found": list(campaign_ids.keys()), "results": results}
