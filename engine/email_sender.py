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
from engine.llm_client import generate_text

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
    quality_findings: list | None = None,
    creative_actions: list | None = None,
) -> str | None:
    """
    Pasa Ads + GA4 + Sheets + calidad a Claude Haiku y devuelve UNA oración ejecutiva
    correlacionando los datos del día para el dueño.

    Retorna None si faltan datos suficientes o si Haiku no responde.
    """
    import os

    _spend    = float((ads_data or {}).get("spend_mxn", 0) or 0)
    _conv     = float((ads_data or {}).get("conversions", 0) or 0)
    _pedir    = int((ga4_data or {}).get("click_pedir", 0) or 0)
    _reservar = int((ga4_data or {}).get("click_reservar", 0) or 0)
    _views    = int((ga4_data or {}).get("page_views", 0) or 0)

    _sd = sheets_data or {}
    _coms        = _sd.get("comensales_total")
    _venta_local = float(_sd.get("venta_local_total", 0) or 0)
    _venta_plat  = float(_sd.get("venta_plataformas_bruto", 0) or 0)
    _venta_total = float(_sd.get("venta_total_dia", 0) or 0)

    has_ads    = _spend > 0 or _conv > 0
    has_ga4    = _pedir > 0 or _reservar > 0 or _views > 0
    has_sheets = _coms is not None
    if not (has_ads and (has_ga4 or has_sheets)):
        return None

    _clics_web = _pedir + _reservar

    _sheets_parts = []
    if _coms is not None:
        _sheets_parts.append(f"{int(_coms)} comensales en restaurante")
    if _venta_local > 0:
        _sheets_parts.append(f"venta local ${_venta_local:,.0f} (tarjeta+efectivo)")
    if _venta_plat > 0:
        _sheets_parts.append(f"delivery ${_venta_plat:,.0f} (plataformas bruto)")
    if _venta_total > 0:
        _sheets_parts.append(f"venta total ${_venta_total:,.0f}")
    _sheets_str = ", ".join(_sheets_parts) if _sheets_parts else "sin dato de ventas"

    if _conv > 0:
        _ads_str = (
            f"Ayer se invirtieron ${_spend:.0f} MXN en Ads y se obtuvieron {_conv:.0f} conversiones "
            f"(CPA ${_spend / _conv:.0f} MXN)"
        )
    else:
        _ads_str = f"Ayer se invirtieron ${_spend:.0f} MXN en Ads sin conversiones registradas"

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

    # Contexto de calidad — solo si hay issues relevantes
    _quality_str = ""
    _qf = quality_findings or []
    _ca = creative_actions or []
    _qs_issues = [f for f in _qf if f.get("type") == "QS_LOW"]
    _poor_ads  = [f for f in _qf if f.get("type") == "AD_STRENGTH_POOR"]
    _disapp    = [f for f in _qf if f.get("type") == "AD_DISAPPROVED"]
    _quality_parts = []
    if _qs_issues:
        _quality_parts.append(f"{len(_qs_issues)} keyword(s) con Quality Score bajo")
    if _poor_ads:
        _quality_parts.append(f"{len(_poor_ads)} anuncio(s) con Ad Strength POOR")
    if _disapp:
        _quality_parts.append(f"{len(_disapp)} anuncio(s) rechazado(s) por Google")
    if _ca:
        _exec = [a for a in _ca if isinstance(a.get("result"), dict) and a["result"].get("status") == "executed"]
        if _exec:
            _quality_parts.append(f"{len(_exec)} acción(es) creativa(s) ejecutada(s) automáticamente")
    if _quality_parts:
        _quality_str = " Calidad de anuncios: " + "; ".join(_quality_parts) + "."

    # Contexto de objetivo de comensales
    _objetivo_coms = _COMENSALES_OBJ_DIA = 40
    _coms_int = int(_coms) if _coms is not None else None
    _coms_vs_objetivo = ""
    if _coms_int is not None:
        if _coms_int >= _objetivo_coms:
            _coms_vs_objetivo = f" (objetivo diario de {_objetivo_coms} comensales: ✅ alcanzado)"
        else:
            _diff = _objetivo_coms - _coms_int
            _coms_vs_objetivo = f" (objetivo diario de {_objetivo_coms} comensales: faltan {_diff})"

    _CONTEXTO_NEGOCIO = (
        "CONTEXTO DE NEGOCIO — Thai Thai, Mérida, Yucatán:\n"
        "Restaurante de comida tailandesa auténtica adaptada al paladar local. "
        "Objetivo: 40 comensales/día, 1,200/mes.\n\n"
        "TRES CANALES:\n"
        "1. RESTAURANTE (campañas Local + Experiencia 2026): margen alto, sin comisiones. "
        "   Se mide con comensales reales del corte de caja.\n"
        "2. TIENDA ONLINE (campaña Delivery): pedidos por GloriaFood (tienda propia del restaurante), "
        "   SIN comisiones de plataformas externas. Se mide con pedidos reales del webhook de GloriaFood y GA4.\n"
        "3. RESERVACIONES: reservas online via landing page thaithaimerida.com. Se mide con conversiones GA4.\n\n"
        "REGLAS PARA EL INSIGHT:\n"
        "- NO digas 'excelente eficiencia' si los comensales están bajo el objetivo de 40/día.\n"
        "- NO menciones cifras de presupuesto mensual.\n"
        "- SÍ menciona si el día fue bueno o malo vs el objetivo real.\n"
        "- SÍ menciona problemas de calidad de anuncios si los hay.\n"
        "- SÍ correlaciona Ads + GA4 + corte de caja en una sola oración.\n"
    )

    _prompt = (
        _CONTEXTO_NEGOCIO
        + "DATOS DE AYER (últimas 24 horas — período real de los datos de Ads):\n"
        + f"{_ads_str}. "
        + f"Web (GA4): {_views} vistas, {_clics_web} clics de intención "
        + f"(pedir: {_pedir}, reservar: {_reservar}). "
        + f"Corte de caja: {_sheets_str}{_coms_vs_objetivo}."
        + (_local_str if _local_str else "")
        + (_quality_str if _quality_str else "")
        + "\n\nEscribe UNA SOLA oración ejecutiva correlacionando estos datos para el dueño. "
        "Sin bullets, sin saltos de línea, sin markdown. Solo la oración."
    )

    try:
        _text = generate_text(
            model_role="haiku",
            user_prompt=_prompt,
            max_tokens=450,
        ).strip()
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

def _build_pro_daily_html(run: dict) -> str:
    """
    Genera el correo diario pro — formato aprobado Módulo 3.
    Secciones: score, snapshot, negocio, redistribución, keywords, ad groups, checklist, quick wins.
    """
    from datetime import date as _date_cls
    import html as _html_lib

    def _esc(v): return _html_lib.escape(str(v or ""))
    def _mxn(v):
        try: return f"${float(v):,.0f}"
        except: return "—"

    ar  = run.get("audit_result") or {}
    bo  = run.get("budget_optimizer") or {}
    vy  = run.get("ventas_ayer") or {}
    ads = run.get("ads_24h") or {}
    mbs = run.get("monthly_budget_status") or {}
    ca  = run.get("creative_actions") or []
    kp  = run.get("keyword_proposals") or []
    boo_dec = bo.get("decisions") or []
    boo_red = bo.get("redistribution") or {}
    boo_analysis = bo.get("redistribution_analysis") or {}
    boo_ped = bo.get("pedidos_gloriafood_detalle") or []
    boo_ped_count = bo.get("pedidos_gloriafood_24h") or 0
    boo_exec = bo.get("executed") or []

    score       = ar.get("score") or 0
    grade       = ar.get("grade") or "—"
    cat_scores  = ar.get("category_scores") or {}
    delta       = ar.get("score_delta")
    prev_score  = ar.get("previous_score")
    quick_wins  = ar.get("quick_wins") or []
    checks_by_cat = ar.get("checks_by_category") or {}

    fecha = _date_cls.today().strftime("%Y-%m-%d")
    _ads_spend = float(ads.get("spend_mxn") or 0)
    _mes_pct   = 0
    _mes_cap   = float(mbs.get("monthly_cap") or 10000)
    _mes_spent = float(mbs.get("spend_so_far") or 0)
    if _mes_cap > 0:
        _mes_pct = round(_mes_spent / _mes_cap * 100, 1)

    def _bar(s, w=180):
        if s is None: return ""
        pct = int(s)
        color = "#1D9E75" if s >= 70 else ("#EF9F27" if s >= 45 else "#E24B4A")
        filled = int(w * pct / 100)
        return (
            f'<div style="display:inline-flex;align-items:center;gap:6px;">'
            f'<div style="width:{w}px;height:6px;background:#e0e0e0;border-radius:3px;overflow:hidden;">'
            f'<div style="width:{filled}px;height:100%;background:{color};border-radius:3px;"></div>'
            f'</div><span style="font-size:12px;font-weight:500;color:#333;">{s:.0f}/100</span></div>'
        )

    CAT_LABELS = [
        ("CT",        "Conversion Tracking", "25%"),
        ("Wasted",    "Wasted Spend",        "20%"),
        ("Structure", "Account Structure",   "15%"),
        ("KW",        "Keywords & QS",       "15%"),
        ("Ads",       "Ads & Assets",        "15%"),
        ("Settings",  "Settings & Targeting","10%"),
    ]

    def _check_icon(result):
        icons = {"PASS": ("✓", "#1D9E75"), "FAIL": ("✗", "#E24B4A"), "WARNING": ("⚠", "#EF9F27"), "SKIP": ("–", "#aaa"), "N/A": ("–", "#aaa")}
        sym, col = icons.get(result, ("?", "#aaa"))
        return f'<span style="color:{col};font-weight:500;">{sym}</span>'

    _CSS = """
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;background:#f5f5f5;}
    .wrap{max-width:600px;margin:0 auto;padding:16px;}
    .card{background:#fff;border:0.5px solid #e0e0e0;border-radius:12px;padding:16px 18px;margin-bottom:12px;}
    .sec-title{font-size:10px;font-weight:600;color:#999;text-transform:uppercase;letter-spacing:.06em;
               margin-bottom:10px;padding-bottom:6px;border-bottom:0.5px solid #e8e8e8;}
    .row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:12px;}
    .row-border{border-bottom:0.5px solid #f0f0f0;}
    .row-border:last-child{border-bottom:none;}
    .badge{display:inline-block;font-size:10px;padding:1px 7px;border-radius:4px;font-weight:500;}
    .badge-green{background:#e8f5e9;color:#2e7d32;}
    .badge-amber{background:#fff8e1;color:#e65100;}
    .badge-red{background:#fce4ec;color:#b71c1c;}
    .badge-info{background:#e3f2fd;color:#1565c0;}
    .kw-tag{font-size:10px;padding:1px 5px;border-radius:3px;font-weight:500;}
    .kw-blocked{background:#fce4ec;color:#b71c1c;}
    .kw-added{background:#e8f5e9;color:#2e7d32;}
    .kw-watch{background:#fff8e1;color:#e65100;}
    .kw-auto{background:#e3f2fd;color:#1565c0;}
    .check-row{display:flex;gap:8px;padding:4px 0;font-size:12px;align-items:flex-start;}
    .check-done{color:#2e7d32;flex-shrink:0;}
    table.data{width:100%;border-collapse:collapse;font-size:12px;}
    table.data th{color:#999;font-weight:500;padding:4px 6px;border-bottom:0.5px solid #e8e8e8;text-align:left;}
    table.data td{padding:5px 6px;border-bottom:0.5px solid #f0f0f0;color:#333;}
    table.data tr:last-child td{border-bottom:none;}
    .metric-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;}
    .metric-card{background:#f8f8f8;border-radius:8px;padding:10px 12px;}
    .metric-label{font-size:11px;color:#999;margin-bottom:2px;}
    .metric-value{font-size:20px;font-weight:500;color:#111;}
    .metric-sub{font-size:11px;color:#aaa;}
    .budget-type-r{color:#E24B4A;font-weight:500;}
    .budget-type-s{color:#1D9E75;font-weight:500;}
    .budget-type-p{color:#999;}
    """

    # ── Score header ──────────────────────────────────────────────────────────
    delta_html = ""
    if delta is not None and prev_score is not None:
        sign = "+" if delta >= 0 else ""
        color = "#1D9E75" if delta >= 0 else "#E24B4A"
        delta_html = f'<div style="font-size:13px;color:{color};">{sign}{delta:.1f} pts vs ayer</div>'

    score_color = "#1D9E75" if score >= 70 else ("#EF9F27" if score >= 45 else "#E24B4A")
    cats_html = ""
    for cat_key, cat_label, cat_weight in CAT_LABELS:
        sv = cat_scores.get(cat_key)
        sv_str = f"{sv:.0f}/100" if sv is not None else "N/D"
        cats_html += f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:12px;">
          <span style="width:140px;color:#666;flex-shrink:0;">{cat_label}</span>
          <span style="width:50px;font-weight:500;color:#333;text-align:right;flex-shrink:0;">{sv_str}</span>
          {_bar(sv)}
          <span style="width:30px;color:#aaa;font-size:11px;text-align:right;">{cat_weight}</span>
        </div>"""

    score_section = f"""
    <div class="card" style="background:#f8f9fa;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;">
        <div>
          <div style="font-size:15px;font-weight:500;color:#111;">Google Ads Health Score — Thai Thai Mérida</div>
          <div style="font-size:11px;color:#999;margin-top:2px;">{fecha} · Últimos 30 días · ID 4021070209</div>
        </div>
        <div style="text-align:right;">
          <span style="font-size:30px;font-weight:500;color:{score_color};">{score:.0f}</span>
          <span style="font-size:13px;color:#999;">/100 ({_esc(grade)})</span>
          {delta_html}
        </div>
      </div>
      {cats_html}
    </div>"""

    # ── Snapshot de campañas ──────────────────────────────────────────────────
    camp_rows = ""
    for c in ads.get("por_campana") or []:
        cname  = _esc(c.get("name", "—"))
        tipo   = _esc(c.get("tipo", "—"))
        gasto  = _mxn(c.get("spend_mxn"))
        clics  = int(c.get("clicks", 0) or 0)
        conv   = float(c.get("conversions", 0) or 0)
        spend  = float(c.get("spend_mxn", 0) or 0)
        cpa    = _mxn(spend / conv) if conv > 0 else "—"
        camp_rows += f"""
        <tr>
          <td>{cname}</td>
          <td style="color:#888;font-size:11px;">{tipo}</td>
          <td>{gasto}</td>
          <td>{clics:,}</td>
          <td>{conv:.0f}</td>
          <td>{cpa}</td>
          <td><span class="badge badge-green">Activa</span></td>
        </tr>"""
    snapshot_section = f"""
    <div class="card">
      <div class="sec-title">Snapshot de campañas (30d)</div>
      <table class="data">
        <tr><th>Campaña</th><th>Tipo</th><th>Gasto</th><th>Clics</th><th>Conv</th><th>CPA</th><th>Estado</th></tr>
        {camp_rows if camp_rows else '<tr><td colspan="7" style="color:#aaa;text-align:center;">Sin datos de campañas</td></tr>'}
      </table>
      <div style="font-size:10px;color:#aaa;margin-top:8px;">*Smart: micro-acciones locales. No son reservas ni pedidos.</div>
    </div>"""

    # ── Negocio ayer ──────────────────────────────────────────────────────────
    _coms  = vy.get("comensales_total")
    _efect = float(vy.get("pago_efectivo_total") or 0)
    _tarj  = float(vy.get("pago_tarjeta_total") or 0)
    _plat  = float(vy.get("venta_plataformas_bruto") or 0)
    _total = float(vy.get("venta_total_dia") or 0)
    coms_html = ""
    if _coms is not None:
        ok = "✓" if int(_coms) >= 40 else "⚠"
        coms_html = f'<div class="metric-card"><div class="metric-label">Comensales</div><div class="metric-value">{_coms}</div><div class="metric-sub">Objetivo: 40 {ok}</div></div>'

    pedidos_html = ""
    if boo_ped:
        total_gf = sum(p.get("total_mxn", 0) for p in boo_ped)
        rows_gf = ""
        for p in boo_ped:
            oid   = _esc(p.get("order_id", ""))
            tmxn  = _mxn(p.get("total_mxn"))
            hora  = str(p.get("accepted_at") or "")[-8:-3] if p.get("accepted_at") else "—"
            rows_gf += f'<div class="row row-border"><span>#{oid}</span><span>{tmxn} MXN</span><span style="color:#aaa;">{hora}h</span></div>'
        pedidos_html = f"""
        <div style="margin-top:10px;">
          <div class="sec-title">Pedidos GloriaFood (24h) — {boo_ped_count} pedidos · {_mxn(total_gf)} MXN total</div>
          {rows_gf}
        </div>"""
    elif boo_ped_count == 0:
        pedidos_html = '<div style="font-size:12px;color:#aaa;margin-top:8px;">Sin pedidos GloriaFood en las últimas 24h</div>'

    negocio_section = f"""
    <div class="card">
      <div class="sec-title">Negocio ayer</div>
      <div class="metric-grid">
        {coms_html}
        <div class="metric-card"><div class="metric-label">Venta total</div><div class="metric-value">{_mxn(_total)}</div><div class="metric-sub">MXN</div></div>
      </div>
      <div style="font-size:12px;color:#666;">
        <div class="row row-border"><span>Efectivo</span><span>{_mxn(_efect)} MXN</span></div>
        <div class="row row-border"><span>Tarjeta</span><span>{_mxn(_tarj)} MXN</span></div>
        <div class="row row-border"><span>Plataformas</span><span>{_mxn(_plat)} MXN</span></div>
      </div>
      {pedidos_html}
      <div style="font-size:11px;color:#aaa;margin-top:10px;display:flex;justify-content:space-between;">
        <span>Gasto Ads hoy: {_mxn(_ads_spend)} MXN</span>
        <span>Mes: {_mxn(_mes_spent)} / {_mxn(_mes_cap)} ({_mes_pct}%)</span>
      </div>
    </div>"""

    # ── Redistribución de presupuesto ─────────────────────────────────────────
    reduced   = boo_red.get("reduced") or []
    scaled    = boo_red.get("scaled") or []
    protected = boo_red.get("protected") or []
    net_daily = boo_red.get("net_daily_mxn") or 0

    budget_rows = ""
    for r in reduced:
        budget_rows += f"""
        <div class="row row-border">
          <span class="budget-type-r" style="width:68px;flex-shrink:0;font-size:11px;">Reducido</span>
          <div style="flex:1;font-size:12px;color:#333;">{_esc(r.get('name',''))}
            <div style="font-size:11px;color:#aaa;">{_esc(str(r.get('reason',''))[:80])} · Libera ~{_mxn(r.get('saved_monthly'))}/mes</div>
          </div>
          <div style="text-align:right;font-size:12px;">{_mxn(r.get('before'))}/día → {_mxn(r.get('after'))}/día<br>
            <span style="color:#E24B4A;font-size:11px;">-{_mxn(r.get('saved_daily'))}/día</span></div>
        </div>"""
    for s in scaled:
        budget_rows += f"""
        <div class="row row-border">
          <span class="budget-type-s" style="width:68px;flex-shrink:0;font-size:11px;">Escalado</span>
          <div style="flex:1;font-size:12px;color:#333;">{_esc(s.get('name',''))}
            <div style="font-size:11px;color:#aaa;">{_esc(str(s.get('reason',''))[:80])} · Recibe +{_mxn(s.get('added_monthly'))}/mes</div>
          </div>
          <div style="text-align:right;font-size:12px;">{_mxn(s.get('before'))}/día → {_mxn(s.get('after'))}/día<br>
            <span style="color:#1D9E75;font-size:11px;">+{_mxn(s.get('added_daily'))}/día</span></div>
        </div>"""
    for p in protected:
        budget_rows += f"""
        <div class="row row-border">
          <span class="budget-type-p" style="width:68px;flex-shrink:0;font-size:11px;">Protegido</span>
          <div style="flex:1;font-size:12px;color:#333;">{_esc(p.get('name',''))}
            <div style="font-size:11px;color:#aaa;">70% motor del negocio — sin cambio</div>
          </div>
          <div style="text-align:right;font-size:12px;color:#999;">{_mxn(p.get('daily_budget'))}/día</div>
        </div>"""

    net_color = "#1D9E75" if net_daily >= 0 else "#E24B4A"
    net_sign  = "+" if net_daily >= 0 else ""
    budget_section = f"""
    <div class="card">
      <div class="sec-title">Redistribución de presupuesto hoy</div>
      {budget_rows if budget_rows else '<div style="font-size:12px;color:#aaa;">Sin cambios de presupuesto hoy</div>'}
      <div style="font-size:12px;font-weight:500;color:#666;margin-top:10px;padding-top:10px;border-top:0.5px solid #e8e8e8;">
        Balance neto: <span style="color:{net_color};">{net_sign}{_mxn(abs(net_daily))}/día</span>
      </div>
    </div>"""

    # ── Keywords hoy ──────────────────────────────────────────────────────────
    analysis_sources = boo_analysis.get("fund_sources") or []
    analysis_receivers = boo_analysis.get("receiver_candidates") or []
    analysis_matrix = boo_analysis.get("allocation_matrix") or []
    analysis_rows = ""

    if analysis_sources or analysis_receivers or analysis_matrix:
        source_html = ""
        for source in analysis_sources:
            source_html += f"""
            <div class="row row-border">
              <span class="budget-type-r" style="width:68px;flex-shrink:0;font-size:11px;">Fuente</span>
              <div style="flex:1;font-size:12px;color:#333;">{_esc(source.get('campaign_name',''))}
                <div style="font-size:11px;color:#aaa;">{_esc(source.get('source_action','reduce'))} justificado · {_esc(str(source.get('reason',''))[:80])}</div>
              </div>
              <div style="text-align:right;font-size:12px;color:#E24B4A;">-{_mxn(source.get('freed_daily_mxn'))}/dia</div>
            </div>"""

        receiver_html = ""
        for receiver in analysis_receivers:
            receiver_html += f"""
            <div class="row row-border">
              <span class="budget-type-s" style="width:68px;flex-shrink:0;font-size:11px;">Candidata</span>
              <div style="flex:1;font-size:12px;color:#333;">{_esc(receiver.get('campaign_name',''))}
                <div style="font-size:11px;color:#aaa;">scale elegible · {_esc(str(receiver.get('eligibility_reason',''))[:80])}</div>
              </div>
              <div style="text-align:right;font-size:12px;color:#1D9E75;">+{_mxn(receiver.get('max_receivable_daily_mxn'))}/dia</div>
            </div>"""

        matrix_html = ""
        for allocation in analysis_matrix:
            matrix_html += f"""
            <div class="row row-border">
              <span style="width:68px;flex-shrink:0;font-size:11px;color:#1565c0;font-weight:500;">Traza</span>
              <div style="flex:1;font-size:12px;color:#333;">{_esc(allocation.get('from_campaign_name',''))} -> {_esc(allocation.get('to_campaign_name',''))}</div>
              <div style="text-align:right;font-size:12px;color:#1565c0;">{_mxn(allocation.get('amount_daily_mxn'))}/dia</div>
            </div>"""

        analysis_rows = f"""
        <div style="font-size:12px;color:#1565c0;font-weight:500;margin-bottom:8px;">Sin ejecucion automatica</div>
        <div style="font-size:12px;color:#666;margin-bottom:10px;">No cambia presupuestos todavia</div>
        <div style="font-size:12px;font-weight:500;color:#333;margin-bottom:6px;">Fondo liberado potencial: {_mxn(boo_analysis.get('potential_freed_daily_mxn'))}/dia</div>
        {source_html}
        {receiver_html}
        {matrix_html}
        <div style="font-size:12px;font-weight:500;color:#666;margin-top:10px;padding-top:10px;border-top:0.5px solid #e8e8e8;">
          Balance neto analizado: {_mxn(boo_analysis.get('net_daily_mxn'))}/dia
        </div>"""

    budget_analysis_section = f"""
    <div class="card">
      <div class="sec-title">Redistribucion potencial analizada</div>
      {analysis_rows if analysis_rows else '<div style="font-size:12px;color:#aaa;">Sin redistribucion potencial analizada hoy</div>'}
    </div>"""

    blocked_kws = [p for p in kp if p.get("action") == "add_negative" and (p.get("result") or {}).get("status") == "executed"]
    added_kws   = [p for p in kp if p.get("action") == "add_keyword"  and (p.get("result") or {}).get("status") == "executed"]

    kw_blocked_html = ""
    total_saved = 0
    for bkw in blocked_kws[:10]:
        term  = _esc(bkw.get("keyword_text") or bkw.get("term") or "")
        cost  = float(bkw.get("cost_mxn") or bkw.get("wasted_spend") or 0)
        total_saved += cost
        camp  = _esc(bkw.get("campaign_name") or "")
        kw_blocked_html += f"""
        <div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:0.5px solid #f0f0f0;font-size:12px;">
          <span style="flex:1;">"{term}"</span>
          <span style="color:#E24B4A;width:44px;text-align:right;">{_mxn(cost)}</span>
          <span style="color:#aaa;width:90px;text-align:right;font-size:11px;">{camp}</span>
          <span class="kw-tag kw-blocked">bloqueada</span>
        </div>"""

    kw_added_html = ""
    for akw in added_kws[:5]:
        term = _esc(akw.get("keyword_text") or akw.get("term") or "")
        camp = _esc(akw.get("campaign_name") or "")
        kw_added_html += f"""
        <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:0.5px solid #f0f0f0;font-size:12px;">
          <span style="flex:1;">"{term}"</span>
          <span style="color:#aaa;font-size:11px;">{camp}</span>
          <span class="kw-tag kw-added">agregada</span>
        </div>"""

    sonnet_html = ""
    for cact in ca:
        if cact.get("action") in ("add_headlines", "replace_headlines") \
                and (cact.get("result") or {}).get("status") in ("executed", "success"):
            hls = cact.get("headlines") or []
            if hls:
                ad_group = _esc(cact.get("ad_group_name") or cact.get("campaign_name") or "")
                sonnet_html += f"""
                <div style="padding:5px 0;border-bottom:0.5px solid #f0f0f0;font-size:12px;">
                  <div style="color:#333;margin-bottom:3px;">{ad_group} <span class="kw-tag kw-auto">remediado</span></div>
                  <div style="font-size:11px;color:#1565c0;">{' · '.join(_esc(h) for h in hls[:5])}</div>
                  <div style="font-size:10px;color:#aaa;margin-top:2px;">Headlines generados por Sonnet — Google re-evalúa en 24-48h</div>
                </div>"""

    saved_html = f' · Ahorrado: {_mxn(total_saved)} MXN' if total_saved > 0 else ""
    keywords_section = f"""
    <div class="card">
      <div class="sec-title">Keywords hoy</div>
      {"" if not kw_blocked_html else f'<div style="font-size:11px;color:#666;font-weight:500;margin-bottom:6px;">Negativas bloqueadas — automático{saved_html}</div>' + kw_blocked_html}
      {"" if not kw_added_html else '<div style="font-size:11px;color:#666;font-weight:500;margin:10px 0 6px;">Keywords nuevas agregadas — automático</div>' + kw_added_html}
      {"" if not sonnet_html else '<div style="font-size:11px;color:#666;font-weight:500;margin:10px 0 6px;">Copy RSA generado por Sonnet</div>' + sonnet_html}
      {"<div style='font-size:12px;color:#aaa;'>Sin cambios de keywords hoy</div>" if not (kw_blocked_html or kw_added_html or sonnet_html) else ""}
    </div>"""

    # ── Agente ejecutó solo hoy ───────────────────────────────────────────────
    exec_items = []
    if boo_exec:
        for bdec in boo_exec:
            if bdec.get("action") in ("scale", "reduce"):
                exec_items.append(
                    f'{bdec["campaign_name"]}: {bdec["action"].upper()} '
                    f'{_mxn(bdec.get("current_daily_budget_mxn"))} → {_mxn(bdec.get("new_daily_budget_mxn"))}/día'
                )
    if blocked_kws:
        exec_items.append(f'Bloqueó {len(blocked_kws)} términos desperdiciados ({_mxn(total_saved)} MXN ahorrados)')
    if added_kws:
        exec_items.append(f'Agregó {len(added_kws)} keywords estratégicas')
    for cact in ca:
        if cact.get("action") in ("add_headlines",) and (cact.get("result") or {}).get("status") in ("executed", "success"):
            n = len(cact.get("headlines") or [])
            exec_items.append(f'Generó {n} headlines para RSA "{_esc(cact.get("ad_group_name") or "")}" (Ad Strength POOR)')

    exec_html = "\n".join(
        f'<div class="check-row"><span class="check-done">✓</span><span>{_esc(item)}</span></div>'
        for item in exec_items
    ) if exec_items else '<div style="font-size:12px;color:#aaa;">Sin cambios automáticos hoy</div>'

    exec_section = f"""
    <div class="card">
      <div class="sec-title">Agente ejecutó solo hoy</div>
      {exec_html}
    </div>"""

    # ── Quick Wins pendientes ─────────────────────────────────────────────────
    qw_rows = ""
    for i, qw in enumerate(quick_wins, 1):
        sev   = _esc(qw.get("severity", ""))
        sev_color = "#E24B4A" if sev == "Critical" else ("#EF9F27" if sev == "High" else "#666")
        mins  = qw.get("fix_minutes", 0)
        desc  = _esc(qw.get("description", ""))
        qw_rows += f"""
        <tr>
          <td>{i}</td>
          <td>{desc}</td>
          <td style="color:{sev_color};font-weight:500;">{sev}</td>
          <td>{mins} min</td>
        </tr>"""

    qw_section = f"""
    <div class="card">
      <div class="sec-title">Quick wins pendientes — tú los resuelves</div>
      <table class="data">
        <tr><th>#</th><th>Acción</th><th>Severidad</th><th>Tiempo</th></tr>
        {qw_rows if qw_rows else '<tr><td colspan="4" style="color:#aaa;">Sin quick wins pendientes</td></tr>'}
      </table>
    </div>"""

    # ── Desglose por categoría (expandible) ───────────────────────────────────
    CAT_SCORE_STYLE = lambda s: (
        'background:#e8f5e9;color:#2e7d32' if (s or 0) >= 70
        else ('background:#fff8e1;color:#e65100' if (s or 0) >= 45
              else 'background:#fce4ec;color:#b71c1c')
    )
    cat_sections = ""
    for cat_key, cat_label, _ in CAT_LABELS:
        sv = cat_scores.get(cat_key)
        sv_str = f"{sv:.0f}/100" if sv is not None else "N/D"
        checks = checks_by_cat.get(cat_key) or []
        checks_html = ""
        for ch in checks:
            icon_html = _check_icon(ch.get("result", ""))
            detail = _esc(ch.get("detail", ""))
            cid    = _esc(ch.get("id", ""))
            sev_c  = ch.get("severity", "")
            sev_badge = ""
            if ch.get("result") in ("FAIL", "WARNING") and sev_c in ("Critical", "High"):
                sev_color2 = "#E24B4A" if sev_c == "Critical" else "#EF9F27"
                sev_badge = f' <span style="font-size:9px;color:{sev_color2};">({sev_c})</span>'
            checks_html += f"""
            <div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:0.5px solid #f0f0f0;font-size:12px;">
              <span style="flex-shrink:0;width:16px;">{icon_html}</span>
              <div style="flex:1;"><span style="color:#aaa;margin-right:4px;font-size:10px;">{cid}</span><span style="color:#333;">{detail}{sev_badge}</span></div>
            </div>"""
        cat_sections += f"""
        <div style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;padding-bottom:6px;border-bottom:0.5px solid #e8e8e8;margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:13px;font-weight:500;color:#333;">{cat_label}</span>
              <span style="font-size:10px;padding:1px 7px;border-radius:4px;font-weight:500;{CAT_SCORE_STYLE(sv)}">{sv_str}</span>
            </div>
          </div>
          <div>{checks_html}</div>
        </div>"""

    desglose_section = f"""
    <div class="card">
      <div class="sec-title">Desglose por categoría — clic para expandir</div>
      {cat_sections}
    </div>"""

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = """
    <div style="font-size:11px;color:#aaa;text-align:center;padding-top:10px;border-top:0.5px solid #e8e8e8;">
      Thai Thai Ads Agent · administracion@thaithaimerida.com.mx
    </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style></head>
<body><div class="wrap">
{score_section}
{snapshot_section}
{negocio_section}
{budget_section}
{budget_analysis_section}
{keywords_section}
{exec_section}
{qw_section}
{desglose_section}
{footer}
</div></body></html>"""

    try:
        from premailer import transform
        html = transform(html)
    except Exception:
        pass
    return html


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
    _monthly_budget_status = run.get("monthly_budget_status", {}) or {}
    _ads_24h      = run.get("ads_24h", {})
    _ads_spend    = float(_ads_24h.get("spend_mxn", 0) or 0)
    _ads_conv     = float(_ads_24h.get("conversions", 0) or 0)
    _landing_ms   = run.get("landing_response_ms")
    _ventas_ayer        = run.get("ventas_ayer", {}) or {}
    # Nuevo formato: resumen_negocio_para_agente
    _COMENSALES_OBJ_DIA = 40
    _coms_ayer          = _ventas_ayer.get("comensales_total")          # personas en restaurante
    _coms_obj           = _COMENSALES_OBJ_DIA                           # objetivo fijo diario
    _coms_prom          = _ventas_ayer.get("comensales_promedio_diario") # solo útil si days>1
    _venta_local        = float(_ventas_ayer.get("venta_local_total", 0) or 0)    # tarjeta+efectivo
    _venta_plat_bruto   = float(_ventas_ayer.get("venta_plataformas_bruto", 0) or 0)  # col H
    _pago_efectivo_ayer = float(_ventas_ayer.get("pago_efectivo_total", 0) or 0)
    _pago_tarjeta_ayer  = float(_ventas_ayer.get("pago_tarjeta_total", 0) or 0)
    _propinas_ayer      = float(_ventas_ayer.get("propinas_total", 0) or 0)
    _venta_total_dia    = float(_ventas_ayer.get("venta_total_dia", 0) or 0)
    _venta_neta_prom    = float(_ventas_ayer.get("venta_neta_promedio_diario", 0) or 0)

    # GA4 web traffic (Sección 0: Movimiento en la Web)
    _ga4_web      = run.get("ga4_web")
    _ga4_ok       = isinstance(_ga4_web, dict) and "error" not in _ga4_web and bool(_ga4_web)
    _ga4_views    = int(_ga4_web.get("page_views", 0) or 0)       if _ga4_ok else 0
    _ga4_pedir    = int(_ga4_web.get("click_pedir", 0) or 0)      if _ga4_ok else 0
    _ga4_reservar = int(_ga4_web.get("click_reservar", 0) or 0)   if _ga4_ok else 0
    _ga4_activos  = int(_ga4_web.get("usuarios_activos", 0) or 0) if _ga4_ok else 0
    _budget_optimizer = run.get("budget_optimizer") or {}
    _redistribution_analysis = _budget_optimizer.get("redistribution_analysis") or {}
    _recently_approved       = int(run.get("recently_approved_count", 0) or 0)
    _agent_insight           = run.get("agent_insight")
    _quality_findings        = run.get("quality_creative_findings", []) or []
    _creative_actions_email  = run.get("creative_actions", []) or []
    _paused_campaigns_email  = run.get("paused_campaigns", []) or []
    _builder_proposals_email = run.get("builder_executed", []) or []

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

    # ── Override de meaning si hay quality findings críticos ─────────────────
    # Aplica a sin_acciones y con_cambios donde el texto genérico ignoraría alertas de calidad
    if rc in ("sin_acciones", "sin_novedades", "con_cambios") and _quality_findings:
        _qf_overrides = []
        _lost_is = [f for f in _quality_findings if f.get("type") in ("LOST_IS_BUDGET_HIGH", "LOW_IMPRESSION_SHARE")]
        _poor_ads_qf = [f for f in _quality_findings if f.get("type") == "AD_STRENGTH_POOR"]
        _disapp_qf   = [f for f in _quality_findings if f.get("type") == "AD_DISAPPROVED"]
        _qs_low_qf   = [f for f in _quality_findings if f.get("type") == "QS_LOW"]
        if _lost_is:
            # Intentar extraer el IS% si está disponible
            _is_vals = [f.get("search_impression_share") for f in _lost_is if f.get("search_impression_share")]
            if _is_vals:
                _min_is = min(_is_vals)
                _qf_overrides.append(
                    f"Tus campañas Search solo capturan el {_min_is*100:.0f}% del mercado "
                    f"— estás perdiendo el {(1-_min_is)*100:.0f}% de búsquedas por presupuesto."
                )
            else:
                _qf_overrides.append("Hay campañas perdiendo Impression Share por presupuesto — considera aumentarlo.")
        if _poor_ads_qf:
            _qf_overrides.append(f"Hay {len(_poor_ads_qf)} anuncio(s) con Ad Strength POOR que necesitan mejora de copy.")
        if _disapp_qf:
            _qf_overrides.append(f"Hay {len(_disapp_qf)} anuncio(s) rechazado(s) por Google — requieren revisión urgente.")
        if _qs_low_qf:
            _qf_overrides.append(f"{len(_qs_low_qf)} keyword(s) con Quality Score bajo (< 7) — afecta el costo por clic.")
        if _qf_overrides:
            meaning = " ".join(_qf_overrides)
            if _disapp_qf or _poor_ads_qf:
                action = "Revisar la sección 'Salud de Anuncios y Calidad' en este correo."
            elif _lost_is:
                action = "Considera aprobar un aumento de presupuesto en las campañas Search afectadas."

    # ── Override dinámico de meaning con datos de negocio reales ─────────────
    # Solo si meaning todavía es el texto genérico (no fue sobreescrito por quality findings)
    if rc not in ("con_errores",):
        _meaning_parts = []
        if _coms_ayer is not None:
            if _coms_ayer >= _COMENSALES_OBJ_DIA:
                _meaning_parts.append(
                    f"Hoy llegaron {_coms_ayer} comensales — sobre el objetivo de {_COMENSALES_OBJ_DIA}/día. ✅"
                )
            elif _coms_ayer >= 30:
                _meaning_parts.append(
                    f"Hoy llegaron {_coms_ayer} comensales — bajo el objetivo de {_COMENSALES_OBJ_DIA}/día. ⚠️"
                )
            else:
                _meaning_parts.append(
                    f"Solo {_coms_ayer} comensales hoy — muy por debajo del objetivo de {_COMENSALES_OBJ_DIA}/día. 🔴"
                )
        # Agregar dato de pedidos online si están disponibles en run
        _gf_count_run = run.get("gloriafood_orders_24h", {})
        if isinstance(_gf_count_run, dict) and _gf_count_run.get("orders"):
            _gf_n = _gf_count_run["orders"]
            _gf_rev = _gf_count_run.get("revenue_mxn", 0)
            _meaning_parts.append(
                f"{_gf_n} pedido(s) online (${_gf_rev:,.0f} MXN) via GloriaFood en las últimas 24h."
            )
        if _meaning_parts:
            meaning = " ".join(_meaning_parts) + " " + meaning

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

    # Presupuesto mensual card
    _mbs_pace      = _monthly_budget_status.get("pace", "")
    _mbs_spent     = _monthly_budget_status.get("spend_so_far", 0)
    _mbs_cap       = _monthly_budget_status.get("monthly_cap", 10000)
    _mbs_pct       = _monthly_budget_status.get("pct_consumed", 0)
    _mbs_remaining = _monthly_budget_status.get("days_remaining", 0)
    _mbs_allowed   = _monthly_budget_status.get("daily_allowed", 0)
    _pace_colors   = {"SOBRE_RITMO": "#dc2626", "EN_RITMO": "#16a34a", "BAJO_RITMO": "#d97706"}
    _mbs_color     = _pace_colors.get(_mbs_pace, "#6b7280")
    if _mbs_pace:
        _mbs_val = (
            f"<strong>${_mbs_spent:,.0f}</strong> / ${_mbs_cap:,.0f}"
            f" <span style='color:{_mbs_color};font-size:10px;'>({_mbs_pct:.0f}%)</span>"
        )
        _mbs_sub = f"Quedan {_mbs_remaining}d · Permitido: ${_mbs_allowed:,.0f}/día"
    else:
        _mbs_val = "<strong>—</strong>"
        _mbs_sub = "Sin datos de gasto mensual"

    # Landing card — diagnóstico completo
    _has_landing_weak = any(
        f.get("type") in ("LANDING_SLOW", "LANDING_ERROR", "POST_CLICK_BELOW_AVERAGE", "QS_LANDING_WEAK")
        for f in _quality_findings
    )
    if landing in (None, "ok") and not _has_landing_weak:
        _land_icon, _land_label, _land_color = "✅", "OK", "#16a34a"
        _land_status_text = "Funcional"
    elif landing == "warning" or _has_landing_weak:
        _land_icon, _land_label, _land_color = "⚠️", "Lento", "#d97706"
        _land_status_text = "Respuesta lenta" if landing == "warning" else "Post-click bajo promedio"
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
        _ven_sub = "Sobre objetivo"
    elif _coms_ayer >= 30:
        _ven_val = f"<strong style='color:#d97706;'>{_coms_ayer}</strong> / {_coms_obj} obj 🟡"
        _ven_sub = "Bajo objetivo"
    else:
        _ven_val = f"<strong style='color:#dc2626;'>{_coms_ayer}</strong> / {_coms_obj} obj 🔴"
        _ven_sub = "Bajo equilibrio"

    # ── Card: Venta Total (efectivo + tarjeta + plataformas + propinas) ─────
    if _venta_total_dia > 0:
        _vtotal_val = f"<strong>${_venta_total_dia:,.0f}</strong>"
        _vtotal_sub = "Cortes_de_Caja · todos los canales"
    else:
        _vtotal_val = "<span style='color:#9ca3af;'>N/D</span>"
        _vtotal_sub = "Sin dato"

    def _card(icon_label: str, val: str, sub: str) -> str:
        return (
            f'<td style="padding:8px 10px;background:#f9fafb;border:1px solid #e5e7eb;'
            f'border-radius:5px;text-align:center;vertical-align:top;">'
            f'<p style="margin:0 0 3px 0;font-size:11px;color:#6b7280;font-weight:bold;">{icon_label}</p>'
            f'<p style="margin:0 0 2px 0;font-size:13px;color:#111;">{val}</p>'
            f'<p style="margin:0;font-size:11px;color:#9ca3af;">{sub}</p>'
            f'</td>'
        )

    # ── Desglose de Ventas del Día (Cortes_de_Caja) ─────────────────────────
    if _venta_total_dia > 0:
        _desglose_rows = ""
        _desglose_items = [
            ("Efectivo",    _pago_efectivo_ayer, False),
            ("Tarjeta",     _pago_tarjeta_ayer,  False),
            ("Plataformas", _venta_plat_bruto,   False),
            ("Propinas",    _propinas_ayer,       True),   # rojo
        ]
        for _label, _monto, _es_rojo in _desglose_items:
            _color = "#dc2626" if _es_rojo else "#374151"
            _desglose_rows += (
                f'<tr style="border-top:1px solid #f0f0f0;">'
                f'<td style="padding:5px 8px;color:{_color};font-size:12px;">{_label}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:bold;color:{_color};">'
                f'${_monto:,.0f}</td>'
                f'</tr>'
            )
        _canales_block = f"""
  <tr><td style="padding:8px 20px 14px 20px;">
    <p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;
              text-transform:uppercase;letter-spacing:0.5px;">💳 Desglose de Ventas del Día</p>
    <table width="100%" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#f9fafb;">
        <th style="text-align:left;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Concepto</th>
        <th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Monto</th>
      </tr>
      {_desglose_rows}
      <tr style="border-top:2px solid #374151;">
        <td style="padding:6px 8px;font-size:12px;font-weight:bold;">TOTAL</td>
        <td style="text-align:right;padding:6px 8px;font-size:13px;font-weight:bold;">${_venta_total_dia:,.0f}</td>
      </tr>
    </table>
  </td></tr>"""
    else:
        _canales_block = ""

    # ── Gasto por Campaña (24h) ──────────────────────────────────────────────
    _por_campana = _ads_24h.get("por_campana", []) or []
    if _por_campana:
        _camp_rows = ""
        _paused_ids = {str(p.get("campaign_id", "")) for p in (_paused_campaigns_email or [])}
        for _cp in sorted(_por_campana, key=lambda x: -x.get("spend_mxn", 0)):
            _cp_conv = _cp.get("conversions")
            _cp_conv_str = f"{_cp_conv:.0f}" if _cp_conv is not None else "—"
            _cp_name_display = _cp.get("name", "—")
            if str(_cp.get("id", "")) in _paused_ids:
                _cp_name_display += ' <span style="color:#d97706;font-size:10px;">(pausada hoy)</span>'
            _camp_rows += (
                f'<tr style="border-top:1px solid #f0f0f0;">'
                f'<td style="padding:5px 8px;color:#374151;font-size:12px;">{_cp_name_display}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:bold;">'
                f'${_cp.get("spend_mxn",0):,.0f}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;color:#6b7280;">'
                f'{_cp_conv_str}</td>'
                f'</tr>'
            )
        _gasto_campana_block = f"""
  <tr><td style="padding:8px 20px 14px 20px;">
    <p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;
              text-transform:uppercase;letter-spacing:0.5px;">📢 Gasto por Campaña (24h)</p>
    <table width="100%" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#f9fafb;">
        <th style="text-align:left;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Campaña</th>
        <th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Gasto</th>
        <th style="text-align:right;padding:5px 8px;color:#6b7280;font-size:11px;font-weight:bold;
                   border-bottom:1px solid #e5e7eb;">Conv.</th>
      </tr>
      {_camp_rows}
    </table>
  </td></tr>"""
    else:
        _gasto_campana_block = ""

    _seccion1_block = (
        '<tr><td style="padding:14px 20px 6px 20px;">'
        '<p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;'
        'text-transform:uppercase;letter-spacing:0.5px;">📊 Salud de Canales — Hoy</p>'
        '<table width="100%" cellpadding="0" cellspacing="4">'
        '<tr>'
        + _card("📢 Google Ads 24h", _ads_val, _ads_sub)
        + '<td style="width:4px;"></td>'
        + _card("📅 Presupuesto Mes", _mbs_val, _mbs_sub)
        + '<td style="width:4px;"></td>'
        + _card("🌐 Landing", _land_val, _land_sub)
        + '<td style="width:4px;"></td>'
        + _card("🍽️ Comensales", _ven_val, _ven_sub)
        + '<td style="width:4px;"></td>'
        + _card("💰 Venta Total", _vtotal_val, _vtotal_sub)
        + '</tr></table>'
        '</td></tr>'
        + _gasto_campana_block
        + _canales_block
    )

    # ── Pedidos Online GloriaFood (24h) ─────────────────────────────────────────
    try:
        from engine.db_sync import get_db_path as _get_db_path_gf
        import sqlite3 as _sqlite3_gf
        _gf_conn = _sqlite3_gf.connect(_get_db_path_gf())
        _gf_cursor = _gf_conn.cursor()
        _gf_cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0)
            FROM gloriafood_orders
            WHERE received_at >= datetime('now', '-24 hours')
        """)
        _gf_row = _gf_cursor.fetchone()
        _gf_conn.close()
        _gf_count = int(_gf_row[0]) if _gf_row else 0
        _gf_total = float(_gf_row[1]) if _gf_row else 0.0
        _gf_ticket = round(_gf_total / _gf_count, 0) if _gf_count > 0 else 0.0
        if _gf_count > 0:
            _pedidos_block = f"""
  <tr><td style="padding:8px 20px 14px 20px;">
    <p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;
              text-transform:uppercase;letter-spacing:0.5px;">🛒 Pedidos Online (24h)</p>
    <table width="100%" style="border-collapse:collapse;font-size:12px;">
      <tr style="border-top:1px solid #f0f0f0;">
        <td style="padding:5px 8px;color:#374151;">Pedidos recibidos</td>
        <td style="text-align:right;padding:5px 8px;font-weight:bold;">{_gf_count}</td>
      </tr>
      <tr style="border-top:1px solid #f0f0f0;">
        <td style="padding:5px 8px;color:#374151;">Total</td>
        <td style="text-align:right;padding:5px 8px;font-weight:bold;">${_gf_total:,.0f} MXN</td>
      </tr>
      <tr style="border-top:1px solid #f0f0f0;">
        <td style="padding:5px 8px;color:#374151;">Ticket promedio</td>
        <td style="text-align:right;padding:5px 8px;font-weight:bold;">${_gf_ticket:,.0f} MXN</td>
      </tr>
    </table>
  </td></tr>"""
        else:
            _pedidos_block = (
                '<tr><td style="padding:8px 20px 10px 20px;">'
                '<p style="margin:0 0 4px 0;font-size:12px;font-weight:bold;color:#6b7280;'
                'text-transform:uppercase;letter-spacing:0.5px;">🛒 Pedidos Online (24h)</p>'
                '<p style="margin:0;font-size:12px;color:#9ca3af;">Sin pedidos registrados</p>'
                '</td></tr>'
            )
    except Exception:
        _pedidos_block = (
            '<tr><td style="padding:8px 20px 10px 20px;">'
            '<p style="margin:0 0 4px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            'text-transform:uppercase;letter-spacing:0.5px;">🛒 Pedidos Online (24h)</p>'
            '<p style="margin:0;font-size:12px;color:#9ca3af;">Sin pedidos registrados en las últimas 24 horas</p>'
            '</td></tr>'
        )

    # ── Salud de Anuncios y Calidad (Fase 6D) ──────────────────────────────────
    def _quality_table_row(cells: list) -> str:
        return "<tr>" + "".join(
            f'<td style="padding:5px 8px;font-size:12px;{s}">{v}</td>'
            for v, s in cells
        ) + "</tr>"

    def _th(label: str) -> str:
        return (
            f'<th style="text-align:left;padding:5px 8px;color:#6b7280;font-size:11px;'
            f'font-weight:bold;border-bottom:1px solid #e5e7eb;">{label}</th>'
        )

    # Sub-sección 1: Quality Score (solo QS_LOW, deduplicado por keyword+campaign)
    _qs_seen = set()
    _qs_findings = []
    for _f in _quality_findings:
        if _f.get("type") != "QS_LOW":
            continue
        _qs_key = (_f.get("keyword_text", ""), _f.get("campaign_id", ""))
        if _qs_key in _qs_seen:
            continue
        _qs_seen.add(_qs_key)
        _qs_findings.append(_f)
    if _qs_findings:
        _qs_rows = ""
        for _qf in _qs_findings[:10]:
            _qs_val = _qf.get("quality_score")
            _qs_color = "color:#dc2626;font-weight:bold;" if (_qs_val and _qs_val < 4) else ""
            _qs_rows += _quality_table_row([
                (_qf.get("keyword_text", "—"), "color:#374151;"),
                (_qf.get("campaign_name", "—"), "color:#6b7280;"),
                (str(_qs_val) if _qs_val else "—", _qs_color),
                (_qf.get("creative_quality_score") or "—", ""),
                (_qf.get("post_click_quality_score") or "—", ""),
                (_qf.get("search_predicted_ctr") or "—", ""),
            ])
        _qs_block = f"""
    <p style="margin:8px 0 4px 0;font-size:11px;font-weight:bold;color:#6b7280;">Quality Score (keywords &lt; 7)</p>
    <table width="100%" style="border-collapse:collapse;font-size:12px;">
      <tr style="background:#f9fafb;">{_th("Keyword")}{_th("Campaña")}{_th("QS")}{_th("Anuncio")}{_th("Landing")}{_th("CTR")}</tr>
      {_qs_rows}
    </table>"""
    else:
        _qs_block = '<p style="margin:8px 0;font-size:12px;color:#16a34a;">✅ Quality Score OK — sin keywords críticas</p>'

    # Sub-sección 2: Estado de Anuncios
    _ad_findings = [f for f in _quality_findings if f.get("type") in
                    ("AD_STRENGTH_POOR", "AD_STRENGTH_AVERAGE", "AD_DISAPPROVED", "AD_IN_REVIEW")]
    if _ad_findings:
        _ad_rows = ""
        for _af in _ad_findings[:10]:
            _af_type = _af.get("type", "")
            _af_color = "color:#dc2626;font-weight:bold;" if "POOR" in _af_type or "DISAPPROVED" in _af_type else ""
            _ad_rows += _quality_table_row([
                (_af.get("campaign_name", "—"), "color:#374151;"),
                (_af.get("ad_group_name", "—"), "color:#6b7280;"),
                (_af_type.replace("AD_", "").replace("_", " "), _af_color),
            ])
        _ad_block = f"""
    <p style="margin:8px 0 4px 0;font-size:11px;font-weight:bold;color:#6b7280;">Estado de Anuncios</p>
    <table width="100%" style="border-collapse:collapse;font-size:12px;">
      <tr style="background:#f9fafb;">{_th("Campaña")}{_th("Ad Group")}{_th("Estado")}</tr>
      {_ad_rows}
    </table>"""
    else:
        _ad_block = '<p style="margin:8px 0;font-size:12px;color:#16a34a;">✅ Ad Strength y aprobación OK — sin rechazos ni anuncios débiles</p>'

    # Sub-sección 3: Impression Share
    _is_findings = [f for f in _quality_findings if f.get("type") in
                    ("LOW_IMPRESSION_SHARE", "LOST_IS_RANK_HIGH", "LOST_IS_BUDGET_HIGH")]
    if _is_findings:
        _is_rows = ""
        _seen_is_camps = set()
        for _isf in _is_findings:
            _camp_key = _isf.get("campaign_id", "")
            if _camp_key in _seen_is_camps:
                continue
            _seen_is_camps.add(_camp_key)
            _sis   = _isf.get("search_impression_share", 0)
            _rlost = _isf.get("search_rank_lost_impression_share", 0)
            _blost = _isf.get("search_budget_lost_impression_share", 0)
            _is_rows += _quality_table_row([
                (_isf.get("campaign_name", "—"), "color:#374151;"),
                (f"{_sis*100:.0f}%" if _sis else "—", "color:#374151;font-weight:bold;"),
                (f"{_rlost*100:.0f}%" if _rlost else "—", "color:#d97706;" if _rlost > 0.30 else ""),
                (f"{_blost*100:.0f}%" if _blost else "—", "color:#d97706;" if _blost > 0.20 else ""),
            ])
        _is_block = f"""
    <p style="margin:8px 0 4px 0;font-size:11px;font-weight:bold;color:#6b7280;">Visibilidad (Impression Share)</p>
    <table width="100%" style="border-collapse:collapse;font-size:12px;">
      <tr style="background:#f9fafb;">{_th("Campaña")}{_th("IS %")}{_th("Perdido Rank")}{_th("Perdido Budget")}</tr>
      {_is_rows}
    </table>"""
    else:
        _is_block = '<p style="margin:8px 0;font-size:12px;color:#16a34a;">✅ Impression Share — sin alertas de visibilidad</p>'

    # Sub-sección 4: Acciones Creativas del Día
    _exec_creative = [a for a in _creative_actions_email
                      if a.get("action") not in ("alert_disapproved",)]
    _alert_creative = [a for a in _creative_actions_email if a.get("action") == "alert_disapproved"]
    if _exec_creative or _alert_creative:
        _ca_lines = ""
        for _ca in _exec_creative[:8]:
            _ca_status = (_ca.get("result") or {}).get("status", "—")
            _ca_icon   = "✅" if _ca_status in ("success", "dry_run") else "⚠️"
            _ca_camp   = _ca.get("campaign_name", "—")
            _ca_act    = _ca.get("action", "").replace("_", " ")
            _ca_items  = _ca.get("headlines") or _ca.get("descriptions") or []
            _ca_items_str = ", ".join(f'"{x}"' for x in _ca_items[:3])
            _ca_lines += (
                f'<li style="font-size:12px;margin-bottom:4px;">'
                f'{_ca_icon} <strong>{_ca_camp}</strong> — {_ca_act}: {_ca_items_str}'
                f' <span style="color:#9ca3af;">({_ca_status})</span></li>'
            )
        for _ca in _alert_creative[:5]:
            _ca_lines += (
                f'<li style="font-size:12px;margin-bottom:4px;color:#dc2626;">'
                f'⚠️ Anuncio RECHAZADO en <strong>{_ca.get("campaign_name","—")}</strong>'
                f' (ad_id: {_ca.get("ad_id","—")})</li>'
            )
        _creative_act_block = f'<ul style="margin:4px 0;padding-left:16px;">{_ca_lines}</ul>'
    else:
        _creative_act_block = '<p style="font-size:12px;color:#16a34a;">✅ Todos los anuncios en buen estado — sin acciones creativas</p>'

    # ── Campañas pausadas ────────────────────────────────────────────────────
    _paused_block = ""
    if _paused_campaigns_email:
        _pc_rows = ""
        for _pc in _paused_campaigns_email:
            _pc_name   = str(_pc.get("campaign_name", "—"))
            _pc_status = str((_pc.get("result") or {}).get("status", "—"))
            _pc_color  = "#15803d" if _pc_status == "executed" else "#dc2626"
            _pc_label  = "Pausada ✓" if _pc_status == "executed" else f"Error: {_pc_status}"
            _pc_rows += (
                f'<tr style="border-top:1px solid #f0f0f0;">'
                f'<td style="padding:5px 8px;color:#374151;font-size:12px;">{_pc_name}</td>'
                f'<td style="text-align:right;padding:5px 8px;font-size:12px;'
                f'color:{_pc_color};font-weight:bold;">{_pc_label}</td></tr>'
            )
        _paused_block = (
            '<p style="margin:8px 0 4px 0;font-size:11px;font-weight:bold;color:#6b7280;">Campañas Pausadas en este Ciclo</p>'
            '<table width="100%" style="border-collapse:collapse;font-size:12px;">'
            + _pc_rows
            + '</table>'
        )

    # Sub-sección: Keywords con problema estructural de CTR
    _structural_ctr_findings = [f for f in _quality_findings if f.get("type") == "CTR_STRUCTURAL_ISSUE"]
    if _structural_ctr_findings:
        _sc_rows = ""
        for _sc in _structural_ctr_findings[:10]:
            _sc_qs = _sc.get("quality_score")
            _sc_rows += _quality_table_row([
                (_sc.get("keyword_text", "—"), "color:#374151;"),
                (_sc.get("campaign_name", "—"), "color:#6b7280;"),
                (str(_sc_qs) if _sc_qs else "—", "color:#d97706;font-weight:bold;"),
                (_sc.get("creative_quality_score") or "—", ""),
                (_sc.get("post_click_quality_score") or "—", ""),
                (_sc.get("ad_strength_summary") or "—", "color:#16a34a;"),
            ])
        _structural_ctr_block = f"""
    <p style="margin:12px 0 2px 0;font-size:11px;font-weight:bold;color:#6b7280;">Keywords que requieren mayor especificidad</p>
    <p style="margin:0 0 6px 0;font-size:11px;color:#6b7280;">El anuncio ya es fuerte (GOOD/EXCELLENT) — el QS bajo es por CTR esperado, no por creatividad. La búsqueda necesita un ad group propio con mensaje más específico.</p>
    <table width="100%" style="border-collapse:collapse;font-size:12px;">
      <tr style="background:#f9fafb;">{_th("Keyword")}{_th("Campaña")}{_th("QS")}{_th("Anuncio")}{_th("Landing")}{_th("RSA Strength")}</tr>
      {_sc_rows}
    </table>
    <p style="margin:4px 0 0 0;font-size:11px;color:#6b7280;">💡 Siguiente paso ideal: crear ad group dedicado con RSA hiper-relevante para cada intención. No requiere acción automática.</p>"""
    else:
        _structural_ctr_block = ""

    # Sub-sección: Ad Groups creados por Builder (auto-ejecutados)
    _builder_prop_block = ""
    if _builder_proposals_email:
        _bp_rows = ""
        for _bp in _builder_proposals_email[:5]:
            _bp_name    = _bp.get("ad_group_name", "—")
            _bp_camp    = _bp.get("campaign_name", "—")
            _bp_intent  = _bp.get("intent", "—")
            _bp_kws     = _bp.get("keywords", [])
            _bp_heads   = _bp.get("headlines", [])[:3]
            _bp_kw_str  = ", ".join(f'"{k}"' for k in _bp_kws[:5])
            _bp_head_str = " · ".join(f'"{h}"' for h in _bp_heads)
            _bp_status  = (_bp.get("result") or {}).get("status", "error")
            _bp_icon    = "✅ Creado" if _bp_status == "success" else "❌ Error"
            _bp_icon_color = "#16a34a" if _bp_status == "success" else "#dc2626"
            _bp_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'🏗️ {_bp_name}'
                f'<span style="margin-left:8px;background:#eff6ff;color:#1d4ed8;'
                f'padding:2px 6px;border-radius:3px;font-size:10px;">{_bp_intent}</span>'
                f'<span style="margin-left:8px;font-size:11px;font-weight:bold;'
                f'color:{_bp_icon_color};">{_bp_icon}</span></p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">Campaña: {_bp_camp}</p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#374151;">Keywords: {_bp_kw_str}</p>'
                f'<p style="margin:0 0 4px 0;font-size:11px;color:#6b7280;">Headlines: {_bp_head_str}</p>'
                f'</td></tr>'
            )
        _builder_prop_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 4px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">🏗️ Ad Groups Creados Hoy</p>'
            f'<p style="margin:0 0 8px 0;font-size:11px;color:#6b7280;">'
            f'El agente detectó keywords que necesitan un ad group dedicado y los creó automáticamente '
            f'para mejorar el CTR. Los anuncios existentes son fuertes — '
            f'el problema era de ajuste entre la búsqueda y el mensaje.</p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_bp_rows}</table>'
            f'</td></tr>'
        )

    _quality_block = f"""
  <tr><td style="padding:14px 20px 6px 20px;">
    <p style="margin:0 0 8px 0;font-size:12px;font-weight:bold;color:#6b7280;
              text-transform:uppercase;letter-spacing:0.5px;">🎨 Salud de Anuncios y Calidad</p>
    {_qs_block}
    {_structural_ctr_block}
    {_ad_block}
    {_is_block}
    <p style="margin:8px 0 4px 0;font-size:11px;font-weight:bold;color:#6b7280;">Acciones Creativas del Día</p>
    {_creative_act_block}
    {_paused_block}
  </td></tr>"""

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

    # ── Override de action por coherencia con ejecuciones AI y pendientes ────
    _ai_reduce_executed = [d for d in _ai_executed if d.get("action") == "reduce"]
    if _ai_reduce_executed:
        action = "El agente ya ajustó presupuestos para controlar el gasto mensual."
    _kw_pending_count = len(_kw_proposals)  # solo keywords visibles en la sección manual
    if _kw_pending_count > 0:
        _pending_note = f"Hay {_kw_pending_count} keyword(s) esperando tu aprobación en el correo."
        action = (action + " " + _pending_note).strip() if action not in ("No.", "") else _pending_note

    # Línea de contexto del día (ocupación histórica)
    _occ_ctx = run.get("occupancy_context") or {}
    _occ_context_line = ""
    # Mostrar si hay datos de Sheets O si al menos tenemos el día de hoy (aunque data_sufficient=False)
    if _occ_ctx.get("today"):
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
            _d_reason  = str(_d.get("reason", ""))[:700]
            _d_conf    = int(_d.get("confidence", 0))
            _d_old     = float(_d.get("exec_result", {}).get("old_budget_mxn") or 0)
            if _d_old == 0 and _d_pct != 0:
                # Recalcular desde new_budget y change_pct cuando exec_result no lo trae
                _d_old = round(_d_budget / (1 + _d_pct / 100), 2)
            _d_color   = "#15803d" if _d_action == "scale" else "#dc2626"
            _d_arrow   = "↑" if _d_action == "scale" else "↓"
            _d_conf_color = "#15803d" if _d_conf >= 80 else "#d97706" if _d_conf >= 70 else "#dc2626"
            _d_budget_str = (
                f'${_d_old:,.0f} → <strong style="color:{_d_color};">${_d_budget:,.0f}/día</strong>'
                if _d_old > 0
                else f'<strong style="color:{_d_color};">→ ${_d_budget:,.0f}/día</strong>'
            )
            _ai_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:10px 0;">'
                f'<p style="margin:0 0 3px 0;font-size:13px;font-weight:bold;color:#111;">'
                f'🧠 {_d_name}'
                f'<span style="margin-left:8px;background:{_d_color}20;color:{_d_color};'
                f'padding:2px 6px;border-radius:3px;font-size:10px;font-weight:bold;">'
                f'{_d_arrow} {_d_action.upper()}</span></p>'
                f'<p style="margin:0 0 2px 0;font-size:11px;color:#6b7280;">'
                f'{_d_budget_str}'
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
            _kd_reason = str(_kd.get("reason", ""))[:700]
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
    _redistribution_analysis_block = ""
    _ra_sources = _redistribution_analysis.get("fund_sources") or []
    _ra_receivers = _redistribution_analysis.get("receiver_candidates") or []
    _ra_allocations = _redistribution_analysis.get("allocation_matrix") or []
    if _ra_sources or _ra_receivers or _ra_allocations:
        _ra_rows = ""
        for _src in _ra_sources:
            _ra_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:8px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                f'Fuente: {_src.get("campaign_name", "—")}</p>'
                f'<p style="margin:0;font-size:12px;color:#b91c1c;">'
                f'Libera ${float(_src.get("freed_daily_mxn", 0) or 0):,.0f}/dia via {_src.get("source_action", "reduce")}</p>'
                f'</td></tr>'
            )
        for _rcv in _ra_receivers:
            _ra_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:8px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                f'Candidata: {_rcv.get("campaign_name", "—")}</p>'
                f'<p style="margin:0;font-size:12px;color:#166534;">'
                f'Scale elegible hasta ${float(_rcv.get("max_receivable_daily_mxn", 0) or 0):,.0f}/dia</p>'
                f'</td></tr>'
            )
        for _alloc in _ra_allocations:
            _ra_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:8px 0;">'
                f'<p style="margin:0 0 2px 0;font-size:12px;font-weight:bold;color:#111;">'
                f'Traza: {_alloc.get("from_campaign_name", "—")} -> {_alloc.get("to_campaign_name", "—")}</p>'
                f'<p style="margin:0;font-size:12px;color:#1d4ed8;">'
                f'${float(_alloc.get("amount_daily_mxn", 0) or 0):,.0f}/dia analizados</p>'
                f'</td></tr>'
            )

        _redistribution_analysis_block = (
            f'<tr><td style="padding:14px 20px 4px 20px;">'
            f'<p style="margin:0 0 6px 0;font-size:12px;font-weight:bold;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.5px;">Redistribucion potencial analizada</p>'
            f'<p style="margin:0 0 6px 0;font-size:12px;color:#1565c0;font-weight:bold;">Sin ejecucion automatica</p>'
            f'<p style="margin:0 0 8px 0;font-size:12px;color:#6b7280;">No cambia presupuestos todavia.</p>'
            f'<p style="margin:0 0 8px 0;font-size:12px;color:#111;">'
            f'Fondo liberado potencial: <strong>${float(_redistribution_analysis.get("potential_freed_daily_mxn", 0) or 0):,.0f}/dia</strong>'
            f' &nbsp;·&nbsp; Balance neto analizado: <strong>${float(_redistribution_analysis.get("net_daily_mxn", 0) or 0):,.0f}/dia</strong></p>'
            f'<table width="100%" cellpadding="0" cellspacing="0">{_ra_rows}</table>'
            f'</td></tr>'
        )

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

  <!-- SECCIÓN: Pedidos Online GloriaFood (24h) -->
  {_pedidos_block}

  <!-- Separador -->
  <tr><td style="padding:8px 20px 0 20px;"><hr style="border:none; border-top:1px solid #eee; margin:0;"></td></tr>

  <!-- SECCIÓN: Salud de Anuncios y Calidad (Fase 6D) -->
  {_quality_block}

  <!-- SECCIÓN: Propuestas de Ad Groups (Fase 6E Builder) -->
  {_builder_prop_block}

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
  {_redistribution_analysis_block}

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

    # Construir label dinámico basado en acciones reales
    _acciones = []
    _exec_budget = run.get("executed_budget", [])
    _exec_kw = run.get("ai_keyword_decisions", [])
    _builder = run.get("builder_executed", [])
    _paused = run.get("paused_campaigns", [])

    if _exec_budget:
        _budget_count = len(_exec_budget)
        _acciones.append(f"{_budget_count} ajuste{'s' if _budget_count > 1 else ''} de presupuesto")
    if _exec_kw:
        _kw_count = len(_exec_kw)
        _acciones.append(f"{_kw_count} keyword{'s' if _kw_count > 1 else ''}")
    if _builder:
        _bg_count = len([b for b in _builder if isinstance(b.get("result"), dict) and b["result"].get("status") == "success"])
        if _bg_count:
            _acciones.append(f"{_bg_count} ad group{'s' if _bg_count > 1 else ''} creado{'s' if _bg_count > 1 else ''}")
    if _paused:
        _pc_count = len([p for p in _paused if isinstance(p.get("result"), dict) and p["result"].get("status") == "executed"])
        if _pc_count:
            _acciones.append(f"{_pc_count} campaña{'s' if _pc_count > 1 else ''} pausada{'s' if _pc_count > 1 else ''}")

    if _acciones:
        _label = " + ".join(_acciones)
    elif rc == "con_observaciones":
        _label = "Con observaciones"
    elif rc == "con_alertas":
        _label = "Con alertas"
    elif rc == "con_errores":
        _label = "Con errores"
    else:
        _label = "Sin cambios"

    fecha = run.get("timestamp_merida", "—")
    subject = f"[Thai Thai Agente] Actividad diaria — {_label} · {fecha}"

    # Usar el nuevo reporte pro si hay datos del audit_engine
    if run.get("audit_result") and run["audit_result"].get("score") is not None:
        html_body = _build_pro_daily_html(run)
    else:
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
