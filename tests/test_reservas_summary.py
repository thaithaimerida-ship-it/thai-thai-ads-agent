"""Tests de la sección '📅 Reservas' del monitor: ventana LAST_7_DAYS por fecha_creacion,
agrupación por día en Mérida (UTC migradas vs Mérida landing), totales, degradación y SIN PII."""
from datetime import datetime

from engine.monitor_sections import _MERIDA, build_reservas_summary
from engine.monitor_email_renderer import _reservas

AHORA = datetime(2026, 7, 15, 12, 0, tzinfo=_MERIDA)   # ancla determinística (Mérida)


def _r(fecha_creacion, nombre, fecha_reserva, personas, origen="landing", telefono="+52999", email="x@y.com"):
    """Fila con el shape de list_reservations() (dict header→valor), CON tel/email para probar que NO se filtran."""
    return {"id": "id1", "fecha_creacion": fecha_creacion, "nombre": nombre, "telefono": telefono,
            "email": email, "fecha_reserva": fecha_reserva, "hora_reserva": "20:00:00",
            "personas": personas, "ocasion": "", "notas": "", "origen": origen,
            "estado": "confirmed", "notificaciones": ""}


def _ctx(items):
    return {"reservas": {"data_broken": False, "items": items}}


def test_ventana_por_fecha_creacion_y_totales():
    ctx = _ctx([
        _r("2026-07-14 10:00:00", "Ana", "2026-07-20", "4"),   # dentro
        _r("2026-07-13 21:30:00", "Beto", "2026-07-15", "2"),  # dentro
        _r("2026-04-01 2:38:28", "Viejo", "2026-04-20", "2", origen="migracion_supabase"),  # FUERA (>7d)
    ])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    assert s["data_broken"] is False
    assert s["total_reservas"] == 2                 # la vieja no entra
    assert s["total_comensales"] == 6               # 4 + 2
    assert [g["dia"] for g in s["grupos"]] == ["2026-07-14", "2026-07-13"]  # más reciente primero


def test_cero_cuando_todas_viejas_no_es_data_broken():
    # Realidad de hoy: las 10 migradas (abr-jun) → 0 en la ventana, pero NO es error.
    ctx = _ctx([_r("2026-05-10 09:00:00", "M", "2026-06-01", "3", origen="migracion_supabase")])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    assert s["data_broken"] is False
    assert s["total_reservas"] == 0 and s["total_comensales"] == 0 and s["grupos"] == []


def test_tz_migradas_utc_vs_landing_merida():
    # Mismo wall-clock 02:30 del 14-jul: la migrada es UTC (→ 13-jul 20:30 Mérida), la landing es Mérida (→ 14-jul).
    ctx = _ctx([
        _r("2026-07-14 02:30:00", "Migrada", "2026-07-25", "2", origen="migracion_supabase"),
        _r("2026-07-14 02:30:00", "Landing", "2026-07-25", "2", origen="landing"),
    ])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    dias = {g["dia"]: [x["nombre"] for x in g["reservas"]] for g in s["grupos"]}
    assert dias["2026-07-13"] == ["Migrada"]     # UTC → un día antes en Mérida
    assert dias["2026-07-14"] == ["Landing"]     # Mérida nativa


def test_hora_sin_zero_padding_parsea():
    ctx = _ctx([_r("2026-07-14 2:38:28", "SinPad", "2026-07-20", "5")])  # hora 1 dígito
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    assert s["total_reservas"] == 1 and s["grupos"][0]["dia"] == "2026-07-14"


def test_data_broken_si_sheets_falla():
    assert build_reservas_summary({"reservas": {"data_broken": True}}, ahora=AHORA)["data_broken"] is True
    assert build_reservas_summary({}, ahora=AHORA)["data_broken"] is True  # sin 'reservas' en context


def test_summary_no_lleva_pii():
    ctx = _ctx([_r("2026-07-14 10:00:00", "Ana", "2026-07-20", "4",
                   telefono="+529990001122", email="ana@secreto.com")])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    reserva = s["grupos"][0]["reservas"][0]
    assert set(reserva.keys()) == {"nombre", "fecha_reserva", "personas"}   # NADA de tel/email
    assert "telefono" not in reserva and "email" not in reserva


# ── renderer ──────────────────────────────────────────────────────────────────
def test_render_con_datos_sin_pii():
    ctx = _ctx([_r("2026-07-14 10:00:00", "Ana", "2026-07-20", "4",
                   telefono="+529990001122", email="ana@secreto.com")])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    text: list[str] = []
    html = _reservas({"reservas_summary": s}, text)
    plano = "\n".join(text)
    assert "📅 Reservas" in html
    # fecha_reserva en formato corto español, NO ISO:
    assert "Ana" in html and "20 jul" in html and "2026-07-20" not in html and "4 personas" in html
    assert "comensales" in html                      # el número va en <b>4</b>, el texto plano lo verifica:
    assert "4 comensales" in plano and "1 reserva nueva" in plano
    # PII jamás en el correo (ni HTML ni texto):
    assert "+529990001122" not in html and "ana@secreto.com" not in html
    assert "secreto.com" not in plano and "+529990001122" not in plano


def test_render_encabezado_dia_conteos_y_plurales():
    """Encabezado por día 'Día corto → N reservas · M personas' + plurales en las 3 posiciones."""
    ctx = _ctx([
        _r("2026-07-14 10:00:00", "Ana", "2026-07-20", "5"),   # día 14: Ana (10:00) primero
        _r("2026-07-14 09:00:00", "Beto", "2026-07-21", "1"),  # día 14: Beto, 1 persona (singular)
        _r("2026-07-13 20:00:00", "Cleo", "2026-07-25", "2"),  # día 13: 1 reserva (singular)
    ])
    s = build_reservas_summary(ctx, ahora=AHORA, dias=7)
    text: list[str] = []
    _reservas({"reservas_summary": s}, text)
    plano = "\n".join(text)
    # total: 3 reservas nuevas · 8 comensales
    assert "3 reservas nuevas" in plano and "8 comensales" in plano
    # encabezado por día con conteos y plural correcto:
    assert "→ 2 reservas · 6 personas" in plano      # día 14 (Ana 5 + Beto 1)
    assert "→ 1 reserva · 2 personas" in plano       # día 13 (Cleo)
    # singular de persona en la reserva de Beto:
    assert "· 1 persona" in plano
    # orden: día 14 (más reciente) aparece antes que día 13; Ana antes que Beto dentro del 14:
    assert plano.index("14 jul") < plano.index("13 jul")
    assert plano.index("Ana") < plano.index("Beto")


def test_render_cero_reservas():
    s = build_reservas_summary(_ctx([]), ahora=AHORA, dias=7)
    html = _reservas({"reservas_summary": s}, [])
    assert "Sin reservas nuevas registradas" in html


def test_render_data_broken():
    html = _reservas({"reservas_summary": {"data_broken": True}}, [])
    assert "no disponible esta vez" in html
