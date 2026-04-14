#!/usr/bin/env python3
"""
ads_conversion_goals.py — Reestructurar conversiones primarias/secundarias por campaña
Customer ID: 4021070209

Search campaigns (CampaignConversionGoal):
  - Thai Mérida - Reservaciones
  - Thai Mérida - Experiencia 2026
  → BOOK_APPOINTMENT = biddable=True (primary), todo lo demás = False

Account-level (CustomerConversionGoal) para Smart campaigns:
  → biddable=True:  GET_DIRECTIONS, PHONE_CALL_LEAD, PURCHASE
  → biddable=False: PAGE_VIEW, ENGAGEMENT, BEGIN_CHECKOUT, STORE_VISIT
  → sin tocar:      SIGNUP, BOOK_APPOINTMENT, CONTACT, otros
"""

import os
import sys

PROJECT_DIR = r"G:\Mi unidad\thai-thai-vault\thai-thai-ads-agent"
os.chdir(PROJECT_DIR)

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
RESERVA_CONV_ID = 7569100920
RESERVA_CATEGORY = "BOOK_APPOINTMENT"  # confirmado arriba

# Campañas Search (resource names conocidos)
SEARCH_CAMPAIGN_RNS = [
    "customers/4021070209/campaigns/23680871468",   # Reservaciones
    "customers/4021070209/campaigns/23730364039",   # Experiencia 2026
]

# Account-level goals: solo cambiar estas categorías; el resto no se toca
ACCOUNT_FORCE_TRUE  = {"GET_DIRECTIONS", "PHONE_CALL_LEAD", "PURCHASE"}
ACCOUNT_FORCE_FALSE = {"PAGE_VIEW", "ENGAGEMENT", "BEGIN_CHECKOUT", "STORE_VISIT"}

results = {}


def log(msg):
    print(f"[goals] {msg}", flush=True)


def ga_search(ga, query):
    svc = ga.get_service("GoogleAdsService")
    return list(svc.search(customer_id=CUSTOMER_ID, query=query))


def _fmt_err(ex: GoogleAdsException) -> str:
    if ex.failure and ex.failure.errors:
        return ex.failure.errors[0].message
    return str(ex)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de estado
# ─────────────────────────────────────────────────────────────────────────────

def show_customer_goals(ga, label):
    log(f"\n--- CustomerConversionGoals ({label}) ---")
    rows = ga_search(ga, """
        SELECT customer_conversion_goal.category,
               customer_conversion_goal.origin,
               customer_conversion_goal.biddable,
               customer_conversion_goal.resource_name
        FROM customer_conversion_goal
    """)
    for r in rows:
        g = r.customer_conversion_goal
        state = "PRIMARY (biddable)" if g.biddable else "secondary"
        log(f"  {g.category.name}/{g.origin.name}: {state}")
    return rows


def show_campaign_goals(ga, label):
    log(f"\n--- CampaignConversionGoals ({label}) ---")
    camp_filter = ", ".join(f"'{rn}'" for rn in SEARCH_CAMPAIGN_RNS)
    rows = ga_search(ga, f"""
        SELECT campaign_conversion_goal.campaign,
               campaign_conversion_goal.category,
               campaign_conversion_goal.origin,
               campaign_conversion_goal.biddable,
               campaign_conversion_goal.resource_name
        FROM campaign_conversion_goal
        WHERE campaign_conversion_goal.campaign IN ({camp_filter})
    """)
    for r in rows:
        g = r.campaign_conversion_goal
        camp_id = g.campaign.split("/")[-1]
        camp_label = "Reservaciones" if camp_id == "23680871468" else "Experiencia"
        state = "PRIMARY" if g.biddable else "secondary"
        log(f"  [{camp_label}] {g.category.name}/{g.origin.name}: {state}")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Mutaciones
# ─────────────────────────────────────────────────────────────────────────────

def update_campaign_goals(ga):
    """Cada Search campaign: BOOK_APPOINTMENT=True, todo lo demás=False."""
    log(f"\n=== Actualizando CampaignConversionGoals ===")
    camp_filter = ", ".join(f"'{rn}'" for rn in SEARCH_CAMPAIGN_RNS)
    rows = ga_search(ga, f"""
        SELECT campaign_conversion_goal.campaign,
               campaign_conversion_goal.category,
               campaign_conversion_goal.origin,
               campaign_conversion_goal.biddable,
               campaign_conversion_goal.resource_name
        FROM campaign_conversion_goal
        WHERE campaign_conversion_goal.campaign IN ({camp_filter})
    """)

    svc = ga.get_service("CampaignConversionGoalService")
    ops = []
    for r in rows:
        g = r.campaign_conversion_goal
        should = (g.category.name == RESERVA_CATEGORY)
        if g.biddable == should:
            continue  # ya correcto

        op = ga.get_type("CampaignConversionGoalOperation")
        op.update.resource_name = g.resource_name
        op.update.biddable = should
        op.update_mask.paths[:] = ["biddable"]
        ops.append(op)

        camp_id = g.campaign.split("/")[-1]
        camp_label = "Reservaciones" if camp_id == "23680871468" else "Experiencia"
        log(f"  [{camp_label}] {g.category.name}/{g.origin.name}: {g.biddable} -> {should}")

    if not ops:
        log("  Sin cambios necesarios en campaign goals")
        results["campaign_goals"] = "OK: sin cambios"
        return

    try:
        resp = svc.mutate_campaign_conversion_goals(
            customer_id=CUSTOMER_ID, operations=ops
        )
        log(f"  Actualizados: {len(resp.results)}")
        results["campaign_goals"] = f"OK: {len(resp.results)} actualizados"
    except GoogleAdsException as ex:
        log(f"  ERROR: {_fmt_err(ex)}")
        results["campaign_goals"] = f"ERROR: {_fmt_err(ex)}"


def update_customer_goals(ga):
    """Account-level: solo cambia las categorías en FORCE_TRUE / FORCE_FALSE."""
    log(f"\n=== Actualizando CustomerConversionGoals ===")
    rows = ga_search(ga, """
        SELECT customer_conversion_goal.category,
               customer_conversion_goal.origin,
               customer_conversion_goal.biddable,
               customer_conversion_goal.resource_name
        FROM customer_conversion_goal
    """)

    svc = ga.get_service("CustomerConversionGoalService")
    ops = []
    for r in rows:
        g = r.customer_conversion_goal
        cat = g.category.name
        # Origins UNKNOWN no son mutables via API — saltarlos
        if g.origin.name == "UNKNOWN":
            continue

        if cat in ACCOUNT_FORCE_TRUE:
            should = True
        elif cat in ACCOUNT_FORCE_FALSE:
            should = False
        else:
            continue  # no tocar (SIGNUP, BOOK_APPOINTMENT, CONTACT…)

        if g.biddable == should:
            continue  # ya correcto

        op = ga.get_type("CustomerConversionGoalOperation")
        op.update.resource_name = g.resource_name
        op.update.biddable = should
        op.update_mask.paths[:] = ["biddable"]
        ops.append(op)
        log(f"  {cat}/{g.origin.name}: {g.biddable} -> {should}")

    if not ops:
        log("  Sin cambios necesarios en customer goals")
        results["customer_goals"] = "OK: sin cambios"
        return

    try:
        resp = svc.mutate_customer_conversion_goals(
            customer_id=CUSTOMER_ID, operations=ops
        )
        log(f"  Actualizados: {len(resp.results)}")
        results["customer_goals"] = f"OK: {len(resp.results)} actualizados"
    except GoogleAdsException as ex:
        log(f"  ERROR: {_fmt_err(ex)}")
        results["customer_goals"] = f"ERROR: {_fmt_err(ex)}"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log("Cargando Google Ads client...")
    ga = GoogleAdsClient.load_from_storage("google-ads.yaml")

    # Estado ANTES
    show_customer_goals(ga, "ANTES")
    show_campaign_goals(ga, "ANTES")

    # Aplicar cambios
    update_campaign_goals(ga)
    update_customer_goals(ga)

    # Estado DESPUES
    show_customer_goals(ga, "DESPUES")
    show_campaign_goals(ga, "DESPUES")

    # Resumen
    log("\n" + "=" * 60)
    log("RESUMEN")
    log("=" * 60)
    for k, v in results.items():
        icon = "[OK] " if v.startswith("OK") else "[ERR]"
        log(f"  {k}: {icon} {v}")

    failed = [k for k, v in results.items() if v.startswith("ERROR")]
    if failed:
        log(f"\n{len(failed)} errores: {failed}")
        sys.exit(1)
    else:
        log("\nConversiones reestructuradas exitosamente.")


if __name__ == "__main__":
    main()
