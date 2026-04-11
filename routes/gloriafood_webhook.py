"""
Webhook receptor de pedidos aceptados de GloriaFood.
Recibe POST JSON de la API Accepted Orders v2.
Doc: https://github.com/GlobalFood/integration_docs/blob/master/accepted_orders/README.md
"""
import logging
import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger("gloriafood_webhook")
router = APIRouter()

# Master key configurado en GloriaFood — se valida en cada request
GLORIAFOOD_MASTER_KEY = os.getenv("GLORIAFOOD_MASTER_KEY", "")


def _parse_order(order: dict) -> dict:
    """Extrae campos relevantes de un pedido GloriaFood v2."""
    # Total del pedido
    total_price = 0.0
    try:
        total_price = float(order.get("total_price", 0) or 0)
    except (ValueError, TypeError):
        pass

    # Items del pedido
    items = []
    for item in (order.get("items") or []):
        items.append({
            "name": item.get("name", ""),
            "quantity": item.get("quantity", 1),
            "price": float(item.get("price", 0) or 0),
        })

    # Tipo de pedido
    order_type = order.get("type", "unknown")  # "pickup" o "delivery"

    # Datos del cliente (para Enhanced Conversions futuro)
    client = order.get("client", {}) or {}
    client_name = client.get("first_name", "") + " " + client.get("last_name", "")
    client_phone = client.get("phone", "")
    client_email = client.get("email", "")

    # Método de pago
    payment = order.get("payment", "")

    # Timestamps
    accepted_at = order.get("accepted_at", "")

    return {
        "gloriafood_order_id": str(order.get("id") or order.get("order_id") or order.get("cust_order_id") or ""),
        "total_price_mxn": total_price,
        "order_type": order_type,
        "payment_method": payment,
        "client_name": client_name.strip(),
        "client_phone": client_phone,
        "client_email": client_email,
        "items": items,
        "items_count": len(items),
        "accepted_at": accepted_at,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def _log_order_to_db(parsed_order: dict):
    """Guarda el pedido en SQLite para el reporte diario."""
    try:
        from engine.memory import get_db_path
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Crear tabla si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gloriafood_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gloriafood_order_id TEXT UNIQUE,
                total_price_mxn REAL,
                order_type TEXT,
                payment_method TEXT,
                client_name TEXT,
                client_phone TEXT,
                client_email TEXT,
                items_json TEXT,
                items_count INTEGER,
                accepted_at TEXT,
                received_at TEXT,
                conversion_sent INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO gloriafood_orders
            (gloriafood_order_id, total_price_mxn, order_type, payment_method,
             client_name, client_phone, client_email, items_json, items_count,
             accepted_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parsed_order["gloriafood_order_id"],
            parsed_order["total_price_mxn"],
            parsed_order["order_type"],
            parsed_order["payment_method"],
            parsed_order["client_name"],
            parsed_order["client_phone"],
            parsed_order["client_email"],
            json.dumps(parsed_order["items"], ensure_ascii=False),
            parsed_order["items_count"],
            parsed_order["accepted_at"],
            parsed_order["received_at"],
        ))
        conn.commit()
        conn.close()
        logger.info(
            "Pedido %s guardado: $%.2f MXN, %d items, tipo=%s",
            parsed_order["gloriafood_order_id"],
            parsed_order["total_price_mxn"],
            parsed_order["items_count"],
            parsed_order["order_type"],
        )
        return True
    except Exception as e:
        logger.error("Error guardando pedido en DB: %s", e)
        return False


def _send_google_ads_conversion(parsed_order: dict):
    """
    Conversión offline a Google Ads — pendiente de implementar Enhanced Conversions.
    UploadClickConversions requiere GCLID, que no está disponible en el webhook de GloriaFood.
    TODO: implementar Enhanced Conversions con hashed email/phone cuando esté disponible.
    """
    # Sin GCLID no se puede subir ClickConversion — se omite por ahora
    logger.info(
        "Pedido %s guardado en DB ($%.2f MXN). Conversión Google Ads pendiente — requiere Enhanced Conversions (futuro).",
        parsed_order["gloriafood_order_id"],
        parsed_order["total_price_mxn"],
    )
    return None

    # ── Código para Enhanced Conversions (futuro) ────────────────────────────
    # import os
    # from engine.ads_client import get_ads_client
    # client = get_ads_client()
    # customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")
    # conversion_upload_service = client.get_service("ConversionUploadService")
    # conversion_action_service = client.get_service("GoogleAdsService")
    # query = """
    #     SELECT conversion_action.resource_name, conversion_action.name
    #     FROM conversion_action
    #     WHERE conversion_action.name = 'Pedido completado Gloria Food'
    #     AND conversion_action.status = 'ENABLED'
    # """
    # results = list(conversion_action_service.search(customer_id=customer_id, query=query))
    # if not results:
    #     return False
    # conversion_action_rn = results[0].conversion_action.resource_name
    # click_conversion = client.get_type("ClickConversion")
    # click_conversion.conversion_action = conversion_action_rn
    # click_conversion.conversion_value = parsed_order["total_price_mxn"]
    # click_conversion.currency_code = "MXN"
    # click_conversion.conversion_date_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
    # if parsed_order.get("client_email") or parsed_order.get("client_phone"):
    #     user_identifier = client.get_type("UserIdentifier")
    #     if parsed_order.get("client_email"):
    #         user_identifier.hashed_email = parsed_order["client_email"].lower().strip()
    #     if parsed_order.get("client_phone"):
    #         user_identifier.hashed_phone_number = parsed_order["client_phone"].strip()
    #     click_conversion.user_identifiers.append(user_identifier)
    # request = client.get_type("UploadClickConversionsRequest")
    # request.customer_id = customer_id
    # request.conversions.append(click_conversion)
    # request.partial_failure = True
    # response = conversion_upload_service.upload_click_conversions(request=request)
    # if response.partial_failure_error:
    #     logger.warning("Conversión GloriaFood fallida: %s", response.partial_failure_error.message)
    #     return False
    # return True


@router.post("/webhook/gloriafood")
async def receive_gloriafood_order(request: Request):
    """
    Endpoint receptor de webhooks de GloriaFood.
    GloriaFood envía POST con Authorization header = master key.
    El body contiene uno o más pedidos aceptados en JSON.
    """
    # Validar master key
    auth_header = request.headers.get("Authorization", "")
    if GLORIAFOOD_MASTER_KEY and auth_header not in (
        GLORIAFOOD_MASTER_KEY,
        f"Bearer {GLORIAFOOD_MASTER_KEY}",
    ):
        logger.warning("Webhook GloriaFood: master key inválida — recibida: %s", auth_header[:10] + "...")
        raise HTTPException(status_code=401, detail="Invalid master key")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Webhook GloriaFood payload raw: %s", json.dumps(body, default=str)[:2000])

    # GloriaFood puede mandar:
    # 1. Una lista de pedidos: [{...}, {...}]
    # 2. Un dict con key "orders": {"orders": [{...}]}
    # 3. Un dict que ES el pedido: {"id": ..., "type": ...}
    if isinstance(body, list):
        orders = body
    elif isinstance(body, dict) and "orders" in body:
        orders = body["orders"] if isinstance(body["orders"], list) else [body["orders"]]
    else:
        orders = [body]

    results = []
    for order in orders:
        parsed = _parse_order(order)

        if not parsed["gloriafood_order_id"]:
            logger.warning("Pedido sin ID, ignorando")
            continue

        # 1. Guardar en DB
        db_ok = _log_order_to_db(parsed)

        # 2. Enviar conversión a Google Ads
        ads_ok = _send_google_ads_conversion(parsed)

        results.append({
            "order_id": parsed["gloriafood_order_id"],
            "total": parsed["total_price_mxn"],
            "db_saved": db_ok,
            "ads_conversion_sent": ads_ok,
        })

        logger.info(
            "Webhook GloriaFood procesado: order=%s total=$%.2f db=%s ads=%s",
            parsed["gloriafood_order_id"],
            parsed["total_price_mxn"],
            db_ok, ads_ok,
        )

    return {"status": "ok", "orders_processed": len(results), "results": results}


@router.get("/webhook/gloriafood/stats")
async def gloriafood_stats():
    """Endpoint de diagnóstico: muestra pedidos recibidos."""
    try:
        from engine.memory import get_db_path
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_price_mxn), 0),
                   SUM(CASE WHEN conversion_sent = 1 THEN 1 ELSE 0 END)
            FROM gloriafood_orders
            WHERE received_at >= datetime('now', '-7 days')
        """)
        row = cursor.fetchone()
        conn.close()

        return {
            "status": "ok",
            "last_7_days": {
                "orders": row[0] if row else 0,
                "revenue_mxn": round(row[1], 2) if row else 0,
                "conversions_sent": row[2] if row else 0,
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/webhook/gloriafood/debug-fields")
async def gloriafood_debug_fields():
    """Muestra qué campos tienen datos en el último pedido (sin valores personales)."""
    try:
        from engine.memory import get_db_path
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                gloriafood_order_id IS NOT NULL AND gloriafood_order_id != '' as has_order_id,
                total_price_mxn,
                order_type,
                client_name IS NOT NULL AND client_name != '' as has_name,
                client_phone IS NOT NULL AND client_phone != '' as has_phone,
                client_email IS NOT NULL AND client_email != '' as has_email,
                items_count
            FROM gloriafood_orders
            ORDER BY id DESC LIMIT 3
        """)
        rows = cursor.fetchall()
        conn.close()
        return {"orders": [
            {
                "has_order_id": bool(r[0]),
                "total": r[1],
                "type": r[2],
                "has_name": bool(r[3]),
                "has_phone": bool(r[4]),
                "has_email": bool(r[5]),
                "items_count": r[6],
            } for r in rows
        ]}
    except Exception as e:
        return {"error": str(e)}
