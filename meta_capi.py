"""
Meta Conversions API (CAPI) module — agnostic to delivery platform.

Receives a standardized OrderConfirmed dict and dispatches a Purchase event
to Meta. Designed to be called from any webhook handler (GloriaFood, Resto Lab, etc.)
without coupling.

Reference: https://developers.facebook.com/docs/marketing-api/conversions-api
"""

import hashlib
import os
import time
import uuid
import logging
from typing import TypedDict, Optional
import requests

logger = logging.getLogger(__name__)

META_PIXEL_ID = os.environ['META_PIXEL_ID']
META_CAPI_ACCESS_TOKEN = os.environ['META_CAPI_ACCESS_TOKEN']
META_API_VERSION = os.environ.get('META_API_VERSION', 'v22.0')
META_TEST_EVENT_CODE = os.environ.get('META_TEST_EVENT_CODE', '').strip() or None

CAPI_ENDPOINT = f"https://graph.facebook.com/{META_API_VERSION}/{META_PIXEL_ID}/events"


class OrderConfirmed(TypedDict, total=False):
    """Standard input from any delivery platform webhook."""
    order_id: str            # required - unique per order, used for dedup
    value: float             # required - order total (without delivery fee)
    currency: str            # required - ISO 4217 (e.g., "MXN")
    email: Optional[str]     # raw, will be hashed
    phone: Optional[str]     # raw with or without country code, will be normalized + hashed
    first_name: Optional[str]
    last_name: Optional[str]
    city: Optional[str]
    country: Optional[str]   # ISO 3166-1 alpha-2 (e.g., "MX")
    client_ip: Optional[str]
    client_user_agent: Optional[str]
    fbp: Optional[str]       # Meta browser cookie (_fbp), if available
    fbc: Optional[str]       # Meta click cookie (_fbc), if available
    event_source_url: Optional[str]


def _sha256_norm(value: str) -> str:
    """Normalize and SHA256 hash per Meta spec: lowercase, strip whitespace."""
    return hashlib.sha256(value.strip().lower().encode('utf-8')).hexdigest()


def _normalize_phone(phone: str) -> str:
    """Strip everything that isn't a digit. Meta expects E.164-style without '+'."""
    return ''.join(c for c in phone if c.isdigit())


def _build_user_data(order: OrderConfirmed) -> dict:
    """Build user_data block with all available match keys, properly hashed."""
    ud = {}
    if order.get('email'):
        ud['em'] = [_sha256_norm(order['email'])]
    if order.get('phone'):
        ud['ph'] = [_sha256_norm(_normalize_phone(order['phone']))]
    if order.get('first_name'):
        ud['fn'] = [_sha256_norm(order['first_name'])]
    if order.get('last_name'):
        ud['ln'] = [_sha256_norm(order['last_name'])]
    if order.get('city'):
        ud['ct'] = [_sha256_norm(order['city'])]
    if order.get('country'):
        ud['country'] = [_sha256_norm(order['country'])]
    # IP and User-Agent are NOT hashed
    if order.get('client_ip'):
        ud['client_ip_address'] = order['client_ip']
    if order.get('client_user_agent'):
        ud['client_user_agent'] = order['client_user_agent']
    if order.get('fbp'):
        ud['fbp'] = order['fbp']
    if order.get('fbc'):
        ud['fbc'] = order['fbc']
    return ud


def send_purchase(order: OrderConfirmed) -> dict:
    """
    Dispatch a Purchase event to Meta CAPI.

    Returns Meta's response dict. Raises on HTTP errors.

    Dedup with browser pixel:
    - event_id = order['order_id'] — Meta uses this to dedup with the browser
      Pixel event when the user also fires Purchase from the front-end.
    """
    if not order.get('order_id'):
        raise ValueError("order_id is required for dedup")
    if order.get('value') is None:
        raise ValueError("value is required")
    if not order.get('currency'):
        raise ValueError("currency is required")

    event = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "event_id": order['order_id'],  # dedup key with browser pixel
        "action_source": "website",
        "user_data": _build_user_data(order),
        "custom_data": {
            "currency": order['currency'].upper(),
            "value": float(order['value']),
        },
    }
    if order.get('event_source_url'):
        event["event_source_url"] = order['event_source_url']

    payload = {"data": [event]}
    if META_TEST_EVENT_CODE:
        payload["test_event_code"] = META_TEST_EVENT_CODE

    params = {"access_token": META_CAPI_ACCESS_TOKEN}

    logger.info(
        "meta_capi.send_purchase",
        extra={
            "order_id": order['order_id'],
            "value": order['value'],
            "currency": order['currency'],
            "match_keys": list(event["user_data"].keys()),
            "test_mode": bool(META_TEST_EVENT_CODE),
        }
    )

    response = requests.post(CAPI_ENDPOINT, params=params, json=payload, timeout=10)
    response.raise_for_status()
    result = response.json()

    logger.info(
        "meta_capi.response",
        extra={
            "order_id": order['order_id'],
            "events_received": result.get('events_received'),
            "fbtrace_id": result.get('fbtrace_id'),
        }
    )
    return result


def send_synthetic_test() -> dict:
    """Send a synthetic Purchase for testing. Requires META_TEST_EVENT_CODE set."""
    if not META_TEST_EVENT_CODE:
        raise RuntimeError(
            "META_TEST_EVENT_CODE not set. Generate one in Events Manager → "
            "Probar eventos and set it as env var before running synthetic tests."
        )

    fake_order: OrderConfirmed = {
        "order_id": f"synthetic-{uuid.uuid4()}",
        "value": 350.00,
        "currency": "MXN",
        "email": "test+capi@thaithaimerida.com",
        "phone": "529991234567",
        "first_name": "Test",
        "last_name": "Synthetic",
        "city": "Mérida",
        "country": "MX",
        "event_source_url": "https://thaithaimerida.com/",
    }
    return send_purchase(fake_order)
