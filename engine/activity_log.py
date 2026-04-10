"""
Thai Thai Ads Agent — Registro de actividad del sistema

Persiste un historial compacto de cada corrida de /run-autonomous-audit
en data/system_activity.json.

Propósito:
  - Dar visibilidad de que el sistema está trabajando entre reportes semanales.
  - Registrar la última ejecución exitosa, el último cambio aplicado, y el
    último bloqueo por guarda de seguridad.
  - Servir como fuente del endpoint GET /last-activity.

El archivo nunca crece indefinidamente: se mantienen los últimos MAX_RUNS
resúmenes. Las entradas pinned apuntan siempre al evento más reciente de
cada tipo relevante.
"""

import json
import os
from datetime import datetime, timezone, timedelta

_ACTIVITY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "system_activity.json"
)
MAX_RUNS = 30   # ~1 mes de corridas diarias


# ─── Helpers de timezone ──────────────────────────────────────────────────────

_merida_tz = None
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        _merida_tz = ZoneInfo("America/Merida")
    except (ZoneInfoNotFoundError, KeyError):
        pass
except ImportError:
    pass

if _merida_tz is None:
    try:
        import pytz
        _merida_tz = pytz.timezone("America/Merida")
    except (ImportError, Exception):
        pass


def _now_merida_str() -> str:
    """Retorna la hora actual de Mérida como string legible."""
    now_utc = datetime.now(timezone.utc)
    if _merida_tz:
        local = now_utc.astimezone(_merida_tz)
    else:
        local = now_utc - timedelta(hours=6)
    return local.strftime("%Y-%m-%d %H:%M")


# ─── Derivación de resumen desde resultados de auditoría ─────────────────────

def had_successful_run_today(path: str | None = None) -> bool:
    """
    Devuelve True si ya hubo una corrida real hoy (campaigns_reviewed > 0).
    Usado por /run-compensatory-audit para evitar duplicar la auditoría.

    Fuente primaria: snapshot en GCS (persiste entre reinicios de Cloud Run).
    Fuente secundaria: archivo local data/system_activity.json (fallback).
    """
    today = _now_merida_str()[:10]   # "YYYY-MM-DD"

    # ── 1. Fuente primaria: snapshot GCS ──────────────────────────────────────
    # El snapshot se actualiza al final de cada auditoría real (_run_audit_task
    # llama mission_control_data() que llama _save_mc_snapshot). Su campo
    # _snapshot_saved_at persiste entre cold starts y reemplazos de instancia.
    try:
        from google.cloud import storage as _gcs
        _client = _gcs.Client()
        _blob = _client.bucket("thai-thai-agent-data").blob("snapshots/dashboard_snapshot.json")
        if _blob.exists():
            import json as _json
            _snap = _json.loads(_blob.download_as_text())
            _saved_at = _snap.get("_snapshot_saved_at", "")  # "YYYY-MM-DDTHH:MM:SS"
            if _saved_at[:10] == today:
                return True
    except Exception:
        pass  # GCS no disponible → caer al fallback local

    # ── 2. Fuente secundaria: archivo local ───────────────────────────────────
    target = path or _ACTIVITY_PATH
    data = _load(target)
    for run in reversed(data.get("runs", [])):
        if run.get("timestamp_merida", "")[:10] == today:
            if run.get("campaigns_reviewed", 0) > 0:
                return True
    return False


def _derive_run_summary(audit_results: dict, session_id: str, run_type: str = "daily") -> dict:
    """
    Extrae un resumen compacto del dict devuelto por /run-autonomous-audit.

    Args:
        audit_results : el dict completo devuelto por run_autonomous_audit()
        session_id    : ID de la sesión

    Returns:
        dict con campos normalizados para almacenamiento y reporting.
    """
    summary = audit_results.get("summary", {})
    now_utc = datetime.now(timezone.utc).isoformat()

    # ── Módulos ejecutados ────────────────────────────────────────────────────
    modules_run = ["tracking", "landing", "keywords", "adgroups", "observation", "budget_ba1", "geo"]

    # ── Issues detectados ─────────────────────────────────────────────────────
    tracking_signals = []
    if "tracking_alert" in audit_results:
        ta = audit_results["tracking_alert"]
        if "error" not in ta:
            tracking_signals = ta.get("signals", [])

    landing_severity = None
    if "landing_alert" in audit_results:
        la = audit_results["landing_alert"]
        if "error" not in la:
            landing_severity = la.get("severity")

    geo_issues = []
    if "geo_audit" in audit_results:
        ga = audit_results["geo_audit"]
        policy = ga.get("policy_audit", {})
        geo_issues = [e["signal"] for e in policy.get("issues", [])]
        # Capa 1
        for e in ga.get("issues", []):
            if e["signal"] == "GEO1" and e["campaign_id"] not in [g for g in geo_issues]:
                geo_issues.append(f"GEO1:{e['campaign_name']}")

    # ── Contadores de cambios y bloqueos ──────────────────────────────────────
    changes_executed   = summary.get("actually_executed", 0)

    # Contar keywords agregadas por AI
    _kw_added = len(audit_results.get("ai_keyword_proposals_executed", []))
    if not _kw_added:
        _kw_added = sum(
            1 for i in audit_results.get("executed", [])
            if "keyword" in str(i.get("type", "")).lower()
        )

    # Contar ad groups creados por Builder
    _builder_created = len([
        b for b in (audit_results.get("builder_executed", []) or [])
        if isinstance(b.get("result"), dict) and b["result"].get("status") == "success"
    ])

    # Contar campañas pausadas
    _campaigns_paused = len([
        p for p in (audit_results.get("paused_campaigns", []) or [])
        if isinstance(p.get("result"), dict) and p["result"].get("status") == "executed"
    ])

    # Total real de cambios
    _total_changes = changes_executed + _kw_added + _builder_created + _campaigns_paused
    blocked_by_guard   = (
        summary.get("by_reason", {}).get("protected_keyword", 0)
        + summary.get("by_reason", {}).get("protected_campaign", 0)
        + summary.get("by_reason", {}).get("high_risk_blocked", 0)
    )
    auto_exec_disabled = summary.get("by_reason", {}).get("auto_execute_disabled", 0)

    # ── Pendientes de validación humana ───────────────────────────────────────
    keyword_pending = summary.get("keyword_proposals_count", summary.get("proposed_for_approval", 0))

    ba_pending = 0
    if "budget_actions" in audit_results:
        ba_pending = len([
            b for b in audit_results["budget_actions"]
            if "error" not in b and b.get("decision") == "proposed"
        ])

    geo_policy_pending = len([s for s in geo_issues if s not in ("GEO0",)])

    geo_unverified = 0
    if "geo_audit" in audit_results:
        policy_correct = audit_results["geo_audit"].get("policy_audit", {}).get("correct", [])
        geo_unverified = len([
            e for e in policy_correct
            if e.get("final_operational_state") in ("unverified", "stale")
        ])

    human_pending = keyword_pending + ba_pending + geo_policy_pending + geo_unverified

    # ── Errores ───────────────────────────────────────────────────────────────
    errors = []
    if audit_results.get("tracking_alert", {}).get("error"):
        errors.append(f"tracking: {audit_results['tracking_alert']['error']}")
    if audit_results.get("landing_alert", {}).get("error"):
        errors.append(f"landing: {audit_results['landing_alert']['error']}")
    if isinstance(audit_results.get("geo_audit"), dict) and audit_results["geo_audit"].get("error"):
        errors.append(f"geo: {audit_results['geo_audit']['error']}")

    # ── Clasificación del resultado ───────────────────────────────────────────
    has_alerts = bool(
        tracking_signals
        or (landing_severity in ("critical", "warning"))
        or any(s.startswith("GEO1") for s in geo_issues)
        or any(
            i.get("urgency") in ("critical", "urgent")
            for i in audit_results.get("proposed", [])
        )
    )
    # smart_issues_count aún no está calculado aquí; lo obtenemos del audit_results
    _smart_issues_now = 0
    if "smart_audit" in audit_results and isinstance(audit_results["smart_audit"], dict):
        _smart_issues_now = audit_results["smart_audit"].get("summary", {}).get("issues_total", 0)

    if errors:
        result_class = "con_errores"
    elif has_alerts:
        result_class = "con_alertas"
    elif _total_changes > 0:
        result_class = "con_cambios"
    elif _smart_issues_now > 0:
        result_class = "con_observaciones"
    else:
        result_class = "sin_acciones"

    # ── Cobertura real de campañas por tipo ──────────────────────────────────
    # campaigns_audited puede ser un dict {search, smart, total} (nuevo formato)
    # o un int (total_evaluated, formato legado para compatibilidad)
    _campaigns_audited = summary.get("campaigns_audited", {})
    if isinstance(_campaigns_audited, dict):
        campaigns_search   = _campaigns_audited.get("search", 0)
        campaigns_smart    = _campaigns_audited.get("smart", 0)
        campaigns_reviewed = _campaigns_audited.get("total", 0)
    else:
        # Formato legado: total_evaluated contaba keywords, no campañas
        campaigns_search   = 0
        campaigns_smart    = 0
        campaigns_reviewed = summary.get("total_evaluated", 0)

    keywords_evaluated = summary.get("keywords_evaluated", summary.get("total_evaluated", 0))

    # Smart audit issues
    smart_issues_count = summary.get("smart_issues", 0)
    if "smart_audit" in audit_results and isinstance(audit_results["smart_audit"], dict):
        smart_issues_count = audit_results["smart_audit"].get("summary", {}).get("issues_total", smart_issues_count)

    # Un run es "real" si auditó al menos una campaña de cualquier tipo.
    # Smart Campaigns siempre se auditan si hay >= 1 SMART ENABLED.
    is_real_audit = campaigns_reviewed > 0 or keywords_evaluated > 0

    return {
        "run_id":            session_id,
        "timestamp_utc":     now_utc,
        "timestamp_merida":  _now_merida_str(),
        "result_class":      result_class,
        "run_type":          run_type,        # "daily" | "compensatory"
        "is_real_audit":     is_real_audit,
        "modules":           modules_run,
        # Cobertura por tipo (corrige bug histórico de "campaigns_reviewed = keywords")
        "campaigns_reviewed":  campaigns_reviewed,  # total = search + smart
        "campaigns_search":    campaigns_search,
        "campaigns_smart":     campaigns_smart,
        "keywords_evaluated":  keywords_evaluated,
        "issues_detected":   (
            len(tracking_signals)
            + (1 if landing_severity not in (None, "ok") else 0)
            + len(geo_issues)
            + smart_issues_count
        ),
        "changes_executed":  changes_executed,
        "blocked_by_guard":  blocked_by_guard,
        "auto_exec_disabled": auto_exec_disabled,
        "human_pending":     human_pending,
        "errors":            errors,
        "had_error":         bool(errors),
        "had_change":        changes_executed > 0,
        "had_alert":         has_alerts,
        # Detalle por área
        "detail": {
            "tracking_signals":   tracking_signals,
            "landing_severity":   landing_severity,
            "geo_issues":         geo_issues,
            "geo_unverified":     geo_unverified,
            "keyword_pending":    keyword_pending,
            "ba_pending":         ba_pending,
            "dry_run":            summary.get("dry_run", True),
            "smart_issues":       smart_issues_count,
        },
    }


# ─── Persistencia ─────────────────────────────────────────────────────────────

def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {"runs": [], "pinned": {}}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"runs": [], "pinned": {}}


def _save(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_run(audit_results: dict, session_id: str, path: str | None = None,
               run_type: str = "daily") -> dict:
    """
    Deriva un resumen compacto de audit_results y lo persiste.

    Mantiene los últimos MAX_RUNS resúmenes en order cronológico (más reciente último).
    Actualiza los "pinned" de última ejecución exitosa, errores, cambios y bloqueos.

    Args:
        audit_results : el dict completo devuelto por run_autonomous_audit()
        session_id    : ID de la sesión de auditoría
        path          : ruta al JSON (opcional, usa data/system_activity.json por defecto)

    Returns:
        El dict del resumen de esta corrida.
    """
    target = path or _ACTIVITY_PATH
    run = _derive_run_summary(audit_results, session_id, run_type=run_type)
    try:
        data = _load(target)

        # Agregar al historial y truncar
        data["runs"].append(run)
        if len(data["runs"]) > MAX_RUNS:
            data["runs"] = data["runs"][-MAX_RUNS:]

        # Actualizar pinned
        pinned = data.setdefault("pinned", {})

        if not run["had_error"]:
            pinned["last_successful_run"] = run

        if run["had_error"]:
            pinned["last_run_with_errors"] = run

        if run["had_change"]:
            pinned["last_change_applied"] = run

        if run["blocked_by_guard"] > 0:
            pinned["last_block_by_security"] = run

        _save(data, target)
    except Exception as _persist_exc:
        import logging as _log
        _log.getLogger(__name__).warning(
            "activity_log: no se pudo persistir en disco (filesystem no disponible en Cloud Run): %s",
            _persist_exc,
        )
    return run


def get_last_activity(path: str | None = None) -> dict:
    """
    Retorna el estado de actividad más reciente del sistema.

    Returns:
        dict con:
          'latest_run'          — último run registrado (puede ser el de hoy)
          'last_successful_run' — último run sin errores
          'last_run_with_errors'— último run con errores
          'last_change_applied' — último run donde se ejecutó algún cambio
          'last_block_by_security' — último run donde una guarda bloqueó algo
          'run_count'           — total de runs en el historial
    """
    target = path or _ACTIVITY_PATH
    data = _load(target)
    runs = data.get("runs", [])
    pinned = data.get("pinned", {})

    return {
        "latest_run":            runs[-1] if runs else None,
        "last_successful_run":   pinned.get("last_successful_run"),
        "last_run_with_errors":  pinned.get("last_run_with_errors"),
        "last_change_applied":   pinned.get("last_change_applied"),
        "last_block_by_security": pinned.get("last_block_by_security"),
        "run_count":             len(runs),
    }


def get_activity_log(n: int = 30, path: str | None = None) -> list:
    """Retorna los últimos n runs en orden cronológico (más reciente último)."""
    target = path or _ACTIVITY_PATH
    data = _load(target)
    return data.get("runs", [])[-n:]
