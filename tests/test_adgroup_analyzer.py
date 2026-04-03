"""
Thai Thai Ads Agent — Tests de Fase 4: Ad Group Analyzer

Pruebas unitarias para detect_adgroup_issues().
No realizan llamadas a la API de Google Ads — todo con datos sintéticos.

Casos cubiertos:
  1. AG1 detectado: gasto $187, clicks 42, conv 0 → candidato
  2. Gasto insuficiente ($80): debajo de umbral → sin señal
  3. Clicks insuficientes (15 < 25): debajo de umbral → sin señal
  4. Ad group PAUSED → ignorado aunque cumpla condiciones numéricas
  5. Campaña en aprendizaje (9 días): protegida → sin señal
  6. Dos candidatos → ordenados por gasto, máximo 2 retornados
  7. Tiene conversiones (conv=2) → no es AG1 → sin señal

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_adgroup_analyzer.py -v
    # o sin pytest:
    py -3.14 tests/test_adgroup_analyzer.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.adgroup_analyzer import detect_adgroup_issues


# ============================================================================
# HELPERS
# ============================================================================

def _ag(
    adgroup_id="100",
    adgroup_name="Grupo Test",
    campaign_id="999",
    campaign_name="Thai Merida - Delivery",
    status="ENABLED",
    cost_mxn=187.40,
    clicks=42,
    conversions=0,
    impressions=520,
    campaign_days_active=None,
):
    """Construye un dict de ad group con valores por defecto sobrescribibles."""
    d = {
        "adgroup_id": adgroup_id,
        "adgroup_name": adgroup_name,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "status": status,
        "cost_mxn": cost_mxn,
        "clicks": clicks,
        "conversions": conversions,
        "impressions": impressions,
    }
    if campaign_days_active is not None:
        d["campaign_days_active"] = campaign_days_active
    return d


# ============================================================================
# CASO 1 — AG1 detectado correctamente
# ============================================================================

def test_ag1_detected():
    """
    Gasto $187, clicks 42, conv 0, status ENABLED.
    Debe detectar AG1 y retornar el candidato.
    """
    result = detect_adgroup_issues([_ag()])

    assert len(result) == 1, f"Se esperaba 1 candidato, se obtuvieron {len(result)}"
    assert result[0]["signal"] == "AG1"
    assert result[0]["adgroup_id"] == "100"
    assert result[0]["cost_mxn"] == 187.40
    assert result[0]["conversions"] == 0
    print("PASS CASO 1 - AG1 detectado (gasto $187, clicks 42, conv 0)")


# ============================================================================
# CASO 2 — Gasto insuficiente: debajo del umbral
# ============================================================================

def test_no_signal_insufficient_spend():
    """
    Gasto $80 < $120 (umbral). No debe detectar AG1.
    """
    result = detect_adgroup_issues([_ag(cost_mxn=80.0, clicks=35)])

    assert result == [], f"Se esperaba lista vacía, se obtuvo: {result}"
    print("PASS CASO 2 - Sin señal: gasto $80 < umbral $120")


# ============================================================================
# CASO 3 — Clicks insuficientes: debajo del umbral
# ============================================================================

def test_no_signal_insufficient_clicks():
    """
    Gasto $150 pero solo 15 clicks < 25 (umbral). No debe detectar AG1.
    """
    result = detect_adgroup_issues([_ag(cost_mxn=150.0, clicks=15)])

    assert result == [], f"Se esperaba lista vacía, se obtuvo: {result}"
    print("PASS CASO 3 - Sin señal: 15 clicks < umbral 25")


# ============================================================================
# CASO 4 — Ad group PAUSED: debe ignorarse
# ============================================================================

def test_paused_adgroup_ignored():
    """
    Ad group con status PAUSED, aunque cumpla todas las condiciones numéricas.
    El agente no debe proponer pausar algo que ya está pausado.
    """
    result = detect_adgroup_issues([_ag(status="PAUSED")])

    assert result == [], f"Se esperaba lista vacía para grupo PAUSED, se obtuvo: {result}"
    print("PASS CASO 4 - Ad group PAUSED ignorado correctamente")


# ============================================================================
# CASO 5 — Campaña en aprendizaje: protección activa
# ============================================================================

def test_learning_phase_protection():
    """
    campaign_days_active=9 < 14 (CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION).
    El agente debe omitir el grupo por protección de aprendizaje temprano.
    """
    result = detect_adgroup_issues([_ag(campaign_days_active=9)])

    assert result == [], f"Se esperaba lista vacía para campaña en aprendizaje, se obtuvo: {result}"
    print("PASS CASO 5 - Proteccion de aprendizaje: campaign_days_active=9 < 14")


# ============================================================================
# CASO 6 — Múltiples candidatos: ordenados por gasto, máximo 2
# ============================================================================

def test_multiple_candidates_sorted_and_capped():
    """
    Tres candidatos con gasto $300, $187, $150.
    Deben retornarse los dos de mayor gasto, en ese orden.
    El tercer candidato ($150) queda fuera por el límite de 2 por ciclo.
    """
    adgroups = [
        _ag(adgroup_id="101", adgroup_name="Grupo B", cost_mxn=187.0, clicks=30),
        _ag(adgroup_id="102", adgroup_name="Grupo C", cost_mxn=150.0, clicks=28),
        _ag(adgroup_id="103", adgroup_name="Grupo A", cost_mxn=300.0, clicks=55),
    ]

    result = detect_adgroup_issues(adgroups)

    assert len(result) == 2, f"Se esperaban 2 candidatos (cap), se obtuvieron {len(result)}"
    assert result[0]["adgroup_id"] == "103", "El primero debe ser el de mayor gasto ($300)"
    assert result[1]["adgroup_id"] == "101", "El segundo debe ser el de $187"
    print("PASS CASO 6 - Multiples candidatos: ordenados por gasto, cap=2")


# ============================================================================
# CASO 7 — Tiene conversiones: no es AG1
# ============================================================================

def test_no_signal_has_conversions():
    """
    Ad group con 2 conversiones — no es candidato AG1.
    AG1 requiere conversiones == 0.
    """
    result = detect_adgroup_issues([_ag(cost_mxn=200.0, clicks=50, conversions=2)])

    assert result == [], f"Se esperaba lista vacía con conversiones > 0, se obtuvo: {result}"
    print("PASS CASO 7 - Sin señal AG1: tiene 2 conversiones")


# ============================================================================
# CASOS POR TIPO DE CAMPAÑA (Fase 4 ajuste — thresholds por tipo)
# ============================================================================

# ── CASO 8 — Delivery: umbral propio (ag1_min_spend=$100, ag1_min_clicks=20) ─

def test_delivery_ag1_own_thresholds():
    """
    Delivery: gasto $102 > $100, clicks 21 > 20, conv 0.
    Debe detectar AG1 usando thresholds propios de delivery (no el global de $120/$25).
    Verifica que el candidato retorna campaign_type='delivery' y los thresholds correctos.
    """
    result = detect_adgroup_issues([
        _ag(campaign_name="Thai Merida - Delivery", cost_mxn=102.0, clicks=21)
    ])

    assert len(result) == 1, f"Se esperaba 1 candidato, se obtuvieron {len(result)}"
    assert result[0]["signal"] == "AG1"
    assert result[0]["campaign_type"] == "delivery"
    assert result[0]["min_spend_required"] == 100.0
    assert result[0]["min_clicks_required"] == 20
    assert result[0]["min_days_protection"] == 14
    assert result[0]["campaign_days_active"] is None
    assert result[0]["days_protection_applied"] is False
    assert "$102.00 MXN (req. $100.00)" in result[0]["reason"]
    assert "clicks 21 (req. 20)" in result[0]["reason"]
    assert "[delivery]" in result[0]["reason"]
    print("PASS CASO 8 - Delivery AG1: thresholds propios ($100/$20) aplicados correctamente")


# ── CASO 9 — Delivery: gasto insuficiente con nuevo umbral ────────────────────

def test_delivery_spend_below_own_threshold():
    """
    Delivery: gasto $95 < $100 (umbral delivery). Clicks suficientes.
    No debe detectar AG1 — el umbral de delivery ($100) es menor que el global ($120)
    pero sigue siendo mayor que $95.
    """
    result = detect_adgroup_issues([
        _ag(campaign_name="Thai Merida - Delivery", cost_mxn=95.0, clicks=21)
    ])

    assert result == [], f"Se esperaba lista vacia, se obtuvo: {result}"
    print("PASS CASO 9 - Delivery: gasto $95 < umbral $100 -> sin senal")


# ── CASO 10 — Reservaciones: gasto insuficiente (umbral $150) ─────────────────

def test_reservaciones_spend_below_threshold():
    """
    Reservaciones: gasto $140 < $150 (umbral conservador). Clicks suficientes.
    No debe detectar AG1 aunque superaria el umbral global de $120.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Reservaciones",
            cost_mxn=140.0,
            clicks=36,
        )
    ])

    assert result == [], f"Se esperaba lista vacia, se obtuvo: {result}"
    print("PASS CASO 10 - Reservaciones: gasto $140 < umbral $150 -> sin senal")


# ── CASO 11 — Reservaciones: clicks insuficientes (umbral 35) ─────────────────

def test_reservaciones_clicks_below_threshold():
    """
    Reservaciones: gasto $160 > $150, pero solo 30 clicks < 35.
    No debe detectar AG1 aunque superaria el umbral global de 25 clicks.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Reservaciones",
            cost_mxn=160.0,
            clicks=30,
        )
    ])

    assert result == [], f"Se esperaba lista vacia, se obtuvo: {result}"
    print("PASS CASO 11 - Reservaciones: 30 clicks < umbral 35 -> sin senal")


# ── CASO 12 — Reservaciones: ambos umbrales superados, evidencia completa ─────

def test_reservaciones_ag1_full_evidence():
    """
    Reservaciones: gasto $160 > $150, clicks 36 > 35, conv 0.
    Debe detectar AG1 con campaign_type='reservaciones' y thresholds correctos.
    Verifica todos los campos de evidencia del ajuste del usuario.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Reservaciones",
            cost_mxn=160.0,
            clicks=36,
        )
    ])

    assert len(result) == 1, f"Se esperaba 1 candidato, se obtuvieron {len(result)}"
    c = result[0]
    assert c["signal"] == "AG1"
    assert c["campaign_type"] == "reservaciones"
    assert c["min_spend_required"] == 150.0
    assert c["min_clicks_required"] == 35
    assert c["min_days_protection"] == 30
    assert c["campaign_days_active"] is None, "Sin days_active debe ser None"
    assert c["days_protection_applied"] is False, "Sin dato de dias, proteccion no se aplico"
    assert "[reservaciones]" in c["reason"]
    assert "$160.00 MXN (req. $150.00)" in c["reason"]
    assert "clicks 36 (req. 35)" in c["reason"]
    assert "no disponible" in c["reason"]
    print("PASS CASO 12 - Reservaciones AG1: ambos umbrales superados, evidencia completa")


# ── CASO 13 — Reservaciones: proteccion nueva campana activa (25 dias < 30) ───

def test_reservaciones_new_campaign_protection():
    """
    Reservaciones: campana activa 25 dias < 30 (proteccion especifica del tipo).
    Aunque cumpla gasto y clicks, debe omitirse.
    days_protection_applied no aplica aqui porque el ad group no llega al candidato.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Reservaciones",
            cost_mxn=160.0,
            clicks=36,
            campaign_days_active=25,
        )
    ])

    assert result == [], f"Se esperaba lista vacia (25 dias < 30), se obtuvo: {result}"
    print("PASS CASO 13 - Reservaciones: 25 dias activa < 30 -> proteccion nueva campana")


# ── CASO 14 — Reservaciones: proteccion superada (31 dias >= 30) ──────────────

def test_reservaciones_protection_passed():
    """
    Reservaciones: campana activa 31 dias >= 30. Gasto y clicks suficientes.
    Debe detectar AG1 y marcar days_protection_applied=True con los dias correctos.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Reservaciones",
            cost_mxn=160.0,
            clicks=36,
            campaign_days_active=31,
        )
    ])

    assert len(result) == 1, f"Se esperaba 1 candidato, se obtuvieron {len(result)}"
    c = result[0]
    assert c["signal"] == "AG1"
    assert c["campaign_type"] == "reservaciones"
    assert c["campaign_days_active"] == 31
    assert c["days_protection_applied"] is True
    assert c["min_days_protection"] == 30
    assert "31 dias (req. 30)" in c["reason"] or "31" in c["reason"]
    print("PASS CASO 14 - Reservaciones: 31 dias >= 30 -> proteccion superada, AG1 detectado")


# ── CASO 15 — Local: comportamiento sin cambio respecto al global ──────────────

def test_local_unchanged_behavior():
    """
    Local: gasto $120 == umbral local, clicks 25 == umbral local, conv 0.
    Debe detectar AG1 — comportamiento identico al global anterior.
    Verifica que campaign_type='local' y thresholds coinciden con los globales.
    """
    result = detect_adgroup_issues([
        _ag(
            campaign_name="Thai Merida - Local",
            cost_mxn=120.0,
            clicks=25,
        )
    ])

    assert len(result) == 1, f"Se esperaba 1 candidato, se obtuvieron {len(result)}"
    c = result[0]
    assert c["signal"] == "AG1"
    assert c["campaign_type"] == "local"
    assert c["min_spend_required"] == 120.0
    assert c["min_clicks_required"] == 25
    assert c["min_days_protection"] == 14
    print("PASS CASO 15 - Local: comportamiento sin cambio (identico al global)")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_ag1_detected,
        test_no_signal_insufficient_spend,
        test_no_signal_insufficient_clicks,
        test_paused_adgroup_ignored,
        test_learning_phase_protection,
        test_multiple_candidates_sorted_and_capped,
        test_no_signal_has_conversions,
        # Por tipo de campana
        test_delivery_ag1_own_thresholds,
        test_delivery_spend_below_own_threshold,
        test_reservaciones_spend_below_threshold,
        test_reservaciones_clicks_below_threshold,
        test_reservaciones_ag1_full_evidence,
        test_reservaciones_new_campaign_protection,
        test_reservaciones_protection_passed,
        test_local_unchanged_behavior,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"FALLO en {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"ERROR en {test_fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'─' * 40}")
    print(f"Resultados: {passed}/{len(tests)} tests pasaron")
    if failed:
        print(f"ATENCION: {failed} test(s) fallaron")
        sys.exit(1)
    else:
        print("Todos los tests pasaron")
