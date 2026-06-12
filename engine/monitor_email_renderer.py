"""Email renderer for Monitor Digest V3 — Visual Contract v6.2 (mirrors the frozen
reference docs/contrato_v6_2/referencia.html, section by section).

Formats an existing digest. No fetching, no business decisions. Gmail/Outlook safe:
tables + inline CSS (grid/flex of the reference → tables), no SVG, no JS, no external
fonts, 600px, multipart text, thousands separators, $/conv. always 2 decimals.
Action buttons are links to the protected Part-B pages (no mailto).
"""
from __future__ import annotations

import html
from typing import Any


MAX_RENDERED_DECISIONS = 5
BRAND_TITLE = "Thai Thai Monitor"
TAGLINE = "Tu resumen semanal de Google Ads, Maps y tu web."
FOOTER = "🔒 Nada se ejecuta sin tu confirmación · Protegido: marca, términos thai, reservas."

# Palette from the frozen reference.
_NUMC = {"verde": "#3B6D11", "amarillo": "#854F0B", "rojo": "#A32D2D"}
_BARC = {"verde": "#639922", "amarillo": "#EF9F27", "rojo": "#A32D2D"}
_PILL = {"g": ("#EAF3DE", "#27500A"), "a": ("#FAEEDA", "#633806"), "r": ("#FCEBEB", "#791F1F")}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_text(value: Any) -> str:
    return f"{int(round(_number(value))):,}"


def _money(value: Any) -> str:
    return "$" + f"{_number(value):,.0f}"


def _money_mxn(value: Any) -> str:
    return "$" + f"{_number(value):,.0f}" + " MXN"


def _money2(value: Any) -> str:
    return "—" if value is None else "$" + f"{_number(value):,.2f}"


def _text(value: Any, fallback: str = "sin dato") -> str:
    value = "" if value is None else str(value)
    return " ".join(value.split()) or fallback


def _escape(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _human_range(date_range: Any) -> str:
    return {"TODAY": "hoy", "YESTERDAY": "ayer", "LAST_7_DAYS": "últimos 7 días",
            "LAST_14_DAYS": "últimos 14 días", "LAST_30_DAYS": "últimos 30 días",
            "THIS_MONTH": "mes actual", "LAST_MONTH": "mes anterior"}.get(
        str(date_range or "").strip().upper(), "periodo reciente")


def _num_color(c: Any) -> str:
    return _NUMC.get(str(c or "").strip().lower(), "#555")


def _important_anomalies(digest: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in digest.get("anomalies", []) or [] if i.get("type") == "negative_leak"]


def build_subject_email(digest: dict[str, Any]) -> str:
    n = len(digest.get("decisions", []) or [])
    if n:
        return f"🍜 Thai Thai — {n} decisiones esta semana"
    if _important_anomalies(digest):
        return f"🍜 Thai Thai — {len(_important_anomalies(digest))} aviso(s) importante(s)"
    return "🍜 Thai Thai — Todo normal, sin decisiones"


def _bar(pct: float, color: str, track: str = "#eee", height: int = 6) -> str:
    p = max(0, min(100, int(round(pct))))
    return (f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            f"style=\"border-collapse:collapse;background:{track};border-radius:3px;\">"
            f"<tr><td height=\"{height}\" width=\"{p}%\" style=\"background:{color};border-radius:3px;font-size:0;line-height:0;\">&nbsp;</td>"
            f"<td height=\"{height}\" style=\"font-size:0;line-height:0;\">&nbsp;</td></tr></table>")


def _btn(href: str, label: str, primary: bool = True) -> str:
    if primary:
        st = "background:#2d2a26;color:#fff;border:1px solid #2d2a26;"
    else:
        st = "background:#fff;color:#2d2a26;border:1px solid #ccc;"
    return (f"<a href=\"{_escape(href)}\" style=\"display:block;text-align:center;{st}"
            "border-radius:6px;padding:7px 10px;font-size:12px;text-decoration:none;font-weight:bold;\">"
            f"{_escape(label)}</a>")


def _pill(text: str, kind: str) -> str:
    bg, fg = _PILL.get(kind, _PILL["a"])
    return (f"<span style=\"background:{bg};color:{fg};font-size:11px;padding:2px 9px;"
            f"border-radius:10px;font-weight:bold;\">{_escape(text)}</span>")


def _kpi_lt(label: str, value: str, accent: str, num_color: str = "#1a1a1a") -> str:
    """KPI box: label TOP, value BOTTOM (campaigns/Maps/Search Console)."""
    return (f"<div style=\"border:1px solid #e2dccf;border-left:3px solid {accent};border-radius:6px;"
            "padding:9px 11px;background:#fff;height:100%;box-sizing:border-box;\">"
            f"<div style=\"font-size:10.5px;color:#666;\">{_escape(label)}</div>"
            f"<div style=\"font-size:19px;font-weight:bold;color:{num_color};\">{_escape(value)}</div></div>")


def _kpi_vt(value: str, label: str, accent: str, num_color: str = "#1a1a1a") -> str:
    """KPI box: value TOP, label BOTTOM (búsquedas — el número es el héroe)."""
    return (f"<div style=\"border:1px solid #e2dccf;border-left:3px solid {accent};border-radius:6px;"
            "padding:9px 11px;background:#fff;height:100%;box-sizing:border-box;\">"
            f"<div style=\"font-size:19px;font-weight:bold;color:{num_color};\">{_escape(value)}</div>"
            f"<div style=\"font-size:10.5px;color:#555;line-height:1.4;\">{_escape(label)}</div></div>")


def _grid2(cards: list[str]) -> str:
    """2×2 table of KPI cards."""
    rows = ""
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        tds = "".join(f"<td width=\"50%\" valign=\"top\" style=\"padding:4px;\">{c}</td>" for c in pair)
        if len(pair) == 1:
            tds += "<td width=\"50%\"></td>"
        rows += f"<tr>{tds}</tr>"
    return f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">{rows}</table>"


def _section(title: str, inner: str) -> str:
    return f"<div class=\"section\"><h2>{_escape(title)}</h2>{inner}</div>"


def _repair_block(message: str) -> str:
    return ("<div style=\"background:#fbf0e6;border:1px dashed #d9a066;border-radius:6px;"
            f"padding:10px;font-size:12px;color:#8a5a1f;\">🔧 {_escape(message)}</div>")


# ── A1 header ────────────────────────────────────────────────────────────────
def _header(digest: dict[str, Any], text: list[str]) -> str:
    period = _human_range(digest.get("date_range"))
    fecha = _text(digest.get("generated_date"), period) if digest.get("generated_date") else period
    parts = ["<div class=\"section\">",
             f"<p style=\"font-size:12px;color:#777;margin:0;\">{_escape(TAGLINE)}</p>",
             f"<p style=\"font-size:10.5px;color:#999;margin:4px 0 0;\">{_escape(fecha)} · 3 min</p>"]
    text.extend([BRAND_TITLE, TAGLINE, f"{fecha} · 3 min", ""])
    interno = digest.get("pedidos_gloriafood_interno")
    if interno:
        ventas = f"💰 Ventas registradas: {_int_text(interno.get('pedidos_7d'))} pedidos · {_money_mxn(interno.get('monto_mxn_7d'))}"
        if interno.get("pedido_real_mxn") is not None:
            ventas += f" · {_money(interno.get('pedido_real_mxn'))} por pedido real"
        parts.append(
            "<div style=\"background:#E7F0FA;border-radius:6px;padding:8px 10px;margin-top:10px;\">"
            f"<div style=\"font-size:13px;font-weight:bold;color:#114277;\">{_escape(ventas)}</div>"
            "<div style=\"font-size:11px;color:#185FA5;\">Registro interno GloriaFood, últimos 7 días</div></div>"
        )
        text.append(f"{ventas} (registro interno GloriaFood, últimos 7 días)")
    parts.append("</div>")
    text.append("")
    return "".join(parts)


# ── A2 posibles bloqueos ─────────────────────────────────────────────────────
def _posibles_bloqueos(digest: dict[str, Any], text: list[str]) -> str:
    decisions = (digest.get("decisions", []) or [])[:MAX_RENDERED_DECISIONS]
    inner = [
        "<div style=\"border:1px solid #e8b4b4;border-radius:8px;padding:12px;\">"
        "<p style=\"font-size:12.5px;font-weight:bold;color:#A32D2D;margin:0 0 4px;\">⚠ Posibles bloqueos — necesitan tu confirmación</p>"
        "<p style=\"font-size:10.5px;color:#666;margin:0 0 10px;line-height:1.5;\">Estas búsquedas dispararon tus anuncios pero parecen ser de otros negocios. "
        "Si confirmas, se bloquean: tu anuncio deja de aparecer (y de pagar) cuando alguien las busque.</p>"
    ]
    text.append("Posibles bloqueos — necesitan tu confirmación")
    if decisions:
        for i, d in enumerate(decisions, start=1):
            variantes = _number(d.get("variantes_count"))
            var = f" <span style=\"font-size:10.5px;color:#999;\">({_int_text(variantes)} variantes)</span>" if variantes > 1 else ""
            camps = _escape(", ".join(d.get("campaigns") or []) or "—")
            inner.append(
                "<div style=\"background:#f6f3ec;border-radius:6px;padding:10px 12px;margin-bottom:8px;\">"
                f"<p style=\"font-size:13px;margin:0;\"><b>{i}. \"{_escape(d.get('term'))}\"</b>{var} — {_escape(_money(d.get('cost_mxn')))} gastados<br>"
                f"<span style=\"font-size:11px;color:#666;\">Apareció en: {camps}</span></p>"
                "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin-top:8px;\"><tr>"
                f"<td width=\"58%\" style=\"padding-right:6px;\">{_btn(d.get('link_bloquear') or '#', 'Revisar y bloquear →', True)}</td>"
                f"<td width=\"42%\">{_btn(d.get('link_dejar') or '#', 'Dejar', False)}</td>"
                "</tr></table></div>"
            )
            text.append(f"• {i}. \"{_text(d.get('term'))}\" — {_money(d.get('cost_mxn'))} gastados — Apareció en: {', '.join(d.get('campaigns') or [])} [Revisar y bloquear]/[Dejar]")
        inner.append("<p style=\"font-size:10.5px;color:#999;margin-top:9px;line-height:1.5;\">\"Revisar y bloquear\" abre una página segura: ves variantes, "
                     "campañas y gasto, y confirmas. Solo ahí se ejecuta. \"Dejar\" lo marca válido y no se vuelve a preguntar.</p>")
    else:
        inner.append("<p>Sin decisiones esta semana. Sin decisiones pendientes.</p>")
        text.append("Sin decisiones esta semana. Sin decisiones pendientes.")
    inner.append("</div>")
    text.append("")
    return f"<div class=\"section\">{''.join(inner)}</div>"


# ── A3 campañas ──────────────────────────────────────────────────────────────
def _grid_metrics(cells: list[tuple[str, str, str]]) -> str:
    w = int(round(100 / max(len(cells), 1)))
    tds = "".join(
        f"<td align=\"center\" valign=\"top\" width=\"{w}%\" style=\"padding:0 1px;\">"
        f"<div style=\"font-size:9px;color:#999;\">{_escape(lbl)}</div>"
        f"<div style=\"font-size:11.5px;font-weight:bold;color:{col};\">{_escape(val)}</div></td>"
        for lbl, val, col in cells
    )
    return ("<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            f"style=\"background:#f6f3ec;border-radius:6px;padding:8px 2px;margin-top:8px;\"><tr>{tds}</tr></table>")


def _suggestion(row: dict[str, Any]) -> tuple[str, str]:
    sug = row.get("sugerencia_presupuesto") or {}
    accion = str(sug.get("accion") or "mantener")
    detalle = str(sug.get("detalle") or "")
    label = {"escalar": "escalar", "reducir": "reducir", "pausar": "revisar/pausar", "mantener": "mantener"}.get(accion, accion)
    extra = f" {detalle}" if detalle and detalle not in ("0%", "") else ""
    kind = {"escalar": "g", "mantener": "a", "reducir": "r", "pausar": "r"}.get(accion, "a")
    return f"Sugerencia: {label}{extra} · manual", kind


def _campaign_card(row: dict[str, Any]) -> str:
    name = _escape(row.get("campaign_name") or "Campaña")
    salud = int(_number(row.get("salud")))
    ncol = _num_color(row.get("salud_color"))
    salud_label = _escape(row.get("salud_label") or "salud")
    objetivo = _escape(row.get("objetivo_humano")) if row.get("objetivo_humano") else ""
    etiqueta = str(row.get("etiqueta_conversion") or "")
    money_word = "ventas" if etiqueta == "pedidos" else ("reservas" if etiqueta == "reservas" else "ventas")
    ctr = row.get("ctr")
    ctr_v = f"{_number(ctr):.1f}%" if ctr is not None else "—"
    conv_col = _NUMC["verde"] if row.get("mide_local") else "#1a1a1a"

    parts = ["<div style=\"border:1px solid #e2dccf;border-radius:8px;padding:12px;margin-bottom:10px;background:#fff;\">"]
    parts.append(
        "<table role=\"presentation\" width=\"100%\"><tr>"
        f"<td valign=\"top\"><p style=\"font-size:14px;font-weight:bold;margin:0;\">{name}</p>"
        + (f"<p style=\"font-size:10.5px;color:#999;margin:0;\">{objetivo}</p>" if objetivo else "")
        + "</td>"
        f"<td width=\"64\" align=\"center\" valign=\"top\"><div style=\"font-size:22px;font-weight:bold;line-height:1;color:{ncol};\">{salud}</div>"
        f"<div style=\"font-size:9.5px;color:#999;\">{salud_label}</div></td></tr></table>"
    )
    parts.append(_grid_metrics([
        ("Gasto", _money(row.get("gasto_7d", row.get("spend_mxn"))), "#1a1a1a"),
        ("Conv.", _int_text(row.get("all_conversions")), "#1a1a1a"),
        ("$/conv.", _money2(row.get("conv_por_mxn")), conv_col),
        ("CTR", ctr_v, "#1a1a1a"),
    ]))
    parts.append(
        "<p style=\"text-align:center;font-size:11.5px;margin:6px 0 0;\">"
        f"<span style=\"color:#777;\">De esas {_int_text(row.get('all_conversions'))}:</span> "
        f"<b>💰 {_int_text(row.get('conversiones_dinero'))} {money_word}</b> · "
        f"<b style=\"color:#534AB7;\">📍 {_int_text(row.get('senales_locales'))} señales</b> "
        "<span style=\"font-size:10.5px;color:#999;\">(rutas, llamadas, menú)</span></p>"
    )
    # CAMBIO 2: el bloque de pedidos vive en el header; aquí solo una línea tiny.
    if row.get("pedidos_gloriafood_interno"):
        parts.append("<p style=\"font-size:10.5px;color:#999;margin:6px 0 0;\">Pedidos no atribuibles por Google (GloriaFood) — ver ventas registradas arriba.</p>")
    sug_text, sug_kind = _suggestion(row)
    presupuesto = row.get("presupuesto_diario_mxn")
    presupuesto_txt = (_money(presupuesto) + "/día") if presupuesto is not None else "presupuesto sin dato"
    parts.append(
        "<table role=\"presentation\" width=\"100%\" style=\"margin-top:8px;\"><tr>"
        f"<td style=\"font-size:12px;\">📅 {_escape(presupuesto_txt)}</td>"
        f"<td align=\"right\">{_pill(sug_text, sug_kind)}</td></tr></table>"
    )
    parts.append("</div>")
    return "".join(parts)


def _campaign_text(row: dict[str, Any]) -> str:
    return (f"{_text(row.get('campaign_name'))} ({row.get('salud_label','salud')} {int(_number(row.get('salud')))}): "
            f"Gasto {_money(row.get('gasto_7d', row.get('spend_mxn')))} · Conv. {_int_text(row.get('all_conversions'))} · "
            f"CPA {_money2(row.get('cpa_dinero')) if row.get('cpa_dinero') is not None else '—'} · "
            f"$/conv. {_money2(row.get('conv_por_mxn'))} · 💰 {_int_text(row.get('conversiones_dinero'))} · 📍 {_int_text(row.get('senales_locales'))}")


def _campaigns(digest: dict[str, Any], text: list[str]) -> str:
    parts = ["<div class=\"section\"><h2>📊 Campañas — últimos 7 días</h2>",
             "<p style=\"font-size:10.5px;color:#666;margin:0 0 10px;\">Conversiones en dos columnas: 💰 dinero y 📍 señales. Nunca sumadas.</p>"]
    text.append("Campañas — últimos 7 días")
    for row in digest.get("campaign_rows", []) or []:
        parts.append(_campaign_card(row))
        text.append(_campaign_text(row))
    parts.append("<p style=\"font-size:10.5px;color:#999;line-height:1.5;\">\"Conv.\" y \"$/conv.\" cuadran con Google Ads "
                 "($/conv. SIEMPRE con dos decimales). El costo por venta real se medirá cuando la tienda propia "
                 "atribuya ventas. Salud y sugerencias usan solo dinero/señales separados.</p></div>")
    text.append("")
    return "".join(parts)


# ── A4 búsquedas ─────────────────────────────────────────────────────────────
def _busquedas(digest: dict[str, Any], text: list[str]) -> str:
    cards = digest.get("search_terms_cards") or {}
    sts = digest.get("search_terms_summary") or {}
    n = _int_text(sts.get("terminos_revisados") or digest.get("summary", {}).get("terms_reviewed"))
    marca = cards.get("marca_protegida") or {}
    por_conf = _money(cards.get("por_confirmar_mxn"))
    kpis = [
        _kpi_vt(_int_text(marca.get("terminos")), "buscaban Thai Thai o comida thai — protegidas", "#1D9E75", "#0F6E56"),
        _kpi_vt(_int_text(cards.get("pueden_traer_clientes")), "'restaurante cerca de mí' y similares — pueden traer clientes", "#639922", _NUMC["verde"]),
        _kpi_vt(_int_text(cards.get("externos_revision_mensual")), "parecen otros negocios — se revisan al mes", "#EF9F27", _NUMC["amarillo"]),
        _kpi_vt(por_conf, "gastado en esas búsquedas dudosas — por confirmar", "#EF9F27", _NUMC["amarillo"]),
    ]
    parts = ["<div class=\"section\"><h2>🔎 Qué buscó la gente para ver tus anuncios</h2>",
             f"<p style=\"font-size:10.5px;color:#666;margin:0 0 10px;\">Google registra cada búsqueda que hace aparecer tus anuncios. Esta semana fueron {n} distintas; el sistema las clasifica así:</p>",
             _grid2(kpis)]
    link = (digest.get("links") or {}).get("revision")
    if link:
        parts.append(f"<p style=\"margin-top:8px;\"><a href=\"{_escape(link)}\" style=\"color:#1a5276;font-size:11.5px;\">Ver las {n} búsquedas en la bandeja de revisión →</a></p>")
    parts.append("</div>")
    text.append(f"Búsquedas: {n} distintas · {_int_text(marca.get('terminos'))} protegidas · {_int_text(cards.get('pueden_traer_clientes'))} útiles · "
                f"{_int_text(cards.get('externos_revision_mensual'))} otros · por confirmar {por_conf}")
    text.append("")
    return "".join(parts)


# ── A5 reseñas ───────────────────────────────────────────────────────────────
def _resenas(digest: dict[str, Any], text: list[str]) -> str:
    rv = digest.get("reviews_summary") or {}
    if rv.get("data_broken") or not rv:
        text.append("Reseñas: en reparación")
        return _section("⭐ Reseñas", _repair_block("Reseñas en reparación — sin datos confiables esta semana."))
    promedio = rv.get("promedio_general")
    promedio_txt = f"{_number(promedio):.1f}" if promedio is not None else "—"
    nuevas = rv.get("nuevas_semana") or {}
    cinco, cuatro, tres = _number(nuevas.get("cinco")), _number(nuevas.get("cuatro")), _number(nuevas.get("tres_o_menos"))
    total = _number(nuevas.get("total")) or 1

    def brow(lbl, val):
        pct = val / total * 100
        bar = _bar(pct, "#534AB7", "#CECBF6", 6) if val > 0 else _bar(0, "#534AB7", "#CECBF6", 6)
        return (f"<tr><td width=\"30\" style=\"font-size:11.5px;color:#3C3489;\">{lbl}</td>"
                f"<td>{bar}</td><td width=\"18\" align=\"right\" style=\"font-size:11.5px;color:#3C3489;\">{_int_text(val)}</td></tr>")

    sin_resp = _int_text(rv.get("cinco_sin_responder"))
    inner = [
        "<div style=\"background:#EEEDFE;border-radius:8px;padding:14px;\">"
        "<table role=\"presentation\" width=\"100%\"><tr>"
        f"<td width=\"90\" align=\"center\" valign=\"top\"><div style=\"font-size:34px;font-weight:bold;color:#26215C;line-height:1;\">{_escape(promedio_txt)}</div>"
        "<div style=\"font-size:12px;color:#534AB7;\">★★★★½</div><div style=\"font-size:10.5px;color:#534AB7;\">promedio general</div></td>"
        "<td valign=\"top\">"
        f"<p style=\"font-size:11.5px;color:#3C3489;font-weight:bold;margin:0 0 5px;\">{_int_text(nuevas.get('total'))} nuevas esta semana:</p>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        + brow("5★", cinco) + brow("4★", cuatro) + brow("≤3★", tres)
        + "</table></td></tr></table>"
    ]
    for r in rv.get("requieren_atencion") or []:
        if int(_number(r.get("estrellas"))) <= 3:
            inner.append(f"<p style=\"font-size:11.5px;color:#791F1F;margin-top:10px;\">⚠️ {_int_text(r.get('estrellas'))}★ requiere tu atención: \"{_escape(r.get('extracto_corto'))}\"</p>")
    link = (digest.get("links") or {}).get("resenas")
    if link and _number(rv.get("cinco_sin_responder")) > 0:
        inner.append(f"<div style=\"margin-top:10px;\">{_btn(link, f'Responder las {sin_resp} de 5★ con IA →', True)}</div>")
    inner.append("<p style=\"font-size:10.5px;color:#534AB7;margin-top:6px;line-height:1.5;\">Abre una página segura: cada reseña con su respuesta "
                 "redactada por IA, ajustas si quieres y publicas una por una. La de 1★ solo se muestra — esa la respondes tú directo en Google.</p></div>")
    text.append(f"Reseñas: promedio {promedio_txt} · {_int_text(nuevas.get('total'))} nuevas · {sin_resp} de 5★ sin responder")
    text.append("")
    return _section("⭐ Reseñas", "".join(inner))


# ── A6 maps ──────────────────────────────────────────────────────────────────
def _maps(digest: dict[str, Any], text: list[str]) -> str:
    gbp = digest.get("gbp_summary") or {}
    if gbp.get("data_broken") or not gbp.get("metricas"):
        text.append("Maps: en reparación")
        return _section("📍 Tu negocio en Maps — 30 días", _repair_block("Datos de Maps en reparación."))
    m = gbp.get("metricas") or {}

    def v(key):
        return _int_text((m.get(key) or {}).get("valor"))

    kpis = [
        _kpi_lt("Vistas en Maps", v("vistas_maps"), "#378ADD", "#185FA5"),
        _kpi_lt("Rutas pedidas", v("rutas"), "#639922", _NUMC["verde"]),
        _kpi_lt("Clics al menú", v("clics_menu"), "#EF9F27", _NUMC["amarillo"]),
        _kpi_lt("Llamadas", v("llamadas"), "#7F77DD", "#534AB7"),
    ]
    inner = (_grid2(kpis)
             + "<p style=\"font-size:11.5px;color:#777;margin-top:8px;\">"
             f"Clics web {v('clics_web')} · Búsqueda móvil {v('vistas_busqueda_movil')} · "
             f"Maps escritorio {v('vistas_maps_desktop')} · Búsqueda escritorio {v('vistas_busqueda_desktop')}</p>")
    text.append(f"Maps: {v('vistas_maps')} vistas · {v('rutas')} rutas · {v('llamadas')} llamadas")
    text.append("")
    return _section("📍 Tu negocio en Maps — 30 días", inner)


# ── A7 anuncios ──────────────────────────────────────────────────────────────
def _anuncios(digest: dict[str, Any], text: list[str]) -> str:
    ads = digest.get("ads_quality_summary") or {}
    if ads.get("data_broken") or not ads:
        text.append("Anuncios: en reparación")
        return _section("📢 Anuncios", _repair_block("Calidad de anuncios en reparación — pendiente de cablear."))
    total = _int_text(ads.get("total_activos"))
    estado = "todos aprobados" if ads.get("todos_aprobados") else f"{len(ads.get('rechazados') or [])} rechazados"
    title = f"📢 Anuncios — {total} activos, {estado}"
    inner = ["<p style=\"font-size:12px;font-weight:bold;color:#3B6D11;margin:0 0 6px;\">Los que más producen</p>"]
    for h in (ads.get("caballos_de_batalla") or [])[:4]:
        cols = [("CTR", _text(h.get("ctr"))), ("Clics", _int_text(h.get("clics"))),
                ("Impr.", _int_text(h.get("impresiones"))), ("📍 Señales", _int_text(h.get("conversiones")))]
        tds = "".join(
            "<td align=\"center\" width=\"25%\">"
            f"<div style=\"font-size:9px;color:#999;\">{_escape(l)}</div>"
            f"<div style=\"font-size:11.5px;font-weight:bold;color:{'#534AB7' if l.startswith('📍') else '#1a1a1a'};\">{_escape(val)}</div></td>"
            for l, val in cols
        )
        inner.append(
            "<div style=\"border:1px solid #e2dccf;border-radius:8px;padding:9px 11px;margin-bottom:10px;\">"
            f"<p style=\"font-size:12.5px;font-weight:bold;margin:0 0 6px;\">{_escape(h.get('titulo_corto'))}</p>"
            f"<table role=\"presentation\" width=\"100%\"><tr>{tds}</tr></table></div>"
        )
    nt = ads.get("necesitan_trabajo") or {}
    smart_n = int(_number(nt.get("smart_sin_impresiones")))
    search = nt.get("search") or []
    search_total = sum(int(_number(g.get("variantes"))) for g in search)
    ads_link = (digest.get("links") or {}).get("ads")
    if search:
        rows = "".join(
            f"· \"{_escape(g.get('titulo_corto'))}\"" + (f" (×{_int_text(g.get('variantes'))} variantes)" if int(_number(g.get('variantes'))) > 1 else "")
            + f" — {_escape(g.get('campana'))}<br>" for g in search
        )
        link = f" <a href=\"{_escape(ads_link)}\" style=\"color:#1a5276;\">Ver en Ads →</a>" if ads_link else ""
        inner.append(
            "<div style=\"border:1px solid #e8b4b4;border-radius:8px;padding:11px 12px;\">"
            f"<p style=\"font-size:12.5px;color:#A32D2D;font-weight:bold;margin:0 0 6px;\">Los que necesitan trabajo ({_int_text(search_total)}) — sin impresiones 7+ días</p>"
            f"<p style=\"font-size:11.5px;line-height:1.6;margin:0 0 3px;\">{rows}</p>"
            f"<p style=\"font-size:11px;color:#666;margin:0;\">Razón: títulos casi idénticos entre sí — Google elige no mostrarlos.{link}</p></div>"
        )
    if smart_n:
        inner.append(f"<p style=\"font-size:10.5px;color:#999;margin-top:8px;\">Local y Delivery (smart): {_int_text(smart_n)} anuncios automáticos sin impresiones — Google los gestiona.</p>")
    inner.append("<p style=\"font-size:10.5px;color:#999;line-height:1.5;\">La \"calidad\" de Google (excelente/promedio/pobre) mide la variedad del texto, "
                 "no los resultados — un anuncio \"promedio\" puede ser tu mejor productor. Aquí mandan los resultados.</p>")
    text.append(f"Anuncios: {total} activos, {estado} · {_int_text(search_total)} de búsqueda necesitan trabajo · {_int_text(smart_n)} smart sin impresiones")
    text.append("")
    return _section(title, "".join(inner))


# ── A8 seo ───────────────────────────────────────────────────────────────────
def _seo(digest: dict[str, Any], text: list[str]) -> str:
    seo = digest.get("seo_summary") or {}
    if seo.get("data_broken") or not seo:
        text.append("SEO: en reparación")
        return _section("🌐 SEO de tu web", _repair_block("Análisis SEO en reparación — pendiente de cablear."))
    score = _int_text(seo.get("score"))
    comp = seo.get("componentes") or {}
    bars = ""
    for lbl, key in [("Velocidad", "performance"), ("SEO técnico", "seo_tecnico"), ("On-page", "on_page"),
                     ("Web Vitals", "web_vitals"), ("Accesibilidad", "accesibilidad")]:
        val = _number(comp.get(key))
        col = _BARC["verde"] if val >= 70 else _BARC["amarillo"] if val >= 40 else _BARC["rojo"]
        bars += (f"<tr><td width=\"82\" style=\"font-size:11px;color:#777;\">{_escape(lbl)}</td>"
                 f"<td>{_bar(val, col, '#eee', 6)}</td>"
                 f"<td width=\"26\" align=\"right\" style=\"font-size:11px;\"><b>{_int_text(val)}</b></td></tr>")

    def device(emoji, label, dev):
        d = seo.get(dev) or {}
        perf = int(_number(d.get("perf")))
        good = perf >= 70
        bg = "#EAF3DE" if good else "#FCEBEB"
        fg = "#27500A" if good else "#791F1F"
        nf = _NUMC["verde"] if good else _NUMC["rojo"]
        verdict = "bien" if good else "lento"
        carga = f"carga en {_escape(_text(d.get('lcp_s')))}s" if good else f"tarda {_escape(_text(d.get('lcp_s')))}s en cargar"
        return (f"<td width=\"50%\" valign=\"top\" style=\"padding:4px;\"><div style=\"background:{bg};border-radius:6px;padding:10px 12px;\">"
                f"<p style=\"font-size:11px;color:{fg};margin:0;\">{emoji} {label} — {verdict}</p>"
                f"<p style=\"font-size:17px;font-weight:bold;color:{nf};margin:2px 0 0;\">{perf}</p>"
                f"<p style=\"font-size:10.5px;color:{fg};margin:0;\">{carga}</p></div></td>")

    inner = [
        "<table role=\"presentation\" width=\"100%\"><tr>"
        f"<td width=\"80\" align=\"center\" valign=\"top\"><div style=\"font-size:34px;font-weight:bold;line-height:1;color:{_NUMC['verde']};\">{score}</div>"
        "<div style=\"font-size:10.5px;color:#999;\">de 100<br>checks " + _escape(_text(seo.get("checks_onpage"))) + "</div></td>"
        f"<td valign=\"top\"><table role=\"presentation\" width=\"100%\">{bars}</table></td></tr></table>",
        f"<table role=\"presentation\" width=\"100%\" style=\"margin-top:8px;\"><tr>{device('📱', 'Móvil', 'movil')}{device('🖥', 'Escritorio', 'escritorio')}</tr></table>",
    ]
    if seo.get("oportunidad_principal"):
        inner.append(f"<p style=\"font-size:11.5px;color:#633806;background:#FAEEDA;border-radius:6px;padding:8px 12px;margin-top:8px;\">💡 {_escape(seo.get('oportunidad_principal'))}</p>")
    text.append(f"SEO: {score}/100")
    text.append("")
    return _section("🌐 SEO de tu web", "".join(inner))


# ── A9 search console ────────────────────────────────────────────────────────
def _sc_title(sc: dict[str, Any]) -> str:
    base = f"🔍 Search Console · {int(_number(sc.get('dias') or 7))} días"
    s, e = sc.get("start_date"), sc.get("end_date")
    return f"{base} ({s} → {e})" if s and e else base


def _search_console(digest: dict[str, Any], text: list[str]) -> str:
    sc = digest.get("search_console") or {}
    if sc.get("data_broken"):
        text.append("Search Console: en reparación")
        return _section("🔍 Search Console · 7 días", _repair_block("Search Console en reparación — falta conectar la propiedad."))
    imp = _int_text(sc.get("impresiones"))
    clk = _int_text(sc.get("clics"))
    cells = [("Te vieron", imp), ("Entraron", clk), ("CTR", f"{_number(sc.get('ctr')):.1f}%"), ("Posición", f"{_number(sc.get('posicion_promedio')):.1f}")]
    tds = "".join(
        "<td align=\"center\" width=\"25%\">"
        f"<div style=\"font-size:9px;color:#999;\">{_escape(l)}</div>"
        f"<div style=\"font-size:13px;font-weight:bold;\">{_escape(v)}</div></td>" for l, v in cells
    )
    con_clics = [q for q in (sc.get("top_queries") or []) if _number(q.get("clics")) > 0][:3]
    queries = " · ".join(f"\"{_escape(q.get('query'))}\" ({_int_text(q.get('clics'))})" for q in con_clics) or "—"
    inner = [f"<p style=\"font-size:11.5px;color:#555;\">{imp} personas te vieron en los resultados de Google esta semana; {clk} entraron a tu sitio.</p>",
             f"<table role=\"presentation\" width=\"100%\" style=\"background:#f6f3ec;border-radius:6px;padding:8px 4px;margin:8px 0;\"><tr>{tds}</tr></table>",
             "<p style=\"font-size:11px;font-weight:bold;color:#666;margin:0 0 3px;\">Cómo te encuentran:</p>",
             f"<p style=\"font-size:11.5px;color:#555;margin:0;\">{queries}</p>",
             "<p style=\"font-size:10.5px;color:#999;margin-top:4px;\">Solo queries con clics &gt; 0.</p>"]
    rango = f" ({sc.get('start_date')}–{sc.get('end_date')})" if sc.get("start_date") and sc.get("end_date") else ""
    text.append(f"Search Console{rango}: {imp} te vieron · {clk} entraron")
    text.append("")
    return _section(_sc_title(sc), "".join(inner))


def _keepalive_alert(digest: dict[str, Any], text: list[str]) -> str:
    """Alerta SOLO si el keepalive de la DB de reservas falló (Supabase pausado/caído)."""
    k = digest.get("keepalive_db") or {}
    if not k.get("checked") or k.get("ok"):
        return ""
    err = _escape(k.get("error") or "sin detalle")
    text.append(f"⚠ ALERTA: la base de datos de reservas no respondió ({k.get('error')}). Revisa Supabase — "
                "el plan gratuito se pausa tras 7 días sin actividad y las reservas dejan de guardarse.")
    return (
        "<div style=\"border:2px solid #A32D2D;background:#fbe9e7;border-radius:8px;padding:12px;margin-bottom:12px;\">"
        "<p style=\"font-size:13px;font-weight:bold;color:#A32D2D;margin:0 0 4px;\">⚠ La base de datos de reservas no respondió</p>"
        f"<p style=\"font-size:11.5px;color:#5a1f1f;margin:0;line-height:1.5;\">El keepalive falló: {err}. Revisa Supabase "
        "cuanto antes — el plan gratuito se pausa tras 7 días sin actividad y las reservas dejan de guardarse.</p></div>"
    )


def _render_full_html(digest: dict[str, Any]) -> tuple[str, list[str]]:
    text: list[str] = []
    body = (_header(digest, text) + _keepalive_alert(digest, text) + _posibles_bloqueos(digest, text)
            + _campaigns(digest, text)
            + _busquedas(digest, text) + _resenas(digest, text) + _maps(digest, text)
            + _anuncios(digest, text) + _seo(digest, text) + _search_console(digest, text))
    return body, text


# ── A11 viernes ──────────────────────────────────────────────────────────────
def _render_friday_html(digest: dict[str, Any]) -> tuple[str, list[str]]:
    decisions = (digest.get("decisions", []) or [])[:MAX_RENDERED_DECISIONS]
    anomalies = _important_anomalies(digest)
    gasto = sum(_number(r.get("gasto_7d", r.get("spend_mxn"))) for r in digest.get("campaign_rows", []) or [])
    parts = ["<div class=\"section\"><p style=\"font-size:12px;color:#777;margin:0;\">Cierre de viernes — solo lo que necesita tu ojo.</p></div>",
             "<div class=\"section\"><h2>Decisiones pendientes del lunes</h2>"]
    text = [BRAND_TITLE, "Cierre de viernes", ""]
    alerta = _keepalive_alert(digest, text)
    if alerta:
        parts.insert(0, alerta)
    if decisions:
        for d in decisions:
            parts.append(
                "<div style=\"background:#f6f3ec;border-radius:6px;padding:10px 12px;margin-bottom:8px;\">"
                f"<p style=\"font-size:13px;margin:0 0 6px;\"><b>\"{_escape(d.get('term'))}\"</b> · {_escape(_money(d.get('cost_mxn')))}</p>"
                "<table role=\"presentation\" width=\"100%\"><tr>"
                f"<td width=\"58%\" style=\"padding-right:6px;\">{_btn(d.get('link_bloquear') or '#', 'Revisar y bloquear →', True)}</td>"
                f"<td width=\"42%\">{_btn(d.get('link_dejar') or '#', 'Dejar', False)}</td></tr></table></div>"
            )
            text.append(f"• \"{_text(d.get('term'))}\" · {_money(d.get('cost_mxn'))} — [bloquear]/[dejar]")
    else:
        parts.append("<p>Sin decisiones pendientes. Todo en orden.</p>")
        text.append("Sin decisiones pendientes. Todo en orden.")
    parts.append("</div><div class=\"section\"><h2>Anomalías nuevas</h2>")
    text.append("Anomalías nuevas")
    if anomalies:
        for a in anomalies:
            parts.append(f"<p style=\"font-size:12px;\">{_escape(a.get('term'))}: {_escape(_money(a.get('spend_mxn')))}.</p>")
            text.append(f"{_text(a.get('term'))}: {_money(a.get('spend_mxn'))}")
    else:
        parts.append("<p>Sin anomalías nuevas.</p>")
        text.append("Sin anomalías nuevas.")
    parts.append(f"</div><div class=\"section\"><h2>Gasto acumulado</h2><p style=\"font-size:18px;font-weight:bold;\">{_escape(_money_mxn(gasto))}</p></div>")
    text.append(f"Gasto acumulado: {_money_mxn(gasto)}")
    return "".join(parts), text


def _html_document(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;background:#f0ede6;color:#1a1a1a;margin:0;padding:14px 8px;}"
        ".box{max-width:600px;margin:0 auto;background:#fff;border:1px solid #ddd6c8;border-radius:10px;overflow:hidden;}"
        ".head{padding:14px 16px;border-bottom:1px solid #eee;}"
        ".head h1{font-size:17px;margin:0;font-weight:600;}"
        ".section{padding:14px 16px;border-bottom:1px solid #f0f0f0;}"
        "h2{font-size:13.5px;margin:0 0 8px;font-weight:600;}"
        "p,li{font-size:12px;line-height:1.5;}"
        ".footer{padding:12px 16px;font-size:10.5px;color:#999;text-align:center;}"
        "</style></head><body><div class=\"box\">"
        f"<div class=\"head\"><h1>{_escape(title)}</h1></div>"
        f"{body}<div class=\"footer\">{_escape(FOOTER)}</div>"
        "</div></body></html>"
    )


def render_monitor_email(digest: dict[str, Any], mode: str = "monday") -> dict[str, str]:
    subject = build_subject_email(digest)
    if str(mode).strip().lower() == "friday":
        body, text_lines = _render_friday_html(digest)
        subject = "🍜 Thai Thai — Cierre de viernes"
    else:
        body, text_lines = _render_full_html(digest)
    text_lines.append(FOOTER)
    return {"subject_email": subject, "html_email": _html_document(BRAND_TITLE, body), "text_email": "\n".join(text_lines)}
