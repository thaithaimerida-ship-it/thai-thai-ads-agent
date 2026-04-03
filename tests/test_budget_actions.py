"""
Thai Thai Ads Agent — Tests de Fase 6B: Budget Actions (BA1)

Pruebas unitarias para detect_budget_opportunities().
No realizan llamadas a la API de Google Ads — todo con datos sinteticos.

Casos cubiertos:
  1. BA1 detectado: Delivery CPA $100 > $80 critico, 3 conv, $300 gasto -> detectar
  2. BA1 NO detectado: CPA $70 < $80 critico -> NO detectar
  3. BA1 NO detectado: 1 conversion < min_conversions=2 -> NO detectar
  4. BA1 NO detectado: gasto $150 < min_spend_window=200 (delivery) -> NO detectar
  5. BA1 NO detectado: campana nueva 10 dias < 14 dias (delivery) -> NO detectar
  6. BA1 detectado reservaciones: CPA $150 > $120 critico, 2 conv, $400, 35 dias
  7. BA1 verificar presupuesto sugerido: calcular que la formula es correcta

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_budget_actions.py -v
    # o sin pytest:
    py -3.14 tests/test_budget_actions.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.budget_actions import detect_budget_opportunities, _suggest_budget


# ============================================================================
# HELPERS
# ============================================================================

def _camp(
    name="Thai Merida - Delivery",
    campaign_id="999",
    status="ENABLED",
    cost_mxn=300.0,
    conversions=3.0,
    clicks=200,
    impressions=5000,
    days_active=20,
    daily_budget_mxn=150.0,
):
    """
    Construye un dict de campana con valores sobreescribibles.
    Usa cost_mxn directo (budget_actions._cost_mxn lo acepta sin cost_micros).
    """
    d = {
        "id": campaign_id,
        "name": name,
        "status": status,
        "cost_mxn": cost_mxn,
        "conversions": conversions,
        "clicks": clicks,
        "impressions": impressions,
        "daily_budget_mxn": daily_budget_mxn,
    }
    if days_active is not None:
        d["days_active"] = days_active
    return d


# ============================================================================
# BA1
# ============================================================================

def test_ba1_delivery_detectado():
    """
    Delivery: CPA $100 > $80 critico, 3 conversiones, $300 gasto >= $200 min.
    Debe detectar BA1 con presupuesto sugerido calculado.
    CPA = $300 / 3 = $100
    """
    result = detect_budget_opportunities([
        _camp(
            name="Thai Merida - Delivery",
            cost_mxn=300.0,
            conversions=3.0,
            days_active=20,
            daily_budget_mxn=150.0,
        )
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 1, f"Se esperaba 1 BA1, se obtuvieron {len(ba1)}"
    b = ba1[0]
    assert b["campaign_type"] == "delivery"
    assert b["cpa_real"] == 100.0
    assert b["cpa_critical"] == 80.0
    assert b["daily_budget_mxn"] == 150.0
    assert b["suggested_daily_budget"] is not None
    assert b["suggested_daily_budget"] > 0
    # Piso: 30% de 150 = 45. Formula: 150 * (45 / 100) = 67.5
    assert b["suggested_daily_budget"] == 67.5
    assert b["reduction_pct"] == 55.0
    print(f"PASS CASO 1 - BA1 delivery: CPA $100 > $80 -> detectado, sugerido ${b['suggested_daily_budget']}/dia")


def test_ba1_cpa_bajo_umbral():
    """
    Delivery: CPA $70 < $80 critico. NO debe detectar BA1.
    CPA = $210 / 3 = $70
    """
    result = detect_budget_opportunities([
        _camp(name="Thai Merida - Delivery", cost_mxn=210.0, conversions=3.0, days_active=20)
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 0, f"Se esperaba 0 BA1 (CPA bajo umbral), se obtuvieron {len(ba1)}"
    print("PASS CASO 2 - BA1: CPA $70 < $80 critico -> no detectado")


def test_ba1_insuficientes_conversiones():
    """
    Delivery: CPA $200 (alto) pero solo 1 conversion < min_conversions=2.
    NO debe detectar BA1 (CPA inestable con 1 conversion).
    """
    result = detect_budget_opportunities([
        _camp(name="Thai Merida - Delivery", cost_mxn=200.0, conversions=1.0, days_active=20)
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 0, f"Se esperaba 0 BA1 (1 conversion < 2 minimas), se obtuvieron {len(ba1)}"
    print("PASS CASO 3 - BA1: 1 conversion < minimo 2 -> no detectado (CPA inestable)")


def test_ba1_gasto_insuficiente():
    """
    Delivery: CPA $100 > $80 critico, 3 conv, pero gasto $150 < min_spend_window=200.
    NO debe detectar BA1 (evidencia de gasto insuficiente).
    CPA = $150 / 3 = $50... en realidad eso es menor que 80, asi que ajustamos:
    CPA = $250 / 2 = $125... pero gasto es $100 < $200
    Usamos cost_mxn=$100 con conversiones=1 -> 1 conv falla min_conv=2
    Mejor: cost_mxn=100 con conversiones=2 -> CPA=$50 < $80 critico -> falla CPA check
    Para testear solo la guarda de gasto: necesitamos CPA > 80 Y gasto < 200.
    cost_mxn=150, conversions=1.5 -> falla min_conv (1.5 < 2)
    cost_mxn=150, conversions=2 -> CPA=$75 < $80 critico -> falla CPA check
    Usar delivery con cost=190, conv=2 -> CPA=$95>$80, gasto $190 < $200 min_spend
    """
    result = detect_budget_opportunities([
        _camp(
            name="Thai Merida - Delivery",
            cost_mxn=190.0,      # < min_spend_window=200
            conversions=2.0,     # CPA = 95 > 80 critico
            days_active=20,
        )
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 0, f"Se esperaba 0 BA1 (gasto $190 < $200 min), se obtuvieron {len(ba1)}"
    print("PASS CASO 4 - BA1 delivery: gasto $190 < $200 min_spend_window -> no detectado")


def test_ba1_campana_nueva():
    """
    Delivery: CPA $100 > $80 critico, pero solo 10 dias activa (< 14 min).
    NO detectar. Proteccion de campana nueva activa.
    """
    result = detect_budget_opportunities([
        _camp(
            name="Thai Merida - Delivery",
            cost_mxn=300.0,
            conversions=3.0,
            days_active=10,      # < 14 min_days_active
        )
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 0, f"Se esperaba 0 BA1 (10 dias < 14), se obtuvieron {len(ba1)}"
    print("PASS CASO 5 - BA1 delivery: 10 dias < 14 -> proteccion campana nueva activa")


def test_ba1_reservaciones_detectado():
    """
    Reservaciones: CPA $200 > $120 critico, 2 conv, $400 gasto >= $350 min, 35 dias >= 30.
    Debe detectar BA1 con umbrales especificos de reservaciones.
    CPA = $400 / 2 = $200
    """
    result = detect_budget_opportunities([
        _camp(
            name="Thai Merida - Reservaciones",
            cost_mxn=400.0,
            conversions=2.0,
            days_active=35,
            daily_budget_mxn=200.0,
        )
    ])

    ba1 = [r for r in result if r["signal"] == "BA1"]
    assert len(ba1) == 1, f"Se esperaba 1 BA1, se obtuvieron {len(ba1)}"
    b = ba1[0]
    assert b["campaign_type"] == "reservaciones"
    assert b["cpa_real"] == 200.0
    assert b["cpa_critical"] == 120.0
    assert b["cpa_max"] == 85.0
    assert b["min_spend_window"] == 350.0
    assert b["min_days_active"] == 30
    print(f"PASS CASO 6 - BA1 reservaciones: CPA $200 > $120, 35 dias >= 30 -> detectado")


def test_ba1_presupuesto_sugerido_formula():
    """
    Verifica que la formula de presupuesto sugerido sea correcta.
    Delivery: presupuesto actual $200, CPA real $120, CPA max $45.
    suggested = 200 * (45 / 120) = 75.0
    Piso 30%: 200 * 0.30 = 60 < 75 -> aplica formula, no el piso.
    """
    # Verificar la funcion _suggest_budget directamente
    result = _suggest_budget(
        current_budget=200.0,
        cpa_real=120.0,
        cpa_max=45.0,
        floor_pct=0.30,
    )
    expected = round(200.0 * (45.0 / 120.0), 2)  # 75.0
    assert result == expected, f"Se esperaba {expected}, se obtuvo {result}"

    # Verificar que el piso actua cuando la formula baja demasiado
    result_floor = _suggest_budget(
        current_budget=200.0,
        cpa_real=500.0,   # CPA muy alto -> formula daria muy poco
        cpa_max=45.0,
        floor_pct=0.30,
    )
    floor = 200.0 * 0.30  # 60.0
    formula = 200.0 * (45.0 / 500.0)  # 18.0
    assert result_floor == floor, (
        f"El piso deberia ser {floor} (formula {formula} < piso), se obtuvo {result_floor}"
    )
    print(f"PASS CASO 7 - formula presupuesto: $200*({45}/{120})={expected}, piso=${floor}")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_ba1_delivery_detectado,
        test_ba1_cpa_bajo_umbral,
        test_ba1_insuficientes_conversiones,
        test_ba1_gasto_insuficiente,
        test_ba1_campana_nueva,
        test_ba1_reservaciones_detectado,
        test_ba1_presupuesto_sugerido_formula,
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

    print(f"\n{'-' * 40}")
    print(f"Resultados: {passed}/{len(tests)} tests pasaron")
    if failed:
        print(f"ATENCION: {failed} test(s) fallaron")
        sys.exit(1)
    else:
        print("Todos los tests pasaron")
