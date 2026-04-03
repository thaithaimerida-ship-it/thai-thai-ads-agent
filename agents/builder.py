"""
Sub-agente Builder — Crea campañas completas desde lenguaje natural.
Usa Claude Sonnet 4.6 para diseñar la campaña y ads_client.py para deployar.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── Validaciones ────────────────────────────────────────────────────────────

def validate_config(config: dict) -> dict:
    """
    Valida el JSON config generado por Claude.
    Retorna {"valid": True} o {"valid": False, "errors": [...]}.
    """
    errors = []

    # Campaign name
    if not config.get("campaign_name"):
        errors.append("Falta campaign_name")

    # Budget
    budget = config.get("daily_budget_mxn", 0)
    if budget < 10:
        errors.append(f"Budget ${budget} es menor al mínimo ($10 MXN/día)")
    if budget > 500:
        errors.append(f"Budget ${budget} excede el máximo recomendado ($500 MXN/día)")

    # Ad groups
    ad_groups = config.get("ad_groups", [])
    if not ad_groups:
        errors.append("Debe tener al menos 1 ad group")
    if len(ad_groups) > 10:
        errors.append(f"Demasiados ad groups ({len(ad_groups)}), máximo 10")

    for i, ag in enumerate(ad_groups):
        ag_name = ag.get("name", f"Ad Group {i+1}")

        # Headlines
        headlines = ag.get("headlines", [])
        if len(headlines) < 3:
            errors.append(f"[{ag_name}] Necesita mínimo 3 headlines, tiene {len(headlines)}")
        if len(headlines) > 15:
            errors.append(f"[{ag_name}] Máximo 15 headlines, tiene {len(headlines)}")
        for j, h in enumerate(headlines):
            if len(h) > 30:
                errors.append(f"[{ag_name}] Headline {j+1} excede 30 chars ({len(h)}): '{h}'")

        # Descriptions
        descriptions = ag.get("descriptions", [])
        if len(descriptions) < 2:
            errors.append(f"[{ag_name}] Necesita mínimo 2 descriptions, tiene {len(descriptions)}")
        if len(descriptions) > 4:
            errors.append(f"[{ag_name}] Máximo 4 descriptions, tiene {len(descriptions)}")
        for j, d in enumerate(descriptions):
            if len(d) > 90:
                errors.append(f"[{ag_name}] Description {j+1} excede 90 chars ({len(d)}): '{d[:50]}...'")

        # Keywords
        keywords = ag.get("keywords", [])
        if not keywords:
            errors.append(f"[{ag_name}] Necesita al menos 1 keyword")

    # Negative keywords (opcional pero recomendado)
    if not config.get("negative_keywords"):
        errors.append("ADVERTENCIA: Sin negative keywords. Se recomienda agregar al menos 5.")

    # Geo targeting
    geo = config.get("geo_targeting", {})
    if not geo:
        errors.append("Falta geo_targeting")

    return {"valid": len([e for e in errors if not e.startswith("ADVERTENCIA")]) == 0, "errors": errors}


# ── Generación con Claude ──────────────────────────────────────────────────

BUILDER_SYSTEM_PROMPT = """Eres el Campaign Builder de Thai Thai Mérida, un restaurante de cocina tailandesa auténtica en Mérida, Yucatán, México.

CONTEXTO DEL NEGOCIO:
- Restaurante: Thai Thai Mérida — cocina tailandesa auténtica
- Ubicación: Calle 30 No. 351 Col. Emiliano Zapata Norte, Mérida, Yucatán
- WhatsApp: +52 999 931 7457
- Landing page: https://www.thaithaimerida.com
- Servicios: Comer en restaurante (local), delivery a domicilio, reservaciones
- Ticket promedio: $350–$500 MXN por persona
- Temporada alta: Nov–Abr (turismo) | Baja: May–Sep (calor)
- Clientes objetivo: Familias locales, turistas, parejas, grupos corporativos
- Google Ads Customer ID: 4021070209

CAMPAÑAS EXISTENTES (no duplicar):
- "Thai Mérida - Local" (22612348265): Smart, $50/día, visitas físicas
- "Thai Mérida - Delivery" (22839241090): Smart, $100/día, delivery
- "Thai Mérida - Reservaciones" (23680871468): Search, $70/día, reservas

Tu trabajo: recibir un brief en español y generar un JSON config completo para una nueva campaña Search.

REGLAS DE GENERACIÓN:
1. Headlines: máximo 30 caracteres CADA UNO. Cuenta los caracteres. Si excede, acorta.
2. Descriptions: máximo 90 caracteres CADA UNO.
3. Genera mínimo 8 headlines y 3 descriptions por ad group.
4. Keywords en español (mercado es Mérida, México). Incluir variantes con/sin acento.
5. Match types: "PHRASE" para budget < $80/día, "EXACT" para brand terms, "BROAD" solo si budget > $150/día.
6. Negative keywords: SIEMPRE incluir al menos estas: "receta", "recipe", "chino", "china", "japonés", "sushi", "gratis", "free", "empleo", "trabajo", "vacante".
7. Geo targeting: siempre centro de Mérida (lat: 20.9674, lng: -89.5926) + radio en km.
8. La campaña se crea SIEMPRE en estado PAUSED.
9. CPC bid default: $20 MXN (20_000_000 micros).
10. Landing URL default: https://www.thaithaimerida.com (a menos que se indique otra).

RESPONDE ÚNICAMENTE con el JSON. Sin markdown, sin explicaciones, sin backticks.

ESTRUCTURA DEL JSON:
{
  "campaign_name": "Thai Mérida - [Objetivo]",
  "daily_budget_mxn": 80,
  "cpc_bid_mxn": 20,
  "landing_url": "https://www.thaithaimerida.com",
  "geo_targeting": {
    "lat": 20.9674,
    "lng": -89.5926,
    "radius_km": 15
  },
  "ad_groups": [
    {
      "name": "Nombre del Ad Group",
      "headlines": ["Headline 1 (≤30 chars)", "Headline 2", ...],
      "descriptions": ["Description 1 (≤90 chars)", ...],
      "keywords": [
        {"text": "keyword aquí", "match_type": "PHRASE"}
      ]
    }
  ],
  "negative_keywords": ["receta", "chino", "sushi", ...]
}"""


def generate_campaign_config(prompt: str) -> dict:
    """
    Usa Claude Sonnet 4.6 para generar un JSON config de campaña
    a partir de un prompt en lenguaje natural.
    Fallback a Haiku 4.5 si Sonnet falla.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "error", "message": "ANTHROPIC_API_KEY no configurada"}

    client = anthropic.Anthropic(api_key=api_key)
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    user_message = (
        f"FECHA: {fecha}\n\n"
        f"BRIEF DEL CLIENTE:\n{prompt}\n\n"
        f"Genera el JSON config completo para esta campaña."
    )

    for model, label in [("claude-sonnet-4-6", "Sonnet"), ("claude-haiku-4-5-20251001", "Haiku")]:
        try:
            logger.info(f"Builder: generando config con {label}...")
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=BUILDER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )
            raw = response.content[0].text.strip()

            # Limpiar posibles code fences
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                raw = "\n".join(lines)

            config = json.loads(raw)
            config["_generated_by"] = label
            config["_generated_at"] = fecha
            logger.info(f"Builder: config generado exitosamente con {label}")
            return {"status": "success", "config": config}

        except json.JSONDecodeError as e:
            logger.warning(f"Builder: {label} retornó JSON inválido: {e}")
            if model == "claude-haiku-4-5-20251001":
                return {"status": "error", "message": f"Ambos modelos fallaron. Último error JSON: {e}", "raw": raw[:500]}
            continue
        except Exception as e:
            logger.warning(f"Builder: {label} falló: {e}")
            if model == "claude-haiku-4-5-20251001":
                return {"status": "error", "message": f"Ambos modelos fallaron. Último error: {e}"}
            continue

    return {"status": "error", "message": "No se pudo generar el config"}


# ── Deploy en 2 fases ──────────────────────────────────────────────────────

def deploy_campaign(config: dict) -> dict:
    """
    Despliega una campaña completa en Google Ads usando el config validado.

    Fase 1 (Atómica): Budget + Campaign. Si falla, no se crea nada.
    Fase 2 (Parcial): Ad Groups + Keywords + RSAs + Negative Keywords + Geo.
                       Los errores individuales se registran pero no abortan.

    Retorna un receipt completo de lo que se creó.
    """
    from engine.ads_client import (
        get_ads_client,
        create_search_campaign,
        create_ad_group,
        create_rsa,
        add_keyword_to_ad_group,
        add_negative_keyword,
        update_campaign_proximity,
        log_agent_action,
    )

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    receipt = {
        "status": "in_progress",
        "timestamp": datetime.now().isoformat(),
        "campaign_name": config["campaign_name"],
        "phase_1": None,
        "phase_2": {"ad_groups": [], "keywords": [], "ads": [], "negative_keywords": [], "geo": None},
        "errors": [],
    }

    # ── FASE 1: Budget + Campaign (atómica) ─────────────────────────────
    try:
        client = get_ads_client()
    except Exception as e:
        receipt["status"] = "error"
        receipt["errors"].append(f"No se pudo conectar a Google Ads: {e}")
        return receipt

    budget_micros = int(config["daily_budget_mxn"] * 1_000_000)
    campaign_result = create_search_campaign(
        client, customer_id,
        name=config["campaign_name"],
        budget_micros=budget_micros
    )

    if campaign_result.get("status") != "success":
        receipt["status"] = "error"
        receipt["phase_1"] = campaign_result
        receipt["errors"].append(f"Fase 1 falló: {campaign_result.get('message', 'unknown')}")
        return receipt

    campaign_resource = campaign_result["campaign_resource"]
    campaign_id = campaign_resource.split("/")[-1]
    receipt["phase_1"] = {
        "status": "success",
        "campaign_resource": campaign_resource,
        "campaign_id": campaign_id,
        "budget_resource": campaign_result["budget_resource"],
        "budget_mxn_dia": config["daily_budget_mxn"],
    }

    log_agent_action(
        "builder_create_campaign", config["campaign_name"],
        {"brief": config.get("_original_prompt", "")[:200]},
        {"budget_day": config["daily_budget_mxn"], "status": "PAUSED"},
        "success", campaign_result
    )

    # ── FASE 2: Ad Groups + Keywords + RSAs + Negatives + Geo ───────────
    cpc_bid_micros = int(config.get("cpc_bid_mxn", 20) * 1_000_000)
    landing_url = config.get("landing_url", "https://www.thaithaimerida.com")

    for ag in config.get("ad_groups", []):
        ag_name = ag["name"]

        # Crear Ad Group
        ag_result = create_ad_group(client, customer_id, campaign_resource, ag_name, cpc_bid_micros)
        if ag_result.get("status") != "success":
            receipt["errors"].append(f"Ad Group '{ag_name}' falló: {ag_result.get('message')}")
            receipt["phase_2"]["ad_groups"].append({"name": ag_name, "status": "error"})
            continue

        ag_resource = ag_result["resource_name"]
        receipt["phase_2"]["ad_groups"].append({"name": ag_name, "status": "success", "resource": ag_resource})

        # Crear RSA
        rsa_result = create_rsa(
            client, customer_id, ag_resource,
            ag.get("headlines", []),
            ag.get("descriptions", []),
            final_url=landing_url
        )
        receipt["phase_2"]["ads"].append({
            "ad_group": ag_name,
            "status": rsa_result.get("status"),
            "error": rsa_result.get("message") if rsa_result.get("status") != "success" else None,
        })

        # Agregar Keywords
        for kw in ag.get("keywords", []):
            kw_text = kw["text"] if isinstance(kw, dict) else kw
            match_type = kw.get("match_type", "PHRASE") if isinstance(kw, dict) else "PHRASE"
            api_match = "EXACT" if match_type == "EXACT" else "BROAD"
            kw_result = add_keyword_to_ad_group(client, customer_id, ag_resource, kw_text, api_match)
            receipt["phase_2"]["keywords"].append({
                "keyword": kw_text,
                "match_type": match_type,
                "ad_group": ag_name,
                "status": kw_result.get("status"),
            })

    # Negative keywords (campaign-level)
    for nkw in config.get("negative_keywords", []):
        nk_result = add_negative_keyword(client, customer_id, campaign_id, nkw)
        receipt["phase_2"]["negative_keywords"].append({
            "keyword": nkw,
            "status": nk_result.get("status"),
        })

    # Geo targeting
    geo = config.get("geo_targeting", {})
    if geo and geo.get("lat") and geo.get("lng") and geo.get("radius_km"):
        geo_result = update_campaign_proximity(
            client, customer_id, campaign_id,
            lat=geo["lat"], lng=geo["lng"], radius_km=geo["radius_km"]
        )
        receipt["phase_2"]["geo"] = {
            "lat": geo["lat"], "lng": geo["lng"],
            "radius_km": geo["radius_km"],
            "status": geo_result.get("status", "unknown"),
        }

    # Resumen final
    total_errors = len(receipt["errors"])
    receipt["status"] = "success" if total_errors == 0 else "partial_success"
    receipt["summary"] = {
        "campaign": config["campaign_name"],
        "campaign_id": campaign_id,
        "budget": f"${config['daily_budget_mxn']} MXN/día",
        "ad_groups_created": len([a for a in receipt["phase_2"]["ad_groups"] if a["status"] == "success"]),
        "keywords_added": len([k for k in receipt["phase_2"]["keywords"] if k["status"] == "success"]),
        "negative_keywords_added": len([n for n in receipt["phase_2"]["negative_keywords"] if n["status"] == "success"]),
        "ads_created": len([a for a in receipt["phase_2"]["ads"] if a["status"] == "success"]),
        "geo_set": receipt["phase_2"]["geo"] is not None,
        "errors": total_errors,
        "state": "PAUSED — revisar en Google Ads UI antes de activar",
    }

    log_agent_action(
        "builder_deploy_complete", config["campaign_name"],
        {},
        receipt["summary"],
        receipt["status"],
        receipt
    )

    return receipt


# ── Clase Builder ───────────────────────────────────────────────────────────

class Builder:
    """
    Sub-agente Builder — Crea campañas completas desde lenguaje natural.

    Flujo:
    1. build_config(prompt) → genera JSON config con Claude
    2. validate() → valida estructura y límites
    3. deploy() → ejecuta en Google Ads API (2 fases)
    """

    def __init__(self):
        self.customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
        self.config = None
        self.validation = None
        self.receipt = None

    def build_config(self, prompt: str) -> dict:
        """Paso 1: Genera config con Claude desde un prompt en lenguaje natural."""
        result = generate_campaign_config(prompt)
        if result.get("status") == "success":
            self.config = result["config"]
            self.config["_original_prompt"] = prompt[:500]
            self.validation = validate_config(self.config)
            return {
                "status": "success",
                "config": self.config,
                "validation": self.validation,
            }
        return result

    def deploy(self) -> dict:
        """Paso 2: Despliega el config aprobado en Google Ads."""
        if not self.config:
            return {"status": "error", "message": "No hay config generado. Llama build_config() primero."}
        if not self.validation or not self.validation.get("valid"):
            return {
                "status": "error",
                "message": "El config no pasó validación.",
                "errors": self.validation.get("errors", []) if self.validation else ["Sin validación"],
            }
        self.receipt = deploy_campaign(self.config)
        return self.receipt

    def get_summary(self) -> dict:
        """Retorna resumen del último deploy."""
        if not self.receipt:
            return {"status": "no_deploy", "message": "No se ha ejecutado deploy aún."}
        return self.receipt.get("summary", {})
