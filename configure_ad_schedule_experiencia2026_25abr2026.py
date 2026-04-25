"""
Fase 3 - Configurar ad schedule en Thai Merida - Experiencia 2026.
Schedule simple sin bid adjustments, basado en horario del restaurante
con margen de planificacion (+2h manana).
Solo modifica campaign_criterion de tipo AD_SCHEDULE en esta campana.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Experiencia 2026"

REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "configure_ad_schedule_experiencia2026_25abr2026.md",
)

TARGET_SCHEDULE = [
    {"day": "MONDAY",    "start_h": 10, "end_h": 23},
    {"day": "TUESDAY",   "start_h": 10, "end_h": 23},
    {"day": "WEDNESDAY", "start_h": 10, "end_h": 23},
    {"day": "THURSDAY",  "start_h": 10, "end_h": 23},
    {"day": "FRIDAY",    "start_h": 10, "end_h": 23},
    {"day": "SATURDAY",  "start_h": 10, "end_h": 23},
    {"day": "SUNDAY",    "start_h": 10, "end_h": 20},
]

DOW_ES = {
    "MONDAY": "Lunes", "TUESDAY": "Martes", "WEDNESDAY": "Miercoles",
    "THURSDAY": "Jueves", "FRIDAY": "Viernes", "SATURDAY": "Sabado",
    "SUNDAY": "Domingo",
}

DAY_REASON = {
    "MONDAY":    "Horario completo con margen planificacion",
    "TUESDAY":   "Horario completo con margen planificacion",
    "WEDNESDAY": "Horario completo con margen planificacion",
    "THURSDAY":  "Horario completo con margen planificacion",
    "FRIDAY":    "Horario completo con margen planificacion",
    "SATURDAY":  "Horario completo con margen planificacion",
    "SUNDAY":    "Cierre temprano 19h + 1h margen",
}


def q(ga, query):
    return list(ga.search(customer_id=CUSTOMER_ID, query=query))


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    cc_service = client.get_service("CampaignCriterionService")

    # -- 1. Obtener campaign_id por nombre ------------------------------------
    print("1. Buscando campana por nombre...")
    rows_camp = q(ga, f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign.status = 'ENABLED'
    """)
    if not rows_camp:
        print(f"   ERROR: Campana '{CAMPAIGN_NAME}' no encontrada o no ENABLED.")
        return
    campaign = rows_camp[0].campaign
    campaign_id = str(campaign.id)
    campaign_resource = f"customers/{CUSTOMER_ID}/campaigns/{campaign_id}"
    print(f"   '{campaign.name}' | ID: {campaign_id} | Status: {campaign.status.name}")

    # -- 2. Listar ad_schedule existentes ------------------------------------
    print("2. Consultando ad_schedule existentes...")
    rows_existing = q(ga, f"""
        SELECT
          campaign_criterion.criterion_id,
          campaign_criterion.ad_schedule.day_of_week,
          campaign_criterion.ad_schedule.start_hour,
          campaign_criterion.ad_schedule.end_hour,
          campaign_criterion.ad_schedule.start_minute,
          campaign_criterion.ad_schedule.end_minute,
          campaign_criterion.bid_modifier,
          campaign_criterion.status,
          campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign_criterion.type = 'AD_SCHEDULE'
        ORDER BY campaign_criterion.ad_schedule.day_of_week
    """)

    existing_schedules = []
    for r in rows_existing:
        cc = r.campaign_criterion
        day_name = cc.ad_schedule.day_of_week.name
        existing_schedules.append({
            "criterion_id": str(cc.criterion_id),
            "resource_name": cc.resource_name,
            "day": day_name,
            "start_h": cc.ad_schedule.start_hour,
            "end_h": cc.ad_schedule.end_hour,
            "bid_modifier": cc.bid_modifier,
            "status": cc.status.name,
        })
        print(f"   Existente: {day_name} "
              f"{cc.ad_schedule.start_hour:02d}:00-{cc.ad_schedule.end_hour:02d}:00 "
              f"| modifier={cc.bid_modifier:.2f} | status={cc.status.name}")

    if not existing_schedules:
        print("   (ninguno — campana activa 24/7 por defecto)")

    # -- 3. Construir operaciones (removes primero, luego adds) ---------------
    print("\n3. Construyendo operaciones...")
    ops = []
    op_meta = []  # (action, day) para logging

    # Remove operations
    for s in existing_schedules:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = s["resource_name"]
        ops.append(op)
        op_meta.append(("REMOVE", s["day"], s["start_h"], s["end_h"]))
        print(f"   REMOVE: {s['day']} {s['start_h']:02d}:00-{s['end_h']:02d}:00")

    # Add operations
    dow_enum = client.enums.DayOfWeekEnum
    minute_enum = client.enums.MinuteOfHourEnum

    day_map = {
        "MONDAY":    dow_enum.MONDAY,
        "TUESDAY":   dow_enum.TUESDAY,
        "WEDNESDAY": dow_enum.WEDNESDAY,
        "THURSDAY":  dow_enum.THURSDAY,
        "FRIDAY":    dow_enum.FRIDAY,
        "SATURDAY":  dow_enum.SATURDAY,
        "SUNDAY":    dow_enum.SUNDAY,
    }

    for entry in TARGET_SCHEDULE:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_resource
        cc.ad_schedule.day_of_week = day_map[entry["day"]]
        cc.ad_schedule.start_hour = entry["start_h"]
        cc.ad_schedule.end_hour = entry["end_h"]
        cc.ad_schedule.start_minute = minute_enum.ZERO
        cc.ad_schedule.end_minute = minute_enum.ZERO
        ops.append(op)
        op_meta.append(("ADD", entry["day"], entry["start_h"], entry["end_h"]))
        print(f"   ADD:    {entry['day']} {entry['start_h']:02d}:00-{entry['end_h']:02d}:00")

    n_removes = len(existing_schedules)
    n_adds = len(TARGET_SCHEDULE)
    print(f"\n   Total: {n_removes} removes + {n_adds} adds = {len(ops)} operaciones")

    # -- 4. Ejecutar mutacion ------------------------------------------------
    print("\n4. Ejecutando mutate_campaign_criteria...")
    results = []
    global_error = None

    try:
        resp = cc_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=ops,
        )
        add_results = [r for r in resp.results if r.resource_name]
        add_idx = 0
        for action, day, sh, eh in op_meta:
            if action == "REMOVE":
                results.append({"action": "REMOVE", "day": day, "sh": sh, "eh": eh, "status": "OK", "detail": ""})
                print(f"   REMOVE OK: {day}")
            else:
                rname = add_results[add_idx].resource_name if add_idx < len(add_results) else "—"
                add_idx += 1
                results.append({"action": "ADD", "day": day, "sh": sh, "eh": eh, "status": "OK", "detail": rname})
                print(f"   ADD OK: {day} {sh:02d}:00-{eh:02d}:00")

    except GoogleAdsException as ex:
        err_msgs = [f"{e.error_code}: {e.message}" for e in ex.failure.errors]
        global_error = "; ".join(err_msgs)
        print(f"   GoogleAdsException: {global_error}")
        for action, day, sh, eh in op_meta:
            results.append({"action": action, "day": day, "sh": sh, "eh": eh, "status": "ERROR", "detail": global_error})
    except Exception as ex:
        global_error = str(ex)
        print(f"   Error inesperado: {global_error}")
        for action, day, sh, eh in op_meta:
            results.append({"action": action, "day": day, "sh": sh, "eh": eh, "status": "ERROR", "detail": global_error})

    # -- 5. Verificacion post-mutacion ---------------------------------------
    print("\n5. Verificacion post-mutacion...")
    confirmed = []
    rows_after = q(ga, f"""
        SELECT
          campaign_criterion.ad_schedule.day_of_week,
          campaign_criterion.ad_schedule.start_hour,
          campaign_criterion.ad_schedule.end_hour,
          campaign_criterion.bid_modifier,
          campaign_criterion.status
        FROM campaign_criterion
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign_criterion.type = 'AD_SCHEDULE'
        ORDER BY campaign_criterion.ad_schedule.day_of_week
    """)
    for r in rows_after:
        cc = r.campaign_criterion
        confirmed.append({
            "day": cc.ad_schedule.day_of_week.name,
            "start_h": cc.ad_schedule.start_hour,
            "end_h": cc.ad_schedule.end_hour,
            "bid_modifier": cc.bid_modifier,
            "status": cc.status.name,
        })
        print(f"   CONFIRMADO: {cc.ad_schedule.day_of_week.name} "
              f"{cc.ad_schedule.start_hour:02d}:00-{cc.ad_schedule.end_hour:02d}:00 "
              f"| modifier={cc.bid_modifier:.2f}")

    ok_count = sum(1 for r in results if r["status"] == "OK")
    err_count = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\n{'='*60}")
    print(f"RESUMEN: {ok_count} operaciones OK | {err_count} errores")
    print(f"Ad schedule confirmado: {len(confirmed)} entradas (esperado: 7)")
    print(f"{'='*60}\n")

    generate_report(run_ts, existing_schedules, confirmed, results, err_count)
    print(f"Reporte guardado: {REPORT_PATH}")


def generate_report(ts, before, after, results, err_count):
    lines = []
    lines.append("# Configuracion Ad Schedule — Thai Merida Experiencia 2026")
    lines.append("")
    lines.append(f"**Fecha/hora:** {ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Cuenta:** 4021070209  ")
    lines.append(f"**Campaña:** Thai Merida - Experiencia 2026  ")
    lines.append(f"**Operacion:** `CampaignCriterionService.mutate_campaign_criteria`  ")
    lines.append(f"**Bid adjustments:** Ninguno (1.0) — decision consciente por bajo volumen estadistico  ")
    lines.append("")
    estado = "EXITOSO" if err_count == 0 else f"PARCIAL — {err_count} errores, verificar"
    lines.append(f"**Estado:** {estado}  ")
    lines.append("")

    lines.append("## Schedule Anterior")
    lines.append("")
    if before:
        lines.append("| Dia | Inicio | Fin | Bid modifier | Status |")
        lines.append("|-----|:------:|:---:|:------------:|:------:|")
        for s in before:
            lines.append(f"| {DOW_ES.get(s['day'], s['day'])} | {s['start_h']:02d}:00 | {s['end_h']:02d}:00 | {s['bid_modifier']:.2f} | {s['status']} |")
    else:
        lines.append("_La campana no tenia ad schedule configurado (activa 24/7 por defecto)._")
    lines.append("")

    lines.append("## Schedule Nuevo Aplicado")
    lines.append("")
    lines.append("_Basado en: Lun-Sab 12-22h / Dom 12-19h (horario restaurante) + 2h planificacion manana + 1h noche._")
    lines.append("")
    lines.append("| Dia | Hora inicio | Hora fin | Bid modifier | Nota |")
    lines.append("|-----|:-----------:|:--------:|:------------:|------|")
    for entry in TARGET_SCHEDULE:
        day = entry["day"]
        lines.append(f"| {DOW_ES.get(day, day)} | {entry['start_h']:02d}:00 | {entry['end_h']:02d}:00 | 1.00 | {DAY_REASON.get(day, '')} |")
    lines.append("")

    lines.append("## Confirmacion Post-Mutacion (GAQL)")
    lines.append("")
    if after:
        lines.append("| Dia | Inicio | Fin | Bid modifier | Status |")
        lines.append("|-----|:------:|:---:|:------------:|:------:|")
        for s in after:
            # Verificar que el horario coincide con lo esperado
            expected = next((e for e in TARGET_SCHEDULE if e["day"] == s["day"]), None)
            if expected and s["start_h"] == expected["start_h"] and s["end_h"] == expected["end_h"]:
                mark = "OK"
            else:
                mark = "Revisar — horario inesperado"
            lines.append(f"| {DOW_ES.get(s['day'], s['day'])} | {s['start_h']:02d}:00 | {s['end_h']:02d}:00 | {s['bid_modifier']:.2f} | {s['status']} — {mark} |")
        lines.append("")
        lines.append(f"**Entradas confirmadas:** {len(after)} de 7 esperadas  ")
    else:
        lines.append("_No se encontraron entradas post-mutacion. Verificar en Google Ads UI._")
    lines.append("")

    error_list = [r for r in results if r["status"] == "ERROR"]
    if error_list:
        lines.append("## Errores")
        lines.append("")
        for r in error_list:
            lines.append(f"- **{r['action']} {r['day']}:** `{r['detail']}`")
        lines.append("")

    lines.append("## Recordatorio: Re-evaluacion en 60 Dias (~25 jun 2026)")
    lines.append("")
    lines.append("**Por que no se aplicaron bid adjustments:**")
    lines.append("11 conversiones en 30 dias es insuficiente para validar patrones por hora.")
    lines.append("Cada conversion individual mueve el CVR ±15-30 puntos — ruido, no señal.")
    lines.append("")
    lines.append("**Criterio para activar bid adjustments en la proxima revision:**")
    lines.append("- 50+ conversiones/mes sostenidas, O")
    lines.append("- 10+ conversiones por bloque horario a evaluar")
    lines.append("")
    lines.append("**Proceso de re-evaluacion:**")
    lines.append("1. Re-correr `_analisis_horario_experiencia2026.py`")
    lines.append("2. Si patron 10-12h y 22-23h es consistente: ajustar -20% y -10% respectivamente")
    lines.append("3. Si Experiencia 2026 ya tiene 50+ conv/mes, considerar TARGET_CPA")
    lines.append("")
    lines.append("---")
    lines.append("_Solo se modifico ad_schedule en Thai Merida - Experiencia 2026._")
    lines.append("_No se toco bidding, presupuesto, geo, audiencias ni otras campanas._")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run()
