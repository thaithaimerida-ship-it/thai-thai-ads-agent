import sys
sys.path.insert(0, ".")
from unittest.mock import patch, MagicMock
from engine.sheets_client import parse_diario_sheet, parse_canales_sheet

def test_parse_diario_sheet_returns_required_keys():
    mock_rows = [
        ["Fecha", "Comensales_Real", "Comensales_Obj_Ventas", "Comensales_Obj_Equilibrio", "Ingresos_Bruto", "Ingresos_Neto"],
        ["2026-03-17", "45", "60", "35", "9000", "7500"],
        ["2026-03-18", "38", "60", "35", "7600", "6200"],
    ]
    result = parse_diario_sheet(mock_rows)
    assert len(result) == 2
    assert result[0]["comensales_real"] == 45
    assert result[0]["ingresos_bruto"] == 9000.0
    assert result[0]["sobre_equilibrio"] is True

def test_parse_diario_empty_rows():
    result = parse_diario_sheet([["Fecha", "Comensales_Real"]])
    assert result == []

def test_parse_canales_sheet_returns_totals():
    mock_rows = [
        ["Fecha", "Terminal_POS", "Plataforma_Delivery", "Efectivo", "Transferencia"],
        ["2026-03-17", "5000", "2000", "1000", "500"],
    ]
    result = parse_canales_sheet(mock_rows)
    assert result[0]["terminal_pos"] == 5000.0
    assert result[0]["plataforma_delivery"] == 2000.0
