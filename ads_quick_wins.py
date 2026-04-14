#!/usr/bin/env python3
"""
ads_quick_wins.py — 7 Quick Wins restantes de la auditoría Google Ads Thai Thai
Customer ID: 4021070209

QW1: 4 Sitelinks a nivel de cuenta (Assets API)
QW2: 4 Callouts a nivel de cuenta (Assets API)
QW3: 1 Structured Snippet a nivel de cuenta (Assets API)
QW4: Enhanced Conversions — UI required (instrucciones en log)
QW5: 10 nuevas negativas EXACT en lista compartida
QW6: Aplicar lista "Competidores y cocinas irrelevantes" a Delivery
QW7: Asignar valores de conversión (reserva=$500, pedido=$350 MXN)
"""

import os
import sys

PROJECT_DIR = r"G:\Mi unidad\thai-thai-vault\thai-thai-ads-agent"
os.chdir(PROJECT_DIR)

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
NEGATIVE_LIST_NAME = "Competidores y cocinas irrelevantes"

results = {f"qw{i}": "PENDING" for i in range(1, 8)}


def log(msg):
    print(f"[qw] {msg}", flush=True)


def ga_search(ga, query):
    svc = ga.get_service("GoogleAdsService")
    return list(svc.search(customer_id=CUSTOMER_ID, query=query))


def _fmt_err(ex: GoogleAdsException) -> str:
    if ex.failure and ex.failure.errors:
        return ex.failure.errors[0].message
    return str(ex)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: crear Asset + vincular a cuenta
# ─────────────────────────────────────────────────────────────────────────────

def create_asset_and_link(ga, populate_fn, field_type_value: int, label: str) -> bool:
    """Crea un Asset y lo vincula a la cuenta con CustomerAsset."""
    asset_svc = ga.get_service("AssetService")
    ca_svc = ga.get_service("CustomerAssetService")

    # 1. Crear el asset
    a_op = ga.get_type("AssetOperation")
    populate_fn(a_op.create)

    try:
        resp = asset_svc.mutate_assets(customer_id=CUSTOMER_ID, operations=[a_op])
        asset_rn = resp.results[0].resource_name
        log(f"    Asset creado: {asset_rn}")
    except GoogleAdsException as ex:
        log(f"    ERROR creando '{label}': {_fmt_err(ex)}")
        return False

    # 2. Vincular al account
    ca_op = ga.get_type("CustomerAssetOperation")
    ca_op.create.asset = asset_rn
    ca_op.create.field_type = field_type_value

    try:
        ca_svc.mutate_customer_assets(customer_id=CUSTOMER_ID, operations=[ca_op])
        log(f"    Vinculado a cuenta [OK]")
        return True
    except GoogleAdsException as ex:
        log(f"    ERROR vinculando '{label}': {_fmt_err(ex)}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# QW1: SITELINKS
# ─────────────────────────────────────────────────────────────────────────────

# Descripcion1/2 mejoran el espacio en SERP (max 35 chars cada una)
SITELINKS = [
    {
        "link_text": "Reservar Mesa",
        "url": "https://thaithaimerida.com",
        "desc1": "Mesas para 2 a 8 personas",
        "desc2": "Reservacion en linea rapida",
    },
    {
        "link_text": "Ver Menu",
        # Google strips #fragments — usa URL base; el anchor #menu no funciona en final_urls
        "url": "https://thaithaimerida.com",
        "desc1": "Pad Thai, Curries y Sopas",
        "desc2": "Cocina tailandesa autentica",
    },
    {
        "link_text": "Pedir Online",
        "url": (
            "https://www.foodbooking.com/ordering/restaurant/menu"
            "?restaurant_uid=2e45e04c-13f9-4bf7-9fb7-ac8378c9224c"
        ),
        "desc1": "Sin comisiones adicionales",
        "desc2": "Entrega a domicilio Merida",
    },
    {
        "link_text": "Como Llegar",
        "url": "https://maps.google.com/?q=Thai+Thai+Merida+Calle+30+351",
        "desc1": "Calle 30 No. 351",
        "desc2": "Col. Emiliano Zapata Norte",
    },
]


def qw1_sitelinks(ga):
    log("\n=== QW1: 4 Sitelinks a nivel de cuenta ===")
    field_type = ga.enums.AssetFieldTypeEnum.SITELINK
    ok = 0

    for sl in SITELINKS:
        log(f"  Sitelink '{sl['link_text']}' -> {sl['url'][:55]}")

        def populate(asset, _s=sl):
            asset.sitelink_asset.link_text = _s["link_text"]
            asset.final_urls.append(_s["url"])  # final_urls es campo de Asset, no de SitelinkAsset
            asset.sitelink_asset.description1 = _s["desc1"]
            asset.sitelink_asset.description2 = _s["desc2"]

        if create_asset_and_link(ga, populate, field_type, sl["link_text"]):
            ok += 1

    results["qw1"] = f"OK: {ok}/{len(SITELINKS)} sitelinks"
    log(f"QW1 COMPLETE [{ok}/{len(SITELINKS)}]")


# ─────────────────────────────────────────────────────────────────────────────
# QW2: CALLOUTS
# ─────────────────────────────────────────────────────────────────────────────

# Limite de Google: 25 caracteres por callout.
# Originales del usuario ajustados:
#   "Cocina Tailandesa Artesanal" (27) -> "Cocina Thai Artesanal" (21)
#   "Reservaciones por WhatsApp"  (26) -> "Reserva por WhatsApp" (20)
#   "Pedidos Online Sin Comision" (27) -> "Pedidos Sin Comision" (20)
CALLOUTS = [
    "Cocina Thai Artesanal",    # 21 chars
    "Abierto Lunes a Domingo",  # 23 chars
    "Reserva por WhatsApp",     # 20 chars
    "Pedidos Sin Comision",     # 20 chars
]


def qw2_callouts(ga):
    log("\n=== QW2: 4 Callouts a nivel de cuenta ===")
    field_type = ga.enums.AssetFieldTypeEnum.CALLOUT
    ok = 0

    for text in CALLOUTS:
        log(f"  Callout '{text}' ({len(text)} chars)")

        def populate(asset, _t=text):
            asset.callout_asset.callout_text = _t

        if create_asset_and_link(ga, populate, field_type, text):
            ok += 1

    results["qw2"] = f"OK: {ok}/{len(CALLOUTS)} callouts"
    log(f"QW2 COMPLETE [{ok}/{len(CALLOUTS)}]")


# ─────────────────────────────────────────────────────────────────────────────
# QW3: STRUCTURED SNIPPET
# ─────────────────────────────────────────────────────────────────────────────

# "Tipos" es un header aprobado por Google para anuncios en espanol
SNIPPET_HEADER = "Tipos"
SNIPPET_VALUES = [
    "Pad Thai",
    "Curry Verde",
    "Tom Kha Gai",
    "Spring Rolls",
    "Som Tam",
    "Massaman Curry",
]


def qw3_structured_snippet(ga):
    log(f"\n=== QW3: Structured Snippet header='{SNIPPET_HEADER}' ===")
    field_type = ga.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET

    def populate(asset):
        asset.structured_snippet_asset.header = SNIPPET_HEADER
        for v in SNIPPET_VALUES:
            asset.structured_snippet_asset.values.append(v)

    if create_asset_and_link(ga, populate, field_type, f"Snippet {SNIPPET_HEADER}"):
        results["qw3"] = "OK"
        log("QW3 COMPLETE")
    else:
        results["qw3"] = "ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# QW4: ENHANCED CONVERSIONS — requiere UI + cambios en tag web
# ─────────────────────────────────────────────────────────────────────────────

def qw4_enhanced_conversions_report():
    log("\n=== QW4: Enhanced Conversions (requiere UI + GTM) ===")
    log("  [UI REQUIRED] No activable completamente via API.")
    log("  Pasos manuales estimados 20-30 min:")
    log("  1. Google Ads > Herramientas > Conversiones")
    log("  2. Icono de engranaje (Configuracion de conversiones)")
    log("  3. Activar 'Conversiones mejoradas para sitio web'")
    log("  4. Metodo recomendado: Google Tag Manager")
    log("  5. En GTM: crear variable que capture email/telefono del formulario")
    log("     de reserva o de confirmacion de pedido Gloria Food")
    log("  6. Mapear al tag de conversion correspondiente")
    log("  Impacto esperado: +10 pct en conversiones medidas")
    results["qw4"] = "UI_REQUIRED"
    log("QW4 DOCUMENTED")


# ─────────────────────────────────────────────────────────────────────────────
# QW5: NUEVAS NEGATIVAS
# ─────────────────────────────────────────────────────────────────────────────

NEW_NEGATIVES = [
    "que hacer en merida",
    "infiniti merida",
    "infiniti",
    "itzimna",
    "sky city",
    "la plancha",
    "restaurantes de lujo",
    "donde comer",
    "restaurantes cerca de mi",
    "de lujo",
]


def qw5_new_negatives(ga):
    log(f"\n=== QW5: Agregar {len(NEW_NEGATIVES)} negativas a '{NEGATIVE_LIST_NAME}' ===")

    # Buscar lista compartida
    rows = ga_search(ga, f"""
        SELECT shared_set.resource_name
        FROM shared_set
        WHERE shared_set.name = '{NEGATIVE_LIST_NAME}'
          AND shared_set.status = 'ENABLED'
    """)
    if not rows:
        log(f"  ERROR: Lista '{NEGATIVE_LIST_NAME}' no encontrada")
        results["qw5"] = "ERROR: lista no encontrada"
        return
    shared_set_rn = rows[0].shared_set.resource_name
    log(f"  Lista: {shared_set_rn}")

    # Keywords que ya existen (para evitar DUPLICATE_RESOURCE)
    existing_rows = ga_search(ga, f"""
        SELECT shared_criterion.keyword.text
        FROM shared_criterion
        WHERE shared_set.resource_name = '{shared_set_rn}'
    """)
    existing = {r.shared_criterion.keyword.text.lower() for r in existing_rows}
    log(f"  Keywords actuales en lista: {len(existing)}")

    to_add = [kw for kw in NEW_NEGATIVES if kw.lower() not in existing]
    already = [kw for kw in NEW_NEGATIVES if kw.lower() in existing]

    if already:
        log(f"  Ya existian (skip): {already}")
    if not to_add:
        log("  Nada nuevo que agregar.")
        results["qw5"] = "OK: todos ya existian"
        return

    log(f"  Agregando {len(to_add)}: {to_add}")
    sc_svc = ga.get_service("SharedCriterionService")
    ops = []
    for kw in to_add:
        op = ga.get_type("SharedCriterionOperation")
        op.create.shared_set = shared_set_rn
        op.create.keyword.text = kw
        op.create.keyword.match_type = ga.enums.KeywordMatchTypeEnum.EXACT
        ops.append(op)

    try:
        resp = sc_svc.mutate_shared_criteria(customer_id=CUSTOMER_ID, operations=ops)
        added = len(resp.results)
        results["qw5"] = f"OK: {added} agregadas, {len(already)} ya existian"
        log(f"  Agregadas: {added}")
    except GoogleAdsException as ex:
        log(f"  ERROR: {_fmt_err(ex)}")
        results["qw5"] = f"ERROR: {_fmt_err(ex)}"
        return

    log("QW5 COMPLETE")


# ─────────────────────────────────────────────────────────────────────────────
# QW6: APLICAR LISTA A DELIVERY
# ─────────────────────────────────────────────────────────────────────────────

def qw6_apply_list_to_delivery(ga):
    log(f"\n=== QW6: Aplicar '{NEGATIVE_LIST_NAME}' a Delivery ===")

    # Shared set
    ss_rows = ga_search(ga, f"""
        SELECT shared_set.resource_name
        FROM shared_set
        WHERE shared_set.name = '{NEGATIVE_LIST_NAME}'
          AND shared_set.status = 'ENABLED'
    """)
    if not ss_rows:
        log("  ERROR: Lista no encontrada")
        results["qw6"] = "ERROR: lista no encontrada"
        return
    shared_set_rn = ss_rows[0].shared_set.resource_name

    # Campana Delivery
    camp_rows = ga_search(ga, """
        SELECT campaign.resource_name, campaign.name,
               campaign.advertising_channel_type,
               campaign.advertising_channel_sub_type
        FROM campaign
        WHERE campaign.status != 'REMOVED'
          AND campaign.name LIKE '%Delivery%'
    """)
    if not camp_rows:
        log("  ERROR: Campana Delivery no encontrada")
        results["qw6"] = "ERROR: campana no encontrada"
        return
    delivery_rn = camp_rows[0].campaign.resource_name
    delivery_name = camp_rows[0].campaign.name
    ch_type = camp_rows[0].campaign.advertising_channel_type.name
    log(f"  Campana: '{delivery_name}' (tipo: {ch_type})")

    # Smart Campaigns no soportan CampaignSharedSetService — requiere UI
    if ch_type == "SMART":
        log("  [UI REQUIRED] Smart Campaign: shared negative lists no soportados via API.")
        log("  Pasos manuales para agregar negativas en Smart Campaign:")
        log("  1. Google Ads > Campanas > Thai Merida - Delivery")
        log("  2. Palabras clave > Palabras clave negativas")
        log("  3. Agregar: thai, cocina thai, restaurante tailandes, pad thai,")
        log("     curry verde, tom kha, japones, chino, sushi, ramen,")
        log("     coreano, indio, pizza, italiano, burger, hamburgesa,")
        log("     vegan, vegano")
        log("  (No se puede vincular lista compartida a Smart Campaigns)")
        results["qw6"] = "UI_REQUIRED: Smart Campaign no soporta shared sets via API"
        log("QW6 DOCUMENTED (UI required)")
        return

    # Verificar si ya esta aplicada
    existing = ga_search(ga, f"""
        SELECT campaign_shared_set.resource_name, campaign_shared_set.shared_set
        FROM campaign_shared_set
        WHERE campaign_shared_set.campaign = '{delivery_rn}'
    """)
    if any(r.campaign_shared_set.shared_set == shared_set_rn for r in existing):
        log("  Lista ya estaba aplicada a Delivery (re-run)")
        results["qw6"] = "OK: ya estaba aplicada"
        return

    # Aplicar
    css_svc = ga.get_service("CampaignSharedSetService")
    op = ga.get_type("CampaignSharedSetOperation")
    op.create.campaign = delivery_rn
    op.create.shared_set = shared_set_rn

    try:
        resp = css_svc.mutate_campaign_shared_sets(customer_id=CUSTOMER_ID, operations=[op])
        log(f"  Aplicada: {resp.results[0].resource_name}")
        results["qw6"] = "OK"
    except GoogleAdsException as ex:
        if any("DUPLICATE" in str(e.error_code) for e in ex.failure.errors):
            log("  Ya estaba aplicada")
            results["qw6"] = "OK: ya estaba aplicada"
        else:
            log(f"  ERROR: {_fmt_err(ex)}")
            results["qw6"] = f"ERROR: {_fmt_err(ex)}"
            return

    log("QW6 COMPLETE")


# ─────────────────────────────────────────────────────────────────────────────
# QW7: CONVERSION VALUES
# ─────────────────────────────────────────────────────────────────────────────

# reserva_completada_directa: always_use_default=True (todas las reservas $500)
# Pedido GloriaFood Online (UPLOAD_CLICKS): always_use_default=False para preservar
#   valores reales del upload cuando existan; $350 solo como fallback
CONVERSION_CONFIG = {
    "reserva_completada_directa": {
        "value": 500.0,
        "currency": "MXN",
        "always_use_default": True,
    },
    "Pedido GloriaFood Online": {
        "value": 350.0,
        "currency": "MXN",
        "always_use_default": False,
    },
}


def qw7_conversion_values(ga):
    log("\n=== QW7: Asignar valores de conversion ===")

    rows = ga_search(ga, """
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.resource_name,
            conversion_action.type,
            conversion_action.value_settings.default_value,
            conversion_action.value_settings.always_use_default_value
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """)
    conv_map = {r.conversion_action.name: r.conversion_action for r in rows}

    conv_svc = ga.get_service("ConversionActionService")
    ok = 0

    for name, cfg in CONVERSION_CONFIG.items():
        if name not in conv_map:
            log(f"  SKIP: '{name}' no encontrado en conversion actions")
            continue

        conv = conv_map[name]
        current_val = conv.value_settings.default_value
        log(f"  '{name}'")
        log(f"    Valor actual: {current_val} -> {cfg['value']} {cfg['currency']}")
        log(f"    always_use_default: {cfg['always_use_default']}")

        op = ga.get_type("ConversionActionOperation")
        op.update.resource_name = conv.resource_name
        op.update.value_settings.default_value = cfg["value"]
        op.update.value_settings.default_currency_code = cfg["currency"]
        op.update.value_settings.always_use_default_value = cfg["always_use_default"]
        op.update_mask.paths[:] = [
            "value_settings.default_value",
            "value_settings.default_currency_code",
            "value_settings.always_use_default_value",
        ]

        try:
            resp = conv_svc.mutate_conversion_actions(
                customer_id=CUSTOMER_ID, operations=[op]
            )
            log(f"    [OK] {resp.results[0].resource_name}")
            ok += 1
        except GoogleAdsException as ex:
            log(f"    ERROR: {_fmt_err(ex)}")

    results["qw7"] = f"OK: {ok}/{len(CONVERSION_CONFIG)} valores asignados"
    log(f"QW7 COMPLETE [{ok}/{len(CONVERSION_CONFIG)}]")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log("Cargando Google Ads client...")
    ga = GoogleAdsClient.load_from_storage("google-ads.yaml")

    qw1_sitelinks(ga)
    qw2_callouts(ga)
    qw3_structured_snippet(ga)
    qw4_enhanced_conversions_report()
    qw5_new_negatives(ga)
    qw6_apply_list_to_delivery(ga)
    qw7_conversion_values(ga)

    log("\n" + "=" * 60)
    log("RESUMEN QUICK WINS")
    log("=" * 60)
    for qw, status in results.items():
        if status.startswith("OK"):
            icon = "[OK] "
        elif status.startswith("UI"):
            icon = "[UI] "
        elif status.startswith("PENDING"):
            icon = "[??] "
        else:
            icon = "[ERR]"
        log(f"  {qw.upper()}: {icon} {status}")
    log("=" * 60)

    failed = [k for k, v in results.items() if v.startswith("ERROR")]
    if failed:
        log(f"\n{len(failed)} QW(s) con error: {failed}")
        sys.exit(1)
    else:
        log("\nTodos los Quick Wins procesados exitosamente.")


if __name__ == "__main__":
    main()
