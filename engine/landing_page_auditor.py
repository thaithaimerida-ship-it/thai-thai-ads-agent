"""
Landing Page Auditor — Thai Thai
Analyzes landing page code structure and correlates with GA4 metrics.
In production (Cloud Run): fetches the live URL and audits HTML.
Locally: audits source code files.
"""
import os
from typing import Dict

LANDING_PAGE_PATH = os.getenv(
    "LANDING_PAGE_PATH",
    "C:/Users/usuario/Downloads/thai-thai web"
)
LANDING_PAGE_URL = os.getenv(
    "LANDING_PAGE_URL",
    "https://www.thaithaimerida.com"
)


def compute_friction_score(ctr_pct: float, conversion_rate_pct: float) -> Dict:
    """
    Computes landing page friction based on CTR vs conversion rate gap.
    Thresholds:
    - conversion_rate >= 3%: good regardless of CTR
    - gap <= 1%: good (score 80-100)
    - gap 1-1.5%: warning (score 50-79)
    - gap > 1.5%: critical (score 0-49)
    """
    gap = max(0.0, ctr_pct - conversion_rate_pct)

    if conversion_rate_pct >= 3.0:
        status = "good"
        score = 100
        action = None
    elif gap <= 1.0:
        status = "good"
        score = max(80, int(100 - gap * 20))
        action = None
    elif gap <= 1.5:
        status = "warning"
        score = max(50, int(79 - (gap - 1.0) * 58))
        action = "Auditar posicion del CTA y velocidad de carga en movil"
    else:
        status = "critical"
        score = max(0, int(49 - (gap - 1.5) * 30))
        action = "Landing page audit completo: CTA, formulario, tiempo de carga"

    return {
        "status": status,
        "score": score,
        "ctr_pct": ctr_pct,
        "conversion_rate_pct": conversion_rate_pct,
        "gap": round(gap, 2),
        "recommended_action": action,
    }


def _audit_live_url(url: str) -> Dict:
    """
    Fetches the live landing page and audits its HTML structure.
    Checks: mobile meta, CTA buttons, form, GA4/analytics, page speed signals.
    """
    import urllib.request
    import urllib.error

    issues = []
    score = 100

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ThaiThaiAudit/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            status_code = resp.status
    except urllib.error.HTTPError as e:
        return {
            "score": 0, "status": "critical",
            "issues": [f"La landing page devolvio HTTP {e.code} — pagina no accesible"],
            "issues_count": 1, "url": url, "mode": "live_url_audit",
        }
    except Exception as e:
        return {
            "score": 50, "status": "warning",
            "issues": [f"No se pudo conectar a {url}: {e}"],
            "issues_count": 1, "url": url, "mode": "live_url_audit_failed",
        }

    html_lower = html.lower()

    # Detect React/Vue/Angular SPA — content is rendered by JavaScript, not in HTML
    is_spa = (
        'id="root"' in html_lower or "id='root'" in html_lower or
        'id="app"' in html_lower or "id='app'" in html_lower or
        "/assets/index" in html_lower or "react" in html_lower
    )

    # Check 1: Mobile viewport meta tag (verifiable in static HTML)
    if 'name="viewport"' not in html_lower and "name='viewport'" not in html_lower:
        issues.append("Sin meta viewport — el sitio puede verse mal en movil")
        score -= 20

    # Check 2: Title (verifiable in static HTML)
    if "<title" not in html_lower:
        issues.append("Sin etiqueta <title> — mal para SEO y Quality Score del anuncio")
        score -= 10

    # Check 3: Meta description (verifiable in static HTML)
    if 'name="description"' not in html_lower and "name='description'" not in html_lower:
        issues.append("Sin meta description — puede afectar Quality Score del anuncio")
        score -= 10

    # Check 4: Analytics / GA4 tracking (verifiable in static HTML)
    has_ga4 = "gtag" in html_lower or "google-analytics" in html_lower or "googletagmanager" in html_lower
    if not has_ga4:
        issues.append("No se detecto Google Analytics / GA4 — conversiones no rastreadas")
        score -= 25

    # Check 5: Google Ads conversion tracking
    has_ads_tracking = "aw-" in html_lower or "google_conversion" in html_lower or "googleadservices" in html_lower
    if not has_ads_tracking:
        issues.append("No se detecto pixel de Google Ads — conversiones de anuncios no rastreadas")
        score -= 15

    # Check 6: HTTPS
    if not url.startswith("https://"):
        issues.append("URL no usa HTTPS — reduce conversiones y Quality Score")
        score -= 10

    # Check 7: Form / CTA — ONLY check in static HTML if NOT a SPA
    # React/Vue/Angular apps render these via JavaScript, not in the HTML source
    if not is_spa:
        cta_keywords = ["reserva", "reservacion", "pedir", "order", "book", "mesa"]
        if not any(kw in html_lower for kw in cta_keywords):
            issues.append("No se detecto CTA de reserva/pedido en el HTML")
            score -= 15
        if "<form" not in html_lower:
            issues.append("Sin formulario <form> en el HTML")
            score -= 15

    score = max(0, score)
    status = "good" if score >= 80 else "warning" if score >= 50 else "critical"

    notes = []
    if is_spa:
        notes.append("Sitio React/SPA: formularios y CTAs se renderizan via JavaScript (correcto)")

    return {
        "score": score,
        "status": status,
        "issues": issues,
        "notes": notes,
        "issues_count": len(issues),
        "url": url,
        "http_status": status_code,
        "is_spa": is_spa,
        "mode": "live_url_audit",
    }


def audit_landing_page_code() -> Dict:
    """
    Analyzes the thai-thai web project code for structural issues.
    Returns a dict with issues found and overall score.
    Skips code audit gracefully when running in Cloud Run (path not present).
    """
    # In Cloud Run the local source is not mounted — audit the live URL instead
    if not os.path.isdir(LANDING_PAGE_PATH):
        return _audit_live_url(LANDING_PAGE_URL)

    issues = []
    score = 100

    # Check 1: ReservationModal exists and has form + tracking
    modal_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "ReservationModal.jsx")
    if os.path.exists(modal_path):
        with open(modal_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "handleSubmit" not in content:
            issues.append("ReservationModal no tiene manejador de envio")
            score -= 20
        if "trackConversion" not in content:
            issues.append("ReservationModal no llama trackConversion — conversiones no rastreadas")
            score -= 15
        if "localhost" in content:
            issues.append("BACKEND_URL apunta a localhost — las reservas no funcionan en produccion")
            score -= 25
    else:
        issues.append("ReservationModal.jsx no encontrado")
        score -= 30

    # Check 2: Analytics utility exists
    analytics_path = os.path.join(LANDING_PAGE_PATH, "src", "utils", "analytics.js")
    if not os.path.exists(analytics_path):
        issues.append("utils/analytics.js no encontrado — tracking puede estar roto")
        score -= 20

    # Check 3: HeroSection has CTA
    hero_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "HeroSection.jsx")
    if os.path.exists(hero_path):
        with open(hero_path, "r", encoding="utf-8") as f:
            hero_content = f.read()
        if "reserva" not in hero_content.lower() and "pedir" not in hero_content.lower():
            issues.append("HeroSection posiblemente no tiene CTA de reserva/pedido visible")
            score -= 10

    # Check 4: Mobile sticky bar
    sticky_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "MobileStickyBar.jsx")
    if not os.path.exists(sticky_path):
        issues.append("No existe barra sticky para movil — CTA dificil de encontrar en celular")
        score -= 15

    score = max(0, score)
    status = "good" if score >= 80 else "warning" if score >= 50 else "critical"

    return {
        "score": score,
        "status": status,
        "issues": issues,
        "issues_count": len(issues),
        "landing_path": LANDING_PAGE_PATH,
        "mode": "local_code_audit",
    }


def get_full_landing_audit(ga4_data: Dict = None) -> Dict:
    """
    Full audit: code analysis + GA4 correlation.
    ga4_data: output of fetch_ga4_events_detailed()
    """
    code_audit = audit_landing_page_code()

    friction = {}
    if ga4_data and "conversion_funnel" in ga4_data:
        funnel = ga4_data["conversion_funnel"]
        page_views = funnel.get("page_view", 0)
        reservas = funnel.get("reserva_completada", 0)
        clicks_reservar = funnel.get("click_reservar", 0)

        if clicks_reservar > 0 and page_views > 0:
            implied_ctr = round((clicks_reservar / page_views) * 100, 2)
            conv_rate = round((reservas / clicks_reservar) * 100, 2) if clicks_reservar else 0
            friction = compute_friction_score(implied_ctr, conv_rate)
        else:
            friction = {"status": "sin_datos", "score": 50, "gap": 0}

    return {
        "code_audit": code_audit,
        "friction": friction,
        "overall_score": code_audit["score"],
        "top_issue": code_audit["issues"][0] if code_audit["issues"] else None,
        "audited_url": code_audit.get("url", LANDING_PAGE_URL),
        "audit_mode": code_audit.get("mode", "unknown"),
    }
