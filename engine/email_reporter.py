"""
Email Reporter — Thai Thai Ads Agent (v2)
Genera y envía el reporte ejecutivo semanal via Gmail SMTP.

Bloques del reporte (spec completo):
  B0  — Header
  B1  — Resumen ejecutivo (2-3 párrafos dinámicos)
  B2  — KPIs del negocio (semana cerrada + MTD + proyección)
  B3  — Estado Google Ads (gasto, clics, conversiones, CPA)
  B4  — Acciones ejecutadas por el agente
  B5  — Propuestas para aprobación (✅ APROBAR / ❌ RECHAZAR)
  B6  — Riesgos y alertas
  B7  — Siguiente mejor acción
  B8  — GEO — cumplimiento geotargeting
  B9  — Smart Campaigns — hallazgos y temas
  B10 — Footer

Funciones públicas:
  build_html_report(...)        — genera el HTML completo del reporte semanal
  send_weekly_report(...)       — genera y envía por correo
  build_proposal_card(...)      — tarjeta standalone para correos de propuesta (sin cambios)
"""

import os
import smtplib
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from typing import Dict, List, Optional

from config.agent_config import (
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_TO,
    GMAIL_APP_PASSWORD,
)
from engine.weekly_supervisor import STATUS_ICON, STATUS_COLOR, STATUS_LABELS, STATUS_ORDER


# ── Configuración ─────────────────────────────────────────────────────────────

BASE_URL = os.getenv(
    "CLOUD_RUN_BASE_URL",
    "https://thai-thai-ads-agent-624172071613.us-central1.run.app",
)

_DIAS_SEMANA_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_MESES_ES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                   "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
_MESES_ES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

_ACTION_LABELS = {
    "block_keyword":    "Bloqueo de keyword",
    "adgroup_proposal": "Pausa de grupo de anuncios",
    "budget_action":    "Ajuste de presupuesto",
    "geo_action":       "Corrección de geotargeting",
    "alert_sent":       "Alerta enviada",
    "dry_run_alert":    "Alerta (modo observación)",
}

_RISK_LEVEL_BADGE = {
    0: ("#f0fdf4", "#15803d", "OBSERVACIÓN"),
    1: ("#eff6ff", "#1d4ed8", "EJECUCIÓN AUTO"),
    2: ("#fefce8", "#92400e", "PROPUESTA"),
    3: ("#fef2f2", "#dc2626", "BLOQUEADO"),
}


# ── Utilidades de formato ─────────────────────────────────────────────────────

def _fmt_mxn(value) -> str:
    """Formatea como $1,234.56 MXN."""
    try:
        return f"${float(value):,.2f} MXN"
    except (TypeError, ValueError):
        return "—"


def _fmt_mxn_short(value) -> str:
    """Formatea sin decimales: $1,234."""
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_date(d: date) -> str:
    return f"{d.day} {_MESES_ES_CORTO[d.month - 1]}"


def _fmt_date_long(d: date) -> str:
    return f"{d.day} {_MESES_ES_LARGO[d.month - 1]} {d.year}"


def _dias_semana(d: date) -> str:
    return _DIAS_SEMANA_ES[d.weekday()]


def _status_badge_html(status: str) -> str:
    cfg = {
        "sobre_objetivo":  ("#dcfce7", "#16a34a", "▲ Sobre objetivo"),
        "en_rango":        ("#fef9c3", "#ca8a04", "● En rango"),
        "bajo_equilibrio": ("#fee2e2", "#dc2626", "▼ Bajo equilibrio"),
    }
    bg, color, label = cfg.get(status, ("#f3f4f6", "#6b7280", status))
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;'
        f'letter-spacing:0.3px;">{label}</span>'
    )


def _delta_html(current: float, prev: float, is_mxn: bool = True) -> str:
    if prev == 0:
        return '<span style="font-size:11px;color:#9ca3af;">— sin datos ant.</span>'
    diff = current - prev
    pct = (diff / prev) * 100
    color = "#16a34a" if diff >= 0 else "#dc2626"
    icon = "▲" if diff >= 0 else "▼"
    val_str = _fmt_mxn_short(abs(diff)) if is_mxn else f"{abs(diff):,.0f}"
    return (
        f'<span style="font-size:11px;color:{color};font-weight:600;">'
        f'{icon} {val_str} ({pct:+.1f}%) vs sem. ant.</span>'
    )


def _kpi_card_html(
    label: str,
    value_html: str,
    delta_html: str,
    badge_html: str,
    meta_text: str,
) -> str:
    return f"""
    <td style="background:#f9fafb;border-radius:10px;padding:16px 18px;vertical-align:top;width:50%;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:#9ca3af;margin-bottom:6px;">{label}</div>
      <div style="font-size:24px;font-weight:700;color:#111827;margin-bottom:6px;">{value_html}</div>
      <div style="margin-bottom:8px;">{badge_html}</div>
      <div style="margin-bottom:4px;">{delta_html}</div>
      <div style="font-size:11px;color:#9ca3af;">{meta_text}</div>
    </td>"""


def _agent_count_row_html(status: str, count: int) -> str:
    if count == 0:
        return ""
    icon = STATUS_ICON.get(status, "•")
    label = STATUS_LABELS.get(status, status)
    color = STATUS_COLOR.get(status, "#6b7280")
    return (
        f'<tr>'
        f'<td style="padding:7px 12px;font-size:14px;color:#374151;">'
        f'<span style="color:{color};">{icon}</span> {label}</td>'
        f'<td style="padding:7px 12px;text-align:right;font-weight:700;'
        f'font-size:15px;color:{color};">{count}</td>'
        f'</tr>'
    )


def _agent_detail_item_html(row: dict) -> str:
    """Una línea de detalle del agente con borde de color izquierdo."""
    status = row.get("_status", "other")
    color = STATUS_COLOR.get(status, "#9ca3af")
    icon = STATUS_ICON.get(status, "•")
    auto_tag = ""
    if row.get("_auto_executed"):
        auto_tag = (
            ' <span style="background:#dcfce7;color:#15803d;font-size:10px;'
            'padding:1px 6px;border-radius:10px;font-weight:700;">AUTO</span>'
        )
    name = (
        row.get("keyword")
        or row.get("adgroup_name")
        or row.get("signal")
        or "—"
    )
    action_type = row.get("action_type", "")
    action_label = _ACTION_LABELS.get(action_type, action_type)
    action_prefix = (
        f'<span style="font-size:10px;color:#9ca3af;margin-right:4px;">{action_label}</span>'
        if action_label else ""
    )
    campaign = row.get("campaign_name") or ""
    cost = row.get("cost_mxn")
    cost_str = f" · {_fmt_mxn_short(cost)} MXN" if cost else ""
    signal = row.get("signal") or ""
    signal_tag = (
        f' <span style="background:#e0f2fe;color:#0369a1;font-size:10px;'
        f'padding:1px 6px;border-radius:10px;">{signal}</span>'
        if signal else ""
    )
    return (
        f'<div style="border-left:3px solid {color};padding:8px 12px;'
        f'margin-bottom:6px;background:#fafafa;border-radius:0 6px 6px 0;">'
        f'<span style="color:{color};font-size:13px;">{icon}</span>'
        f'{action_prefix}'
        f'<span style="font-size:13px;font-weight:600;color:#111827;margin-left:2px;">{name}</span>'
        f'{signal_tag}{auto_tag}'
        f'<span style="font-size:12px;color:#6b7280;margin-left:6px;">{campaign}{cost_str}</span>'
        f'</div>'
    )


# ── Bloque Smart Campaigns ────────────────────────────────────────────────────

def _build_smart_block_html(smart_data: dict | None) -> str:
    """Construye el bloque HTML de Smart Campaigns para el reporte semanal."""
    if not smart_data or smart_data.get("error"):
        return ""

    campaigns = smart_data.get("campaigns", [])
    if not campaigns:
        return ""

    summary = smart_data.get("summary", {})
    total_issues   = summary.get("issues_total", 0)
    total_critical = summary.get("issues_critical", 0)
    proposals = smart_data.get("proposals", [])

    if total_issues == 0:
        status_badge = '<span style="color:#15803d;font-weight:600;">✅ Sin hallazgos</span>'
    elif total_critical > 0:
        status_badge = f'<span style="color:#dc2626;font-weight:600;">⚠ {total_issues} hallazgo(s) — {total_critical} crítico(s)</span>'
    else:
        status_badge = f'<span style="color:#d97706;font-weight:600;">◉ {total_issues} hallazgo(s)</span>'

    rows_html = ""
    for c in campaigns:
        issues = c.get("issues", [])
        themes_bad   = c.get("keyword_themes_bad", 0)
        themes_total = c.get("keyword_themes_total", 0)
        final_url    = c.get("final_url", "")
        cname        = c.get("campaign_name", "")
        m    = c.get("metrics_7d", {})
        cost = m.get("cost_mxn", 0)
        conv = m.get("conversions", 0)
        cpa  = m.get("cpa_mxn")

        signals = [i.get("signal", "") for i in issues]
        signal_tags = " ".join(
            f'<span style="background:#fee2e2;color:#b91c1c;font-size:10px;'
            f'padding:1px 5px;border-radius:8px;margin-right:2px;">{s}</span>'
            for s in signals if s
        )
        if not signals:
            signal_tags = '<span style="color:#15803d;font-size:11px;">✓ OK</span>'

        url_cell = (
            f'<span style="color:#dc2626;font-size:11px;">vacía</span>'
            if not final_url else
            f'<span style="font-size:11px;color:#374151;">{final_url[:35]}{"…" if len(final_url) > 35 else ""}</span>'
        )

        cpa_str  = f"${cpa:,.0f}" if cpa else ("$0" if conv == 0 and cost > 0 else "—")
        conv_str = str(int(conv)) if conv else "0"

        rows_html += f"""
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:7px 6px;font-size:12px;color:#111827;white-space:nowrap;">{cname}</td>
          <td style="padding:7px 6px;font-size:11px;color:#374151;text-align:center;">${cost:,.0f}</td>
          <td style="padding:7px 6px;font-size:11px;color:#374151;text-align:center;">{conv_str}</td>
          <td style="padding:7px 6px;font-size:11px;color:#374151;text-align:center;">{cpa_str}</td>
          <td style="padding:7px 6px;font-size:11px;color:#6b7280;text-align:center;">{themes_bad}/{themes_total}</td>
          <td style="padding:7px 6px;">{url_cell}</td>
          <td style="padding:7px 6px;">{signal_tags}</td>
        </tr>"""

    proposals_html = ""
    if proposals:
        items = ""
        for p in proposals:
            themes = p.get("themes_to_remove", [])
            themes_str = ", ".join(f'"{t}"' for t in themes[:5])
            if len(themes) > 5:
                themes_str += f" +{len(themes)-5} más"
            items += (
                f'<li style="font-size:12px;color:#374151;margin-bottom:4px;">'
                f'<strong>{p.get("campaign_name","")}</strong> — '
                f'Eliminar {len(themes)} tema(s) irrelevante(s): {themes_str}</li>'
            )
        proposals_html = f"""
    <div style="margin-top:10px;padding:10px 14px;background:#fff8e1;border-left:3px solid #f59e0b;border-radius:0 6px 6px 0;">
      <div style="font-size:11px;font-weight:700;color:#92400e;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.4px;">
        ⏳ {len(proposals)} propuesta(s) pendiente(s) de revisión manual
      </div>
      <ul style="margin:0;padding-left:16px;">{items}</ul>
    </div>"""

    return f"""
    <h2 style="font-size:15px;font-weight:700;color:#111827;margin:28px 0 4px;padding-bottom:8px;border-bottom:2px solid #f3f4f6;">
      ⚡ Smart Campaigns · estado y hallazgos
      <span style="font-size:12px;font-weight:400;margin-left:8px;">{status_badge}</span>
    </h2>

    <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0 8px;">
      <thead>
        <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb;">
          <th style="padding:6px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Campaña</th>
          <th style="padding:6px 6px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;">Gasto 7d</th>
          <th style="padding:6px 6px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;">Conv.</th>
          <th style="padding:6px 6px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;">CPA</th>
          <th style="padding:6px 6px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;">Temas malos</th>
          <th style="padding:6px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Landing URL</th>
          <th style="padding:6px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Señales</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
    {proposals_html}"""


# ── Propuesta standalone (para correos de propuesta individuales) ─────────────

def _encode_proposal(proposal: Dict) -> str:
    data = {
        "id": proposal.get("decision_id", ""),
        "type": proposal.get("type", ""),
        "campaign_id": str(proposal.get("target", {}).get("campaign_id", "")),
        "campaign_name": proposal.get("target", {}).get("campaign_name", ""),
    }
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _priority_badge(priority: int) -> str:
    if priority == 1:
        return '<span style="background:#dc2626;color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">URGENTE</span>'
    elif priority == 2:
        return '<span style="background:#d97706;color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">ALTA</span>'
    else:
        return '<span style="background:#2563eb;color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">MEDIA</span>'


def build_proposal_card(proposal: Dict, idx: int, agent_proposals: List[Dict] = None) -> str:
    """Genera una tarjeta de propuesta con links de aprobación/rechazo (correos standalone)."""
    priority = proposal.get("priority", idx + 1)
    action_type = proposal.get("action_type", "")

    matched = None
    if agent_proposals:
        for ap in agent_proposals:
            if ap.get("type") == "scale_campaign" and proposal.get("action_type") in ("budget_change", "keyword"):
                matched = ap
                break

    if matched:
        encoded = _encode_proposal(matched)
        approve_link = f"{BASE_URL}/approve?d={encoded}&action=approve"
        reject_link  = f"{BASE_URL}/approve?d={encoded}&action=reject"
    else:
        pid = proposal.get("id", f"prop_{idx}")
        approve_link = f"{BASE_URL}/approve?proposal_id={pid}&action=approve"
        reject_link  = f"{BASE_URL}/approve?proposal_id={pid}&action=reject"

    return f"""
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
        {_priority_badge(priority)}
        <span style="font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">{action_type}</span>
      </div>
      <h3 style="margin:0 0 8px 0;font-size:16px;color:#111827;">{proposal.get('title','')}</h3>
      <p style="margin:0 0 12px 0;font-size:14px;color:#374151;line-height:1.6;">{proposal.get('description','')}</p>
      <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;margin-bottom:12px;border-radius:0 4px 4px 0;">
        <p style="margin:0;font-size:13px;color:#92400e;"><strong>Impacto esperado:</strong> {proposal.get('expected_impact','')}</p>
      </div>
      <div style="background:#fee2e2;border-left:4px solid #dc2626;padding:10px 14px;margin-bottom:16px;border-radius:0 4px 4px 0;">
        <p style="margin:0;font-size:13px;color:#991b1b;"><strong>Riesgo si no se actúa:</strong> {proposal.get('risk_if_ignored','')}</p>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <a href="{approve_link}"
           style="display:inline-block;background:#16a34a;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;">
          ✅ Aprobar y ejecutar
        </a>
        <a href="{reject_link}"
           style="display:inline-block;background:#f3f4f6;color:#374151;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;border:1px solid #d1d5db;">
          ❌ Rechazar
        </a>
      </div>
    </div>
    """


# ── Helpers de estructura ─────────────────────────────────────────────────────

def _section_h2(title: str, subtitle: str = "") -> str:
    subtitle_html = (
        f'<span style="font-size:12px;font-weight:400;color:#9ca3af;margin-left:8px;">{subtitle}</span>'
        if subtitle else ""
    )
    return (
        f'<h2 style="font-size:15px;font-weight:700;color:#111827;margin:28px 0 4px;'
        f'padding-bottom:8px;border-bottom:2px solid #f3f4f6;">'
        f'{title}{subtitle_html}</h2>'
    )


# ── B1: Resumen ejecutivo ─────────────────────────────────────────────────────

def _build_executive_summary_html(
    week_data: dict,
    prev_week_data: dict,
    supervisor_data: dict,
    geo_data: dict | None,
) -> str:
    """Genera el bloque de resumen ejecutivo de 2-3 párrafos."""
    # Situación del negocio
    v_sem = week_data.get("ventas_netas", 0.0)
    c_sem = week_data.get("comensales", 0)
    pv    = prev_week_data.get("ventas_netas", 0.0)
    v_status = week_data.get("ventas_status", "")
    c_status = week_data.get("comensales_status", "")

    _status_text = {
        "sobre_objetivo":  "por encima del objetivo",
        "en_rango":        "dentro del rango esperado",
        "bajo_equilibrio": "por debajo del punto de equilibrio",
    }
    v_status_text = _status_text.get(v_status, "")
    c_status_text = _status_text.get(c_status, "")

    v_diff_pct = ""
    if pv and pv > 0:
        pct = ((v_sem - pv) / pv) * 100
        direction = "arriba" if pct >= 0 else "abajo"
        v_diff_pct = f", un {abs(pct):.1f}% {direction} respecto a la semana anterior"

    p1_parts = [
        f"Esta semana el restaurante registró <strong>{_fmt_mxn_short(v_sem)} MXN</strong> en ventas netas "
        f"y <strong>{c_sem:,} comensales</strong>{v_diff_pct}."
    ]
    if v_status_text:
        p1_parts.append(f"Las ventas están {v_status_text}.")
    if c_status_text and c_status != v_status:
        p1_parts.append(f"Los comensales están {c_status_text}.")
    p1 = " ".join(p1_parts)

    # Actividad del agente
    counts        = supervisor_data.get("counts", {})
    total         = supervisor_data.get("total_relevant", 0)
    n_executed    = counts.get("executed", 0)
    n_pending     = counts.get("pending", 0)
    n_alerts      = counts.get("alert", 0)
    n_rejected    = counts.get("rejected", 0)
    n_blocked     = counts.get("approved_blocked", 0)
    auto_executed = len(supervisor_data.get("auto_executed", []))

    agent_parts = [f"El agente monitoreó las campañas durante los últimos 8 días y registró <strong>{total} acción(es)</strong> en total."]
    if auto_executed:
        agent_parts.append(f"Ejecutó <strong>{auto_executed} cambio(s) automáticamente</strong>.")
    if n_pending:
        agent_parts.append(f"Tiene <strong>{n_pending} propuesta(s) pendiente(s)</strong> de aprobación.")
    if n_alerts:
        agent_parts.append(f"Emitió <strong>{n_alerts} alerta(s)</strong>.")
    if n_blocked:
        agent_parts.append(f"<strong>{n_blocked} acción(es)</strong> quedaron bloqueadas por las guardas de seguridad.")
    if not total:
        agent_parts = ["El agente operó en modo observación esta semana. No se registraron acciones ni propuestas."]
    p2 = " ".join(agent_parts)

    # Urgencias (condicional)
    p3 = ""
    urgencies = []
    if n_pending:
        urgencies.append(f"{n_pending} propuesta(s) requiere(n) tu aprobación")
    if geo_data and geo_data.get("issues"):
        n_geo = len(geo_data["issues"])
        urgencies.append(f"{n_geo} campaña(s) con problema de geotargeting")
    if n_blocked:
        urgencies.append(f"{n_blocked} acción(es) bloqueada(s) a revisar")
    if urgencies:
        p3 = "<strong>Requiere atención:</strong> " + " · ".join(urgencies) + "."

    p3_html = f'<p style="margin:10px 0 0;font-size:13px;color:#374151;line-height:1.6;">{p3}</p>' if p3 else ""

    return f"""
    {_section_h2("📋 Resumen ejecutivo")}
    <div style="background:#f9fafb;border-radius:8px;padding:16px 20px;margin:12px 0 0;">
      <p style="margin:0 0 10px;font-size:13px;color:#374151;line-height:1.7;">{p1}</p>
      <p style="margin:0;font-size:13px;color:#374151;line-height:1.7;">{p2}</p>
      {p3_html}
    </div>"""


# ── B3: Estado Google Ads ─────────────────────────────────────────────────────

def _build_ads_status_html(ads_data: dict | None) -> str:
    """Muestra las métricas de Google Ads de la semana. Placeholder si ads_data es None."""
    if not ads_data:
        return f"""
    {_section_h2("📊 Google Ads · métricas de la semana")}
    <div style="background:#f9fafb;border-radius:8px;padding:16px 20px;margin:12px 0 0;border:1px dashed #d1d5db;text-align:center;">
      <p style="font-size:13px;color:#9ca3af;margin:0;">
        Métricas de Google Ads no disponibles en este reporte.<br>
        <span style="font-size:11px;">Se incluirán automáticamente cuando <code>ads_data</code> esté conectado al endpoint.</span>
      </p>
    </div>"""

    cost  = ads_data.get("cost_mxn", 0)
    clicks = ads_data.get("clicks", 0)
    impr  = ads_data.get("impressions", 0)
    conv  = ads_data.get("conversions", 0)
    cpa   = ads_data.get("cpa_mxn")
    ctr   = ads_data.get("ctr_pct")

    # CPA semáforo
    if cpa is None:
        cpa_color = "#6b7280"
        cpa_str   = "—"
    elif cpa <= 45:
        cpa_color = "#16a34a"
        cpa_str   = f"${cpa:,.0f} MXN"
    elif cpa <= 80:
        cpa_color = "#d97706"
        cpa_str   = f"${cpa:,.0f} MXN"
    else:
        cpa_color = "#dc2626"
        cpa_str   = f"${cpa:,.0f} MXN"

    ctr_str = f"{ctr:.2f}%" if ctr is not None else "—"

    return f"""
    {_section_h2("📊 Google Ads · métricas de la semana")}
    <table style="width:100%;border-collapse:collapse;margin:12px 0 0;">
      <tr>
        <td style="padding:0 6px 0 0;width:25%;">
          <div style="background:#f9fafb;border-radius:8px;padding:14px 16px;text-align:center;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:#9ca3af;margin-bottom:4px;">Gasto</div>
            <div style="font-size:20px;font-weight:700;color:#111827;">{_fmt_mxn_short(cost)}</div>
          </div>
        </td>
        <td style="padding:0 6px;width:25%;">
          <div style="background:#f9fafb;border-radius:8px;padding:14px 16px;text-align:center;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:#9ca3af;margin-bottom:4px;">Conversiones</div>
            <div style="font-size:20px;font-weight:700;color:#111827;">{conv:,.0f}</div>
          </div>
        </td>
        <td style="padding:0 6px;width:25%;">
          <div style="background:#f9fafb;border-radius:8px;padding:14px 16px;text-align:center;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:#9ca3af;margin-bottom:4px;">CPA</div>
            <div style="font-size:20px;font-weight:700;color:{cpa_color};">{cpa_str}</div>
          </div>
        </td>
        <td style="padding:0 0 0 6px;width:25%;">
          <div style="background:#f9fafb;border-radius:8px;padding:14px 16px;text-align:center;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:#9ca3af;margin-bottom:4px;">CTR</div>
            <div style="font-size:20px;font-weight:700;color:#111827;">{ctr_str}</div>
          </div>
        </td>
      </tr>
    </table>
    <p style="font-size:11px;color:#9ca3af;margin:8px 0 0;padding-left:2px;">
      Clics: {clicks:,} · Impresiones: {impr:,}
    </p>"""


# ── B4: Acciones ejecutadas ───────────────────────────────────────────────────

def _build_executed_actions_html(supervisor_data: dict) -> str:
    """Lista de acciones ejecutadas automáticamente por el agente."""
    by_status    = supervisor_data.get("by_status", {})
    executed     = by_status.get("executed", [])
    auto_executed = supervisor_data.get("auto_executed", [])
    approved_reg  = by_status.get("approved_registered", [])
    approved_blk  = by_status.get("approved_blocked", [])

    # Todas las ejecuciones (auto + aprobadas)
    all_executed = executed + approved_reg

    if not all_executed and not approved_blk:
        return f"""
    {_section_h2("✅ Acciones ejecutadas")}
    <p style="font-size:13px;color:#9ca3af;margin:8px 0 0;padding:12px 0 4px;">
      El agente no ejecutó cambios esta semana. Operó en modo observación o propuesta.
    </p>"""

    items_html = ""
    for row in all_executed:
        name    = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
        atype   = _ACTION_LABELS.get(row.get("action_type", ""), row.get("action_type", ""))
        campaign = row.get("campaign_name") or ""
        cost    = row.get("cost_mxn")
        cost_str = f" · {_fmt_mxn_short(cost)} MXN" if cost else ""
        is_auto  = row.get("_auto_executed", False)
        auto_tag = (
            '<span style="background:#dcfce7;color:#15803d;font-size:10px;'
            'padding:1px 6px;border-radius:10px;font-weight:700;margin-left:6px;">AUTO</span>'
            if is_auto else
            '<span style="background:#dbeafe;color:#1d4ed8;font-size:10px;'
            'padding:1px 6px;border-radius:10px;margin-left:6px;">Aprobado</span>'
        )
        items_html += (
            f'<div style="border-left:3px solid #16a34a;padding:8px 12px;'
            f'margin-bottom:6px;background:#f0fdf4;border-radius:0 6px 6px 0;">'
            f'<span style="font-size:13px;font-weight:600;color:#111827;">{name}</span>'
            f'{auto_tag}'
            f'<span style="font-size:11px;color:#6b7280;margin-left:6px;">{atype}'
            f'{" · " + campaign if campaign else ""}{cost_str}</span>'
            f'</div>'
        )

    blocked_html = ""
    if approved_blk:
        b_items = ""
        for row in approved_blk:
            name = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
            atype = _ACTION_LABELS.get(row.get("action_type", ""), row.get("action_type", ""))
            b_items += (
                f'<li style="font-size:12px;color:#374151;margin-bottom:4px;">'
                f'<strong>{name}</strong> — {atype}</li>'
            )
        blocked_html = f"""
    <div style="margin-top:12px;padding:10px 14px;background:#fdf4ff;border-left:3px solid #7c3aed;border-radius:0 6px 6px 0;">
      <div style="font-size:11px;font-weight:700;color:#6d28d9;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.4px;">
        🔒 Aprobadas pero bloqueadas por guarda de seguridad ({len(approved_blk)})
      </div>
      <ul style="margin:0;padding-left:16px;">{b_items}</ul>
    </div>"""

    return f"""
    {_section_h2("✅ Acciones ejecutadas", f"{len(all_executed)} cambio(s) aplicado(s)")}
    <div style="margin:12px 0 0;">
      {items_html}
      {blocked_html}
    </div>"""


# ── B5: Propuestas para aprobación ────────────────────────────────────────────

def _build_weekly_proposal_card(row: dict, idx: int) -> str:
    """Tarjeta de propuesta dentro del reporte semanal, con botones de aprobación directos."""
    token = row.get("approval_token", "")
    name  = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
    atype = _ACTION_LABELS.get(row.get("action_type", ""), row.get("action_type", "propuesta"))
    campaign = row.get("campaign_name") or "—"
    cost  = row.get("cost_mxn")
    cost_str = _fmt_mxn_short(cost) + " MXN" if cost else "N/D"
    reason = row.get("reason") or "—"
    risk  = int(row.get("risk_level") or 0)

    risk_bg, risk_color, risk_label = _RISK_LEVEL_BADGE.get(risk, ("#f3f4f6", "#6b7280", str(risk)))

    if token:
        approve_url = f"{BASE_URL}/approve?d={token}&action=approve"
        reject_url  = f"{BASE_URL}/approve?d={token}&action=reject"
        btn_approve = (
            f'<a href="{approve_url}" '
            f'style="display:inline-block;background:#16a34a;color:white;padding:10px 22px;'
            f'border-radius:6px;text-decoration:none;font-size:13px;font-weight:700;'
            f'letter-spacing:0.2px;">✅ APROBAR</a>'
        )
        btn_reject = (
            f'<a href="{reject_url}" '
            f'style="display:inline-block;background:#f3f4f6;color:#374151;padding:10px 22px;'
            f'border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;'
            f'border:1px solid #d1d5db;">❌ RECHAZAR</a>'
        )
    else:
        btn_approve = (
            '<span style="display:inline-block;background:#9ca3af;color:white;padding:10px 22px;'
            'border-radius:6px;font-size:13px;font-weight:700;opacity:0.5;">✅ APROBAR</span>'
        )
        btn_reject = (
            '<span style="display:inline-block;background:#f3f4f6;color:#9ca3af;padding:10px 22px;'
            'border-radius:6px;font-size:13px;border:1px solid #e5e7eb;opacity:0.5;">❌ RECHAZAR</span>'
        )

    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;margin-bottom:16px;overflow:hidden;">
      <!-- Cabecera de propuesta -->
      <div style="background:#fffbeb;padding:12px 20px;border-bottom:1px solid #fde68a;">
        <span style="background:{risk_bg};color:{risk_color};font-size:10px;font-weight:700;
                     padding:2px 8px;border-radius:4px;text-transform:uppercase;
                     letter-spacing:0.3px;margin-right:8px;">{risk_label}</span>
        <span style="font-size:12px;color:#6b7280;">{atype}</span>
        <span style="float:right;font-size:11px;color:#9ca3af;">#{idx + 1}</span>
      </div>
      <!-- Cuerpo -->
      <div style="padding:16px 20px;">
        <div style="font-size:15px;font-weight:700;color:#111827;margin-bottom:10px;">{name}</div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <tr>
            <td style="padding:4px 0;color:#9ca3af;width:120px;">Campaña</td>
            <td style="padding:4px 0;color:#374151;">{campaign}</td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#9ca3af;">Gasto involucrado</td>
            <td style="padding:4px 0;color:#374151;font-weight:600;">{cost_str}</td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#9ca3af;vertical-align:top;">Motivo</td>
            <td style="padding:4px 0;color:#374151;line-height:1.5;">{reason}</td>
          </tr>
        </table>
      </div>
      <!-- Botones -->
      <div style="padding:14px 20px;background:#f9fafb;border-top:1px solid #f3f4f6;">
        <table style="border-collapse:collapse;">
          <tr>
            <td style="padding-right:10px;">{btn_approve}</td>
            <td>{btn_reject}</td>
          </tr>
        </table>
      </div>
    </div>"""


def _build_pending_proposals_html(supervisor_data: dict) -> str:
    """Bloque de propuestas pendientes de aprobación con botones de acción directa."""
    pending = supervisor_data.get("by_status", {}).get("pending", [])

    if not pending:
        return f"""
    {_section_h2("⏳ Propuestas para aprobación")}
    <div style="background:#f9fafb;border-radius:8px;padding:14px 20px;margin:12px 0 0;text-align:center;">
      <p style="font-size:13px;color:#9ca3af;margin:0;">✓ Sin propuestas pendientes esta semana.</p>
    </div>"""

    # Ordenar por costo desc, mostrar máx. 3
    sorted_pending = sorted(
        pending,
        key=lambda r: float(r.get("cost_mxn") or 0),
        reverse=True,
    )[:3]

    cards_html = "".join(
        _build_weekly_proposal_card(row, i)
        for i, row in enumerate(sorted_pending)
    )

    overflow_html = ""
    if len(pending) > 3:
        overflow_html = (
            f'<p style="font-size:12px;color:#6b7280;margin:0 0 8px;">'
            f'+ {len(pending) - 3} propuesta(s) adicional(es) — revisa el correo de propuesta original.</p>'
        )

    return f"""
    {_section_h2("⏳ Propuestas para aprobación", f"{len(pending)} pendiente(s)")}
    <div style="margin:12px 0 0;">
      <p style="font-size:12px;color:#6b7280;margin:0 0 12px;">
        Usa los botones de cada propuesta para aprobar o rechazar directamente desde este correo.
        La acción se registra automáticamente.
      </p>
      {cards_html}
      {overflow_html}
    </div>"""


# ── B6: Riesgos y alertas ─────────────────────────────────────────────────────

def _build_risks_alerts_html(supervisor_data: dict) -> str:
    """Bloque de riesgos, alertas y elementos que requieren revisión."""
    by_status  = supervisor_data.get("by_status", {})
    alerts     = by_status.get("alert", [])
    rejected   = by_status.get("rejected", [])
    expired    = by_status.get("expired", [])
    blocked    = by_status.get("approved_blocked", [])

    if not any([alerts, rejected, expired, blocked]):
        return f"""
    {_section_h2("🔔 Riesgos y alertas")}
    <div style="background:#f0fdf4;border-radius:8px;padding:14px 20px;margin:12px 0 0;">
      <p style="font-size:13px;color:#15803d;margin:0;font-weight:600;">
        ✅ Sin alertas ni riesgos esta semana. Operación dentro de parámetros normales.
      </p>
    </div>"""

    sections_html = ""

    if alerts:
        items = ""
        for row in alerts:
            name    = row.get("signal") or row.get("keyword") or row.get("adgroup_name") or "—"
            atype   = _ACTION_LABELS.get(row.get("action_type", ""), "alerta")
            date_str = (row.get("created_at") or "")[:10]
            items += (
                f'<li style="font-size:12px;color:#374151;margin-bottom:4px;">'
                f'<strong>{name}</strong> — {atype}'
                f'{" · " + date_str if date_str else ""}</li>'
            )
        sections_html += f"""
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;font-weight:700;color:#ea580c;margin-bottom:6px;
                    text-transform:uppercase;letter-spacing:0.4px;">
          🔔 Alertas enviadas ({len(alerts)})
        </div>
        <ul style="margin:0;padding-left:16px;">{items}</ul>
      </div>"""

    if blocked:
        items = ""
        for row in blocked:
            name  = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
            atype = _ACTION_LABELS.get(row.get("action_type", ""), "acción")
            items += (
                f'<li style="font-size:12px;color:#374151;margin-bottom:4px;">'
                f'<strong>{name}</strong> — {atype} (aprobado pero bloqueado por guarda)</li>'
            )
        sections_html += f"""
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;font-weight:700;color:#7c3aed;margin-bottom:6px;
                    text-transform:uppercase;letter-spacing:0.4px;">
          🔒 Bloqueados por seguridad ({len(blocked)})
        </div>
        <ul style="margin:0;padding-left:16px;">{items}</ul>
      </div>"""

    if expired:
        items = ""
        for row in expired:
            name = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
            items += f'<li style="font-size:12px;color:#6b7280;margin-bottom:2px;">{name}</li>'
        sections_html += f"""
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;font-weight:700;color:#6b7280;margin-bottom:6px;
                    text-transform:uppercase;letter-spacing:0.4px;">
          ⏰ Propuestas expiradas ({len(expired)})
        </div>
        <ul style="margin:0;padding-left:16px;">{items}</ul>
      </div>"""

    if rejected:
        items = ""
        for row in rejected:
            name = row.get("keyword") or row.get("adgroup_name") or row.get("signal") or "—"
            atype = _ACTION_LABELS.get(row.get("action_type", ""), "propuesta")
            items += (
                f'<li style="font-size:12px;color:#374151;margin-bottom:2px;">'
                f'{name} — {atype}</li>'
            )
        sections_html += f"""
      <div>
        <div style="font-size:11px;font-weight:700;color:#dc2626;margin-bottom:6px;
                    text-transform:uppercase;letter-spacing:0.4px;">
          ❌ Rechazadas por supervisor ({len(rejected)})
        </div>
        <ul style="margin:0;padding-left:16px;">{items}</ul>
      </div>"""

    return f"""
    {_section_h2("🔔 Riesgos y alertas")}
    <div style="background:#fff8f0;border-radius:8px;padding:16px 20px;margin:12px 0 0;border-left:3px solid #ea580c;">
      {sections_html}
    </div>"""


# ── B7: Siguiente mejor acción ────────────────────────────────────────────────

def _build_next_action_html(next_action: str) -> str:
    return f"""
    {_section_h2("⚡ Siguiente mejor acción")}
    <div style="background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #f59e0b;
                border-radius:6px;padding:14px 18px;margin:12px 0 0;">
      <p style="margin:0;font-size:14px;color:#78350f;line-height:1.7;">{next_action}</p>
    </div>"""


# ── B8: GEO ───────────────────────────────────────────────────────────────────

def _build_geo_block_html(geo_data: dict) -> str:
    """Construye el bloque HTML del módulo GEO para el reporte semanal."""
    if not geo_data:
        return ""

    all_entries = geo_data.get("correct", []) + geo_data.get("issues", [])
    if not all_entries:
        return ""

    all_entries.sort(key=lambda e: (0 if e.get("compliant") else 1, e.get("campaign_name", "")))

    _SIGNAL_LABEL = {
        "OK":                       ("✅", "#15803d", "Correcto"),
        "GEO0":                     ("⚠️", "#b45309", "Sin geo activo"),
        "GEO1":                     ("❌", "#dc2626", "Ubicación incorrecta"),
        "WRONG_TYPE_LOC_FOR_PROX":  ("❌", "#dc2626", "Tipo incorrecto (loc→prox)"),
        "WRONG_TYPE_PROX_FOR_LOC":  ("❌", "#dc2626", "Tipo incorrecto (prox→loc)"),
        "PROX_RADIUS_EXCEEDED":     ("⚠️", "#b45309", "Radio excedido"),
        "PROX_RADIUS_INSUFFICIENT": ("⚠️", "#b45309", "Radio insuficiente"),
        "POLICY_UNDEFINED":         ("⚠️", "#b45309", "Sin política definida"),
    }

    _FOS_LABELS = {
        "verified":              "✓ Verificado en UI",
        "unverified":            "Sin verificar en UI",
        "ui_validation_pending": "Verificación UI pendiente",
        "geo_issue":             "⚠ Problema GEO activo",
        "stale":                 "⚠ Validación desactualizada",
    }

    rows_html = ""
    for e in all_entries:
        signal = e.get("signal", "")
        name   = e.get("campaign_name", "")[:32]
        obj    = e.get("objective_type", "—")
        fos    = e.get("final_operational_state", "")
        reason = e.get("reason", "")
        icon, color, label = _SIGNAL_LABEL.get(signal, ("❓", "#6b7280", signal))
        fos_display = _FOS_LABELS.get(fos, fos)
        reason_cell = (
            f'<span style="font-size:10px;color:#9ca3af;display:block;">{reason[:60]}{"…" if len(reason) > 60 else ""}</span>'
            if reason else ""
        )

        rows_html += f"""
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:8px 6px;font-size:12px;color:#111827;white-space:nowrap;">{name}</td>
          <td style="padding:8px 6px;font-size:11px;color:#6b7280;">{obj}</td>
          <td style="padding:8px 6px;font-size:12px;color:{color};font-weight:600;">{icon} {label}{reason_cell}</td>
          <td style="padding:8px 6px;font-size:11px;color:#6b7280;">{fos_display}</td>
        </tr>"""

    n_ok  = len(geo_data.get("correct", []))
    n_bad = len(geo_data.get("issues", []))
    summary_color = "#15803d" if n_bad == 0 else ("#b45309" if n_bad <= 1 else "#dc2626")
    summary_icon  = "✅" if n_bad == 0 else "⚠️"

    return f"""
    {_section_h2(
        "🗺️ Geotargeting · estado por campaña",
        f"{summary_icon} {n_ok} correcta(s) · {n_bad} con problema(s)"
    )}

    <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0 20px;">
      <thead>
        <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb;">
          <th style="padding:7px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Campaña</th>
          <th style="padding:7px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Objetivo</th>
          <th style="padding:7px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Estado GEO</th>
          <th style="padding:7px 6px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;">Operacional</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>"""


# ── Reporte ejecutivo semanal — función principal ─────────────────────────────

def build_html_report(
    week_data: dict,
    prev_week_data: dict,
    mtd_data: dict,
    supervisor_data: dict,
    next_action: str,
    geo_data: dict | None = None,
    smart_data: dict | None = None,
    ads_data: dict | None = None,
) -> str:
    """
    Genera el HTML del reporte ejecutivo semanal completo (9 bloques).

    Args:
      week_data       — fetch_week_business_data(weeks_ago=1)
      prev_week_data  — fetch_week_business_data(weeks_ago=2)
      mtd_data        — fetch_mtd_business_data()
      supervisor_data — build_supervisor_data(rows)  [rows incluyen approval_token]
      next_action     — get_next_best_action(supervisor_data)
      geo_data        — detect_geo_issues_by_policy() (opcional)
      smart_data      — audit_smart_campaigns() (opcional)
      ads_data        — métricas Google Ads de la semana (opcional)
    """
    now = datetime.now()
    gen_date = now.strftime("%d %b %Y, %H:%M hrs")

    # ── Encabezado de semana cerrada ─────────────────────────────────────────
    ws = week_data.get("week_start")
    we = week_data.get("week_end")
    if ws and we:
        if ws.month == we.month:
            week_label = (
                f"{_dias_semana(ws)} {ws.day}–{_dias_semana(we)} {we.day} "
                f"{_MESES_ES_LARGO[ws.month-1]} {ws.year}"
            )
            week_title = f"{ws.day}–{we.day} {_MESES_ES_LARGO[ws.month-1]} {ws.year}"
        else:
            week_label = f"{_fmt_date(ws)} – {_fmt_date(we)} {we.year}"
            week_title = week_label
    else:
        week_title = "Semana cerrada"
        week_label = week_title

    # ── B1: Resumen ejecutivo ─────────────────────────────────────────────────
    executive_summary_html = _build_executive_summary_html(
        week_data, prev_week_data, supervisor_data, geo_data
    )

    # ── B2: KPIs Negocio ─────────────────────────────────────────────────────
    v_sem = week_data.get("ventas_netas", 0.0)
    c_sem = week_data.get("comensales", 0)
    pv    = prev_week_data.get("ventas_netas", 0.0)
    pc    = prev_week_data.get("comensales", 0)

    obj_v_sem = week_data.get("obj_ventas_semana", 0)
    eq_v_sem  = week_data.get("eq_ventas_semana", 0)
    obj_c_sem = week_data.get("obj_comensales_semana", 0)
    eq_c_sem  = week_data.get("eq_comensales_semana", 0)

    kpi_ventas_sem = _kpi_card_html(
        label="Ventas Netas",
        value_html=_fmt_mxn_short(v_sem),
        delta_html=_delta_html(v_sem, pv, is_mxn=True),
        badge_html=_status_badge_html(week_data.get("ventas_status", "")),
        meta_text=f"Obj. semanal: {_fmt_mxn_short(obj_v_sem)} · Eq.: {_fmt_mxn_short(eq_v_sem)}",
    )
    kpi_comensales_sem = _kpi_card_html(
        label="Comensales",
        value_html=f"{c_sem:,}",
        delta_html=_delta_html(float(c_sem), float(pc), is_mxn=False),
        badge_html=_status_badge_html(week_data.get("comensales_status", "")),
        meta_text=f"Obj. semanal: {obj_c_sem:,} · Eq.: {eq_c_sem:,}",
    )

    dias_sobre_obj  = week_data.get("dias_sobre_objetivo", 0)
    dias_sobre_eq   = week_data.get("dias_sobre_equilibrio", 0)
    dias_con_datos  = week_data.get("dias_con_datos", 0)
    dias_texto = (
        f"{dias_sobre_obj} de {dias_con_datos} días sobre objetivo (40+ comensales)"
        f" · {dias_sobre_eq} días sobre equilibrio (35+)"
        if dias_con_datos else "Sin datos de días"
    )

    # MTD
    mes_nombre = mtd_data.get("mes_nombre", "")
    anio       = mtd_data.get("anio", now.year)
    dias_t     = mtd_data.get("dias_transcurridos", 0)
    dias_mes   = mtd_data.get("dias_en_mes", 30)
    v_mtd      = mtd_data.get("ventas_netas", 0.0)
    c_mtd      = mtd_data.get("comensales", 0)
    obj_v_prop = mtd_data.get("obj_ventas_prop", 0)
    eq_v_prop  = mtd_data.get("eq_ventas_prop", 0)
    obj_c_prop = mtd_data.get("obj_comensales_prop", 0)
    obj_v_mes  = mtd_data.get("obj_ventas_mes", 335_000)
    obj_c_mes  = mtd_data.get("obj_comensales_mes", 1_200)
    proy_v     = mtd_data.get("proyeccion_ventas", 0.0)
    proy_c     = mtd_data.get("proyeccion_comensales", 0)

    v_pct = round(v_mtd / obj_v_prop * 100, 1) if obj_v_prop else 0
    c_pct = round(c_mtd / obj_c_prop * 100, 1) if obj_c_prop else 0

    kpi_ventas_mtd = _kpi_card_html(
        label="Ventas Netas MTD",
        value_html=_fmt_mxn_short(v_mtd),
        delta_html=f'<span style="font-size:11px;color:#6b7280;">{v_pct}% del prop. esperado ({_fmt_mxn_short(obj_v_prop)})</span>',
        badge_html=_status_badge_html(mtd_data.get("ventas_status", "")),
        meta_text=f"Meta mensual: {_fmt_mxn_short(obj_v_mes)} · Eq.: {_fmt_mxn_short(mtd_data.get('eq_ventas_mes', 295000))}",
    )
    kpi_comensales_mtd = _kpi_card_html(
        label="Comensales MTD",
        value_html=f"{c_mtd:,}",
        delta_html=f'<span style="font-size:11px;color:#6b7280;">{c_pct}% del prop. esperado ({obj_c_prop:,})</span>',
        badge_html=_status_badge_html(mtd_data.get("comensales_status", "")),
        meta_text=f"Meta mensual: {obj_c_mes:,} · Eq.: {mtd_data.get('eq_comensales_mes', 1035):,}",
    )

    proy_v_ok   = proy_v >= obj_v_mes
    proy_v_eq   = proy_v >= mtd_data.get("eq_ventas_mes", 295_000)
    proy_v_icon = "🟢" if proy_v_ok else "🟡" if proy_v_eq else "🔴"
    proy_c_ok   = proy_c >= obj_c_mes
    proy_c_eq   = proy_c >= mtd_data.get("eq_comensales_mes", 1_035)
    proy_c_icon = "🟢" if proy_c_ok else "🟡" if proy_c_eq else "🔴"

    proyeccion_html = f"""
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:14px 18px;margin-top:16px;">
      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#0369a1;margin-bottom:8px;font-weight:700;">
        📈 Proyección cierre del mes
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          <td style="font-size:13px;color:#374151;padding:3px 0;">
            {proy_v_icon} Ventas netas: <strong>{_fmt_mxn_short(proy_v)}</strong>
            <span style="color:#6b7280;font-size:12px;">&nbsp;(vs meta {_fmt_mxn_short(obj_v_mes)})</span>
          </td>
        </tr>
        <tr>
          <td style="font-size:13px;color:#374151;padding:3px 0;">
            {proy_c_icon} Comensales: <strong>{proy_c:,}</strong>
            <span style="color:#6b7280;font-size:12px;">&nbsp;(vs meta {obj_c_mes:,})</span>
          </td>
        </tr>
      </table>
    </div>"""

    # ── B3, B4, B5, B6, B7 ───────────────────────────────────────────────────
    ads_status_html         = _build_ads_status_html(ads_data)
    executed_actions_html   = _build_executed_actions_html(supervisor_data)
    pending_proposals_html  = _build_pending_proposals_html(supervisor_data)
    risks_alerts_html       = _build_risks_alerts_html(supervisor_data)
    next_action_html        = _build_next_action_html(next_action)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Reporte Semanal Thai Thai · {week_title}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">

<div style="max-width:640px;margin:0 auto;background:white;">

  <!-- ▌ B0: HEADER ▌ -->
  <div style="background:linear-gradient(135deg,#1e3a5f 0%,#c8941a 100%);padding:28px 32px 22px;text-align:center;">
    <div style="font-size:26px;margin-bottom:6px;">🍜</div>
    <h1 style="margin:0;color:white;font-size:21px;font-weight:700;letter-spacing:-0.3px;">
      Reporte Semanal · {week_title}
    </h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.6);font-size:12px;">
      Generado el {gen_date}
    </p>
  </div>

  <div style="padding:28px 32px;">

    <!-- ═══════════════════════════════════
         B1: RESUMEN EJECUTIVO
    ═══════════════════════════════════ -->
    {executive_summary_html}

    <!-- ═══════════════════════════════════
         B2: KPIs DEL NEGOCIO
    ═══════════════════════════════════ -->

    {_section_h2("📅 Semana cerrada · " + week_label)}

    <table style="width:100%;border-collapse:separate;border-spacing:12px 0;margin:16px -12px 0;table-layout:fixed;">
      <tr>
        {kpi_ventas_sem}
        {kpi_comensales_sem}
      </tr>
    </table>

    <p style="font-size:12px;color:#6b7280;margin:12px 0 20px;padding-left:4px;">
      📆 {dias_texto}
    </p>

    {_section_h2("📈 Mes a la fecha · " + mes_nombre + " " + str(anio) + " · " + str(dias_t) + "/" + str(dias_mes) + " días")}

    <table style="width:100%;border-collapse:separate;border-spacing:12px 0;margin:16px -12px 0;table-layout:fixed;">
      <tr>
        {kpi_ventas_mtd}
        {kpi_comensales_mtd}
      </tr>
    </table>

    {proyeccion_html}

    <!-- ═══════════════════════════════════
         B3: ESTADO GOOGLE ADS
    ═══════════════════════════════════ -->
    {ads_status_html}

    <!-- ═══════════════════════════════════
         B4: ACCIONES EJECUTADAS
    ═══════════════════════════════════ -->
    {executed_actions_html}

    <!-- ═══════════════════════════════════
         B5: PROPUESTAS PARA APROBACIÓN
    ═══════════════════════════════════ -->
    {pending_proposals_html}

    <!-- ═══════════════════════════════════
         B6: RIESGOS Y ALERTAS
    ═══════════════════════════════════ -->
    {risks_alerts_html}

    <!-- ═══════════════════════════════════
         B7: SIGUIENTE MEJOR ACCIÓN
    ═══════════════════════════════════ -->
    {next_action_html}

  </div>

  <!-- ▌ B10: FOOTER ▌ -->
  <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 32px;text-align:center;">
    <p style="font-size:11px;color:#9ca3af;margin:0;line-height:1.8;">
      Thai Thai Ads Agent · Claude Sonnet 4.6<br>
      <a href="{BASE_URL}/audit-log" style="color:#2563eb;text-decoration:none;">Historial de acciones</a>
    </p>
  </div>

</div>
</body>
</html>"""


# ── Envío de correo ───────────────────────────────────────────────────────────

def send_weekly_report(
    week_data: dict,
    prev_week_data: dict,
    mtd_data: dict,
    supervisor_data: dict,
    next_action: str,
    geo_data: dict | None = None,
    smart_data: dict | None = None,
    ads_data: dict | None = None,
) -> dict:
    """
    Genera y envía el reporte ejecutivo semanal vía Gmail SMTP (STARTTLS port 587).
    Retorna dict con success, recipient, subject, sent_at o error.
    """
    if not GMAIL_APP_PASSWORD:
        return {"success": False, "error": "GMAIL_APP_PASSWORD no configurado."}
    if not EMAIL_TO:
        return {"success": False, "error": "EMAIL_TO no configurado."}

    try:
        html_body = build_html_report(
            week_data, prev_week_data, mtd_data,
            supervisor_data, next_action,
            geo_data=geo_data, smart_data=smart_data, ads_data=ads_data,
        )

        ws = week_data.get("week_start")
        we = week_data.get("week_end")
        if ws and we:
            subject = (
                f"Thai Thai · Reporte Semanal "
                f"{ws.day}–{we.day} {_MESES_ES_LARGO[we.month-1]} {we.year}"
            )
        else:
            subject = f"Thai Thai · Reporte Semanal {datetime.now().strftime('%d/%m/%Y')}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"]      = EMAIL_TO

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

        now = datetime.now()
        print(f"[EMAIL] Reporte semanal enviado a {EMAIL_TO} · {subject}")
        return {
            "success":   True,
            "recipient": EMAIL_TO,
            "subject":   subject,
            "sent_at":   now.isoformat(),
        }

    except Exception as e:
        import traceback
        print(f"[EMAIL] Error enviando reporte: {e}")
        print(f"[EMAIL] {traceback.format_exc()}")
        return {"success": False, "error": str(e)}
