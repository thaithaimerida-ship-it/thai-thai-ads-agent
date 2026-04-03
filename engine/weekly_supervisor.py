"""
Thai Thai Ads Agent — Supervisor Semanal (Fase 5)

Lee los últimos N días de `autonomous_decisions` y construye el bloque
de actividad del agente para el reporte ejecutivo semanal.

Funciones públicas:
  query_week_activity(db_path, days)    — consulta SQLite
  build_supervisor_data(rows)           — clasifica y agrega
  get_next_best_action(supervisor_data) — texto de próxima acción recomendada
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Dict

from engine.db_sync import get_db_path


# ── Clasificación de estados ──────────────────────────────────────────────────

# Orden canónico para mostrar en el reporte (de más a menos urgente)
STATUS_ORDER = [
    "executed",
    "pending",
    "rejected",
    "expired",
    "approved_blocked",
    "approved_registered",
    "alert",
]

STATUS_LABELS = {
    "executed":           "Ejecutado",
    "pending":            "Pendiente aprobación",
    "rejected":           "Rechazado",
    "expired":            "Expirado",
    "approved_blocked":   "Aprobado (bloqueado)",
    "approved_registered":"Aprobado (registrado)",
    "alert":              "Alerta enviada",
    "other":              "Otro",
}

STATUS_ICON = {
    "executed":           "✅",
    "pending":            "⏳",
    "rejected":           "❌",
    "expired":            "⏰",
    "approved_blocked":   "🔒",
    "approved_registered":"📋",
    "alert":              "🔔",
    "other":              "ℹ️",
}

STATUS_COLOR = {
    "executed":           "#16a34a",   # verde
    "pending":            "#d97706",   # amarillo
    "rejected":           "#dc2626",   # rojo
    "expired":            "#6b7280",   # gris
    "approved_blocked":   "#7c3aed",   # morado
    "approved_registered":"#2563eb",   # azul
    "alert":              "#ea580c",   # naranja
    "other":              "#9ca3af",   # gris claro
}


def _classify(row: dict) -> str:
    """
    Clasifica una fila de autonomous_decisions en uno de los estados del supervisor.

    Lógica:
      executed=1                                          → "executed"
      approved_at AND executed=0 AND outcome='approved_blocked'  → "approved_blocked"
      approved_at AND executed=0 AND outcome='approved_registered'→"approved_registered"
      rejected_at                                         → "rejected"
      postponed_at                                        → "expired"
      decision in ('alert_sent', 'dry_run_alert')         → "alert"
      decision == 'proposed'                              → "pending"
      else                                                → "other"
    """
    executed = int(row.get("executed", 0) or 0)
    approved_at = row.get("approved_at")
    rejected_at = row.get("rejected_at")
    postponed_at = row.get("postponed_at")
    decision = str(row.get("decision", "") or "").strip()
    approve_outcome = str(row.get("approve_outcome", "") or "").strip()

    if executed:
        return "executed"
    if approved_at and not executed:
        if approve_outcome == "approved_blocked":
            return "approved_blocked"
        if approve_outcome == "approved_registered":
            return "approved_registered"
    if rejected_at:
        return "rejected"
    if postponed_at:
        return "expired"
    if decision in ("alert_sent", "dry_run_alert"):
        return "alert"
    if decision == "proposed":
        return "pending"
    return "other"


def query_week_activity(
    db_path: str = None,
    days: int = 8,
) -> List[Dict]:
    """
    Consulta las filas de autonomous_decisions de los últimos `days` días.
    Parsea evidence_json y lo fusiona en cada fila para que los helpers de
    clasificación y renderizado accedan a signal, cost_mxn, adgroup_name, etc.
    Retorna [] si la BD no existe o la tabla está vacía.
    """
    import json as _json

    resolved_path = db_path or get_db_path()
    try:
        conn = sqlite3.connect(resolved_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        cur.execute(
            """
            SELECT
                id, action_type, risk_level, urgency,
                campaign_id, campaign_name, keyword,
                evidence_json, decision, executed,
                approved_at, rejected_at, postponed_at,
                created_at, approval_token
            FROM autonomous_decisions
            WHERE created_at >= ?
            ORDER BY created_at DESC
            """,
            (cutoff,),
        )
        rows = []
        for r in cur.fetchall():
            row = dict(r)
            # Parsear evidence_json y fusionar campos relevantes al nivel del dict
            ev = {}
            if row.get("evidence_json"):
                try:
                    ev = _json.loads(row["evidence_json"])
                except Exception:
                    pass
            row["signal"]          = ev.get("signal", "")
            row["adgroup_id"]      = ev.get("adgroup_id", "")
            row["adgroup_name"]    = ev.get("adgroup_name", "")
            row["cost_mxn"]        = ev.get("cost_mxn")
            row["approve_outcome"] = ev.get("approve_outcome", "")
            row["reason"]          = ev.get("reason", "")
            rows.append(row)
        conn.close()
        return rows

    except Exception as e:
        print(f"[SUPERVISOR] Error consultando BD: {e}")
        return []


def build_supervisor_data(rows: List[Dict]) -> dict:
    """
    Agrega las filas en estructura lista para renderizar en el reporte.

    Retorna:
      by_status    — dict[status] = lista de rows clasificados
      counts       — dict[status] = int
      total_relevant — total de filas clasificadas (excluye "other")
      status_order — lista ordenada de estados
      auto_executed — lista de rows ejecutados automáticamente (sin aprobación)
    """
    by_status: Dict[str, List[dict]] = {s: [] for s in STATUS_ORDER}
    by_status["other"] = []

    for row in rows:
        status = _classify(row)
        row["_status"] = status
        row["_auto_executed"] = (
            status == "executed"
            and not row.get("approved_at")
        )
        bucket = by_status.get(status, by_status["other"])
        bucket.append(row)

    counts = {s: len(by_status[s]) for s in STATUS_ORDER}
    total_relevant = sum(counts[s] for s in STATUS_ORDER)

    auto_executed = [r for r in by_status["executed"] if r["_auto_executed"]]

    return {
        "by_status": by_status,
        "counts": counts,
        "total_relevant": total_relevant,
        "status_order": STATUS_ORDER,
        "auto_executed": auto_executed,
    }


def get_next_best_action(supervisor_data: dict) -> str:
    """
    Genera el texto de la próxima acción recomendada al supervisor.

    Prioridad:
      1. pending        → aprobar o rechazar la propuesta más costosa
      2. approved_blocked → revisar por qué la pausa quedó bloqueada
      3. alert          → revisar la alerta enviada
      4. executed       → revisar que la acción ejecutada fue correcta
      5. sin incidencias → confirmación positiva
    """
    counts = supervisor_data.get("counts", {})
    by_status = supervisor_data.get("by_status", {})

    pending = by_status.get("pending", [])
    if pending:
        # Mostrar la de mayor gasto
        top = sorted(pending, key=lambda r: float(r.get("cost_mxn") or 0), reverse=True)[0]
        name = top.get("keyword") or top.get("adgroup_name") or top.get("signal") or "propuesta"
        cost = top.get("cost_mxn")
        cost_str = f"${cost:,.0f} MXN" if cost else ""
        return (
            f"Hay {len(pending)} propuesta(s) pendiente(s) de aprobación. "
            f"La más urgente: «{name}»{' · ' + cost_str if cost_str else ''}. "
            f"Revisa el correo de propuesta y aprueba o rechaza."
        )

    approved_blocked = by_status.get("approved_blocked", [])
    if approved_blocked:
        return (
            f"Hay {len(approved_blocked)} acción(es) aprobada(s) pero bloqueada(s) por "
            f"las guardas de seguridad. Revisa el log del agente para más detalles."
        )

    alerts = by_status.get("alert", [])
    if alerts:
        return (
            f"Se enviaron {len(alerts)} alerta(s) esta semana. "
            f"Verifica que las campañas afectadas hayan sido atendidas."
        )

    executed = by_status.get("executed", [])
    if executed:
        return (
            f"El agente ejecutó {len(executed)} acción(es) automáticamente esta semana. "
            f"Revisa el detalle abajo para confirmar que fue correcto."
        )

    return "Sin incidencias esta semana. El agente operó en modo observación."
