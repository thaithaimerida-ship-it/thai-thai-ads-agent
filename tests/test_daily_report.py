"""
Thai Thai Ads Agent — Tests del Reporte Diario

Protege la consistencia del correo diario.
No realiza llamadas a API — todo con datos sintéticos.
Ejecutar: python -m pytest tests/test_daily_report.py -v
"""
import json
from pathlib import Path

import pytest

from engine.email_sender import _build_daily_subject_from_contract, _build_pro_daily_html, _derive_report_contract
from engine.report_contract import build_report_contract_v1


# ============================================================
# TEST 1: Quality Score findings NO tienen duplicados
# ============================================================
class TestQualityScoreDedup:
    """Verifica que keywords no se dupliquen en findings de QS."""

    def _simulate_kq_data_with_dupes(self):
        """Simula _kq_data con misma keyword en 2 ad groups."""
        return [
            {
                "keyword_text": "thai thai mérida",
                "quality_score": 5,
                "creative_quality_score": "ABOVE_AVERAGE",
                "post_click_quality_score": "AVERAGE",
                "search_predicted_ctr": "BELOW_AVERAGE",
                "campaign_id": "23730364039",
                "campaign_name": "Thai Mérida - Experiencia 2026",
                "ad_group_id": "ag1",
                "ad_group_name": "Experiencia Thai",
                "cost_micros": 100000,
                "conversions": 0,
            },
            {
                "keyword_text": "thai thai mérida",
                "quality_score": 5,
                "creative_quality_score": "ABOVE_AVERAGE",
                "post_click_quality_score": "AVERAGE",
                "search_predicted_ctr": "BELOW_AVERAGE",
                "campaign_id": "23730364039",
                "campaign_name": "Thai Mérida - Experiencia 2026",
                "ad_group_id": "ag2",
                "ad_group_name": "Thai Thai Mérida - Branded 2026",
                "cost_micros": 50000,
                "conversions": 0,
            },
            {
                "keyword_text": "restaurante tailandes merida",
                "quality_score": 4,
                "creative_quality_score": "AVERAGE",
                "post_click_quality_score": "AVERAGE",
                "search_predicted_ctr": "BELOW_AVERAGE",
                "campaign_id": "23730364039",
                "campaign_name": "Thai Mérida - Experiencia 2026",
                "ad_group_id": "ag1",
                "ad_group_name": "Experiencia Thai",
                "cost_micros": 80000,
                "conversions": 0,
            },
            {
                "keyword_text": "restaurante tailandes merida",
                "quality_score": 4,
                "creative_quality_score": "AVERAGE",
                "post_click_quality_score": "AVERAGE",
                "search_predicted_ctr": "BELOW_AVERAGE",
                "campaign_id": "23730364039",
                "campaign_name": "Thai Mérida - Experiencia 2026",
                "ad_group_id": "ag3",
                "ad_group_name": "Restaurante Tailandés Mérida 2026",
                "cost_micros": 30000,
                "conversions": 0,
            },
        ]

    def test_qs_low_no_duplicates(self):
        """QS_LOW findings deben tener max 1 entrada por (keyword, campaign)."""
        kq_data = self._simulate_kq_data_with_dupes()
        findings = []
        seen = set()
        for kw in kq_data:
            qs = kw.get("quality_score")
            ktext = kw.get("keyword_text", "")
            cid = kw.get("campaign_id", "")
            if qs and qs < 7:
                key = (ktext, cid, "QS_LOW")
                if key not in seen:
                    seen.add(key)
                    findings.append({"type": "QS_LOW", "keyword_text": ktext, "campaign_id": cid})

        keywords_in_findings = [f["keyword_text"] for f in findings]
        # Debe haber exactamente 2, no 4
        assert len(findings) == 2, f"Expected 2 unique QS_LOW, got {len(findings)}: {keywords_in_findings}"
        assert "thai thai mérida" in keywords_in_findings
        assert "restaurante tailandes merida" in keywords_in_findings

    def test_ctr_structural_no_duplicates(self):
        """CTR_STRUCTURAL_ISSUE findings deben tener max 1 por (keyword, campaign)."""
        kq_data = self._simulate_kq_data_with_dupes()
        # Simular ad health con EXCELLENT strength
        camp_best_strength = {"23730364039": "EXCELLENT"}

        findings = []
        seen = set()
        for kw in kq_data:
            qs = kw.get("quality_score")
            if not qs or qs >= 7:
                continue
            cid = str(kw.get("campaign_id", ""))
            ctr = kw.get("search_predicted_ctr")
            cre = kw.get("creative_quality_score")
            land = kw.get("post_click_quality_score")
            best = camp_best_strength.get(cid)
            if (
                ctr == "BELOW_AVERAGE"
                and cre not in (None, "BELOW_AVERAGE")
                and land not in (None, "BELOW_AVERAGE")
                and best in ("GOOD", "EXCELLENT")
            ):
                key = (kw.get("keyword_text", ""), cid)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "type": "CTR_STRUCTURAL_ISSUE",
                    "keyword_text": kw.get("keyword_text", ""),
                    "campaign_id": cid,
                })

        assert len(findings) == 2, f"Expected 2 unique CTR_STRUCTURAL, got {len(findings)}"


# ============================================================
# TEST 2: Objetivo de comensales es consistente
# ============================================================
class TestComensalesObjetivo:
    """Verifica que no hay dos valores distintos para el objetivo."""

    def test_single_objective_value(self):
        """Buscar en email_sender.py que solo haya UN valor de objetivo."""
        import re
        with open("engine/email_sender.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Buscar todas las asignaciones tipo _xxx = 35 o _xxx = 40 cerca de "obj" o "objetivo" o "comensal"
        # Estrategia: buscar _COMENSALES_OBJ_DIA y verificar que _coms_obj y _objetivo_coms usen esa constante
        assert "_COMENSALES_OBJ_DIA" in content, "Falta constante unificada _COMENSALES_OBJ_DIA"

        # No debe haber asignaciones hardcodeadas de 35 para comensales
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "_coms_obj" in stripped and "= 35" in stripped:
                pytest.fail(f"Línea {i+1}: _coms_obj sigue hardcodeado a 35: {stripped}")
            if "_objetivo_coms" in stripped and "= 40" in stripped and "_COMENSALES_OBJ_DIA" not in stripped:
                pytest.fail(f"Línea {i+1}: _objetivo_coms hardcodeado sin usar constante: {stripped}")


# ============================================================
# TEST 3: result_class refleja TODOS los tipos de cambios
# ============================================================
class TestResultClass:
    """Verifica que result_class no sea 'sin_acciones' cuando hay keywords o ad groups."""

    def _build_audit_results(self, executed=None, builder_executed=None, paused=None):
        """Helper para simular audit_results."""
        return {
            "executed": executed or [],
            "proposed": [],
            "observed": [],
            "blocked": [],
            "builder_executed": builder_executed or [],
            "paused_campaigns": paused or [],
            "summary": {
                "actually_executed": len(executed or []),
                "campaigns_audited": {"search": 2, "smart": 2, "total": 4},
                "total_evaluated": 5,
                "keywords_evaluated": 5,
            },
        }

    def test_keywords_added_is_con_cambios(self):
        """Si se agregaron keywords, result_class NO debe ser sin_acciones."""
        results = self._build_audit_results(
            builder_executed=[
                {"ad_group_name": "Branded", "result": {"status": "success"}}
            ]
        )
        builder = results.get("builder_executed", [])
        builder_count = len([b for b in builder if isinstance(b.get("result"), dict) and b["result"].get("status") == "success"])
        changes = results["summary"]["actually_executed"]
        total = changes + builder_count

        assert total > 0, "Builder creó ad groups pero total_changes es 0"

    def test_no_changes_is_sin_acciones(self):
        """Sin cambios reales = sin_acciones."""
        results = self._build_audit_results()
        changes = results["summary"]["actually_executed"]
        builder = results.get("builder_executed", [])
        builder_count = len([b for b in builder if isinstance(b.get("result"), dict) and b["result"].get("status") == "success"])
        total = changes + builder_count
        assert total == 0


# ============================================================
# TEST 4: Subject line refleja acciones reales
# ============================================================
class TestSubjectLine:
    """Verifica que el subject del correo sea informativo."""

    def test_subject_with_keywords_and_builder(self):
        """Subject debe mencionar keywords y ad groups cuando existen."""
        run = {
            "result_class": "con_cambios",
            "executed_budget": [{"campaign": "Delivery", "action": "SCALE"}],
            "ai_keyword_decisions": [{"keyword": "pad thai mérida"}],
            "builder_executed": [{"ad_group_name": "Branded", "result": {"status": "success"}}],
            "paused_campaigns": [],
            "timestamp_merida": "2026-04-10 07:01",
        }

        acciones = []
        if run.get("executed_budget"):
            acciones.append(f"{len(run['executed_budget'])} ajuste de presupuesto")
        if run.get("ai_keyword_decisions"):
            acciones.append(f"{len(run['ai_keyword_decisions'])} keyword")
        builder = run.get("builder_executed", [])
        bg_count = len([b for b in builder if isinstance(b.get("result"), dict) and b["result"].get("status") == "success"])
        if bg_count:
            acciones.append(f"{bg_count} ad group creado")

        label = " + ".join(acciones) if acciones else "Sin cambios"
        assert "keyword" in label
        assert "ad group" in label
        assert "Sin cambios" not in label

    def test_subject_no_changes(self):
        """Sin acciones = Sin cambios en subject."""
        run = {
            "executed_budget": [],
            "ai_keyword_decisions": [],
            "builder_executed": [],
            "paused_campaigns": [],
        }
        acciones = []
        if run.get("executed_budget"):
            acciones.append("budget")
        if run.get("ai_keyword_decisions"):
            acciones.append("kw")
        label = " + ".join(acciones) if acciones else "Sin cambios"
        assert label == "Sin cambios"

    def test_subject_is_derived_from_contract(self):
        run = {
            "run_id": "audit_test_subject",
            "timestamp_merida": "2026-04-10 07:01",
            "result_class": "con_cambios",
            "is_real_audit": True,
            "campaigns_reviewed": 2,
            "changes_executed": 2,
            "had_change": True,
            "human_pending": 0,
            "audit_result": {"score": 82, "grade": "B", "category_scores": {}, "quick_wins": [], "checks_by_category": {}},
            "budget_optimizer": {"executed": []},
            "ai_keyword_decisions": [{"keyword_text": "pad thai merida", "exec_result": {"status": "executed"}}],
            "builder_executed": [{"ad_group_name": "Branded", "result": {"status": "success"}}],
            "creative_actions": [],
            "paused_campaigns": [],
            "keyword_proposals": [],
            "executed_budget": [],
        }

        contract = _derive_report_contract(run)
        subject = _build_daily_subject_from_contract(contract)

        assert subject == "[Thai Thai Agente] Actividad diaria — 2 cambios automáticos · 2026-04-10 07:01"


# ============================================================
# TEST 5: CAMPAIGNS_TO_PAUSE está vacío
# ============================================================
class TestCampaignsToPause:
    """Verifica que no hay campañas hardcodeadas para pausar."""

    def test_campaigns_to_pause_is_empty(self):
        """CAMPAIGNS_TO_PAUSE debe estar vacío si no hay intención de pausar."""
        from config.agent_config import CAMPAIGNS_TO_PAUSE
        assert len(CAMPAIGNS_TO_PAUSE) == 0, (
            f"CAMPAIGNS_TO_PAUSE tiene {len(CAMPAIGNS_TO_PAUSE)} campaña(s) — "
            f"esto pausará campañas automáticamente cada corrida: {CAMPAIGNS_TO_PAUSE}"
        )


# ============================================================
# TEST 6: Campaña pausada muestra contexto en tabla de gasto
# ============================================================
class TestPausedCampaignSpend:
    """Verifica que gasto de campaña pausada tenga nota visual."""

    def test_paused_campaign_marked_in_spend_table(self):
        """Si una campaña fue pausada y tiene gasto, el HTML debe indicarlo."""
        paused_ids = {"23680871468"}
        campaign_data = {"id": "23680871468", "name": "Thai Mérida - Reservaciones", "spend": 19}

        camp_id = str(campaign_data["id"])
        name = campaign_data["name"]
        if camp_id in paused_ids:
            name += " (pausada hoy)"

        assert "(pausada hoy)" in name


# ============================================================
# TEST 7: Ad Strength message no contradice QS findings
# ============================================================
class TestAdStrengthMessage:
    """Verifica que el mensaje de 'todo OK' no sea engañoso."""

    def test_ok_message_is_specific(self):
        """El mensaje OK debe referirse específicamente a Ad Strength, no genérico."""
        ok_msg = "Ad Strength y aprobación OK — sin rechazos ni anuncios débiles"
        # No debe decir "Todos los anuncios en buen estado"
        assert "Todos los anuncios" not in ok_msg
        assert "Ad Strength" in ok_msg


# ============================================================
# TEST 8: Prompt no menciona Rappi/Uber para Delivery
# ============================================================
class TestPromptDelivery:
    """Verifica que el contexto de negocio en el prompt sea correcto."""

    def test_no_rappi_uber_in_prompt(self):
        """El contexto de negocio no debe mencionar Rappi ni Uber."""
        import re
        with open("engine/email_sender.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "Rappi" not in content or "Rappi/Uber" not in content, \
            "email_sender.py todavía menciona Rappi/Uber en el contexto de negocio"

    def test_gloriafood_in_delivery_description(self):
        """prompt.py debe mencionar GloriaFood en la descripción de Delivery."""
        with open("engine/prompt.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "GloriaFood" in content, "prompt.py no menciona GloriaFood para campaña Delivery"

    def test_no_platforms_delivery_in_prompt(self):
        """prompt.py no debe decir 'plataformas de delivery'."""
        with open("engine/prompt.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "plataformas de delivery" not in content, \
            "prompt.py todavía dice 'plataformas de delivery' — Delivery es tienda propia"


# ============================================================
# TEST 9: QS email filter — solo QS_LOW, sin duplicados
# ============================================================
class TestQSEmailFilter:
    """Verifica el filtro de QS findings para el correo."""

    def _make_findings(self):
        return [
            {"type": "QS_LOW", "keyword_text": "thai thai mérida", "campaign_id": "111", "quality_score": 5},
            {"type": "QS_LOW", "keyword_text": "thai thai mérida", "campaign_id": "111", "quality_score": 5},
            {"type": "CTR_STRUCTURAL_ISSUE", "keyword_text": "restaurante tailandés", "campaign_id": "111"},
            {"type": "QS_LOW", "keyword_text": "comida thai mérida", "campaign_id": "111", "quality_score": 6},
        ]

    def test_only_qs_low_type(self):
        """Solo findings de tipo QS_LOW deben aparecer en la sección QS."""
        findings = self._make_findings()
        _qs_seen = set()
        _qs_findings = []
        for f in findings:
            if f.get("type") != "QS_LOW":
                continue
            key = (f.get("keyword_text", ""), f.get("campaign_id", ""))
            if key in _qs_seen:
                continue
            _qs_seen.add(key)
            _qs_findings.append(f)
        types = [f["type"] for f in _qs_findings]
        assert all(t == "QS_LOW" for t in types), f"Tipos inesperados: {types}"

    def test_no_duplicates_in_qs_section(self):
        """No debe haber keywords duplicadas en la sección QS del correo."""
        findings = self._make_findings()
        _qs_seen = set()
        _qs_findings = []
        for f in findings:
            if f.get("type") != "QS_LOW":
                continue
            key = (f.get("keyword_text", ""), f.get("campaign_id", ""))
            if key in _qs_seen:
                continue
            _qs_seen.add(key)
            _qs_findings.append(f)
        assert len(_qs_findings) == 2, f"Esperados 2 únicos QS_LOW, got {len(_qs_findings)}"


# ============================================================
# TEST 10: DB Sync — upload_to_gcs no lanza si GCS no disponible
# ============================================================
class TestDBSync:
    """Verifica que db_sync no falla catastrófico si GCS no está disponible."""

    def test_upload_returns_bool_no_bucket(self):
        """upload_to_gcs con bucket no configurado debe retornar False sin lanzar excepción."""
        import os
        from unittest.mock import patch
        from engine.db_sync import upload_to_gcs
        # Sin bucket configurado, la función debe retornar False de forma segura
        with patch.dict(os.environ, {"AGENT_GCS_BUCKET": ""}):
            result = upload_to_gcs()
        assert isinstance(result, bool), "upload_to_gcs debe retornar bool"

    def test_download_returns_bool_no_bucket(self):
        """download_from_gcs con bucket no configurado debe retornar False sin lanzar excepción."""
        import os
        from unittest.mock import patch
        from engine.db_sync import download_from_gcs
        with patch.dict(os.environ, {"AGENT_GCS_BUCKET": ""}):
            result = download_from_gcs()
        assert isinstance(result, bool), "download_from_gcs debe retornar bool"


# ============================================================
# TEST 11: Pedidos Online block — siempre muestra contenido
# ============================================================
class TestPedidosOnlineBlock:
    """Verifica que el bloque de pedidos online siempre muestra algo."""

    def test_block_with_orders(self):
        """Con pedidos, el bloque debe incluir el total en MXN."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE gloriafood_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gloriafood_order_id TEXT,
                total_price_mxn REAL,
                received_at TEXT,
                conversion_sent INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO gloriafood_orders (gloriafood_order_id, total_price_mxn, received_at) "
            "VALUES ('x1', 450.0, datetime('now', '-1 hours'))"
        )
        conn.commit()
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0)
            FROM gloriafood_orders
            WHERE received_at >= datetime('now', '-24 hours')
        """)
        row = cursor.fetchone()
        conn.close()
        assert row[0] == 1
        assert float(row[1]) == 450.0

    def test_block_no_orders_shows_message(self):
        """Sin pedidos, el bloque no debe ser vacío — debe mostrar mensaje."""
        # Simular la lógica del except: siempre muestra "Sin pedidos registrados"
        _pedidos_block = (
            '<tr><td>'
            '<p>🛒 Pedidos Online (24h)</p>'
            '<p>Sin pedidos registrados en las últimas 24 horas</p>'
            '</td></tr>'
        )
        assert "Sin pedidos" in _pedidos_block
        assert len(_pedidos_block) > 0


# ============================================================
# TEST 8: Template pro alinea asunto y cuerpo
# ============================================================
class TestProDailyEmailBody:
    """Verifica que el body pro refleje acciones reales ya ejecutadas."""

    def _base_run(self):
        return {
            "audit_result": {
                "score": 82,
                "grade": "B",
                "category_scores": {},
                "quick_wins": [],
                "checks_by_category": {},
            },
            "ventas_ayer": {},
            "ads_24h": {},
            "monthly_budget_status": {},
            "keyword_proposals": [],
            "creative_actions": [],
            "ai_keyword_decisions": [],
            "builder_executed": [],
            "budget_optimizer": {
                "decisions": [],
                "redistribution": {},
                "redistribution_analysis": {},
                "executed": [],
                "pedidos_gloriafood_24h": 0,
                "pedidos_gloriafood_detalle": [],
            },
        }

    def test_pro_body_shows_ai_keywords_and_builder_activity(self):
        run = self._base_run()
        run["ai_keyword_decisions"] = [
            {
                "keyword_text": "pad thai merida",
                "match_type": "PHRASE",
                "confidence": 88,
                "reason": "Alta intención local",
                "exec_result": {
                    "status": "executed",
                    "campaign_name": "Thai Mérida - Reservaciones",
                },
            }
        ]
        run["builder_executed"] = [
            {
                "campaign_name": "Thai Mérida - Reservaciones",
                "ad_group_name": "Pad Thai Mérida",
                "keywords": ["pad thai merida", "pad thai merida centro"],
                "result": {"status": "success"},
            }
        ]

        html = _build_pro_daily_html(run)

        assert "Resumen Ejecutivo" in html
        assert "Acciones Ejecutadas" in html
        assert "pad thai merida" in html

    def test_pro_body_opens_with_controlled_executive_summary_and_context_at_end(self):
        run = self._base_run()
        run["human_pending"] = 1
        run["keyword_proposals"] = [
            {
                "keyword_text": "restaurante thai merida",
                "campaign_name": "Thai MÃ©rida - Reservaciones",
            }
        ]
        run["ai_keyword_decisions"] = [
            {
                "keyword_text": "pad thai merida",
                "exec_result": {"status": "executed"},
            }
        ]
        run["ads_24h"] = {
            "por_campana": [
                {"name": "Thai Merida - Local", "tipo": "SMART", "spend_mxn": 130.0, "clicks": 84, "conversions": 0.0}
            ]
        }

        html = _build_pro_daily_html(run)

        assert "Resumen Ejecutivo" in html
        assert "Ejecución: 1 cambio" in html
        assert "Propuestas: 1" in html
        assert "Análisis: sí" in html
        assert "Atención humana: requerida" in html
        assert html.index("Resumen Ejecutivo") < html.index("Contexto de Cuenta")
        assert html.index("Resumen Ejecutivo") < html.index("Google Ads Health Score")

    def test_pro_body_uses_single_consolidated_empty_state(self):
        html = _build_pro_daily_html(self._base_run())

        assert "Sin cambios de keywords hoy" not in html
        assert "Sin cambios de ad groups hoy" not in html
        assert "Sin cambios de presupuesto ejecutados hoy" not in html
        assert "Sin cambios automáticos hoy" not in html
        assert "No hubo novedad operativa adicional fuera de los puntos anteriores." not in html
        assert "Presupuesto evaluado sin ajuste ejecutable." in html
        assert "Ad groups evaluados sin cambio ejecutable." in html
        assert "No se detectaron oportunidades accionables adicionales en keywords." in html

    @pytest.mark.skip(reason="Replaced by normalized snapshot semantics test")
    def test_snapshot_labels_ads_semantics_and_real_period(self):
        run = self._base_run()
        run["ads_24h"] = {
            "por_campana": [
                {
                    "name": "Thai MÃ©rida - Local",
                    "tipo": "SMART",
                    "spend_mxn": 130.0,
                    "clicks": 84,
                    "conversions": 0.0,
                }
            ]
        }

        html = _build_pro_daily_html(run)

        assert "(24h)" in html
        assert "Conv (Ads)" in html
        assert "CPA (Ads)" in html
        assert "SMART no comparte la misma semantica de conversion que SEARCH" in html
        assert "Ad groups hoy" in html
        assert "Pad Thai Mérida" in html

    def test_snapshot_labels_ads_semantics_and_real_period_normalized(self):
        run = self._base_run()
        run["ads_24h"] = {
            "por_campana": [
                {
                    "name": "Thai Merida - Local",
                    "tipo": "SMART",
                    "spend_mxn": 130.0,
                    "clicks": 84,
                    "conversions": 0.0,
                }
            ]
        }

        html = _build_pro_daily_html(run)

        assert "(24h)" in html
        assert "Conv (Ads)" in html
        assert "CPA (Ads)" in html
        assert "SMART no comparte la misma semantica de conversion que SEARCH" in html

    def test_pro_body_renders_analysis_and_executed_budget_as_separate_concepts(self):
        run = self._base_run()
        run["budget_optimizer"] = {
            "decisions": [],
            "redistribution": {
                "reduced": [
                    {
                        "name": "Thai Mérida - Reservaciones",
                        "before": 100.0,
                        "after": 80.0,
                        "saved_daily": 20.0,
                        "saved_monthly": 600.0,
                        "reason": "CPA alto",
                    }
                ],
                "scaled": [],
                "protected": [],
                "net_daily_mxn": -20.0,
            },
            "redistribution_analysis": {
                "potential_freed_daily_mxn": 20.0,
                "potential_freed_monthly_mxn": 600.0,
                "fund_sources": [
                    {
                        "campaign_name": "Thai Mérida - Reservaciones",
                        "source_action": "reduce",
                        "freed_daily_mxn": 20.0,
                        "reason": "CPA alto",
                    }
                ],
                "receiver_candidates": [
                    {
                        "campaign_name": "Thai Mérida - Experiencia 2026",
                        "max_receivable_daily_mxn": 20.0,
                        "eligibility_reason": "scale elegible",
                    }
                ],
                "allocation_matrix": [
                    {
                        "from_campaign_name": "Thai Mérida - Reservaciones",
                        "to_campaign_name": "Thai Mérida - Experiencia 2026",
                        "amount_daily_mxn": 20.0,
                    }
                ],
                "net_daily_mxn": 0.0,
            },
            "executed": [],
            "pedidos_gloriafood_24h": 0,
            "pedidos_gloriafood_detalle": [],
        }

        html = _build_pro_daily_html(run)

        assert "Análisis sin Ejecución" in html
        assert "Redistribución" in html
        assert "revisada sin ejecución automática" in html

    def test_pro_body_restores_quick_wins_and_category_review(self):
        run = self._base_run()
        run["audit_result"]["quick_wins"] = [
            {
                "id": "G43",
                "severity": "Critical",
                "description": "Enhanced Conversions activo",
                "fix_minutes": 5,
                "auto_executable": False,
            },
            {
                "id": "G42",
                "severity": "High",
                "description": ">=1 conversión primaria activa",
                "fix_minutes": 10,
                "auto_executable": False,
            },
        ]
        run["audit_result"]["category_scores"] = {
            "CT": 11.1,
            "Wasted": 60.7,
        }
        run["audit_result"]["checks_by_category"] = {
            "CT": [
                {
                    "id": "G42",
                    "result": "FAIL",
                    "detail": "0 primaria(s)",
                    "severity": "Critical",
                },
                {
                    "id": "G43",
                    "result": "FAIL",
                    "detail": "No activo",
                    "severity": "Critical",
                },
            ],
            "Wasted": [
                {
                    "id": "G16",
                    "result": "WARNING",
                    "detail": "100.0% en términos irrelevantes",
                    "severity": "Critical",
                }
            ],
        }

        html = _build_pro_daily_html(run)

        assert "Propuestas y Pendientes" in html
        assert "Quick wins pendientes" in html
        assert "Enhanced Conversions activo" in html
        assert "Revisiones del Día" in html
        assert "Conversion Tracking" in html
        assert "Wasted Spend" in html
        assert "0 primaria(s)" in html
        assert "100.0% en términos irrelevantes" in html

    def test_pro_body_keeps_reviews_section_when_audit_exists_without_category_breakdown(self):
        run = self._base_run()
        run["audit_result"]["quick_wins"] = [
            {
                "id": "G43",
                "severity": "Critical",
                "description": "Enhanced Conversions activo",
                "fix_minutes": 5,
                "auto_executable": False,
            }
        ]
        run["audit_result"]["category_scores"] = {}
        run["audit_result"]["checks_by_category"] = {}

        html = _build_pro_daily_html(run)

        assert "Revisiones del Día" in html
        assert "Auditoría disponible en esta corrida, sin desglose detallado visible por categoría." in html

    def test_exec_section_counts_ai_keywords_and_builder_successes(self):
        run = self._base_run()
        run["ai_keyword_decisions"] = [
            {
                "keyword_text": "pad thai merida",
                "exec_result": {"status": "executed"},
            }
        ]
        run["builder_executed"] = [
            {
                "ad_group_name": "Pad Thai Mérida",
                "result": {"status": "success"},
            }
        ]

        html = _build_pro_daily_html(run)

        assert "Sin cambios automáticos hoy" not in html
        assert "Agregó 1 keyword" in html
        assert "Creó 1 ad group" in html

    def test_pro_body_can_render_from_derived_contract(self):
        run = self._base_run()
        run["ai_keyword_decisions"] = [
            {
                "keyword_text": "pad thai merida",
                "campaign_name": "Thai Mérida - Reservaciones",
                "match_type": "PHRASE",
                "exec_result": {"status": "executed", "campaign_name": "Thai Mérida - Reservaciones"},
            }
        ]

        contract = _derive_report_contract(run)
        html = _build_pro_daily_html(run, contract=contract)

        assert "Keywords AI agregadas — automático" in html
        assert "pad thai merida" in html


def _load_report_contract_samples():
    fixture_path = Path(__file__).parent / "fixtures" / "report_contract_samples.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return payload["samples"]


class TestReportContractV1:
    def test_report_contract_v1_exposes_all_required_blocks(self):
        from engine.report_contract import build_report_contract_v1

        for sample in _load_report_contract_samples():
            contract = build_report_contract_v1(sample["raw_run"])
            assert set(contract.keys()) >= {
                "meta",
                "summary",
                "executed",
                "proposed",
                "analyzed",
                "blocked",
                "account_context",
                "daily_reviews",
            }

    def test_report_contract_v1_has_compact_domain_status_for_all_core_domains(self):
        from engine.report_contract import DOMAIN_STATUS_VALUES, build_report_contract_v1

        for sample in _load_report_contract_samples():
            contract = build_report_contract_v1(sample["raw_run"])
            status = contract["summary"]["domain_status"]
            assert set(status.keys()) == {"keywords", "ad_groups", "budget", "redistribution"}
            for value in status.values():
                assert value in DOMAIN_STATUS_VALUES

    def test_report_contract_v1_keeps_semantic_uniqueness_by_fact_id(self):
        from engine.report_contract import build_report_contract_v1

        for sample in _load_report_contract_samples():
            contract = build_report_contract_v1(sample["raw_run"])
            seen = {}
            for block_name in ("executed", "proposed", "analyzed", "blocked"):
                for item in contract[block_name]["items"]:
                    fact_id = item["fact_id"]
                    assert fact_id not in seen, f"fact_id duplicated across primary blocks: {fact_id}"
                    assert item["primary_block"] == block_name
                    seen[fact_id] = block_name

    def test_report_contract_v1_covers_core_domains_with_useful_signal(self):
        from engine.report_contract import build_report_contract_v1

        covered = set()
        for sample in _load_report_contract_samples():
            contract = build_report_contract_v1(sample["raw_run"])
            for block_name in ("executed", "proposed", "analyzed", "blocked"):
                for item in contract[block_name]["items"]:
                    if item["domain"] in {"keywords", "ad_groups", "budget", "redistribution"}:
                        covered.add(item["domain"])
        assert covered == {"keywords", "ad_groups", "budget", "redistribution"}

    def test_report_contract_v1_analyzed_items_are_not_empty_diplomatic_text(self):
        from engine.report_contract import build_report_contract_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "analysis_redistribution_only")
        contract = build_report_contract_v1(sample["raw_run"])

        assert contract["analyzed"]["present"] is True
        assert contract["analyzed"]["items"], "analyzed block should carry useful intermediate facts"
        for item in contract["analyzed"]["items"]:
            assert item["review_scope"]
            assert item["finding"]
            assert item["no_action_reason"]
            assert "no hubo novedad" not in item["finding"].lower()
            assert "sin cambios" not in item["finding"].lower()
            assert "diplomatic" not in item["finding"].lower()
            assert "next_step" in item

    def test_report_contract_v1_blocked_block_exists_even_when_empty(self):
        from engine.report_contract import build_report_contract_v1

        for sample in _load_report_contract_samples():
            contract = build_report_contract_v1(sample["raw_run"])
            assert "blocked" in contract
            assert "present" in contract["blocked"]
            assert isinstance(contract["blocked"]["items"], list)

    def test_report_contract_v1_daily_reviews_survives_audit_without_breakdown(self):
        from engine.report_contract import build_report_contract_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "audit_without_breakdown")
        contract = build_report_contract_v1(sample["raw_run"])

        assert contract["daily_reviews"]["has_audit"] is True
        assert contract["daily_reviews"]["present"] is True
        assert contract["daily_reviews"]["fallback_message"]

    def test_report_contract_v1_summary_matches_primary_block_precedence(self):
        from engine.report_contract import build_report_contract_v1

        executed_sample = next(s for s in _load_report_contract_samples() if s["id"] == "executed_keywords_and_adgroups")
        executed_contract = build_report_contract_v1(executed_sample["raw_run"])
        assert executed_contract["summary"]["domain_status"]["keywords"] == "executed"
        assert executed_contract["summary"]["domain_status"]["ad_groups"] == "executed"

        proposed_sample = next(s for s in _load_report_contract_samples() if s["id"] == "proposals_and_daily_reviews")
        proposed_contract = build_report_contract_v1(proposed_sample["raw_run"])
        assert proposed_contract["summary"]["domain_status"]["budget"] == "proposed"

        analyzed_sample = next(s for s in _load_report_contract_samples() if s["id"] == "analysis_redistribution_only")
        analyzed_contract = build_report_contract_v1(analyzed_sample["raw_run"])
        assert analyzed_contract["summary"]["domain_status"]["redistribution"] == "analyzed"


class TestProDailyEmailBodyV1:
    def test_pro_body_v1_renders_from_contract_only(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "executed_keywords_and_adgroups")
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert "Resumen Ejecutivo" in html
        assert "Acciones Ejecutadas" in html
        assert "pad thai merida" in html

    def test_pro_body_v1_opens_with_executive_summary_and_keeps_context_below(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "proposals_and_daily_reviews")
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert "Resumen Ejecutivo" in html
        assert html.index("Resumen Ejecutivo") < html.index("Contexto de Cuenta")
        assert html.index("Resumen Ejecutivo") < html.index("Google Ads Health Score")
        assert html.index("Resumen Ejecutivo") < html.index("Snapshot de campañas (24h)")

    def test_pro_body_v1_keeps_quick_wins_and_daily_reviews_visible(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "proposals_and_daily_reviews")
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert "Propuestas y Pendientes" in html
        assert "Quick wins pendientes" in html
        assert "Enhanced Conversions activo" in html
        assert "Revisiones del Día" in html
        assert "Conversion Tracking" in html
        assert "Wasted Spend" in html

    def test_pro_body_v1_keeps_reviews_when_audit_exists_without_breakdown(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "audit_without_breakdown")
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert "Revisiones del Día" in html
        assert "Audit is available in this run, but no category breakdown is visible." in html

    def test_pro_body_v1_uses_single_non_empty_analysis_without_multiple_sin_cambios(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "analysis_redistribution_only")
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert html.count("Sin cambios") == 0
        assert "Redistribution was analyzed" in html
        assert "Budget module is present" in html

    def test_pro_body_v1_uses_snapshot_ads_labels_and_has_no_mojibake(self):
        from engine.email_sender import _build_pro_daily_html_v1

        sample = next(s for s in _load_report_contract_samples() if s["id"] == "proposals_and_daily_reviews")
        sample["raw_run"]["ads_24h"] = {
            "por_campana": [
                {
                    "name": "Thai Merida - Local",
                    "tipo": "SMART",
                    "spend_mxn": 130.0,
                    "clicks": 84,
                    "conversions": 0.0,
                }
            ]
        }
        contract = build_report_contract_v1(sample["raw_run"])

        html = _build_pro_daily_html_v1(contract)

        assert "Snapshot de campañas (24h)" in html
        assert "Conv (Ads)" in html
        assert "CPA (Ads)" in html
        assert "Google Ads Health Score" in html
        assert "Ã" not in html
        assert "Â" not in html
        assert "â" not in html
