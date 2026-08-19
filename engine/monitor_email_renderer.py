"""Email renderer for Monitor Digest V3 — Visual Contract v6.2 (mirrors the frozen
reference docs/contrato_v6_2/referencia.html, section by section).

Formats an existing digest. No fetching, no business decisions. Gmail/Outlook safe:
tables + inline CSS (grid/flex of the reference → tables), no SVG, no JS, no external
fonts, 600px, multipart text, thousands separators, $/conv. always 2 decimals.
Action buttons are links to the protected Part-B pages (no mailto).
"""
from __future__ import annotations

import html
from datetime import date
from typing import Any


_DIAS_ABBR_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_MESES_ABBR_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha_corta_es(iso: Any, con_dia: bool = False) -> str:
    """'2026-07-17' → '17 jul' (o 'Jue 17 jul' con con_dia). Fallback: el valor crudo si no parsea."""
    try:
        d = date.fromisoformat(str(iso or "").strip()[:10])
    except (ValueError, TypeError):
        return _text(iso, "")
    corto = f"{d.day} {_MESES_ABBR_ES[d.month - 1]}"
    return f"{_DIAS_ABBR_ES[d.weekday()]} {corto}" if con_dia else corto


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
    # Contrato v6.2 (2026-06-12): asunto fijo con la fecha de envío, igual para lunes y viernes.
    fecha = _text(digest.get("generated_date"), _human_range(digest.get("date_range")))
    return f"Thai Thai Monitor — {fecha}"


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
    todas = digest.get("decisions", []) or []
    decisions = todas[:MAX_RENDERED_DECISIONS]
    total_n = len(todas)
    total_gasto = sum(_number(d.get("cost_mxn")) for d in todas)
    bandeja = (digest.get("links") or {}).get("bloqueos") or "#"
    inner = [
        "<div style=\"border:1px solid #e8b4b4;border-radius:8px;padding:12px;\">"
        "<p style=\"font-size:12.5px;font-weight:bold;color:#A32D2D;margin:0 0 4px;\">⚠ Posibles bloqueos — necesitan tu confirmación</p>"
    ]
    text.append("Posibles bloqueos — necesitan tu confirmación")
    if decisions:
        inner.append(
            "<p style=\"font-size:11px;color:#A32D2D;margin:0 0 10px;\">"
            f"<b>{total_n} búsqueda{'s' if total_n != 1 else ''}</b> de otros negocios dispararon tus anuncios · "
            f"<b>{_escape(_money_mxn(total_gasto))}</b> gastados esta semana.</p>"
        )
        text.append(f"{total_n} búsquedas de otros negocios · {_money_mxn(total_gasto)} gastados esta semana")
        for i, d in enumerate(decisions, start=1):
            variantes = _number(d.get("variantes_count"))
            var = f" <span style=\"font-size:10.5px;color:#999;\">({_int_text(variantes)} variantes)</span>" if variantes > 1 else ""
            camps = _escape(", ".join(d.get("campaigns") or []) or "—")
            inner.append(
                "<div style=\"background:#f6f3ec;border-radius:6px;padding:9px 12px;margin-bottom:6px;\">"
                f"<p style=\"font-size:13px;margin:0;\"><b>{i}. \"{_escape(d.get('term'))}\"</b>{var} — {_escape(_money(d.get('cost_mxn')))}<br>"
                f"<span style=\"font-size:11px;color:#666;\">Apareció en: {camps}</span></p></div>"
            )
            text.append(f"• {i}. \"{_text(d.get('term'))}\" — {_money(d.get('cost_mxn'))} — {', '.join(d.get('campaigns') or [])}")
        if total_n > len(decisions):
            inner.append(f"<p style=\"font-size:11px;color:#999;margin:2px 0 10px;\">+{total_n - len(decisions)} más en la bandeja.</p>")
            text.append(f"+{total_n - len(decisions)} más en la bandeja")
        inner.append(f"<div style=\"margin-top:4px;\">{_btn(bandeja, 'Revisar y bloquear en la bandeja →', True)}</div>")
        inner.append("<p style=\"font-size:10.5px;color:#999;margin-top:9px;line-height:1.5;\">En la bandeja marcas varias y las bloqueas juntas, o revisas "
                     "una por una. Nada se ejecuta sin tu confirmación.</p>")
        text.append(f"→ Revisar y bloquear en la bandeja: {bandeja}")
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
    promedio_txt = f"{_number(promedio):.1f}" if promedio is not None else "—"   # 4.7 tal cual de la API
    total_reviews = rv.get("total_reviews")
    total_txt = _int_text(total_reviews) if total_reviews is not None else "—"
    nuevas = rv.get("nuevas_semana") or {}
    dist = rv.get("distribucion") or {}
    scan_ok = rv.get("scan_completo", True)

    # Barras = distribución HISTÓRICA por estrella (5★..1★) sobre el total real. Si el escaneo
    # completo falló, NO inventamos barras: "no disponible esta vez" (rating y total sí salen).
    if scan_ok and dist and total_reviews:
        def brow(estrellas):
            val = _number(dist.get(estrellas) if estrellas in dist else dist.get(str(estrellas)) or 0)
            pct = (val / total_reviews * 100) if total_reviews else 0
            return (f"<tr><td width=\"30\" style=\"font-size:11.5px;color:#3C3489;\">{estrellas}★</td>"
                    f"<td>{_bar(pct, '#534AB7', '#CECBF6', 6)}</td>"
                    f"<td width=\"40\" align=\"right\" style=\"font-size:11.5px;color:#3C3489;\">{_int_text(val)}</td></tr>")
        barras = ("<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
                  + "".join(brow(e) for e in (5, 4, 3, 2, 1)) + "</table>")
    else:
        barras = "<p style=\"font-size:11.5px;color:#999;\">Distribución: no disponible esta vez.</p>"

    sin_resp = _int_text(rv.get("cinco_sin_responder"))
    inner = [
        "<div style=\"background:#EEEDFE;border-radius:8px;padding:14px;\">"
        "<table role=\"presentation\" width=\"100%\"><tr>"
        f"<td width=\"100\" align=\"center\" valign=\"top\"><div style=\"font-size:34px;font-weight:bold;color:#26215C;line-height:1;\">{_escape(promedio_txt)}</div>"
        "<div style=\"font-size:15px;color:#534AB7;\">⭐</div>"
        "<div style=\"font-size:10.5px;color:#534AB7;\">promedio general</div>"
        f"<div style=\"font-size:10.5px;color:#534AB7;margin-top:4px;\">{_escape(total_txt)} reseñas</div></td>"
        "<td valign=\"top\">"
        "<p style=\"font-size:11.5px;color:#3C3489;font-weight:bold;margin:0 0 5px;\">Distribución (histórico):</p>"
        + barras +
        f"<p style=\"font-size:10.5px;color:#534AB7;margin:6px 0 0;\">{_int_text(nuevas.get('total'))} nuevas esta semana</p>"
        "</td></tr></table>"
    ]
    for r in rv.get("requieren_atencion") or []:
        if int(_number(r.get("estrellas"))) <= 3:
            inner.append(f"<p style=\"font-size:11.5px;color:#791F1F;margin-top:10px;\">⚠️ {_int_text(r.get('estrellas'))}★ requiere tu atención: \"{_escape(r.get('extracto_corto'))}\"</p>")

    # Módulo cerrado: hasta 3 pendientes (5★ sin responder) + "+N más" + UN botón a la bandeja.
    pendientes = rv.get("pendientes") or []
    pend_total = int(_number(rv.get("pendientes_total")))
    if pendientes:
        inner.append("<p style=\"font-size:11.5px;color:#3C3489;font-weight:bold;margin:12px 0 2px;\">Pendientes de responder (5★)</p>")
        inner.append(f"<p style=\"font-size:11px;color:#534AB7;margin:0 0 6px;\">"
                     f"<b>{_int_text(rv.get('cinco_sin_responder'))}</b> nuevas esta semana · "
                     f"<b>{pend_total}</b> sin responder en total</p>")
        for p in pendientes:
            inner.append(
                "<div style=\"background:#f6f3ec;border-radius:6px;padding:8px 10px;margin-bottom:5px;\">"
                f"<p style=\"font-size:11.5px;margin:0;\"><b>{_escape(p.get('reviewer'))}</b> · 5★<br>"
                f"<span style=\"color:#555;\">\"{_escape(p.get('extracto_corto'))}\"</span></p></div>"
            )
        extra = pend_total - len(pendientes)
        if extra > 0:
            inner.append(f"<p style=\"font-size:11px;color:#999;margin:0 0 8px;\">+{extra} más en la bandeja.</p>")
    link = (digest.get("links") or {}).get("resenas")
    if link and pend_total > 0:
        inner.append(f"<div style=\"margin-top:8px;\">{_btn(link, 'Responder reseñas en la bandeja →', True)}</div>")
    # La cláusula de ≤4★ solo aparece si hay reseñas bajas reales esta semana (singular/plural).
    n_bajas = int(_number(nuevas.get("cuatro"))) + int(_number(nuevas.get("tres_o_menos")))
    if n_bajas > 0:
        clausula = (" Las de ≤4★ solo se muestran — esas las respondes tú directo en Google."
                    if n_bajas != 1 else
                    " La de ≤4★ solo se muestra — esa la respondes tú directo en Google.")
    else:
        clausula = ""
    inner.append("<p style=\"font-size:10.5px;color:#534AB7;margin-top:6px;line-height:1.5;\">"
                 "En la bandeja cada reseña trae su respuesta redactada por IA: ajustas si quieres, "
                 "marcas varias y publicas." + clausula + "</p></div>")
    text.append(f"Reseñas: promedio {promedio_txt} · {total_txt} en total · {_int_text(pend_total)} sin responder")
    if pendientes:
        for p in pendientes:
            text.append(f"  • {_text(p.get('reviewer'))} (5★): \"{_text(p.get('extracto_corto'))}\"")
        if pend_total > len(pendientes):
            text.append(f"  +{pend_total - len(pendientes)} más en la bandeja")
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


def _reservas_persist_alert(digest: dict[str, Any], text: list[str]) -> str:
    """Dos alertas independientes de reservas (marcas durables en GCS):
      1) persist_failures → reservas que NO se guardaron en el libro (están en el correo).
      2) unconfirmed → reservas guardadas pero SIN confirmación al cliente: lista nombre/tel/
         fecha-hora para contactarlos sin ir al Sheet.
    """
    rp = digest.get("reservas_persist") or {}
    if not rp.get("checked"):
        return ""
    bloques = []

    n_fail = (rp.get("persist_failures") or {}).get("count", 0)
    if n_fail:
        text.append(f"⚠ ALERTA: {n_fail} reservas no se guardaron en el libro (Google Sheets) — "
                    "están en tu correo. Captúralas a mano en la pestaña Reservas.")
        bloques.append(
            "<div style=\"border:2px solid #A32D2D;background:#fbe9e7;border-radius:8px;padding:12px;margin-bottom:12px;\">"
            f"<p style=\"font-size:13px;font-weight:bold;color:#A32D2D;margin:0 0 4px;\">⚠ {n_fail} reservas no se guardaron en el libro</p>"
            "<p style=\"font-size:11.5px;color:#5a1f1f;margin:0;line-height:1.5;\">Estas reservas SÍ te llegaron por "
            "correo (la notificación nunca se pierde), pero no pudieron escribirse en Google Sheets. Captúralas a mano "
            "en la pestaña <b>Reservas</b>.</p></div>"
        )

    dup = rp.get("posible_duplicado") or {}
    n_dup = dup.get("count", 0)
    if n_dup:
        text.append(f"⚠ ALERTA: {n_dup} reservas con mismo contacto/slot pero distinto nombre "
                    "(¿duplicado o cuenta compartida?) — revisa:")
        filas_html = []
        for it in dup.get("items") or []:
            nuevo = _escape(it.get("nombre_nuevo") or "?")
            prev = _escape(", ".join(it.get("nombres_existentes") or []) or "?")
            fecha = _escape(it.get("fecha") or "")
            hora = _escape(it.get("hora") or "")
            text.append(f"   · {it.get('nombre_nuevo','')} vs {', '.join(it.get('nombres_existentes') or [])} "
                        f"· {it.get('fecha','')} {it.get('hora','')}")
            filas_html.append(f"<li style=\"margin:2px 0;\"><b>{nuevo}</b> vs {prev} · {fecha} {hora}</li>")
        bloques.append(
            "<div style=\"border:2px solid #7A5C00;background:#fff9e6;border-radius:8px;padding:12px;margin-bottom:12px;\">"
            f"<p style=\"font-size:13px;font-weight:bold;color:#7A5C00;margin:0 0 4px;\">⚠ {n_dup} reservas: mismo contacto/slot, distinto nombre</p>"
            "<p style=\"font-size:11.5px;color:#4a3a00;margin:0 0 6px;line-height:1.5;\">Mismo email+teléfono+fecha+hora+personas "
            "que otra reserva, pero con nombre distinto. Puede ser un duplicado o una cuenta compartida (pareja/familia). "
            "Ambas se guardaron — revisa y borra la que sobre:</p>"
            f"<ul style=\"font-size:11.5px;color:#4a3a00;margin:0;padding-left:18px;\">{''.join(filas_html)}</ul></div>"
        )

    unconf = rp.get("unconfirmed") or {}
    n_unc = unconf.get("count", 0)
    if n_unc:
        items = unconf.get("items") or []
        text.append(f"⚠ ALERTA: {n_unc} reservas guardadas SIN confirmación al cliente — contáctalos:")
        filas_html = []
        for it in items:
            nombre = _escape(it.get("nombre") or "(sin nombre)")
            tel = _escape(it.get("telefono") or "(sin teléfono)")
            fecha = _escape(it.get("fecha") or "")
            hora = _escape(it.get("hora") or "")
            text.append(f"   · {it.get('nombre','')} · {it.get('telefono','')} · {it.get('fecha','')} {it.get('hora','')}")
            filas_html.append(
                f"<li style=\"margin:2px 0;\"><b>{nombre}</b> · {tel} · {fecha} {hora}</li>")
        bloques.append(
            "<div style=\"border:2px solid #A36A00;background:#fff4e0;border-radius:8px;padding:12px;margin-bottom:12px;\">"
            f"<p style=\"font-size:13px;font-weight:bold;color:#A36A00;margin:0 0 4px;\">⚠ {n_unc} reservas guardadas sin confirmación al cliente — contáctalos</p>"
            "<p style=\"font-size:11.5px;color:#5a3a00;margin:0 0 6px;line-height:1.5;\">Estas reservas SÍ quedaron en el "
            "libro, pero no pudimos avisar al cliente (correo/WhatsApp fallaron). Llámalos para confirmar:</p>"
            f"<ul style=\"font-size:11.5px;color:#5a3a00;margin:0;padding-left:18px;\">{''.join(filas_html)}</ul></div>"
        )

    return "".join(bloques)


def _reservas(digest: dict[str, Any], text: list[str]) -> str:
    """Sección '📅 Reservas': reservas HECHAS esta semana (por fecha_creacion). Total de reservas
    + comensales, y desglose por día con nombre · fecha_reserva · personas. SIN PII (ni tel ni
    email — /monitor/digest es público). Degrada: si Sheets falló, 'no disponible esta vez'."""
    rz = digest.get("reservas_summary") or {}
    if rz.get("data_broken") or not rz:
        text.append("Reservas: no disponible esta vez")
        return _section("📅 Reservas", _repair_block("Reservas: no disponible esta vez."))

    total_r = int(_number(rz.get("total_reservas")))
    total_c = int(_number(rz.get("total_comensales")))
    r_txt = "reserva" if total_r == 1 else "reservas"
    nueva_txt = "nueva" if total_r == 1 else "nuevas"
    c_txt = "comensal" if total_c == 1 else "comensales"
    text.append(f"Reservas (hechas esta semana): {total_r} {r_txt} {nueva_txt} · {total_c} {c_txt}")

    inner = [
        "<div style=\"background:#eef6ee;border-radius:8px;padding:12px;\">"
        f"<p style=\"font-size:12px;margin:0;color:#245a24;\"><b>{_int_text(total_r)}</b> {r_txt} "
        f"{nueva_txt} esta semana · <b>{_int_text(total_c)}</b> {c_txt}</p></div>"
    ]
    if total_r == 0:
        inner.append("<p style=\"font-size:11.5px;color:#777;margin:10px 0 0;\">"
                     "Sin reservas nuevas registradas en el libro esta semana.</p>")
    else:
        for g in rz.get("grupos") or []:
            reservas = g.get("reservas") or []
            n_r = len(reservas)
            n_p = sum(int(_number(x.get("personas"))) for x in reservas)
            dia_hdr = _fecha_corta_es(g.get("dia"), con_dia=True)           # 'Jue 17 jul'
            rd_txt = "reserva" if n_r == 1 else "reservas"
            pd_txt = "persona" if n_p == 1 else "personas"
            inner.append(f"<p style=\"font-size:11.5px;color:#245a24;font-weight:bold;margin:12px 0 4px;\">"
                         f"{_escape(dia_hdr)} <span style=\"color:#4c8a4c;font-weight:normal;\">→ "
                         f"{n_r} {rd_txt} · {n_p} {pd_txt}</span></p>")
            text.append(f"  {dia_hdr} → {n_r} {rd_txt} · {n_p} {pd_txt}")
            filas = []
            for r in reservas:
                pers = int(_number(r.get("personas")))
                p_txt = "persona" if pers == 1 else "personas"
                fr = _fecha_corta_es(r.get("fecha_reserva"))               # '25 jul'
                filas.append(f"<li style=\"margin:2px 0;\"><b>{_escape(r.get('nombre'))}</b> · "
                             f"para {_escape(fr)} · {_int_text(pers)} {p_txt}</li>")
                text.append(f"     • {r.get('nombre', '')} · para {fr} · {pers} {p_txt}")
            inner.append(f"<ul style=\"font-size:11.5px;color:#333;margin:0 0 4px;padding-left:18px;\">"
                         f"{''.join(filas)}</ul>")
    return _section("📅 Reservas", "".join(inner))


def _render_full_html(digest: dict[str, Any]) -> tuple[str, list[str]]:
    text: list[str] = []
    body = (_header(digest, text) + _reservas_persist_alert(digest, text) + _posibles_bloqueos(digest, text)
            + _campaigns(digest, text)
            + _busquedas(digest, text) + _resenas(digest, text) + _maps(digest, text)
            + _reservas(digest, text)
            + _anuncios(digest, text) + _seo(digest, text) + _search_console(digest, text))
    return body, text


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


def _ads_error_banner_html() -> str:
    """Banner rojo, ancho completo, ARRIBA del correo: reporte degradado por Google Ads caído."""
    return (
        '<div style="background:#7f1d1d;color:#ffffff;padding:16px 20px;border-radius:8px;'
        'margin:0 0 20px;font-family:Arial,Helvetica,sans-serif;line-height:1.5;">'
        '<div style="font-size:16px;font-weight:bold;margin-bottom:4px;">'
        '&#9888;&#65039; Google Ads no respondió — reporte incompleto</div>'
        '<div style="font-size:14px;">Se omitieron las secciones de Google Ads '
        '(campañas, términos de búsqueda, calidad de anuncios). El resto del reporte es válido.<br>'
        '<strong>Acción:</strong> revisar el token de Google Ads (posible credencial revocada).</div>'
        '</div>'
    )


def _ads_error_banner_text() -> str:
    return (
        "========================================\n"
        "⚠️  GOOGLE ADS NO RESPONDIÓ — REPORTE INCOMPLETO\n"
        "Se omitieron las secciones de Google Ads.\n"
        "Acción: revisar el token de Google Ads (posible credencial revocada).\n"
        "========================================"
    )


def _ads_unexpected_banner_html(exc_type: str) -> str:
    """Banner naranja para una excepción INESPERADA (probable bug) — NO un token caído."""
    tipo = exc_type or "desconocido"
    return (
        '<div style="background:#78350f;color:#ffffff;padding:16px 20px;border-radius:8px;'
        'margin:0 0 20px;font-family:Arial,Helvetica,sans-serif;line-height:1.5;">'
        '<div style="font-size:16px;font-weight:bold;margin-bottom:4px;">'
        f'&#9888;&#65039; Error inesperado al generar la sección de Ads: {tipo}</div>'
        '<div style="font-size:14px;">Esto <strong>NO</strong> es un token caído — es una '
        'excepción no prevista. Revisar el log del servicio (posible bug), no solo el token.</div>'
        '</div>'
    )


def _ads_unexpected_banner_text(exc_type: str) -> str:
    return (
        "========================================\n"
        f"⚠️  ERROR INESPERADO EN LA SECCIÓN DE ADS: {exc_type or 'desconocido'}\n"
        "NO es un token caído — revisar el log del servicio (posible bug).\n"
        "========================================"
    )


def render_monitor_email(digest: dict[str, Any], mode: str = "monday") -> dict[str, str]:
    # Contrato v6.2 (2026-06-12): un solo formato completo para lunes y viernes. El parámetro
    # `mode` se conserva por compatibilidad de firma pero ya no cambia el render.
    subject = build_subject_email(digest)
    body, text_lines = _render_full_html(digest)
    # Reporte degradado: Google Ads caído → banner de aviso ARRIBA del todo + asunto inequívoco.
    # Dos variantes: fallo identificable de Ads/auth vs. excepción inesperada (probable bug).
    ads_error = digest.get("ads_error")
    if ads_error:
        exc_type = ads_error.get("exc_type", "") if isinstance(ads_error, dict) else ""
        if isinstance(ads_error, dict) and ads_error.get("kind") == "unexpected":
            subject = f"⚠️ {subject} · Error inesperado (Ads)"
            body = _ads_unexpected_banner_html(exc_type) + body
            text_lines = [_ads_unexpected_banner_text(exc_type), ""] + text_lines
        else:
            subject = f"⚠️ {subject} · Google Ads sin datos"
            body = _ads_error_banner_html() + body
            text_lines = [_ads_error_banner_text(), ""] + text_lines
    text_lines.append(FOOTER)
    return {"subject_email": subject, "html_email": _html_document(BRAND_TITLE, body), "text_email": "\n".join(text_lines)}
