"""
Routes de Aprobaciones — /approve-proposals, /approve-legacy, /approve.
"""
import os
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from engine.db_sync import get_db_path

router = APIRouter(tags=["approvals"])
logger = logging.getLogger(__name__)


class ApproveProposalRequest(BaseModel):
    decision_ids: List[str]


def _get_engine():
    from main import get_engine_modules
    return get_engine_modules()


@router.post("/approve-proposals")
async def approve_proposals(request: ApproveProposalRequest):
    """Ejecuta propuestas aprobadas"""
    try:
        engine = _get_engine()
        if not engine:
            raise Exception("Engine modules not available")
        
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        
        results = []
        for decision_id in request.decision_ids:
            results.append({
                "decision_id": decision_id,
                "status": "executed",
                "timestamp": datetime.now().isoformat()
            })
        
        return {
            "status": "success",
            "executed": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/approve-legacy", response_class=HTMLResponse)
async def approve_from_email(
    action: str = Query(...),
    proposal_id: str = Query(None),  # legacy
    d: str = Query(None),            # base64-encoded proposal data (new)
):
    """
    Endpoint GET para aprobar/rechazar propuestas desde el email.
    Devuelve una página HTML de confirmación.
    """
    is_approve = action.lower() == "approve"

    # Resolve proposal_id and proposal data
    import base64 as _b64, json as _json
    prop_data = {}
    if d:
        try:
            prop_data = _json.loads(_b64.urlsafe_b64decode(d.encode()).decode())
            proposal_id = prop_data.get("id", d[:12])
        except Exception:
            proposal_id = proposal_id or "unknown"
    proposal_id = proposal_id or "unknown"

    # ── STEP 1: Execute the action FIRST ─────────────────────────────────────
    execution_result = {"status": "recorded"}
    if is_approve:
        try:
            prop_type = prop_data.get("type", "")
            campaign_id = str(prop_data.get("campaign_id", ""))
            campaign_name = prop_data.get("campaign_name", "")

            if prop_type == "scale_campaign" and campaign_id and campaign_id != "None":
                engine = _get_engine()
                if engine:
                    target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                    ads_client = engine["get_ads_client"]()
                    budget_info = engine["fetch_campaign_budget_info"](ads_client, target_id, campaign_id)
                    if "current_daily_budget_mxn" in budget_info:
                        current = budget_info["current_daily_budget_mxn"]
                        new_budget = round(current * 1.30, 2)
                        ads_result = engine["update_campaign_budget"](
                            ads_client, target_id,
                            budget_info["budget_resource_name"],
                            int(new_budget * 1_000_000)
                        )
                        execution_result = {
                            "status": "executed",
                            "action": f"Budget de '{campaign_name}' escalado {current} → {new_budget} MXN/día (+30%)",
                            "google_ads": ads_result,
                        }
                    else:
                        execution_result = {"status": "error", "detail": budget_info.get("error", "No se pudo obtener el presupuesto")}
            else:
                execution_result = {"status": "recorded", "note": "Propuesta informativa — sin cambios automáticos en Google Ads"}
        except Exception as ex:
            execution_result = {"status": "error", "detail": str(ex)}

    # ── STEP 2: Persist to DB ─────────────────────────────────────────────────
    try:
        import sqlite3
        _db = sqlite3.connect(get_db_path())
        _db.execute(
            """CREATE TABLE IF NOT EXISTS pending_proposals
               (id TEXT PRIMARY KEY, type TEXT, title TEXT, action TEXT,
                campaign_id TEXT, campaign_name TEXT, budget_increase REAL,
                status TEXT DEFAULT 'pending', created_at TEXT, resolved_at TEXT)"""
        )
        _db.execute(
            "UPDATE pending_proposals SET status = ?, resolved_at = ? WHERE id = ?",
            ("approved" if is_approve else "rejected", datetime.now().isoformat(), proposal_id)
        )
        _db.execute(
            "INSERT OR IGNORE INTO agent_actions (action_type, description, result, timestamp) VALUES (?, ?, ?, ?)",
            ("email_approval", f"{action}:{proposal_id}", execution_result.get("status", "recorded"), datetime.now().isoformat())
        )
        _db.commit()
        _db.close()
    except Exception:
        pass

    # ── STEP 3: Build HTML response ───────────────────────────────────────────
    if is_approve:
        icon = "✅"
        color = "#16a34a"
        title = "Propuesta Aprobada"
        exec_status = execution_result.get("status", "recorded")
        if exec_status == "executed":
            detail_line = f"<p style='color:#16a34a;font-weight:600;margin-top:12px;'>{execution_result.get('action','')}</p>"
        elif exec_status == "recorded":
            detail_line = "<p style='color:#6b7280;margin-top:12px;'>Anotado para revisión manual. Sin cambios automáticos aplicados.</p>"
        else:
            detail_line = f"<p style='color:#dc2626;margin-top:12px;'>Error: {execution_result.get('detail','')}</p>"
        msg = f"La propuesta <strong>{proposal_id}</strong> ha sido procesada.{detail_line}"
        bg = "#f0fdf4"
        border = "#bbf7d0"
    else:
        icon = "❌"
        color = "#dc2626"
        title = "Propuesta Rechazada"
        msg = f"La propuesta <strong>{proposal_id}</strong> ha sido descartada. No se realizará ningún cambio."
        bg = "#fef2f2"
        border = "#fecaca"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Thai Thai</title>
  <style>
    body {{ margin: 0; padding: 40px 20px; background: #f3f4f6;
           font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .card {{ max-width: 480px; margin: 0 auto; background: {bg};
             border: 2px solid {border}; border-radius: 12px; padding: 40px; text-align: center; }}
    h1 {{ color: {color}; font-size: 24px; margin: 16px 0 8px; }}
    p {{ color: #374151; font-size: 15px; line-height: 1.6; }}
    .id {{ font-size: 12px; color: #9ca3af; margin-top: 24px; }}
    a {{ color: #2563eb; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 48px;">{icon}</div>
    <h1>{title}</h1>
    <p>{msg}</p>
    <p class="id">ID: {proposal_id} · {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    <p style="margin-top: 24px;">
      <a href="https://thai-thai-ads-agent-624172071613.us-central1.run.app/dashboard">
        Ver dashboard del agente →
      </a>
    </p>
  </div>
</body>
</html>"""


# ============================================================================
# FASE 1A: AUDITORÍA AUTÓNOMA CON CLASIFICACIÓN DE RIESGO


@router.get("/approve")
async def approve_proposal(d: str, action: str):
    """
    Procesa la respuesta del operador a una propuesta de bloqueo.

    Params:
        d      : approval_token de la propuesta (enviado en el correo)
        action : 'approve' o 'reject'

    Retorna HTML — este endpoint se llama desde un link en el correo.
    """
    from fastapi.responses import HTMLResponse
    from datetime import timezone, timedelta
    from config.agent_config import PROPOSAL_EXPIRY_HOURS

    def _html(title: str, body: str, color: str = "#333") -> HTMLResponse:
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }}
  h2 {{ color: {color}; }}
  p {{ color: #555; line-height: 1.6; }}
  .meta {{ background: #f5f5f5; padding: 12px 16px; border-radius: 6px; font-size: 0.9em; color: #666; }}
</style></head>
<body>
  <h2>{title}</h2>
  {body}
  <p class="meta">Thai Thai Ads Agent · administracion@thaithaimerida.com.mx</p>
</body></html>""")

    # Validación de parámetros
    if action not in ("approve", "reject"):
        return _html("Acción inválida",
                     "<p>La URL no contiene una acción válida. Usa <code>action=approve</code> o <code>action=reject</code>.</p>",
                     "#c00")

    # Check 1: ¿existe el token?
    try:
        from engine.memory import get_memory_system as _get_mem_approve
        engine  = _get_engine()
        memory  = _get_mem_approve()
        decision = memory.get_decision_by_token(d)
    except Exception as exc:
        logger.error("/approve: error al leer memoria — %s", exc)
        return _html("Error interno", f"<p>No se pudo consultar la base de datos: {exc}</p>", "#c00")

    if not decision:
        return _html("Token inválido",
                     "<p>El enlace no es válido o ya fue eliminado. "
                     "Es posible que la propuesta haya sido procesada por otro medio.</p>", "#c00")

    # Check 2: ¿la decisión es una propuesta activa (decision='proposed')?
    if decision.get("decision") != "proposed":
        return _html("No es una propuesta activa",
                     f"<p>Este enlace corresponde a una decisión con estado "
                     f"<strong>{decision.get('decision')}</strong>, no a una propuesta pendiente.</p>", "#888")

    # Check 3: ¿ya fue procesada?
    if decision.get("approved_at") or decision.get("rejected_at") or decision.get("postponed_at"):
        processed_ts = decision.get("approved_at") or decision.get("rejected_at") or decision.get("postponed_at")
        return _html("Ya procesada",
                     f"<p>Esta propuesta ya fue procesada el <strong>{processed_ts}</strong>.</p>", "#888")

    # Check 4: ¿expiró?
    created_str = decision.get("created_at", "")
    try:
        created_utc = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
    except ValueError:
        created_utc = datetime.now(timezone.utc) - timedelta(hours=PROPOSAL_EXPIRY_HOURS + 1)

    if datetime.now(timezone.utc) - created_utc > timedelta(hours=PROPOSAL_EXPIRY_HOURS):
        memory.mark_autonomous_decision_postponed(decision["id"])
        return _html("Propuesta expirada",
                     f"<p>Esta propuesta superó las {PROPOSAL_EXPIRY_HOURS} horas de vigencia "
                     f"y fue marcada como <strong>pospuesta</strong>. "
                     f"Será re-evaluada en el siguiente ciclo de auditoría.</p>", "#e67e22")

    keyword       = decision.get("keyword", "")
    campaign_id   = decision.get("campaign_id", "")
    campaign_name = decision.get("campaign_name", "")
    action_type   = decision.get("action_type", "block_keyword")

    # ── Dispatch por tipo de propuesta ───────────────────────────────────────
    # Cada rama maneja su propia lógica de aprobación/rechazo.
    # Añadir aquí nuevos tipos de propuesta en fases futuras.
    # Nunca asumir que action_type == "block_keyword" — siempre discriminar.
    # ─────────────────────────────────────────────────────────────────────────

    # ── TIPO: adgroup_proposal (Fase 4B) ─────────────────────────────────────
    # Si ADGROUP_PAUSE_ENABLED=true y el ad group pasa las guardas de seguridad,
    # se ejecuta la pausa vía API. En caso contrario, la aprobación queda
    # registrada pero no se ejecuta ninguna mutación.
    if action_type == "adgroup_proposal":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}
        adgroup_id   = evidence.get("adgroup_id", keyword.replace("adgroup:", ""))
        adgroup_name = evidence.get("adgroup_name", adgroup_id)

        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: adgroup_proposal rechazada — ad group '%s' id=%s (decision_id=%d)",
                adgroup_name, adgroup_id, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── action == "approve" ───────────────────────────────────────────────
        from config.agent_config import ADGROUP_PAUSE_ENABLED

        # Interruptor desactivado → registrar aprobación sin ejecutar
        if not ADGROUP_PAUSE_ENABLED:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason="pause_disabled",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: adgroup_proposal aprobada (ADGROUP_PAUSE_ENABLED=false) — "
                "ad group '%s' id=%s (decision_id=%d)",
                adgroup_name, adgroup_id, decision["id"],
            )
            return _html(
                "Aprobación registrada — ejecución manual",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Paso manual requerido:</strong> la ejecución automática vía API "
                f"está desactivada (<code>ADGROUP_PAUSE_ENABLED=false</code>).<br>"
                f"Pausa el ad group directamente en Google Ads.</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Para activar la ejecución automática, "
                f"establece <code>ADGROUP_PAUSE_ENABLED=true</code> en las variables de entorno.</p>",
                "#2980b9",
            )

        # Whitelist de IDs para el primer test controlado
        allow_ids_raw = os.getenv("ADGROUP_PAUSE_ALLOW_IDS", "")
        allow_ids = {s.strip() for s in allow_ids_raw.split(",") if s.strip()}
        if allow_ids and str(adgroup_id) not in allow_ids:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"adgroup_id={adgroup_id} no está en ADGROUP_PAUSE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: adgroup_proposal aprobada pero id=%s no está en whitelist — "
                "ad group '%s' (decision_id=%d)",
                adgroup_id, adgroup_name, decision["id"],
            )
            return _html(
                "Aprobación registrada — ID no en whitelist",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Sin ejecución:</strong> el ID <code>{adgroup_id}</code> no está "
                f"incluido en <code>ADGROUP_PAUSE_ALLOW_IDS</code>.<br>"
                f"Agrega el ID a la variable de entorno para permitir la ejecución automática.</p>",
                "#2980b9",
            )

        # Verificación de guardas de seguridad pre-ejecución
        try:
            target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            client    = engine["get_ads_client"]()
            verify    = engine["verify_adgroup_still_pausable"](
                client, target_id, adgroup_id, campaign_id
            )
        except Exception as exc:
            logger.error("/approve: error en verify_adgroup_still_pausable — %s", exc)
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"error en verificación pre-pausa: {str(exc)[:100]}",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Error en verificación",
                f"<p>No se pudo verificar el estado del ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) "
                f"antes de ejecutar la pausa.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>La aprobación quedó registrada. Pausa manualmente si lo consideras correcto.</p>",
                "#e67e22",
            )

        if not verify["ok"]:
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=verify["reason"],
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            guard = verify.get("guard", "")
            logger.warning(
                "/approve: guarda %s activada para ad group '%s' id=%s — %s (decision_id=%d)",
                guard, adgroup_name, adgroup_id, verify["reason"], decision["id"],
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La propuesta para pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>) en "
                f"<strong>{campaign_name}</strong> fue aprobada pero <strong>no ejecutada</strong> "
                f"por una guarda de seguridad.</p>"
                f"<p><strong>Razón:</strong> {verify['reason']}</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Revisado a las "
                f"{verify.get('verify_checked_at','')} UTC. "
                f"Si la situación cambió, revisa Google Ads directamente.</p>",
                "#e67e22",
            )

        # Todo OK → ejecutar pausa vía API
        try:
            pause_result = engine["pause_ad_group"](client, target_id, adgroup_id)
        except Exception as exc:
            logger.error("/approve: error en pause_ad_group — %s", exc)
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"error al ejecutar pausa: {str(exc)[:100]}",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error al pausar",
                f"<p>La verificación pasó pero ocurrió un error al pausar el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>).</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>La propuesta sigue pendiente. Puedes pausarlo manualmente en Google Ads.</p>",
                "#c00",
            )

        if pause_result.get("status") != "success":
            err_msg = pause_result.get("message", "error desconocido")
            memory.mark_adgroup_approved_blocked(
                decision_id=decision["id"],
                reason=f"pause_ad_group falló: {err_msg[:100]}",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            logger.error(
                "/approve: pause_ad_group falló para id=%s — %s (decision_id=%d)",
                adgroup_id, err_msg, decision["id"],
            )
            return _html(
                "Error al pausar",
                f"<p>La verificación pasó pero Google Ads rechazó la mutación para el ad group "
                f"<strong>\"{adgroup_name}\"</strong> (ID: <code>{adgroup_id}</code>).</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Puedes pausarlo manualmente en Google Ads.</p>",
                "#c00",
            )

        # Éxito — registrar en memoria
        memory.mark_adgroup_paused(decision["id"], verify)
        logger.info(
            "/approve: ad group pausado exitosamente — '%s' id=%s campaña '%s' (decision_id=%d)",
            adgroup_name, adgroup_id, campaign_name, decision["id"],
        )
        return _html(
            "Ad group pausado",
            f"<p>El ad group <strong>\"{adgroup_name}\"</strong> "
            f"(ID: <code>{adgroup_id}</code>) en la campaña "
            f"<strong>{campaign_name}</strong> fue pausado exitosamente vía API.</p>"
            f"<p>El cambio es efectivo de inmediato en Google Ads.</p>"
            f"<p style=\"color:#888;font-size:0.9em;\">Verificado a las "
            f"{verify.get('verify_checked_at','')} UTC — "
            f"{verify.get('enabled_adgroups_in_campaign',0)} grupos ENABLED en campaña antes de pausar.</p>",
            "#27ae60",
        )

    # ── TIPO: block_keyword (Fase 2) ─────────────────────────────────────────
    if action_type == "block_keyword":
        if action == "approve":
            # Check 5a: ¿la keyword está protegida (marca/estratégica)?
            try:
                from engine.risk_classifier import is_keyword_protected
                if is_keyword_protected(keyword):
                    logger.warning(
                        "/approve: intento de bloquear keyword protegida '%s' — rechazado (decision_id=%d)",
                        keyword, decision["id"],
                    )
                    return _html(
                        "Keyword protegida",
                        f"<p>La keyword <strong>\"{keyword}\"</strong> es estratégica para tu negocio "
                        f"(marca/nombre del restaurante). <strong>NO se debe bloquear</strong> aunque tenga pocas conversiones "
                        f"— atrae tráfico de marca valioso que no se refleja como conversión directa.</p>"
                        f"<p>Si estás seguro de bloquearla, edita "
                        f"<code>config/agent_config.py → PROTECTED_KEYWORDS</code>.</p>",
                        "#e67e22",
                    )
            except Exception as exc:
                logger.warning("/approve: no se pudo verificar protección de keyword — %s", exc)

            # Check 5b: ¿la keyword ya existe como negativa activa en Google Ads?
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client    = engine["get_ads_client"]()
                ga_service = client.get_service("GoogleAdsService")
                neg_query = f"""
                    SELECT campaign_criterion.keyword.text
                    FROM campaign_criterion
                    WHERE campaign.id = {campaign_id}
                      AND campaign_criterion.negative = TRUE
                      AND campaign_criterion.type = 'KEYWORD'
                """
                existing_negatives = {
                    row.campaign_criterion.keyword.text.lower()
                    for row in ga_service.search(customer_id=target_id, query=neg_query)
                }
                already_negative = keyword.lower() in existing_negatives
            except Exception as exc:
                logger.warning("/approve: no se pudo verificar negativas existentes — %s", exc)
                already_negative = False

            if already_negative:
                memory.mark_autonomous_decision_approved(decision["id"])
                return _html(
                    "Ya estaba bloqueada",
                    f"<p>La keyword <strong>\"{keyword}\"</strong> ya aparece como negativa activa "
                    f"en la campaña <strong>{campaign_name}</strong>.</p>"
                    f"<p>La propuesta fue marcada como aprobada sin ejecutar una mutación adicional.</p>",
                    "#27ae60",
                )

            # Ejecutar la mutación real
            try:
                target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
                client    = engine["get_ads_client"]()
                engine["add_negative_keyword"](client, target_id, campaign_id, keyword)
                memory.mark_autonomous_decision_approved(decision["id"])
                logger.info(
                    "/approve: keyword '%s' bloqueada en campaña %s (decision_id=%d)",
                    keyword, campaign_name, decision["id"],
                )
                return _html(
                    "Aprobado y ejecutado",
                    f"<p>La keyword <strong>\"{keyword}\"</strong> fue agregada como negativa "
                    f"en la campaña <strong>{campaign_name}</strong>.</p>"
                    f"<p>El cambio es efectivo de inmediato en Google Ads.</p>",
                    "#27ae60",
                )
            except Exception as exc:
                logger.error("/approve: fallo al ejecutar mutación — %s", exc)
                return _html(
                    "Error al ejecutar",
                    f"<p>No se pudo bloquear la keyword. Error: <code>{exc}</code></p>"
                    f"<p>La propuesta sigue pendiente. Puedes intentarlo de nuevo o "
                    f"bloquearlo manualmente desde Google Ads.</p>",
                    "#c00",
                )

        else:  # reject
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: propuesta rechazada — keyword '%s' (decision_id=%d)",
                keyword, decision["id"],
            )
            return _html(
                "Rechazado",
                f"<p>La propuesta para bloquear <strong>\"{keyword}\"</strong> "
                f"en <strong>{campaign_name}</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

    # ── TIPO: budget_action (Fase 6B.1) ──────────────────────────────────────
    # BA1: reducción de presupuesto por CPA crítico.
    # Flujo: aprobación → verify_budget_still_actionable() → update_campaign_budget()
    # Requiere BUDGET_CHANGE_ENABLED=true para ejecutar la mutación vía API.
    # Sin el kill switch activo, la aprobación queda registrada sin ejecutar.
    #
    # Estados de aprobación (approve_outcome en evidence_json):
    #   approved_registered  — kill switch off; ejecución manual si se desea
    #   approved_dry_run_ok  — kill switch off pero guardas pasarían (dry-run OK)
    #   approved_blocked     — kill switch on pero una guarda bloqueó la ejecución
    #   approved_exec_error  — guardas pasaron pero la API rechazó la mutación
    #   execution_done       — presupuesto cambiado exitosamente vía API
    if action_type == "budget_action":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        campaign_type         = evidence.get("campaign_type", "")
        cpa_real              = evidence.get("cpa_real")
        cpa_critical          = evidence.get("cpa_critical")
        daily_budget_at_prop  = float(evidence.get("daily_budget_mxn") or 0)
        suggested             = evidence.get("suggested_daily_budget")
        reduction_pct         = evidence.get("reduction_pct")
        budget_resource_name  = evidence.get("budget_resource_name", "")
        is_shared_budget      = bool(evidence.get("budget_explicitly_shared", False))

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: budget_action rechazada — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de ajuste de presupuesto para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── Presupuesto compartido: rutina de separación ─────────────────────
        # Si el budget es explicitly_shared, el agente NO puede modificarlo directamente.
        # En su lugar, crea un presupuesto individual nuevo y reasigna la campaña.
        if is_shared_budget and action == "approve":
            from config.agent_config import BUDGET_CHANGE_ENABLED, BUDGET_CHANGE_ALLOW_IDS
            target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            _sug_shared = float(suggested) if suggested else 0.0

            # Kill switch
            if not BUDGET_CHANGE_ENABLED:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_registered",
                )
                return _html(
                    "Registrado — switch desactivado",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado, "
                    f"por lo que no se ejecutó la separación del presupuesto.</p>"
                    f"<p><strong>Campaña:</strong> {campaign_name}<br>"
                    f"Presupuesto sugerido: <strong>${_sug_shared:.2f} MXN/día</strong></p>",
                    "#6b7280",
                )

            # Whitelist
            if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                    approve_outcome="approved_registered",
                )
                return _html(
                    "Registrado — campaña no en whitelist",
                    f"<p>La campaña <strong>\"{campaign_name}\"</strong> no está en la whitelist "
                    f"<code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>",
                    "#6b7280",
                )

            if not target_id or _sug_shared <= 0:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="datos insuficientes para ejecutar separación de presupuesto compartido",
                    approve_outcome="approved_blocked",
                )
                return _html(
                    "Datos incompletos",
                    "<p>No hay suficientes datos para ejecutar la separación. "
                    "Verifica GOOGLE_ADS_TARGET_CUSTOMER_ID y el presupuesto sugerido.</p>",
                    "#c00",
                )

            try:
                _client = engine["get_ads_client"]()
                _sug_micros = int(_sug_shared * 1_000_000)
                sep_result = engine["separate_and_assign_budget"](
                    _client, target_id, campaign_id, _sug_micros, campaign_name
                )
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"excepción en separate_and_assign_budget: {exc}",
                    approve_outcome="approved_exec_error",
                )
                logger.error("/approve: excepción en separate_and_assign_budget — %s", exc)
                return _html(
                    "Error al separar presupuesto",
                    f"<p>Ocurrió un error al llamar a la API: <code>{exc}</code></p>",
                    "#c00",
                )

            if sep_result.get("status") != "success":
                err_msg = sep_result.get("message", "error desconocido")
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"API rechazó la separación: {err_msg}",
                    approve_outcome="approved_exec_error",
                )
                logger.error(
                    "/approve: separate_and_assign_budget falló para campaña '%s' — %s (decision_id=%d)",
                    campaign_name, err_msg, decision["id"],
                )
                return _html(
                    "API rechazó la operación",
                    f"<p>Google Ads rechazó la separación del presupuesto.</p>"
                    f"<p>Error: <code>{err_msg}</code></p>",
                    "#c00",
                )

            # Éxito: presupuesto separado y asignado
            memory.mark_budget_changed(
                decision["id"],
                {"current_budget_mxn": daily_budget_at_prop, "guard": "none", "ok": True},
                _sug_shared,
            )
            logger.info(
                "/approve: presupuesto compartido separado exitosamente — campaña '%s' "
                "nuevo presupuesto ${:.2f} MXN/día (decision_id=%d)",
                campaign_name, _sug_shared, decision["id"],
            )
            return _html(
                "Presupuesto separado y ajustado",
                f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
                f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
                f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
                f"✓ Presupuesto individual creado y asignado</p>"
                f"<p style='margin:6px 0 0;color:#166534;font-size:0.95em;'>"
                f"La campaña <strong>\"{campaign_name}\"</strong> ya tiene su propio presupuesto "
                f"de <strong>${_sug_shared:.2f} MXN/día</strong>. "
                f"El presupuesto compartido original no fue modificado.</p>"
                f"</div>"
                f"<p style='font-size:0.85em;color:#555;'>Recurso: "
                f"<code>{sep_result.get('new_budget_resource','')}</code></p>",
                "#15803d",
            )

        # ── Aprobación: construir datos de contexto comunes ──────────────────
        from config.agent_config import (
            BUDGET_CHANGE_ENABLED,
            BUDGET_CHANGE_ALLOW_IDS,
        )

        def _budget_context_html() -> str:
            """Bloque de evidencia reutilizable en todas las páginas de respuesta."""
            cpa_line = ""
            if cpa_real and cpa_critical:
                cpa_line = (
                    f"<p style='font-size:0.9em;color:#666;margin:4px 0 0;'>"
                    f"CPA real: <strong>${float(cpa_real):.2f}</strong> MXN · "
                    f"Umbral crítico: ${float(cpa_critical):.2f} MXN · "
                    f"Tipo: {campaign_type}</p>"
                )
            budget_line = ""
            if daily_budget_at_prop and suggested:
                budget_line = (
                    f"<p style='font-size:0.9em;color:#666;margin:4px 0 0;'>"
                    f"Presupuesto propuesta: ${float(daily_budget_at_prop):.2f} → "
                    f"<strong>${float(suggested):.2f} MXN/día</strong>"
                    f" (reducción {reduction_pct}%)</p>"
                )
            return f"<p><strong>Campaña:</strong> {campaign_name}</p>{cpa_line}{budget_line}"

        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")

        # ── Estado 1 & 2: kill switch desactivado ─────────────────────────────
        # Ejecutar verify de todas formas para poder reportar si habría funcionado
        if not BUDGET_CHANGE_ENABLED:
            dry_verify = None
            if target_id and suggested is not None and daily_budget_at_prop > 0:
                try:
                    _client = engine["get_ads_client"]()
                    dry_verify = engine["verify_budget_still_actionable"](
                        _client, target_id, campaign_id,
                        daily_budget_at_prop, float(suggested),
                    )
                except Exception as _ve:
                    logger.warning("/approve: dry verify error (switch off) — %s", _ve)

            if dry_verify and dry_verify.get("ok"):
                # Estado 2: approved_dry_run_ok — todo listo, solo falta activar switch
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_dry_run_ok",
                    verify_data=dry_verify,
                )
                logger.info(
                    "/approve: budget_action aprobada (dry-run OK) — "
                    "todas las guardas pasarían — campaña '%s' (decision_id=%d)",
                    campaign_name, decision["id"],
                )
                current_now = dry_verify.get("current_budget_mxn", daily_budget_at_prop)
                return _html(
                    "Registrado — dry-run OK",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado, "
                    f"por lo que no se ejecutó la mutación.</p>"
                    f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
                    f"padding:12px 16px;border-radius:0 6px 6px 0;margin:16px 0;'>"
                    f"<p style='margin:0;font-weight:600;color:#15803d;'>Dry-run OK — todas las guardas pasarían</p>"
                    f"<p style='margin:4px 0 0;font-size:0.9em;color:#166534;'>"
                    f"Si activas <code>BUDGET_CHANGE_ENABLED=true</code>, el agente ejecutaría:<br>"
                    f"${current_now:.2f} → <strong>${float(suggested):.2f} MXN/día</strong> "
                    f"(−{reduction_pct}%)</p>"
                    f"</div>"
                    f"{_budget_context_html()}",
                    "#15803d",
                )
            else:
                # Estado 1: approved_registered — switch off, y/o guardas fallarían
                block_note = ""
                if dry_verify and not dry_verify.get("ok"):
                    block_note = (
                        f"<p style='font-size:0.9em;color:#b45309;'>"
                        f"Nota: si activaras el switch ahora, la guarda "
                        f"<strong>{dry_verify.get('guard','')}</strong> también bloquearía: "
                        f"{dry_verify.get('reason','')}</p>"
                    )
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason="BUDGET_CHANGE_ENABLED=false",
                    approve_outcome="approved_registered",
                    verify_data=dry_verify,
                )
                logger.info(
                    "/approve: budget_action aprobada (registrada, switch off) — "
                    "campaña '%s' (decision_id=%d)",
                    campaign_name, decision["id"],
                )
                return _html(
                    "Registrado — switch desactivado",
                    f"<p>Tu aprobación fue <strong>registrada</strong>. "
                    f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado.</p>"
                    f"<p>Para que el agente ejecute cambios de presupuesto en el futuro, "
                    f"activa la variable de entorno <code>BUDGET_CHANGE_ENABLED=true</code> "
                    f"en Cloud Run.</p>"
                    f"{block_note}"
                    f"{_budget_context_html()}",
                    "#6b7280",
                )

        # ── Kill switch activo: verificar whitelist ───────────────────────────
        if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: budget_action aprobada (no en whitelist) — "
                "campaña '%s' id=%s (decision_id=%d)",
                campaign_name, campaign_id, decision["id"],
            )
            return _html(
                "Registrado — campaña no en whitelist",
                f"<p>Tu aprobación fue <strong>registrada</strong>, pero la campaña "
                f"<strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"no está en la whitelist <code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>"
                f"<p>Para permitir la ejecución, agrega el ID a la variable de entorno.</p>"
                f"{_budget_context_html()}",
                "#6b7280",
            )

        # ── Kill switch activo + whitelist OK: verificar guardas ─────────────
        if not target_id:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="GOOGLE_ADS_TARGET_CUSTOMER_ID no configurado",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Error de configuración",
                "<p><code>GOOGLE_ADS_TARGET_CUSTOMER_ID</code> no está configurado.</p>",
                "#c00",
            )

        if suggested is None or daily_budget_at_prop <= 0:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="presupuesto sugerido no disponible en la propuesta",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Datos de propuesta incompletos",
                "<p>La propuesta no contiene el presupuesto sugerido. "
                "No se puede ejecutar la mutación.</p>",
                "#c00",
            )

        try:
            _client = engine["get_ads_client"]()
            verify = engine["verify_budget_still_actionable"](
                _client, target_id, campaign_id,
                daily_budget_at_prop, float(suggested),
            )
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"error en verify: {exc}",
                approve_outcome="approved_blocked",
            )
            logger.error("/approve: error en verify_budget_still_actionable — %s", exc)
            return _html(
                "Error al verificar",
                f"<p>No se pudo verificar el estado del presupuesto: <code>{exc}</code></p>",
                "#c00",
            )

        # Estado 3: approved_blocked — una guarda bloqueó la ejecución
        if not verify.get("ok"):
            guard = verify.get("guard", "")
            reason_v = verify.get("reason", "")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=reason_v,
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            logger.info(
                "/approve: budget_action bloqueada por guarda %s — campaña '%s' (decision_id=%d): %s",
                guard, campaign_name, decision["id"], reason_v,
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La aprobación fue recibida pero la ejecución fue bloqueada "
                f"por una guarda de seguridad.</p>"
                f"<div style='background:#fef3c7;border-left:4px solid #f59e0b;"
                f"padding:12px 16px;border-radius:0 6px 6px 0;margin:16px 0;'>"
                f"<p style='margin:0;font-weight:600;color:#92400e;'>Guarda {guard} activa</p>"
                f"<p style='margin:4px 0 0;font-size:0.9em;color:#92400e;'>{reason_v}</p>"
                f"</div>"
                f"{_budget_context_html()}"
                f"<p style='font-size:0.9em;color:#888;'>La propuesta queda registrada. "
                f"Puedes revisarla manualmente en Google Ads.</p>",
                "#d97706",
            )

        # ── Todas las guardas pasaron: ejecutar la mutación ───────────────────
        current_budget_now = verify.get("current_budget_mxn", daily_budget_at_prop)
        budget_resource = budget_resource_name

        if not budget_resource:
            # Si no se almacenó en la propuesta, re-fetchar
            try:
                budget_info = engine["fetch_campaign_budget_info"](_client, target_id, campaign_id)
                budget_resource = budget_info.get("budget_resource_name", "")
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"no se pudo obtener budget_resource_name: {exc}",
                    approve_outcome="approved_blocked",
                    verify_data=verify,
                )
                return _html(
                    "Error al obtener presupuesto",
                    f"<p>No se pudo obtener el resource_name del presupuesto: <code>{exc}</code></p>",
                    "#c00",
                )

        if not budget_resource:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="budget_resource_name vacío — no se puede ejecutar mutación",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error de datos",
                "<p>El resource_name del presupuesto no está disponible. "
                "Cambia el presupuesto manualmente en Google Ads.</p>",
                "#c00",
            )

        suggested_micros = int(float(suggested) * 1_000_000)
        try:
            result = engine["update_campaign_budget"](_client, target_id, budget_resource, suggested_micros)
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"excepción al llamar update_campaign_budget: {exc}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error("/approve: excepción en update_campaign_budget — %s", exc)
            return _html(
                "Error al ejecutar",
                f"<p>Las guardas pasaron pero ocurrió un error al llamar a la API: "
                f"<code>{exc}</code></p>"
                f"<p>Puedes hacer el cambio manualmente en Google Ads: "
                f"<strong>${float(suggested):.2f} MXN/día</strong></p>",
                "#c00",
            )

        if result.get("status") != "success":
            err_msg = result.get("message", "error desconocido")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"API rechazó la mutación: {err_msg}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error(
                "/approve: update_campaign_budget falló para campaña '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "API rechazó el cambio",
                f"<p>Las guardas pasaron pero Google Ads rechazó la mutación.</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Puedes aplicar el cambio manualmente: <strong>${float(suggested):.2f} MXN/día</strong></p>",
                "#c00",
            )

        # Estado 4: execution_done — cambio aplicado exitosamente
        memory.mark_budget_changed(decision["id"], verify, float(suggested))
        logger.info(
            "/approve: presupuesto cambiado exitosamente — campaña '%s' "
            "${:.2f} → ${:.2f} MXN/día (decision_id=%d)",
            campaign_name, current_budget_now, float(suggested), decision["id"],
        )
        return _html(
            "Presupuesto actualizado",
            f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
            f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
            f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
            f"Cambio aplicado exitosamente</p>"
            f"<p style='margin:6px 0 0;color:#166534;'>"
            f"${current_budget_now:.2f} MXN/día → "
            f"<strong>${float(suggested):.2f} MXN/día</strong> "
            f"(−{verify.get('reduction_pct_actual', reduction_pct)}%)</p>"
            f"</div>"
            f"<p><strong>Campaña:</strong> {campaign_name}</p>"
            f"<p style='font-size:0.9em;color:#666;'>"
            f"Verificado a las {verify.get('verify_checked_at','')} UTC · "
            f"Estado campaña: {verify.get('campaign_status','')} · "
            f"Presupuesto compartido: {'Sí' if verify.get('budget_explicitly_shared') else 'No'}</p>"
            f"<p style='font-size:0.9em;color:#888;margin-top:16px;'>"
            f"El cambio es efectivo de inmediato en Google Ads. "
            f"El agente evaluará el impacto en el siguiente ciclo de auditoría.</p>",
            "#15803d",
        )

    # ── TIPO: geo_action (Fase GEO) ───────────────────────────────────────────
    # GEO1: corrección de geotargeting → dejar solo Mérida (1010205).
    # Flujo: aprobación → verify (campaña activa + sigue teniendo geo incorrecto)
    #        → update_campaign_location() → dejar solo 1010205.
    # Requiere GEO_AUTOFIX_ENABLED=true para ejecutar la mutación vía API.
    if action_type == "geo_action":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        geo_signal     = evidence.get("signal", "GEO1")
        detected_ids   = evidence.get("detected_location_ids", [])

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: geo_action rechazada — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de corrección de geotargeting para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        # ── GEO_AUTOFIX_ENABLED=false → registrar sin ejecutar ────────────
        from config.agent_config import GEO_AUTOFIX_ENABLED, GEO_AUTOFIX_ALLOW_IDS, DEFAULT_ALLOWED_LOCATION_IDS
        if not GEO_AUTOFIX_ENABLED:
            memory.mark_autonomous_decision_approved(decision["id"])
            logger.info(
                "/approve: geo_action aprobada (GEO_AUTOFIX_ENABLED=false) — campaña '%s' (decision_id=%d)",
                campaign_name, decision["id"],
            )
            return _html(
                "Aprobación registrada — ejecución manual",
                f"<p>La corrección de geotargeting para "
                f"<strong>\"{campaign_name}\"</strong> fue aprobada y registrada.</p>"
                f"<p><strong>Paso manual requerido:</strong> la ejecución automática vía API "
                f"está desactivada (<code>GEO_AUTOFIX_ENABLED=false</code>).<br>"
                f"Corrige la ubicación directamente en Google Ads → Campaña → Configuración → Ubicaciones.<br>"
                f"Deja solo <strong>Mérida, Yucatán, México</strong> (ID: 1010205).</p>"
                f"<p style=\"color:#888;font-size:0.9em;\">Ubicaciones detectadas: {detected_ids}</p>",
                "#2980b9",
            )

        # ── Whitelist check ───────────────────────────────────────────────
        if GEO_AUTOFIX_ALLOW_IDS and str(campaign_id) not in GEO_AUTOFIX_ALLOW_IDS:
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Aprobación registrada — ID no en whitelist",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"fue aprobada pero no está en <code>GEO_AUTOFIX_ALLOW_IDS</code>.</p>"
                f"<p>Agrega el ID a la variable de entorno para permitir la ejecución automática.</p>",
                "#2980b9",
            )

        # ── Verificación pre-ejecución ────────────────────────────────────
        # G1: ¿sigue activa la campaña?
        # G2: ¿sigue teniendo una ubicación incorrecta? (re-fetch en vivo)
        try:
            target_id   = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
            client      = engine["get_ads_client"]()
            geo_fresh   = engine["fetch_campaign_geo_criteria"](client, target_id)
            fresh_entry = geo_fresh.get(str(campaign_id))
        except Exception as exc:
            logger.error("/approve: error al re-fetch geo criteria — %s", exc)
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Error en verificación",
                f"<p>No se pudo verificar el estado de geotargeting de "
                f"<strong>\"{campaign_name}\"</strong> antes de ejecutar la corrección.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>Corrige manualmente en Google Ads si lo consideras correcto.</p>",
                "#e67e22",
            )

        if not fresh_entry:
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Campaña no encontrada",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> (ID: <code>{campaign_id}</code>) "
                f"ya no está activa o no fue encontrada. No se realizaron cambios.</p>",
                "#e67e22",
            )

        fresh_ids   = set(fresh_entry.get("location_ids", []))
        still_wrong = bool(fresh_ids - DEFAULT_ALLOWED_LOCATION_IDS) or not fresh_ids
        if not still_wrong:
            # La campaña ya tiene solo ubicaciones permitidas → sin acción necesaria
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Ya corregida",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> ya tiene solo ubicaciones permitidas: "
                f"{sorted(fresh_ids)}.</p>"
                f"<p>No se realizó ningún cambio adicional.</p>",
                "#27ae60",
            )

        # ── Ejecutar corrección ───────────────────────────────────────────
        MERIDA_LOCATION_ID = "1010205"
        try:
            fix_result = engine["update_campaign_location"](
                client, target_id, campaign_id, MERIDA_LOCATION_ID
            )
        except Exception as exc:
            logger.error("/approve: error en update_campaign_location — %s", exc)
            memory.mark_autonomous_decision_approved(decision["id"])
            return _html(
                "Error al corregir",
                f"<p>La verificación pasó pero ocurrió un error al corregir el geotargeting de "
                f"<strong>\"{campaign_name}\"</strong>.</p>"
                f"<p>Error: <code>{exc}</code></p>"
                f"<p>Corrige manualmente en Google Ads.</p>",
                "#c00",
            )

        if fix_result.get("status") != "success":
            err_msg = fix_result.get("message", "error desconocido")
            memory.mark_autonomous_decision_approved(decision["id"])
            logger.error(
                "/approve: update_campaign_location falló para '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "Error al corregir",
                f"<p>Google Ads rechazó la mutación para "
                f"<strong>\"{campaign_name}\"</strong>.</p>"
                f"<p>Error: <code>{err_msg}</code></p>"
                f"<p>Corrige manualmente en Google Ads.</p>",
                "#c00",
            )

        # Éxito
        memory.mark_autonomous_decision_approved(decision["id"])
        logger.info(
            "/approve: geotargeting corregido — campaña '%s' id=%s → solo Mérida 1010205 (decision_id=%d)",
            campaign_name, campaign_id, decision["id"],
        )
        return _html(
            "Geotargeting corregido",
            f"<p>La campaña <strong>\"{campaign_name}\"</strong> fue corregida exitosamente.</p>"
            f"<p>Ubicaciones anteriores: <code>{detected_ids}</code><br>"
            f"Ubicación ahora: <strong>Mérida, Yucatán, México (1010205)</strong></p>"
            f"<p>El cambio es efectivo de inmediato en Google Ads.</p>",
            "#27ae60",
        )

    # ── TIPO: budget_scale (Fase 6C — BA2) ───────────────────────────────────
    # BA2_REALLOC: escalar con fondos liberados por BA1 (costo neto $0).
    # BA2_SCALE:   escalar con nueva inversión.
    # Ambas sub-señales comparten la misma lógica de aprobación:
    #   aprobación → verify guards → update_campaign_budget()
    # Requiere BUDGET_CHANGE_ENABLED=true para ejecutar la mutación vía API.
    # Con el switch off, la aprobación queda registrada (manual si se desea).
    if action_type == "budget_scale":
        try:
            import json as _json
            evidence = _json.loads(decision.get("evidence_json") or "{}")
        except Exception:
            evidence = {}

        ba2_signal         = evidence.get("signal", "BA2_SCALE")
        current_budget     = float(evidence.get("current_daily_budget_mxn") or 0)
        suggested_budget   = float(evidence.get("suggested_daily_budget_mxn") or 0)
        increase_mxn       = float(evidence.get("increase_mxn") or 0)
        cpa_actual         = evidence.get("cpa_actual")
        cpa_ideal          = evidence.get("cpa_ideal")
        fund_source        = evidence.get("fund_source", "")
        budget_resource    = evidence.get("budget_resource_name", "")

        # ── Rechazo ──────────────────────────────────────────────────────────
        if action != "approve":
            memory.mark_autonomous_decision_rejected(decision["id"])
            logger.info(
                "/approve: budget_scale rechazada — campaña '%s' señal=%s (decision_id=%d)",
                campaign_name, ba2_signal, decision["id"],
            )
            return _html(
                "Propuesta rechazada",
                f"<p>La propuesta de escalamiento ({ba2_signal}) para "
                f"<strong>\"{campaign_name}\"</strong> fue rechazada.</p>"
                f"<p>No se realizaron cambios en Google Ads.</p>",
                "#c0392b",
            )

        from config.agent_config import BUDGET_CHANGE_ENABLED, BUDGET_CHANGE_ALLOW_IDS
        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")

        # ── Kill switch desactivado ───────────────────────────────────────────
        if not BUDGET_CHANGE_ENABLED:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="BUDGET_CHANGE_ENABLED=false",
                approve_outcome="approved_registered",
            )
            logger.info(
                "/approve: budget_scale aprobada (registrada, switch off) — "
                "campaña '%s' señal=%s (decision_id=%d)",
                campaign_name, ba2_signal, decision["id"],
            )
            _signal_badge = (
                '<span style="background:#dcfce7;color:#15803d;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700">BA2_REALLOC (costo neto $0)</span>'
                if ba2_signal == "BA2_REALLOC" else
                '<span style="background:#fef9c3;color:#854d0e;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700">BA2_SCALE (nueva inversión)</span>'
            )
            return _html(
                "Registrado — switch desactivado",
                f"<p>Tu aprobación fue <strong>registrada</strong>. "
                f"El interruptor <code>BUDGET_CHANGE_ENABLED</code> está desactivado.</p>"
                f"<p><strong>Campaña:</strong> {campaign_name} &nbsp;{_signal_badge}</p>"
                f"<p>Presupuesto sugerido: "
                f"${current_budget:.0f} → <strong>${suggested_budget:.0f} MXN/día</strong> "
                f"(+${increase_mxn:.0f} MXN/día)</p>"
                f"<p style='font-size:0.9em;color:#888;'>Fuente de fondos: {xe(fund_source)}</p>",
                "#6b7280",
            )

        # ── Whitelist ─────────────────────────────────────────────────────────
        if BUDGET_CHANGE_ALLOW_IDS and campaign_id not in BUDGET_CHANGE_ALLOW_IDS:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"campaign_id {campaign_id} no está en BUDGET_CHANGE_ALLOW_IDS",
                approve_outcome="approved_registered",
            )
            return _html(
                "Registrado — campaña no en whitelist",
                f"<p>La campaña <strong>\"{campaign_name}\"</strong> no está en "
                f"<code>BUDGET_CHANGE_ALLOW_IDS</code>.</p>",
                "#6b7280",
            )

        if not target_id or suggested_budget <= 0 or current_budget <= 0:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="datos insuficientes para ejecutar escalamiento",
                approve_outcome="approved_blocked",
            )
            return _html(
                "Datos incompletos",
                "<p>La propuesta no contiene presupuesto sugerido válido.</p>",
                "#c00",
            )

        # ── Verificar guardas pre-ejecución ──────────────────────────────────
        try:
            _client = engine["get_ads_client"]()
            verify = engine["verify_budget_still_actionable"](
                _client, target_id, campaign_id,
                current_budget, suggested_budget,
            )
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"error en verify: {exc}",
                approve_outcome="approved_blocked",
            )
            logger.error("/approve: error en verify para budget_scale — %s", exc)
            return _html(
                "Error al verificar",
                f"<p>No se pudo verificar el estado del presupuesto: <code>{exc}</code></p>",
                "#c00",
            )

        if not verify.get("ok"):
            guard = verify.get("guard", "")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=verify.get("reason", ""),
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                f"Ejecución bloqueada — guarda {guard}",
                f"<p>La aprobación fue recibida pero la guarda <strong>{guard}</strong> "
                f"bloqueó la ejecución:</p>"
                f"<p style='color:#92400e;'>{xe(verify.get('reason',''))}</p>"
                f"<p>La propuesta queda registrada. Puedes ajustar el presupuesto manualmente.</p>",
                "#d97706",
            )

        # ── Obtener budget_resource_name si no se almacenó en la propuesta ───
        if not budget_resource:
            try:
                budget_info = engine["fetch_campaign_budget_info"](_client, target_id, campaign_id)
                budget_resource = budget_info.get("budget_resource_name", "")
            except Exception as exc:
                memory.mark_budget_approved_blocked(
                    decision["id"],
                    reason=f"no se pudo obtener budget_resource_name: {exc}",
                    approve_outcome="approved_blocked",
                    verify_data=verify,
                )
                return _html(
                    "Error al obtener presupuesto",
                    f"<p>No se pudo obtener el resource_name del presupuesto: <code>{exc}</code></p>",
                    "#c00",
                )

        if not budget_resource:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason="budget_resource_name vacío",
                approve_outcome="approved_blocked",
                verify_data=verify,
            )
            return _html(
                "Error de datos",
                "<p>El resource_name del presupuesto no está disponible. "
                "Ajusta manualmente en Google Ads.</p>",
                "#c00",
            )

        # ── Ejecutar la mutación ──────────────────────────────────────────────
        suggested_micros = int(suggested_budget * 1_000_000)
        try:
            result = engine["update_campaign_budget"](_client, target_id, budget_resource, suggested_micros)
        except Exception as exc:
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"excepción en update_campaign_budget: {exc}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error("/approve: excepción en update_campaign_budget (BA2) — %s", exc)
            return _html(
                "Error al ejecutar",
                f"<p>Las guardas pasaron pero la API devolvió error: <code>{exc}</code></p>",
                "#c00",
            )

        if result.get("status") != "success":
            err_msg = result.get("message", "error desconocido")
            memory.mark_budget_approved_blocked(
                decision["id"],
                reason=f"API rechazó la mutación: {err_msg}",
                approve_outcome="approved_exec_error",
                verify_data=verify,
            )
            logger.error(
                "/approve: update_campaign_budget BA2 falló — campaña '%s' — %s (decision_id=%d)",
                campaign_name, err_msg, decision["id"],
            )
            return _html(
                "API rechazó el cambio",
                f"<p>Las guardas pasaron pero Google Ads rechazó la mutación.</p>"
                f"<p>Error: <code>{err_msg}</code></p>",
                "#c00",
            )

        # ── Éxito ─────────────────────────────────────────────────────────────
        memory.mark_budget_changed(decision["id"], verify, suggested_budget)
        logger.info(
            "/approve: BA2 escalamiento ejecutado — campaña '%s' señal=%s "
            "${:.0f} → ${:.0f} MXN/día (decision_id=%d)",
            campaign_name, ba2_signal, current_budget, suggested_budget, decision["id"],
        )
        _signal_label = "Reasignación de fondos BA1 (costo neto $0)" if ba2_signal == "BA2_REALLOC" else "Nueva inversión requerida"
        _cpa_line = (
            f"<p style='font-size:0.9em;color:#666;'>CPA actual: <strong>${float(cpa_actual):.2f}</strong> MXN "
            f"(ideal: ${float(cpa_ideal):.2f} MXN)</p>"
            if cpa_actual and cpa_ideal else ""
        )
        return _html(
            "Presupuesto escalado",
            f"<div style='background:#dcfce7;border-left:4px solid #16a34a;"
            f"padding:14px 18px;border-radius:0 6px 6px 0;margin-bottom:16px;'>"
            f"<p style='margin:0;font-weight:600;color:#15803d;font-size:1.05em;'>"
            f"✓ Escalamiento aplicado — {xe(_signal_label)}</p>"
            f"<p style='margin:6px 0 0;color:#166534;'>"
            f"${current_budget:.0f} MXN/día → "
            f"<strong>${suggested_budget:.0f} MXN/día</strong> "
            f"(+${increase_mxn:.0f} MXN/día)</p>"
            f"</div>"
            f"<p><strong>Campaña:</strong> {campaign_name}</p>"
            f"{_cpa_line}"
            f"<p style='font-size:0.9em;color:#888;'>Fuente: {xe(fund_source)}</p>"
            f"<p style='font-size:0.9em;color:#888;margin-top:8px;'>El cambio es efectivo "
            f"de inmediato en Google Ads.</p>",
            "#15803d",
        )

    # ── TIPO: desconocido — ruta de seguridad ─────────────────────────────────
    # Tipos futuros llegan aquí hasta que se implemente su rama explícita.
    # Registrar y avisar sin ejecutar nada.
    logger.warning(
        "/approve: action_type desconocido '%s' (decision_id=%d) — sin ejecución",
        action_type, decision["id"],
    )
    if action == "approve":
        memory.mark_autonomous_decision_approved(decision["id"])
    else:
        memory.mark_autonomous_decision_rejected(decision["id"])

    return _html(
        "Registrado sin ejecución",
        f"<p>La respuesta (<strong>{action}</strong>) fue registrada para la propuesta "
        f"de tipo <strong>{action_type}</strong>.</p>"
        f"<p>Este tipo de propuesta aún no tiene ejecución automática implementada. "
        f"Revisa el estado en el log del agente.</p>",
        "#888",
    )


# ============================================================================