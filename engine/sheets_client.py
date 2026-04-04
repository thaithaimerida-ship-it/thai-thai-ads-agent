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
    Auto-detects columns by header name with positional fallback.
    Known layout: A=Fecha, C=Venta Neta, E=Venta c/Imp, F=Efectivo,
                  G=Tarjeta, H=Otros (plataformas), J=No. de Comensales
    """
    if len(rows) < 2:
        return []

    header = rows[0]

    def _col(fallback, *names):
        idx = _find_col(header, *names)
        return idx if idx != -1 else fallback

    col_fecha           = _col(0,  "Fecha", "fecha", "FECHA")
    col_venta_neta      = _col(2,  "Venta Neta", "venta_neta", "Neta")
    col_venta_bruta     = _col(4,  "Venta con Imp.", "Venta c/Imp", "Venta c/Imp.", "venta_bruta", "Bruta")
    col_pago_efectivo   = _col(5,  "Efectivo", "efectivo", "Pago Efectivo")
    col_pago_tarjeta    = _col(6,  "Tarjeta", "tarjeta", "Terminal", "POS")
    col_pago_plataformas = _col(7, "Otros", "otros", "Plataformas", "Delivery apps")
    col_comensales      = _col(9,  "No. de Comensales", "Comensales", "No.de Comensales", "comensales_real")
    col_obj_ventas      = _find_col(header, "Comensales_Obj_Ventas", "Obj_Ventas", "Objetivo Ventas", "obj_ventas")
    col_obj_equilibrio  = _find_col(header, "Comensales_Obj_Equilibrio", "Punto Equilibrio", "Equilibrio", "obj_equilibrio")
    col_ingresos_bruto  = _find_col(header, "Ingresos_Bruto", "Ingresos Bruto", "Ingresos Brutos", "ingresos_bruto")
    col_ingresos_neto   = _find_col(header, "Ingresos_Neto", "Ingresos Neto", "Ingresos Netos", "ingresos_neto")

    def _val_f(row, col):
        return _safe_float(row[col]) if col != -1 and col < len(row) else 0.0

    def _val_i(row, col):
        return _safe_int(row[col]) if col != -1 and col < len(row) else 0

    result = []
    for row in rows[1:]:  # skip header
        if not row or (col_fecha < len(row) and not row[col_fecha]):
            continue
        fecha = str(row[col_fecha]) if col_fecha < len(row) else ""
        if not fecha:
            continue

        comensales_real   = _val_i(row, col_comensales)
        obj_ventas        = _val_i(row, col_obj_ventas)
        obj_equilibrio    = _val_i(row, col_obj_equilibrio)
        ingresos_bruto    = _val_f(row, col_ingresos_bruto)
        ingresos_neto     = _val_f(row, col_ingresos_neto)
        venta_neta        = _val_f(row, col_venta_neta)
        venta_bruta       = _val_f(row, col_venta_bruta)
        pago_efectivo     = _val_f(row, col_pago_efectivo)
        pago_tarjeta      = _val_f(row, col_pago_tarjeta)
        pago_plataformas  = _val_f(row, col_pago_plataformas)

        result.append({
            "fecha": fecha,
            "comensales_real": comensales_real,
            "obj_ventas": obj_ventas,
            "obj_equilibrio": obj_equilibrio,
            "ingresos_bruto": ingresos_bruto,
            "ingresos_neto": ingresos_neto,
            "venta_neta": venta_neta,
            "venta_bruta": venta_bruta,
            "pago_efectivo": pago_efectivo,
            "pago_tarjeta": pago_tarjeta,
            "pago_plataformas": pago_plataformas,  # Rappi, Uber, delivery apps
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
    from engine.credentials import get_credentials, is_available
    if not spreadsheet_id or not is_available():
        print("[SHEETS] Credenciales o spreadsheet no configurados. Saltando.")
        return {}

    try:
        import gspread
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = get_credentials(scopes=scopes)
        if creds is None:
            print("[SHEETS] No se pudieron cargar credenciales. Saltando.")
            return {}
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
    from engine.credentials import get_credentials
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("[SHEETS] GOOGLE_SHEETS_SPREADSHEET_ID no configurado.")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = get_credentials(scopes=scopes)
    if creds is None:
        raise RuntimeError("[SHEETS] Credenciales no disponibles.")
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id)


def _read_ingresos_by_daterange(sh, start: date, end: date) -> dict:
    """
    Lee Ingresos_BD y agrega las filas cuya fecha está en [start, end].

    Retorna:
      total_neto (float) — suma de col F (Monto Neto)
      por_canal  (list)  — [{fuente, bruto, comision, neto, comision_pct}]
                           agrupado por col B (Fuente/Cliente)
    """
    COL_FECHA    = 0  # A
    COL_FUENTE   = 1  # B
    COL_BRUTO    = 3  # D — Monto Bruto
    COL_COMISION = 4  # E — Comisión/Retención
    COL_NETO     = 5  # F — Monto Neto

    _empty = {"total_neto": 0.0, "por_canal": []}

    try:
        ws = sh.worksheet("Ingresos_BD")
        rows = ws.get_all_values()
    except Exception as e:
        print(f"[SHEETS] Error leyendo Ingresos_BD: {e}")
        return _empty

    canal_map: dict = {}  # fuente -> {bruto, comision, neto}

    for row in rows[1:]:  # saltar header
        if not row or len(row) <= COL_NETO:
            continue
        fecha = _parse_fecha(str(row[COL_FECHA]).strip())
        if fecha is None or not (start <= fecha <= end):
            continue

        fuente   = str(row[COL_FUENTE]).strip().upper() if len(row) > COL_FUENTE else "OTRO"
        bruto    = _safe_float(row[COL_BRUTO])    if len(row) > COL_BRUTO    else 0.0
        comision = _safe_float(row[COL_COMISION]) if len(row) > COL_COMISION else 0.0
        neto     = _safe_float(row[COL_NETO])

        if fuente not in canal_map:
            canal_map[fuente] = {"bruto": 0.0, "comision": 0.0, "neto": 0.0}
        canal_map[fuente]["bruto"]    += bruto
        canal_map[fuente]["comision"] += comision
        canal_map[fuente]["neto"]     += neto

    total_neto = sum(v["neto"] for v in canal_map.values())

    por_canal = []
    for fuente, v in sorted(canal_map.items(), key=lambda x: -x[1]["neto"]):
        comision_pct = round(v["comision"] / v["bruto"] * 100, 1) if v["bruto"] > 0 else 0.0
        por_canal.append({
            "fuente": fuente,
            "bruto": round(v["bruto"], 2),
            "comision": round(v["comision"], 2),
            "neto": round(v["neto"], 2),
            "comision_pct": comision_pct,
        })

    return {"total_neto": round(total_neto, 2), "por_canal": por_canal}


def _read_comensales_by_daterange(sh, start: date, end: date) -> dict:
    """
    Lee Cortes_de_Caja para el rango [start, end] y agrega:
      Columnas confirmadas:
        A(0)=Fecha, C(2)=Venta Neta, E(4)=Venta con Imp.,
        F(5)=Efectivo, G(6)=Tarjeta, H(7)=Otros (delivery apps), J(9)=No. de Comensales

    Retorna totales de comensales + ventas por tipo de pago.
    """
    COL_FECHA        = 0
    COL_VENTA_NETA   = 2   # C — Venta Neta
    COL_VENTA_BRUTA  = 4   # E — Venta con Imp.
    COL_EFECTIVO     = 5   # F — Efectivo
    COL_TARJETA      = 6   # G — Tarjeta
    COL_PLATAFORMAS  = 7   # H — Otros (Rappi, Uber, delivery apps)
    COL_COMENSALES   = 9   # J — No. de Comensales

    _empty = {
        "total_comensales": 0, "dias_con_datos": 0,
        "dias_sobre_objetivo": 0, "dias_sobre_equilibrio": 0,
        "venta_neta_total": 0.0, "venta_bruta_total": 0.0,
        "pago_efectivo_total": 0.0, "pago_tarjeta_total": 0.0,
        "pago_plataformas_total": 0.0,
    }

    try:
        ws = sh.worksheet("Cortes_de_Caja")
        rows = ws.get_all_values()
    except Exception as e:
        print(f"[SHEETS] Error leyendo Cortes_de_Caja: {e}")
        return _empty

    total_coms       = 0
    dias_con_datos   = 0
    dias_sobre_obj   = 0
    dias_sobre_eq    = 0
    venta_neta       = 0.0
    venta_bruta      = 0.0
    pago_efectivo    = 0.0
    pago_tarjeta     = 0.0
    pago_plataformas = 0.0

    def _v(row, col):
        return _safe_float(row[col]) if col < len(row) else 0.0

    for row in rows[1:]:
        if not row or len(row) <= COL_COMENSALES:
            continue
        fecha = _parse_fecha(str(row[COL_FECHA]).strip())
        if fecha is None or not (start <= fecha <= end):
            continue

        coms = _safe_int(row[COL_COMENSALES])
        total_coms       += coms
        venta_neta       += _v(row, COL_VENTA_NETA)
        venta_bruta      += _v(row, COL_VENTA_BRUTA)
        pago_efectivo    += _v(row, COL_EFECTIVO)
        pago_tarjeta     += _v(row, COL_TARJETA)
        pago_plataformas += _v(row, COL_PLATAFORMAS)
        dias_con_datos   += 1
        if coms >= OBJETIVO_COMENSALES_DIA:
            dias_sobre_obj += 1
        if coms >= EQUILIBRIO_COMENSALES_DIA:
            dias_sobre_eq += 1

    return {
        "total_comensales":      total_coms,
        "dias_con_datos":        dias_con_datos,
        "dias_sobre_objetivo":   dias_sobre_obj,
        "dias_sobre_equilibrio": dias_sobre_eq,
        "venta_neta_total":      round(venta_neta, 2),
        "venta_bruta_total":     round(venta_bruta, 2),
        "pago_efectivo_total":   round(pago_efectivo, 2),
        "pago_tarjeta_total":    round(pago_tarjeta, 2),
        "pago_plataformas_total": round(pago_plataformas, 2),
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

        ingresos_sem = _read_ingresos_by_daterange(sh, monday, sunday)
        ventas = ingresos_sem["total_neto"]
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

        coms_data  = _read_comensales_by_daterange(sh, inicio, ayer)
        total_coms = coms_data["total_comensales"]

        # Fuente primaria: Cortes_de_Caja col C (Venta Neta)
        ventas = coms_data["venta_neta_total"]
        # Fallback: Ingresos_BD si Cortes_de_Caja no tiene datos de venta
        if ventas == 0.0:
            ingresos_mtd = _read_ingresos_by_daterange(sh, inicio, ayer)
            ventas = ingresos_mtd["total_neto"]

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
            # Desglose de pagos del periodo (de Cortes_de_Caja)
            "venta_neta_total":      coms_data["venta_neta_total"],
            "venta_bruta_total":     coms_data["venta_bruta_total"],
            "pago_efectivo_total":   coms_data["pago_efectivo_total"],
            "pago_tarjeta_total":    coms_data["pago_tarjeta_total"],
            "pago_plataformas_total": coms_data["pago_plataformas_total"],
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


# ── Función para agentes: resumen completo con ROI real por canal ─────────────

_DELIVERY_FUENTES = {"RAPPI", "UBBER", "UBER", "DIDI", "IFOOD"}
_LOCAL_FUENTES    = {"BBVA", "CAJA", "CLIP", "PAYPAL", "TRANSFERENCIA", "BANAMEX", "EFECTIVO"}


def resumen_negocio_para_agente(days: int = 7) -> dict:
    """
    Resumen ejecutivo de negocio para los agentes. Últimos `days` días (hasta ayer).

    CONTEXTO CLAVE para los agentes:
      - comensales (col J) = personas que comieron EN el restaurante (campaña Local)
      - pago_plataformas (col H) = pedidos delivery Rappi/Uber (campaña Delivery) — NO son comensales
      - Campaña Local  → medir con comensales + tarjeta + efectivo
      - Campaña Delivery → medir con plataformas (col H) y cruzar con neto Rappi+Uber en Ingresos_BD

    Retorna {} si no hay credenciales o falla la lectura.
    """
    try:
        sh = _get_spreadsheet()

        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        # ── Cortes_de_Caja: fuente primaria para todos los datos de venta ────
        coms_data = _read_comensales_by_daterange(sh, start, end)
        dias_con_datos         = coms_data["dias_con_datos"] or 1
        total_comensales       = coms_data["total_comensales"]
        total_venta_neta       = coms_data["venta_neta_total"]
        total_venta_bruta      = coms_data["venta_bruta_total"]
        total_pago_efectivo    = coms_data["pago_efectivo_total"]
        total_pago_tarjeta     = coms_data["pago_tarjeta_total"]
        total_pago_plataformas = coms_data["pago_plataformas_total"]

        # Ventas del restaurante físico (campaña Local)
        venta_local_total = round(total_pago_tarjeta + total_pago_efectivo, 2)
        ingreso_por_comensal = round(
            venta_local_total / total_comensales, 2
        ) if total_comensales > 0 else 0.0

        # ── Ingresos_BD: comisiones reales por fuente (delivery) ─────────────
        ingresos_result = _read_ingresos_by_daterange(sh, start, end)
        por_canal = ingresos_result["por_canal"]

        # Delivery: neto real después de comisiones Rappi/Uber
        delivery_canales = [c for c in por_canal if c["fuente"] in _DELIVERY_FUENTES]
        plataformas_neto  = round(sum(c["neto"]      for c in delivery_canales), 2)
        plataformas_bruto = round(sum(c["bruto"]     for c in delivery_canales), 2)
        plataformas_comision_total = round(sum(c["comision"] for c in delivery_canales), 2)
        comision_delivery_pct = round(
            plataformas_comision_total / plataformas_bruto * 100, 1
        ) if plataformas_bruto > 0 else 0.0

        porcentaje_plataformas = round(
            total_pago_plataformas / total_venta_bruta * 100, 1
        ) if total_venta_bruta > 0 else 0.0

        return {
            "periodo_dias": days,
            "fecha_inicio": start.isoformat(),
            "fecha_fin": end.isoformat(),
            "dias_con_datos": dias_con_datos,

            # ── VENTAS EN RESTAURANTE (campaña Local) ─────────────────────
            "comensales_total": total_comensales,
            "comensales_promedio_diario": round(total_comensales / dias_con_datos, 1),
            "venta_local_total": venta_local_total,         # tarjeta + efectivo
            "pago_efectivo_total": round(total_pago_efectivo, 2),
            "pago_tarjeta_total": round(total_pago_tarjeta, 2),
            "ingreso_por_comensal": ingreso_por_comensal,   # ticket promedio real

            # ── VENTAS DELIVERY (campaña Delivery) ────────────────────────
            "venta_plataformas_bruto": round(total_pago_plataformas, 2),  # col H Cortes_de_Caja
            "venta_plataformas_neto": plataformas_neto,     # después de comisiones Rappi+Uber
            "comision_delivery_pct": comision_delivery_pct,  # % comisión promedio

            # ── TOTALES ───────────────────────────────────────────────────
            "venta_neta_total": round(total_venta_neta, 2),
            "venta_bruta_total": round(total_venta_bruta, 2),
            "venta_neta_promedio_diario": round(total_venta_neta / dias_con_datos, 2),
            "porcentaje_plataformas": porcentaje_plataformas,
            "por_canal": por_canal,

            # ── ROI PARA AGENTES ──────────────────────────────────────────
            # El agente suma el gasto de la campaña correspondiente y calcula ROI
            "roi_data_local": {
                "venta": venta_local_total,
                "comensales": total_comensales,
                # costo_por_comensal lo calcula el agente: gasto_local / comensales
            },
            "roi_data_delivery": {
                "bruto": round(total_pago_plataformas, 2),
                "neto": plataformas_neto,
                "comision_pct": comision_delivery_pct,
                # roi_x lo calcula el agente: neto / gasto_delivery
            },
        }

    except Exception as e:
        import traceback
        print(f"[SHEETS] resumen_negocio_para_agente error: {e}")
        print(f"[SHEETS] {traceback.format_exc()}")
        return {}
