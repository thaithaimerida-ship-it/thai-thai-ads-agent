"""
Webhook receptor de pedidos aceptados de GloriaFood.
Recibe POST JSON de la API Accepted Orders v2.
Doc: https://github.com/GlobalFood/integration_docs/blob/master/accepted_orders/README.md
"""
import logging
import os
import json
import re
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

    # Datos del cliente — GloriaFood v2 los manda como campos planos, no anidados
    client_first = str(order.get("client_first_name") or "")
    client_last = str(order.get("client_last_name") or "")
    client_name = f"{client_first} {client_last}".strip()
    client_phone = str(order.get("client_phone") or "")
    client_email = str(order.get("client_email") or "")

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
    Sube conversión offline a Google Ads vía Enhanced Conversions for Leads.
    Usa email/teléfono hasheado en vez de GCLID.
    """
    import hashlib
    import traceback
    import os

    order_id = parsed_order.get("gloriafood_order_id", "?")

    # Sin datos de cliente, no podemos hacer match
    if not parsed_order.get("client_email") and not parsed_order.get("client_phone"):
        logger.info("[CONV %s] Sin email/teléfono — no se puede enviar Enhanced Conversion", order_id)
        return None

    try:
        from engine.ads_client import get_ads_client
        customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")

        if not customer_id:
            logger.warning("[CONV %s] GOOGLE_ADS_TARGET_CUSTOMER_ID no configurado", order_id)
            return False

        client = get_ads_client()
        if not client:
            logger.warning("[CONV %s] No se pudo obtener Google Ads client", order_id)
            return False

        logger.info("[CONV %s] client ok — buscando conversion action...", order_id)

        # Buscar conversion action
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT conversion_action.resource_name
            FROM conversion_action
            WHERE conversion_action.name = 'Pedido GloriaFood Online'
            AND conversion_action.status = 'ENABLED'
        """
        results = list(ga_service.search(customer_id=customer_id, query=query))
        if not results:
            logger.warning("[CONV %s] Conversión 'Pedido GloriaFood Online' no encontrada", order_id)
            return False

        conversion_action_rn = results[0].conversion_action.resource_name
        logger.info("[CONV %s] conversion action encontrada: %s", order_id, conversion_action_rn)

        # Construir ClickConversion con user identifiers (sin GCLID)
        click_conversion = client.get_type("ClickConversion")
        click_conversion.conversion_action = conversion_action_rn
        click_conversion.conversion_value = parsed_order["total_price_mxn"]
        click_conversion.currency_code = "MXN"
        click_conversion.conversion_date_time = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S+00:00")
        click_conversion.order_id = parsed_order["gloriafood_order_id"]

        # User identifiers — hasheados con SHA-256
        if parsed_order.get("client_email"):
            email_normalized = parsed_order["client_email"].strip().lower()
            email_hash = hashlib.sha256(email_normalized.encode()).hexdigest()
            user_id = client.get_type("UserIdentifier")
            user_id.hashed_email = email_hash
            click_conversion.user_identifiers.append(user_id)
            logger.info("[CONV %s] email identifier agregado", order_id)

        if parsed_order.get("client_phone"):
            phone_clean = re.sub(r'[\s\-\(\)]', '', parsed_order["client_phone"].strip())
            if not phone_clean.startswith("+"):
                phone_clean = "+52" + phone_clean
            phone_hash = hashlib.sha256(phone_clean.encode()).hexdigest()
            user_id2 = client.get_type("UserIdentifier")
            user_id2.hashed_phone_number = phone_hash
            click_conversion.user_identifiers.append(user_id2)
            logger.info("[CONV %s] phone identifier agregado", order_id)

        # Subir
        upload_service = client.get_service("ConversionUploadService")
        request = client.get_type("UploadClickConversionsRequest")
        request.customer_id = customer_id
        request.conversions.append(click_conversion)
        request.partial_failure = True

        logger.info("[CONV %s] uploading $%.2f MXN...", order_id, parsed_order["total_price_mxn"])
        response = upload_service.upload_click_conversions(request=request)

        if response.partial_failure_error and response.partial_failure_error.code != 0:
            raw_error = response.partial_failure_error
            logger.error("[CONV %s] PARTIAL FAILURE: code=%s, message=%s, details_count=%s",
                         order_id, raw_error.code, raw_error.message, len(raw_error.details))
            for i, detail in enumerate(raw_error.details):
                logger.error("[CONV %s] PARTIAL FAILURE detail[%d]: %s", order_id, i, detail)
            return False

        logger.info("[CONV %s] Enhanced Conversion enviada: $%.2f MXN", order_id, parsed_order["total_price_mxn"])

        # Marcar en DB como enviada
        try:
            from engine.memory import get_db_path
            import sqlite3
            conn = sqlite3.connect(get_db_path())
            conn.execute(
                "UPDATE gloriafood_orders SET conversion_sent = 1 WHERE gloriafood_order_id = ?",
                (parsed_order["gloriafood_order_id"],)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return True

    except Exception as e:
        logger.error("[CONV %s] Error Enhanced Conversion: %s\n%s", order_id, e, traceback.format_exc())
        return False


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

        # 1b. Persistir DB en GCS
        if db_ok:
            try:
                from engine.db_sync import upload_to_gcs
                upload_to_gcs()
            except Exception as _sync_exc:
                logger.warning("upload_to_gcs falló: %s", _sync_exc)

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


@router.get("/webhook/gloriafood/retry")
async def gloriafood_retry_conversions():
    """Reintenta enviar conversiones pendientes (conversion_sent=0) — LIMIT 10."""
    try:
        from engine.memory import get_db_path
        import sqlite3
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT gloriafood_order_id, total_price_mxn, order_type, payment_method,
                   client_name, client_phone, client_email, items_json, accepted_at
            FROM gloriafood_orders
            WHERE conversion_sent = 0
            AND (client_email != '' OR client_phone != '')
            ORDER BY id DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if not rows:
        return {"status": "ok", "message": "No hay conversiones pendientes", "retried": 0}

    results = []
    for row in rows:
        parsed = {
            "gloriafood_order_id": row[0],
            "total_price_mxn": row[1],
            "order_type": row[2],
            "payment_method": row[3],
            "client_name": row[4],
            "client_phone": row[5],
            "client_email": row[6],
            "items": json.loads(row[7] or "[]"),
            "accepted_at": row[8],
        }
        ok = _send_google_ads_conversion(parsed)
        results.append({"order_id": row[0], "success": ok})
        logger.info("[RETRY] order=%s result=%s", row[0], ok)

    sent = sum(1 for r in results if r["success"])
    return {"status": "ok", "retried": len(results), "sent": sent, "results": results}


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


@router.get("/webhook/gloriafood/create-conversion-action")
async def create_offline_conversion_action():
    """Crea la conversion action tipo UPLOAD_CLICKS para recibir Enhanced Conversions."""
    try:
        import os
        from engine.ads_client import get_ads_client
        customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")
        client = get_ads_client()

        conversion_action_service = client.get_service("ConversionActionService")
        conversion_action_operation = client.get_type("ConversionActionOperation")
        conversion_action = conversion_action_operation.create

        conversion_action.name = "Pedido GloriaFood Online"
        conversion_action.category = client.enums.ConversionActionCategoryEnum.PURCHASE
        conversion_action.type_ = client.enums.ConversionActionTypeEnum.UPLOAD_CLICKS
        conversion_action.status = client.enums.ConversionActionStatusEnum.ENABLED
        conversion_action.value_settings.default_value = 450.0
        conversion_action.value_settings.default_currency_code = "MXN"
        conversion_action.value_settings.always_use_default_value = False

        response = conversion_action_service.mutate_conversion_actions(
            customer_id=customer_id,
            operations=[conversion_action_operation],
        )

        new_rn = response.results[0].resource_name
        return {"status": "ok", "resource_name": new_rn, "name": "Pedido GloriaFood Online"}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/webhook/gloriafood/conversion-tag-info")
async def get_conversion_tag_info():
    """Consulta tag_snippets de todas las conversion actions."""
    try:
        import os
        from engine.ads_client import get_ads_client
        customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT conversion_action.name, conversion_action.id,
                   conversion_action.tag_snippets, conversion_action.status,
                   conversion_action.type
            FROM conversion_action
            WHERE conversion_action.status != 'REMOVED'
        """
        results = list(ga_service.search(customer_id=customer_id, query=query))
        actions = []
        for row in results:
            ca = row.conversion_action
            snippets = []
            for s in ca.tag_snippets:
                snippets.append({"type": str(s.type_), "event_snippet": s.event_snippet[:200] if s.event_snippet else ""})
            actions.append({
                "name": ca.name,
                "id": ca.id,
                "type": str(ca.type_),
                "status": str(ca.status),
                "snippets": snippets
            })
        return {"status": "ok", "actions": actions}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/webhook/gloriafood/reactivate-conversion")
async def reactivate_conversion():
    """Reactiva Pedido GloriaFood Online cambiando status de REMOVED a ENABLED."""
    import os
    from engine.ads_client import get_ads_client
    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")
    client = get_ads_client()

    conversion_action_service = client.get_service("ConversionActionService")

    # Resource name conocido
    resource_name = f"customers/{customer_id}/conversionActions/7572944047"

    op = client.get_type("ConversionActionOperation")
    op.update.resource_name = resource_name
    op.update.status = client.enums.ConversionActionStatusEnum.ENABLED

    from google.protobuf import field_mask_pb2
    op.update_mask = field_mask_pb2.FieldMask(paths=["status"])

    try:
        response = conversion_action_service.mutate_conversion_actions(
            customer_id=customer_id,
            operations=[op],
        )
        return {"status": "ok", "result": str(response.results[0].resource_name)}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.get("/webhook/gloriafood/set-goal-biddable")
async def set_goal_biddable():
    """Lista todos los CustomerConversionGoals para diagnóstico."""
    import os
    from engine.ads_client import get_ads_client
    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "").replace("-", "")
    client = get_ads_client()

    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT customer_conversion_goal.category,
               customer_conversion_goal.origin,
               customer_conversion_goal.biddable,
               customer_conversion_goal.resource_name
        FROM customer_conversion_goal
    """
    results = list(ga_service.search(customer_id=customer_id, query=query))

    goals = []
    for row in results:
        g = row.customer_conversion_goal
        goals.append({
            "resource_name": g.resource_name,
            "category": g.category.name if hasattr(g.category, 'name') else str(g.category),
            "origin": g.origin.name if hasattr(g.origin, 'name') else str(g.origin),
            "biddable": g.biddable
        })

    return {"status": "ok", "total": len(goals), "goals": goals}
