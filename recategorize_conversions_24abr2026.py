"""
Fase 2 — Recategorizar 4 conversiones: Primaria → Secundaria (primary_for_goal=False)
Operación de escritura acotada: solo cambia primary_for_goal.
No modifica status, value_settings, counting_type ni lookback_window.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "recategorize_conversions_24abr2026.md",
)

# 4 conversiones a cambiar a secundaria (primary_for_goal=False)
TARGET_CONVERSIONS = [
    "Thai Thai Merida (web) reserva_completada",
    "reserva_completada_directa",
    "Contacto (Evento de Google Analytics click_ubicacion)",
    "Pedido GloriaFood Online",
]

# Conversiones que DEBEN mantenerse primarias — doble verificación
KEEP_PRIMARY = {
    "Thai Thai Merida (web) click_pedir_online",
    "Contacto (Evento de Google Analytics click_whatsapp)",
}

# Conversiones de sistema — no intentar mutar (MUTATE_NOT_ALLOWED)
SYSTEM_CONVERSIONS = {
    "Local actions - Directions",
    "Calls from Smart Campaign Ads",
    "Smart campaign ad clicks to call",
    "Smart campaign map directions",
}


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga_service = client.get_service("GoogleAdsService")
    ca_service = client.get_service("ConversionActionService")

    # ── 1. Obtener todas las conversiones ENABLED ─────────────────────────────
    q = """
        SELECT
          conversion_action.id,
          conversion_action.name,
          conversion_action.type,
          conversion_action.primary_for_goal,
          conversion_action.include_in_conversions_metric,
          conversion_action.status,
          conversion_action.resource_name
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
        ORDER BY conversion_action.name
    """
    print("Consultando conversiones ENABLED...")
    all_ca = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=q):
        ca = row.conversion_action
        all_ca[ca.name] = {
            "id": str(ca.id),
            "resource_name": ca.resource_name,
            "type": ca.type_.name if hasattr(ca.type_, "name") else str(ca.type_),
            "primary_for_goal_before": ca.primary_for_goal,
            "include_in_conversions_before": ca.include_in_conversions_metric,
            "primary_for_goal_after": ca.primary_for_goal,
            "result": "NOT ATTEMPTED",
        }

    print(f"  → {len(all_ca)} conversiones ENABLED encontradas")

    # ── 2. Mutar cada conversión objetivo ─────────────────────────────────────
    changed_ok = []
    already_secondary = []
    not_found = []
    errors = []

    for name in TARGET_CONVERSIONS:
        # Doble verificación: nunca tocar las que deben mantenerse primarias
        if name in KEEP_PRIMARY:
            print(f"  SKIP (keep primary): {name}")
            continue

        if name in SYSTEM_CONVERSIONS:
            print(f"  SKIP (sistema, MUTATE_NOT_ALLOWED): {name}")
            continue

        if name not in all_ca:
            print(f"  NOT FOUND: {name}")
            not_found.append(name)
            continue

        ca_data = all_ca[name]

        if not ca_data["primary_for_goal_before"]:
            print(f"  ALREADY_SECONDARY: {name} — primary_for_goal ya es False")
            ca_data["result"] = "ALREADY_SECONDARY"
            already_secondary.append(name)
            continue

        # Construir operación de recategorización
        op = client.get_type("ConversionActionOperation")
        op.update.resource_name = ca_data["resource_name"]
        op.update.primary_for_goal = False
        op.update_mask.paths[:] = ["primary_for_goal"]

        try:
            resp = ca_service.mutate_conversion_actions(
                customer_id=CUSTOMER_ID, operations=[op]
            )
            ca_data["primary_for_goal_after"] = False
            ca_data["result"] = "OK"
            changed_ok.append(name)
            print(f"  ✓ SECUNDARIA: {name} (id={ca_data['id']})")
        except GoogleAdsException as ex:
            err_msgs = [
                f"{e.error_code}: {e.message}" for e in ex.failure.errors
            ]
            err_str = "; ".join(err_msgs)
            ca_data["result"] = f"ERROR: {err_str}"
            errors.append((name, err_str))
            print(f"  ✗ ERROR en {name}: {err_str}")
        except Exception as ex:
            ca_data["result"] = f"ERROR: {ex}"
            errors.append((name, str(ex)))
            print(f"  ✗ ERROR en {name}: {ex}")

    # ── 3. Verificación post-ejecución ────────────────────────────────────────
    print("\nVerificando estado final de todas las conversiones ENABLED...")
    q_verify = """
        SELECT
          conversion_action.id,
          conversion_action.name,
          conversion_action.type,
          conversion_action.primary_for_goal,
          conversion_action.status
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
        ORDER BY conversion_action.primary_for_goal DESC, conversion_action.name
    """
    final_state = {}
    for row in ga_service.search(customer_id=CUSTOMER_ID, query=q_verify):
        ca = row.conversion_action
        pfg = ca.primary_for_goal
        tipo = ca.type_.name if hasattr(ca.type_, "name") else str(ca.type_)
        final_state[ca.name] = {
            "id": str(ca.id),
            "type": tipo,
            "primary_for_goal": pfg,
        }
        label = "PRIMARIA ✅" if pfg else "secundaria  "
        print(f"  {label}  {ca.name}")

    # Actualizar after con datos reales confirmados
    for name, data in final_state.items():
        if name in all_ca:
            all_ca[name]["primary_for_goal_after"] = data["primary_for_goal"]

    # ── 4. Resumen en consola ─────────────────────────────────────────────────
    total_target = len(TARGET_CONVERSIONS)
    total_ok = len(changed_ok) + len(already_secondary)
    print(f"\n{'='*60}")
    print(f"RESUMEN: {total_ok} de {total_target} en estado secundario")
    print(f"  Cambiadas: {len(changed_ok)} | Ya eran secundarias: {len(already_secondary)}")
    if not_found:
        print(f"  NOT FOUND ({len(not_found)}): {', '.join(not_found)}")
    if errors:
        print(f"  ERRORES ({len(errors)}):")
        for name, err in errors:
            print(f"    - {name}: {err}")

    # Verificar que las protegidas siguen primarias
    for name in KEEP_PRIMARY:
        if name in final_state:
            ok = final_state[name]["primary_for_goal"]
            status = "✅ PRIMARIA (correcto)" if ok else "⚠️ INESPERADO — revisar"
            print(f"  Verificación guardada: '{name}' → {status}")
    print(f"{'='*60}\n")

    # ── 5. Generar reporte Markdown ───────────────────────────────────────────
    lines = []
    lines.append("# Fase 2 — Recategorización de Conversiones Primarias → Secundarias")
    lines.append("")
    lines.append(f"**Fecha/hora:** {run_ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Cuenta:** {CUSTOMER_ID}  ")
    lines.append(f"**Campo modificado:** `primary_for_goal` True → False  ")
    lines.append(f"**No se modificó:** status, value_settings, counting_type, lookback_window  ")
    lines.append("")

    lines.append("## Resultado de Ejecución")
    lines.append("")
    lines.append("| Resultado | Cantidad |")
    lines.append("|-----------|----------|")
    lines.append(f"| Cambiadas a secundaria exitosamente | {len(changed_ok)} |")
    lines.append(f"| Ya eran secundarias (sin cambio) | {len(already_secondary)} |")
    lines.append(f"| No encontradas | {len(not_found)} |")
    lines.append(f"| Errores | {len(errors)} |")
    lines.append("")

    lines.append("## Detalle: 4 Conversiones Objetivo")
    lines.append("")
    lines.append("| Nombre | ID | Tipo | Antes | Después | Resultado |")
    lines.append("|--------|----|------|:-----:|:-------:|-----------|")
    for name in TARGET_CONVERSIONS:
        if name in all_ca:
            d = all_ca[name]
            antes = "PRIMARIA" if d["primary_for_goal_before"] else "secundaria"
            despues = "PRIMARIA" if d["primary_for_goal_after"] else "secundaria"
            lines.append(
                f"| {name} | {d['id']} | {d['type']} | {antes} | {despues} | {d['result']} |"
            )
        else:
            lines.append(f"| {name} | — | — | — | — | NOT FOUND |")
    lines.append("")

    lines.append("## Verificación: Conversiones Protegidas (deben mantenerse primarias)")
    lines.append("")
    lines.append("| Nombre | ID | primary_for_goal final | Estado |")
    lines.append("|--------|----|:----------------------:|--------|")
    for name in sorted(KEEP_PRIMARY):
        if name in final_state:
            d = final_state[name]
            pfg = d["primary_for_goal"]
            estado = "✅ CORRECTO — sigue primaria" if pfg else "🚨 ERROR — cambió inesperadamente"
            lines.append(f"| {name} | {d['id']} | {pfg} | {estado} |")
        else:
            lines.append(f"| {name} | — | no encontrada | ⚠️ revisar |")
    lines.append("")

    if errors:
        lines.append("## Errores")
        lines.append("")
        for name, err in errors:
            lines.append(f"- **{name}:** `{err}`")
        lines.append("")

    if not_found:
        lines.append("## No Encontradas")
        lines.append("")
        for name in not_found:
            lines.append(f"- `{name}` — verificar nombre exacto en Google Ads UI")
        lines.append("")

    lines.append("## Estado Final — Todas las Conversiones ENABLED")
    lines.append("")
    lines.append("_Confirmado via GAQL post-ejecución (ordenado: primarias primero):_")
    lines.append("")
    lines.append("| Nombre | ID | Tipo | primary_for_goal |")
    lines.append("|--------|----|------|:----------------:|")
    for name, d in sorted(final_state.items(), key=lambda x: (not x[1]["primary_for_goal"], x[0])):
        pfg_label = "✅ PRIMARIA" if d["primary_for_goal"] else "secundaria"
        lines.append(f"| {name} | {d['id']} | {d['type']} | {pfg_label} |")
    lines.append("")

    lines.append("## Pendiente: Conversiones de Sistema (requieren UI manual)")
    lines.append("")
    lines.append("Estas 4 conversiones devuelven `MUTATE_NOT_ALLOWED` via API.")
    lines.append("Deben cambiarse manualmente en Google Ads UI:")
    lines.append("**Herramientas → Conversiones → [nombre] → Configuración → Incluir en conversiones → No**")
    lines.append("")
    lines.append("| Conversión | Tipo | Razón |")
    lines.append("|------------|------|-------|")
    lines.append("| Local actions - Directions | GOOGLE_HOSTED | 716 conv/mes artificiales — micro-conversión |")
    lines.append("| Calls from Smart Campaign Ads | SMART_CAMPAIGN_TRACKED_CALLS | Llamadas auto-rastreadas, no verificables |")
    lines.append("| Smart campaign ad clicks to call | SMART_CAMPAIGN_AD_CLICKS_TO_CALL | Engagement, no conversión de negocio |")
    lines.append("| Smart campaign map directions | SMART_CAMPAIGN_MAP_DIRECTIONS | Duplica Local actions - Directions |")
    lines.append("")

    lines.append("---")
    lines.append(
        "_Operación completada. Solo se modificó `primary_for_goal` en las conversiones listadas._"
    )

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✓ Reporte guardado: {REPORT_PATH}")


if __name__ == "__main__":
    run()
