"""
Google Sheets Client — Thai Thai Business Data
Fetches real business data: comensales, ingresos, gastos, canales de venta.
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional


def _safe_float(val) -> float:
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    return int(_safe_float(val))


def parse_diario_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses the Diario sheet rows into structured dicts.
    Expects header row first, then data rows.
    Columns: Fecha | Comensales_Real | Comensales_Obj_Ventas | Comensales_Obj_Equilibrio | Ingresos_Bruto | Ingresos_Neto
    """
    if len(rows) < 2:
        return []

    result = []
    for row in rows[1:]:  # skip header
        if not row or not row[0]:
            continue
        comensales_real = _safe_int(row[1]) if len(row) > 1 else 0
        obj_ventas = _safe_int(row[2]) if len(row) > 2 else 0
        obj_equilibrio = _safe_int(row[3]) if len(row) > 3 else 0
        ingresos_bruto = _safe_float(row[4]) if len(row) > 4 else 0.0
        ingresos_neto = _safe_float(row[5]) if len(row) > 5 else 0.0

        result.append({
            "fecha": str(row[0]),
            "comensales_real": comensales_real,
            "obj_ventas": obj_ventas,
            "obj_equilibrio": obj_equilibrio,
            "ingresos_bruto": ingresos_bruto,
            "ingresos_neto": ingresos_neto,
            "sobre_equilibrio": comensales_real >= obj_equilibrio,
            "sobre_objetivo_ventas": comensales_real >= obj_ventas,
        })
    return result


def parse_canales_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses Canales sheet.
    Columns: Fecha | Terminal_POS | Plataforma_Delivery | Efectivo | Transferencia
    """
    if len(rows) < 2:
        return []

    result = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        result.append({
            "fecha": str(row[0]),
            "terminal_pos": _safe_float(row[1]) if len(row) > 1 else 0.0,
            "plataforma_delivery": _safe_float(row[2]) if len(row) > 2 else 0.0,
            "efectivo": _safe_float(row[3]) if len(row) > 3 else 0.0,
            "transferencia": _safe_float(row[4]) if len(row) > 4 else 0.0,
        })
    return result


def fetch_sheets_data(days: int = 7) -> Dict:
    """
    Main entry point. Returns aggregated business data from Google Sheets.
    Falls back to empty dict if credentials or spreadsheet not configured.
    """
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "./ga4-credentials.json")

    if not spreadsheet_id or not os.path.exists(credentials_path):
        print("[SHEETS] Credenciales o spreadsheet no configurados. Saltando.")
        return {}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        # Fetch Diario sheet
        diario_rows = []
        canales_rows = []
        try:
            diario_ws = sh.worksheet("Diario")
            diario_rows = diario_ws.get_all_values()
        except Exception:
            try:
                diario_ws = sh.get_worksheet(0)
                diario_rows = diario_ws.get_all_values()
            except Exception as e:
                print(f"[SHEETS] No se pudo leer hoja Diario: {e}")

        try:
            canales_ws = sh.worksheet("Canales")
            canales_rows = canales_ws.get_all_values()
        except Exception:
            pass  # Optional sheet

        diario_data = parse_diario_sheet(diario_rows)
        canales_data = parse_canales_sheet(canales_rows)

        recent_diario = diario_data[-days:] if diario_data else []
        recent_canales = canales_data[-days:] if canales_data else []

        if not recent_diario:
            return {}

        total_comensales = sum(r["comensales_real"] for r in recent_diario)
        total_ingresos_bruto = sum(r["ingresos_bruto"] for r in recent_diario)
        total_ingresos_neto = sum(r["ingresos_neto"] for r in recent_diario)
        dias_sobre_equilibrio = sum(1 for r in recent_diario if r["sobre_equilibrio"])
        dias_sobre_ventas = sum(1 for r in recent_diario if r["sobre_objetivo_ventas"])
        promedio_comensales = round(total_comensales / len(recent_diario), 1)
        last = recent_diario[-1]

        return {
            "periodo_dias": len(recent_diario),
            "total_comensales": total_comensales,
            "promedio_comensales_diario": promedio_comensales,
            "total_ingresos_bruto": round(total_ingresos_bruto, 2),
            "total_ingresos_neto": round(total_ingresos_neto, 2),
            "dias_sobre_equilibrio": dias_sobre_equilibrio,
            "dias_sobre_objetivo_ventas": dias_sobre_ventas,
            "ultimo_dia": last,
            "canales": recent_canales[-1] if recent_canales else {},
        }

    except Exception as e:
        print(f"[SHEETS] Error inesperado: {e}")
        return {}
