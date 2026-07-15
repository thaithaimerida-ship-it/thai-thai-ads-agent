"""
Routes de Reservaciones — POST /reservations, GET /reservations
Incluye helpers de email, WhatsApp e ICS.
"""
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine import reservas_sheets
from engine.url_safety import UnsafeUrlError, safe_urlopen

router = APIRouter(tags=["reservations"])
CALLMEBOT_BASE_URL = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_ALLOWED_HOSTS = {"api.callmebot.com"}
# WhatsApp público del restaurante — se le da al cliente si no pudimos confirmarle.
RESTAURANT_WHATSAPP_DISPLAY = "+52 999 931 7457"


class ReservationRequest(BaseModel):
    name: str
    email: str
    phone: str
    date: str
    time: str
    guests: str
    occasion: Optional[str] = None
    # Opcionales, retrocompatibles con el frontend actual (no cambia el contrato).
    notas: Optional[str] = None
    origen: Optional[str] = "landing"


def _check_email_config() -> dict:
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_APP_PASSWORD", "")
    issues = []
    if not sender:
        issues.append("EMAIL_SENDER no configurado")
    if not password:
        issues.append("EMAIL_APP_PASSWORD no configurado")
    elif "xxxx" in password:
        issues.append("EMAIL_APP_PASSWORD contiene placeholder 'xxxx'")
    return {"ok": len(issues) == 0, "issues": issues}


def _generate_ics(reservation: ReservationRequest) -> str:
    import re
    try:
        dt_str = f"{reservation.date} {reservation.time}"
        dt_start = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            dt_start = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
        except ValueError:
            dt_start = datetime.now().replace(hour=19, minute=0, second=0)

    dt_end = dt_start + timedelta(hours=2)
    fmt = "%Y%m%dT%H%M%S"
    occasion_desc = f" — {reservation.occasion}" if reservation.occasion else ""
    uid = f"reserva-{reservation.date}-{re.sub(r'[^a-z0-9]', '', reservation.name.lower())}@thaithaimerida.com"

    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Thai Thai Merida//Reservas//ES\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{dt_start.strftime(fmt)}\r\n"
        f"DTEND:{dt_end.strftime(fmt)}\r\n"
        f"SUMMARY:Cena en Thai Thai Mérida{occasion_desc}\r\n"
        f"DESCRIPTION:Reserva para {reservation.guests} personas.\\n"
        f"Dirección: Calle 30 No. 351\\, Col. Emiliano Zapata Norte\\, Mérida\\, Yucatán\\n"
        f"¿Necesitas cambiar algo? Escríbenos al WhatsApp.\r\n"
        "LOCATION:Calle 30 No. 351\\, Col. Emiliano Zapata Norte\\, Mérida\\, Yucatán\r\n"
        "STATUS:CONFIRMED\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def send_whatsapp_restaurant(reservation: ReservationRequest):
    phone = os.getenv("CALLMEBOT_PHONE", "")
    apikey = os.getenv("CALLMEBOT_APIKEY", "")
    if not phone or not apikey:
        print("[WA] CALLMEBOT_PHONE o CALLMEBOT_APIKEY no configurados — saltando")
        return

    occasion_part = f"\nOcasion: {reservation.occasion}" if reservation.occasion else ""
    text = (
        f"Nueva Reserva Thai Thai\n"
        f"Nombre: {reservation.name}\n"
        f"Fecha: {reservation.date} a las {reservation.time}\n"
        f"Personas: {reservation.guests}{occasion_part}\n"
        f"Tel: {reservation.phone}"
    )
    url = (
        f"{CALLMEBOT_BASE_URL}"
        f"?phone={phone}&text={urllib.parse.quote(text)}&apikey={apikey}"
    )
    try:
        with safe_urlopen(url, allowed_hosts=CALLMEBOT_ALLOWED_HOSTS, timeout=10) as resp:
            print(f"[whatsapp_sent] status={resp.status}")
    except UnsafeUrlError:
        print("[whatsapp_failed] unsafe_url")
    except Exception as e:
        print(f"[whatsapp_failed] error={e}")


def send_email_to_customer(reservation: ReservationRequest):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg = _check_email_config()
    if not cfg["ok"]:
        print(f"[customer_email_failed] config inválida: {cfg['issues']}")
        return

    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_APP_PASSWORD")
    occasion_line = f"\n🎉 <b>Ocasión:</b> {reservation.occasion}" if reservation.occasion else ""

    client_html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;background:#09090b;color:#fff;border-radius:16px;overflow:hidden">
      <div style="background:#c2410c;padding:24px 32px">
        <h1 style="margin:0;font-size:22px;letter-spacing:1px">Thai Thai Mérida</h1>
        <p style="margin:4px 0 0;color:#fed7aa;font-size:13px">Cocina tailandesa artesanal</p>
      </div>
      <div style="padding:32px">
        <h2 style="color:#4ade80;margin-top:0">Reserva confirmada ✅</h2>
        <p style="color:#a1a1aa">Hola <b style="color:#fff">{reservation.name}</b>, ya tienes tu mesa asegurada.</p>
        <div style="background:#18181b;border-radius:12px;padding:20px;margin:20px 0">
          <p style="margin:6px 0;color:#d4d4d8">📅 <b>Fecha:</b> {reservation.date}</p>
          <p style="margin:6px 0;color:#d4d4d8">🕐 <b>Hora:</b> {reservation.time}</p>
          <p style="margin:6px 0;color:#d4d4d8">👥 <b>Personas:</b> {reservation.guests}{occasion_line}</p>
        </div>
        <a href="https://maps.google.com/?q=Thai+Thai+Merida+Calle+30+No.351+Emiliano+Zapata+Norte"
           style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:bold;font-size:14px;margin-bottom:16px">
          Ver en Google Maps
        </a>
        <p style="color:#a1a1aa;font-size:13px;margin:4px 0">Calle 30 No. 351, Col. Emiliano Zapata Norte, Mérida, Yucatán</p>
        <p style="color:#71717a;font-size:12px;margin-top:24px">¿Necesitas cambiar algo? Escríbenos al WhatsApp o llámanos.</p>
      </div>
    </div>
    """

    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Reserva confirmada — Thai Thai Merida"
    msg["From"] = f"Thai Thai Merida <{sender}>"
    msg["To"] = reservation.email

    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText(client_html, "html", "utf-8"))
    msg.attach(html_part)

    ics_content = _generate_ics(reservation)
    ics_part = MIMEText(ics_content, "calendar", "utf-8")
    ics_part.add_header("Content-Disposition", "attachment", filename="reserva_thai_thai.ics")
    msg.attach(ics_part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, reservation.email, msg.as_bytes())
        print(f"[customer_email_sent] destinatario={reservation.email}")
    except Exception as e:
        print(f"[customer_email_failed] error={e}")


def send_email_to_owner(reservation: ReservationRequest):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg = _check_email_config()
    if not cfg["ok"]:
        print(f"[owner_email_failed] config inválida: {cfg['issues']}")
        return

    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_APP_PASSWORD")
    restaurant_email = os.getenv("EMAIL_RESTAURANT", sender)
    occasion_line = f"<p style='margin:6px 0'><b>Ocasion:</b> {reservation.occasion}</p>" if reservation.occasion else ""
    notas_line = f"<p style='margin:6px 0;color:#a1a1aa'><b>Notas:</b> {reservation.notas}</p>" if reservation.notas else ""
    origen_line = f"<p style='margin:6px 0;color:#71717a;font-size:12px'><b>Origen:</b> {reservation.origen}</p>" if reservation.origen else ""
    wa_link = f"https://wa.me/{reservation.phone.replace('+','').replace(' ','').replace('-','')}"

    restaurant_html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;background:#09090b;color:#fff;border-radius:16px;overflow:hidden">
      <div style="background:#c2410c;padding:20px 28px">
        <h1 style="margin:0;font-size:18px">Nueva Reserva — Thai Thai</h1>
      </div>
      <div style="padding:28px">
        <div style="background:#18181b;border-radius:12px;padding:20px;margin-bottom:20px">
          <p style="margin:6px 0;font-size:20px;font-weight:bold;color:#4ade80">{reservation.name}</p>
          <p style="margin:6px 0;color:#d4d4d8"><b>Fecha:</b> {reservation.date} a las {reservation.time}</p>
          <p style="margin:6px 0;color:#d4d4d8"><b>Personas:</b> {reservation.guests}</p>
          {occasion_line}
          <p style="margin:6px 0;color:#a1a1aa"><b>Tel:</b> {reservation.phone}</p>
          <p style="margin:6px 0;color:#a1a1aa"><b>Email:</b> {reservation.email}</p>
          {notas_line}
          {origen_line}
        </div>
        <a href="{wa_link}" style="display:inline-block;background:#25d366;color:#fff;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:bold;font-size:16px">Responder por WhatsApp</a>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[RESERVA] {reservation.name} — {reservation.date} {reservation.time} ({reservation.guests} personas)"
    msg["From"] = f"Thai Thai Reservas <{sender}>"
    msg["To"] = restaurant_email
    msg.attach(MIMEText(restaurant_html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, restaurant_email, msg.as_bytes())
        print(f"[owner_email_sent] destinatario={restaurant_email}")
    except Exception as e:
        print(f"[owner_email_failed] error={e}")


def _notify_all(reservation: "ReservationRequest") -> tuple[str, bool]:
    """Dispara los 3 canales, cada uno AISLADO en su try/except. Si uno falla, los otros
    siguen. Retorna (resumen 'email_cliente:ok, email_dueño:ok, whatsapp:error', alguna_ok)."""
    resultados = []
    any_ok = False
    for etiqueta, fn in (
        ("email_cliente", send_email_to_customer),
        ("email_dueño", send_email_to_owner),
        ("whatsapp", send_whatsapp_restaurant),
    ):
        try:
            fn(reservation)
            resultados.append(f"{etiqueta}:ok")
            any_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"[notify_failed] canal={etiqueta} error={e}")
            resultados.append(f"{etiqueta}:error")
    return ", ".join(resultados), any_ok


@router.post("/reservations")
async def create_reservation(reservation: ReservationRequest):
    """Orden nuevo: validar → NOTIFICAR (independiente) → PERSISTIR en Sheets.
    Una reserva NUNCA se pierde por almacenamiento. 200 si al menos una notificación salió."""
    # 1) Validación: Pydantic ya validó el payload al entrar.

    # 2) Notificar — cada canal aislado. El correo al dueño trae TODOS los datos: red de seguridad final.
    notif_result, any_ok = _notify_all(reservation)
    print(f"[reservation_notified] name={reservation.name} date={reservation.date} -> {notif_result}")

    # 3) Persistir en Google Sheets — su fallo NO rompe la respuesta.
    data = reservation.model_dump()
    persist = reservas_sheets.append_reservation(data, notif_result)
    persisted = persist["ok"]

    if not persisted:
        # Reserva NO quedó en Sheets → red de seguridad = correo al dueño (si salió). Marca durable.
        print(f"[reservation_persist_FAILED] id={persist['id']} error={persist['error']} data={data}")
        try:
            reservas_sheets.record_persist_failure(persist["id"], data, persist["error"] or "desconocido")
        except Exception as e:  # noqa: BLE001
            print(f"[reservation_persist_mark_failed] error={e}")
    elif not any_ok:
        # Reserva SÍ quedó en Sheets pero el cliente no recibió confirmación (todos los canales
        # fallaron) → marcar para que el monitor alerte "contáctalos".
        print(f"[reservation_unconfirmed] id={persist['id']} data={data} notif={notif_result}")
        try:
            reservas_sheets.record_unconfirmed(persist["id"], data, notif_result)
        except Exception as e:  # noqa: BLE001
            print(f"[reservation_unconfirmed_mark_failed] error={e}")

    # 4) 502 SOLO cuando no hay rastro en ningún lado: ni en Sheets ni ninguna notificación.
    if not persisted and not any_ok:
        raise HTTPException(
            status_code=502,
            detail="No se pudo registrar ni notificar la reserva por ningún medio",
        )

    # 5) 200. Si guardó pero no pudimos avisar al cliente, decírselo y darle el WhatsApp.
    if any_ok:
        message = f"Reserva confirmada para {reservation.name} el {reservation.date} a las {reservation.time}"
    else:
        message = (
            "Tu reserva quedó registrada, pero no pudimos enviarte la confirmación en este momento. "
            f"Escríbenos por WhatsApp al {RESTAURANT_WHATSAPP_DISPLAY} para confirmarla."
        )

    return {
        "status": "success",
        "reservation_id": persist["id"],
        "persisted": persisted,
        "notified": any_ok,
        "message": message,
    }


@router.get("/reservations")
async def get_reservations(limit: int = 50):
    """Lee las reservas más recientes de la pestaña `Reservas` (Google Sheets)."""
    try:
        reservas = reservas_sheets.list_reservations(limit=limit)
        return {"status": "success", "total": len(reservas), "reservations": reservas}
    except Exception as e:  # noqa: BLE001
        print(f"[get_reservations_error] {e}")
        return {"status": "error", "message": str(e), "reservations": []}
