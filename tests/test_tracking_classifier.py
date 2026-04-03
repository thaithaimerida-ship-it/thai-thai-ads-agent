"""
Thai Thai Ads Agent — Tests de Fase 3A: Detección de Tracking Crítico

Pruebas unitarias para detect_tracking_signals().
No requieren conexión a Google Ads ni modifican ninguna conversion action.

Casos cubiertos:
  1. Señal A: caída de CVR en 2+ campañas con volumen suficiente
  2. Señal B: 0 conversiones con clicks en 2+ campañas
  3. Señal C: 0 conversiones globales con volumen mínimo suficiente
  4. Sin señal — solo 1 campaña afectada (no global, no dispara)
  5. Sin señal — clicks insuficientes en todas las campañas
  6. Sin señal — Señal C bloqueada por volumen insuficiente

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_tracking_classifier.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.risk_classifier import detect_tracking_signals


# ============================================================================
# HELPERS
# ============================================================================

def _make_campaign(id: str, name: str, clicks: int, conversions: int,
                   cost_mxn: float = 0.0) -> dict:
    """Construye un dict de campaña con la estructura que retorna ads_client."""
    return {
        "id": id,
        "name": name,
        "clicks": clicks,
        "conversions": conversions,
        "cost_mxn": cost_mxn,
        "cvr": (conversions / clicks) if clicks > 0 else 0.0,
    }


# ============================================================================
# CASO 1 — Señal A: caída de CVR ≥70 % en 2 campañas
# ============================================================================

def test_signal_a_two_campaigns_cvr_drop():
    """
    Dos campañas con clicks suficientes y CVR que cayó >70%.
    Debe detectar Señal A con severidad 'warning'.
    """
    # Semana anterior: CVR 10 % en ambas campañas
    prev_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=50, conversions=5),   # cvr=0.10
        _make_campaign("2", "Thai - Reservaciones", clicks=40, conversions=4),   # cvr=0.10
    ]
    # Semana actual: CVR cayó a 1 % (caída del 90 %)
    current_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=50, conversions=0),   # cvr=0.0
        _make_campaign("2", "Thai - Reservaciones", clicks=40, conversions=0),   # cvr=0.0
    ]

    result = detect_tracking_signals(current_week, prev_week)

    assert "A" in result["signals"], f"Señal A no detectada. Resultado: {result}"
    assert result["severity"] in ("warning", "critical")
    assert len(result["signal_a_affected"]) == 2
    # Lenguaje tentativo en reason
    assert "posible" in result["reason"].lower() or "señal compatible" in result["reason"].lower()
    print("PASS CASO 1 - Senal A detectada correctamente")


# ============================================================================
# CASO 2 — Señal B: 0 conversiones con clicks en 2+ campañas
# ============================================================================

def test_signal_b_two_campaigns_zero_conversions():
    """
    Dos campañas con ≥10 clicks y 0 conversiones (sin semana anterior para comparar CVR).
    Debe detectar Señal B.
    """
    prev_week = []  # sin datos históricos — no hay referencia de CVR
    current_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=25, conversions=0),
        _make_campaign("2", "Thai - Reservaciones", clicks=15, conversions=0),
        _make_campaign("3", "Thai - Local",         clicks=30, conversions=0),
    ]

    result = detect_tracking_signals(current_week, prev_week)

    assert "B" in result["signals"], f"Señal B no detectada. Resultado: {result}"
    assert len(result["signal_b_affected"]) >= 2
    assert "requiere verificación" in result["reason"].lower()
    print("✅ CASO 2 — Señal B detectada correctamente")


# ============================================================================
# CASO 3 — Señal C: 0 conversiones globales con volumen suficiente
# ============================================================================

def test_signal_c_global_zero_conversions_sufficient_volume():
    """
    Cuenta con 1 sola campaña activa pero con ≥20 clicks totales y 0 conversiones.
    La Señal C debe disparar porque la condición de volumen se cumple a nivel cuenta.
    (Cubre el caso en que solo hay 1 campaña activa con tráfico decente.)
    """
    prev_week = [
        _make_campaign("1", "Thai - Local", clicks=30, conversions=3),
    ]
    current_week = [
        _make_campaign("1", "Thai - Local", clicks=25, conversions=0),
    ]

    result = detect_tracking_signals(current_week, prev_week)

    # Con 25 clicks totales y 0 conversiones → Señal C debe disparar
    assert "C" in result["signals"], f"Señal C no detectada. Resultado: {result}"
    assert result["severity"] == "critical"  # C sola → critical
    assert "0 conversiones" in result["reason"].lower()
    print("✅ CASO 3 — Señal C detectada correctamente (volumen suficiente)")


# ============================================================================
# CASO 4 — Sin señal: solo 1 campaña afectada (Señal B no alcanza mínimo global)
# ============================================================================

def test_no_signal_only_one_campaign_affected():
    """
    Solo 1 campaña muestra 0 conversiones con clicks suficientes.
    Señal B requiere mínimo 2 campañas para ser global — no debe disparar.
    """
    prev_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=50, conversions=5),
        _make_campaign("2", "Thai - Reservaciones", clicks=40, conversions=4),
    ]
    current_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=50, conversions=0),  # afectada
        _make_campaign("2", "Thai - Reservaciones", clicks=40, conversions=3),  # sana
    ]

    result = detect_tracking_signals(current_week, prev_week)

    # B no dispara (solo 1 campaña afectada)
    assert "B" not in result["signals"], f"Falso positivo Señal B. Resultado: {result}"
    # Tampoco C porque hay conversiones en Reservaciones (total > 0)
    assert "C" not in result["signals"], f"Falso positivo Señal C. Resultado: {result}"
    assert result["severity"] == "none" or (
        result["signals"] == [] or "A" not in result["signals"]
    )
    print("✅ CASO 4 — Sin señal global (solo 1 campaña afectada)")


# ============================================================================
# CASO 5 — Sin señal: clicks insuficientes en todas las campañas
# ============================================================================

def test_no_signal_insufficient_clicks_all_campaigns():
    """
    Todas las campañas tienen < TRACKING_MIN_CLICKS_FOR_SIGNAL (10) clicks.
    No hay señales A ni B porque no hay volumen suficiente.
    """
    prev_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=50, conversions=5),
        _make_campaign("2", "Thai - Reservaciones", clicks=40, conversions=4),
    ]
    # Semana de muy poco tráfico — probablemente feriado o presupuesto agotado
    current_week = [
        _make_campaign("1", "Thai - Delivery",      clicks=3,  conversions=0),
        _make_campaign("2", "Thai - Reservaciones", clicks=5,  conversions=0),
    ]

    result = detect_tracking_signals(current_week, prev_week)

    # Sin volumen suficiente — no se puede distinguir falla de tráfico bajo
    assert result["signals"] == [] or "A" not in result["signals"]
    assert result["signals"] == [] or "B" not in result["signals"]
    # C tampoco: total_clicks = 8 < TRACKING_MIN_CLICKS_SIGNAL_C (20)
    assert "C" not in result["signals"], f"Falso positivo Señal C con clicks bajos. Resultado: {result}"
    print("✅ CASO 5 — Sin señal (clicks insuficientes en toda la cuenta)")


# ============================================================================
# CASO 6 — Sin señal C: volumen total insuficiente
# ============================================================================

def test_no_signal_c_insufficient_total_clicks():
    """
    0 conversiones totales pero total_clicks < TRACKING_MIN_CLICKS_SIGNAL_C (20).
    La Señal C no debe disparar — no se puede distinguir de semana sin tráfico.
    """
    prev_week = [
        _make_campaign("1", "Thai - Local", clicks=20, conversions=2),
    ]
    # Solo 12 clicks en toda la cuenta esta semana
    current_week = [
        _make_campaign("1", "Thai - Local", clicks=12, conversions=0),
    ]

    result = detect_tracking_signals(current_week, prev_week)

    # C no debe disparar — volumen insuficiente (12 < 20)
    assert "C" not in result["signals"], (
        f"Falso positivo: Señal C disparó con solo {result['account_metrics']['total_clicks']} clicks. "
        f"Resultado: {result}"
    )
    print("✅ CASO 6 — Señal C bloqueada por volumen insuficiente")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_signal_a_two_campaigns_cvr_drop,
        test_signal_b_two_campaigns_zero_conversions,
        test_signal_c_global_zero_conversions_sufficient_volume,
        test_no_signal_only_one_campaign_affected,
        test_no_signal_insufficient_clicks_all_campaigns,
        test_no_signal_c_insufficient_total_clicks,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"❌ FALLO en {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 ERROR en {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'─' * 40}")
    print(f"Resultados: {passed}/{len(tests)} tests pasaron")
    if failed:
        print(f"⚠️  {failed} test(s) fallaron")
        sys.exit(1)
    else:
        print("✅ Todos los tests pasaron")
