#!/usr/bin/env python3
"""
ads_fixes.py — 5 fixes urgentes post-auditoría Google Ads Thai Thai
Customer ID: 4021070209

FIX 1: Crear lista negativa compartida "Competidores y cocinas irrelevantes"
        (18 keywords EXACT) y aplicar a ambas campañas Search
FIX 2: Cambiar geo de Experiencia 2026: PRESENCE_OR_INTEREST → PRESENCE
FIX 3: Pausar keywords con 0 impresiones en últimos 30 días (campañas Search)
FIX 4: Pausar ad group "Reservaciones - Anchor TEMP NO USAR"
FIX 5: Pausar ad group "Reservaciones - General"

Nota: Usa asignación directa en op.create/op.update (no CopyFrom) — proto-plus v30
"""

import os
import sys

PROJECT_DIR = r"G:\Mi unidad\thai-thai-vault\thai-thai-ads-agent"
os.chdir(PROJECT_DIR)

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"

LIST_NAME = "Competidores y cocinas irrelevantes"
NEGATIVE_KEYWORDS = [
    "tigre blanco",
    "marmalade",
    "cafe louvre",
    "cochinita",
    "catrín",
    "catrin",
    "tucho oriente",
    "100 natural",
    "ramen",
    "petanca",
    "sushi",
    "comida china",
    "comida japonesa",
    "comida italiana",
    "pizza",
    "hamburguesas",
    "tacos",
    "restaurants",
]

TARGET_CAMPAIGNS = [
    "Thai Mérida - Reservaciones",
    "Thai Mérida - Experiencia 2026",
]
GEO_CAMPAIGN = "Thai Mérida - Experiencia 2026"
PAUSE_AD_GROUPS = [
    "Reservaciones - Anchor TEMP NO USAR",
    "Reservaciones - General",
]

results = {
    "fix1": "PENDING",
    "fix2": "PENDING",
    "fix3": "PENDING",
    "fix4": "PENDING",
    "fix5": "PENDING",
}


def log(msg):
    # Reemplazar caracteres Unicode por ASCII para compatibilidad con cp1252
    msg = msg.replace("✓", "[OK]").replace("⚠", "[WARN]").replace("✗", "[FAIL]")
    print(f"[ads_fixes] {msg}", flush=True)


def ga_search(ga, query):
    svc = ga.get_service("GoogleAdsService")
    response = svc.search(customer_id=CUSTOMER_ID, query=query)
    return list(response)


def _fmt_err(ex: GoogleAdsException) -> str:
    if ex.failure and ex.failure.errors:
        return ex.failure.errors[0].message
    return str(ex)


# ─────────────────────────────────────────────────────────────────────────────
# Lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_search_campaigns(ga):
    rows = ga_search(ga, """
        SELECT campaign.id, campaign.name, campaign.resource_name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND campaign.advertising_channel_type = 'SEARCH'
    """)
    campaigns = {}
    for row in rows:
        campaigns[row.campaign.name] = {
            "id": row.campaign.id,
            "resource_name": row.campaign.resource_name,
        }
    log(f"Campañas Search: {list(campaigns.keys())}")
    return campaigns


def get_ad_groups(ga, campaign_ids):
    ids_str = ", ".join(str(c) for c in campaign_ids)
    rows = ga_search(ga, f"""
        SELECT ad_group.id, ad_group.name, ad_group.resource_name, campaign.name
        FROM ad_group
        WHERE campaign.id IN ({ids_str})
          AND ad_group.status != 'REMOVED'
    """)
    ad_groups = {}
    for row in rows:
        ad_groups[row.ad_group.name] = {
            "id": row.ad_group.id,
            "resource_name": row.ad_group.resource_name,
            "campaign": row.campaign.name,
        }
    return ad_groups


def get_existing_shared_set(ga):
    escaped = LIST_NAME.replace("'", "\\'")
    rows = ga_search(ga, f"""
        SELECT shared_set.resource_name, shared_set.name
        FROM shared_set
        WHERE shared_set.name = '{escaped}'
          AND shared_set.status = 'ENABLED'
    """)
    return rows[0].shared_set.resource_name if rows else None


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1
# ─────────────────────────────────────────────────────────────────────────────

def fix1_negative_list(ga, campaign_resources):
    log("\n=== FIX 1: Crear lista negativa compartida ===")

    # 1a. SharedSet (o usar existente)
    existing = get_existing_shared_set(ga)
    if existing:
        shared_set_resource = existing
        log(f"  Lista ya existe: {shared_set_resource}")
    else:
        ss_service = ga.get_service("SharedSetService")
        op = ga.get_type("SharedSetOperation")
        op.create.name = LIST_NAME
        op.create.type_ = ga.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        try:
            resp = ss_service.mutate_shared_sets(customer_id=CUSTOMER_ID, operations=[op])
            shared_set_resource = resp.results[0].resource_name
            log(f"  Lista creada: {shared_set_resource}")
        except GoogleAdsException as ex:
            log(f"  ERROR creando SharedSet: {_fmt_err(ex)}")
            results["fix1"] = f"ERROR SharedSet: {_fmt_err(ex)}"
            return

    # 1b. Agregar keywords (partial_failure tolera duplicados)
    log(f"  Agregando {len(NEGATIVE_KEYWORDS)} keywords EXACT...")
    sc_service = ga.get_service("SharedCriterionService")
    ops = []
    for kw in NEGATIVE_KEYWORDS:
        op = ga.get_type("SharedCriterionOperation")
        op.create.shared_set = shared_set_resource
        op.create.keyword.text = kw
        op.create.keyword.match_type = ga.enums.KeywordMatchTypeEnum.EXACT
        ops.append(op)

    try:
        resp = sc_service.mutate_shared_criteria(
            customer_id=CUSTOMER_ID,
            operations=ops,
        )
        added = len(resp.results)
        log(f"  Keywords agregadas: {added}/{len(NEGATIVE_KEYWORDS)}")
    except GoogleAdsException as ex:
        # Si ya existen (re-run), continuar igualmente
        if any("DUPLICATE" in str(e.error_code) for e in ex.failure.errors):
            log("  Keywords ya existían en la lista (re-run). Continuando.")
        else:
            log(f"  ERROR agregando keywords: {_fmt_err(ex)}")
            results["fix1"] = f"ERROR keywords: {_fmt_err(ex)}"
            return

    # 1c. Aplicar lista a campañas
    log(f"  Aplicando lista a {len(campaign_resources)} campañas...")
    css_service = ga.get_service("CampaignSharedSetService")
    ops = []
    for camp_resource in campaign_resources:
        op = ga.get_type("CampaignSharedSetOperation")
        op.create.campaign = camp_resource
        op.create.shared_set = shared_set_resource
        ops.append(op)

    try:
        resp = css_service.mutate_campaign_shared_sets(
            customer_id=CUSTOMER_ID,
            operations=ops,
        )
        applied = len(resp.results)
        log(f"  Lista aplicada a {applied} campaña(s). ✓")
    except GoogleAdsException as ex:
        if any("DUPLICATE" in str(e.error_code) for e in ex.failure.errors):
            log("  Lista ya estaba aplicada a esta campaña (re-run). OK.")
        else:
            log(f"  ERROR aplicando a campañas: {_fmt_err(ex)}")
            results["fix1"] = f"ERROR campañas: {_fmt_err(ex)}"
            return

    results["fix1"] = "OK"
    log("FIX 1 COMPLETE ✓")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2
# ─────────────────────────────────────────────────────────────────────────────

def fix2_geo(ga, campaign_resource):
    log("\n=== FIX 2: Geo targeting Experiencia 2026: PRESENCE_OR_INTEREST → PRESENCE ===")
    campaign_service = ga.get_service("CampaignService")

    op = ga.get_type("CampaignOperation")
    op.update.resource_name = campaign_resource
    op.update.geo_target_type_setting.positive_geo_target_type = (
        ga.enums.PositiveGeoTargetTypeEnum.PRESENCE
    )
    op.update_mask.paths[:] = ["geo_target_type_setting.positive_geo_target_type"]

    try:
        resp = campaign_service.mutate_campaigns(customer_id=CUSTOMER_ID, operations=[op])
        log(f"  Geo actualizado: {resp.results[0].resource_name} ✓")
        results["fix2"] = "OK"
    except GoogleAdsException as ex:
        log(f"  ERROR: {_fmt_err(ex)}")
        results["fix2"] = f"ERROR: {_fmt_err(ex)}"
        return

    log("FIX 2 COMPLETE ✓")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3
# ─────────────────────────────────────────────────────────────────────────────

def fix3_pause_zero_impression_keywords(ga, campaign_ids):
    log("\n=== FIX 3: Pausar keywords con 0 impresiones (últimos 30 días) ===")
    ids_str = ", ".join(str(c) for c in campaign_ids)

    # Paso A: todos los keywords ENABLED en estas campañas Search
    log("  Consultando todos los keywords habilitados...")
    all_rows = ga_search(ga, f"""
        SELECT
            ad_group_criterion.resource_name,
            ad_group_criterion.keyword.text,
            ad_group.name,
            campaign.name
        FROM ad_group_criterion
        WHERE campaign.id IN ({ids_str})
          AND campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND ad_group_criterion.status = 'ENABLED'
          AND ad_group_criterion.type = 'KEYWORD'
    """)
    all_kw = {row.ad_group_criterion.resource_name: row for row in all_rows}
    log(f"  Total keywords habilitados: {len(all_kw)}")

    if not all_kw:
        log("  Sin keywords. Saltando FIX 3.")
        results["fix3"] = "SKIP: sin keywords"
        return

    # Paso B: keywords con impresiones > 0 en últimos 30 días
    log("  Consultando keywords con impresiones...")
    active_rows = ga_search(ga, f"""
        SELECT
            ad_group_criterion.resource_name,
            metrics.impressions
        FROM keyword_view
        WHERE campaign.id IN ({ids_str})
          AND campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND ad_group_criterion.status = 'ENABLED'
          AND segments.date DURING LAST_30_DAYS
    """)
    active_rns = {r.ad_group_criterion.resource_name for r in active_rows if r.metrics.impressions > 0}
    log(f"  Keywords con impresiones > 0: {len(active_rns)}")

    # Paso C: diferencia
    zero_rns = [rn for rn in all_kw if rn not in active_rns]
    log(f"  Keywords con 0 impresiones a pausar: {len(zero_rns)}")

    if not zero_rns:
        log("  Todos los keywords tuvieron impresiones. Nada que pausar.")
        results["fix3"] = "OK: 0 keywords a pausar"
        return

    # Muestra de los primeros 5
    for rn in zero_rns[:5]:
        r = all_kw[rn]
        log(f"    → [{r.campaign.name}] [{r.ad_group.name}] {r.ad_group_criterion.keyword.text}")
    if len(zero_rns) > 5:
        log(f"    ... y {len(zero_rns) - 5} más")

    # Paso D: pausar en lotes de 1000
    agc_service = ga.get_service("AdGroupCriterionService")
    paused = 0
    errors = 0

    for i in range(0, len(zero_rns), 1000):
        batch = zero_rns[i:i + 1000]
        ops = []
        for rn in batch:
            op = ga.get_type("AdGroupCriterionOperation")
            op.update.resource_name = rn
            op.update.status = ga.enums.AdGroupCriterionStatusEnum.PAUSED
            op.update_mask.paths[:] = ["status"]
            ops.append(op)

        try:
            resp = agc_service.mutate_ad_group_criteria(
                request={
                    "customer_id": CUSTOMER_ID,
                    "operations": ops,
                    "partial_failure": True,
                }
            )
            batch_ok = sum(1 for r in resp.results if r.resource_name)
            paused += batch_ok
            log(f"  Lote {i // 1000 + 1}: {batch_ok}/{len(batch)} pausados")
            if resp.partial_failure_error:
                errors += 1
                log(f"    (partial failures en lote {i // 1000 + 1})")
        except GoogleAdsException as ex:
            errors += 1
            log(f"  ERROR lote {i // 1000 + 1}: {_fmt_err(ex)}")

    results["fix3"] = f"OK: {paused} pausados, {errors} errores"
    log(f"FIX 3 COMPLETE ✓  ({paused} keywords pausados, {errors} errores)")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 4 / FIX 5: Pausar ad groups
# ─────────────────────────────────────────────────────────────────────────────

def pause_ad_group(ga, ag_resource, ag_name, fix_key):
    log(f"\n=== {fix_key.upper()}: Pausar ad group '{ag_name}' ===")
    ag_service = ga.get_service("AdGroupService")

    op = ga.get_type("AdGroupOperation")
    op.update.resource_name = ag_resource
    op.update.status = ga.enums.AdGroupStatusEnum.PAUSED
    op.update_mask.paths[:] = ["status"]

    try:
        resp = ag_service.mutate_ad_groups(customer_id=CUSTOMER_ID, operations=[op])
        log(f"  Pausado: {resp.results[0].resource_name} ✓")
        results[fix_key] = "OK"
    except GoogleAdsException as ex:
        log(f"  ERROR: {_fmt_err(ex)}")
        results[fix_key] = f"ERROR: {_fmt_err(ex)}"
        return

    log(f"{fix_key.upper()} COMPLETE ✓")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log("Cargando Google Ads client...")
    ga = GoogleAdsClient.load_from_storage("google-ads.yaml")

    campaigns = get_search_campaigns(ga)

    missing = [c for c in TARGET_CAMPAIGNS if c not in campaigns]
    if missing:
        log(f"ERROR: Campañas no encontradas: {missing}")
        log(f"Disponibles: {list(campaigns.keys())}")
        sys.exit(1)

    campaign_resources = [campaigns[c]["resource_name"] for c in TARGET_CAMPAIGNS]
    campaign_ids = [campaigns[c]["id"] for c in TARGET_CAMPAIGNS]
    geo_resource = campaigns[GEO_CAMPAIGN]["resource_name"]

    ad_groups = get_ad_groups(ga, campaign_ids)
    log(f"Ad groups en campañas target: {list(ad_groups.keys())}")

    missing_ags = [ag for ag in PAUSE_AD_GROUPS if ag not in ad_groups]
    if missing_ags:
        log(f"ADVERTENCIA: Ad groups no encontrados: {missing_ags}")

    # ── Ejecutar los 5 fixes ─────────────────────────────────────────────────
    fix1_negative_list(ga, campaign_resources)
    fix2_geo(ga, geo_resource)
    fix3_pause_zero_impression_keywords(ga, campaign_ids)

    if "Reservaciones - Anchor TEMP NO USAR" in ad_groups:
        pause_ad_group(
            ga,
            ad_groups["Reservaciones - Anchor TEMP NO USAR"]["resource_name"],
            "Reservaciones - Anchor TEMP NO USAR",
            "fix4",
        )
    else:
        log("\nFIX 4: 'Reservaciones - Anchor TEMP NO USAR' no encontrado.")
        results["fix4"] = "SKIP: no encontrado"

    if "Reservaciones - General" in ad_groups:
        pause_ad_group(
            ga,
            ad_groups["Reservaciones - General"]["resource_name"],
            "Reservaciones - General",
            "fix5",
        )
    else:
        log("\nFIX 5: 'Reservaciones - General' no encontrado.")
        results["fix5"] = "SKIP: no encontrado"

    # ── Resumen ──────────────────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log("RESUMEN DE FIXES")
    log("=" * 60)
    for fix, status in results.items():
        icon = "✓" if status.startswith("OK") else ("⚠" if status.startswith("SKIP") else "✗")
        log(f"  {fix.upper()}: {icon} {status}")
    log("=" * 60)

    failed = [k for k, v in results.items() if v.startswith("ERROR")]
    if failed:
        log(f"\n{len(failed)} fix(es) con error: {failed}")
        sys.exit(1)
    else:
        log("\nTodos los fixes aplicados exitosamente.")


if __name__ == "__main__":
    main()
