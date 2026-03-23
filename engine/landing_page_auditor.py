"""
Landing Page Auditor — Thai Thai
Analyzes landing page code structure and correlates with GA4 metrics.
Landing page project path: C:/Users/usuario/Downloads/thai-thai web
"""
import os
from typing import Dict

LANDING_PAGE_PATH = os.getenv(
    "LANDING_PAGE_PATH",
    "C:/Users/usuario/Downloads/thai-thai web"
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


def audit_landing_page_code() -> Dict:
    """
    Analyzes the thai-thai web project code for structural issues.
    Returns a dict with issues found and overall score.
    """
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
    }
