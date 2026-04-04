"""
Sub-agente Auditor — Solo lectura.
Recopila datos de Google Ads, GA4, Sheets, y landing page.
Genera un diagnóstico completo del estado actual.
"""
import os
from datetime import datetime, timedelta
import logging


logger = logging.getLogger(__name__)


def _get_engine_modules():
    """Lazy import de get_engine_modules desde main para evitar imports circulares."""
    try:
        from main import get_engine_modules
        return get_engine_modules()
    except Exception:
        return None


class Auditor:
    """Lee todas las fuentes de datos y genera un snapshot."""

    def __init__(self):
        self.customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")

    def run_full_audit(self) -> dict:
        """Ejecuta auditoría completa. Retorna dict con todos los datos."""
        from engine.ads_client import get_ads_client, fetch_campaign_data, fetch_keyword_data, fetch_search_term_data
        from engine.normalizer import normalize_google_ads_data

        client = get_ads_client()
        campaigns = fetch_campaign_data(client, self.customer_id)
        keywords = fetch_keyword_data(client, self.customer_id)
        search_terms = fetch_search_term_data(client, self.customer_id)
        normalized = normalize_google_ads_data(campaigns, keywords, search_terms)

        ga4_data = self._fetch_ga4()
        sheets_data = self._fetch_sheets()
        landing_audit = self._fetch_landing_audit(ga4_data)

        return {
            "timestamp": datetime.now().isoformat(),
            "campaigns": campaigns,
            "keywords": keywords,
            "search_terms": search_terms,
            "normalized": normalized,
            "ga4_data": ga4_data,
            "sheets_data": sheets_data,
            "landing_audit": landing_audit,
        }

    def _fetch_ga4(self) -> dict:
        try:
            from engine.ga4_client import fetch_ga4_events_detailed
            return fetch_ga4_events_detailed(days=7)
        except Exception as e:
            print(f"[WARN] GA4 fetch failed: {e}")
            return {}

    def _fetch_sheets(self) -> dict:
        try:
            from engine.sheets_client import fetch_sheets_data
            return fetch_sheets_data(days=7)
        except Exception as e:
            print(f"[WARN] Sheets fetch failed: {e}")
            return {}


    async def run_autonomous_audit(self, run_type: str = "daily") -> None:
        """Delegación al ciclo completo de auditoría. Genera session_id y llama _run_audit_task."""
        import secrets
        session_id = secrets.token_hex(8)
        await _run_audit_task(session_id, run_type)

    def _fetch_landing_audit(self, ga4_data: dict) -> dict:
        try:
            from engine.landing_page_auditor import get_full_landing_audit
            return get_full_landing_audit(ga4_data)
        except Exception as e:
            print(f"[WARN] Landing audit failed: {e}")
            return {}


async def _run_audit_task(session_id: str, run_type: str = "daily") -> None:
    """
    Ejecuta el ciclo completo de auditoría en background.
    Al correr fuera del request-response cycle, Cloud Run no mata el proceso
    por timeout de request. Todos los errores se capturan internamente.
    """
    import secrets
    from engine.risk_classifier import classify_action, RISK_EXECUTE, RISK_PROPOSE, RISK_OBSERVE, RISK_BLOCK
    from engine.memory import get_memory_system

    try:
        engine = _get_engine_modules()
        if not engine:
            logger.error("_run_audit_task: Engine no disponible — sesión %s", session_id)
            return

        target_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID")
        client = engine["get_ads_client"]()
        campaigns = engine["fetch_campaign_data"](client, target_id)
        keywords = engine["fetch_keyword_data"](client, target_id)
        search_terms = engine["fetch_search_term_data"](client, target_id)

        # Totales 24h para Sección 1 del correo consolidado
        _ads_24h = {
            "spend_mxn":   round(sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns), 2),
            "conversions": round(sum(float(c.get("conversions", 0)) for c in campaigns), 1),
        }

        memory = get_memory_system()

        # Índice de campañas para consultar datos de aprendizaje
        campaign_index = {str(c.get("id", "")): c for c in campaigns}

        results = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "executed": [],
            "proposed": [],
            "observed": [],
            "blocked": [],
            "summary": {}
        }

        from config.agent_config import KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE, MAX_PROPOSALS_PER_EMAIL
        auto_executed_count = 0

        # Switch de seguridad: AUTO_EXECUTE_ENABLED debe ser "true" explícitamente
        # para que se ejecuten cambios reales en Google Ads.
        # Por defecto es false — modo dry-run (solo clasifica, decide y registra).
        auto_execute_enabled = os.getenv("AUTO_EXECUTE_ENABLED", "false").lower() == "true"
        dry_run = not auto_execute_enabled

        results["dry_run"] = dry_run
        results["auto_execute_enabled"] = auto_execute_enabled

        # Colectores para el correo consolidado (se llenan durante las fases)
        _pending_kw_proposals    = []   # propuestas de keywords para mark_sent
        _pending_ba_proposals    = []   # propuestas de presupuesto BA1 para mark_sent
        _pending_ba2_proposals   = []   # propuestas de escala BA2 (informativas)
        _pending_geo_proposals   = []   # propuestas GEO1 para mark_sent
        _geo_issues_for_email    = []   # todas las alertas GEO (GEO1 + GEO0)
        _geo_dedup_should_record = False  # True si hay geo nuevo y no hay dedup activo
        budget_scale_result: dict = {}  # resultado de Fase 6C (BA2)

        # Fase 2: expirar propuestas antiguas antes de evaluar el ciclo actual
        expired_count = memory.sweep_expired_proposals()
        if expired_count:
            logger.info("sweep_expired_proposals: %d propuesta(s) marcadas como postponed", expired_count)

        # ====================================================================
        # FASE 3A: DETECCIÓN DE TRACKING CRÍTICO
        #
        # NOTA IMPORTANTE: RISK_EXECUTE en este bloque = ENVIAR ALERTA
        # AUTOMÁTICAMENTE. No se ejecutan mutaciones en Google Ads aquí.
        # Cualquier cambio en conversion actions requiere autorización explícita.
        # ====================================================================
        tracking_alert_result = None
        try:
            from engine.risk_classifier import detect_tracking_signals
            from engine.email_sender import send_alert_email
            from config.agent_config import TRACKING_ALERT_DEDUP_HOURS

            # Rangos: semana actual (días 1-7) vs semana anterior (días 8-14)
            _now = datetime.now()
            curr_end   = (_now - timedelta(days=1)).strftime("%Y-%m-%d")
            curr_start = (_now - timedelta(days=7)).strftime("%Y-%m-%d")
            prev_end   = (_now - timedelta(days=8)).strftime("%Y-%m-%d")
            prev_start = (_now - timedelta(days=14)).strftime("%Y-%m-%d")

            current_week_metrics = engine["fetch_campaign_metrics_range"](
                client, target_id, curr_start, curr_end
            )
            prev_week_metrics = engine["fetch_campaign_metrics_range"](
                client, target_id, prev_start, prev_end
            )

            detection = detect_tracking_signals(current_week_metrics, prev_week_metrics)

            if detection["signals"]:
                classification = classify_action(
                    "tracking_issue", {"severity": detection["severity"]}
                )

                alert_data = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "affected_campaigns": detection["affected_campaigns"],
                    "signal_a_affected": detection.get("signal_a_affected", []),
                    "signal_b_affected": detection.get("signal_b_affected", []),
                    "account_metrics": detection["account_metrics"],
                    "current_week_range": f"{curr_start} → {curr_end}",
                    "prev_week_range": f"{prev_start} → {prev_end}",
                }

                # De-duplicación: no enviar alerta si ya enviamos una en las
                # últimas TRACKING_ALERT_DEDUP_HOURS horas
                already_alerted = memory.has_recent_alert(
                    "tracking_alert", TRACKING_ALERT_DEDUP_HOURS
                )

                if already_alerted:
                    alert_decision = "dedup_skipped"
                    alert_sent = False
                else:
                    # TRACKING: RISK_EXECUTE aquí = enviar alerta, NO mutar Google Ads
                    if classification.risk_level == RISK_EXECUTE and not dry_run:
                        alert_sent = send_alert_email(alert_data, session_id)
                        alert_decision = "alert_sent" if alert_sent else "alert_error"
                    else:
                        alert_sent = False
                        alert_decision = "dry_run_alert" if dry_run else "observe_alert"

                memory.record_autonomous_decision(
                    action_type="tracking_alert",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=alert_decision,
                    campaign_id="ACCOUNT",
                    campaign_name="Cuenta completa",
                    keyword="",
                    evidence=alert_data,
                    session_id=session_id,
                )

                tracking_alert_result = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "affected_campaigns": detection["affected_campaigns"],
                    "account_metrics": detection["account_metrics"],
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "alert_sent": alert_sent,
                    "alert_decision": alert_decision,
                    "dry_run": dry_run,
                }

                logger.info(
                    "Fase 3A tracking: señales=%s severity=%s decision=%s",
                    detection["signals"], detection["severity"], alert_decision
                )

        except Exception as _tracking_exc:
            logger.warning("Fase 3A: error en detección de tracking — %s", _tracking_exc)
            tracking_alert_result = {"error": str(_tracking_exc)}

        if tracking_alert_result:
            results["tracking_alert"] = tracking_alert_result

        # ====================================================================
        # FASE 3B: VERIFICACIÓN DE LANDING Y FLUJO DE CONVERSIÓN
        #
        # NOTA IMPORTANTE: RISK_EXECUTE en este bloque = ENVIAR ALERTA.
        # No se modifica el sitio web ni ningún recurso externo.
        #
        # Señales: S1_DOWN (landing caída), S2_SLOW (respuesta lenta),
        #          S4_LINK_BROKEN (Gloria Food no accesible).
        # S3_CTA_MISSING excluido: el sitio es SPA Vite+React, los CTAs
        # se inyectan en cliente — requests vería HTML vacío (falso positivo).
        #
        # Email solo para 'critical'. 'warning' → SQLite + response, sin email.
        # ====================================================================
        landing_alert_result = None
        _landing_response_ms = None
        try:
            from engine.landing_checker import check_landing_health
            from engine.email_sender import send_landing_alert_email
            from config.agent_config import (
                LANDING_URL,
                LANDING_CONVERSION_URL,
                LANDING_TIMEOUT_WARN_S,
                LANDING_TIMEOUT_CRITICAL_S,
                LANDING_RETRY_COUNT,
                LANDING_RETRY_DELAY_S,
                LANDING_OK_STATUS_CODES,
                LANDING_ALERT_DEDUP_HOURS,
            )

            detection = check_landing_health(
                landing_url=LANDING_URL,
                conversion_url=LANDING_CONVERSION_URL,
                timeout_warn_s=LANDING_TIMEOUT_WARN_S,
                timeout_critical_s=LANDING_TIMEOUT_CRITICAL_S,
                retry_count=LANDING_RETRY_COUNT,
                retry_delay_s=LANDING_RETRY_DELAY_S,
                ok_status_codes=LANDING_OK_STATUS_CODES,
            )

            # Capturar tiempo de respuesta para Sección 1 del correo
            _rt = detection.get("details", {}).get("response_time_avg_s")
            if _rt:
                _landing_response_ms = round(_rt * 1000)

            if detection["signals"]:
                classification = classify_action(
                    "landing_issue", {"severity": detection["severity"]}
                )

                alert_data = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "landing_url": LANDING_URL,
                    "conversion_url": LANDING_CONVERSION_URL,
                    "details": detection["details"],
                }

                # De-dup: evitar enviar el mismo correo varias veces en 4h
                already_alerted = memory.has_recent_alert(
                    "landing_alert", LANDING_ALERT_DEDUP_HOURS
                )

                if already_alerted:
                    alert_decision = "dedup_skipped"
                    alert_sent = False
                else:
                    # LANDING: RISK_EXECUTE = enviar alerta, NO modificar web
                    # Solo se envía email para 'critical' — 'warning' solo SQLite
                    if (
                        classification.risk_level == RISK_EXECUTE
                        and detection["severity"] == "critical"
                        and not dry_run
                    ):
                        alert_sent = send_landing_alert_email(alert_data, session_id)
                        alert_decision = "alert_sent" if alert_sent else "alert_error"
                    else:
                        alert_sent = False
                        if dry_run:
                            alert_decision = "dry_run_alert"
                        elif detection["severity"] == "warning":
                            alert_decision = "warning_logged"
                        else:
                            alert_decision = "observe_alert"

                memory.record_autonomous_decision(
                    action_type="landing_alert",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=alert_decision,
                    campaign_id="LANDING",
                    campaign_name=LANDING_URL,
                    keyword="",
                    evidence=alert_data,
                    session_id=session_id,
                )

                landing_alert_result = {
                    "signals": detection["signals"],
                    "severity": detection["severity"],
                    "reason": detection["reason"],
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "alert_sent": alert_sent,
                    "alert_decision": alert_decision,
                    "dry_run": dry_run,
                }

                logger.info(
                    "Fase 3B landing: señales=%s severity=%s decision=%s",
                    detection["signals"], detection["severity"], alert_decision,
                )

        except Exception as _landing_exc:
            logger.warning("Fase 3B: error en verificación de landing — %s", _landing_exc)
            landing_alert_result = {"error": str(_landing_exc)}

        if landing_alert_result:
            results["landing_alert"] = landing_alert_result

        for kw in keywords:
            spend = kw.get("cost_micros", 0) / 1_000_000
            conversions = float(kw.get("conversions", 0))
            keyword_text = kw.get("text", "")
            campaign_id = str(kw.get("campaign_id", ""))
            campaign_name = kw.get("campaign_name", "")

            # Solo evaluar keywords con algún gasto
            if spend <= 0:
                continue

            # Solo evaluar keywords sin conversiones (o con CPA muy alto)
            if conversions > 0:
                cpa = spend / conversions
                if cpa <= 200:
                    continue

            keyword_data = {
                "text": keyword_text,
                "keyword": keyword_text,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "spend": spend,
                "conversions": conversions,
                "impressions": int(kw.get("impressions", 0)),
            }

            campaign_data = campaign_index.get(campaign_id, {
                "id": campaign_id,
                "name": campaign_name,
            })

            classification = classify_action("block_keyword", keyword_data, campaign_data)

            evidence = {
                "spend_mxn": round(spend, 2),
                "conversions": conversions,
                "impressions": keyword_data["impressions"],
                "campaign": campaign_name,
                "dry_run": dry_run,
                "block_reason": classification.block_reason,
                "execution_action": "add_negative_keyword",  # Phase 1B: acción real que se ejecutará
            }

            if classification.risk_level == RISK_EXECUTE and auto_executed_count < KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE:
                execution_failed = False
                if dry_run:
                    # Dry-run: solo clasificar y registrar — no tocar Google Ads
                    exec_result = {
                        "status": "dry_run",
                        "action": "add_negative_keyword",
                        "note": "AUTO_EXECUTE_ENABLED=false — sin cambios reales",
                    }
                    final_decision = "dry_run_execute"
                else:
                    # Ejecución real — solo cuando AUTO_EXECUTE_ENABLED=true
                    exec_result = {"status": "skipped", "action": "add_negative_keyword", "reason": "engine_unavailable"}
                    if engine and campaign_id:
                        try:
                            engine["add_negative_keyword"](client, target_id, campaign_id, keyword_text)
                            exec_result = {
                                "status": "executed",
                                "action": "add_negative_keyword",
                                "campaign_id": campaign_id,
                                "keyword": keyword_text,
                            }
                            auto_executed_count += 1
                        except Exception as ex:
                            exec_result = {
                                "status": "error",
                                "action": "add_negative_keyword",
                                "error": str(ex),
                            }
                            evidence["execution_error"] = str(ex)
                            execution_failed = True
                            # HOOK Phase 1C: disparar email urgente si AUTO_EXECUTE_ENABLED=true
                            # Ejemplo de integración futura:
                            #   if os.getenv("AUTO_EXECUTE_ENABLED", "false").lower() == "true":
                            #       send_urgent_email(
                            #           subject=f"[FALLA CRÍTICA] No se pudo bloquear '{keyword_text}'",
                            #           body=f"Campaña: {campaign_name}\nError: {ex}",
                            #       )

                    final_decision = "executed" if exec_result["status"] == "executed" else "observe"

                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision=final_decision if not dry_run else "dry_run_execute",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                    executed=False if dry_run else (exec_result["status"] == "executed"),
                )

                results["executed"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "exec_result": exec_result,
                    "decision_id": decision_id,
                    "dry_run": dry_run,
                })

                # Si la ejecución real falló, detener el ciclo — no intentar más keywords
                if not dry_run and execution_failed:
                    break

            elif classification.risk_level == RISK_PROPOSE:
                # Fase 2: de-dup — si ya hay una propuesta activa para esta keyword,
                # no crear un nuevo registro ni un nuevo token.
                if memory.has_pending_proposal(keyword_text, campaign_id):
                    decision_id = memory.record_autonomous_decision(
                        action_type="block_keyword",
                        risk_level=RISK_OBSERVE,
                        urgency=classification.urgency,
                        decision="observe",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=keyword_text,
                        evidence={**evidence, "block_reason": "pending_proposal"},
                        session_id=session_id,
                    )
                    results["observed"].append({
                        "keyword": keyword_text,
                        "campaign": campaign_name,
                        "spend": round(spend, 2),
                        "risk_level": RISK_OBSERVE,
                        "urgency": classification.urgency,
                        "block_reason": "pending_proposal",
                        "reason": "Ya existe una propuesta activa pendiente de respuesta para esta keyword.",
                        "decision_id": decision_id,
                    })
                else:
                    # Nueva propuesta — generar token y registrar
                    token = secrets.token_urlsafe(16)

                    decision_id = memory.record_autonomous_decision(
                        action_type="block_keyword",
                        risk_level=classification.risk_level,
                        urgency=classification.urgency,
                        decision="proposed",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=keyword_text,
                        evidence=evidence,
                        session_id=session_id,
                        approval_token=token,
                        proposal_sent=False,
                        whitelisted=classification.protected,
                        learning_phase_protected=classification.learning_phase,
                    )

                    # Enriquecer propuesta con datos del Keyword Planner (graceful)
                    _kp_volume = 0
                    _kp_cpc_low = 0
                    _kp_cpc_high = 0
                    _kp_competition = "UNKNOWN"
                    try:
                        from engine.keyword_planner import suggest_additional_keywords
                        _kp_ideas = suggest_additional_keywords(
                            [keyword_text], min_searches=0, max_results=1
                        )
                        if _kp_ideas:
                            _kp_volume = _kp_ideas[0].get("avg_monthly_searches", 0)
                            _kp_cpc_low = _kp_ideas[0].get("low_bid_mxn", 0)
                            _kp_cpc_high = _kp_ideas[0].get("high_bid_mxn", 0)
                            _kp_competition = _kp_ideas[0].get("competition", "UNKNOWN")
                    except Exception:
                        pass  # Keyword Planner no disponible — continuar sin datos de volumen

                    results["proposed"].append({
                        "keyword": keyword_text,
                        "campaign": campaign_name,
                        "spend": round(spend, 2),
                        "conversions": conversions,
                        "impressions": keyword_data["impressions"],
                        "risk_level": classification.risk_level,
                        "urgency": classification.urgency,
                        "block_reason": classification.block_reason,
                        "reason": classification.reason,
                        "approval_token": token,
                        "decision_id": decision_id,
                        "protected": classification.protected,
                        "avg_monthly_searches": _kp_volume,
                        "estimated_cpc_low": _kp_cpc_low,
                        "estimated_cpc_high": _kp_cpc_high,
                        "competition": _kp_competition,
                    })

            elif classification.risk_level == RISK_BLOCK:
                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision="blocked",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                )

                results["blocked"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "decision_id": decision_id,
                })

            else:
                # RISK_OBSERVE
                decision_id = memory.record_autonomous_decision(
                    action_type="block_keyword",
                    risk_level=classification.risk_level,
                    urgency=classification.urgency,
                    decision="observe",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    keyword=keyword_text,
                    evidence=evidence,
                    session_id=session_id,
                    whitelisted=classification.protected,
                    learning_phase_protected=classification.learning_phase,
                )

                results["observed"].append({
                    "keyword": keyword_text,
                    "campaign": campaign_name,
                    "spend": round(spend, 2),
                    "risk_level": classification.risk_level,
                    "urgency": classification.urgency,
                    "block_reason": classification.block_reason,
                    "reason": classification.reason,
                    "decision_id": decision_id,
                })

        # ====================================================================
        # FASE 4: DETECTOR DE AD GROUPS CON BAJA EFICIENCIA
        #
        # MVP: solo Señal AG1 — gasto >= $120 MXN + 0 conversiones + >= 25 clicks
        # en ventana de 14 días.
        #
        # RISK_PROPOSE siempre — no hay autoejecución en esta fase.
        # Se reutilizan los tokens de aprobación y el endpoint /approve existente.
        # Dedup: has_recent_adgroup_proposal() vía convención 'adgroup:{id}'
        # en el campo keyword de autonomous_decisions.
        # ====================================================================
        adgroup_proposals_result = []
        try:
            from engine.adgroup_analyzer import detect_adgroup_issues
            from engine.email_sender import send_adgroup_proposal_email
            from engine.risk_classifier import classify_action as _classify_action
            from config.agent_config import (
                ADGROUP_EVIDENCE_WINDOW_DAYS,
                ADGROUP_MAX_PROPOSALS_PER_CYCLE,
            )

            # Ventana de 14 días para ad groups
            ag_end = datetime.now()
            ag_start = ag_end - timedelta(days=ADGROUP_EVIDENCE_WINDOW_DAYS)
            ag_start_str = ag_start.strftime("%Y-%m-%d")
            ag_end_str   = ag_end.strftime("%Y-%m-%d")

            _adgroup_rows = []
            if engine:
                _adgroup_rows = engine.get("fetch_adgroup_metrics", lambda *a, **k: [])(
                    client, target_id, ag_start_str, ag_end_str
                )

            # Detección: función pura, sin API
            candidates = detect_adgroup_issues(_adgroup_rows)

            new_ag_proposals = []
            for cand in candidates:
                adgroup_id   = cand["adgroup_id"]
                campaign_id  = cand["campaign_id"]
                campaign_name= cand["campaign_name"]
                adgroup_name = cand["adgroup_name"]

                # Clasificar riesgo
                classification = _classify_action("adgroup_efficiency", cand)

                if classification.risk_level == RISK_PROPOSE:
                    # Clave de dedup: convención 'adgroup:{id}'
                    ag_keyword_key = f"adgroup:{adgroup_id}"

                    if memory.has_recent_adgroup_proposal(adgroup_id, campaign_id):
                        # Ya existe propuesta activa para este ad group
                        memory.record_autonomous_decision(
                            action_type="adgroup_proposal",
                            risk_level=RISK_OBSERVE,
                            urgency=classification.urgency,
                            decision="observe",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            keyword=ag_keyword_key,
                            evidence={
                                "adgroup_id": adgroup_id,
                                "adgroup_name": adgroup_name,
                                "signal": cand["signal"],
                                "cost_mxn": cand["cost_mxn"],
                                "clicks": cand["clicks"],
                                "conversions": 0,
                                "impressions": cand["impressions"],
                                "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                                "block_reason": "pending_proposal",
                            },
                            session_id=session_id,
                        )
                    else:
                        # Nueva propuesta — generar token y registrar
                        ag_token = secrets.token_urlsafe(16)

                        decision_id = memory.record_autonomous_decision(
                            action_type="adgroup_proposal",
                            risk_level=classification.risk_level,
                            urgency=classification.urgency,
                            decision="proposed",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            keyword=ag_keyword_key,
                            evidence={
                                "adgroup_id": adgroup_id,
                                "adgroup_name": adgroup_name,
                                "signal": cand["signal"],
                                "cost_mxn": cand["cost_mxn"],
                                "clicks": cand["clicks"],
                                "conversions": 0,
                                "impressions": cand["impressions"],
                                "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                                "dry_run": dry_run,
                            },
                            session_id=session_id,
                            approval_token=ag_token,
                            proposal_sent=False,
                        )

                        new_ag_proposals.append({
                            "adgroup_id": adgroup_id,
                            "adgroup_name": adgroup_name,
                            "campaign_id": campaign_id,
                            "campaign_name": campaign_name,
                            "cost_mxn": cand["cost_mxn"],
                            "clicks": cand["clicks"],
                            "conversions": 0,
                            "impressions": cand["impressions"],
                            "signal": cand["signal"],
                            "reason": cand["reason"],
                            "window_days": ADGROUP_EVIDENCE_WINDOW_DAYS,
                            "urgency": classification.urgency,
                            "risk_level": classification.risk_level,
                            "approval_token": ag_token,
                            "decision_id": decision_id,
                        })

                elif classification.risk_level == RISK_BLOCK:
                    memory.record_autonomous_decision(
                        action_type="adgroup_proposal",
                        risk_level=classification.risk_level,
                        urgency=classification.urgency,
                        decision="blocked",
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        keyword=f"adgroup:{adgroup_id}",
                        evidence={
                            "adgroup_id": adgroup_id,
                            "adgroup_name": adgroup_name,
                            "signal": cand["signal"],
                            "cost_mxn": cand["cost_mxn"],
                            "reason": classification.reason,
                        },
                        session_id=session_id,
                    )

            # Enviar correo si hay propuestas nuevas
            if new_ag_proposals:
                ag_email_ok = send_adgroup_proposal_email(new_ag_proposals, session_id)
                if ag_email_ok:
                    memory.mark_proposals_sent([p["decision_id"] for p in new_ag_proposals])
                adgroup_proposals_result = new_ag_proposals

        except Exception as _ag_exc:
            logger.warning("Fase 4: error en detector de ad groups — %s", _ag_exc)
            adgroup_proposals_result = [{"error": str(_ag_exc)}]

        if adgroup_proposals_result:
            results["adgroup_proposals"] = adgroup_proposals_result

        # ====================================================================
        # FASE 6A — Campaign Health: CH1 (CPA crítico) + CH3 (sin conversiones)
        # Capa de observación pura — RISK_PROPOSE, sin autoejecución.
        # Los candidatos se registran en autonomous_decisions y aparecen
        # en el bloque del agente del reporte semanal de Fase 5.
        # ====================================================================
        campaign_health_result = []
        try:
            from engine.campaign_health import detect_campaign_issues as _detect_ch

            ch_candidates = _detect_ch(campaigns)

            for ch in ch_candidates:
                ch_campaign_id   = ch["campaign_id"]
                ch_campaign_name = ch["campaign_name"]
                ch_signal        = ch["signal"]

                # Clave de dedup: 'campaign:{id}:{signal}'
                ch_keyword = f"campaign:{ch_campaign_id}:{ch_signal}"

                if memory.has_pending_proposal(keyword=ch_keyword, campaign_id=ch_campaign_id):
                    # Ya existe propuesta activa → solo observar
                    memory.record_autonomous_decision(
                        action_type="campaign_health",
                        risk_level=RISK_OBSERVE,
                        urgency="normal",
                        decision="observe",
                        campaign_id=ch_campaign_id,
                        campaign_name=ch_campaign_name,
                        keyword=ch_keyword,
                        evidence={
                            "signal":       ch_signal,
                            "cost_mxn":     ch["cost_mxn"],
                            "reason":       ch["reason"],
                            "block_reason": "pending_proposal",
                        },
                        session_id=session_id,
                    )
                else:
                    # Nueva señal → registrar propuesta
                    decision_id = memory.record_autonomous_decision(
                        action_type="campaign_health",
                        risk_level=RISK_PROPOSE,
                        urgency="normal",
                        decision="proposed",
                        campaign_id=ch_campaign_id,
                        campaign_name=ch_campaign_name,
                        keyword=ch_keyword,
                        evidence={
                            "signal":       ch_signal,
                            "cost_mxn":     ch["cost_mxn"],
                            "conversions":  ch.get("conversions", 0),
                            "campaign_type":ch.get("campaign_type", ""),
                            "reason":       ch["reason"],
                            # CH1
                            "cpa_real":     ch.get("cpa_real"),
                            "cpa_critical": ch.get("cpa_critical"),
                            # CH3
                            "min_spend":           ch.get("min_spend"),
                            "min_days_active":     ch.get("min_days_active"),
                            "days_active":         ch.get("days_active"),
                            "days_protection_applied": ch.get("days_protection_applied"),
                            "dry_run": dry_run,
                        },
                        session_id=session_id,
                    )
                    campaign_health_result.append({
                        **ch,
                        "decision_id": decision_id,
                    })

        except Exception as _ch_exc:
            logger.warning("Fase 6A: error en campaign_health — %s", _ch_exc)
            campaign_health_result = [{"error": str(_ch_exc)}]

        if campaign_health_result:
            results["campaign_health"] = campaign_health_result

        # ====================================================================
        # FASE 6B — Budget Actions: BA1 (ajuste de presupuesto por CPA crítico)
        # Capa de propuesta pura — RISK_PROPOSE, sin autoejecución.
        # La aprobación REGISTRA la decisión; el operador hace el cambio
        # manualmente en Google Ads.
        # Silencio post-aprobación: deuda técnica Fase 6B.1.
        # ====================================================================
        budget_actions_result = []
        try:
            from engine.budget_actions import detect_budget_opportunities as _detect_ba
            import secrets as _ba_secrets

            ba_candidates = _detect_ba(campaigns)

            for ba in ba_candidates:
                ba_campaign_id   = ba["campaign_id"]
                ba_campaign_name = ba["campaign_name"]

                # Clave de dedup: 'campaign:{id}:BA1'
                ba_keyword = f"campaign:{ba_campaign_id}:BA1"

                if memory.has_pending_proposal(keyword=ba_keyword, campaign_id=ba_campaign_id):
                    # Ya existe propuesta activa → solo observar
                    memory.record_autonomous_decision(
                        action_type="budget_action",
                        risk_level=RISK_OBSERVE,
                        urgency="normal",
                        decision="observe",
                        campaign_id=ba_campaign_id,
                        campaign_name=ba_campaign_name,
                        keyword=ba_keyword,
                        evidence={
                            "signal":       "BA1",
                            "cost_mxn":     ba["cost_mxn"],
                            "reason":       ba["reason"],
                            "block_reason": "pending_proposal",
                        },
                        session_id=session_id,
                    )
                else:
                    # Nueva señal → registrar propuesta con token de aprobación
                    ba_token = _ba_secrets.token_urlsafe(16)

                    decision_id = memory.record_autonomous_decision(
                        action_type="budget_action",
                        risk_level=RISK_PROPOSE,
                        urgency="normal",
                        decision="proposed",
                        campaign_id=ba_campaign_id,
                        campaign_name=ba_campaign_name,
                        keyword=ba_keyword,
                        evidence={
                            "signal":                "BA1",
                            "cost_mxn":              ba["cost_mxn"],
                            "conversions":           ba.get("conversions", 0),
                            "campaign_type":         ba.get("campaign_type", ""),
                            "cpa_real":              ba.get("cpa_real"),
                            "cpa_critical":          ba.get("cpa_critical"),
                            "cpa_max":               ba.get("cpa_max"),
                            "daily_budget_mxn":      ba.get("daily_budget_mxn"),
                            "suggested_daily_budget":ba.get("suggested_daily_budget"),
                            "reduction_pct":         ba.get("reduction_pct"),
                            "days_active":           ba.get("days_active"),
                            "min_spend_window":      ba.get("min_spend_window"),
                            "reason":                ba["reason"],
                            "dry_run":               dry_run,
                            # Guardas 6B.1: capturar al momento de propuesta
                            # El verify siempre re-fetcha estado fresco en /approve
                            "budget_resource_name":    ba.get("budget_resource_name", ""),
                            "budget_explicitly_shared":ba.get("budget_explicitly_shared", False),
                        },
                        session_id=session_id,
                        approval_token=ba_token,
                        proposal_sent=False,
                    )

                    budget_actions_result.append({
                        **ba,
                        "decision_id":    decision_id,
                        "approval_token": ba_token,
                    })

        except Exception as _ba_exc:
            logger.warning("Fase 6B: error en budget_actions — %s", _ba_exc)
            budget_actions_result = [{"error": str(_ba_exc)}]

        if budget_actions_result:
            results["budget_actions"] = budget_actions_result

            # Colectar propuestas BA1 para el correo consolidado
            new_ba_proposals = [p for p in budget_actions_result if "error" not in p]
            if new_ba_proposals:
                _pending_ba_proposals = new_ba_proposals[:MAX_PROPOSALS_PER_EMAIL]
                logger.info(
                    "Fase 6B: %d propuesta(s) BA1 colectadas para correo consolidado",
                    len(_pending_ba_proposals),
                )

        # ====================================================================
        # FASE 6C — Budget Scale: BA2 (acelerador de campañas rentables)
        # Detecta campañas con CPA ideal + presupuesto saturado y propone escalar.
        # BA2_REALLOC: usa fondos liberados por BA1 (costo neto = $0).
        # BA2_SCALE:   requiere nueva inversión (propone, sin autoejecución).
        # No hay autoejecución — la propuesta es para decisión del operador.
        # ====================================================================
        try:
            from engine.budget_scale import detect_scale_opportunities as _detect_ba2
            from config.agent_config import CAMPAIGN_TYPE_CONFIG as _ctc
            from config.agent_config import CAMPAIGN_HEALTH_CONFIG as _chc

            _ba2_cfg = _chc.get("ba2", {})
            _ba2_evidence_days = _ba2_cfg.get("evidence_window_days", 14)

            # Pasar ba1_candidates para que BA2 pueda calcular fondos liberados
            _ba2_raw = _detect_ba2(
                campaigns=campaigns,
                campaign_type_config=_ctc,
                ba2_config=_ba2_cfg,
                ba1_candidates=_pending_ba_proposals,  # propuestas BA1 aprobadas en este ciclo
                evidence_days=_ba2_evidence_days,
            )

            if _ba2_raw.get("proposals"):
                budget_scale_result = _ba2_raw
                results["budget_scale"] = _ba2_raw

                _pending_ba2_proposals = _ba2_raw["proposals"][:MAX_PROPOSALS_PER_EMAIL]
                logger.info(
                    "Fase 6C: %d propuesta(s) BA2 detectadas — REALLOC=%.0f MXN/día, SCALE=%.0f MXN/día",
                    len(_pending_ba2_proposals),
                    _ba2_raw.get("total_realloc_mxn", 0),
                    _ba2_raw.get("total_scale_mxn", 0),
                )
            else:
                logger.info("Fase 6C: sin oportunidades de escalamiento en este ciclo.")

        except Exception as _ba2_exc:
            logger.warning("Fase 6C: error en budget_scale — %s", _ba2_exc)
            budget_scale_result = {"error": str(_ba2_exc)}

        # ====================================================================
        # MÓDULO GEO — Auditoría de Geotargeting
        #
        # Módulo oficial del agente MVP. Evalúa todas las campañas activas en
        # dos capas:
        #   1. detect_geo_issues — GEO1/GEO0 por location_id (capa básica).
        #   2. detect_geo_issues_by_policy — cumplimiento vs política por
        #      objetivo de negocio (DELIVERY, RESERVACIONES, LOCAL_DISCOVERY).
        #
        # GEO1 genera correo accionable con link de aprobación.
        # GEO0 queda en el correo como aviso informativo.
        # Las señales por política (WRONG_TYPE_*, PROX_RADIUS_EXCEEDED,
        # POLICY_UNDEFINED) se incluyen en geo_audit_result["policy_audit"]
        # y se incluyen en el reporte semanal.
        # ====================================================================
        geo_audit_result = []
        try:
            from config.agent_config import (
                GEO_AUDIT_ENABLED,
                DEFAULT_ALLOWED_LOCATION_IDS,
                GEO_ALERT_DEDUP_HOURS,
                CAMPAIGN_GEO_OBJECTIVES,
                GEO_OBJECTIVE_POLICIES,
            )
            from engine.geo_auditor import (
                detect_geo_issues as _detect_geo,
                detect_geo_issues_by_policy as _detect_geo_policy,
            )
            if GEO_AUDIT_ENABLED and engine:
                geo_criteria = engine["fetch_campaign_geo_criteria"](client, target_id)
                geo_result_raw = _detect_geo(geo_criteria, DEFAULT_ALLOWED_LOCATION_IDS)
                geo_candidates = geo_result_raw["issues"]
                geo_correct    = geo_result_raw["correct"]

                geo1_to_propose = []
                for geo in geo_candidates:
                    geo_campaign_id   = geo["campaign_id"]
                    geo_campaign_name = geo["campaign_name"]
                    geo_signal        = geo["signal"]

                    # Clave de dedup: 'geo:{id}:{signal}'
                    geo_keyword = f"geo:{geo_campaign_id}:{geo_signal}"

                    if geo_signal == "GEO1":
                        if memory.has_pending_proposal(keyword=geo_keyword, campaign_id=geo_campaign_id):
                            # Ya existe propuesta activa → observar
                            memory.record_autonomous_decision(
                                action_type="geo_action",
                                risk_level=RISK_OBSERVE,
                                urgency="normal",
                                decision="observe",
                                campaign_id=geo_campaign_id,
                                campaign_name=geo_campaign_name,
                                keyword=geo_keyword,
                                evidence={
                                    "signal":       geo_signal,
                                    "reason":       geo["reason"],
                                    "block_reason": "pending_proposal",
                                    **{k: geo[k] for k in ("detected_location_ids", "disallowed_location_ids", "allowed_location_ids")},
                                },
                                session_id=session_id,
                            )
                        else:
                            # Nueva señal GEO1 → registrar propuesta con token
                            geo_token = secrets.token_urlsafe(16)
                            decision_id = memory.record_autonomous_decision(
                                action_type="geo_action",
                                risk_level=RISK_PROPOSE,
                                urgency="normal",
                                decision="proposed",
                                campaign_id=geo_campaign_id,
                                campaign_name=geo_campaign_name,
                                keyword=geo_keyword,
                                evidence={
                                    "signal":       geo_signal,
                                    "reason":       geo["reason"],
                                    **{k: geo[k] for k in (
                                        "detected_location_ids",
                                        "disallowed_location_ids",
                                        "allowed_location_ids",
                                        "advertising_channel_type",
                                    )},
                                    "dry_run": dry_run,
                                },
                                session_id=session_id,
                                approval_token=geo_token,
                                proposal_sent=False,
                            )
                            geo1_to_propose.append({
                                **geo,
                                "decision_id":    decision_id,
                                "approval_token": geo_token,
                            })
                    else:
                        # GEO0: solo registrar en DB (aviso informativo, sin token)
                        # Nota: dedup de GEO0 queda protegido por el check externo
                        # has_recent_alert("geo_alert", ...) que envuelve todo el email.
                        memory.record_autonomous_decision(
                            action_type="geo_action",
                            risk_level=RISK_OBSERVE,
                            urgency="normal",
                            decision="observe",
                            campaign_id=geo_campaign_id,
                            campaign_name=geo_campaign_name,
                            keyword=geo_keyword,
                            evidence={
                                "signal":   geo_signal,
                                "reason":   geo["reason"],
                                **{k: geo[k] for k in ("detected_location_ids", "allowed_location_ids")},
                            },
                            session_id=session_id,
                        )

                # Colectar alertas GEO para el correo consolidado
                geo0_list = [g for g in geo_candidates if g.get("signal") == "GEO0"]
                all_for_email = geo1_to_propose + geo0_list
                if all_for_email:
                    already_alerted = memory.has_recent_alert("geo_alert", GEO_ALERT_DEDUP_HOURS)
                    if not already_alerted:
                        _geo_issues_for_email    = all_for_email
                        _pending_geo_proposals   = geo1_to_propose
                        _geo_dedup_should_record = True
                        logger.info(
                            "Fase GEO: %d alerta(s) GEO colectadas para correo consolidado "
                            "(GEO1=%d GEO0=%d)",
                            len(all_for_email), len(geo1_to_propose), len(geo0_list),
                        )

                # ── Capa 2: auditoría por política de objetivo ──────────────
                policy_result = _detect_geo_policy(
                    geo_criteria,
                    CAMPAIGN_GEO_OBJECTIVES,
                    GEO_OBJECTIVE_POLICIES,
                )

                # ── Capa 3: aplicar validaciones humanas de UI (SMART) ──────
                from engine.geo_ui_validator import (
                    load_ui_validations as _load_ui_val,
                    apply_ui_validations as _apply_ui_val,
                )
                _ui_vals = _load_ui_val()
                policy_result = _apply_ui_val(policy_result, _ui_vals, geo_criteria)

                # Resultado final: issues + campañas correctas + cumplimiento por política
                geo_audit_result = {
                    "issues":  geo_candidates,
                    "correct": geo_correct,
                    "policy_audit": policy_result,
                    "summary": {
                        "geo1_count":       len([g for g in geo_candidates if g["signal"] == "GEO1"]),
                        "geo0_count":       len([g for g in geo_candidates if g["signal"] == "GEO0"]),
                        "verified_count":   len([c for c in geo_correct if c.get("final_operational_state") == "verified"]),
                        "unverified_count": len([c for c in geo_correct if c.get("final_operational_state") == "unverified"]),
                        "ui_pending_count": len([c for c in geo_correct if c.get("final_operational_state") == "ui_validation_pending"]),
                        "policy_compliant":     len(policy_result.get("correct", [])),
                        "policy_non_compliant": len(policy_result.get("issues", [])),
                    },
                }

        except Exception as _geo_exc:
            print(f"Módulo GEO: error en geo_auditor — {_geo_exc}")
            geo_audit_result = [{"error": str(_geo_exc)}]

        if geo_audit_result:
            results["geo_audit"] = geo_audit_result

        # ====================================================================
        # FASE SMART: AUDITORÍA DE SMART CAMPAIGNS
        #
        # Cubre lo que sí es auditable vía API para campañas SMART:
        #   - Performance (CPA, gasto, conversiones vs targets)
        #   - Keyword theme quality (temas irrelevantes para restaurante)
        #   - Landing/setting (final_url vacía o incorrecta)
        #
        # "no auditable por keyword_view" ≠ "no auditable en absoluto"
        # keyword_view no aplica a Smart por diseño de Google — no es una
        # limitación del módulo, es una restricción del tipo de campaña.
        # ====================================================================
        smart_audit_result = None
        try:
            from engine.smart_campaign_auditor import audit_smart_campaigns
            smart_audit_result = audit_smart_campaigns(client, target_id)

            # Registrar propuestas de Smart en autonomous_decisions para que
            # aparezcan en el reporte semanal (acción humana requerida)
            for _sp in smart_audit_result.get("proposals", []):
                memory.record_autonomous_decision(
                    action_type="smart_audit",
                    risk_level=2,       # PROPOSE — requiere aprobación humana
                    urgency="normal",
                    decision="proposed",
                    campaign_id=_sp.get("campaign_id", ""),
                    campaign_name=_sp.get("campaign_name", ""),
                    keyword="",
                    evidence={
                        "signal":           "SMART_KT1",
                        "action":           _sp.get("action", ""),
                        "themes_to_remove": _sp.get("themes_to_remove", []),
                        "reason":           _sp.get("reason", ""),
                        "auto_execute":     False,
                    },
                    session_id=session_id,
                )
            _ss = smart_audit_result.get("summary", {})
            print(f"Fase SMART: {_ss.get('campaigns_audited', 0)} campaña(s) auditadas, "
                  f"{_ss.get('issues_total', 0)} issues, {_ss.get('proposals_generated', 0)} propuestas")
        except Exception as _smart_exc:
            print(f"Módulo SMART: error en smart_campaign_auditor — {_smart_exc}")
            smart_audit_result = {"error": str(_smart_exc)}

        if smart_audit_result:
            results["smart_audit"] = smart_audit_result

        # Extraer datos de campaña Local para inyectar en Haiku
        _local_data_for_insight = None
        if smart_audit_result and not smart_audit_result.get("error"):
            for _c in smart_audit_result.get("campaigns", []):
                if "local" in _c.get("campaign_name", "").lower():
                    _local_data_for_insight = {
                        "local_directions_count": _c.get("local_directions_count"),
                        "local_campaign_spend":   _c.get("metrics_7d", {}).get("cost_mxn"),
                    }
                    break

        # ── Smart Campaign: limpieza autónoma de temas irrelevantes ──────────
        # Ejecuta REMOVE solo si SMART_THEME_REMOVAL_ENABLED=true y hay >= 5 temas
        # restantes después de la eliminación (guarda de seguridad).
        smart_removals: list = []
        from config.agent_config import SMART_THEME_REMOVAL_ENABLED as _smart_removal_enabled, SMART_THEME_MIN_REMAINING as _smart_min_remaining
        if (
            smart_audit_result
            and not smart_audit_result.get("error")
            and _smart_removal_enabled
        ):
            from engine.ads_client import remove_smart_campaign_theme as _rm_theme
            for _sp in smart_audit_result.get("proposals", []):
                if _sp.get("type") != "smart_theme_cleanup":
                    continue
                _cid            = _sp.get("campaign_id", "")
                _cname          = _sp.get("campaign_name", "")
                _total_before   = _sp.get("total_themes_before", 0)
                _entries        = _sp.get("themes_to_remove_with_resources", [])
                _would_remain   = _total_before - len(_entries)

                if _would_remain < _smart_min_remaining:
                    _msg = (
                        f"Guarda activada: solo quedarían {_would_remain} temas "
                        f"(mínimo {_smart_min_remaining}) — se omite la limpieza."
                    )
                    print(f"Fase SMART cleanup [{_cname}]: {_msg}")
                    smart_removals.append({
                        "campaign_id":   _cid,
                        "campaign_name": _cname,
                        "status":        "guard_blocked",
                        "message":       _msg,
                        "themes":        [e["theme"] for e in _entries],
                    })
                    continue

                _removed_ok  = []
                _removed_err = []
                for _entry in _entries:
                    _res = _rm_theme(client, target_id, _entry["resource_name"])
                    if _res.get("status") == "success":
                        _removed_ok.append(_entry["theme"])
                    else:
                        _removed_err.append({"theme": _entry["theme"], "error": _res.get("message")})

                smart_removals.append({
                    "campaign_id":   _cid,
                    "campaign_name": _cname,
                    "status":        "executed" if not _removed_err else "partial",
                    "removed_ok":    _removed_ok,
                    "removed_err":   _removed_err,
                })
                print(
                    f"Fase SMART cleanup [{_cname}]: "
                    f"{len(_removed_ok)} eliminados, {len(_removed_err)} errores"
                )

        if smart_removals:
            results["smart_removals"] = smart_removals

        # Conteos por motivo para el summary granular
        all_items = results["executed"] + results["proposed"] + results["observed"] + results["blocked"]
        def _count_reason(reason_code):
            return sum(1 for i in all_items if i.get("block_reason") == reason_code)

        actually_executed = sum(
            1 for i in results["executed"]
            if i.get("exec_result", {}).get("status") == "executed"
        )
        would_auto_execute = len(results["executed"])  # risk_level==1, independiente de dry_run

        # ── Cobertura real por tipo de campaña ──────────────────────────────
        # SEARCH: campañas con al menos 1 keyword con gasto en el período.
        # (all_items usa "campaign" como nombre, no "campaign_id", por eso
        # se deriva directamente de la lista keywords ya cargada)
        _search_campaign_ids = {
            str(kw.get("campaign_id", ""))
            for kw in keywords
            if kw.get("cost_micros", 0) > 0 and kw.get("campaign_id")
        }
        # SMART: campañas auditadas por smart_campaign_auditor
        _smart_summary = (results.get("smart_audit") or {}).get("summary", {})
        _smart_count   = _smart_summary.get("campaigns_audited", 0)
        _smart_issues  = _smart_summary.get("issues_total", 0)

        results["summary"] = {
            # Estado del switch
            "auto_execute_enabled": auto_execute_enabled,
            "dry_run": dry_run,

            # Cobertura real por tipo (corrige el bug de "2 campañas auditadas")
            "campaigns_audited": {
                "search":  len(_search_campaign_ids),
                "smart":   _smart_count,
                "total":   len(_search_campaign_ids) + _smart_count,
            },
            # Conteo de keywords evaluados en módulo SEARCH (no son campañas)
            "keywords_evaluated": len(all_items),
            # Mantenido para compatibilidad con activity_log existente
            "total_evaluated": len(all_items),

            # Totales por decisión
            "observe": len(results["observed"]),
            "proposed_for_approval": len(results["proposed"]),
            "would_auto_execute": would_auto_execute,
            "actually_executed": actually_executed,
            "blocked_high_risk": len(results["blocked"]),

            # Issues de Smart Campaigns
            "smart_issues": _smart_issues,

            # Desglose por motivo (por qué no se ejecutó)
            "by_reason": {
                "learning_phase": _count_reason("learning_phase"),
                "protected_keyword": _count_reason("protected_keyword"),
                "protected_campaign": _count_reason("protected_campaign"),
                "insufficient_evidence": _count_reason("insufficient_evidence"),
                "requires_approval": _count_reason("requires_approval"),
                "high_risk_blocked": _count_reason("high_risk_blocked"),
                "auto_execute_ready": _count_reason("auto_execute_ready"),
                "auto_execute_disabled": would_auto_execute if dry_run else 0,
                "pending_proposal": _count_reason("pending_proposal"),
            },
        }

        # Fase 2: colectar propuestas nuevas para el correo consolidado
        proposals_emailed = 0
        email_error = False
        new_proposals = results["proposed"]  # solo las creadas en este ciclo (proposal_sent=0)
        if new_proposals:
            urgency_rank = {"critical": 0, "urgent": 1, "normal": 2}
            _pending_kw_proposals = sorted(
                new_proposals,
                key=lambda x: (urgency_rank.get(x.get("urgency", "normal"), 9), -x.get("spend", 0))
            )[:MAX_PROPOSALS_PER_EMAIL]
            logger.info(
                "Fase 2: %d propuesta(s) de keywords colectadas para correo consolidado",
                len(_pending_kw_proposals),
            )

        results["summary"]["proposals_emailed"] = proposals_emailed
        if email_error:
            results["summary"]["email_error"] = True

        # ====================================================================
        # CAPA DE VISIBILIDAD — Registro de actividad + correo diario
        #
        # Regla de honestidad:
        #   - Si campaigns_reviewed > 0 → corrida real → send_daily_summary_email
        #   - Si campaigns_reviewed == 0 → no hubo auditoría real →
        #     send_operational_incident_email (nunca disfrazamos un fallo)
        # ====================================================================
        try:
            from engine.activity_log import record_run as _record_run
            from engine.email_sender import (
                send_daily_summary_email as _send_daily,
                send_operational_incident_email as _send_incident,
            )
            from engine.memory import get_memory_system as _get_mem_daily

            _run_type = run_type
            _run_summary = _record_run(results, session_id, run_type=_run_type)
            _is_real     = _run_summary.get("is_real_audit", False)

            # Enriquecer con datos colectados para el correo consolidado
            _run_summary["keyword_proposals"]    = _pending_kw_proposals
            _run_summary["budget_proposals"]     = _pending_ba_proposals
            _run_summary["ba2_proposals"]        = _pending_ba2_proposals
            _run_summary["ba2_freed_budget_mxn"] = budget_scale_result.get("freed_budget_mxn", 0.0)
            _run_summary["geo_issues_for_email"] = _geo_issues_for_email
            # Sección 1: Salud de Canales
            _run_summary["ads_24h"]              = _ads_24h
            _run_summary["landing_response_ms"]  = _landing_response_ms
            # Smart audit data completa — para mostrar issues inline en el correo diario
            # (no retener hasta el reporte semanal del lunes)
            _run_summary["smart_audit"]    = results.get("smart_audit")
            _run_summary["smart_removals"] = results.get("smart_removals") or []
            # GEO unverified: campañas SMART con geo correcto según API pero sin confirmación de UI Express
            _geo_audit_d = results.get("geo_audit")
            if isinstance(_geo_audit_d, dict):
                _geo_pol_correct = (_geo_audit_d.get("policy_audit") or {}).get("correct") or []
                _run_summary["geo_unverified_campaigns"] = [
                    e for e in _geo_pol_correct
                    if e.get("final_operational_state") in ("unverified", "stale")
                ]
            else:
                _run_summary["geo_unverified_campaigns"] = []
            try:
                from engine.sheets_client import resumen_negocio_para_agente as _rna
                _run_summary["ventas_ayer"] = _rna(days=1)
            except Exception as _sheets_exc:
                logger.warning("ventas_ayer: no disponible — %s", _sheets_exc)
                _run_summary["ventas_ayer"] = {}

            # GA4: Movimiento en la Web (24h) para correo consolidado
            try:
                from engine.ga4_client import fetch_ga4_events_detailed as _ga4_fetch
                _ga4_raw = _ga4_fetch(days=1)
                if isinstance(_ga4_raw, dict) and "error" not in _ga4_raw:
                    _funnel = _ga4_raw.get("conversion_funnel", {})
                    _run_summary["ga4_web"] = {
                        "page_views":         _funnel.get("page_view", 0),
                        "click_pedir":        _funnel.get("click_pedir_online", 0),
                        "click_reservar":     _funnel.get("click_reservar", 0),
                        "reserva_completada": _funnel.get("reserva_completada", 0),
                        # session_start ≈ sesiones únicas (mejor proxy para usuarios activos)
                        "usuarios_activos":   _ga4_raw.get("events_by_name", {}).get("session_start", 0),
                    }
                else:
                    _run_summary["ga4_web"] = {"error": str((_ga4_raw or {}).get("error", "unknown"))}
            except Exception as _ga4_exc:
                logger.warning("ga4_web: no disponible — %s", _ga4_exc)
                _run_summary["ga4_web"] = None

            # Acciones aprobadas recientemente (últimas 72h) — confirmación visual en el correo
            try:
                import sqlite3 as _sq3
                from engine.db_sync import get_db_path as _get_db_path_email
                _conn_a = _sq3.connect(_get_db_path_email())
                _row_a = _conn_a.execute(
                    "SELECT COUNT(*) FROM autonomous_decisions "
                    "WHERE decision = 'approved' AND approved_at > datetime('now', '-72 hours')"
                ).fetchone()
                _conn_a.close()
                _run_summary["recently_approved_count"] = int(_row_a[0]) if _row_a else 0
            except Exception as _apr_exc:
                logger.warning("recently_approved_count: no disponible — %s", _apr_exc)
                _run_summary["recently_approved_count"] = 0

            # 🧠 Inteligencia cruzada: Ads + GA4 + Sheets → Claude Haiku
            try:
                from engine.email_sender import generate_daily_insight as _gen_insight
                _run_summary["agent_insight"] = _gen_insight(
                    ads_data=_ads_24h,
                    ga4_data=_run_summary.get("ga4_web"),
                    sheets_data=_run_summary.get("ventas_ayer"),
                    local_data=_local_data_for_insight,
                )
            except Exception as _insight_exc:
                logger.warning("agent_insight: no disponible — %s", _insight_exc)
                _run_summary["agent_insight"] = None

            _mem_daily    = _get_mem_daily()
            _already_sent = _mem_daily.has_recent_alert("daily_summary", 12)

            _email_sent = False
            if not _already_sent:
                if _is_real:
                    # Auditoría real — correo consolidado (heartbeat + propuestas + geo)
                    _email_sent = _send_daily(_run_summary, session_id)
                else:
                    # Sin campañas revisadas — incidente operativo
                    _errors = _run_summary.get("errors", [])
                    _email_sent = _send_incident(
                        session_id=session_id,
                        incident_reason="La auditoría no pudo obtener datos de Google Ads.",
                        retry_attempted=False,
                        compensatory_ran=False,
                        system_restored=False,
                        technical_detail=" | ".join(_errors[:3]),
                        timestamp_merida=_run_summary.get("timestamp_merida", ""),
                    )

                if _email_sent:
                    # Marcar todas las propuestas del ciclo como enviadas
                    _all_sent_ids = (
                        [p["decision_id"] for p in _pending_kw_proposals if "decision_id" in p] +
                        [p["decision_id"] for p in _pending_ba_proposals  if "decision_id" in p] +
                        [p["decision_id"] for p in _pending_geo_proposals  if "decision_id" in p]
                    )
                    if _all_sent_ids:
                        _mem_daily.mark_proposals_sent(_all_sent_ids)
                    # Registrar dedup de geo_alert si hubo alertas GEO nuevas
                    if _geo_dedup_should_record:
                        _mem_daily.record_autonomous_decision(
                            action_type="geo_alert",
                            risk_level=RISK_EXECUTE,
                            urgency="normal",
                            decision="alert_sent",
                            campaign_id="",
                            campaign_name="",
                            keyword="geo_alert",
                            evidence={
                                "geo1_count":   len(_pending_geo_proposals),
                                "geo0_count":   len([g for g in _geo_issues_for_email
                                                     if g.get("signal") == "GEO0"]),
                                "consolidated": True,
                            },
                            session_id=session_id,
                        )
                    _mem_daily.record_autonomous_decision(
                        action_type="daily_summary",
                        risk_level=0,
                        urgency="normal",
                        decision="alert_sent",
                        campaign_id="SYSTEM",
                        campaign_name="Sistema",
                        keyword="",
                        evidence={
                            "result_class": _run_summary.get("result_class"),
                            "is_real_audit": _is_real,
                        },
                        session_id=session_id,
                    )

            results["daily_summary"] = {
                "run_id":         _run_summary.get("run_id"),
                "result_class":   _run_summary.get("result_class"),
                "is_real_audit":  _is_real,
                "email_sent":     _email_sent,
                "email_type":     "daily" if _is_real else "incident",
            }
        except Exception as _daily_exc:
            logger.warning("Visibilidad diaria: error no crítico — %s", _daily_exc)

        # ── Persistir DB en GCS (no bloquea la respuesta) ─────────────────────
        try:
            from engine.db_sync import upload_to_gcs as _upload_db
            _uploaded = _upload_db()
            if _uploaded:
                print("[DB_SYNC] ✓ DB sincronizada a GCS tras auditoría")
        except Exception as _upload_err:
            logger.warning("[DB_SYNC] upload post-audit falló (no crítico): %s", _upload_err)

        # ── Actualizar snapshot del dashboard para carga rápida ─────────────
        try:
            _mc_snap = await __import__("main", fromlist=["mission_control_data"]).mission_control_data()
            logger.info("[SNAPSHOT] Dashboard snapshot actualizado tras auditoría")
        except Exception as _snap_exc:
            logger.warning("[SNAPSHOT] No se pudo actualizar snapshot post-audit: %s", _snap_exc)

        logger.info(
            "_run_audit_task: completada — sesión=%s run_type=%s",
            session_id, run_type,
        )

    except Exception as exc:
        import traceback
        logger.error(
            "_run_audit_task: error no capturado — sesión=%s\n%s",
            session_id, traceback.format_exc(),
        )
        # Si era una corrida compensatoria, enviar incidente de doble falla
        if run_type == "compensatory":
            try:
                from engine.email_sender import send_operational_incident_email as _si
                _si(
                    session_id=f"compensatory_failed_{session_id}",
                    incident_reason="Falló tanto la corrida de las 7am como la corrida compensatoria.",
                    retry_attempted=True,
                    compensatory_ran=False,
                    system_restored=False,
                    technical_detail=str(exc)[:400],
                )
            except Exception as _email_exc:
                logger.error(
                    "_run_audit_task: no se pudo enviar incidente de doble falla — %s",
                    _email_exc,
                )
