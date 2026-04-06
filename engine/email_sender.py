"""
Thai Thai Ads Agent — Email Sender (Fase 2)

Envía el correo de propuestas de optimización por SMTP Gmail.
Requiere GMAIL_APP_PASSWORD en el entorno (App Password de 16 chars).

Uso:
    from engine.email_sender import send_proposal_email
    ok = send_proposal_email(proposals, session_id)
"""

import smtplib
import logging
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_merida_tz = None
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        _merida_tz = ZoneInfo("America/Merida")
    except (ZoneInfoNotFoundError, KeyError):
        pass  # datos de zona no instalados — fallback UTC-6
except ImportError:
    pass

if _merida_tz is None:
    try:
        import pytz
        _merida_tz = pytz.timezone("America/Merida")
    except (ImportError, Exception):
        pass  # fallback UTC-6 fijo en _to_merida()

logger = logging.getLogger(__name__)


def _to_merida(dt_utc: datetime) -> str:
    """Convierte un datetime UTC a string legible en hora de Mérida."""
    if _merida_tz is None:
        # Fallback: UTC-6 fijo (CST Mérida sin horario de verano)
        merida_time = dt_utc - timedelta(hours=6)
        dias   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses  = ["enero","febrero","marzo","abril","mayo","junio",
                  "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        return (f"{dias[merida_time.weekday()]} {merida_time.day} de "
                f"{meses[merida_time.month - 1]} de {merida_time.year} "
                f"a las {merida_time.strftime('%H:%M')} hrs (Mérida, UTC-6)")
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(_merida_tz)
    # Formato en español manual (strftime no localiza en Windows)
    dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
    meses = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    dia_nombre = dias[local.weekday()]
    mes_nombre = meses[local.month - 1]
    return f"{dia_nombre} {local.day} de {mes_nombre} de {local.year} a las {local.strftime('%H:%M')} hrs (Mérida)"


def _urgency_label(urgency: str) -> str:
    return {"critical": "🔴 Crítica", "urgent": "🟡 Urgente", "normal": "🟢 Normal"}.get(urgency, urgency)


def _build_proposal_block(proposal: dict, index: int, total: int, base_url: str) -> str:
    """Genera el bloque de texto plano para una propuesta individual."""
    token   = proposal.get("approval_token", "")
    keyword = proposal.get("keyword", "")
    campaign = proposal.get("campaign", "")
    spend   = proposal.get("spend", 0)
    reason  = proposal.get("reason", "")
    urgency = _urgency_label(proposal.get("urgency", "normal"))

    approve_url = f"{base_url}/approve?d={token}&action=approve"
    reject_url  = f"{base_url}/approve?d={token}&action=reject"

    # Extraer evidencia del proposal (viene del classified result)
    conversions = proposal.get("conversions", 0)
    impressions = proposal.get("impressions", 0)

    lines = [
        f"{'─' * 62}",
        f"PROPUESTA {index} / {total}",
        f"{'─' * 62}",
        "",
        f"  Keyword    : \"{keyword}\"",
        f"  Campaña    : {campaign}",
        f"  Urgencia   : {urgency}",
        "",
        "  EVIDENCIA",
        f"    Gasto acumulado : ${spend:.2f} MXN",
        f"    Conversiones    : {conversions}",
        f"    Impresiones     : {impressions}",
        f"    Período         : últimos 30 días",
        "",
        "  ACCIÓN PROPUESTA",
        f"    Agregar \"{keyword}\" como keyword negativa",
        f"    en la campaña {campaign}.",
        "",
        "  POR QUÉ",
        f"    {reason}",
        "",
        "  QUÉ MEJORARÍA",
        "    Elimina gasto sin retorno. El presupuesto se redistribuye",
        "    hacia keywords con mejor rendimiento.",
        "",
        "  RIESGO",
        "    Bajo. No es una keyword de marca ni aparece en la lista",
        "    de términos estratégicos protegidos.",
        "",
        "  REVERSIBILIDAD",
        "    Alta. Puedes eliminar la keyword negativa en menos de 1",
        "    minuto desde Google Ads. Sin efectos permanentes.",
        "",
        "  RECOMENDACIÓN DEL AGENTE",
        "    Aprobar. Evidencia suficiente de desperdicio sin conversiones.",
        "",
        f"  ✅  APROBAR esta propuesta:",
        f"      {approve_url}",
        "",
        f"  ❌  RECHAZAR esta propuesta:",
        f"      {reject_url}",
        "",
    ]
    return "\n".join(lines)


def build_proposal_email_text(proposals: list, session_id: str, base_url: str) -> tuple[str, str]:
    """
    Construye asunto y cuerpo del correo de propuestas.

    Args:
        proposals : lista de dicts de proposed[] ya priorizados (máx 3)
        session_id: identificador del ciclo de auditoría
        base_url  : URL base para links de aprobación

    Returns:
        (subject, body_text)
    """
    from config.agent_config import PROPOSAL_EXPIRY_HOURS

    n = len(proposals)
    subject = (
        f"[Thai Thai Ads] {n} propuesta{'s' if n > 1 else ''} de optimización "
        f"— aprobación requerida"
    )

    # Calcular expiración a partir de ahora (peor caso: propuesta recién creada)
    expiry_utc = datetime.now(timezone.utc) + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
    expiry_str = _to_merida(expiry_utc)

    header = "\n".join([
        "=" * 62,
        "  THAI THAI ADS AGENT — Propuestas de optimización",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"Se detectaron {n} keyword{'s' if n > 1 else ''} candidata{'s' if n > 1 else ''} a bloqueo.",
        "Requieren tu revisión antes de ejecutarse automáticamente.",
        "",
        f"Este correo expira el {expiry_str}.",
        "Las propuestas sin respuesta quedan pospuestas y serán",
        "re-evaluadas en el siguiente ciclo de auditoría.",
        "",
    ])

    blocks = [
        _build_proposal_block(p, i + 1, n, base_url)
        for i, p in enumerate(proposals)
    ]

    footer = "\n".join([
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automáticamente — no responder a este correo.",
        "=" * 62,
    ])

    body = header + "\n".join(blocks) + "\n" + footer
    return subject, body


def build_alert_email_text(alert_data: dict, session_id: str) -> tuple[str, str]:
    """
    Construye asunto y cuerpo del correo de alerta de tracking (Fase 3A).

    Este correo es solo de NOTIFICACIÓN — no incluye botones de aprobación.
    No hay mutaciones en Google Ads asociadas.

    Args:
        alert_data: dict producido por detect_tracking_signals() + metadatos de ciclo
        session_id: identificador del ciclo de auditoría

    Returns:
        (subject, body_text)
    """
    signals = alert_data.get("signals", [])
    severity = alert_data.get("severity", "warning")
    reason = alert_data.get("reason", "")
    affected = alert_data.get("affected_campaigns", [])
    signal_a = alert_data.get("signal_a_affected", [])
    signal_b = alert_data.get("signal_b_affected", [])
    acct = alert_data.get("account_metrics", {})
    curr_range = alert_data.get("current_week_range", "—")
    prev_range = alert_data.get("prev_week_range", "—")

    severity_label = {"critical": "🔴 CRÍTICA", "warning": "🟡 ADVERTENCIA"}.get(severity, severity.upper())
    signals_str = " + ".join(f"Señal {s}" for s in signals)

    subject = (
        f"[Thai Thai Ads] Alerta de tracking {severity_label} — {signals_str} detectada"
    )

    expiry_utc = datetime.now(timezone.utc)
    timestamp_str = _to_merida(expiry_utc)

    header_lines = [
        "=" * 62,
        "  THAI THAI ADS AGENT — Alerta de Tracking (Fase 3A)",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"  Severidad : {severity_label}",
        f"  Señales   : {signals_str}",
        f"  Detectado : {timestamp_str}",
        "",
        "  IMPORTANTE: Este correo es solo de diagnóstico.",
        "  El agente NO ha realizado cambios en Google Ads.",
        "  Las acciones correctivas requieren intervención manual.",
        "",
    ]

    detail_lines = [
        "─" * 62,
        "  DIAGNÓSTICO",
        "─" * 62,
        "",
        f"  {reason}",
        "",
        f"  Período analizado : semana actual  {curr_range}",
        f"  Período referencia: semana anterior {prev_range}",
        "",
        f"  Clicks totales (semana actual) : {acct.get('total_clicks', 0)}",
        f"  Conversiones totales           : {acct.get('total_conversions', 0)}",
        f"  Campañas evaluadas             : {acct.get('campaigns_evaluated', 0)}",
        "",
    ]

    if signal_a:
        detail_lines += [
            "  DETALLE — SEÑAL A (caída de CVR)",
        ]
        for c in signal_a:
            detail_lines.append(
                f"    • {c['campaign']} — CVR: {c['cvr_prev_pct']}% → {c['cvr_current_pct']}% "
                f"(caída {c['drop_pct']}%)"
            )
        detail_lines.append("")

    if signal_b:
        detail_lines += [
            "  DETALLE — SEÑAL B (clicks sin conversiones)",
        ]
        for c in signal_b:
            detail_lines.append(
                f"    • {c['campaign']} — {c['clicks']} clicks, 0 conversiones"
            )
        detail_lines.append("")

    if affected:
        detail_lines += [
            f"  Campañas afectadas ({len(affected)}):",
        ]
        for name in affected:
            detail_lines.append(f"    • {name}")
        detail_lines.append("")

    steps_lines = [
        "─" * 62,
        "  PASOS DE VERIFICACIÓN RECOMENDADOS",
        "─" * 62,
        "",
        "  1. Abre Google Tag Assistant y verifica que los tags de",
        "     conversión disparen correctamente en thaithaimerida.com.",
        "",
        "  2. Revisa el estado de las conversion actions en Google Ads:",
        "     Herramientas → Medición → Conversiones.",
        "     Busca el indicador 'Sin actividad reciente'.",
        "",
        "  3. Si usas Gloria Food, verifica que el pixel de pedido",
        "     completado siga activo.",
        "",
        "  4. Confirma en GA4 que los eventos de conversión aparecen",
        "     en Informes → Tiempo real durante una prueba de pedido.",
        "",
        "  5. Si detectas el problema, corrígelo manualmente. El agente",
        "     NO realizará cambios en conversion actions sin autorización.",
        "",
        "  Este diagnóstico es tentativo. No se descarta que sea",
        "  variación normal de tráfico o temporada baja.",
        "",
    ]

    footer_lines = [
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automáticamente — no responder a este correo.",
        "=" * 62,
    ]

    body = "\n".join(
        header_lines + detail_lines + steps_lines + footer_lines
    )
    return subject, body


def send_alert_email(alert_data: dict, session_id: str) -> bool:
    """
    Envía correo de alerta de tracking (Fase 3A) vía SMTP Gmail con STARTTLS.

    IMPORTANTE: Este correo es solo de NOTIFICACIÓN — no incluye botones de
    aprobación. No hay mutaciones en Google Ads asociadas a este correo.
    RISK_EXECUTE para tracking_alert = enviar alerta, no mutar Google Ads.

    Args:
        alert_data : dict producido por detect_tracking_signals() + metadatos
        session_id : identificador del ciclo de auditoría

    Returns:
        True si el correo se envió correctamente, False si hubo error.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST,
        EMAIL_SMTP_PORT,
        EMAIL_FROM,
        EMAIL_FROM_NAME,
        EMAIL_TO,
        GMAIL_APP_PASSWORD,
    )

    if not GMAIL_APP_PASSWORD:
        logger.error(
            "send_alert_email: GMAIL_APP_PASSWORD no configurado — "
            "alerta no enviada. Setear la variable de entorno."
        )
        return False

    subject, body_text = build_alert_email_text(alert_data, session_id)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        logger.info(
            "send_alert_email: alerta de tracking enviada a %s [ciclo=%s, señales=%s]",
            EMAIL_TO, session_id, alert_data.get("signals", [])
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "send_alert_email: error de autenticación SMTP — "
            "verifica GMAIL_APP_PASSWORD (16 chars, sin espacios)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("send_alert_email: SMTPException — %s", exc)
        return False

    except Exception as exc:
        logger.error("send_alert_email: error inesperado — %s", exc)
        return False


def build_landing_alert_email_text(alert_data: dict, session_id: str) -> tuple[str, str]:
    """
    Construye asunto y cuerpo del correo de alerta de landing (Fase 3B).

    Solo se llama para severidad 'critical'. Las alertas 'warning' se registran
    en SQLite y en el response pero NO generan correo.

    Args:
        alert_data : dict producido por check_landing_health() + metadatos
        session_id : identificador del ciclo de auditoría

    Returns:
        (subject, body_text)
    """
    signals = alert_data.get("signals", [])
    severity = alert_data.get("severity", "critical")
    reason = alert_data.get("reason", "")
    details = alert_data.get("details", {})

    severity_label = {"critical": "🔴 CRÍTICA", "warning": "🟡 ADVERTENCIA"}.get(
        severity, severity.upper()
    )
    signals_str = " + ".join(signals) if signals else "desconocida"

    subject = (
        f"[Thai Thai Ads] Alerta de landing {severity_label} — {signals_str} detectada"
    )

    timestamp_str = _to_merida(datetime.now(timezone.utc))

    header = "\n".join([
        "=" * 62,
        "  THAI THAI ADS AGENT — Alerta de Landing (Fase 3B)",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"  Severidad : {severity_label}",
        f"  Señales   : {signals_str}",
        f"  Detectado : {timestamp_str}",
        "",
        "  IMPORTANTE: El agente NO ha realizado cambios en la web.",
        "  Las acciones correctivas requieren intervención manual.",
        "",
    ])

    detail_lines = [
        "─" * 62,
        "  DIAGNÓSTICO",
        "─" * 62,
        "",
        f"  {reason}",
        "",
    ]

    if "S1_DOWN" in signals:
        d = details.get("s1", {})
        attempts = details.get("landing_attempts", [])
        detail_lines += [
            "  DETALLE — S1_DOWN (landing sin respuesta)",
            f"    URL           : {alert_data.get('landing_url', 'https://thaithaimerida.com')}",
            f"    Intentos      : {d.get('failed_attempts', '?')}/{d.get('total_attempts', '?')} fallaron",
            f"    Último status : {d.get('last_status_code', 'sin respuesta')}",
        ]
        for a in attempts:
            status = a.get("status_code", "—")
            elapsed = f"{a.get('elapsed_s', '—')}s" if a.get("elapsed_s") else "—"
            ok_str = "OK" if a.get("ok") else "FALLO"
            error = f" ({a['error']})" if a.get("error") else ""
            detail_lines.append(
                f"    Intento {a['attempt']}: {ok_str} | status {status} | {elapsed}{error}"
            )
        detail_lines.append("")

    if "S2_SLOW" in signals:
        d = details.get("s2", {})
        detail_lines += [
            "  DETALLE — S2_SLOW (respuesta lenta)",
            f"    Tiempo promedio : {d.get('response_time_s', '?')}s",
            f"    Umbral          : {d.get('threshold_s', '?')}s ({d.get('level', '?')})",
            "",
        ]

    if "S4_LINK_BROKEN" in signals:
        d = details.get("s4", {})
        conv = details.get("conversion_check", {})
        detail_lines += [
            "  DETALLE — S4_LINK_BROKEN (enlace de pedidos no accesible)",
            f"    URL           : {d.get('url', alert_data.get('conversion_url', '—'))}",
            f"    Status code   : {d.get('status_code', 'sin respuesta')}",
            f"    Método último : {d.get('method_used', 'HEAD+GET')}",
        ]
        if d.get("error"):
            detail_lines.append(f"    Error         : {d['error']}")
        detail_lines.append("")

    steps = "\n".join([
        "─" * 62,
        "  PASOS DE VERIFICACIÓN",
        "─" * 62,
        "",
    ])

    step_items = []
    if "S1_DOWN" in signals:
        step_items += [
            "  1. Abre https://thaithaimerida.com en un navegador ahora",
            "     y confirma si la página carga correctamente.",
            "",
            "  2. Verifica el estado del sitio en el panel de Netlify",
            "     (deploys recientes, errores de build, estado del CDN).",
            "",
            "  3. Si hubo un deploy reciente, revisa si introdujo errores",
            "     y considera hacer rollback desde el panel de Netlify.",
            "",
        ]
    if "S4_LINK_BROKEN" in signals:
        step_items += [
            "  4. Verifica que el widget de pedidos de Gloria Food esté",
            "     activo en el panel de restaurantlogin.com.",
            "",
            "  5. Prueba el enlace de pedidos manualmente desde un navegador:",
            f"     {alert_data.get('conversion_url', 'https://www.restaurantlogin.com/api/fb/_y5_p1_j')}",
            "",
        ]
    if not step_items:
        step_items = [
            "  1. Verifica el estado del sitio y el flujo de conversión",
            "     manualmente antes de tomar cualquier acción.",
            "",
        ]

    footer = "\n".join([
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automáticamente — no responder a este correo.",
        "=" * 62,
    ])

    body = (
        header
        + "\n".join(detail_lines)
        + "\n"
        + steps
        + "\n".join(step_items)
        + "\n"
        + footer
    )
    return subject, body


def send_landing_alert_email(alert_data: dict, session_id: str) -> bool:
    """
    Envía correo de alerta de landing (Fase 3B) vía SMTP Gmail con STARTTLS.

    Solo debe llamarse para severidad 'critical'. Las alertas 'warning' solo
    se registran en SQLite — no generan correo en este MVP.

    Args:
        alert_data : dict producido por check_landing_health() + metadatos
        session_id : identificador del ciclo de auditoría

    Returns:
        True si el correo se envió correctamente, False si hubo error.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST,
        EMAIL_SMTP_PORT,
        EMAIL_FROM,
        EMAIL_FROM_NAME,
        EMAIL_TO,
        GMAIL_APP_PASSWORD,
    )

    if not GMAIL_APP_PASSWORD:
        logger.error(
            "send_landing_alert_email: GMAIL_APP_PASSWORD no configurado — "
            "alerta no enviada."
        )
        return False

    subject, body_text = build_landing_alert_email_text(alert_data, session_id)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        logger.info(
            "send_landing_alert_email: alerta enviada a %s [ciclo=%s, señales=%s]",
            EMAIL_TO, session_id, alert_data.get("signals", []),
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "send_landing_alert_email: error de autenticación SMTP — "
            "verifica GMAIL_APP_PASSWORD (16 chars, sin espacios)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("send_landing_alert_email: SMTPException — %s", exc)
        return False

    except Exception as exc:
        logger.error("send_landing_alert_email: error inesperado — %s", exc)
        return False


def _build_adgroup_proposal_block(proposal: dict, index: int, total: int, base_url: str) -> str:
    """Genera el bloque de texto para una propuesta de ad group individual."""
    token         = proposal.get("approval_token", "")
    adgroup_name  = proposal.get("adgroup_name", "")
    campaign_name = proposal.get("campaign_name", "")
    cost_mxn      = proposal.get("cost_mxn", 0)
    clicks        = proposal.get("clicks", 0)
    impressions   = proposal.get("impressions", 0)
    reason        = proposal.get("reason", "")
    window_days   = proposal.get("window_days", 14)

    approve_url = f"{base_url}/approve?d={token}&action=approve"
    reject_url  = f"{base_url}/approve?d={token}&action=reject"

    lines = [
        f"{'─' * 62}",
        f"PROPUESTA {index} / {total}",
        f"{'─' * 62}",
        "",
        f"  Ad Group   : \"{adgroup_name}\"",
        f"  Campaña    : {campaign_name}",
        f"  Señal      : AG1 — gasto sin conversiones",
        "",
        "  EVIDENCIA",
        f"    Gasto acumulado : ${cost_mxn:.2f} MXN",
        f"    Conversiones    : 0",
        f"    Clicks          : {clicks}",
        f"    Impresiones     : {impressions}",
        f"    Período         : últimos {window_days} días",
        "",
        "  ACCIÓN PROPUESTA",
        f"    Pausar el ad group \"{adgroup_name}\"",
        f"    en la campaña {campaign_name}.",
        "",
        "  POR QUÉ",
        f"    {reason}",
        "",
        "  QUÉ MEJORARÍA",
        "    Detiene el gasto en este grupo sin retorno.",
        "    El presupuesto se redistribuye hacia otros grupos",
        "    con mejor rendimiento en la misma campaña.",
        "",
        "  RIESGO",
        "    Bajo. No afecta otras campañas ni el presupuesto",
        "    total. El ad group puede reactivarse en cualquier",
        "    momento desde Google Ads.",
        "",
        "  REVERSIBILIDAD",
        "    Alta. Reactivar el ad group toma menos de 1 minuto",
        "    desde Google Ads. Sin efectos permanentes.",
        "",
        "  RECOMENDACIÓN DEL AGENTE",
        "    Revisar antes de aprobar. Considerar si el grupo",
        "    tiene alguna función estratégica que no refleje",
        "    conversiones directas.",
        "",
        f"  APROBAR esta propuesta:",
        f"      {approve_url}",
        "",
        f"  RECHAZAR esta propuesta:",
        f"      {reject_url}",
        "",
    ]
    return "\n".join(lines)


def build_adgroup_proposal_email_text(
    proposals: list, session_id: str, base_url: str
) -> tuple[str, str]:
    """
    Construye asunto y cuerpo del correo de propuestas de ad groups (Fase 4).

    Tono: revisión de optimización, no incidente crítico.
    Urgencia se omite del asunto — se muestra el conteo y el monto total.

    Args:
        proposals : lista de dicts de adgroup_proposals ya priorizados (máx 2)
        session_id: identificador del ciclo de auditoría
        base_url  : URL base para links de aprobación

    Returns:
        (subject, body_text)
    """
    from config.agent_config import PROPOSAL_EXPIRY_HOURS, ADGROUP_EVIDENCE_WINDOW_DAYS

    n = len(proposals)
    total_spend = sum(p.get("cost_mxn", 0) for p in proposals)

    subject = (
        f"[Thai Thai Ads] {n} ad group{'s' if n > 1 else ''} con gasto sin conversiones "
        f"— revisión recomendada"
    )

    expiry_utc = datetime.now(timezone.utc) + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
    expiry_str = _to_merida(expiry_utc)
    timestamp_str = _to_merida(datetime.now(timezone.utc))

    header = "\n".join([
        "=" * 62,
        "  THAI THAI ADS AGENT — Revisión de Ad Groups (Fase 4)",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"  Detectado : {timestamp_str}",
        "",
        f"Se {'detectó' if n == 1 else 'detectaron'} {n} ad group{'s' if n > 1 else ''} con "
        f"${total_spend:.2f} MXN en gasto acumulado y 0 conversiones",
        f"en los últimos {ADGROUP_EVIDENCE_WINDOW_DAYS} días.",
        "",
        "Se recomienda revisar y decidir si pausarlos.",
        "El agente NO ejecutará ninguna acción sin tu aprobación.",
        "",
        f"Esta propuesta expira el {expiry_str}.",
        "",
    ])

    blocks = [
        _build_adgroup_proposal_block(p, i + 1, n, base_url)
        for i, p in enumerate(proposals)
    ]

    footer = "\n".join([
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automáticamente — no responder a este correo.",
        "=" * 62,
    ])

    body = header + "\n".join(blocks) + "\n" + footer
    return subject, body


def send_adgroup_proposal_email(proposals: list, session_id: str) -> bool:
    """
    Envía el correo de propuestas de ad groups (Fase 4) vía SMTP Gmail con STARTTLS.

    Args:
        proposals : lista de dicts del adgroup_proposals[] ya priorizados (máx 2)
        session_id: identificador del ciclo de auditoría

    Returns:
        True si el correo se envió correctamente, False si hubo error.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST,
        EMAIL_SMTP_PORT,
        EMAIL_FROM,
        EMAIL_FROM_NAME,
        EMAIL_TO,
        GMAIL_APP_PASSWORD,
        APPROVAL_BASE_URL,
    )

    if not proposals:
        logger.info("send_adgroup_proposal_email: no hay propuestas — correo no enviado")
        return False

    if not GMAIL_APP_PASSWORD:
        logger.error(
            "send_adgroup_proposal_email: GMAIL_APP_PASSWORD no configurado — "
            "correo no enviado. Setear la variable de entorno."
        )
        return False

    subject, body_text = build_adgroup_proposal_email_text(proposals, session_id, APPROVAL_BASE_URL)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        logger.info(
            "send_adgroup_proposal_email: correo enviado a %s con %d propuesta(s) [ciclo=%s]",
            EMAIL_TO, len(proposals), session_id,
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "send_adgroup_proposal_email: error de autenticación SMTP — "
            "verifica que GMAIL_APP_PASSWORD sea un App Password válido (16 chars)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("send_adgroup_proposal_email: SMTPException — %s", exc)
        return False

    except Exception as exc:
        logger.error("send_adgroup_proposal_email: error inesperado — %s", exc)
        return False


def send_proposal_email(proposals: list, session_id: str) -> bool:
    """
    Envía el correo de propuestas vía SMTP Gmail con STARTTLS.

    Args:
        proposals : lista de dicts del proposed[] ya priorizados (máx 3)
        session_id: identificador del ciclo de auditoría

    Returns:
        True si el correo se envió correctamente, False si hubo error.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST,
        EMAIL_SMTP_PORT,
        EMAIL_FROM,
        EMAIL_FROM_NAME,
        EMAIL_TO,
        GMAIL_APP_PASSWORD,
        APPROVAL_BASE_URL,
    )

    if not proposals:
        logger.info("send_proposal_email: no hay propuestas — correo no enviado")
        return False

    if not GMAIL_APP_PASSWORD:
        logger.error(
            "send_proposal_email: GMAIL_APP_PASSWORD no configurado — "
            "correo no enviado. Setear la variable de entorno."
        )
        return False

    subject, body_text = build_proposal_email_text(proposals, session_id, APPROVAL_BASE_URL)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        logger.info(
            "send_proposal_email: correo enviado a %s con %d propuesta(s) [ciclo=%s]",
            EMAIL_TO, len(proposals), session_id
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "send_proposal_email: error de autenticación SMTP — "
            "verifica que GMAIL_APP_PASSWORD sea un App Password válido (16 chars)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("send_proposal_email: SMTPException — %s", exc)
        return False

    except Exception as exc:
        logger.error("send_proposal_email: error inesperado — %s", exc)
        return False


# ============================================================================
# FASE 6B — BUDGET ACTIONS: CORREO DE PROPUESTAS DE PRESUPUESTO
# ============================================================================

def _build_budget_proposal_block(proposal: dict, index: int, total: int, base_url: str) -> str:
    """Genera el bloque de texto para una propuesta BA1 individual."""
    token              = proposal.get("approval_token", "")
    campaign_name      = proposal.get("campaign_name", "")
    campaign_type      = proposal.get("campaign_type", "")
    cost_mxn           = proposal.get("cost_mxn", 0)
    conversions        = proposal.get("conversions", 0)
    cpa_real           = proposal.get("cpa_real", 0)
    cpa_critical       = proposal.get("cpa_critical", 0)
    cpa_max            = proposal.get("cpa_max", 0)
    daily_budget       = proposal.get("daily_budget_mxn", 0)
    suggested          = proposal.get("suggested_daily_budget")
    reduction_pct      = proposal.get("reduction_pct")
    days_active        = proposal.get("days_active")
    evidence_window    = proposal.get("evidence_window_days", 14)
    reason             = proposal.get("reason", "")

    approve_url = f"{base_url}/approve?d={token}&action=approve"
    reject_url  = f"{base_url}/approve?d={token}&action=reject"

    budget_lines = []
    if daily_budget > 0:
        budget_lines = [
            f"    Presupuesto actual  : ${daily_budget:.2f} MXN/dia",
        ]
        if suggested is not None:
            budget_lines.append(
                f"    Presupuesto sugerido: ${suggested:.2f} MXN/dia"
                f" (-{reduction_pct}%)"
            )
        else:
            budget_lines.append("    Presupuesto sugerido: calcular en Google Ads")
    else:
        budget_lines = [
            "    Presupuesto actual  : no disponible",
            "    Presupuesto sugerido: revisar en Google Ads",
        ]

    days_line = (
        f"    Dias activa         : {days_active}"
        if days_active is not None
        else "    Dias activa         : no disponible"
    )

    lines = [
        f"{'─' * 62}",
        f"PROPUESTA {index} / {total}",
        f"{'─' * 62}",
        "",
        f"  Campana    : \"{campaign_name}\"",
        f"  Tipo       : {campaign_type}",
        f"  Senal      : BA1 — CPA critico, ajuste de presupuesto recomendado",
        "",
        "  EVIDENCIA",
        f"    Gasto en ventana    : ${cost_mxn:.2f} MXN ({evidence_window} dias)",
        f"    Conversiones        : {int(conversions)}",
        f"    CPA real            : ${cpa_real:.2f} MXN",
        f"    CPA critico del tipo: ${cpa_critical:.2f} MXN",
        f"    CPA maximo tolerable: ${cpa_max:.2f} MXN",
        days_line,
        "",
        "  AJUSTE PROPUESTO",
    ] + budget_lines + [
        "",
        "  POR QUE",
        f"    {reason}",
        "",
        "  QUE MEJORARIA",
        "    Reducir el presupuesto limita el gasto diario mientras el CPA",
        "    esta por encima del umbral critico. No elimina conversiones;",
        "    simplemente frena el desperdicio hasta ajustar la segmentacion.",
        "",
        "  IMPORTANTE — ESTA PROPUESTA NO ES AUTOMATICA",
        "    Aprobar esta propuesta SOLO registra tu decision en el agente.",
        "    El cambio de presupuesto DEBES hacerlo manualmente en Google Ads:",
        f"      Google Ads > Campanas > \"{campaign_name}\"",
        f"      > Configuracion > Presupuesto diario > ${suggested:.2f}" if suggested else
        f"      > Configuracion > Presupuesto diario > [revisa el CPA objetivo]",
        "",
        f"  APROBAR (registrar decision):",
        f"      {approve_url}",
        "",
        f"  RECHAZAR esta propuesta:",
        f"      {reject_url}",
        "",
    ]
    return "\n".join(lines)


def build_budget_proposal_email_text(
    proposals: list, session_id: str, base_url: str
) -> tuple:
    """
    Construye asunto y cuerpo del correo de propuestas BA1 (Fase 6B).

    Tono: propuesta de gestión / ajuste de rendimiento, no alerta urgente.
    El asunto refleja que es una recomendación de optimización.

    Args:
        proposals : lista de dicts de budget_actions priorizados
        session_id: identificador del ciclo de auditoría
        base_url  : URL base para links de aprobación

    Returns:
        (subject, body_text)
    """
    from config.agent_config import PROPOSAL_EXPIRY_HOURS
    from datetime import timezone, timedelta

    n = len(proposals)
    total_spend = sum(p.get("cost_mxn", 0) for p in proposals)

    subject = (
        f"[Thai Thai Ads] {n} campana{'s' if n > 1 else ''} con CPA elevado "
        f"— ajuste de presupuesto recomendado"
    )

    expiry_utc = datetime.now(timezone.utc) + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
    expiry_str = _to_merida(expiry_utc)
    timestamp_str = _to_merida(datetime.now(timezone.utc))

    header = "\n".join([
        "=" * 62,
        "  THAI THAI ADS AGENT — Ajuste de Presupuesto (Fase 6B)",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"  Detectado : {timestamp_str}",
        "",
        f"Se {'detectó' if n == 1 else 'detectaron'} {n} campana{'s' if n > 1 else ''} con "
        f"CPA por encima del umbral critico.",
        f"Gasto acumulado en ventana: ${total_spend:.2f} MXN.",
        "",
        "Se recomienda revisar el presupuesto diario para limitar el desperdicio",
        "mientras se ajusta la segmentacion o las pujas.",
        "",
        "IMPORTANTE: Aprobar esta propuesta SOLO registra tu decision.",
        "El cambio de presupuesto debes hacerlo MANUALMENTE en Google Ads.",
        "El agente no modifica presupuestos automaticamente.",
        "",
        f"Esta propuesta expira el {expiry_str}.",
        "",
    ])

    evidence_window = 14
    blocks = [
        _build_budget_proposal_block(
            {**p, "evidence_window_days": evidence_window},
            i + 1, n, base_url
        )
        for i, p in enumerate(proposals)
    ]

    footer = "\n".join([
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automaticamente — no responder a este correo.",
        "=" * 62,
    ])

    body = header + "\n".join(blocks) + "\n" + footer
    return subject, body


def send_budget_proposal_email(proposals: list, session_id: str) -> bool:
    """
    Envía el correo de propuestas BA1 (Fase 6B) vía SMTP Gmail con STARTTLS.

    Tono: propuesta de gestión / ajuste, no alerta urgente.

    Args:
        proposals : lista de dicts de budget_actions ya priorizados
        session_id: identificador del ciclo de auditoría

    Returns:
        True si el correo se envió correctamente, False si hubo error.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST,
        EMAIL_SMTP_PORT,
        EMAIL_FROM,
        EMAIL_FROM_NAME,
        EMAIL_TO,
        GMAIL_APP_PASSWORD,
        APPROVAL_BASE_URL,
    )

    if not proposals:
        logger.info("send_budget_proposal_email: no hay propuestas — correo no enviado")
        return False

    if not GMAIL_APP_PASSWORD:
        logger.error(
            "send_budget_proposal_email: GMAIL_APP_PASSWORD no configurado — "
            "correo no enviado. Setear la variable de entorno."
        )
        return False

    subject, body_text = build_budget_proposal_email_text(proposals, session_id, APPROVAL_BASE_URL)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        logger.info(
            "send_budget_proposal_email: correo enviado a %s con %d propuesta(s) [ciclo=%s]",
            EMAIL_TO, len(proposals), session_id,
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "send_budget_proposal_email: error de autenticacion SMTP — "
            "verifica que GMAIL_APP_PASSWORD sea un App Password valido (16 chars)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("send_budget_proposal_email: SMTPException — %s", exc)
        return False

    except Exception as exc:
        logger.error("send_budget_proposal_email: error inesperado — %s", exc)
        return False


# ── GEO ALERT EMAIL (Fase GEO) ────────────────────────────────────────────

def _build_geo_alert_block(alert: dict, index: int, total: int, base_url: str) -> str:
    """Bloque de texto para una señal geo individual."""
    token         = alert.get("approval_token", "")
    campaign_name = alert.get("campaign_name", "")
    campaign_id   = alert.get("campaign_id", "")
    signal        = alert.get("signal", "")
    reason        = alert.get("reason", "")
    disallowed    = alert.get("disallowed_location_ids", [])
    detected      = alert.get("detected_location_ids", [])
    allowed       = alert.get("allowed_location_ids", [])

    lines = [
        f"{'─' * 62}",
        f"SEÑAL {index} / {total}  [{signal}]",
        f"{'─' * 62}",
        "",
        f"  Campaña    : \"{campaign_name}\"",
        f"  ID         : {campaign_id}",
        f"  Señal      : {signal} — {'ubicación incorrecta' if signal == 'GEO1' else 'sin restricción geográfica'}",
        "",
        "  EVIDENCIA",
    ]

    if signal == "GEO1":
        lines += [
            f"    Ubicaciones detectadas   : {detected}",
            f"    Ubicaciones NO permitidas: {disallowed}",
            f"    Ubicaciones permitidas   : {allowed}",
        ]
    else:
        lines += [
            "    La campaña no tiene ningún criterio de ubicación configurado.",
            f"    Ubicaciones permitidas: {allowed}",
        ]

    lines += [
        "",
        "  RAZÓN",
        f"    {reason}",
        "",
    ]

    if signal == "GEO1" and token:
        approve_url = f"{base_url}/approve?d={token}&action=approve"
        reject_url  = f"{base_url}/approve?d={token}&action=reject"
        lines += [
            "  ACCIÓN PROPUESTA",
            "    Corregir geotargeting → dejar solo Mérida, Yucatán, México (1010205).",
            "    El agente eliminará las ubicaciones incorrectas y configurará solo Mérida.",
            "",
            "  RIESGO",
            "    Medio. Afecta el alcance de la campaña inmediatamente.",
            "    Reversible — puedes ajustar la ubicación en Google Ads en cualquier momento.",
            "",
            f"  APROBAR corrección:",
            f"      {approve_url}",
            "",
            f"  RECHAZAR (mantener como está):",
            f"      {reject_url}",
            "",
        ]
    else:
        lines += [
            "  ACCIÓN SUGERIDA",
            "    Revisar manualmente en Google Ads → Configuración → Ubicaciones.",
            "    Considera agregar Mérida, Yucatán, México (ID 1010205) como ubicación objetivo.",
            "",
        ]

    return "\n".join(lines)


def build_geo_alert_email_text(
    alerts: list, session_id: str, base_url: str
) -> tuple[str, str]:
    """Construye asunto y cuerpo del correo de alertas de geotargeting."""
    from config.agent_config import PROPOSAL_EXPIRY_HOURS

    geo1_count = sum(1 for a in alerts if a.get("signal") == "GEO1")
    geo0_count = sum(1 for a in alerts if a.get("signal") == "GEO0")
    n = len(alerts)

    parts = []
    if geo1_count:
        parts.append(f"{geo1_count} campaña(s) con ubicación incorrecta (GEO1)")
    if geo0_count:
        parts.append(f"{geo0_count} campaña(s) sin restricción geográfica (GEO0)")

    subject = f"[Thai Thai Ads] Geotargeting — {' · '.join(parts)}"

    expiry_utc    = datetime.now(timezone.utc) + timedelta(hours=PROPOSAL_EXPIRY_HOURS)
    expiry_str    = _to_merida(expiry_utc)
    timestamp_str = _to_merida(datetime.now(timezone.utc))

    header = "\n".join([
        "=" * 62,
        "  THAI THAI ADS AGENT — Auditoría de Geotargeting",
        f"  Ciclo : {session_id}",
        "=" * 62,
        "",
        f"  Detectado : {timestamp_str}",
        "",
        f"Se detectaron {n} campaña(s) con segmentación geográfica incorrecta o ausente.",
        "",
        "GEO1 (ubicación incorrecta): requiere corrección accionable.",
        "GEO0 (sin restricción): aviso informativo — revisar manualmente.",
        "",
        "El agente NO ejecutará ninguna corrección sin tu aprobación.",
        "",
        f"Las propuestas GEO1 expiran el {expiry_str}.",
        "",
    ])

    blocks = [
        _build_geo_alert_block(a, i + 1, n, base_url)
        for i, a in enumerate(alerts)
    ]

    footer = "\n".join([
        "=" * 62,
        "Thai Thai Ads Agent",
        "administracion@thaithaimerida.com.mx",
        "Generado automáticamente — no responder a este correo.",
        "=" * 62,
    ])

    body = header + "\n".join(blocks) + "\n" + footer
    return subject, body


def send_geo_alert_email(alerts: list, session_id: str) -> bool:
    """Envía el correo de alertas de geotargeting vía SMTP Gmail con STARTTLS."""
    from config.agent_config import (
        EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
        EMAIL_FROM, EMAIL_FROM_NAME, EMAIL_TO,
        GMAIL_APP_PASSWORD, APPROVAL_BASE_URL,
    )

    if not alerts:
        return False
    if not GMAIL_APP_PASSWORD:
        logger.warning("send_geo_alert_email: GMAIL_APP_PASSWORD no configurado")
        return False

    subject, body = build_geo_alert_email_text(alerts, session_id, APPROVAL_BASE_URL)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            smtp.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        logger.info("send_geo_alert_email: correo enviado — %d alerta(s)", len(alerts))
        return True
    except Exception as exc:
        logger.error("send_geo_alert_email: error SMTP — %s", exc)
        return False


# ============================================================================
# INCIDENTE OPERATIVO — corrida fallida o deploy roto
# ============================================================================

def _build_incident_email_html(
    incident_reason: str,
    retry_attempted: bool = False,
    compensatory_ran: bool = False,
    system_restored: bool = False,
    technical_detail: str = "",
    timestamp_merida: str = "",
) -> str:
    """
    Correo de incidente operativo: la auditoría diaria programada NO ocurrió.
    No es un reporte diario normal. Es una notificación de fallo del sistema.

    Separación clara:
      - Sección principal: qué pasó en términos de negocio / operación
      - Sección técnica: causa exacta, al pie
    """
    ts = timestamp_merida or "—"

    # Bloque de recuperación
    if compensatory_ran:
        recovery_html = """
      <div style="background:#e8f5e9; border-left:3px solid #2e7d32;
                  padding:10px 14px; border-radius:4px; margin-top:12px;
                  font-size:13px; color:#2e7d32;">
        <b>✓ Corrida compensatoria ejecutada</b> — El sistema realizó una auditoría completa
        más tarde el mismo día. Tus campañas fueron revisadas.
      </div>"""
        meaning = (
            "La auditoría programada falló, pero el sistema ejecutó una corrida compensatoria "
            "más tarde el mismo día. La cobertura del día fue recuperada."
        )
        action = "No. La auditoría compensatoria cubrió el día."
    elif system_restored and not retry_attempted:
        recovery_html = """
      <div style="background:#fff8e1; border-left:3px solid #f9a825;
                  padding:10px 14px; border-radius:4px; margin-top:12px;
                  font-size:13px; color:#7a5c00;">
        <b>⚡ Sistema restablecido</b> — La auditoría compensatoria se ejecutará a las 11am.
      </div>"""
        meaning = (
            "La auditoría programada de las 7am no se completó. "
            "El sistema fue restablecido. Se intentará una corrida compensatoria a las 11am."
        )
        action = "No por ahora. Esperar el correo de la corrida compensatoria a las 11am."
    elif system_restored:
        recovery_html = """
      <div style="background:#fff8e1; border-left:3px solid #f9a825;
                  padding:10px 14px; border-radius:4px; margin-top:12px;
                  font-size:13px; color:#7a5c00;">
        <b>⚡ Sistema restablecido</b> — No se ejecutó corrida compensatoria hoy.
      </div>"""
        meaning = (
            "La auditoría programada de las 7am no se completó. "
            "El sistema fue restablecido, pero no se realizó corrida compensatoria hoy. "
            "Tus campañas no fueron revisadas por el agente en este día."
        )
        action = (
            "No hay acción urgente. Las campañas continúan activas en Google Ads sin cambios "
            "del agente. El reporte del lunes cubrirá el análisis de la semana completa."
        )
    else:
        recovery_html = """
      <div style="background:#fce4ec; border-left:3px solid #b71c1c;
                  padding:10px 14px; border-radius:4px; margin-top:12px;
                  font-size:13px; color:#b71c1c;">
        <b>✗ Sin recuperación</b> — El sistema aún no está restablecido.
      </div>"""
        meaning = (
            "La auditoría programada no se completó y el sistema aún no fue restablecido. "
            "Tus campañas no están siendo supervisadas por el agente."
        )
        action = (
            "Verificar el estado del sistema. Si el error persiste, "
            "contactar al equipo técnico."
        )

    retry_line = (
        "Sí — se intentó reintento automático pero también falló."
        if retry_attempted else
        "No — el fallo ocurrió antes de que el sistema pudiera reintentar."
    )

    tech_section = ""
    if technical_detail:
        tech_section = f"""
  <tr>
    <td style="padding:4px 20px 14px 20px;">
      <p style="margin:0 0 4px 0; font-size:11px; color:#bbb; border-top:1px solid #eee;
                padding-top:10px;">DETALLE TÉCNICO</p>
      <p style="margin:0; font-size:12px; color:#999; font-family:monospace;
                word-break:break-all;">{technical_detail[:400]}</p>
    </td>
  </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif; background:#f9f9f9; padding:20px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff; border:1px solid #ddd; border-radius:6px; margin:0 auto;">

  <!-- Encabezado — rojo, incidente -->
  <tr>
    <td style="background:#fce4ec; padding:14px 20px; border-radius:6px 6px 0 0;">
      <span style="font-size:17px; font-weight:bold; color:#b71c1c;">
        ✗ Incidente operativo — Auditoría diaria no ejecutada
      </span><br>
      <span style="font-size:12px; color:#666;">Thai Thai Ads Agent &nbsp;·&nbsp; {ts}</span>
    </td>
  </tr>

  <!-- Estado operativo -->
  <tr>
    <td style="padding:16px 20px 4px 20px;">
      <p style="margin:0; font-size:14px; color:#333;">
        <b>La auditoría diaria programada no ocurrió.</b><br>
        No se revisaron campañas. No se aplicaron cambios.
      </p>
      {recovery_html}
    </td>
  </tr>

  <tr><td style="padding:12px 20px 0 20px;"><hr style="border:none; border-top:1px solid #eee; margin:0;"></td></tr>

  <!-- ¿Qué significa esto para mí hoy? -->
  <tr>
    <td style="padding:14px 20px 6px 20px;">
      <p style="margin:0 0 4px 0; font-size:12px; font-weight:bold; color:#999;
                text-transform:uppercase; letter-spacing:0.5px;">
        ¿Qué significa esto para mí hoy?
      </p>
      <p style="margin:0; font-size:14px; color:#333; line-height:1.5;">{meaning}</p>
    </td>
  </tr>

  <!-- ¿Necesito hacer algo hoy? -->
  <tr>
    <td style="padding:10px 20px 14px 20px;">
      <p style="margin:0 0 4px 0; font-size:12px; font-weight:bold; color:#999;
                text-transform:uppercase; letter-spacing:0.5px;">
        ¿Necesito hacer algo hoy?
      </p>
      <p style="margin:0; font-size:14px; color:#333; line-height:1.5;">{action}</p>
    </td>
  </tr>

  <!-- Fila de datos de incidente -->
  <tr>
    <td style="padding:0 20px 14px 20px;">
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-top:1px solid #eee; padding-top:10px;">
        <tr>
          <td style="padding:3px 0; font-size:12px; color:#999; width:200px;">Causa del fallo</td>
          <td style="padding:3px 0; font-size:12px; color:#555;">{incident_reason}</td>
        </tr>
        <tr>
          <td style="padding:3px 0; font-size:12px; color:#999;">Reintento automático</td>
          <td style="padding:3px 0; font-size:12px; color:#555;">{retry_line}</td>
        </tr>
        <tr>
          <td style="padding:3px 0; font-size:12px; color:#999;">Corrida compensatoria</td>
          <td style="padding:3px 0; font-size:12px; color:#555;">
            {"✓ Ejecutada" if compensatory_ran else "No ejecutada"}
          </td>
        </tr>
      </table>
    </td>
  </tr>

  {tech_section}

  <!-- Footer -->
  <tr>
    <td style="padding:10px 20px; font-size:11px; color:#bbb;
               border-top:1px solid #eee; border-radius:0 0 6px 6px;">
      Thai Thai Ads Agent &nbsp;·&nbsp; Notificación de incidente operativo
    </td>
  </tr>

</table>
</body>
</html>"""


def send_operational_incident_email(
    session_id: str,
    incident_reason: str,
    retry_attempted: bool = False,
    compensatory_ran: bool = False,
    system_restored: bool = False,
    technical_detail: str = "",
    timestamp_merida: str = "",
) -> bool:
    """
    Envía correo de incidente operativo cuando la auditoría diaria no pudo ejecutarse.
    No debe confundirse con el correo diario normal — tiene asunto y diseño distintos.
    """
    from config.agent_config import (
        EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
        EMAIL_FROM, EMAIL_FROM_NAME, EMAIL_TO,
        GMAIL_APP_PASSWORD,
    )
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not GMAIL_APP_PASSWORD:
        logger.warning("send_operational_incident_email: GMAIL_APP_PASSWORD no configurado")
        return False

    ts = timestamp_merida or _now_merida_str() if "_now_merida_str" in dir() else "—"
    subject = f"[Thai Thai Agente] ⚠ Incidente operativo — Auditoría no ejecutada · {ts}"

    html_body = _build_incident_email_html(
        incident_reason=incident_reason,
        retry_attempted=retry_attempted,
        compensatory_ran=compensatory_ran,
        system_restored=system_restored,
        technical_detail=technical_detail,
        timestamp_merida=ts,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        logger.info("send_operational_incident_email: enviado — sesión=%s", session_id)
        return True
    except Exception as exc:
        logger.error("send_operational_incident_email: error SMTP — %s", exc)
        return False


# ============================================================================
# INTELIGENCIA CRUZADA DIARIA — Claude Haiku
# ============================================================================

def generate_daily_insight(
    ads_data: dict | None,
    ga4_data: dict | None,
    sheets_data: dict | None,
    local_data: dict | None = None,
) -> str | None:
    """
    Pasa Ads + GA4 + Sheets a Claude Haiku y devuelve UNA oración ejecutiva
    correlacionando los tres bloques de datos para el dueño.

    Retorna None si faltan datos suficientes o si Haiku no responde.
    """
    import os
    import anthropic as _anthropic

    _spend    = float((ads_data or {}).get("spend_mxn", 0) or 0)
    _conv     = float((ads_data or {}).get("conversions", 0) or 0)
    _pedir    = int((ga4_data or {}).get("click_pedir", 0) or 0)
    _reservar = int((ga4_data or {}).get("click_reservar", 0) or 0)
    _views    = int((ga4_data or {}).get("page_views", 0) or 0)

    # Nuevo formato: resumen_negocio_para_agente
    _sd = sheets_data or {}
    _coms           = _sd.get("comensales_total")          # personas en restaurante
    _venta_local    = float(_sd.get("venta_local_total", 0) or 0)      # tarjeta+efectivo
    _venta_del_neto = float(_sd.get("venta_plataformas_neto", 0) or 0) # post-comisión
    _comision_pct   = float(_sd.get("comision_delivery_pct", 0) or 0)
    _ticket         = float(_sd.get("ingreso_por_comensal", 0) or 0)

    # Necesitamos al menos un dato de cada fuente para que el cruce tenga sentido
    has_ads    = _spend > 0 or _conv > 0
    has_ga4    = _pedir > 0 or _reservar > 0 or _views > 0
    has_sheets = _coms is not None
    if not (has_ads and (has_ga4 or has_sheets)):
        return None

    _clics_web = _pedir + _reservar

    # Descripción de ventas con formato nuevo
    _sheets_parts = []
    if _coms is not None:
        _sheets_parts.append(f"{int(_coms)} comensales en restaurante")
        if _ticket > 0:
            _sheets_parts.append(f"ticket promedio ${_ticket:,.0f}")
    if _venta_local > 0:
        _sheets_parts.append(f"venta local ${_venta_local:,.0f} (tarjeta+efectivo)")
    if _venta_del_neto > 0:
        _sheets_parts.append(
            f"delivery neto ${_venta_del_neto:,.0f} (después de {_comision_pct:.0f}% comisión plataformas)"
        )
    _sheets_str = ", ".join(_sheets_parts) if _sheets_parts else "sin dato de ventas"

    if _conv > 0:
        _ads_str = (
            f"Hoy gastamos ${_spend:.0f} MXN en Ads y obtuvimos {_conv:.0f} conversiones "
            f"(CPA ${_spend / _conv:.0f} MXN)"
        )
    else:
        _ads_str = f"Hoy gastamos ${_spend:.0f} MXN en Ads sin conversiones registradas"

    # Contexto de campaña Local (acciones físicas en Google Maps)
    _local_str = ""
    _ldir   = int((local_data or {}).get("local_directions_count", 0) or 0)
    _lspend = float((local_data or {}).get("local_campaign_spend", 0) or 0)
    if _ldir > 0 and _lspend > 0:
        _cpd = _lspend / _ldir
        _local_str = (
            f" Además, la campaña Local (Google Maps) invirtió ${_lspend:.0f} MXN "
            f"y generó {_ldir} intenciones de visita física ('Cómo llegar' + Store visits), "
            f"equivalente a un costo por auto en camino al restaurante de ${_cpd:.0f} MXN. "
            "Nota importante: estas acciones ocurren en Google Maps, no en la web, "
            "por eso no aparecen en GA4 — es normal y esperado."
        )

    _CONTEXTO_NEGOCIO = (
        "CONTEXTO DE NEGOCIO — Thai Thai, Mérida, Yucatán:\n"
        "Restaurante de comida tailandesa auténtica adaptada al paladar local. "
        "Mucha gente en Mérida no conoce la comida thai; hay que educar y atraer. "
        "Presupuesto de ads: $8,000 MXN/mes (subió de $6,000 en marzo, que fue bien). "
        "Objetivo: 40 comensales/día, 1,200/mes.\n\n"
        "DOS CANALES CON MÁRGENES DISTINTOS:\n"
        "1. RESTAURANTE (campaña Local): gente que VA al restaurante a comer. "
        "   Margen alto — sin comisiones. Se mide con comensales (col J), tarjeta+efectivo, "
        "   y 'Cómo llegar' en Google Maps. Conversiones en Google Ads, NO en GA4 (eso es normal).\n"
        "2. ONLINE (campañas Delivery + Reservaciones): gente que PIDE por thaithaimerida.com.mx. "
        "   Rappi/Uber cobran ~30% comisión ($200 bruto = $140 neto). "
        "   Se mide con GA4 click_ordenar_online, click_reservar, y ventas en plataformas. "
        "   Aunque el margen es menor, delivery amplía el alcance a gente que no vendría al restaurante.\n"
        "Ambos canales son valiosos. El agente debe optimizar los dos, no sacrificar uno por el otro.\n\n"
    )

    _prompt = (
        _CONTEXTO_NEGOCIO
        + "DATOS DE HOY:\n"
        + f"{_ads_str}. "
        + f"Web (GA4): {_views} vistas, {_clics_web} clics de intención "
        + f"(pedir: {_pedir}, reservar: {_reservar}). "
        + f"Corte de caja: {_sheets_str}."
        + (_local_str if _local_str else "")
        + "\n\nEscribe UNA SOLA oración ejecutiva correlacionando estos datos para el dueño. "
        "Menciona si el canal restaurante, el canal online, o ambos tuvieron buen desempeño. "
        "Sin bullets, sin saltos de línea, sin markdown. Solo la oración."
    )

    try:
        _client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        _resp = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            messages=[{"role": "user", "content": _prompt}],
        )
        _text = (_resp.content[0].text or "").strip()
        # Truncar si el modelo se extendió (no debería, pero por seguridad)
        if len(_text) > 500:
            _text = _text[:300].rsplit(" ", 1)[0] + "."
        return _text if _text else None
    except Exception as _exc:
        import logging as _lg
        _lg.getLogger(__name__).warning("generate_daily_insight: Haiku no respondió — %s", _exc)
        return None


# ============================================================================
# RESUMEN DIARIO DE ACTIVIDAD
# ============================================================================

def _build_daily_summary_html(run: dict) -> str:
    """
    Construye el HTML del resumen diario de actividad del sistema.

    Diseño ejecutivo en dos capas:
      1. Capa operativa — qué pasó, qué significa, si hay algo que hacer.
      2. Capa técnica — detalle compacto al pie, no como mensaje principal.

    Campos obligatorios:
      - ¿Qué significa esto para mí hoy?
      - ¿Necesito hacer algo hoy?
      - Estado del sistema (si fue restablecido tras fallo).
    """
    rc              = run.get("result_class", "sin_acciones")
    detail          = run.get("detail", {})
    errors          = run.get("errors", [])
    system_restored = run.get("system_restored", False)
    campaigns       = run.get("campaigns_reviewed", 0)
    changes         = run.get("changes_executed", 0)
    blocked         = run.get("blocked_by_guard", 0)
    human_pending   = run.get("human_pending", 0)

    tracking = detail.get("tracking_signals", [])
    landing  = detail.get("landing_severity")
    geo      = detail.get("geo_issues", [])
    geo_unv  = detail.get("geo_unverified", 0)

    # Sección 1 — Salud de Canales
    _ads_24h      = run.get("ads_24h", {})
    _ads_spend    = float(_ads_24h.get("spend_mxn", 0) or 0)
    _ads_conv     = float(_ads_24h.get("conversions", 0) or 0)
    _landing_ms   = run.get("landing_response_ms")
    _ventas_ayer        = run.get("ventas_ayer", {}) or {}
    # Nuevo formato: resumen_negocio_para_agente
    _coms_ayer          = _ventas_ayer.get("comensales_total")          # personas en restaurante
    _coms_obj           = 35                                             # objetivo fijo diario
    _coms_prom          = _ventas_ayer.get("comensales_promedio_diario") # solo útil si days>1
    _venta_local        = float(_ventas_ayer.get("venta_local_total", 0) or 0)   # tarjeta+efectivo
    _venta_plat_bruto   = float(_ventas_ayer.get("venta_plataformas_bruto", 0) or 0)  # col H
    _venta_plat_neto    = float(_ventas_ayer.get("venta_plataformas_neto", 0) or 0)   # post-comisión
    _comision_del_pct   = float(_ventas_ayer.get("comision_delivery_pct", 0) or 0)
    _ingreso_por_coms   = float(_ventas_ayer.get("ingreso_por_comensal", 0) or 0)
    _venta_neta_prom    = float(_ventas_ayer.get("venta_neta_promedio_diario", 0) or 0)
    _por_canal          = _ventas_ayer.get("por_canal", []) or []

    # GA4 web traffic (Sección 0: Movimiento en la Web)
    _ga4_web      = run.get("ga4_web")
    _ga4_ok       = isinstance(_ga4_web, dict) and "error" not in _ga4_web and bool(_ga4_web)
    _ga4_views    = int(_ga4_web.get("page_views", 0) or 0)       if _ga4_ok else 0
    _ga4_pedir    = int(_ga4_web.get("click_pedir", 0) or 0)      if _ga4_ok else 0
    _ga4_reservar = int(_ga4_web.get("click_reservar", 0) or 0)   if _ga4_ok else 0
    _ga4_activos  = int(_ga4_web.get("usuarios_activos", 0) or 0) if _ga4_ok else 0
    _recently_approved = int(run.get("recently_approved_count", 0) or 0)
    _agent_insight = run.get("agent_insight")

    _smart_issues_email = detail.get("smart_issues", 0)

    # ── Configuración visual por resultado ──────────────────────────────────
    _cfg = {
        "sin_acciones": {
            "bg": "#e8f5e9", "color": "#2e7d32",
            "badge": "✓ Auditoría completada",
            "status_line": f"El agente revisó {campaigns} campañas. No encontró novedades.",
            "meaning": "Operación normal. Tus campañas estuvieron bajo supervisión. No ocurrió nada que requiera tu atención.",
            "action": "No.",
        },
        # Compatibilidad con registros históricos
        "sin_cambios": {
            "bg": "#e8f5e9", "color": "#2e7d32",
            "badge": "✓ Auditoría completada",
            "status_line": f"El agente revisó {campaigns} campañas. No encontró novedades.",
            "meaning": "Operación normal. Tus campañas estuvieron bajo supervisión. No ocurrió nada que requiera tu atención.",
            "action": "No.",
        },
        "con_observaciones": {
            "bg": "#fff8e1", "color": "#e65100",
            "badge": "◉ Auditoría completada — Con observaciones",
            "status_line": f"El agente revisó {campaigns} campañas y detectó {_smart_issues_email} hallazgo(s) en Smart Campaigns.",
            "meaning": (
                "No se ejecutaron cambios automáticos ni hay alertas urgentes en tracking o landing. "
                "Sin embargo, el agente detectó hallazgos en tus Smart Campaigns que conviene revisar."
            ),
            "action": "Revisar el detalle de Smart Campaigns más abajo.",
        },
        "con_cambios": {
            "bg": "#e3f2fd", "color": "#1565c0",
            "badge": "↗ Auditoría completada — Con cambios automáticos",
            "status_line": f"El agente revisó {campaigns} campañas y ejecutó {changes} cambio(s) automático(s).",
            "meaning": "El agente detectó oportunidades de bajo riesgo y actuó según sus reglas. Los cambios están registrados en el detalle técnico abajo.",
            "action": "Revisar los cambios aplicados en la sección de detalle. Si tienes dudas, el reporte del lunes los explica con contexto completo.",
        },
        "con_alertas": {
            "bg": "#fff3e0", "color": "#e65100",
            "badge": "⚠ Auditoría completada — Con alertas",
            "status_line": f"El agente revisó {campaigns} campañas y detectó situaciones que requieren atención.",
            "meaning": None,   # se construye dinámicamente
            "action": None,    # se construye dinámicamente
        },
        "con_errores": {
            "bg": "#fce4ec", "color": "#b71c1c",
            "badge": "✗ Auditoría diaria no completada",
            "status_line": "La auditoría diaria no se pudo ejecutar completamente.",
            "meaning": (
                "El agente no pudo hacer su revisión de hoy. "
                "Tus campañas siguieron corriendo normalmente en Google Ads, "
                "pero sin supervisión del agente durante esta corrida."
            ),
            "action": (
                "No hay acción urgente. Las campañas siguen activas sin cambios del agente. "
                + ("El sistema ya fue restablecido — la auditoría de mañana correrá normalmente."
                   if system_restored else
                   "Si el error persiste mañana, habrá que revisar el sistema.")
            ),
        },
    }

    run_type = run.get("run_type", "daily")
    cfg = _cfg.get(rc, _cfg["con_errores"])
    bg    = cfg["bg"]
    color = cfg["color"]
    badge = cfg["badge"]
    if run_type == "compensatory":
        badge = f"↺ Corrida compensatoria — {badge.lstrip('✓↗⚠✗ ')}"
        color = "#4527a0"   # púrpura — diferente a todos los estados normales
        bg    = "#ede7f6"

    # ── Texto operativo dinámico para alertas ────────────────────────────────
    if rc == "con_alertas":
        alert_lines = []
        action_lines = []
        if tracking:
            alert_lines.append(f"Señal de tracking anómala detectada ({', '.join(tracking)}).")
            action_lines.append("Revisar el panel de conversiones en Google Ads hoy.")
        if landing and landing not in (None, "ok"):
            alert_lines.append(f"Landing o Gloria Food con problema de acceso ({landing}).")
            action_lines.append("Verificar que thaithaimerida.com y Gloria Food respondan correctamente.")
        if any(str(g).startswith("GEO1") for g in geo):
            alert_lines.append("Campaña con geotargeting incorrecto detectado (GEO1 activo).")
            action_lines.append("Revisar y aprobar la corrección de geotargeting pendiente.")
        if human_pending:
            alert_lines.append(f"{human_pending} propuesta(s) esperando aprobación.")
            action_lines.append("Revisar propuestas pendientes en el sistema.")

        cfg["meaning"] = (
            " ".join(alert_lines) if alert_lines
            else "El agente detectó una o más situaciones fuera del rango normal."
        )
        cfg["action"] = (
            " ".join(action_lines) if action_lines
            else "Revisar las alertas en el detalle técnico abajo."
        )

    meaning = cfg["meaning"]
    action  = cfg["action"]

    # ── Bloque de restablecimiento del sistema ───────────────────────────────
    restored_block = ""
    if system_restored and rc != "con_errores":
        # Para errores ya se incluye en el texto de action
        restored_block = """
  <tr>
    <td style="padding:12px 20px 0 20px;">
      <div style="background:#e8f5e9; border-left:3px solid #2e7d32;
                  padding:10px 14px; border-radius:4px; font-size:13px; color:#2e7d32;">
        ✓ El sistema fue restablecido correctamente. La auditoría de mañana correrá normalmente.
      </div>
    </td>
  </tr>"""
    elif system_restored and rc == "con_errores":
        restored_block = """
  <tr>
    <td style="padding:12px 20px 0 20px;">
      <div style="background:#e8f5e9; border-left:3px solid #2e7d32;
                  padding:10px 14px; border-radius:4px; font-size:13px; color:#2e7d32;">
        ✓ Sistema ya restablecido — La auditoría de mañana correrá normalmente.
      </div>
    </td>
  </tr>"""

    # ── Tabla técnica compacta ───────────────────────────────────────────────
    def _tech_row(lbl, val, warn=False):
        vc = "#c62828" if warn else "#555"
        return (
            f"<tr>"
            f"<td style='padding:3px 12px; color:#999; font-size:12px; width:200px;'>{lbl}</td>"
            f"<td style='padding:3px 12px; color:{vc}; font-size:12px;'>{val}</td>"
            f"</tr>"
        )

    pending_parts = []
    if detail.get("keyword_pending"):
        pending_parts.append(f"{detail['keyword_pending']} keywords")
    if detail.get("ba_pending"):
        pending_parts.append(f"{detail['ba_pending']} presupuesto")

    issues_parts = []
    if tracking:
        issues_parts.append(f"Tracking: {', '.join(tracking)}")
    if landing and landing not in (None, "ok"):
        issues_parts.append(f"Landing: {landing}")
    if geo:
        issues_parts.append(f"GEO: {', '.join(str(g) for g in geo[:3])}")

    errors_str  = " · ".join(e[:120] for e in errors[:2]) if errors else "—"
    pending_str = ", ".join(pending_parts) if pending_parts else "—"
    issues_str  = " · ".join(issues_parts) if issues_parts else "—"
    modules_str = ", ".join(run.get("modules", []))

    # ── Cobertura real por tipo de campaña ──────────────────────────────────
    _c_search  = run.get("campaigns_search", 0)
    _c_smart   = run.get("campaigns_smart", 0)
    _c_total   = run.get("campaigns_reviewed", campaigns)
    _kw_eval   = run.get("keywords_evaluated", 0)
    _smart_iss = run.get("detail", {}).get("smart_issues", 0)

    # Línea de cobertura: "3 de 3 (Search: 1 · Smart: 2)"
    if _c_search or _c_smart:
        _coverage_str = f"{_c_total} de 3 — Search: {_c_search} · Smart: {_c_smart}"
    else:
        _coverage_str = str(_c_total)

    # Bloque de hallazgos Smart — inline, sin remitir al reporte semanal
    _smart_audit_data = run.get("smart_audit") or {}
    _smart_camps_with_issues = [
        c for c in (_smart_audit_data.get("campaigns") or [])
        if c.get("issues_count", 0) > 0
    ] if isinstance(_smart_audit_data, dict) else []
    _smart_removals = run.get("smart_removals") or []

    # ── Bloque de inteligencia cruzada (🧠 Lectura del Agente) ──────────────
    if _agent_insight:
        _insight_block = f"""
  <tr>
    <td style="padding:14px 20px 6px 20px;">
      <div style="background:#f0f9ff; border-left:3px solid #0284c7;
                  padding:12px 16px; border-radius:4px;">
        <p style="margin:0 0 4px 0; font-size:11px; font-weight:bold; color:#0369a1;
                  text-transform:uppercase; letter-spacing:0.5px;">
          🧠 Lectura del Agente
        </p>
        <p style="margin:0; font-size:14px; color:#1e3a5f; line-height:1.5;
                  font-style:italic;">
          {_agent_insight}
        </p>
      </div>
    </td>
  </tr>"""
    else:
        _insight_block = ""

    _smart_block = ""
    if _smart_iss > 0 or _smart_camps_with_issues or _smart_removals:
        _sc_rows = ""

        # ── Resultados de limpieza autónoma (si el Agente eliminó temas) ────
        for _rmv in _smart_removals:
            _rmv_name = _rmv.get("campaign_name", "—")
            _rmv_ok   = _rmv.get("removed_ok", [])
            _rmv_err  = _rmv.get("removed_err", [])
            _rmv_stat = _rmv.get("status", "")

            if _rmv_stat == "guard_blocked":
                _sc_rows += (
                    f'<tr style="border-bottom:1px solid #d1fae5;">'
                    f'<td style="padding:8px 0;">'
                    f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                    f'⚠️ {_rmv_name}</p>'
                    f'<p style="margin:0;font-size:12px;color:#92400e;">'
                    f'{_rmv.get("message", "Limpieza omitida por guarda de seguridad.")}</p>'
                    f'</td></tr>'
                )
            elif _rmv_ok:
                _themes_str = ", ".join(f'"{t}"' for t in _rmv_ok[:5])
                if len(_rmv_ok) > 5:
                    _themes_str += f" y {len(_rmv_ok) - 5} más"
                _sc_rows += (
                    f'<tr style="border-bottom:1px solid #d1fae5;">'
                    f'<td style="padding:8px 0;">'
                    f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                    f'✅ Limpieza Estratégica — {_rmv_name}</p>'
                    f'<p style="margin:0;font-size:12px;color:#065f46;">'
                    f'El Agente eliminó {len(_rmv_ok)} tema(s) de desperdicio real ({_themes_str}). '
                    f'Este presupuesto ahora está libre para que Google Ads lo invierta en '
                    f'búsquedas que sí generan clientes y reservaciones.</p>'
                    f'{"<p style=margin:2px 0 0 0;font-size:11px;color:#dc2626;>" + str(len(_rmv_err)) + " tema(s) no se pudieron eliminar — revisar logs.</p>" if _rmv_err else ""}'
                    f'</td></tr>'
                )

        # ── Issues detectados (sin resolución automática) ────────────────────
        for _sc in _smart_camps_with_issues:
            _sc_name = _sc.get("campaign_name", "—")
            # Omitir issues de keyword_themes si ya fueron resueltos por limpieza
            _resolved_cids = {r.get("campaign_id") for r in _smart_removals if r.get("status") == "executed"}
            for _iss in _sc.get("issues", []):
                if _iss.get("check") == "keyword_themes" and _sc.get("campaign_id") in _resolved_cids:
                    continue  # ya limpiado — no duplicar en hallazgos
                _iss_signal = _iss.get("signal", "—")
                _iss_desc   = _iss.get("description", "—")
                _iss_sev    = _iss.get("severity", "warning")
                _iss_color  = "#dc2626" if _iss_sev == "critical" else "#d97706"
                _iss_icon   = "🔴" if _iss_sev == "critical" else "🟡"
                _sc_rows += (
                    f'<tr style="border-bottom:1px solid #fef3c7;">'
                    f'<td style="padding:8px 0;">'
                    f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                    f'{_iss_icon} {_sc_name}</p>'
                    f'<p style="margin:0 0 1px 0;font-size:11px;color:{_iss_color};font-weight:bold;">'
                    f'{_iss_signal}</p>'
                    f'<p style="margin:0;font-size:12px;color:#374151;">{_iss_desc}</p>'
                    f'</td></tr>'
                )

        if _sc_rows:
            _header_label = f"⚠ Smart Campaigns — {_smart_iss} hallazgo(s)" if _smart_iss > 0 else "✅ Smart Campaigns — limpieza ejecutada"
            _smart_block = (
                f'<tr><td style="padding:14px 20px 4px 20px;">'
                f'<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'{_header_label}</p>'
                f'<table width="100%" cellpadding="0" cellspacing="0">{_sc_rows}</table>'
                f'</td></tr>'
            )

    # Bloque GEO sin verificar — explica qué es y qué revisar (no solo un contador)
    _geo_unv_camps = run.get("geo_unverified_campaigns") or []
    # Fallback: si main.py todavía no pasa el campo, omitir silenciosamente
    _geo_unv_block = ""
    if _geo_unv_camps:
        _guv_rows = ""
        for _guv in _geo_unv_camps:
            _guv_name = _guv.get("campaign_name", "—")
            _guv_rows += (
                f'<tr style="border-bottom:1px solid #e0f2fe;">'
                f'<td style="padding:7px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                f'📍 {_guv_name}</p>'
                f'<p style="margin:0;font-size:12px;color:#374151;">'
                f'La API confirma geotargeting correcto. Verifica que el <strong>Área de entrega</strong> '
                f'en la UI de Google Ads Express coincida con Mérida: '
                f'Google Ads → {_guv_name} → Configuración → Área de entrega.</p>'
                f'</td></tr>'
            )
        _geo_unv_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">'
            f'🗺 GEO sin confirmar ({len(_geo_unv_camps)})</p>'
            f'<div style="background:#e0f2fe;border-left:3px solid #0284c7;padding:8px 10px;'
            f'border-radius:3px;font-size:12px;color:#0c4a6e;margin-bottom:8px;">'
            f'ℹ️ La API dice que estas Smart Campaigns apuntan a la ubicación correcta, '
            f'pero la interfaz Express de Google Ads no se puede verificar automáticamente. '
            f'No es un error — es una confirmación pendiente de tu parte.'
            f'</div>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_guv_rows}</table>'
            f'</td></tr>'
        )

    # ── Botones de aprobación / rechazo ─────────────────────────────────────────
    from config.agent_config import APPROVAL_BASE_URL as _appr_base

    def _approval_buttons(token: str) -> str:
        if not token:
            return ""
        _a = f"{_appr_base}/approve?d={token}&action=approve"
        _r = f"{_appr_base}/approve?d={token}&action=reject"
        return (
            f'<a href="{_a}" style="display:inline-block;background:#16a34a;color:#fff;'
            f'padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px;'
            f'font-weight:bold;margin-right:6px;">✓ Aprobar</a>'
            f'<a href="{_r}" style="display:inline-block;background:#dc2626;color:#fff;'
            f'padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px;'
            f'font-weight:bold;">✗ Rechazar</a>'
        )

    # ── SECCIÓN 1: Salud de Canales ──────────────────────────────────────────────
    # Google Ads card
    _ads_cpa = round(_ads_spend / _ads_conv, 0) if _ads_conv > 0 else None
    _ads_val = f"<strong>${_ads_spend:,.0f}</strong> · {_ads_conv:.0f} conv"
    _ads_sub = (
        f"CPA: ${_ads_cpa:,.0f}"
        if _ads_cpa
        else ("Sin gasto" if _ads_spend == 0 else "Sin conversiones")
    )

    # Landing card — diagnóstico completo
    if landing in (None, "ok"):
        _land_icon, _land_label, _land_color = "✅", "OK", "#16a34a"
        _land_status_text = "Funcional"
    elif landing == "warning":
        _land_icon, _land_label, _land_color = "⚠️", "Lento", "#d97706"
        _land_status_text = "Respuesta lenta"
    else:
        _land_icon, _land_label, _land_color = "🔴", "Error", "#dc2626"
        _land_status_text = "Error / No disponible"
    _ms_display = f"{_landing_ms} ms" if _landing_ms else "—"
    _land_val = f"<strong style='color:{_land_color};'>{_land_icon} {_land_label}</strong>"
    _land_sub = f"Carga: {_ms_display} · Estado: {_land_status_text}"

    # ── Card: Comensales (restaurante físico — campaña Local) ───────────────
    if _coms_ayer is None:
        _ven_val = "<span style='color:#9ca3af;'>N/D</span>"
        _ven_sub = "Sheets no disponible"
    elif _coms_ayer >= _coms_obj:
        _ven_val = f"<strong style='color:#16a34a;'>{_coms_ayer}</strong> / {_coms_obj} obj 🟢"
        _ven_sub = f"Sobre objetivo · ticket ${_ingreso_por_coms:,.0f}" if _ingreso_por_coms else "Sobre objetivo"
    elif _coms_ayer >= 30:
        _ven_val = f"<strong style='color:#d97706;'>{_coms_ayer}</strong> / {_coms_obj} obj 🟡"
        _ven_sub = f"Bajo objetivo · ticket ${_ingreso_por_coms:,.0f}" if _ingreso_por_coms else "Bajo objetivo"
    else:
        _ven_val = f"<strong style='color:#dc2626;'>{_coms_ayer}</strong> / {_coms_obj} obj 🔴"
        _ven_sub = f"Bajo equilibrio · ticket ${_ingreso_por_coms:,.0f}" if _ingreso_por_coms else "Bajo equilibrio"

    # ── Card: Venta local (tarjeta + efectivo) ──────────────────────────────
    if _venta_local > 0:
        _vlocal_val = f"<strong>${_venta_local:,.0f}</strong>"
        _vlocal_sub = "Tarjeta + efectivo"
    else:
        _vlocal_val = "<span style='color:#9ca3af;'>N/D</span>"
        _vlocal_sub = "Sin dato"

    # ── Card: Delivery (plataformas) ────────────────────────────────────────
    if _venta_plat_bruto > 0:
        _del_val = f"<strong>${_venta_plat_neto:,.0f}</strong> neto"
        _del_sub = f"Bruto ${_venta_plat_bruto:,.0f} · comisión {_comision_del_pct:.0f}%"
    else:
        _del_val = "<span style='color:#9ca3af;'>N/D</span>"
        _del_sub = "Sin pedidos delivery"

    def _card(icon_label: str, val: str, sub: str) -> str:
        return (
            f'<td style="padding:8px 10px;background:#f9fafb;border:1px solid #e5e7eb;'
            f'border-radius:5px;text-align:center;vertical-align:top;">'
            f'<p style="margin:0 0 3px 0;font-size:11px;color:#6b7280;font-weight:bold;">{icon_label}</p>'
            f'<p style="margin:0 0 2px 0;font-size:13px;color:#111;">{val}</p>'
            f'<p style="margin:0;font-size:11px;color:#9ca3af;">{sub}</p>'
            f'</td>'
        )

    # ── Desglose por canal (Rappi, Uber, BBVA, etc.) ────────────────────────
    if _por_canal:
        _canal_rows = ""
        for _c in _por_canal[:8]:  # max 8 canales
            _f   = _c.get("fuente", "—")
            _n   = float(_c.get("neto", 0))
            _b   = float(_c.get("bruto", 0))
            _pct = float(_c.get("comision_pct", 0))
            if _pct > 0:
                _canal_detail = f"${_n:,.0f} neto · {_pct:.0f}% comisión"
            else:
                _canal_detail = f"${_n:,.0f} neto"
            _canal_rows += (
                f'<tr style="border-top:1px solid #f0f0f0;">'
                f'<td style="padding:5px 8px;color:#374151;font-size:12px;">{_f}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:bold;">'
                f'${_b:,.0f}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;color:#6b7280;">'
                f'{_canal_detail}</td>'
                f'</tr>'
            )
        _canales_block = f"""
  <tr><td style="padding:8px 20px 14px 20px;">
    <p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;
              text-transform:uppercase;letter-spacing:0.5px;">💳 Desglose por Canal</p>
    <table width="100%" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#f9fafb;">
        <th style="text-align:left;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Canal</th>
        <th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Bruto</th>
        <th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Neto / Comisión</th>
      </tr>
      {_canal_rows}
    </table>
  </td></tr>"""
    else:
        _canales_block = ""

    _seccion1_block = (
        '<tr><td style="padding:14px 20px 6px 20px;">'
        '<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
        'text-transform:uppercase;letter-spacing:0.5px;">📊 Salud de Canales — Hoy</p>'
        '<table width="100%" cellpadding="0" cellspacing="4">'
        '<tr>'
        + _card("📢 Google Ads 24h", _ads_val, _ads_sub)
        + '<td style="width:4px;"></td>'
        + _card("🌐 Landing", _land_val, _land_sub)
        + '<td style="width:4px;"></td>'
        + _card("🍽️ Comensales", _ven_val, _ven_sub)
        + '<td style="width:4px;"></td>'
        + _card("🏪 Venta Local", _vlocal_val, _vlocal_sub)
        + '<td style="width:4px;"></td>'
        + _card("🛵 Delivery", _del_val, _del_sub)
        + '</tr></table>'
        '</td></tr>'
        + _canales_block
    )

    # ── GA4: Movimiento en la Web (24h) — tabla siempre visible ─────────────────
    def _ga4_val(v: int) -> str:
        return "N/A" if not _ga4_ok else str(v)

    _ga4_block = (
        '<tr><td style="padding:14px 20px 8px 20px;">'
        '<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
        'text-transform:uppercase;letter-spacing:0.5px;">🌍 Movimiento en la Web (24h)</p>'
        + (
            '<p style="margin:0 0 6px 0;font-size:11px;color:#9ca3af;font-style:italic;">'
            'GA4 no disponible para este período — valores mostrados como referencia</p>'
            if not _ga4_ok else ''
        )
        + '<table width="100%" style="border-collapse:collapse;font-size:13px;">'
        '<tr style="background:#f9fafb;">'
        '<th style="text-align:left;padding:5px 8px;color:#6b7280;font-size:11px;'
        'font-weight:bold;border-bottom:1px solid #e5e7eb;">Evento GA4</th>'
        '<th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;'
        'font-weight:bold;border-bottom:1px solid #e5e7eb;">Conteo (24h)</th>'
        '</tr>'
        f'<tr style="border-top:1px solid #f0f0f0;">'
        f'<td style="padding:6px 8px;color:#374151;">👥 usuarios_activos</td>'
        f'<td style="text-align:right;padding:6px 8px;font-weight:bold;color:#111;">'
        f'{_ga4_val(_ga4_activos)}</td></tr>'
        f'<tr style="border-top:1px solid #f0f0f0;">'
        f'<td style="padding:6px 8px;color:#374151;">🛒 click_ordenar_online</td>'
        f'<td style="text-align:right;padding:6px 8px;font-weight:bold;color:#111;">'
        f'{_ga4_val(_ga4_pedir)}</td></tr>'
        f'<tr style="border-top:1px solid #f0f0f0;">'
        f'<td style="padding:6px 8px;color:#374151;">📅 click_reservar</td>'
        f'<td style="text-align:right;padding:6px 8px;font-weight:bold;color:#111;">'
        f'{_ga4_val(_ga4_reservar)}</td></tr>'
        '</table>'
        '</td></tr>'
    )

    # ── SECCIÓN 2: Propuestas Keywords ───────────────────────────────────────────
    _kw_proposals = run.get("keyword_proposals", [])
    _kw_block = ""
    if _kw_proposals:
        _rows = ""
        for _p in _kw_proposals:
            _kw_text  = str(_p.get("keyword") or _p.get("text", "—"))
            _camp     = str(_p.get("campaign_name") or _p.get("campaign", "—"))
            _spend    = float(_p.get("spend", 0))
            _conv     = float(_p.get("conversions", 0))
            _urgency  = str(_p.get("urgency", "normal"))
            _reason   = str(_p.get("reason", ""))[:120]
            _token    = str(_p.get("approval_token", ""))
            _cpa      = round(_spend / _conv, 0) if _conv > 0 else None
            _cpa_txt  = f"CPA: ${_cpa:,.0f}" if _cpa else "sin conversiones"
            _urg_map  = {"critical": ("🔴", "#dc2626"), "urgent": ("🟡", "#d97706"), "normal": ("⚪", "#6b7280")}
            _ui, _uc  = _urg_map.get(_urgency, ("⚪", "#6b7280"))
            _rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'{_ui} {_kw_text}</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'📢 {_camp} &nbsp;·&nbsp; {_cpa_txt} &nbsp;·&nbsp; Gasto 30d: ${_spend:,.0f}</p>'
                f'<p style="margin:0 0 8px 0;font-size:12px;color:#374151;">{_reason}</p>'
                + _approval_buttons(_token)
                + f'</td></tr>'
            )
        _kw_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">🔑 Propuestas — Keywords ({len(_kw_proposals)})</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_rows}</table>'
            f'</td></tr>'
        )

    # ── SECCIÓN 2: Propuestas Presupuesto ────────────────────────────────────────
    _ba_proposals = run.get("budget_proposals", [])
    _ba_block = ""
    if _ba_proposals:
        _rows = ""
        for _p in _ba_proposals:
            _camp     = str(_p.get("campaign_name", "—"))
            _cpa_r    = float(_p.get("cpa_real", 0))
            _cpa_max  = float(_p.get("cpa_max", 0)) or float(_p.get("cpa_critical", 0))
            _curr_b   = float(_p.get("daily_budget_mxn", 0))
            _sug_b    = float(_p.get("suggested_daily_budget", 0))
            _token    = str(_p.get("approval_token", ""))
            _reason   = str(_p.get("reason", ""))[:120]
            _is_shared = bool(_p.get("budget_explicitly_shared", False))
            _savings  = round((_curr_b - _sug_b) * 30) if _curr_b > _sug_b else 0
            _sav_html = (
                f'<p style="margin:0 0 4px 0;font-size:11px;color:#16a34a;font-weight:bold;">'
                f'💰 Ahorro estimado: ${_savings:,}/mes</p>'
            ) if _savings > 0 else ""
            # Presupuesto compartido: botón especial que ejecuta separación + asignación
            if _is_shared:
                _sug_txt = f"${_sug_b:,.0f}" if _sug_b else "monto sugerido"
                _a_url = f"{_appr_base}/approve?d={_token}&action=approve"
                _r_url = f"{_appr_base}/approve?d={_token}&action=reject"
                _action_html = (
                    f'<div style="margin-top:6px;padding:8px 10px;background:#eff6ff;'
                    f'border-left:3px solid #3b82f6;border-radius:3px;font-size:12px;color:#1e40af;'
                    f'margin-bottom:6px;">'
                    f'ℹ️ El CPA está alto y el presupuesto es compartido. El Agente separará esta '
                    f'campaña con su propio presupuesto de <strong>{_sug_txt}/día</strong> '
                    f'sin afectar a las demás campañas.'
                    f'</div>'
                    f'<a href="{_a_url}" style="display:inline-block;background:#1d4ed8;color:#fff;'
                    f'padding:5px 12px;border-radius:4px;text-decoration:none;font-size:12px;'
                    f'font-weight:bold;margin-right:6px;">✂️ Separar Presupuesto y Ajustar a {_sug_txt}</a>'
                    f'<a href="{_r_url}" style="display:inline-block;background:#dc2626;color:#fff;'
                    f'padding:5px 12px;border-radius:4px;text-decoration:none;font-size:12px;'
                    f'font-weight:bold;">✗ Rechazar</a>'
                )
            else:
                _action_html = _approval_buttons(_token)
            _rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'📊 {_camp}</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'CPA real: <strong>${_cpa_r:,.0f}</strong> · Límite: ${_cpa_max:,.0f}'
                f' &nbsp;·&nbsp; Presupuesto: ${_curr_b:,.0f} → ${_sug_b:,.0f}/día</p>'
                + _sav_html
                + f'<p style="margin:0 0 8px 0;font-size:12px;color:#374151;">{_reason}</p>'
                + _action_html
                + f'</td></tr>'
            )
        _ba_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">📉 Propuestas — Presupuesto ({len(_ba_proposals)})</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_rows}</table>'
            f'</td></tr>'
        )

    # ── SECCIÓN 2B: Oportunidades de Escalamiento (BA2) ─────────────────────────
    _ba2_proposals = run.get("ba2_proposals", [])
    _ba2_freed = float(run.get("ba2_freed_budget_mxn", 0.0))
    _ba2_block = ""
    if _ba2_proposals:
        _rows = ""
        for _p2 in _ba2_proposals:
            _camp2     = str(_p2.get("campaign_name", "—"))
            _signal2   = str(_p2.get("signal", "BA2_SCALE"))
            _cpa2      = float(_p2.get("cpa_actual", 0))
            _cpa_ideal = float(_p2.get("cpa_ideal", 0))
            _curr_b2   = float(_p2.get("current_daily_budget_mxn", 0))
            _new_b2    = float(_p2.get("suggested_daily_budget_mxn", 0))
            _inc2      = float(_p2.get("increase_mxn", 0))
            _util2     = float(_p2.get("utilization_rate", 0))
            _days2     = _p2.get("days_active", "?")
            _src2      = str(_p2.get("fund_source", ""))
            _evd2      = int(_p2.get("evidence_days", 14))
            _conv2     = float(_p2.get("conversions", 0))

            if _signal2 == "BA2_REALLOC":
                _signal_badge = (
                    '<span style="background:#dcfce7;color:#15803d;padding:2px 6px;'
                    'border-radius:3px;font-size:10px;font-weight:bold;">REALLOC · $0 neto</span>'
                )
                _action_line = (
                    f'<p style="margin:4px 0 8px 0;font-size:12px;color:#15803d;">'
                    f'♻️ {_src2}. Ajusta el presupuesto en Google Ads.</p>'
                )
            else:
                _signal_badge = (
                    '<span style="background:#fef9c3;color:#854d0e;padding:2px 6px;'
                    'border-radius:3px;font-size:10px;font-weight:bold;">SCALE · nueva inversión</span>'
                )
                _action_line = (
                    f'<p style="margin:4px 0 8px 0;font-size:12px;color:#854d0e;">'
                    f'📈 {_src2}. Evalúa si quieres autorizar esta inversión.</p>'
                )

            _rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 4px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'🚀 {_camp2} &nbsp;{_signal_badge}</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'CPA: <strong>${_cpa2:,.0f}</strong> (ideal: ${_cpa_ideal:,.0f})'
                f' &nbsp;·&nbsp; Conv: {_conv2:.0f} en {_evd2}d'
                f' &nbsp;·&nbsp; Utilización: {_util2 * 100:.0f}%'
                f' &nbsp;·&nbsp; {_days2}d activa</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'Presupuesto actual: ${_curr_b2:,.0f}/día → sugerido: '
                f'<strong>${_new_b2:,.0f}/día</strong> (+${_inc2:,.0f})</p>'
                + _action_line
                + f'</td></tr>'
            )
        _freed_note = (
            f'<p style="margin:0 0 6px 0;font-size:11px;color:#15803d;">'
            f'💡 Fondos liberados por BA1 disponibles: <strong>${_ba2_freed:,.0f} MXN/día</strong></p>'
        ) if _ba2_freed > 0 else ""
        _ba2_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">🚀 Oportunidades de Escalamiento ({len(_ba2_proposals)})</p>'
            + _freed_note
            + f'<table width="100%" cellpadding="0" cellspacing="0">{_rows}</table>'
            f'</td></tr>'
        )

    # ── SECCIÓN 2C: Decisiones AI (Claude Haiku) ────────────────────────────────
    _ai_decisions = run.get("ai_decisions", []) or []
    _ai_block = ""
    _ai_executed = [d for d in _ai_decisions if d.get("exec_result", {}).get("status") == "executed"]

    # Línea de contexto del día (ocupación histórica)
    _occ_ctx = run.get("occupancy_context") or {}
    _occ_context_line = ""
    if _occ_ctx.get("data_sufficient") and _occ_ctx.get("today"):
        _occ_level_colors = {"BAJO": "#dc2626", "MEDIO": "#d97706", "ALTO": "#15803d"}
        _occ_lv = _occ_ctx.get("today_level", "")
        _occ_color = _occ_level_colors.get(_occ_lv, "#6b7280")
        _occ_context_line = (
            f'<tr><td style="padding:4px 20px 0 20px;">'
            f'<p style="margin:0;font-size:11px;color:#6b7280;">'
            f'📅 Contexto del día: <strong>{_occ_ctx["today"]}</strong>'
            f' — ocupación histórica '
            f'<strong style="color:{_occ_color};">{_occ_ctx["today_occupancy_pct"]}%</strong>'
            f' ({_occ_ctx["today_avg_comensales"]} comensales avg)'
            f' — Nivel <strong style="color:{_occ_color};">{_occ_lv}</strong>'
            f'</p></td></tr>'
        )

    # La línea de ocupación se muestra siempre que haya datos, independiente de si Haiku ejecutó algo
    if _occ_context_line:
        _ai_block = _occ_context_line

    if _ai_executed:
        _ai_rows = ""
        for _d in _ai_executed:
            _d_action  = str(_d.get("action", "hold"))
            _d_name    = str(_d.get("campaign_name", "—"))
            _d_budget  = float(_d.get("new_budget_mxn", 0))
            _d_pct     = float(_d.get("change_pct", 0))
            _d_reason  = str(_d.get("reason", ""))[:160]
            _d_conf    = int(_d.get("confidence", 0))
            _d_old     = float(_d.get("exec_result", {}).get("old_budget_mxn", 0))
            _d_color   = "#15803d" if _d_action == "scale" else "#dc2626"
            _d_arrow   = "↑" if _d_action == "scale" else "↓"
            _d_conf_color = "#15803d" if _d_conf >= 80 else "#d97706" if _d_conf >= 70 else "#dc2626"
            _ai_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 3px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'🧠 {_d_name}'
                f'<span style="margin-left:8px;background:{_d_color}20;color:{_d_color};'
                f'padding:2px 6px;border-radius:3px;font-size:10px;font-weight:bold;">'
                f'{_d_arrow} {_d_action.upper()}</span></p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'${_d_old:,.0f} → <strong style="color:{_d_color};">${_d_budget:,.0f}/día</strong>'
                f' &nbsp;({_d_pct:+.0f}%)'
                f' &nbsp;·&nbsp; Confianza: <strong style="color:{_d_conf_color};">{_d_conf}%</strong></p>'
                f'<p style="margin:0 0 0 0;font-size:12px;color:#374151;">{_d_reason}</p>'
                f'</td></tr>'
            )
        _ai_block += (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">'
            f'🧠 Decisiones AI — Claude Haiku ({len(_ai_executed)} ejecutada(s))</p>'
            f'<p style="margin:0 0 8px 0;font-size:11px;color:#6b7280;">'
            f'El agente cruzó datos de Ads + Sheets + GA4 y tomó estas decisiones automáticamente.</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_ai_rows}</table>'
            f'</td></tr>'
        )

    # ── SECCIÓN 2D: Keywords agregadas por AI ───────────────────────────────────
    _kw_ai_decisions = run.get("ai_keyword_decisions", []) or []
    _kw_executed = [d for d in _kw_ai_decisions if d.get("exec_result", {}).get("status") == "executed"]
    if _kw_executed:
        _kw_rows = ""
        for _kd in _kw_executed:
            _kd_text   = str(_kd.get("keyword_text", "—"))
            _kd_camp   = str(_kd.get("exec_result", {}).get("campaign_name", _kd.get("campaign_id", "—")))
            _kd_conf   = int(_kd.get("confidence", 0))
            _kd_reason = str(_kd.get("reason", ""))[:160]
            _kd_match  = str(_kd.get("match_type", "PHRASE"))
            _kd_conf_color = "#15803d" if _kd_conf >= 85 else "#d97706"
            _kw_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 3px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'🔑 &ldquo;{_kd_text}&rdquo;'
                f'<span style="margin-left:8px;background:#0369a120;color:#0369a1;'
                f'padding:2px 6px;border-radius:3px;font-size:10px;font-weight:bold;">'
                f'{_kd_match}</span></p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'Agregada a: <strong>{_kd_camp}</strong>'
                f' &nbsp;·&nbsp; Confianza: <strong style="color:{_kd_conf_color};">{_kd_conf}%</strong></p>'
                f'<p style="margin:0;font-size:12px;color:#374151;">{_kd_reason}</p>'
                f'</td></tr>'
            )
        _kw_ai_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">'
            f'🔑 Keywords agregadas por AI ({len(_kw_executed)})</p>'
            f'<p style="margin:0 0 8px 0;font-size:11px;color:#6b7280;">'
            f'Haiku analizó el Keyword Planner + rendimiento actual y agregó estas keywords a tus campañas Search.</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_kw_rows}</table>'
            f'</td></tr>'
        )
        _ai_block = _ai_block + _kw_ai_block

    # ── SECCIÓN 3: Alertas GEO ───────────────────────────────────────────────────
    _geo_alerts_email = run.get("geo_issues_for_email", [])
    _geo_email_block = ""
    if _geo_alerts_email:
        # Radios esperados por campaña (confirmación de configuración)
        _geo_radio_map = {
            "delivery":  "8 km (PROXIMITY)",
            "local":     "15 km (PROXIMITY)",
            "reserva":   "Zona Mérida (LOCATION)",
        }
        _rows = ""
        for _g in _geo_alerts_email:
            _camp   = str(_g.get("campaign_name", "—"))
            _signal = str(_g.get("signal", "—"))
            _reason = str(_g.get("reason", "—"))[:120]
            _token  = str(_g.get("approval_token", ""))
            _sc     = "#dc2626" if _signal == "GEO1" else "#d97706"
            _radio  = "—"
            for _k, _rl in _geo_radio_map.items():
                if _k in _camp.lower():
                    _radio = _rl
                    break
            _btn_html = (
                f'<div style="margin-top:6px;">{_approval_buttons(_token)}</div>'
                if _signal == "GEO1" else ""
            )
            _rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'📍 {_camp}</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'Radio esperado: <strong>{_radio}</strong>'
                f' &nbsp;·&nbsp; Estado: <strong style="color:{_sc};">{_signal}</strong></p>'
                f'<p style="margin:0 0 4px 0;font-size:12px;color:#374151;">{_reason}</p>'
                + _btn_html
                + f'</td></tr>'
            )
        _geo_email_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">📍 Alertas GEO ({len(_geo_alerts_email)})</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_rows}</table>'
            f'</td></tr>'
        )

    tech_table = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      {_tech_row("Cobertura de campañas", _coverage_str)}
      {_tech_row("Keywords evaluadas (Search)", str(_kw_eval))}
      {_tech_row("Módulos ejecutados", modules_str or "—")}
      {_tech_row("Cambios automáticos", changes)}
      {_tech_row("Bloqueados por guarda", blocked, warn=blocked > 0)}
      {_tech_row("Pendientes aprobación", f"{human_pending} → {pending_str}", warn=human_pending > 0)}
      {_tech_row("Issues detectados", issues_str, warn=bool(issues_parts))}
      {_tech_row("Hallazgos Smart Campaigns", str(_smart_iss) if _smart_iss else "—", warn=_smart_iss > 0)}
      {_tech_row("Errores técnicos", errors_str, warn=bool(errors))}
      {_tech_row("Sesión ID", run.get("run_id", "—"))}
    </table>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif; background:#f9f9f9; padding:20px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff; border:1px solid #ddd; border-radius:6px; margin:0 auto;">

  <!-- Encabezado -->
  <tr>
    <td style="background:{bg}; padding:14px 20px; border-radius:6px 6px 0 0;">
      <span style="font-size:17px; font-weight:bold; color:{color};">{badge}</span><br>
      <span style="font-size:12px; color:#666;">Thai Thai Ads Agent &nbsp;·&nbsp; {run.get("timestamp_merida", "—")}</span>
    </td>
  </tr>

  <!-- Estado operativo -->
  <tr>
    <td style="padding:16px 20px 8px 20px;">
      <p style="margin:0; font-size:14px; color:#333;">{cfg["status_line"]}</p>
    </td>
  </tr>

  {restored_block}

  <!-- Separador -->
  <tr><td style="padding:8px 20px 0 20px;"><hr style="border:none; border-top:1px solid #eee; margin:0;"></td></tr>

  <!-- Movimiento en la Web (GA4 24h) -->
  {_ga4_block}

  <!-- Separador -->
  <tr><td style="padding:8px 20px 0 20px;"><hr style="border:none; border-top:1px solid #eee; margin:0;"></td></tr>

  <!-- SECCIÓN 1: Salud de Canales -->
  {_seccion1_block}

  <!-- Separador -->
  <tr><td style="padding:8px 20px 0 20px;"><hr style="border:none; border-top:1px solid #eee; margin:0;"></td></tr>

  <!-- ¿Qué significa esto para mí hoy? -->
  <tr>
    <td style="padding:14px 20px 6px 20px;">
      <p style="margin:0 0 4px 0; font-size:12px; font-weight:bold; color:#999; text-transform:uppercase; letter-spacing:0.5px;">
        ¿Qué significa esto para mí hoy?
      </p>
      <p style="margin:0; font-size:14px; color:#333; line-height:1.5;">{meaning}</p>
    </td>
  </tr>

  <!-- ¿Necesito hacer algo hoy? -->
  <tr>
    <td style="padding:10px 20px 14px 20px;">
      <p style="margin:0 0 4px 0; font-size:12px; font-weight:bold; color:#999; text-transform:uppercase; letter-spacing:0.5px;">
        ¿Necesito hacer algo hoy?
      </p>
      <p style="margin:0; font-size:14px; color:#333; line-height:1.5;
                {'font-weight:bold;' if rc == 'con_alertas' else ''}">{action}</p>
    </td>
  </tr>

  {_insight_block}

  {_smart_block}

  <!-- SECCIÓN 2: Propuestas Explicadas -->
  {_kw_block}
  {_ba_block}
  {_ba2_block}
  {_ai_block}

  <!-- SECCIÓN 3: Alertas GEO -->
  {_geo_email_block}

  <!-- GEO sin confirmar (Smart Campaigns) -->
  {_geo_unv_block}

  <!-- Acciones aprobadas recientemente -->
  <tr>
    <td style="padding:6px 20px 12px 20px;">
      <p style="margin:0; font-size:12px; color:#16a34a;">
        ✅ Acciones aprobadas recientemente: <strong>{_recently_approved}</strong>
        <span style="color:#9ca3af; font-size:11px;">(últimas 72h)</span>
      </p>
    </td>
  </tr>

  <!-- Separador sección técnica -->
  <tr>
    <td style="padding:0 20px;">
      <p style="margin:0; font-size:11px; color:#bbb; border-top:1px solid #eee;
                padding-top:10px;">DETALLE TÉCNICO</p>
    </td>
  </tr>

  <!-- Tabla técnica compacta -->
  <tr>
    <td style="padding:4px 8px 12px 8px;">
      {tech_table}
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:10px 20px; font-size:11px; color:#bbb;
               border-top:1px solid #eee; border-radius:0 0 6px 6px;">
      Thai Thai Ads Agent &nbsp;·&nbsp; Corrida automática diaria &nbsp;·&nbsp;
      Historial: <code>/last-activity</code>
    </td>
  </tr>

</table>
</body>
</html>"""
    return html


def send_daily_summary_email(run: dict, session_id: str) -> bool:
    """
    Envía el correo de resumen diario SOLO si hubo una auditoría real.

    Una auditoría real = campaigns_reviewed > 0.
    Si no hubo campañas revisadas, este correo NO debe enviarse — en su lugar
    debe usarse send_operational_incident_email() para no disfrazar un fallo
    como si fuera una corrida normal.

    Args:
        run        : dict devuelto por activity_log.record_run()
        session_id : ID de la sesión de auditoría

    Returns:
        True si el correo fue enviado.
        False si no hubo auditoría real, no aplica, o hubo error.
    """
    # Guardia de honestidad: sin auditoría real, no se envía reporte normal
    if not run.get("is_real_audit", False) and run.get("campaigns_reviewed", 0) == 0:
        logger.warning(
            "send_daily_summary_email: rechazado — no hubo auditoría real "
            "(campaigns_reviewed=0). Usar send_operational_incident_email()."
        )
        return False
    from config.agent_config import (
        EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
        EMAIL_FROM, EMAIL_FROM_NAME, EMAIL_TO,
        GMAIL_APP_PASSWORD,
    )

    if not GMAIL_APP_PASSWORD:
        logger.warning("send_daily_summary_email: GMAIL_APP_PASSWORD no configurado")
        return False

    rc = run.get("result_class", "sin_acciones")
    _label = {
        "sin_acciones":      "Sin cambios",
        "sin_cambios":       "Sin cambios",     # compatibilidad histórica
        "con_observaciones": "Con observaciones",
        "con_cambios":       "Con cambios",
        "con_alertas":       "Con alertas",
        "con_errores":       "Con errores",
    }.get(rc, rc)

    fecha = run.get("timestamp_merida", "—")
    subject = f"[Thai Thai Agente] Actividad diaria — {_label} · {fecha}"

    html_body = _build_daily_summary_html(run)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        logger.info(
            "send_daily_summary_email: enviado — resultado=%s sesión=%s",
            rc, session_id,
        )
        return True
    except Exception as exc:
        logger.error("send_daily_summary_email: error SMTP — %s", exc)
        return False
