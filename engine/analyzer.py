import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .prompt import THAI_THAI_ADS_MASTER_PROMPT


def _strip_code_fences(text: str) -> str:
    """
    Removes Markdown code fences if the model returns them by mistake.
    """
    if not text:
        return text

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    return text.strip()


def _safe_json_loads(text: str) -> Optional[dict]:
    """
    Safely parse JSON text into a dict. Returns None if parsing fails.
    """
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except Exception:
        return None


def _fallback_analysis(data: dict) -> dict:
    """
    Local fallback analyzer that returns the official Thai Thai Ads Agent schema.
    Used when no LLM API key is available or when the LLM response fails.
    """

    account_name = data.get("account_name", "")
    date_range = data.get("date_range", {})
    historical_data_available = data.get("historical_data_available", False)

    campaign_data = data.get("campaign_data", [])
    keyword_data = data.get("keyword_data", [])
    search_term_data = data.get("search_term_data", [])

    total_spend = sum(c.get("spend", 0) or 0 for c in campaign_data)
    total_clicks = sum(c.get("clicks", 0) or 0 for c in campaign_data)
    total_impressions = sum(c.get("impressions", 0) or 0 for c in campaign_data)
    total_conversions = sum(c.get("conversions", 0) or 0 for c in campaign_data)

    ctr = round((total_clicks / total_impressions) * 100, 2) if total_impressions > 0 else 0
    conversion_rate = round((total_conversions / total_clicks) * 100, 2) if total_clicks > 0 else 0
    cpa = round(total_spend / total_conversions, 2) if total_conversions > 0 else None

    estimated_waste = 0
    for c in campaign_data:
        spend = c.get("spend", 0) or 0
        conversions = c.get("conversions", 0) or 0
        if spend > 0 and conversions == 0:
            estimated_waste += spend

    waste_sources: List[Dict[str, Any]] = []

    for st in search_term_data:
        conversions = st.get("conversions", 0) or 0
        cost = st.get("cost", 0) or 0
        if cost > 0 and conversions == 0:
            waste_sources.append({
                "type": "search_term",
                "name": st.get("search_term", ""),
                "cost": cost,
                "reason": "Término con gasto sin conversiones."
            })

    for kw in keyword_data:
        conversions = kw.get("conversions", 0) or 0
        cost = kw.get("cost", 0) or 0
        if cost > 0 and conversions == 0:
            waste_sources.append({
                "type": "keyword",
                "name": kw.get("keyword_text", ""),
                "cost": cost,
                "reason": "Keyword con gasto sin conversiones."
            })

    waste_sources = sorted(waste_sources, key=lambda x: x["cost"], reverse=True)[:5]

    campaigns = []
    for c in campaign_data:
        spend = c.get("spend", 0) or 0
        clicks = c.get("clicks", 0) or 0
        impressions = c.get("impressions", 0) or 0
        conversions = c.get("conversions", 0) or 0

        campaign_cpa = round(spend / conversions, 2) if conversions > 0 else None

        if spend > 1000 and conversions == 0:
            success_score = 20
            success_label = "Problemático"
            issue = "Gasto alto sin conversiones."
            action = "Revisar de inmediato términos de búsqueda, concordancias y presupuesto."
            confidence = {
                "level": "Alta",
                "reason": "Hay suficiente volumen para identificar bajo desempeño."
            }
        elif conversions > 0 and campaign_cpa is not None and campaign_cpa < 100:
            success_score = 90
            success_label = "Excelente"
            issue = "Sin problema crítico detectado."
            action = "Mantener activa y vigilar presupuesto."
            confidence = {
                "level": "Media",
                "reason": "La campaña muestra eficiencia positiva, aunque aún puede requerir más histórico."
            }
        elif conversions > 0:
            success_score = 75
            success_label = "Bueno"
            issue = "Desempeño aceptable con margen de mejora."
            action = "Optimizar sin afectar el volumen actual."
            confidence = {
                "level": "Media",
                "reason": "Hay señales suficientes para un diagnóstico útil."
            }
        else:
            success_score = 50
            success_label = "Regular"
            issue = "Datos insuficientes o bajo volumen."
            action = "Seguir observando antes de tomar acciones fuertes."
            confidence = {
                "level": "Baja",
                "reason": "No hay suficiente evidencia para una conclusión fuerte."
            }

        campaigns.append({
            "campaign_id": str(c.get("campaign_id", "")),
            "campaign_name": c.get("campaign_name", ""),
            "diagnosis_confidence": confidence,
            "status": c.get("status", ""),
            "spend": spend,
            "conversions": conversions,
            "cpa": campaign_cpa,
            "success_score": success_score,
            "success_label": success_label,
            "primary_issue": issue,
            "recommended_action": action
        })

    if total_spend > 0 and total_conversions == 0:
        success_index = 20
        success_label = "Problemático"
    elif cpa is not None and cpa < 100:
        success_index = 90
        success_label = "Excelente"
    elif cpa is not None and cpa < 250:
        success_index = 75
        success_label = "Bueno"
    elif total_spend > 0:
        success_index = 35
        success_label = "Problemático"
    else:
        success_index = 0
        success_label = "Datos insuficientes"

    alerts = []
    if estimated_waste > 0:
        alerts.append({
            "severity": "Alta",
            "type": "high_spend_no_conversions",
            "title": "Se detectó gasto sin conversiones",
            "message": "Hay campañas, keywords o términos con gasto y sin resultados.",
            "affected_entity": "Cuenta"
        })

    if not historical_data_available:
        trend_direction = "unknown"
        delta_points = 0
        vs_label = "sin_datos_previos"
        trends = {
            "success_index": [],
            "cpa": [],
            "conversions": [],
            "spend": []
        }
    else:
        trend_direction = "flat"
        delta_points = 0
        vs_label = "periodo_anterior"
        trends = {
            "success_index": [],
            "cpa": [],
            "conversions": [],
            "spend": []
        }

    recommendations = []
    if estimated_waste > 0:
        recommendations.append({
            "priority": "Alta",
            "problem": "Existe desperdicio relevante en la cuenta.",
            "action": "Agregar negativas y revisar concordancias en campañas con gasto sin conversiones.",
            "evidence": f"Se estiman {estimated_waste} MXN de gasto desperdiciado.",
            "impact": "Reducir desperdicio y mejorar eficiencia."
        })

    if campaigns:
        bad_campaigns = [c for c in campaigns if c["success_label"] == "Problemático"]
        if bad_campaigns:
            recommendations.append({
                "priority": "Alta",
                "problem": "Hay campañas con desempeño problemático.",
                "action": "Contener el gasto y revisar segmentación antes de seguir invirtiendo.",
                "evidence": f"Se detectaron {len(bad_campaigns)} campañas con score problemático.",
                "impact": "Proteger presupuesto y evitar más pérdida."
            })

    if any(c["success_label"] == "Excelente" for c in campaigns):
        recommendations.append({
            "priority": "Media",
            "problem": "Hay campañas eficientes que conviene proteger.",
            "action": "Mantener presupuesto suficiente en campañas con buen CPA y conversiones.",
            "evidence": "Se detectó al menos una campaña con desempeño excelente.",
            "impact": "Sostener resultados positivos y capturar demanda de alta intención."
        })

    result = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "agent_name": "Thai Thai Ads Agent",
        "account_name": account_name,
        "diagnosis_confidence": {
            "level": "Media" if total_spend > 0 else "Baja",
            "reason": "El análisis usa reglas locales temporales mientras se integra el modelo final."
        },
        "date_range": {
            "label": date_range.get("label", ""),
            "start": date_range.get("start", ""),
            "end": date_range.get("end", "")
        },
        "summary": {
            "success_index": success_index,
            "success_label": success_label,
            "success_trend": {
                "direction": trend_direction,
                "delta_points": delta_points,
                "vs_label": vs_label
            },
            "spend": total_spend,
            "conversions": total_conversions,
            "cpa": cpa,
            "ctr": ctr,
            "conversion_rate": conversion_rate,
            "estimated_waste": estimated_waste,
            "alerts_count": len(alerts),
            "recommended_actions_count": len(recommendations)
        },
        "executive_summary": {
            "headline": "La cuenta fue analizada con la lógica base del agente.",
            "bullets": [
                "Se calcularon métricas generales de gasto, conversiones y eficiencia.",
                "Se detectó desperdicio cuando hubo gasto sin conversiones.",
                "Las recomendaciones actuales son temporales mientras se conecta el modelo final."
            ],
            "recommended_focus_today": "Validar que el backend ya devuelve el schema oficial correctamente."
        },
        "kpi_breakdown": {
            "conversions_score": 0 if total_conversions == 0 else 70,
            "cpa_score": 0 if cpa is None else (90 if cpa < 100 else 40),
            "ctr_score": 60 if ctr > 0 else 0,
            "conversion_rate_score": 60 if conversion_rate > 0 else 0,
            "waste_control_score": 10 if estimated_waste > 0 else 90
        },
        "campaigns": campaigns,
        "waste": {
            "estimated_waste": estimated_waste,
            "waste_level": "Alto" if estimated_waste > 1000 else ("Medio" if estimated_waste > 0 else "Bajo"),
            "top_waste_sources": waste_sources,
            "notes": []
        },
        "alerts": alerts,
        "recommendations": recommendations,
        "trends": trends
    }

    return result


def _call_openai_analysis(data: dict) -> Optional[dict]:
    """
    Calls OpenAI using the master prompt and returns parsed JSON if successful.
    Returns None if unavailable or invalid.
    """
    # 1. Intentar leer variable de entorno
    api_key = os.getenv("OPENAI_API_KEY")
    
    # 2. Si no hay variable de entorno, intentar leer archivo key.txt
    if not api_key:
        try:
            key_path = os.path.join(os.path.dirname(__file__), "..", "key.txt")
            if os.path.exists(key_path):
                with open(key_path, "r") as f:
                    api_key = f.read().strip()
                print(f"[INFO] API Key cargada desde key.txt")
        except Exception as e:
            print(f"[ERROR] No se pudo leer key.txt: {e}")

    # 3. Validar que tenemos API Key
    if not api_key:
        print("[WARN] No se encontró API Key. Usando fallback local.")
        return None

    # 4. Modelo corregido (gpt-4o-mini en lugar de gpt-4.1-mini)
    model = "gpt-4o-mini"
    print(f"[INFO] Llamando a OpenAI con modelo: {model}")

    try:
        client = OpenAI(api_key=api_key)

        user_payload = json.dumps(data, ensure_ascii=False)

        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": THAI_THAI_ADS_MASTER_PROMPT},
                {"role": "user", "content": user_payload},
            ],
        )

        content = response.choices[0].message.content or ""
        content = _strip_code_fences(content)
        parsed = _safe_json_loads(content)
        
        if parsed is None:
            print("[ERROR] OpenAI devolvió JSON inválido.")
            print(f"[DEBUG] Respuesta cruda (primeros 500 chars): {content[:500]}...")
        
        return parsed

    except Exception as e:
        print(f"[ERROR] Excepción en llamada OpenAI: {str(e)}")
        return None


async def analyze_campaign_data(data: dict) -> dict:
    """
    Main analyzer:
    1. Tries OpenAI with the official Thai Thai master prompt.
    2. Falls back to local deterministic logic if OpenAI is unavailable or fails.
    """
    llm_result = _call_openai_analysis(data)
    
    if llm_result is not None:
        print("[INFO] Análisis completado con LLM real.")
        return llm_result

    print("[INFO] Usando análisis fallback local.")
    return _fallback_analysis(data)