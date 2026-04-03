"""
Routes de Reservaciones — POST /reservations, GET /reservations
Incluye helpers de email, WhatsApp e ICS.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.db_sync import get_db_path

router = APIRouter(tags=["reservations"])


class ReservationRequest(BaseModel):
    name: str
    email: str
    phone: str
    date: str
    time: str
    guests: str
    occasion: Optional[str] = None


def _get_supabase_conn():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(database_url, connect_timeout=5)
    except Exception as e:
        print(f"[db_supabase_error] Conexión fallida, usando SQLite: {e}")
        return None


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
    import urllib.request
    import urllib.parse

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
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={phone}&text={urllib.parse.quote(text)}&apikey={apikey}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            print(f"[whatsapp_sent] status={resp.status}")
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


@router.post("/reservations")
async def create_reservation(reservation: ReservationRequest):
    """Guarda una reserva en la base de datos y envía notificaciones."""
    try:
        pg_conn = _get_supabase_conn()
        if pg_conn:
            cursor = pg_conn.cursor()
            cursor.execute("""
                INSERT INTO reservations (name, email, phone, date, time, guests, occasion)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (reservation.name, reservation.email, reservation.phone, reservation.date,
                  reservation.time, int(reservation.guests), reservation.occasion or ""))
            reservation_id = cursor.fetchone()[0]
            pg_conn.commit()
            pg_conn.close()
            db_source = "supabase"
        else:
            import sqlite3
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reservations (name, email, phone, date, time, guests, occasion)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (reservation.name, reservation.email, reservation.phone, reservation.date,
                  reservation.time, reservation.guests, reservation.occasion or ""))
            conn.commit()
            reservation_id = cursor.lastrowid
            conn.close()
            db_source = "sqlite_fallback"

        print(f"[reservation_created] id={reservation_id} name={reservation.name} date={reservation.date} db={db_source}")

        email_cfg = _check_email_config()
        if not email_cfg["ok"]:
            print(f"[reservation_warning] emails desactivados: {email_cfg['issues']}")

        send_email_to_customer(reservation)
        send_email_to_owner(reservation)
        send_whatsapp_restaurant(reservation)

        return {
            "status": "success",
            "reservation_id": reservation_id,
            "message": f"Reserva confirmada para {reservation.name} el {reservation.date} a las {reservation.time}"
        }
    except Exception as e:
        print(f"[reservation_failed] error={e}")
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la reserva: {e}")


@router.get("/reservations")
async def get_reservations(limit: int = 50):
    """Retorna las reservas más recientes."""
    try:
        pg_conn = _get_supabase_conn()
        if pg_conn:
            cursor = pg_conn.cursor()
            cursor.execute("""
                SELECT id, name, email, phone,
                       date::text, time::text, guests, occasion, status, created_at::text
                FROM reservations
                ORDER BY created_at DESC LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            pg_conn.close()
        else:
            import sqlite3
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, email, phone, date, time, guests, occasion, status, created_at
                FROM reservations ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()

        reservations = [{
            "id": r[0], "name": r[1], "email": r[2], "phone": r[3],
            "date": r[4], "time": r[5], "guests": r[6],
            "occasion": r[7], "status": r[8], "created_at": r[9]
        } for r in rows]

        return {"status": "success", "total": len(reservations), "reservations": reservations}
    except Exception as e:
        return {"status": "error", "message": str(e)}
