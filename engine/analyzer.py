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

def _call_openai_analysis(data: dict) -> dict:
    """Versión Optimizada: Python como calculadora maestra inviolable."""
    
    campaigns = data.get("campaign_data", data.get("campaigns", []))
    
    # --- 🧮 CÁLCULOS MATEMÁTICOS DE PRE-AUDITORÍA ---
    total_spend = sum(_get_robust_spend(c) for c in campaigns)
    total_conversions = sum(float(c.get("conversions", 0) or 0) for c in campaigns)
    total_clicks = sum(int(c.get("clicks", 0) or 0) for c in campaigns)
    total_impressions = sum(int(c.get("impressions", 0) or 0) for c in campaigns)
    
    global_cpa = total_spend / total_conversions if total_conversions > 0 else 0
    global_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    global_cvrate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0

    success_index = 95 if global_cpa <= 15 else 80 if global_cpa <= 30 else 50 if global_cpa <= 45 else 20
    success_label = "Excelente" if success_index >= 90 else "Bueno" if success_index >= 80 else "Regular" if success_index >= 50 else "Problemático"

    data["totals"] = {
        "calculated_total_spend": round(total_spend, 2),
        "calculated_total_conversions": int(total_conversions),
        "calculated_global_cpa": round(global_cpa, 2),
        "calculated_total_ctr": round(global_ctr, 2),
        "calculated_total_conversion_rate": round(global_cvrate, 2),
        "calculated_success_index": success_index,
        "calculated_success_label": success_label
    }

    print("\n" + "🛡️ " * 20)
    print(f"AUDITORÍA LISTA: {len(campaigns)} campañas detectadas.")
    print(f"KPI Real: Spend ${data['totals']['calculated_total_spend']} | CPA ${data['totals']['calculated_global_cpa']}")
    print("🛡️ " * 20 + "\n")

    payload_minificado = json.dumps(data, separators=(',', ':'))
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_message = (
        f"FECHA ACTUAL: {fecha_hoy}\n\n"
        f"ORDEN DE AUDITORÍA: Usa los siguientes TOTALES CALCULADOS para el objeto 'summary'.\n"
        f"{json.dumps(data['totals'], indent=2)}\n\n"
        f"DATOS PARA ANÁLISIS ESTRATÉGICO:\n"
        f"{payload_minificado}"
    )

    try:
        from openai import OpenAI
        from engine.prompt import THAI_THAI_ADS_MASTER_PROMPT
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": THAI_THAI_ADS_MASTER_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1, 
            response_format={"type": "json_object"}
        )
        
        llm_result = _safe_json_loads(response.choices[0].message.content)
        
        # 🟢 HACK DEFINITIVO: Python inyecta sus números exactos
        if llm_result and "summary" in llm_result:
            llm_result["summary"]["spend"] = data["totals"]["calculated_total_spend"]
            llm_result["summary"]["conversions"] = data["totals"]["calculated_total_conversions"]
            llm_result["summary"]["cpa"] = data["totals"]["calculated_global_cpa"]
            llm_result["summary"]["ctr"] = data["totals"]["calculated_total_ctr"]
            llm_result["summary"]["conversion_rate"] = data["totals"]["calculated_total_conversion_rate"]
            llm_result["summary"]["success_index"] = data["totals"]["calculated_success_index"]
            llm_result["summary"]["success_label"] = data["totals"]["calculated_success_label"]
            
        return llm_result
        
    except Exception as e:
        print(f"❌ Error al consultar a OpenAI: {e}")
        raise e

def analyze_campaign_data(data: dict) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback_analysis(data)

    try:
        llm_result = _call_openai_analysis(data)
        if llm_result:
            if "analysis" in llm_result:
                return llm_result["analysis"]
            return llm_result
    except Exception as e:
        print(f"❌ Error crítico en flujo de análisis: {str(e)}")

    return _fallback_analysis(data)