"""
Google Sheets Client — Thai Thai Business Data
Fetches real business data: comensales, ingresos, gastos, canales de venta.
"""
import os
import calendar
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional


def _safe_float(val) -> float:
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    return int(_safe_float(val))


def _find_col(header_row: List, *names) -> int:
    """Returns index of first matching column name (case-insensitive). Returns -1 if not found."""
    for name in names:
        for i, cell in enumerate(header_row):
            if str(cell).strip().lower() == name.lower():
                return i
    return -1


def parse_diario_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses the Cortes_de_Caja sheet into structured dicts.
    Auto-detects columns by header name.
    Known layout: A=Fecha, J=No. de Comensales
    """
    if len(rows) < 2:
        return []

    header = rows[0]

    # Detect column indices by header name
    col_fecha = _find_col(header, "Fecha", "fecha", "FECHA")
    col_comensales = _find_col(header, "No. de Comensales", "Comensales", "No.de Comensales", "comensales_real")
    col_obj_ventas = _find_col(header, "Comensales_Obj_Ventas", "Obj_Ventas", "Objetivo Ventas", "obj_ventas")
    col_obj_equilibrio = _find_col(header, "Comensales_Obj_Equilibrio", "Punto Equilibrio", "Equilibrio", "obj_equilibrio")
    col_ingresos_bruto = _find_col(header, "Ingresos_Bruto", "Ingresos Bruto", "Ingresos Brutos", "ingresos_bruto")
    col_ingresos_neto = _find_col(header, "Ingresos_Neto", "Ingresos Neto", "Ingresos Netos", "ingresos_neto")

    # Fallback to positional (legacy format)
    if col_fecha == -1:
        col_fecha = 0
    if col_comensales == -1:
        col_comensales = 9  # Column J (0-indexed)

    result = []
    for row in rows[1:]:  # skip header
        if not row or (col_fecha < len(row) and not row[col_fecha]):
            continue

        fecha = str(row[col_fecha]) if col_fecha < len(row) else ""
        if not fecha:
            continue

        comensales_real = _safe_int(row[col_comensales]) if col_comensales != -1 and col_comensales < len(row) else 0
        obj_ventas = _safe_int(row[col_obj_ventas]) if col_obj_ventas != -1 and col_obj_ventas < len(row) else 0
        obj_equilibrio = _safe_int(row[col_obj_equilibrio]) if col_obj_equilibrio != -1 and col_obj_equilibrio < len(row) else 0
        ingresos_bruto = _safe_float(row[col_ingresos_bruto]) if col_ingresos_bruto != -1 and col_ingresos_bruto < len(row) else 0.0
        ingresos_neto = _safe_float(row[col_ingresos_neto]) if col_ingresos_neto != -1 and col_ingresos_neto < len(row) else 0.0

        result.append({
            "fecha": fecha,
            "comensales_real": comensales_real,
            "obj_ventas": obj_ventas,
            "obj_equilibrio": obj_equilibrio,
            "ingresos_bruto": ingresos_bruto,
            "ingresos_neto": ingresos_neto,
            "sobre_equilibrio": comensales_real >= obj_equilibrio if obj_equilibrio > 0 else None,
            "sobre_objetivo_ventas": comensales_real >= obj_ventas if obj_ventas > 0 else None,
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


def parse_ingresos_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses Ingresos_BD sheet (transactional format — multiple rows per day).
    Columns: A=Fecha | B=Fuente/Cliente | C=Categoría | D=Monto Bruto | E=Comisión | F=Monto Neto | G=Cuenta | H=Notas
    Groups by date and sums bruto/neto. Also breaks down by category.
    """
    if len(rows) < 2:
        return []

    # Use fixed column positions (confirmed from screenshot)
    COL_FECHA = 0       # A
    COL_FUENTE = 1      # B
    COL_CATEGORIA = 2   # C
    COL_BRUTO = 3       # D — Monto Bruto
    COL_NETO = 5        # F — Monto Neto (Cálculo)

    aggregated: dict = {}  # fecha -> dict

    for row in rows[1:]:
        if not row or len(row) <= COL_NETO:
            continue
        fecha = str(row[COL_FECHA]).strip()
        if not fecha:
            continue

        bruto = _safe_float(row[COL_BRUTO])
        neto = _safe_float(row[COL_NETO])
        categoria = str(row[COL_CATEGORIA]).strip() if len(row) > COL_CATEGORIA else ""
        fuente = str(row[COL_FUENTE]).strip() if len(row) > COL_FUENTE else ""

        if fecha not in aggregated:
            aggregated[fecha] = {
                "fecha": fecha,
                "ingresos_bruto": 0.0,
                "ingresos_neto": 0.0,
                "por_categoria": {},
            }

        aggregated[fecha]["ingresos_bruto"] += bruto
        aggregated[fecha]["ingresos_neto"] += neto

        # Normalize category labels
        cat_key = categoria.lower().replace(" ", "_")
        if cat_key not in aggregated[fecha]["por_categoria"]:
            aggregated[fecha]["por_categoria"][cat_key] = 0.0
        aggregated[fecha]["por_categoria"][cat_key] += neto

    # Return sorted by date (lexicographic — works for "D enero, YYYY" style too)
    return list(aggregated.values())


# ── Business constants (fixed targets) ──────────────────────────────────────
OBJETIVO_INGRESOS_MENSUAL_NETO = 335_000.0   # MXN
EQUILIBRIO_INGRESOS_MENSUAL = 295_000.0      # MXN
OBJETIVO_COMENSALES_MES = 1_200              # físicos + reservaciones
EQUILIBRIO_COMENSALES_MES = 1_035            # punto de equilibrio mensual real
OBJETIVO_COMENSALES_DIA = 40
EQUILIBRIO_COMENSALES_DIA = 35               # 1,035 ÷ 30 días


def fetch_sheets_data(days: int = 7) -> Dict:
    """
    Main entry point. Returns aggregated business data from Google Sheets.
    Reads Cortes_de_Caja (comensales) + Ingresos_BD (ingresos).
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

        # ── Cortes_de_Caja: comensales diarios ─────────────────────────────
        diario_rows = []
        try:
            diario_ws = sh.worksheet("Cortes_de_Caja")
            diario_rows = diario_ws.get_all_values()
        except Exception:
            try:
                diario_ws = sh.get_worksheet(0)
                diario_rows = diario_ws.get_all_values()
            except Exception as e:
                print(f"[SHEETS] No se pudo leer hoja Cortes_de_Caja: {e}")

        # ── Ingresos_BD: ingresos brutos y netos ───────────────────────────
        ingresos_rows = []
        for tab_name in ["Ingresos_BD", "Ingresos BD", "GASTOS THAI THAI", "Ingresos"]:
            try:
                ingresos_ws = sh.worksheet(tab_name)
                ingresos_rows = ingresos_ws.get_all_values()
                print(f"[SHEETS] Ingresos leidos desde pestana: {tab_name} ({len(ingresos_rows)} filas)")
                break
            except Exception:
                continue
        if not ingresos_rows:
            print("[SHEETS] Hoja de ingresos no encontrada — verificar nombre de pestana")

        # ── Canales (opcional) ─────────────────────────────────────────────
        canales_rows = []
        try:
            canales_ws = sh.worksheet("Canales")
            canales_rows = canales_ws.get_all_values()
        except Exception:
            pass

        diario_data = parse_diario_sheet(diario_rows)
        ingresos_data = parse_ingresos_sheet(ingresos_rows)
        canales_data = parse_canales_sheet(canales_rows)

        recent_diario = diario_data[-days:] if diario_data else []
        recent_ingresos = ingresos_data[-days:] if ingresos_data else []
        recent_canales = canales_data[-days:] if canales_data else []

        if not recent_diario:
            return {}

        total_comensales = sum(r["comensales_real"] for r in recent_diario)
        promedio_comensales = round(total_comensales / len(recent_diario), 1)

        # Use Ingresos_BD if available, else fall back to Cortes_de_Caja columns
        if recent_ingresos:
            total_ingresos_bruto = sum(r["ingresos_bruto"] for r in recent_ingresos)
            total_ingresos_neto = sum(r["ingresos_neto"] for r in recent_ingresos)
        else:
            total_ingresos_bruto = sum(r.get("ingresos_bruto", 0) for r in recent_diario)
            total_ingresos_neto = sum(r.get("ingresos_neto", 0) for r in recent_diario)

        # Days above thresholds using fixed business constants
        dias_sobre_equilibrio = sum(1 for r in recent_diario if r["comensales_real"] >= EQUILIBRIO_COMENSALES_DIA)
        dias_sobre_ventas = sum(1 for r in recent_diario if r["comensales_real"] >= OBJETIVO_COMENSALES_DIA)

        # Weekly projection vs monthly objectives
        semanas_en_mes = 4.33
        comensales_objetivo_semana = round(OBJETIVO_COMENSALES_MES / semanas_en_mes)
        comensales_equilibrio_semana = round(EQUILIBRIO_COMENSALES_MES / semanas_en_mes)
        pct_vs_objetivo = round((total_comensales / comensales_objetivo_semana) * 100, 1) if comensales_objetivo_semana else 0
        pct_vs_equilibrio = round((total_comensales / comensales_equilibrio_semana) * 100, 1) if comensales_equilibrio_semana else 0

        return {
            "periodo_dias": len(recent_diario),
            "total_comensales": total_comensales,
            "promedio_comensales_diario": promedio_comensales,
            "total_ingresos_bruto": round(total_ingresos_bruto, 2),
            "total_ingresos_neto": round(total_ingresos_neto, 2),
            "dias_sobre_equilibrio": dias_sobre_equilibrio,
            "dias_sobre_objetivo_ventas": dias_sobre_ventas,
            "objetivos": {
                "comensales_objetivo_semana": comensales_objetivo_semana,
                "comensales_equilibrio_semana": comensales_equilibrio_semana,
                "pct_vs_objetivo_semanal": pct_vs_objetivo,    # % vs objetivo SEMANAL (no mensual)
                "pct_vs_equilibrio_semanal": pct_vs_equilibrio,
                "nota": "Los porcentajes comparan la semana actual vs el objetivo/equilibrio SEMANAL (mensual/4.33). No representan avance mensual acumulado.",
                "estado": (
                    "sobre_objetivo" if promedio_comensales >= OBJETIVO_COMENSALES_DIA
                    else "en_rango" if promedio_comensales >= EQUILIBRIO_COMENSALES_DIA
                    else "bajo_equilibrio"
                ),
            },
            "ultimo_dia": recent_diario[-1],
            "canales": recent_canales[-1] if recent_canales else {},
        }

    except Exception as e:
        import traceback
        print(f"[SHEETS] Error inesperado tipo={type(e).__name__}: {e}")
        print(f"[SHEETS] Traceback: {traceback.format_exc()}")
        return {}


# ── Fase 5: Reporte ejecutivo semanal ────────────────────────────────────────

_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_MESES_ES_NOMBRE = {v: k.capitalize() for k, v in _MESES_ES.items()}


def _parse_fecha(s: str) -> Optional[date]:
    """
    Parsea fechas de Google Sheets en dos formatos:
      '01 marzo 2026'      (Cortes_de_Caja — sin coma)
      '1 marzo, 2026'      (Ingresos_BD — con coma)
    Retorna None si no reconoce el formato.
    """
    if not s:
        return None
    s = s.strip().replace(",", "")  # normaliza coma
    parts = s.split()
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = _MESES_ES.get(parts[1].lower())
        year = int(parts[2])
        if not month:
            return None
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


def _get_spreadsheet():
    """
    Inicializa gspread y retorna el Spreadsheet de Thai Thai.
    Lanza excepción si faltan credenciales o ID de hoja.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "./ga4-credentials.json")

    if not spreadsheet_id or not os.path.exists(credentials_path):
        raise RuntimeError("[SHEETS] Credenciales o spreadsheet no configurados.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id)


def _read_ingresos_by_daterange(sh, start: date, end: date) -> float:
    """
    Lee Ingresos_BD (col F = Monto Neto) y suma las filas cuya fecha
    está en [start, end]. Retorna el total neto en MXN.
    """
    COL_FECHA = 0
    COL_NETO = 5  # F

    try:
        ws = sh.worksheet("Ingresos_BD")
        rows = ws.get_all_values()
    except Exception as e:
        print(f"[SHEETS] Error leyendo Ingresos_BD: {e}")
        return 0.0

    total = 0.0
    for row in rows[1:]:  # saltar header
        if not row or len(row) <= COL_NETO:
            continue
        fecha = _parse_fecha(str(row[COL_FECHA]).strip())
        if fecha is None:
            continue
        if start <= fecha <= end:
            total += _safe_float(row[COL_NETO])
    return total


def _read_comensales_by_daterange(sh, start: date, end: date) -> dict:
    """
    Lee Cortes_de_Caja (col J = No. de Comensales) y agrega:
      total_comensales, dias_con_datos, dias_sobre_objetivo, dias_sobre_equilibrio
    para el rango [start, end].
    """
    COL_FECHA = 0
    COL_COMENSALES = 9  # J (0-indexed)

    try:
        ws = sh.worksheet("Cortes_de_Caja")
        rows = ws.get_all_values()
    except Exception as e:
        print(f"[SHEETS] Error leyendo Cortes_de_Caja: {e}")
        return {"total_comensales": 0, "dias_con_datos": 0,
                "dias_sobre_objetivo": 0, "dias_sobre_equilibrio": 0}

    total = 0
    dias_con_datos = 0
    dias_sobre_obj = 0
    dias_sobre_eq = 0

    for row in rows[1:]:
        if not row or len(row) <= COL_COMENSALES:
            continue
        fecha = _parse_fecha(str(row[COL_FECHA]).strip())
        if fecha is None:
            continue
        if start <= fecha <= end:
            coms = _safe_int(row[COL_COMENSALES])
            total += coms
            dias_con_datos += 1
            if coms >= OBJETIVO_COMENSALES_DIA:
                dias_sobre_obj += 1
            if coms >= EQUILIBRIO_COMENSALES_DIA:
                dias_sobre_eq += 1

    return {
        "total_comensales": total,
        "dias_con_datos": dias_con_datos,
        "dias_sobre_objetivo": dias_sobre_obj,
        "dias_sobre_equilibrio": dias_sobre_eq,
    }


def _business_status(real: float, objetivo: float, equilibrio: float) -> str:
    """
    Clasifica el desempeño relativo a objetivos:
      'sobre_objetivo'  — verde
      'en_rango'        — amarillo (sobre equilibrio pero bajo objetivo)
      'bajo_equilibrio' — rojo
    """
    if real >= objetivo:
        return "sobre_objetivo"
    elif real >= equilibrio:
        return "en_rango"
    else:
        return "bajo_equilibrio"


def fetch_week_business_data(weeks_ago: int = 1) -> dict:
    """
    Retorna datos de negocio para la semana cerrada lunes–domingo.

    weeks_ago=1 → semana inmediata anterior (semana cerrada)
    weeks_ago=2 → la semana antes de esa (para comparación WoW)

    Retorna dict con:
      week_start, week_end (date)
      ventas_netas (float)
      comensales (int)
      dias_sobre_objetivo, dias_sobre_equilibrio (int)
      ventas_status, comensales_status (str)
    Retorna {} si no hay credenciales o falla la lectura.
    """
    try:
        sh = _get_spreadsheet()

        today = date.today()
        monday = today - timedelta(days=today.weekday() + 7 * weeks_ago)
        sunday = monday + timedelta(days=6)

        ventas = _read_ingresos_by_daterange(sh, monday, sunday)
        coms_data = _read_comensales_by_daterange(sh, monday, sunday)

        total_coms = coms_data["total_comensales"]
        dias = coms_data["dias_con_datos"] or 7  # evitar div/0

        # Objetivos semanales derivados del mensual / 4.33
        semanas_mes = 4.33
        obj_v_sem = OBJETIVO_INGRESOS_MENSUAL_NETO / semanas_mes
        eq_v_sem = EQUILIBRIO_INGRESOS_MENSUAL / semanas_mes
        obj_c_sem = OBJETIVO_COMENSALES_MES / semanas_mes
        eq_c_sem = EQUILIBRIO_COMENSALES_MES / semanas_mes

        return {
            "week_start": monday,
            "week_end": sunday,
            "ventas_netas": round(ventas, 2),
            "comensales": total_coms,
            "dias_con_datos": coms_data["dias_con_datos"],
            "dias_sobre_objetivo": coms_data["dias_sobre_objetivo"],
            "dias_sobre_equilibrio": coms_data["dias_sobre_equilibrio"],
            "ventas_status": _business_status(ventas, obj_v_sem, eq_v_sem),
            "comensales_status": _business_status(total_coms, obj_c_sem, eq_c_sem),
            "obj_ventas_semana": round(obj_v_sem),
            "eq_ventas_semana": round(eq_v_sem),
            "obj_comensales_semana": round(obj_c_sem),
            "eq_comensales_semana": round(eq_c_sem),
        }

    except Exception as e:
        import traceback
        print(f"[SHEETS] fetch_week_business_data error: {e}")
        print(f"[SHEETS] {traceback.format_exc()}")
        return {}


def fetch_mtd_business_data() -> dict:
    """
    Retorna datos de negocio del mes en curso (1° del mes hasta ayer).

    Incluye:
      mes_nombre, dias_transcurridos, dias_en_mes
      ventas_netas, comensales (reales)
      obj_ventas_prop, obj_comensales_prop (proporcional a días transcurridos)
      ventas_status, comensales_status
      proyeccion_ventas, proyeccion_comensales (cierre estimado del mes)
    Retorna {} si no hay credenciales o falla la lectura.
    """
    try:
        sh = _get_spreadsheet()

        ayer = date.today() - timedelta(days=1)
        inicio = date(ayer.year, ayer.month, 1)
        dias_mes = calendar.monthrange(ayer.year, ayer.month)[1]
        dias_t = ayer.day  # días transcurridos incluyendo ayer

        ventas = _read_ingresos_by_daterange(sh, inicio, ayer)
        coms_data = _read_comensales_by_daterange(sh, inicio, ayer)
        total_coms = coms_data["total_comensales"]

        # Objetivos proporcionales al avance del mes
        obj_v_prop = round(OBJETIVO_INGRESOS_MENSUAL_NETO * dias_t / dias_mes)
        eq_v_prop = round(EQUILIBRIO_INGRESOS_MENSUAL * dias_t / dias_mes)
        obj_c_prop = round(OBJETIVO_COMENSALES_MES * dias_t / dias_mes)
        eq_c_prop = round(EQUILIBRIO_COMENSALES_MES * dias_t / dias_mes)

        # Proyección lineal al cierre del mes
        proy_v = round(ventas / dias_t * dias_mes, 2) if dias_t > 0 else 0.0
        proy_c = round(total_coms / dias_t * dias_mes) if dias_t > 0 else 0

        return {
            "mes_nombre": _MESES_ES_NOMBRE.get(ayer.month, str(ayer.month)),
            "anio": ayer.year,
            "dias_transcurridos": dias_t,
            "dias_en_mes": dias_mes,
            "inicio": inicio,
            "hasta": ayer,
            "ventas_netas": round(ventas, 2),
            "comensales": total_coms,
            "dias_sobre_objetivo": coms_data["dias_sobre_objetivo"],
            "dias_sobre_equilibrio": coms_data["dias_sobre_equilibrio"],
            # Objetivos proporcionales
            "obj_ventas_prop": obj_v_prop,
            "eq_ventas_prop": eq_v_prop,
            "obj_comensales_prop": obj_c_prop,
            "eq_comensales_prop": eq_c_prop,
            # Objetivos mensuales completos (referencia)
            "obj_ventas_mes": OBJETIVO_INGRESOS_MENSUAL_NETO,
            "eq_ventas_mes": EQUILIBRIO_INGRESOS_MENSUAL,
            "obj_comensales_mes": OBJETIVO_COMENSALES_MES,
            "eq_comensales_mes": EQUILIBRIO_COMENSALES_MES,
            # Clasificación de estado vs proporcional
            "ventas_status": _business_status(ventas, obj_v_prop, eq_v_prop),
            "comensales_status": _business_status(total_coms, obj_c_prop, eq_c_prop),
            # Proyección de cierre
            "proyeccion_ventas": proy_v,
            "proyeccion_comensales": proy_c,
        }

    except Exception as e:
        import traceback
        print(f"[SHEETS] fetch_mtd_business_data error: {e}")
        print(f"[SHEETS] {traceback.format_exc()}")
        return {}
