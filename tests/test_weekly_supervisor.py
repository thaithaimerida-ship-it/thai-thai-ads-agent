"""
Thai Thai Ads Agent — Tests de Fase 5: Weekly Supervisor

Pruebas unitarias para query_week_activity / build_supervisor_data /
get_next_best_action. Todo con datos sintéticos — sin SQLite real ni red.

Casos cubiertos:
  1. Semana vacía → conteos en 0, próxima acción = "sin incidencias"
  2. Pendiente drive next_action → menciona nombre + costo
  3. Ejecutado → aparece en executed count
  4. Expirado (postponed_at) → aparece en expired count
  5. Alerta sin pendiente → next_action menciona "alerta"

Ejecutar:
    cd thai-thai-ads-agent
    py -3.14 -m pytest tests/test_weekly_supervisor.py -v
    # o sin pytest:
    py -3.14 tests/test_weekly_supervisor.py
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.weekly_supervisor import build_supervisor_data, get_next_best_action


# ============================================================================
# HELPERS
# ============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(
    decision="proposed",
    executed=0,
    approved_at=None,
    approve_outcome=None,
    rejected_at=None,
    postponed_at=None,
    adgroup_name="Grupo Test",
    campaign_name="Thai Merida - Delivery",
    signal="AG1",
    cost_mxn=187.0,
):
    return {
        "id": 1,
        "signal": signal,
        "adgroup_id": "100",
        "adgroup_name": adgroup_name,
        "campaign_id": "999",
        "campaign_name": campaign_name,
        "decision": decision,
        "cost_mxn": cost_mxn,
        "risk_level": "RISK_PROPOSE",
        "executed": executed,
        "executed_at": _now() if executed else None,
        "approved_at": approved_at,
        "approve_outcome": approve_outcome,
        "rejected_at": rejected_at,
        "postponed_at": postponed_at,
        "created_at": _now(),
        "reason": "test",
    }


# ============================================================================
# CASO 1 — Semana vacía
# ============================================================================

def test_empty_week():
    """
    Sin filas → todos los conteos en 0.
    get_next_best_action retorna mensaje de sin incidencias.
    """
    data = build_supervisor_data([])

    assert data["total_relevant"] == 0, f"Se esperaba 0, se obtuvo {data['total_relevant']}"
    for s in data["counts"]:
        assert data["counts"][s] == 0, f"Conteo de '{s}' debe ser 0, se obtuvo {data['counts'][s]}"

    next_action = get_next_best_action(data)
    assert "sin incidencias" in next_action.lower(), f"Se esperaba 'sin incidencias' en: {next_action}"
    print("PASS CASO 1 - Semana vacía: conteos 0 y mensaje sin incidencias")


# ============================================================================
# CASO 2 — Pendiente activa el next_action
# ============================================================================

def test_pending_drives_next_action():
    """
    1 fila con decision='proposed' (pendiente).
    get_next_best_action debe mencionar el nombre del ad group y el costo.
    """
    rows = [_row(decision="proposed", cost_mxn=320.0, adgroup_name="Almuerzo Delivery")]
    data = build_supervisor_data(rows)

    assert data["counts"]["pending"] == 1, f"Se esperaba 1 pendiente, se obtuvo {data['counts']['pending']}"

    next_action = get_next_best_action(data)
    assert "Almuerzo Delivery" in next_action, f"Falta nombre del grupo en: {next_action}"
    assert "$320" in next_action or "320" in next_action, f"Falta costo en: {next_action}"
    print(f"PASS CASO 2 - Pendiente: next_action = {next_action[:80]}...")


# ============================================================================
# CASO 3 — Ejecutado aparece en executed count
# ============================================================================

def test_executed_shows_in_count():
    """
    1 fila ejecutada (executed=1).
    Debe aparecer en counts['executed'] y no en pending.
    """
    rows = [_row(executed=1, decision="proposed")]
    data = build_supervisor_data(rows)

    assert data["counts"]["executed"] == 1, f"Se esperaba 1 ejecutado, se obtuvo {data['counts']['executed']}"
    assert data["counts"]["pending"] == 0, f"Pendientes debe ser 0, se obtuvo {data['counts']['pending']}"
    print("PASS CASO 3 - Ejecutado: aparece en executed count correctamente")


# ============================================================================
# CASO 4 — Expirado (postponed_at) clasificado correctamente
# ============================================================================

def test_expired_classified_correctly():
    """
    1 fila con postponed_at y decision='proposed' (expiró por timeout).
    Debe clasificarse como 'expired', no como 'pending'.
    """
    rows = [_row(decision="proposed", postponed_at=_now())]
    data = build_supervisor_data(rows)

    assert data["counts"]["expired"] == 1, f"Se esperaba 1 expirado, se obtuvo {data['counts']['expired']}"
    assert data["counts"]["pending"] == 0, f"Pendientes debe ser 0, se obtuvo {data['counts']['pending']}"
    print("PASS CASO 4 - Expirado: postponed_at -> clasificado como 'expired'")


# ============================================================================
# CASO 5 — Alerta activa next_action cuando no hay pendientes
# ============================================================================

def test_alert_action_when_no_pending():
    """
    1 fila con decision='alert_sent'. Sin pendientes.
    get_next_best_action debe mencionar la alerta enviada.
    """
    rows = [_row(decision="alert_sent")]
    data = build_supervisor_data(rows)

    assert data["counts"]["alert"] == 1, f"Se esperaba 1 alerta, se obtuvo {data['counts']['alert']}"

    next_action = get_next_best_action(data)
    assert "alerta" in next_action.lower(), f"Se esperaba mención de alerta en: {next_action}"
    print(f"PASS CASO 5 - Alerta: next_action menciona alerta = {next_action[:80]}...")


# ============================================================================
# RUNNER MANUAL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_empty_week,
        test_pending_drives_next_action,
        test_executed_shows_in_count,
        test_expired_classified_correctly,
        test_alert_action_when_no_pending,
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
