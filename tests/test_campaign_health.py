"""
Thai Thai Ads Agent — Tests de Fase 6A: Campaign Health (CH1 + CH3)

Pruebas unitarias para detect_campaign_issues().
No realizan llamadas a la API de Google Ads — todo con datos sinteticos.

Casos cubiertos:
  1. CH1: Delivery CPA $92 > $80 critico + 3 conv -> detectar
  2. CH1: Reservaciones CPA $110 < $120 critico + 3 conv -> NO detectar
  3. CH1: Delivery CPA alto pero solo 1 conversion -> NO detectar (min_conv=2)
  4. CH3: Delivery gasto $350, 0 conv, 20 dias activa -> detectar
  5. CH3: Delivery gasto $350, 0 conv, 10 dias activa (< 14) -> NO detectar
  6. CH3: Reservaciones gasto $500, 0 conv, 25 dias (< 30) -> NO detectar
  7. CH3: Reservaciones gasto $500, 0 conv, 31 dias (>= 30) -> detectar

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_campaign_health.py -v
    # o sin pytest:
    py -3.14 tests/test_campaign_health.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.campaign_health import detect_campaign_issues


# ============================================================================
# HELPERS
# ============================================================================

def _camp(
    name="Thai Merida - Delivery",
    campaign_id="999",
    status="ENABLED",
    cost_mxn=300.0,
    conversions=0.0,
    clicks=200,
    impressions=5000,
    days_active=20,
):
    """
    Construye un dict de campana con valores sobreescribibles.
    Usa cost_mxn directo (campaign_health._cost_mxn lo acepta sin cost_micros).
    """
    d = {
        "id": campaign_id,
        "name": name,
        "status": status,
        "cost_mxn": cost_mxn,
        "conversions": conversions,
        "clicks": clicks,
        "impressions": impressions,
    }
    if days_active is not None:
        d["days_active"] = days_active
    return d


# ============================================================================
# CH1
# ============================================================================

def test_ch1_delivery_cpa_critico():
    """
    Delivery: CPA $92 > $80 critico, 3 conversiones. Debe detectar CH1.
    """
    # CPA = cost / conv = $276 / 3 = $92
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Delivery", cost_mxn=276.0, conversions=3.0, days_active=20)
    ])

    ch1 = [r for r in result if r["signal"] == "CH1"]
    assert len(ch1) == 1, f"Se esperaba 1 CH1, se obtuvieron {len(ch1)}"
    assert ch1[0]["campaign_type"] == "delivery"
    assert ch1[0]["cpa_real"] == 92.0
    assert ch1[0]["cpa_critical"] == 80.0
    print(f"PASS CASO 1 - CH1 delivery: CPA $92 > $80 -> detectado")


def test_ch1_reservaciones_bajo_umbral():
    """
    Reservaciones: CPA $110 < $120 critico, 3 conversiones. NO debe detectar CH1.
    """
    # CPA = $330 / 3 = $110 < $120
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Reservaciones", cost_mxn=330.0, conversions=3.0, days_active=35)
    ])

    ch1 = [r for r in result if r["signal"] == "CH1"]
    assert len(ch1) == 0, f"Se esperaba 0 CH1 (CPA bajo umbral), se obtuvieron {len(ch1)}"
    print("PASS CASO 2 - CH1 reservaciones: CPA $110 < $120 -> no detectado")


def test_ch1_insuficientes_conversiones():
    """
    Delivery: CPA altisimo pero solo 1 conversion < min_conversions_for_cpa=2.
    NO debe detectar CH1 (CPA inestable con 1 conversion).
    """
    # CPA = $200 / 1 = $200, muy por encima del critico $80
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Delivery", cost_mxn=200.0, conversions=1.0, days_active=20)
    ])

    ch1 = [r for r in result if r["signal"] == "CH1"]
    assert len(ch1) == 0, f"Se esperaba 0 CH1 (1 conversion < 2 minimas), se obtuvieron {len(ch1)}"
    print("PASS CASO 3 - CH1: 1 conversion < minimo 2 -> no detectado (CPA inestable)")


# ============================================================================
# CH3
# ============================================================================

def test_ch3_delivery_detectado():
    """
    Delivery: $350 gasto, 0 conversiones, 20 dias activa (>= 14). Debe detectar CH3.
    """
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Delivery", cost_mxn=350.0, conversions=0.0, days_active=20)
    ])

    ch3 = [r for r in result if r["signal"] == "CH3"]
    assert len(ch3) == 1, f"Se esperaba 1 CH3, se obtuvieron {len(ch3)}"
    assert ch3[0]["campaign_type"] == "delivery"
    assert ch3[0]["min_spend"] == 300.0
    assert ch3[0]["min_days_active"] == 14
    assert ch3[0]["days_protection_applied"] is True
    print("PASS CASO 4 - CH3 delivery: $350, 0 conv, 20 dias -> detectado")


def test_ch3_delivery_campana_nueva():
    """
    Delivery: $350 gasto, 0 conversiones, 10 dias activa (< 14). NO detectar.
    Proteccion de campana nueva activa.
    """
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Delivery", cost_mxn=350.0, conversions=0.0, days_active=10)
    ])

    ch3 = [r for r in result if r["signal"] == "CH3"]
    assert len(ch3) == 0, f"Se esperaba 0 CH3 (10 dias < 14), se obtuvieron {len(ch3)}"
    print("PASS CASO 5 - CH3 delivery: 10 dias < 14 -> proteccion activa, no detectado")


def test_ch3_reservaciones_proteccion_conservadora():
    """
    Reservaciones: $500 gasto, 0 conversiones, 25 dias (< 30 = proteccion Reservaciones).
    NO detectar aunque supere el umbral de gasto.
    """
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Reservaciones", cost_mxn=500.0, conversions=0.0, days_active=25)
    ])

    ch3 = [r for r in result if r["signal"] == "CH3"]
    assert len(ch3) == 0, f"Se esperaba 0 CH3 (25 dias < 30), se obtuvieron {len(ch3)}"
    print("PASS CASO 6 - CH3 reservaciones: 25 dias < 30 -> proteccion conservadora activa")


def test_ch3_reservaciones_proteccion_superada():
    """
    Reservaciones: $500 gasto, 0 conversiones, 31 dias (>= 30). Debe detectar CH3.
    Verifica umbral de gasto ($450) y proteccion de dias (30) especificos de Reservaciones.
    """
    result = detect_campaign_issues([
        _camp(name="Thai Merida - Reservaciones", cost_mxn=500.0, conversions=0.0, days_active=31)
    ])

    ch3 = [r for r in result if r["signal"] == "CH3"]
    assert len(ch3) == 1, f"Se esperaba 1 CH3, se obtuvieron {len(ch3)}"
    c = ch3[0]
    assert c["campaign_type"] == "reservaciones"
    assert c["min_spend"] == 450.0
    assert c["min_days_active"] == 30
    assert c["days_active"] == 31
    assert c["days_protection_applied"] is True
    print("PASS CASO 7 - CH3 reservaciones: 31 dias >= 30, $500 >= $450 -> detectado")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_ch1_delivery_cpa_critico,
        test_ch1_reservaciones_bajo_umbral,
        test_ch1_insuficientes_conversiones,
        test_ch3_delivery_detectado,
        test_ch3_delivery_campana_nueva,
        test_ch3_reservaciones_proteccion_conservadora,
        test_ch3_reservaciones_proteccion_superada,
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
