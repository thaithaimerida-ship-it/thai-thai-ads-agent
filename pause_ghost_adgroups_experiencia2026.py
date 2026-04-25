"""
Fase 1 — Pausar 12 ad groups fantasma: Thai Mérida - Experiencia 2026
Operación de escritura acotada: solo cambia status ENABLED → PAUSED.
No modifica keywords, anuncios, presupuesto ni estrategia de bidding.
"""
import os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Experiencia 2026"
REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "experiencia2026_pause_fantasmas_24abr2026.md",
)

TARGET_ADGROUPS = [
    "Restaurante Tailandes Merida 2026",
    "Restaurante Tailandés Mérida",
    "Thai Thai Marca",
    "Restaurante Tailandés Mérida - Cat",
    "Restaurante Tailandes Merida",
    "Thai Thai Merida - Branded 2026",
    "Thai Thai Merida Branded",
    "Thai Thai Mérida - Branded 2026",
    "Restaurante Tailandes Merida - Cat",
    "Branded Thai Thai Merida",
    "Thai Thai Merida Brand",
    "Brand Thai Thai Merida",
]

SAFE_ADGROUPS = {
    "Comida Auténtica",
    "Turistas (Inglés)",
    "Experiencia Thai",
    "Rest. Tailandés Mérida - Category",
    "Categoria Tailandes Merida",
    "Restaurante Tailandés Mérida 2026",
}


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga_service = client.get_service("GoogleAdsService")
    ag_service = client.get_service("AdGroupService")

    # ── 1. Obtener todos los ad groups de la campaña ──────────────────────────
    q = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.resource_name
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND ad_group.status != 'REMOVED'
        ORDER BY ad_group.name
    """
    print(f"Consultando ad groups en '{CAMPAIGN_NAME}'...")
    all_ag = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=q):
        ag = row.ad_group
        name = ag.name
        status = ag.status.name if hasattr(ag.status, "name") else str(ag.status)
        all_ag[name] = {
            "id": str(ag.id),
            "resource_name": ag.resource_name,
            "status_before": status,
            "status_after": status,
            "result": "NOT ATTEMPTED",
        }

    print(f"  → {len(all_ag)} ad groups encontrados")

    # ── 2. Pausar cada ad group de la lista objetivo ──────────────────────────
    paused_ok = []
    not_found = []
    errors = []
    skipped_safe = []

    for name in TARGET_ADGROUPS:
        if name in SAFE_ADGROUPS:
            print(f"  SKIP (safe list): {name}")
            skipped_safe.append(name)
            continue

        if name not in all_ag:
            print(f"  NOT FOUND: {name}")
            not_found.append(name)
            continue

        ag_data = all_ag[name]

        if ag_data["status_before"] == "PAUSED":
            print(f"  YA PAUSADO: {name} — sin cambio necesario")
            ag_data["result"] = "ALREADY_PAUSED"
            paused_ok.append(name)
            continue

        # Construir operación de pausa
        op = client.get_type("AdGroupOperation")
        op.update.resource_name = ag_data["resource_name"]
        op.update.status = client.enums.AdGroupStatusEnum.PAUSED
        op.update_mask.paths[:] = ["status"]

        try:
            resp = ag_service.mutate_ad_groups(
                customer_id=CUSTOMER_ID, operations=[op]
            )
            ag_data["status_after"] = "PAUSED"
            ag_data["result"] = "OK"
            paused_ok.append(name)
            print(f"  ✓ PAUSADO: {name} (id={ag_data['id']})")
        except GoogleAdsException as ex:
            err_msg = "; ".join(
                f"{e.error_code}: {e.message}"
                for e in ex.failure.errors
            )
            ag_data["result"] = f"ERROR: {err_msg}"
            errors.append((name, err_msg))
            print(f"  ✗ ERROR pausando {name}: {err_msg}")
        except Exception as ex:
            ag_data["result"] = f"ERROR: {ex}"
            errors.append((name, str(ex)))
            print(f"  ✗ ERROR pausando {name}: {ex}")

    # ── 3. Verificación post-ejecución ────────────────────────────────────────
    print("\nVerificando status final de todos los ad groups...")
    q_verify = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status
        FROM ad_group
        WHERE campaign.name = '{CAMPAIGN_NAME}'
        ORDER BY ad_group.name
    """
    final_status = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=q_verify):
        ag = row.ad_group
        status = ag.status.name if hasattr(ag.status, "name") else str(ag.status)
        final_status[ag.name] = {"id": str(ag.id), "status": status}
        print(f"  {ag.name:<55} {status}")

    # Actualizar status_after con los datos reales confirmados
    for name, data in final_status.items():
        if name in all_ag:
            all_ag[name]["status_after"] = data["status"]

    # ── 4. Resumen en consola ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESUMEN: {len(paused_ok)} de {len(TARGET_ADGROUPS)} pausados/ya-pausados")
    if not_found:
        print(f"  NOT FOUND ({len(not_found)}): {', '.join(not_found)}")
    if errors:
        print(f"  ERRORES ({len(errors)}):")
        for name, err in errors:
            print(f"    - {name}: {err}")
    print(f"{'='*60}\n")

    # ── 5. Generar reporte Markdown ───────────────────────────────────────────
    lines = []
    lines.append("# Fase 1 — Pausa de Ad Groups Fantasma: Experiencia 2026")
    lines.append("")
    lines.append(f"**Fecha/hora:** {run_ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Campaña:** {CAMPAIGN_NAME}  ")
    lines.append(f"**Cuenta:** {CUSTOMER_ID}  ")
    lines.append(f"**Objetivo:** Pausar 12 ad groups con 0 clicks y 0 impresiones en 30 días  ")
    lines.append("")

    lines.append("## Resultado de Ejecución")
    lines.append("")
    lines.append(f"| Resultado | Cantidad |")
    lines.append(f"|-----------|----------|")
    lines.append(f"| Pausados exitosamente | {len([n for n in paused_ok if all_ag.get(n, {}).get('result') == 'OK'])} |")
    lines.append(f"| Ya estaban pausados | {len([n for n in paused_ok if all_ag.get(n, {}).get('result') == 'ALREADY_PAUSED'])} |")
    lines.append(f"| No encontrados | {len(not_found)} |")
    lines.append(f"| Errores | {len(errors)} |")
    lines.append("")

    lines.append("## Detalle: 12 Ad Groups Objetivo")
    lines.append("")
    lines.append("| Ad Group | ID | Status Antes | Status Después | Resultado |")
    lines.append("|----------|----|-------------|----------------|-----------|")
    for name in TARGET_ADGROUPS:
        if name in all_ag:
            d = all_ag[name]
            lines.append(
                f"| {name} | {d['id']} | {d['status_before']} | {d['status_after']} | {d['result']} |"
            )
        else:
            lines.append(f"| {name} | — | — | — | NOT FOUND |")
    lines.append("")

    if not_found:
        lines.append("## Ad Groups No Encontrados")
        lines.append("")
        lines.append("Los siguientes nombres no se hallaron en la campaña (revisar manualmente):")
        lines.append("")
        for name in not_found:
            lines.append(f"- `{name}`")
        lines.append("")

    if errors:
        lines.append("## Errores")
        lines.append("")
        for name, err in errors:
            lines.append(f"- **{name}:** {err}")
        lines.append("")

    lines.append("## Estado Final — Todos los Ad Groups de la Campaña")
    lines.append("")
    lines.append("_Confirmado via GAQL post-ejecución:_")
    lines.append("")
    lines.append("| Ad Group | ID | Status Final |")
    lines.append("|----------|-----|-------------|")
    for name, data in sorted(final_status.items()):
        tag = " ✅" if name in SAFE_ADGROUPS else (" ⏸️" if data["status"] == "PAUSED" else "")
        lines.append(f"| {name}{tag} | {data['id']} | {data['status']} |")
    lines.append("")

    lines.append("---")
    lines.append("_Operación completada. Solo se modificó el campo `status` de los ad groups listados._")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✓ Reporte guardado: {REPORT_PATH}")


if __name__ == "__main__":
    run()
