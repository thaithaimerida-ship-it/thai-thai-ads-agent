"""
Thai Thai Ads Agent — Landing Checker (Fase 3B)

Verifica que la landing principal y el flujo de conversión crítico estén operativos.
Solo checks basados en requests HTTP — sin Playwright, sin DOM inspection.

Por qué no S3_CTA_MISSING:
    El sitio es una SPA Vite+React. Los CTAs ("Pedir en Línea", "Reservar Mesa")
    son <button onClick=...> inyectados por JavaScript en el cliente. El HTML
    estático servido por Netlify contiene <div id="root"></div> — bs4 vería
    un DOM vacío, generando falsos positivos garantizados en cada ciclo.

Señales implementadas:
    S1_DOWN        — landing retorna status != OK en ≥2 de LANDING_RETRY_COUNT intentos
    S2_SLOW        — tiempo de respuesta promedio supera umbral de warning o critical
    S4_LINK_BROKEN — enlace de Gloria Food no accesible (HEAD + fallback GET)

Función pública principal:
    check_landing_health(...) -> dict
"""

import time
import logging

logger = logging.getLogger(__name__)


def _check_conversion_url(url: str, timeout: float) -> dict:
    """
    Verifica la URL de conversión con HEAD primero; fallback a GET si HEAD
    falla o retorna un status dudoso (p. ej. 405 Method Not Allowed).

    Esto reduce falsos positivos: algunos servidores (incluyendo Gloria Food)
    rechazan HEAD pero responden bien a GET.

    Args:
        url     : URL a verificar
        timeout : segundos de timeout por intento

    Returns:
        dict con status_code, method_used, ok, error
    """
    import requests

    # Intento 1: HEAD
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code in (200, 301, 302, 303):
            return {
                "status_code": resp.status_code,
                "method_used": "HEAD",
                "ok": True,
                "error": None,
            }
        # HEAD retornó algo no definitivamente OK (404, 405, 500…) — probar GET
        logger.debug(
            "landing_checker: HEAD retornó %d para %s — intentando GET",
            resp.status_code, url,
        )
    except Exception as head_exc:
        logger.debug(
            "landing_checker: HEAD falló para %s (%s) — intentando GET",
            url, head_exc,
        )

    # Intento 2: GET (stream=True para no descargar el body completo)
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True, stream=True
        )
        resp.close()
        ok = resp.status_code in (200, 301, 302, 303)
        return {
            "status_code": resp.status_code,
            "method_used": "GET_fallback",
            "ok": ok,
            "error": None,
        }
    except Exception as get_exc:
        return {
            "status_code": None,
            "method_used": "GET_fallback",
            "ok": False,
            "error": str(get_exc)[:200],
        }


def check_landing_health(
    landing_url: str,
    conversion_url: str,
    timeout_warn_s: float,
    timeout_critical_s: float,
    retry_count: int,
    retry_delay_s: float,
    ok_status_codes: list,
    _sleep_fn=None,
    _requests_get_fn=None,
) -> dict:
    """
    Ejecuta todos los checks de salud de la landing (Fase 3B, MVP).

    Señales detectadas:
        S1_DOWN        — landing sin respuesta o status incorrecto (≥2 de retry_count)
        S2_SLOW        — respuesta lenta según timeout_warn_s / timeout_critical_s
        S4_LINK_BROKEN — enlace de Gloria Food no accesible (HEAD + fallback GET)

    Args:
        landing_url        : URL de la landing (https://thaithaimerida.com)
        conversion_url     : URL del flujo de pedidos (Gloria Food)
        timeout_warn_s     : segundos para disparar S2 como warning
        timeout_critical_s : segundos para elevar S2 a critical
        retry_count        : número de intentos para S1 (recomendado: 3)
        retry_delay_s      : segundos entre reintentos
        ok_status_codes    : lista de status HTTP considerados OK
        _sleep_fn          : función de sleep — injectable para tests (default: time.sleep)
        _requests_get_fn   : función requests.get — injectable para tests

    Returns:
        dict con:
            signals   — lista de señales detectadas ([], ['S1_DOWN'], ['S4_LINK_BROKEN'], …)
            severity  — 'critical' | 'warning' | 'none'
            reason    — descripción de la falla (para SQLite y correo)
            details   — datos crudos de cada check (para evidence_json)
    """
    import requests as _req_module

    sleep_fn = _sleep_fn or time.sleep
    get_fn = _requests_get_fn or _req_module.get

    signals = []
    details = {}

    # ── S1 / S2: Verificar landing con reintentos ─────────────────────────────
    attempts = []
    response_times_ok = []

    for attempt_num in range(retry_count):
        if attempt_num > 0:
            sleep_fn(retry_delay_s)

        elapsed = None
        try:
            t0 = time.monotonic()
            resp = get_fn(
                landing_url,
                timeout=min(timeout_critical_s + 5, 30),
                allow_redirects=True,
            )
            elapsed = round(time.monotonic() - t0, 3)
            ok = resp.status_code in ok_status_codes
            attempt_record = {
                "attempt": attempt_num + 1,
                "status_code": resp.status_code,
                "ok": ok,
                "elapsed_s": elapsed,
            }
            if ok:
                response_times_ok.append(elapsed)

        except Exception as exc:
            error_msg = str(exc)
            is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
            elapsed = round(time.monotonic() - t0, 3) if elapsed is None else elapsed
            attempt_record = {
                "attempt": attempt_num + 1,
                "status_code": None,
                "ok": False,
                "elapsed_s": elapsed,
                "error": "timeout" if is_timeout else error_msg[:120],
            }

        attempts.append(attempt_record)

    details["landing_attempts"] = attempts
    failed_count = sum(1 for a in attempts if not a["ok"])

    # S1: falla confirmada si ≥2 intentos fallaron
    if failed_count >= 2:
        signals.append("S1_DOWN")
        last_status = next(
            (a.get("status_code") for a in reversed(attempts) if a.get("status_code")),
            None,
        )
        details["s1"] = {
            "failed_attempts": failed_count,
            "total_attempts": retry_count,
            "last_status_code": last_status,
        }

    # S2: usar promedio de intentos exitosos
    if response_times_ok:
        avg_elapsed = sum(response_times_ok) / len(response_times_ok)
        details["response_time_avg_s"] = round(avg_elapsed, 3)

        if avg_elapsed > timeout_critical_s:
            signals.append("S2_SLOW")
            details["s2"] = {
                "response_time_s": round(avg_elapsed, 3),
                "threshold_s": timeout_critical_s,
                "level": "critical",
            }
        elif avg_elapsed > timeout_warn_s:
            signals.append("S2_SLOW")
            details["s2"] = {
                "response_time_s": round(avg_elapsed, 3),
                "threshold_s": timeout_warn_s,
                "level": "warning",
            }

    # ── S4: Verificar enlace de conversión (Gloria Food) ─────────────────────
    try:
        s4_result = _check_conversion_url(conversion_url, timeout=10.0)
        details["conversion_check"] = s4_result
        if not s4_result["ok"]:
            signals.append("S4_LINK_BROKEN")
            details["s4"] = {
                "url": conversion_url,
                "status_code": s4_result["status_code"],
                "method_used": s4_result["method_used"],
                "error": s4_result.get("error"),
            }
    except Exception as exc:
        signals.append("S4_LINK_BROKEN")
        details["s4"] = {
            "url": conversion_url,
            "status_code": None,
            "error": str(exc)[:120],
        }

    # ── Clasificar severidad y construir reason ───────────────────────────────
    if not signals:
        return {
            "signals": [],
            "severity": "none",
            "reason": "Landing y flujo de conversión operativos",
            "details": details,
        }

    # S1 o S4 → critical (impacto directo en conversiones)
    # S2 solo → warning o critical según nivel de demora
    has_s1_or_s4 = "S1_DOWN" in signals or "S4_LINK_BROKEN" in signals
    s2_level = details.get("s2", {}).get("level") if "S2_SLOW" in signals else None

    if has_s1_or_s4 or s2_level == "critical":
        severity = "critical"
    else:
        severity = "warning"

    reason_parts = []
    if "S1_DOWN" in signals:
        d = details["s1"]
        reason_parts.append(
            f"S1_DOWN: landing sin respuesta válida en "
            f"{d['failed_attempts']}/{d['total_attempts']} intentos "
            f"(último status: {d['last_status_code'] or 'sin respuesta'})"
        )
    if "S2_SLOW" in signals:
        d = details["s2"]
        reason_parts.append(
            f"S2_SLOW: tiempo de respuesta {d['response_time_s']}s "
            f"(umbral {d['level']}: {d['threshold_s']}s)"
        )
    if "S4_LINK_BROKEN" in signals:
        d = details["s4"]
        reason_parts.append(
            f"S4_LINK_BROKEN: enlace de pedidos no accesible "
            f"(status: {d['status_code'] or 'sin respuesta'}, "
            f"método: {d.get('method_used', 'HEAD+GET')})"
        )

    return {
        "signals": signals,
        "severity": severity,
        "reason": " / ".join(reason_parts),
        "details": details,
    }
