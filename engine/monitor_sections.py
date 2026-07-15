"""Pure section builders for the Monitor digest (read-only).

Each builder is a pure transform of already-collected data (search-term items +
an optional `context` dict). No IO, no Google Ads calls, no business mutation.
When a section's source is missing the builder returns the section with
`data_broken=true` so the renderer shows "en reparación" — never zeros as data.

Money vs local separation is sacred: money health is computed ONLY from mapped
money conversions; Local-style campaigns are measured by local actions and say so.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from typing import Any


# CPA targets (MXN) per objective — from CLAUDE.md.
_CPA_TARGETS = {
    "delivery": {"ideal": 50, "max": 65, "crit": 90},
    "delivery_search": {"ideal": 50, "max": 70, "crit": 100},
    "reserva": {"ideal": 50, "max": 85, "crit": 120},
    "general": {"ideal": 35, "max": 60, "crit": 100},
}


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(round(_num(value)))
    except (TypeError, ValueError):
        return 0


def classify_campaign(name: str) -> dict[str, Any]:
    """Derive stable metadata from the campaign name (4 stable campaigns).

    Objetivo mapping (confirmado por Hugo):
      - Local (Smart)        -> acciones locales (se mide por Maps), mide_local
      - Delivery (Smart)     -> pedidos (Gloria Food), dinero
      - Delivery Search      -> pedidos, dinero
      - Experiencia 2026     -> RESERVAS (reserva_completada_directa), dinero  (NO acciones locales)
    """
    norm = _normalize(name)
    if "delivery" in norm and "search" in norm:
        return {"tipo": "search", "objetivo_humano": "Pedidos a domicilio (búsqueda)",
                "etiqueta_conversion": "pedidos", "mide_local": False, "cpa_key": "delivery_search"}
    if "delivery" in norm:
        return {"tipo": "smart", "objetivo_humano": "Pedidos a domicilio (Gloria Food)",
                "etiqueta_conversion": "pedidos", "mide_local": False, "cpa_key": "delivery"}
    if "experiencia" in norm:
        return {"tipo": "search", "objetivo_humano": "Reservaciones (experiencia)",
                "etiqueta_conversion": "reservas", "mide_local": False, "cpa_key": "reserva"}
    if "reserva" in norm:
        return {"tipo": "search", "objetivo_humano": "Reservaciones en línea",
                "etiqueta_conversion": "reservas", "mide_local": False, "cpa_key": "reserva"}
    if "local" in norm or "maps" in norm:
        return {"tipo": "smart", "objetivo_humano": "Visibilidad y acciones en Maps",
                "etiqueta_conversion": "acciones locales", "mide_local": True, "cpa_key": "general"}
    return {"tipo": "search", "objetivo_humano": "Campaña general",
            "etiqueta_conversion": "acciones locales", "mide_local": True, "cpa_key": "general"}


def _salud_from_cpa(cpa: float, t: dict[str, int]) -> int:
    ideal, mx, crit = t["ideal"], t["max"], t["crit"]
    if cpa <= ideal:
        return 100
    if cpa <= mx:
        return int(round(100 - (cpa - ideal) / max(mx - ideal, 1) * 35))
    if cpa <= crit:
        return int(round(65 - (cpa - mx) / max(crit - mx, 1) * 35))
    return max(10, int(round(30 - (cpa - crit) / max(crit, 1) * 30)))


def _salud_color(salud: int) -> str:
    if salud >= 70:
        return "verde"
    if salud >= 40:
        return "amarillo"
    return "rojo"


def _suggestion(meta: dict[str, Any], salud: int, money_conv: float, local: float, spend: float) -> dict[str, Any]:
    """Budget SUGGESTION only — never executed. Always a manual change."""
    if meta["mide_local"]:
        if local > 0 and salud >= 80:
            return {"accion": "escalar", "detalle": "+20%",
                    "razon_humana": "Está generando acciones locales a buen costo. Considera subir el presupuesto."}
        if local > 0:
            return {"accion": "mantener", "detalle": "0%",
                    "razon_humana": "Genera acciones locales. Mantener y seguir vigilando."}
        return {"accion": "mantener", "detalle": "0%",
                "razon_humana": "Aún sin acciones locales claras. Mantener y observar antes de mover."}
    # money campaign
    if money_conv <= 0:
        return {"accion": "mantener", "detalle": "0%",
                "razon_humana": "Sin conversiones de dinero medibles (revisar tracking). No mover el presupuesto aún."}
    if salud >= 80:
        return {"accion": "escalar", "detalle": "+20%",
                "razon_humana": "El costo por venta está dentro de objetivo. Considera subir el presupuesto."}
    if salud >= 50:
        return {"accion": "mantener", "detalle": "0%",
                "razon_humana": "Costo por venta aceptable. Mantener y vigilar la tendencia."}
    if salud >= 30:
        return {"accion": "reducir", "detalle": "-20%",
                "razon_humana": "El costo por venta está alto. Considera bajar el presupuesto y revisar."}
    return {"accion": "pausar", "detalle": "revisar",
            "razon_humana": "Costo por venta crítico. Conviene revisar la campaña antes de seguir gastando."}


def _watch_note(meta: dict[str, Any], money_conv: float, local: float, spend: float) -> str:
    if meta["mide_local"]:
        if local > 0:
            return "Campaña local: se mide por acciones en Maps (rutas, llamadas, menú), no por ventas web."
        return "Campaña local: aún sin señales locales claras en la ventana. Vigilar."
    if money_conv > 0:
        return "Vigilar que el costo por venta se mantenga dentro de objetivo."
    # Sin dinero atribuido: el porqué depende del objetivo (no es falla de la campaña).
    if meta.get("etiqueta_conversion") == "pedidos":
        return ("La atribución por Ads no es posible con GloriaFood (sin gclid); "
                "medición completa con la tienda en línea propia.")
    if meta.get("etiqueta_conversion") == "reservas":
        return "Sin reservas atribuidas esta semana."
    return "Sin conversiones de dinero atribuidas en la ventana."


def _provisional_salud(ctr: float, ctr_30d, local: float, local_30d) -> int:
    """A3: 'provisional' health for money campaigns = señales + CTR vs su propio promedio
    de 30 días. Produces distinct, non-cloned values from real ratios."""
    ctr_ratio = (ctr / ctr_30d) if (ctr_30d and ctr_30d > 0) else 1.0
    sen_7d_daily = local / 7.0
    sen_30d_daily = (_num(local_30d) / 30.0) if local_30d else 0.0
    sen_ratio = (sen_7d_daily / sen_30d_daily) if sen_30d_daily > 0 else 1.0
    score = ctr_ratio * 0.5 + sen_ratio * 0.5
    return max(12, min(100, int(round(score * 65))))


def enrich_campaign_rows(rows: list[dict[str, Any]], context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Add the v6.2 campaign fields to already-built rows (additive, superset)."""
    context = context or {}
    budgets = context.get("campaign_budgets") or {}
    interno = context.get("pedidos_gloriafood_interno")
    for row in rows:
        name = row.get("campaign_name") or ""
        meta = classify_campaign(name)
        spend = _num(row.get("spend_mxn"))
        money_conv = _num(row.get("money_conversions"))
        local = _num(row.get("local_signals"))
        all_conv = _num(row.get("all_conversions")) or (money_conv + local)
        clicks = _num(row.get("clicks"))
        impressions = _num(row.get("impressions"))
        money_cpa = row.get("money_cpa_mxn")

        ctr = round(clicks / impressions * 100, 2) if impressions > 0 else None
        conv_por_mxn = round(spend / all_conv, 2) if all_conv > 0 else None  # $/conv. (cuadra con Ads)

        if meta["mide_local"]:
            salud = 85 if (local > 0 and spend / local <= 0.5) else (75 if local > 0 else (50 if spend > 0 else 60))
            salud_label = "salud"
        else:
            salud = _provisional_salud(_num(ctr), row.get("ctr_30d"), local, row.get("local_signals_30d"))
            salud_label = "provisional"

        presupuesto = row.get("daily_budget_mxn")
        if presupuesto is None:
            presupuesto = budgets.get(name)
        row.update({
            "tipo": meta["tipo"],
            "objetivo_humano": meta["objetivo_humano"],
            "mide_local": meta["mide_local"],
            "gasto_7d": spend,
            "all_conversions": round(all_conv, 2),
            "conversiones_dinero": round(money_conv, 2),
            "etiqueta_conversion": meta["etiqueta_conversion"],
            "cpa_dinero": money_cpa if money_conv > 0 else None,  # A3: "—" si no hay ventas
            "conv_por_mxn": conv_por_mxn,
            "ctr": ctr,
            "senales_locales": round(local, 2),
            "salud": salud,
            "salud_label": salud_label,
            "salud_color": _salud_color(salud),
            "presupuesto_diario_mxn": (round(_num(presupuesto), 2) if presupuesto is not None else None),
            "sugerencia_presupuesto": _suggestion(meta, salud, money_conv, local, spend),
            "nota_vigilancia": _watch_note(meta, money_conv, local, spend),
            "link_ads": (context.get("links") or {}).get("ads"),
        })
        # GloriaFood internal register on the Delivery (Smart) card; $/pedido real
        # se calcula desde su gasto y se expone también en el dict del header (CAMBIO 2).
        if interno and meta["tipo"] == "smart" and meta["etiqueta_conversion"] == "pedidos":
            row["pedidos_gloriafood_interno"] = interno
            pedidos = _num(interno.get("pedidos_7d"))
            pedido_real = round(spend / pedidos, 2) if pedidos > 0 else None
            row["pedido_real_mxn"] = pedido_real
            interno["pedido_real_mxn"] = pedido_real
    return rows


def build_campaign_rows_from_context(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """B-1: build campaign rows from the authoritative 4-campaign metrics (incl. Smart)
    when the route provides them, instead of inferring from search terms only."""
    context = context or {}
    rows = []
    for m in context.get("campaign_metrics") or []:
        money = _num(m.get("money_conversions"))
        spend = _num(m.get("spend_mxn"))
        rows.append({
            "campaign_name": m.get("name") or m.get("campaign_name") or "Sin campaña",
            "spend_mxn": round(spend, 2),
            "all_conversions": round(_num(m.get("all_conversions")), 2),
            "money_conversions": round(money, 2),
            "money_cpa_mxn": round(spend / money, 2) if money > 0 else None,
            "local_signals": round(_num(m.get("local_signals")), 2),
            "local_signal_cost_mxn": None,
            "clicks": _int(m.get("clicks")),
            "impressions": _int(m.get("impressions")),
            "daily_budget_mxn": m.get("daily_budget_mxn"),
            "all_conversions_30d": m.get("all_conversions_30d"),
            "local_signals_30d": m.get("local_signals_30d"),
            "ctr_30d": m.get("ctr_30d"),
            "status_human": "",
            "recommendation_human": "Monitorear. No escalar automáticamente.",
        })
    rows.sort(key=lambda r: r["spend_mxn"], reverse=True)
    return enrich_campaign_rows(rows, context)


def _money_in_breakdown(actions: list[dict[str, Any]]) -> float:
    from engine.search_term_classifier import MONEY_ACTION_NAMES, _normalize as _norm_action
    total = 0.0
    for a in actions or []:
        if _norm_action(a.get("name")) in MONEY_ACTION_NAMES:
            total += _num(a.get("all_conversions"))
    return total


def _window_split(campaigns: list[dict[str, Any]], breakdown: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Per-campaign window stats. señales (local) = TODO lo no-dinero, así el desglose
    💰+📍 siempre suma exactamente al total all_conversions (contrato A3)."""
    breakdown = breakdown or {}
    out: dict[str, dict[str, Any]] = {}
    for c in campaigns:
        cid = str(c.get("id") or c.get("campaign_id") or "")
        name = c.get("name") or c.get("campaign_name")
        spend = _num(c.get("cost_micros")) / 1_000_000 if c.get("cost_micros") is not None else _num(c.get("spend_mxn", c.get("spend")))
        all_conv = _num(c.get("all_conversions", c.get("conversions")))
        money = _money_in_breakdown((breakdown.get(cid) or {}).get("actions"))
        local = max(0.0, all_conv - money)
        clicks = _num(c.get("clicks"))
        impr = _num(c.get("impressions"))
        out[name] = {
            "spend_mxn": round(spend, 2), "all_conversions": round(all_conv, 2),
            "money_conversions": round(money, 2), "local_signals": round(local, 2),
            "clicks": _int(clicks), "impressions": _int(impr),
            "ctr": round(clicks / impr * 100, 2) if impr > 0 else 0.0,
            "daily_budget_mxn": c.get("daily_budget_mxn"),
        }
    return out


def build_campaign_metrics(campaigns, breakdown, campaigns_30d=None, breakdown_30d=None):
    """Per-campaign metrics with money/señales split (señales = total − dinero) and,
    when 30-day data is given, the 30d averages used for the 'provisional' health."""
    cur = _window_split(campaigns, breakdown)
    prev = _window_split(campaigns_30d or [], breakdown_30d) if campaigns_30d else {}
    out = []
    for name, m in cur.items():
        p = prev.get(name) or {}
        out.append({
            "name": name,
            **m,
            "all_conversions_30d": p.get("all_conversions"),
            "local_signals_30d": p.get("local_signals"),
            "ctr_30d": p.get("ctr"),
        })
    return out


def build_gbp_summary(context: dict[str, Any] | None) -> dict[str, Any]:
    gbp = (context or {}).get("gbp")
    if not gbp or gbp.get("data_broken"):
        return {"data_broken": True, "periodo_dias": 30}
    metricas = gbp.get("metricas") or {}
    maps = (metricas.get("vistas_maps") or {})
    rutas = (metricas.get("rutas") or {})
    alerta = bool(
        maps.get("delta_pct") is not None and maps.get("delta_pct") <= -20
        and rutas.get("delta_pct") is not None and rutas.get("delta_pct") <= -20
    )
    return {
        "data_broken": False,
        "periodo_dias": gbp.get("periodo_dias", 30),
        "metricas": metricas,
        "alerta_caida": alerta,
    }


def _safe_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError, TypeError):
        return None


def _stars(review: dict[str, Any]) -> int:
    try:
        return int(review.get("stars") or 0)
    except (TypeError, ValueError):
        return 0


def _within_days(iso: Any, reference: datetime, days: int) -> bool:
    ts = _safe_ts(iso)
    if ts is None:
        return False
    return reference - timedelta(days=days) <= ts <= reference + timedelta(days=1)


def build_reviews_summary(context: dict[str, Any] | None, reference_date: str | None = None) -> dict[str, Any]:
    context = context or {}
    reviews_ctx = context.get("reviews")
    if not reviews_ctx or reviews_ctx.get("data_broken"):
        return {"data_broken": True}
    reviews = reviews_ctx.get("reviews") or []
    if not reviews:
        return {"data_broken": True}

    reference = _safe_ts(reference_date)
    if reference is None:
        reference = max(
            (ts for ts in (_safe_ts(r.get("create_time")) for r in reviews) if ts is not None),
            default=datetime(2026, 1, 1),
        )

    stats = reviews_ctx.get("stats") or {}
    promedio = stats.get("average_rating")   # 4.7 directo de la API (bug #2); NO se calcula a mano

    nuevas = [r for r in reviews if _within_days(r.get("create_time"), reference, 7)]
    cinco = sum(1 for r in nuevas if _stars(r) == 5)
    cuatro = sum(1 for r in nuevas if _stars(r) == 4)
    tres_menos = sum(1 for r in nuevas if 0 < _stars(r) <= 3)
    cinco_sin_responder = sum(1 for r in nuevas if _stars(r) == 5 and not r.get("has_reply"))

    link_reviews = (context.get("links") or {}).get("reviews")
    requieren = [
        {
            "estrellas": _stars(r),
            "extracto_corto": ((r.get("comment") or "")[:140] + ("…" if len(r.get("comment") or "") > 140 else "")) or "(sin texto)",
            "link": link_reviews,
        }
        for r in nuevas if 0 < _stars(r) <= 4
    ]

    # Pendientes = FUENTE ÚNICA: stats["pendientes"] de fetch_reviews_full (5★ + sin reply +
    # createTime>=2025). MISMO conteo que la bandeja. El correo muestra 3 + "+N más" y un botón.
    sin_responder = stats.get("pendientes") or []
    pendientes = []
    for r in sin_responder[:3]:
        c = (r.get("comment") or "").strip()
        pendientes.append({
            "estrellas": 5,
            "reviewer": (r.get("reviewer") or "Cliente"),
            "extracto_corto": (c[:90] + "…") if len(c) > 90 else (c or "(sin texto)"),
        })

    return {
        "data_broken": False,
        "promedio_general": promedio,                       # 4.7 de la API (bug #2)
        "total_reviews": stats.get("total_reviews"),        # 1204 de la API (bug #3)
        "distribucion": stats.get("distribucion"),          # histórica 5★..1★ (bug #3)
        "scan_completo": stats.get("completo", True),       # manejo de fallo del escaneo
        "nuevas_semana": {"total": len(nuevas), "cinco": cinco, "cuatro": cuatro, "tres_o_menos": tres_menos},
        "cinco_sin_responder": cinco_sin_responder,
        "requieren_atencion": requieren,
        "pendientes": pendientes,
        "pendientes_total": len(sin_responder),             # = len(stats["pendientes"]) → FUENTE ÚNICA
        "borradores_ia_disponibles": False,
    }


_STRENGTH_BUCKET = {"EXCELLENT": "excelente", "GOOD": "bueno", "AVERAGE": "promedio", "POOR": "pobre"}
_STRENGTH_HUMAN = {"excelente": "Excelente", "bueno": "Bueno", "promedio": "Promedio", "pobre": "Pobre", "sin_datos": "Sin datos"}


def build_ads_quality_from_list(ads: list[dict[str, Any]], dias: int = 7) -> dict[str, Any]:
    """F-1: real ad quality from the /ads-report-style list (ad_strength, approval, CTR, conv)."""
    if not ads:
        return {"data_broken": True}
    distribucion = {"excelente": 0, "bueno": 0, "promedio": 0, "pobre": 0, "sin_datos": 0}
    rechazados = []
    for a in ads:
        bucket = _STRENGTH_BUCKET.get(str(a.get("ad_strength") or "").upper(), "sin_datos")
        distribucion[bucket] += 1
        if str(a.get("approval_status") or "").upper() not in {"APPROVED", ""}:
            rechazados.append({
                "titulo_corto": (a.get("headlines") or ["(sin título)"])[0],
                "campana": a.get("campaign_name"),
                "estado": a.get("approval_status"),
            })

    def _conv(a):
        return _num(a.get("conversiones", a.get("conversions")))

    # V-1: "los que más producen" solo anuncios con título real (los auto-generados sin
    # headline no se muestran individualmente).
    con_titulo = [a for a in ads if a.get("headlines")]
    horses = sorted(con_titulo, key=lambda a: (_conv(a), _num(a.get("clicks"))), reverse=True)[:4]
    caballos = [{
        "titulo_corto": (h.get("headlines") or ["(sin título)"])[0],
        "campana": h.get("campaign_name"),
        "calidad": _STRENGTH_HUMAN.get(_STRENGTH_BUCKET.get(str(h.get("ad_strength") or "").upper(), "sin_datos")),
        "ctr": f"{_num(h.get('ctr_pct', h.get('ctr'))):.1f}%",
        "clics": _int(h.get("clicks")),
        "impresiones": _int(h.get("impressions")),
        "conversiones": round(_conv(h), 1),
    } for h in horses]

    pobres = [a for a in ads if _int(a.get("impressions")) == 0]
    pobres_block = {
        "cantidad": len(pobres),
        "dias": dias,
        "titulos": [(a.get("headlines") or ["(sin título)"])[0] for a in pobres[:5]],
        "diagnostico_humano": (
            f"{len(pobres)} anuncios sin impresiones en {dias} días. Conviene revisar pujas/segmentación o rotar el texto."
            if pobres else "Sin anuncios apagados."
        ),
    }

    # V-1: anuncios que necesitan trabajo. Los auto-generados de campañas Smart
    # (sin headline asset) NO se listan uno por uno → se resumen. Los de búsqueda
    # se listan por nombre, DEDUPLICADOS por título (×N variantes). Jamás "(sin título)".
    smart_sin_impr = 0
    search_groups: dict[str, dict[str, Any]] = {}
    for a in ads:
        approved = str(a.get("approval_status") or "").upper() in {"APPROVED", ""}
        bucket = _STRENGTH_BUCKET.get(str(a.get("ad_strength") or "").upper(), "sin_datos")
        no_impr = _int(a.get("impressions")) == 0
        if approved and not no_impr and bucket != "pobre":
            continue  # no necesita trabajo
        headlines = a.get("headlines") or []
        is_auto = (not headlines) or classify_campaign(a.get("campaign_name") or "")["tipo"] == "smart"
        if is_auto:
            if no_impr:
                smart_sin_impr += 1
            continue
        razon = "rechazado" if not approved else ("sin impresiones" if no_impr else "calidad pobre")
        titulo = headlines[0]
        g = search_groups.setdefault(titulo, {"titulo_corto": titulo, "campana": a.get("campaign_name"),
                                              "razon": razon, "variantes": 0})
        g["variantes"] += 1

    necesitan_trabajo = {
        "smart_sin_impresiones": smart_sin_impr,
        "search": list(search_groups.values()),
    }

    return {
        "data_broken": False,
        "total_activos": len(ads),
        "todos_aprobados": not rechazados,
        "rechazados": rechazados,
        "distribucion": distribucion,
        "caballos_de_batalla": caballos,
        "pobres_sin_impresiones": pobres_block,
        "necesitan_trabajo": necesitan_trabajo,
    }


def build_ads_quality_summary(context: dict[str, Any] | None) -> dict[str, Any]:
    ads = (context or {}).get("ads_quality")
    if not ads or ads.get("data_broken"):
        return {"data_broken": True}
    return {"data_broken": False, **{k: v for k, v in ads.items() if k != "data_broken"}}


def build_seo_summary(context: dict[str, Any] | None) -> dict[str, Any]:
    seo = (context or {}).get("seo")
    if not seo or seo.get("data_broken"):
        return {"data_broken": True}
    return {"data_broken": False, **{k: v for k, v in seo.items() if k != "data_broken"}}


def build_search_console(context: dict[str, Any] | None) -> dict[str, Any]:
    sc = (context or {}).get("search_console")
    if not sc or sc.get("data_broken"):
        # A2: integration not wired yet — never show zeros as data.
        return {
            "data_broken": True,
            "impresiones": None, "clics": None, "ctr": None,
            "posicion_promedio": None, "top_queries": [],
        }
    return {"data_broken": False, **{k: v for k, v in sc.items() if k != "data_broken"}}


def build_search_terms_cards(
    items: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    marca_terms = [i for i in items if i.get("identity_axis") in {"marca_propia", "intencion_thai"}]
    marca_conv = sum(_num(i.get("conversions")) for i in marca_terms)
    pueden = sum(1 for i in items if i.get("identity_axis") in {"generico_util", "categoria_asiatica"})
    externos = sum(1 for i in items if i.get("identity_axis") == "restaurante_externo")
    # Confirmed waste = only negative_leak (red). Pending decisions = "por confirmar" (amber).
    confirmado = sum(_num(d.get("cost_mxn")) for d in decisions if d.get("decision_type") == "negative_leak")
    por_confirmar = sum(
        _num(d.get("cost_mxn")) for d in decisions
        if d.get("decision_type") in {"external_review", "tracking_review"}
    )
    return {
        "marca_protegida": {"terminos": len(marca_terms), "conversiones": round(marca_conv, 1)},
        "pueden_traer_clientes": pueden,
        "externos_revision_mensual": externos,
        "desperdicio_confirmado_mxn": round(confirmado, 2),
        "por_confirmar_mxn": round(por_confirmar, 2),
        "link": (context or {}).get("links", {}).get("negativos"),
    }
