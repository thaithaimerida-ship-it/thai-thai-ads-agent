import os
import json
from datetime import datetime
from typing import Optional

def _strip_code_fences(text: str) -> str:
    """Limpia bloques Markdown si el LLM los incluye."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()

def _safe_json_loads(text: str) -> Optional[dict]:
    """Parseo seguro de JSON."""
    try:
        cleaned_text = _strip_code_fences(text)
        parsed = json.loads(cleaned_text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except json.JSONDecodeError as e:
        print(f"Error al parsear JSON del LLM: {e}")
        return None

def _calculate_success_score(cpa: float, has_conversions: bool) -> int:
    """Calcula el score individual por campaña."""
    if not has_conversions:
        return 20 # Problemático
    if cpa <= 15:
        return 95 # Excelente
    elif cpa <= 30:
        return 80 # Bueno
    elif cpa <= 45:
        return 60 # Regular
    else:
        return 20 # Problemático

def _get_cpa_targets(campaign_name: str) -> dict:
    """Retorna CPA targets según tipo de campaña detectado por nombre."""
    name = campaign_name.lower()
    if "delivery" in name:
        return {"ideal": 25, "max": 45, "critical": 80}
    elif "reserva" in name:
        return {"ideal": 50, "max": 85, "critical": 120}
    else:  # local / brand / default
        return {"ideal": 35, "max": 60, "critical": 100}

def _calculate_success_score_v2(cpa: float, has_conversions: bool, campaign_name: str = "") -> int:
    """Score por campaña usando CPA targets reales por tipo."""
    if not has_conversions:
        return 20
    targets = _get_cpa_targets(campaign_name)
    if cpa <= targets["ideal"]:
        return 95
    elif cpa <= targets["max"]:
        return 75
    elif cpa <= targets["critical"]:
        return 45
    else:
        return 20

def _get_robust_spend(campaign_dict: dict) -> float:
    """
    ¡EL FIX MAESTRO OMNISCIENTE!
    Lee TODAS las llaves del diccionario. Si alguna se parece a 'cost' o 'spend',
    o si está en 'micros', extrae su valor. Se queda siempre con el valor MÁXIMO
    para ignorar los ceros (0.0) falsos que deje el normalizador por defecto.
    """
    best_spend = 0.0
    for k, v in campaign_dict.items():
        if v is None:
            continue
        k_lower = str(k).lower()
        try:
            val = float(v)
            if "micros" in k_lower:
                val = val / 1000000.0
            
            # Si la llave es de costo/gasto y el valor es mayor al que tenemos, lo guardamos
            if ("cost" in k_lower or "spend" in k_lower) and val > best_spend:
                best_spend = val
        except (ValueError, TypeError):
            continue
    
    return best_spend

def _fallback_analysis(data: dict) -> dict:
    """Análisis local de emergencia."""
    print("[INFO] Ejecutando análisis fallback local...")
    campaign_data = data.get("campaign_data", data.get("campaigns", []))
    
    total_spend = sum(_get_robust_spend(c) for c in campaign_data)
    total_clicks = sum(int(c.get("clicks", 0) or 0) for c in campaign_data)
    total_impressions = sum(int(c.get("impressions", 0) or 0) for c in campaign_data)
    total_conversions = sum(float(c.get("conversions", 0) or 0) for c in campaign_data)
    
    ctr = round((total_clicks / total_impressions) * 100, 2) if total_impressions > 0 else 0.0
    c_rate = round((total_conversions / total_clicks) * 100, 2) if total_clicks > 0 else 0.0
    cpa = round(total_spend / total_conversions, 2) if total_conversions > 0 else 0.0
    
    return {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "success_index": 70, 
            "success_label": "Análisis Local",
            "spend": round(total_spend, 2),
            "conversions": int(total_conversions),
            "cpa": cpa,
            "ctr": ctr,
            "conversion_rate": c_rate,
            "estimated_waste": 0.0
        },
        "executive_summary": {
            "headline": "Reporte de Emergencia",
            "bullets": ["Los servicios de IA no están disponibles.", "Mostrando datos crudos."],
            "recommended_focus_today": "Revisar conexión."
        },
        "campaigns": [], "market_opportunities": [], "waste": {}, "alerts": []
    }

def _call_haiku_analysis(data: dict) -> dict:
    """Claude Haiku 4.5 — fast fallback when Sonnet fails."""
    import anthropic
    from engine.prompt import THAI_THAI_ADS_MASTER_PROMPT

    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_message = (
        f"FECHA ACTUAL: {fecha_hoy}\n\n"
        f"TOTALES PRE-CALCULADOS (usa estos valores exactos en el objeto summary):\n"
        f"{json.dumps(data.get('totals', {}), indent=2)}\n\n"
        f"DATOS DE GOOGLE ADS:\n"
        f"{json.dumps(data.get('campaign_data', data.get('campaigns', [])), separators=(',', ':'))}\n\n"
        f"Responde SOLO con JSON válido. Sin markdown, sin explicaciones."
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=THAI_THAI_ADS_MASTER_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text
    result = _safe_json_loads(raw)

    if result and "summary" in result and "totals" in data:
        t = data["totals"]
        s = result["summary"]
        s["spend"] = t.get("calculated_total_spend", s.get("spend", 0))
        s["conversions"] = t.get("calculated_total_conversions", s.get("conversions", 0))
        s["cpa"] = t.get("calculated_global_cpa", s.get("cpa", 0))
        s["ctr"] = t.get("calculated_total_ctr", s.get("ctr", 0))
        s["conversion_rate"] = t.get("calculated_total_conversion_rate", s.get("conversion_rate", 0))
        s["success_index"] = t.get("calculated_success_index", s.get("success_index", 50))
        s["success_label"] = t.get("calculated_success_label", s.get("success_label", ""))

    return result

def _call_claude_analysis(data: dict) -> dict:
    """Claude Sonnet 4.6 — primary AI brain, replaces GPT-4o-mini."""
    import anthropic
    from engine.prompt import THAI_THAI_ADS_MASTER_PROMPT

    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_message = (
        f"FECHA ACTUAL: {fecha_hoy}\n\n"
        f"TOTALES PRE-CALCULADOS (usa estos valores exactos en el objeto summary):\n"
        f"{json.dumps(data.get('totals', {}), indent=2)}\n\n"
        f"DATOS DE GOOGLE ADS:\n"
        f"{json.dumps(data.get('campaign_data', data.get('campaigns', [])), separators=(',', ':'))}\n\n"
        f"DATOS GA4 (ultimos 7 dias):\n"
        f"{json.dumps(data.get('ga4_data', {}), separators=(',', ':'))}\n\n"
        f"DATOS NEGOCIO REAL (Google Sheets):\n"
        f"{json.dumps(data.get('sheets_data', {}), separators=(',', ':'))}\n\n"
        f"AUDITORIA LANDING PAGE:\n"
        f"{json.dumps(data.get('landing_audit', {}), separators=(',', ':'))}\n\n"
        f"MEMORIA HISTORICA (patrones aprendidos):\n"
        f"{json.dumps(data.get('memory_context', {}), separators=(',', ':'))}"
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=THAI_THAI_ADS_MASTER_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text
    result = _safe_json_loads(raw)

    # Inject pre-calculated totals to prevent hallucination
    if result and "summary" in result and "totals" in data:
        t = data["totals"]
        s = result["summary"]
        s["spend"] = t.get("calculated_total_spend", s.get("spend", 0))
        s["conversions"] = t.get("calculated_total_conversions", s.get("conversions", 0))
        s["cpa"] = t.get("calculated_global_cpa", s.get("cpa", 0))
        s["ctr"] = t.get("calculated_total_ctr", s.get("ctr", 0))
        s["conversion_rate"] = t.get("calculated_total_conversion_rate", s.get("conversion_rate", 0))
        s["success_index"] = t.get("calculated_success_index", s.get("success_index", 50))
        s["success_label"] = t.get("calculated_success_label", s.get("success_label", ""))

    return result


def analyze_campaign_data(data: dict) -> dict:
    """
    Main analysis entry point.
    Tries Claude Sonnet first, falls back to Haiku, then local fallback.
    Enriches data with GA4, Sheets, landing audit, and memory before calling LLM.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _fallback_analysis(data)

    # Enrich with GA4
    if "ga4_data" not in data:
        try:
            from engine.ga4_client import fetch_ga4_events_detailed
            data["ga4_data"] = fetch_ga4_events_detailed(days=7)
        except Exception as e:
            print(f"[WARN] GA4 fetch failed: {e}")
            data["ga4_data"] = {}

    # Enrich with Google Sheets
    if "sheets_data" not in data:
        try:
            from engine.sheets_client import fetch_sheets_data
            data["sheets_data"] = fetch_sheets_data(days=7)
        except Exception as e:
            print(f"[WARN] Sheets fetch failed: {e}")
            data["sheets_data"] = {}

    # Enrich with landing page audit
    if "landing_audit" not in data:
        try:
            from engine.landing_page_auditor import get_full_landing_audit
            data["landing_audit"] = get_full_landing_audit(data.get("ga4_data", {}))
        except Exception as e:
            print(f"[WARN] Landing audit failed: {e}")
            data["landing_audit"] = {}

    # Enrich with memory context
    if "memory_context" not in data:
        try:
            from engine.memory import get_memory_system
            mem = get_memory_system()
            data["memory_context"] = {
                "high_confidence_patterns": mem.get_high_confidence_patterns(min_confidence=0.7)[:5],
                "learnings": mem.get_learnings(min_confidence=0.7)[:5],
            }
        except Exception as e:
            print(f"[WARN] Memory fetch failed: {e}")
            data["memory_context"] = {}

    # Try Claude Sonnet first
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            result = _call_claude_analysis(data)
            if result:
                return result
        except Exception as e:
            print(f"[WARN] Claude Sonnet failed, trying Haiku: {e}")

    # Fallback to Haiku (fast + cheap)
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            result = _call_haiku_analysis(data)
            if result:
                return result
        except Exception as e:
            print(f"[ERROR] Haiku fallback failed: {e}")

    return _fallback_analysis(data)