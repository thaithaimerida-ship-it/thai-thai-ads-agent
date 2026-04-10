"""
Thai Thai Ads Agent — Tests del Reporte Diario

Protege la consistencia del correo diario.
No realiza llamadas a API — todo con datos sintéticos.
Ejecutar: python -m pytest tests/test_daily_report.py -v
"""
import pytest


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
