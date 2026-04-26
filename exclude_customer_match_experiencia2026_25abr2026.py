"""
QW6 - Excluir segmento Customer Match "Clientes GloriaFood 2023-2026"
de la campaña "Thai Mérida - Experiencia 2026".
negative=True a nivel campaña via CampaignCriterionService.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Experiencia 2026"
USER_LIST_NAME = "Clientes GloriaFood 2023-2026"

REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "exclude_customer_match_experiencia2026_25abr2026.md",
)


def q(ga, query):
    return list(ga.search(customer_id=CUSTOMER_ID, query=query))


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    cc_service = client.get_service("CampaignCriterionService")

    # -- 1. Obtener user_list ID ---------------------------------------------
    print(f"1. Buscando user_list '{USER_LIST_NAME}'...")
    rows_ul = q(ga, f"""
        SELECT
          user_list.id,
          user_list.name,
          user_list.size_for_search,
          user_list.resource_name
        FROM user_list
        WHERE user_list.name = '{USER_LIST_NAME}'
    """)
    if not rows_ul:
        print(f"   ERROR: user_list '{USER_LIST_NAME}' no encontrado.")
        return
    ul = rows_ul[0].user_list
    ul_id = str(ul.id)
    ul_resource = ul.resource_name
    ul_size = ul.size_for_search
    print(f"   '{ul.name}' | ID: {ul_id} | Miembros search: {ul_size} | Resource: {ul_resource}")

    # -- 2. Obtener campaign ID ----------------------------------------------
    print(f"\n2. Buscando campaña '{CAMPAIGN_NAME}'...")
    rows_camp = q(ga, f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.resource_name
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign.status = 'ENABLED'
    """)
    if not rows_camp:
        print(f"   ERROR: Campaña '{CAMPAIGN_NAME}' no encontrada o no ENABLED.")
        return
    camp = rows_camp[0].campaign
    camp_id = str(camp.id)
    camp_resource = camp.resource_name
    print(f"   '{camp.name}' | ID: {camp_id} | Status: {camp.status.name}")

    # -- 3. Verificar exclusiones USER_LIST actuales en la campaña -----------
    print(f"\n3. Verificando exclusiones USER_LIST existentes en '{CAMPAIGN_NAME}'...")
    rows_cc = q(ga, f"""
        SELECT
          campaign_criterion.criterion_id,
          campaign_criterion.user_list.user_list,
          campaign_criterion.negative,
          campaign_criterion.status,
          campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign_criterion.type = 'USER_LIST'
    """)

    existing = []
    already_excluded = False
    for r in rows_cc:
        cc = r.campaign_criterion
        existing.append({
            "criterion_id": str(cc.criterion_id),
            "user_list_resource": cc.user_list.user_list,
            "negative": cc.negative,
            "status": cc.status.name,
            "resource_name": cc.resource_name,
        })
        is_target = ul_resource in cc.user_list.user_list or cc.user_list.user_list in ul_resource
        neg_label = "EXCLUSION (negative=True)" if cc.negative else "INCLUSION (negative=False)"
        match_label = " <-- ESTE ES EL SEGMENTO OBJETIVO" if is_target else ""
        print(f"   Criterio {cc.criterion_id}: {cc.user_list.user_list} | {neg_label}{match_label}")
        if is_target and cc.negative:
            already_excluded = True

    if not existing:
        print("   (ninguna exclusion/inclusion USER_LIST encontrada)")

    if already_excluded:
        print(f"\n   ALREADY_EXCLUDED: '{USER_LIST_NAME}' ya esta excluida de '{CAMPAIGN_NAME}'.")
        print("   No se ejecutara ninguna mutacion.")
        generate_report(
            run_ts, ul_id, ul_resource, ul_size, camp_id, camp_resource,
            existing, result="ALREADY_EXCLUDED", confirmed=existing, error=None
        )
        print(f"\nReporte guardado: {REPORT_PATH}")
        return

    # -- 4. Crear exclusion --------------------------------------------------
    print(f"\n4. Creando exclusion de '{USER_LIST_NAME}' en '{CAMPAIGN_NAME}'...")
    op = client.get_type("CampaignCriterionOperation")
    cc = op.create
    cc.campaign = camp_resource
    cc.user_list.user_list = ul_resource
    cc.negative = True

    result_status = None
    error_msg = None
    new_resource = None

    try:
        resp = cc_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=[op],
        )
        new_resource = resp.results[0].resource_name if resp.results else "—"
        result_status = "OK"
        print(f"   OK: exclusion creada -> {new_resource}")
    except GoogleAdsException as ex:
        err_msgs = [f"{e.error_code}: {e.message}" for e in ex.failure.errors]
        error_msg = "; ".join(err_msgs)
        result_status = "ERROR"
        print(f"   GoogleAdsException: {error_msg}")
    except Exception as ex:
        error_msg = str(ex)
        result_status = "ERROR"
        print(f"   Error inesperado: {error_msg}")

    # -- 5. Verificacion post-mutacion ---------------------------------------
    print("\n5. Verificacion post-mutacion...")
    rows_after = q(ga, f"""
        SELECT
          campaign_criterion.criterion_id,
          campaign_criterion.user_list.user_list,
          campaign_criterion.negative,
          campaign_criterion.status,
          campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign_criterion.type = 'USER_LIST'
    """)

    confirmed = []
    exclusion_confirmed = False
    for r in rows_after:
        cc = r.campaign_criterion
        is_target = ul_resource in cc.user_list.user_list or cc.user_list.user_list in ul_resource
        confirmed.append({
            "criterion_id": str(cc.criterion_id),
            "user_list_resource": cc.user_list.user_list,
            "negative": cc.negative,
            "status": cc.status.name,
            "resource_name": cc.resource_name,
        })
        neg_label = "EXCLUSION" if cc.negative else "INCLUSION"
        target_label = " <-- OBJETIVO CONFIRMADO" if (is_target and cc.negative) else ""
        print(f"   {neg_label}: {cc.user_list.user_list} | status={cc.status.name}{target_label}")
        if is_target and cc.negative:
            exclusion_confirmed = True

    if exclusion_confirmed:
        print("   CONFIRMADO: exclusion activa y verificada via GAQL.")
    else:
        print("   ADVERTENCIA: no se encontro la exclusion en la verificacion post-mutacion.")

    print(f"\n{'='*60}")
    print(f"RESUMEN: {result_status} | Exclusion confirmada: {exclusion_confirmed}")
    print(f"{'='*60}\n")

    generate_report(
        run_ts, ul_id, ul_resource, ul_size, camp_id, camp_resource,
        existing, result=result_status, confirmed=confirmed, error=error_msg
    )
    print(f"Reporte guardado: {REPORT_PATH}")


def generate_report(ts, ul_id, ul_resource, ul_size, camp_id, camp_resource,
                    before, result, confirmed, error):
    lines = []
    lines.append("# QW6: Exclusion Customer Match — Thai Merida Experiencia 2026")
    lines.append("")
    lines.append(f"**Fecha/hora:** {ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Cuenta:** 4021070209  ")
    lines.append(f"**Operacion:** `CampaignCriterionService.mutate_campaign_criteria` — `negative=True`  ")
    lines.append("")

    estado_label = {
        "OK": "EXITOSO — exclusion aplicada y confirmada",
        "ALREADY_EXCLUDED": "SIN CAMBIO — la exclusion ya existia",
        "ERROR": f"ERROR — {error}",
    }.get(result, result)
    lines.append(f"**Estado:** {estado_label}  ")
    lines.append("")

    lines.append("## Segmento Excluido")
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("|-------|-------|")
    lines.append(f"| Nombre | Clientes GloriaFood 2023-2026 |")
    lines.append(f"| ID | {ul_id} |")
    lines.append(f"| Miembros activos (search) | {ul_size} |")
    lines.append(f"| Resource name | `{ul_resource}` |")
    lines.append("")

    lines.append("## Campaña Afectada")
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("|-------|-------|")
    lines.append(f"| Nombre | Thai Merida - Experiencia 2026 |")
    lines.append(f"| ID | {camp_id} |")
    lines.append(f"| Resource name | `{camp_resource}` |")
    lines.append(f"| Tipo | Search (ENABLED) |")
    lines.append("")

    lines.append("## Estado Pre-Mutacion")
    lines.append("")
    if before:
        lines.append("| Criterio ID | User List | Tipo | Status |")
        lines.append("|-------------|-----------|:----:|:------:|")
        for b in before:
            tipo = "EXCLUSION" if b["negative"] else "INCLUSION"
            lines.append(f"| {b['criterion_id']} | `{b['user_list_resource']}` | {tipo} | {b['status']} |")
    else:
        lines.append("_Ninguna exclusion/inclusion USER_LIST existente en la campaña._")
    lines.append("")

    lines.append("## Resultado de Mutacion")
    lines.append("")
    if result == "ALREADY_EXCLUDED":
        lines.append("La exclusion ya existia antes de ejecutar. No se realizo ninguna mutacion.")
    elif result == "OK":
        lines.append("Exclusion creada exitosamente via `CampaignCriterionOperation.create` con `negative=True`.")
        lines.append("")
        lines.append("| Campo aplicado | Valor |")
        lines.append("|----------------|-------|")
        lines.append(f"| campaign | `{camp_resource}` |")
        lines.append(f"| user_list.user_list | `{ul_resource}` |")
        lines.append(f"| negative | True |")
    elif result == "ERROR":
        lines.append(f"**Error:** `{error}`")
    lines.append("")

    lines.append("## Confirmacion Post-Mutacion (GAQL)")
    lines.append("")
    if confirmed:
        lines.append("| Criterio ID | User List | Tipo | Status |")
        lines.append("|-------------|-----------|:----:|:------:|")
        for c in confirmed:
            tipo = "EXCLUSION" if c["negative"] else "INCLUSION"
            lines.append(f"| {c['criterion_id']} | `{c['user_list_resource']}` | {tipo} | {c['status']} |")
        # Verificar si la exclusion objetivo esta confirmada
        target_confirmed = any(
            c["negative"] and ul_resource in c["user_list_resource"]
            for c in confirmed
        )
        lines.append("")
        if target_confirmed:
            lines.append("**Exclusion de 'Clientes GloriaFood 2023-2026': ACTIVA y CONFIRMADA**")
        else:
            lines.append("**ADVERTENCIA: La exclusion no se encontro en verificacion post-mutacion.**")
    else:
        lines.append("_No se encontraron criterios USER_LIST post-mutacion._")
    lines.append("")

    lines.append("## Razon de Negocio")
    lines.append("")
    lines.append("Los 100 clientes activos en 'Clientes GloriaFood 2023-2026' ya conocen Thai Thai.")
    lines.append("Experiencia 2026 debe enfocarse en adquisicion de nuevos clientes, no en retargeting.")
    lines.append("La exclusion evita gastar presupuesto de adquisicion en audiencias ya convertidas.")
    lines.append("")
    lines.append("**Campanas NO afectadas (decision intencional):**")
    lines.append("- Thai Merida - Delivery: puede mostrar a clientes existentes (recompra)")
    lines.append("- Thai Merida - Local: Smart Campaign, gestion automatica")
    lines.append("- Thai Merida - Reservaciones: PAUSED")
    lines.append("")
    lines.append("---")
    lines.append("_Solo se modifico campaign_criterion USER_LIST en Thai Merida - Experiencia 2026._")
    lines.append("_No se modifico el user_list, otras campanas, bidding, presupuesto ni geo._")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run()
