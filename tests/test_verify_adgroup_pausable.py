"""
Thai Thai Ads Agent — Tests de Fase 4B: verify_adgroup_still_pausable()

Pruebas unitarias con API de Google Ads mockeada.
No realizan llamadas reales — todo con objetos sintéticos.

Casos cubiertos:
  1. Ambas guardas pasan → ok=True
  2. G1: ad group no encontrado → ok=False, guard='G1'
  3. G1: ad group en estado PAUSED → ok=False, guard='G1'
  4. G2: único ENABLED en campaña → ok=False, guard='G2'
  5. G2: dos ENABLED → ok=True (G2 pasa con 2+)
  6. GoogleAPIError → ok=False, guard='G1'

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_verify_adgroup_pausable.py -v
    # o sin pytest:
    py -3.14 tests/test_verify_adgroup_pausable.py
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.ads_client import verify_adgroup_still_pausable


# ============================================================================
# HELPERS
# ============================================================================

def _make_row(ag_id: int, status_name: str):
    """Construye un mock de fila de respuesta de Google Ads."""
    row = MagicMock()
    row.ad_group.id = ag_id
    row.ad_group.status.name = status_name
    return row


def _make_client(q1_rows: list, q2_rows: list, raise_api_error: bool = False):
    """
    Construye un mock de GoogleAdsClient.

    q1_rows: filas para la consulta del ad group específico (G1)
    q2_rows: filas para la consulta de grupos ENABLED en campaña (G2)
    raise_api_error: si True, lanza GoogleAPIError en la primera consulta
    """
    from google.api_core.exceptions import GoogleAPIError

    ga_service = MagicMock()

    call_count = {"n": 0}

    def mock_search(customer_id, query):
        call_count["n"] += 1
        if raise_api_error and call_count["n"] == 1:
            raise GoogleAPIError("error simulado de API")
        if call_count["n"] == 1:
            return iter(q1_rows)
        return iter(q2_rows)

    ga_service.search.side_effect = mock_search

    client = MagicMock()
    client.get_service.return_value = ga_service
    return client


# ============================================================================
# CASO 1 — Ambas guardas pasan → ok=True
# ============================================================================

def test_ok_both_guards_pass():
    """
    G1: ad group ENABLED (encontrado).
    G2: campaña tiene 3 grupos ENABLED → no es el único.
    Debe retornar ok=True.
    """
    q1 = [_make_row(100, "ENABLED")]
    q2 = [_make_row(100, "ENABLED"), _make_row(101, "ENABLED"), _make_row(102, "ENABLED")]
    client = _make_client(q1, q2)

    result = verify_adgroup_still_pausable(client, "4021070209", "100", "999")

    assert result["ok"] is True, f"Se esperaba ok=True, se obtuvo: {result}"
    assert result["guard"] == "", f"No debería haber guarda activada, se obtuvo: {result['guard']}"
    assert result["ad_group_status"] == "ENABLED"
    assert result["enabled_adgroups_in_campaign"] == 3
    assert result["verify_checked_at"] != ""
    print("PASS CASO 1 - ok=True: ambas guardas pasan (3 ENABLED en campaña)")


# ============================================================================
# CASO 2 — G1: ad group no encontrado
# ============================================================================

def test_g1_adgroup_not_found():
    """
    La consulta q1 retorna 0 filas → ad group no existe en la API.
    Debe retornar ok=False con guard='G1'.
    """
    client = _make_client(q1_rows=[], q2_rows=[])

    result = verify_adgroup_still_pausable(client, "4021070209", "999", "888")

    assert result["ok"] is False
    assert result["guard"] == "G1"
    assert "no encontrado" in result["reason"]
    print("PASS CASO 2 - G1: ad group no encontrado en la API")


# ============================================================================
# CASO 3 — G1: ad group ya en estado PAUSED
# ============================================================================

def test_g1_already_paused():
    """
    El ad group fue pausado manualmente antes de que llegue la aprobación.
    status='PAUSED' → guarda G1 activada.
    """
    q1 = [_make_row(100, "PAUSED")]
    client = _make_client(q1, q2_rows=[])

    result = verify_adgroup_still_pausable(client, "4021070209", "100", "999")

    assert result["ok"] is False
    assert result["guard"] == "G1"
    assert result["ad_group_status"] == "PAUSED"
    assert "ENABLED" in result["reason"]
    print("PASS CASO 3 - G1: ad group ya en estado PAUSED -> bloqueado")


# ============================================================================
# CASO 4 — G2: único ENABLED en campaña
# ============================================================================

def test_g2_only_enabled_in_campaign():
    """
    El ad group es el único ENABLED en su campaña.
    Pausarlo dejaría la campaña sin grupos activos → guarda G2 activada.
    """
    q1 = [_make_row(100, "ENABLED")]
    q2 = [_make_row(100, "ENABLED")]  # solo 1
    client = _make_client(q1, q2)

    result = verify_adgroup_still_pausable(client, "4021070209", "100", "999")

    assert result["ok"] is False
    assert result["guard"] == "G2"
    assert result["enabled_adgroups_in_campaign"] == 1
    assert "único" in result["reason"] or "1 ENABLED" in result["reason"]
    print("PASS CASO 4 - G2: unico ad group ENABLED -> bloqueado para proteger campana")


# ============================================================================
# CASO 5 — G2 pasa: exactamente 2 ENABLED (mínimo para permitir pausa)
# ============================================================================

def test_g2_two_enabled_allowed():
    """
    La campaña tiene exactamente 2 grupos ENABLED.
    G2 requiere enabled_count > 1 → debe pasar con 2.
    """
    q1 = [_make_row(100, "ENABLED")]
    q2 = [_make_row(100, "ENABLED"), _make_row(101, "ENABLED")]
    client = _make_client(q1, q2)

    result = verify_adgroup_still_pausable(client, "4021070209", "100", "999")

    assert result["ok"] is True
    assert result["enabled_adgroups_in_campaign"] == 2
    assert result["guard"] == ""
    print("PASS CASO 5 - G2 pasa: 2 grupos ENABLED (mínimo permitido)")


# ============================================================================
# CASO 6 — GoogleAPIError en la primera consulta
# ============================================================================

def test_api_error_returns_g1():
    """
    La API de Google Ads lanza un error en la consulta G1.
    Debe retornar ok=False con guard='G1' y el error en reason.
    """
    client = _make_client(q1_rows=[], q2_rows=[], raise_api_error=True)

    result = verify_adgroup_still_pausable(client, "4021070209", "100", "999")

    assert result["ok"] is False
    assert result["guard"] == "G1"
    assert "error de API" in result["reason"]
    assert result["verify_checked_at"] != ""
    print("PASS CASO 6 - GoogleAPIError -> ok=False, guard='G1'")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_ok_both_guards_pass,
        test_g1_adgroup_not_found,
        test_g1_already_paused,
        test_g2_only_enabled_in_campaign,
        test_g2_two_enabled_allowed,
        test_api_error_returns_g1,
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
