"""
Thai Thai Ads Agent — Tests de Fase 3B: Landing Checker

Pruebas unitarias para check_landing_health().
No hacen requests reales — todo con mocks de requests.get / requests.head.

Casos cubiertos:
  1. Todo OK: landing 200, rápida, Gloria Food OK → severity=none
  2. S1_DOWN: 3/3 intentos retornan 502 → S1_DOWN, critical
  3. Retry filtra falso positivo: 1 de 3 intentos falla → sin S1_DOWN
  4. S4_LINK_BROKEN: HEAD retorna 405, GET también falla → S4_LINK_BROKEN, critical
  5. S4 HEAD falla → GET exitoso (fallback funciona) → sin S4_LINK_BROKEN
  6. S2_SLOW: landing responde pero lenta (> warn threshold) → S2_SLOW, warning

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_landing_checker.py -v
    # o sin pytest:
    py -3.14 tests/test_landing_checker.py
"""

import sys
import os
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.landing_checker import check_landing_health, _check_conversion_url


# ============================================================================
# HELPERS
# ============================================================================

DEFAULTS = dict(
    landing_url="https://thaithaimerida.com",
    conversion_url="https://www.restaurantlogin.com/api/fb/_y5_p1_j",
    timeout_warn_s=8.0,
    timeout_critical_s=20.0,
    retry_count=3,
    retry_delay_s=0,      # 0 en tests para no esperar
    ok_status_codes=[200, 301, 302],
    _sleep_fn=lambda _: None,  # no dormir en tests
)


def _mock_get_ok(elapsed_s=0.3):
    """Simula requests.get que retorna 200 rápido."""
    def _get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        # Simular elapsed modificando time.monotonic en el caller no es limpio,
        # así que inyectamos el tiempo directamente vía side_effect del mock
        return resp
    return _get


def _make_get_with_timing(responses_per_call):
    """
    Retorna un mock de requests.get que devuelve respuestas específicas
    con elapsed simulado en cada llamada.

    responses_per_call: lista de (status_code, elapsed_s) en orden de llamada.
    """
    call_index = [0]
    real_monotonic = time.monotonic

    def _get(url, **kwargs):
        idx = call_index[0]
        call_index[0] += 1
        if idx >= len(responses_per_call):
            # Fallback: último elemento
            idx = len(responses_per_call) - 1

        status, elapsed = responses_per_call[idx]

        resp = MagicMock()
        resp.status_code = status

        # Parchamos time.monotonic dentro de check_landing_health para simular elapsed.
        # En lugar de eso, usamos una estrategia más simple: hacemos que el mock
        # de get duerma el tiempo simulado si se necesita medir elapsed.
        # Como _sleep_fn=lambda _: None, time.monotonic diff será ~0ms real.
        # Para S2_SLOW necesitamos inyectar el tiempo simulado de otra forma.
        resp._simulated_elapsed = elapsed

        return resp
    return _get


# ============================================================================
# CASO 1 — Todo OK
# ============================================================================

def test_all_ok():
    """
    Landing retorna 200 con latencia normal, Gloria Food responde OK.
    No debe detectar ninguna señal.
    """
    get_mock = MagicMock(return_value=MagicMock(status_code=200))

    with patch("engine.landing_checker._check_conversion_url", return_value={
        "status_code": 200, "method_used": "HEAD", "ok": True, "error": None
    }):
        result = check_landing_health(
            **{**DEFAULTS, "_requests_get_fn": get_mock}
        )

    assert result["signals"] == [], f"Falso positivo: {result}"
    assert result["severity"] == "none"
    print("PASS CASO 1 - Todo OK, sin señales")


# ============================================================================
# CASO 2 — S1_DOWN: 3/3 intentos retornan 502
# ============================================================================

def test_s1_down_all_attempts_fail():
    """
    Los 3 intentos retornan 502. Debe detectar S1_DOWN con critical.
    """
    get_mock = MagicMock(return_value=MagicMock(status_code=502))
    # Gloria Food: OK (no queremos S4 en este test)
    head_mock = MagicMock(return_value=MagicMock(status_code=200))

    with patch("engine.landing_checker._check_conversion_url", return_value={
        "status_code": 200, "method_used": "HEAD", "ok": True, "error": None
    }):
        result = check_landing_health(
            **{**DEFAULTS, "_requests_get_fn": get_mock}
        )

    assert "S1_DOWN" in result["signals"], f"S1_DOWN no detectado. Resultado: {result}"
    assert result["severity"] == "critical"
    assert result["details"]["s1"]["failed_attempts"] == 3
    print("PASS CASO 2 - S1_DOWN detectado correctamente (3/3 fallos)")


# ============================================================================
# CASO 3 — Retry filtra el falso positivo: 1 de 3 intentos falla
# ============================================================================

def test_s1_not_triggered_with_single_failure():
    """
    Solo 1 de 3 intentos falla (hipo temporal de Netlify).
    S1_DOWN NO debe disparar — el threshold es ≥2 de 3.
    """
    # Alternamos: fallo, OK, OK
    responses = [502, 200, 200]
    call_idx = [0]

    def get_mock(url, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        resp = MagicMock()
        resp.status_code = responses[min(idx, len(responses) - 1)]
        return resp

    with patch("engine.landing_checker._check_conversion_url", return_value={
        "status_code": 200, "method_used": "HEAD", "ok": True, "error": None
    }):
        result = check_landing_health(
            **{**DEFAULTS, "_requests_get_fn": get_mock}
        )

    assert "S1_DOWN" not in result["signals"], (
        f"Falso positivo S1_DOWN con solo 1 fallo. Resultado: {result}"
    )
    print("PASS CASO 3 - Retry filtra falso positivo (1/3 fallos, sin S1)")


# ============================================================================
# CASO 4 — S4_LINK_BROKEN: HEAD 405, GET también falla
# ============================================================================

def test_s4_link_broken_head_and_get_fail():
    """
    HEAD retorna 405, GET retorna 404. Ambos métodos fallan.
    Debe detectar S4_LINK_BROKEN con critical.
    """
    landing_get = MagicMock(return_value=MagicMock(status_code=200))

    # Simulamos _check_conversion_url directamente para controlar HEAD+GET
    def fake_check_url(url, timeout):
        return {
            "status_code": 404,
            "method_used": "GET_fallback",
            "ok": False,
            "error": None,
        }

    with patch("engine.landing_checker._check_conversion_url", side_effect=fake_check_url):
        result = check_landing_health(
            **{**DEFAULTS, "_requests_get_fn": landing_get}
        )

    assert "S4_LINK_BROKEN" in result["signals"], (
        f"S4_LINK_BROKEN no detectado. Resultado: {result}"
    )
    assert result["severity"] == "critical"
    print("PASS CASO 4 - S4_LINK_BROKEN detectado (HEAD 405 + GET 404)")


# ============================================================================
# CASO 5 — S4 HEAD falla pero GET funciona (fallback exitoso)
# ============================================================================

def test_s4_head_fails_get_succeeds():
    """
    HEAD retorna 405 (método no soportado por Gloria Food),
    pero GET retorna 200. El fallback funciona — no debe detectar S4.
    """
    landing_get = MagicMock(return_value=MagicMock(status_code=200))

    def fake_check_url(url, timeout):
        return {
            "status_code": 200,
            "method_used": "GET_fallback",
            "ok": True,
            "error": None,
        }

    with patch("engine.landing_checker._check_conversion_url", side_effect=fake_check_url):
        result = check_landing_health(
            **{**DEFAULTS, "_requests_get_fn": landing_get}
        )

    assert "S4_LINK_BROKEN" not in result["signals"], (
        f"Falso positivo S4 con GET exitoso. Resultado: {result}"
    )
    print("PASS CASO 5 - Fallback GET funciona, sin S4_LINK_BROKEN")


# ============================================================================
# CASO 6 — S2_SLOW: landing responde pero lenta (> warn threshold)
# ============================================================================

def test_s2_slow_warning():
    """
    Landing responde con 200 pero el tiempo de respuesta supera el umbral
    de warning (8s). Debe detectar S2_SLOW con severity='warning'.
    """
    # Para simular tiempo lento sin dormir de verdad, parcheamos time.monotonic
    # para que reporte un elapsed alto en el contexto de check_landing_health.
    tick = [0.0]

    def fake_monotonic():
        val = tick[0]
        tick[0] += 5.0  # cada llamada avanza 5s → elapsed por llamada = 5s
        return val

    landing_get = MagicMock(return_value=MagicMock(status_code=200))

    with patch("engine.landing_checker.time") as mock_time:
        mock_time.monotonic = fake_monotonic
        mock_time.sleep = lambda _: None

        with patch("engine.landing_checker._check_conversion_url", return_value={
            "status_code": 200, "method_used": "HEAD", "ok": True, "error": None
        }):
            result = check_landing_health(
                **{**DEFAULTS,
                   "_requests_get_fn": landing_get,
                   "_sleep_fn": lambda _: None,
                   "timeout_warn_s": 3.0,
                   "timeout_critical_s": 20.0}
            )

    assert "S2_SLOW" in result["signals"], f"S2_SLOW no detectado. Resultado: {result}"
    # S2 solo sin S1/S4 → warning
    assert result["severity"] == "warning", (
        f"Severidad incorrecta: {result['severity']} (esperado: warning)"
    )
    print("PASS CASO 6 - S2_SLOW warning detectado correctamente")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_all_ok,
        test_s1_down_all_attempts_fail,
        test_s1_not_triggered_with_single_failure,
        test_s4_link_broken_head_and_get_fail,
        test_s4_head_fails_get_succeeds,
        test_s2_slow_warning,
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
