"""
Fase 3 - Agregar 9 keywords de competidores como negativos [exact]
a la lista compartida "Competidores y cocinas irrelevantes" (ID: 12044624629).
Operacion de escritura acotada: solo agrega miembros a shared set existente.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
SHARED_SET_ID = "12044624629"
SHARED_SET_RESOURCE = f"customers/{CUSTOMER_ID}/sharedSets/{SHARED_SET_ID}"
SHARED_SET_NAME = "Competidores y cocinas irrelevantes"

REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "add_competitor_negatives_25abr2026.md",
)

# 9 competidores a agregar como [exact]
TARGET_KEYWORDS = [
    "manawings merida",
    "manzoku merida menu",
    "swing pasta",
    "bachour merida",
    "cienfuegos merida",
    "piedra de agua restaurante",
    "la rueda merida",
    "restaurante la herencia merida",
    "restaurante libertad merida",
]


def q(ga, query):
    return list(ga.search(customer_id=CUSTOMER_ID, query=query))


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    sc_service = client.get_service("SharedCriterionService")

    # -- 1. Verificar que el shared set existe y esta ENABLED -----------------
    print(f"1. Verificando shared set {SHARED_SET_ID}...")
    rows_ss = q(ga, f"""
        SELECT
          shared_set.id,
          shared_set.name,
          shared_set.status,
          shared_set.member_count
        FROM shared_set
        WHERE shared_set.id = {SHARED_SET_ID}
    """)
    if not rows_ss:
        print(f"   ERROR: Shared set {SHARED_SET_ID} no encontrado.")
        return
    ss = rows_ss[0].shared_set
    print(f"   '{ss.name}' | Status: {ss.status.name} | Miembros actuales: {ss.member_count}")

    # -- 2. Obtener keywords existentes para deteccion de duplicados ----------
    print("2. Consultando miembros actuales...")
    rows_sc = q(ga, f"""
        SELECT
          shared_criterion.keyword.text,
          shared_criterion.keyword.match_type
        FROM shared_criterion
        WHERE shared_set.id = {SHARED_SET_ID}
    """)
    existing = {
        (r.shared_criterion.keyword.text.lower(), r.shared_criterion.keyword.match_type.name)
        for r in rows_sc
    }
    print(f"   {len(existing)} keywords existentes en la lista")

    # -- 3. Construir operaciones ----------------------------------------------
    print("3. Preparando operaciones...")
    results = []
    ops = []

    for kw_text in TARGET_KEYWORDS:
        key = (kw_text.lower(), "EXACT")
        if key in existing:
            print(f"   SKIP (duplicado): [{kw_text}]")
            results.append({
                "keyword": kw_text,
                "match_type": "EXACT",
                "status": "ALREADY_EXISTS",
                "detail": "Ya existe en la lista",
            })
            continue

        op = client.get_type("SharedCriterionOperation")
        op.create.shared_set = SHARED_SET_RESOURCE
        op.create.keyword.text = kw_text
        op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
        ops.append((kw_text, op))
        print(f"   + [{kw_text}]")

    # -- 4. Ejecutar mutacion --------------------------------------------------
    if ops:
        print(f"\n4. Ejecutando mutate_shared_criteria ({len(ops)} operaciones)...")
        try:
            request = client.get_type("MutateSharedCriteriaRequest")
            request.customer_id = CUSTOMER_ID
            request.partial_failure = True
            for _, op in ops:
                request.operations.append(op)

            resp = sc_service.mutate_shared_criteria(request=request)

            # Mapear errores parciales por indice
            partial_errors = {}
            if resp.partial_failure_error and resp.partial_failure_error.details:
                try:
                    for detail in resp.partial_failure_error.details:
                        failure = client.get_type("GoogleAdsFailure")
                        detail_msg = type(failure).FromString(detail.value)
                        for err in detail_msg.errors:
                            if err.location.field_path_elements:
                                idx = err.location.field_path_elements[0].index
                                partial_errors[idx] = err.message
                except Exception:
                    pass

            for i, (kw_text, _) in enumerate(ops):
                if i in partial_errors:
                    err_msg = partial_errors[i]
                    print(f"   ERROR [{kw_text}]: {err_msg}")
                    results.append({
                        "keyword": kw_text,
                        "match_type": "EXACT",
                        "status": "ERROR",
                        "detail": err_msg,
                    })
                else:
                    resource = resp.results[i].resource_name if i < len(resp.results) else "-"
                    print(f"   OK [{kw_text}] -> {resource}")
                    results.append({
                        "keyword": kw_text,
                        "match_type": "EXACT",
                        "status": "OK",
                        "detail": resource,
                    })

        except GoogleAdsException as ex:
            err_msgs = [f"{e.error_code}: {e.message}" for e in ex.failure.errors]
            err_str = "; ".join(err_msgs)
            print(f"   GoogleAdsException: {err_str}")
            for kw_text, _ in ops:
                results.append({
                    "keyword": kw_text,
                    "match_type": "EXACT",
                    "status": "ERROR",
                    "detail": err_str,
                })
        except Exception as ex:
            print(f"   Error inesperado: {ex}")
            for kw_text, _ in ops:
                results.append({
                    "keyword": kw_text,
                    "match_type": "EXACT",
                    "status": "ERROR",
                    "detail": str(ex),
                })
    else:
        print("\n4. Ninguna operacion nueva (todas ya existen).")

    # -- 5. Verificacion post-mutacion ----------------------------------------
    print("\n5. Verificacion post-mutacion...")
    rows_after = q(ga, f"""
        SELECT
          shared_criterion.keyword.text,
          shared_criterion.keyword.match_type
        FROM shared_criterion
        WHERE shared_set.id = {SHARED_SET_ID}
        ORDER BY shared_criterion.keyword.text
    """)
    after_members = [
        {
            "text": r.shared_criterion.keyword.text,
            "match_type": r.shared_criterion.keyword.match_type.name,
        }
        for r in rows_after
    ]
    print(f"   {len(after_members)} keywords en la lista tras la operacion")

    ok = sum(1 for r in results if r["status"] == "OK")
    already = sum(1 for r in results if r["status"] == "ALREADY_EXISTS")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\n{'='*60}")
    print(f"RESUMEN: {ok} agregadas | {already} ya existian | {errors} errores")
    print(f"{'='*60}\n")

    generate_report(run_ts, results, after_members, ok, already, errors)
    print(f"Reporte guardado: {REPORT_PATH}")


def match_symbol(mt):
    return {"EXACT": "[exact]", "PHRASE": '"phrase"', "BROAD": "broad"}.get(mt, mt)


def generate_report(ts, results, after_members, ok, already, errors):
    lines = []
    lines.append("# Fase 3 — Agregar Competidores a Lista de Negativos")
    lines.append("")
    lines.append(f"**Fecha/hora:** {ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Cuenta:** 4021070209  ")
    lines.append(f"**Lista:** {SHARED_SET_NAME} (ID: {SHARED_SET_ID})  ")
    lines.append(f"**Operacion:** `SharedCriterionService.mutate_shared_criteria` con `partial_failure=True`  ")
    lines.append("")

    lines.append("## Resultado de Ejecucion")
    lines.append("")
    lines.append("| Resultado | Cantidad |")
    lines.append("|-----------|:--------:|")
    lines.append(f"| Agregadas exitosamente | {ok} |")
    lines.append(f"| Ya existian (sin cambio) | {already} |")
    lines.append(f"| Errores | {errors} |")
    lines.append(f"| **Total objetivo** | **{len(results)}** |")
    lines.append("")

    lines.append("## Detalle: 9 Keywords Objetivo")
    lines.append("")
    lines.append("| Keyword | Match Type | Resultado |")
    lines.append("|---------|:----------:|-----------|")
    for r in results:
        sym = match_symbol(r["match_type"])
        if r["status"] == "OK":
            status_label = "AGREGADA"
        elif r["status"] == "ALREADY_EXISTS":
            status_label = "ya existia"
        else:
            status_label = f"ERROR: {r['detail']}"
        lines.append(f"| `{r['keyword']}` | {sym} | {status_label} |")
    lines.append("")

    lines.append("## Estado Final — Contenido Completo de la Lista")
    lines.append("")
    lines.append(f"_Confirmado via GAQL post-mutacion ({len(after_members)} keywords):_")
    lines.append("")
    if after_members:
        lines.append("| Keyword | Match Type |")
        lines.append("|---------|:----------:|")
        for m in sorted(after_members, key=lambda x: x["text"]):
            lines.append(f"| `{m['text']}` | {match_symbol(m['match_type'])} |")
    else:
        lines.append("_No se encontraron miembros._")
    lines.append("")

    lines.append("## Pendiente: Aplicar Lista a Campanas Activas")
    lines.append("")
    lines.append("La lista 'Competidores y cocinas irrelevantes' actualmente solo esta aplicada a:")
    lines.append("- Thai Merida - Experiencia 2026")
    lines.append("- Thai Merida - Reservaciones (PAUSED) — vinculo inactivo")
    lines.append("")
    lines.append("**Campanas sin cobertura de esta lista:**")
    lines.append("- `Thai Merida - Delivery`")
    lines.append("- `Thai Merida - Local`")
    lines.append("")
    lines.append("Aplicar via `CampaignSharedSetService.mutate_campaign_shared_sets()` en proxima sesion.")
    lines.append("")
    lines.append("---")
    lines.append("_Operacion completada. Solo se modifico el contenido de la lista compartida._")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run()
