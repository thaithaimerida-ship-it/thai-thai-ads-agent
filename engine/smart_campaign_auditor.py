"""
Thai Thai Ads Agent — Auditoría de Smart Campaigns

Cubre las tres dimensiones auditables de Smart Campaigns vía Google Ads API:
  1. Performance    — CPA, gasto, conversiones vs targets de negocio
  2. Keyword themes — temas irrelevantes para restaurante tailandés
  3. Landing/setting — final_url vacía o incorrecta

Distinción importante:
  - "no auditable por keyword_view"  ≠  "no auditable en absoluto"
  - Smart Campaigns NO tienen keyword_view (por diseño de Google)
  - Sí tienen: campaign metrics, smart_campaign_setting, campaign_criterion
    (keyword_theme), geo criteria, y smart_campaign_search_term_view

Limitaciones reales de API (verificadas):
  - keyword_view no aplica — Smart no tiene keywords manuales
  - smart_campaign_search_term_view no soporta métricas de conversiones
  - Keyword themes pueden auditarse pero su modificación vía API
    requiere confirmación manual (no se auto-ejecuta en MVP)

Hallazgos se registran como propuestas en autonomous_decisions
con action_type="smart_audit" para aparecer en el reporte semanal.
"""

from datetime import datetime, timedelta
from typing import Dict, List

import logging
logger = logging.getLogger(__name__)

# Contexto de negocio inyectado en el prompt del LLM.
# Actualizar aquí si cambian los servicios de Thai Thai.
_BUSINESS_CONTEXT = """Thai Thai es un restaurante de comida tailandesa artesanal ubicado en
Mérida, Yucatán, México. Opera con dos objetivos publicitarios en Google Ads:

1. DELIVERY: pedidos a domicilio a través de Gloria Food (plataforma propia).
   Clientes objetivo: personas en Mérida que quieren comida tailandesa en casa.

2. RESERVACIONES: mesas en el restaurante físico.
   Clientes objetivo: personas que buscan cenar en restaurante tailandés en Mérida.

Un keyword theme es RELEVANTE si atrae búsquedas de personas que potencialmente
quieren ordenar comida tailandesa a domicilio o reservar una mesa en Mérida.

Un keyword theme es IRRELEVANTE si atrae búsquedas que nunca convertirán, como:
- Personas buscando empleo o trabajo en restaurantes
- Personas buscando recetas para cocinar en casa
- Búsquedas de otros tipos de cocina (china, japonesa, sushi, etc.)
- Cursos de cocina tailandesa o ingredientes para comprar
- Cualquier búsqueda que no tenga intención de consumo en restaurante"""

# ── CPA targets Thai Thai (MXN) ───────────────────────────────────────────────
# Fuente: CLAUDE.md — CPA Targets sección
_CPA_TARGETS = {
    "delivery": {"ideal": 25, "max": 45, "critical": 80},
    "local":    {"ideal": 35, "max": 60, "critical": 100},
    "default":  {"ideal": 35, "max": 60, "critical": 100},
}

# ── Temas irrelevantes para restaurante tailandés ─────────────────────────────
# Palabras clave libres que no tienen relación con el negocio y
# generan impresiones ante búsquedas equivocadas.
_IRRELEVANT_THEMES = {
    "empleo", "trabajo", "clases", "curso", "cursos",
    "como hacer", "ingredientes", "ingrediente", "receta", "recetas",
    "trabajo cerca", "vacantes", "solicitar empleo", "empleo cerca",
    "cocinero", "chef empleo", "trabajo restaurante",
    "chino", "china", "chinese restaurant", "chinese food",
    "comida china",
}

# Dominio esperado en final_url
_EXPECTED_DOMAIN = "thaithaimerida.com"


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _evaluate_themes_with_llm(themes: List[str]) -> List[str]:
    """
    Envía una lista de keyword themes a Claude Haiku para evaluación semántica.

    Solo se llama con temas que NO están en _IRRELEVANT_THEMES (la lista estática
    actúa como pre-filtro para casos obvios y ahorra tokens).

    Returns:
        Lista de temas que el LLM considera irrelevantes.
        En caso de error de API, retorna [] — el agente continúa con solo la lista estática.
    """
    import anthropic
    import json
    import os

    if not themes:
        return []

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        prompt = f"""{_BUSINESS_CONTEXT}

Se te entrega la siguiente lista de keyword themes actualmente activos en las
Smart Campaigns de Google Ads de Thai Thai:

{json.dumps(themes, ensure_ascii=False, indent=2)}

Tu objetivo NO es recortar gasto por defecto.
Tu objetivo es detectar "desperdicio real" (búsquedas que jamás comprarán) para que
ese presupuesto se libere y el algoritmo de Google Ads lo reasigne automáticamente
a búsquedas que sí traen comensales a las mesas o pedidos de delivery.
Sé estricto identificando la basura para maximizar la rentabilidad del restaurante.

Tu tarea: identifica cuáles de estos temas son DESPERDICIO REAL — búsquedas que
nunca convertirán en un pedido de delivery o una reservación en Thai Thai.

Reglas importantes:
- Sé conservador con temas ambiguos. Un tema con intención mixta debe considerarse
  RELEVANTE — el algoritmo de Google puede encontrar valor en él.
- Solo marca como irrelevante lo que es claramente basura: intención de empleo,
  recetas para cocinar en casa, otros tipos de cocina no tailandesa, cursos, etc.
- Ejemplos de temas RELEVANTES (no tocar): "comida a domicilio mérida",
  "restaurantes en mérida", "comida tailandesa", "cenar mérida".
- Ejemplos de DESPERDICIO REAL: "trabajo de cocinero", "receta pad thai casero",
  "restaurante chino mérida", "clases de cocina tailandesa".

Responde ÚNICAMENTE con un JSON array de strings.
Incluye solo los temas que son DESPERDICIO REAL.
Si todos son relevantes, responde con [].
No escribas explicaciones, código markdown, ni texto adicional. Solo el JSON array."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # Limpiar posibles backticks de markdown si el modelo los incluye
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        if not isinstance(result, list):
            logger.warning("LLM returned non-list for theme evaluation: %s", type(result))
            return []

        # Validar que los resultados sean strings presentes en la lista original
        theme_set = {t.strip().lower() for t in themes}
        validated = [
            t for t in result
            if isinstance(t, str) and t.strip().lower() in theme_set
        ]

        logger.info(
            "LLM theme evaluation: %d temas evaluados → %d irrelevantes detectados",
            len(themes), len(validated),
        )
        return validated

    except Exception as e:
        logger.warning(
            "LLM theme evaluation falló — usando solo lista estática. Error: %s", e
        )
        return []


def _cpa_target(campaign_name: str) -> dict:
    name = campaign_name.lower()
    if "delivery" in name:
        return _CPA_TARGETS["delivery"]
    if "local" in name:
        return _CPA_TARGETS["local"]
    return _CPA_TARGETS["default"]


def _fetch_smart_metrics(client, target_id: str, days: int = 7) -> List[dict]:
    """Métricas agregadas de los últimos `days` días para campañas SMART ENABLED."""
    ga = client.get_service("GoogleAdsService")
    end   = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = f"""
        SELECT
          campaign.id, campaign.name,
          metrics.impressions, metrics.clicks, metrics.conversions,
          metrics.cost_micros, metrics.ctr, metrics.cost_per_conversion
        FROM campaign
        WHERE campaign.advertising_channel_type = 'SMART'
          AND campaign.status = 'ENABLED'
          AND segments.date BETWEEN '{start}' AND '{end}'
    """
    out = []
    try:
        for row in ga.search(customer_id=target_id, query=q):
            c, m = row.campaign, row.metrics
            cost = m.cost_micros / 1_000_000
            cpa  = (m.cost_per_conversion / 1_000_000) if m.conversions > 0 else None
            out.append({
                "campaign_id":   str(c.id),
                "campaign_name": c.name,
                "cost_mxn":      round(cost, 2),
                "conversions":   int(m.conversions),
                "cpa_mxn":       round(cpa, 2) if cpa is not None else None,
                "ctr":           round(m.ctr, 4),
                "clicks":        int(m.clicks),
                "impressions":   int(m.impressions),
                "period_days":   days,
            })
    except Exception as e:
        logger.warning("smart_metrics query failed: %s", e)
        out.append({"error": str(e)})
    return out


def _fetch_smart_settings(client, target_id: str) -> Dict[str, dict]:
    """Retorna final_url e idioma por campaign_id para todas las Smart Campaigns."""
    ga = client.get_service("GoogleAdsService")
    q = """
        SELECT
          campaign.id, campaign.name,
          smart_campaign_setting.final_url,
          smart_campaign_setting.advertising_language_code
        FROM smart_campaign_setting
        WHERE campaign.advertising_channel_type = 'SMART'
          AND campaign.status != 'REMOVED'
    """
    out: Dict[str, dict] = {}
    try:
        for row in ga.search(customer_id=target_id, query=q):
            cid = str(row.campaign.id)
            s   = row.smart_campaign_setting
            out[cid] = {
                "final_url":     s.final_url or "",
                "language_code": s.advertising_language_code or "",
            }
    except Exception as e:
        logger.warning("smart_settings query failed: %s", e)
        out["_error"] = str(e)
    return out


def _fetch_local_actions(client, target_id: str, campaign_id: str, days: int = 7) -> dict:
    """
    Para campañas Local: suma 'Local actions - Directions' y 'Store visits'
    de los últimos `days` días. Retorna el conteo como local_directions_count.
    Estas acciones ocurren en Google Maps y no aparecen en GA4.
    """
    ga = client.get_service("GoogleAdsService")
    end   = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = f"""
        SELECT
            segments.conversion_action_name,
            metrics.all_conversions
        FROM campaign
        WHERE campaign.id = {campaign_id}
          AND segments.date BETWEEN '{start}' AND '{end}'
    """
    _PHYSICAL_INTENT = {"local actions - directions", "store visits"}
    directions = 0.0
    try:
        for row in ga.search(customer_id=target_id, query=q):
            name = (row.segments.conversion_action_name or "").strip().lower()
            if name in _PHYSICAL_INTENT:
                directions += row.metrics.all_conversions
    except Exception as e:
        logger.warning("_fetch_local_actions campaign_id=%s: %s", campaign_id, e)
    return {"local_directions_count": round(directions)}


def _fetch_keyword_themes(client, target_id: str) -> Dict[str, List[dict]]:
    """
    Retorna lista de keyword themes por campaign_id para Smart Campaigns.

    Cada entrada es un dict con:
      {"theme": str, "resource_name": str}

    El resource_name es necesario para las operaciones REMOVE vía
    CampaignCriterionService (ver ads_client.remove_smart_campaign_theme).
    """
    ga = client.get_service("GoogleAdsService")
    q = """
        SELECT
          campaign.id,
          campaign_criterion.resource_name,
          campaign_criterion.keyword_theme.free_form_keyword_theme
        FROM campaign_criterion
        WHERE campaign.advertising_channel_type = 'SMART'
          AND campaign.status != 'REMOVED'
          AND campaign_criterion.type = 'KEYWORD_THEME'
    """
    out: Dict[str, List[dict]] = {}
    try:
        for row in ga.search(customer_id=target_id, query=q):
            cid   = str(row.campaign.id)
            free  = row.campaign_criterion.keyword_theme.free_form_keyword_theme
            rname = row.campaign_criterion.resource_name
            if free:
                out.setdefault(cid, []).append({
                    "theme":         free,
                    "resource_name": rname,
                })
    except Exception as e:
        logger.warning("keyword_themes query failed: %s", e)
        out["_error"] = [{"theme": str(e), "resource_name": ""}]
    return out


# ─── Función principal ────────────────────────────────────────────────────────

def audit_smart_campaigns(client, target_id: str) -> dict:
    """
    Ejecuta la auditoría de Smart Campaigns en 3 dimensiones.

    Returns dict con:
      campaigns        — lista de campañas con sus hallazgos
      issues           — todos los issues planos (para conteo en summary)
      proposals        — propuestas de acción (no se auto-ejecutan)
      summary          — contadores agregados
      audit_coverage   — tabla de cobertura para el correo
    """
    from config.agent_config import SMART_LLM_THEME_EVAL_ENABLED
    _llm_eval_enabled = SMART_LLM_THEME_EVAL_ENABLED

    metrics_list    = _fetch_smart_metrics(client, target_id)
    settings_by_id  = _fetch_smart_settings(client, target_id)
    themes_by_id    = _fetch_keyword_themes(client, target_id)

    campaigns: List[dict] = []
    all_issues: List[dict] = []
    proposals:  List[dict] = []

    for m in metrics_list:
        if "error" in m:
            logger.warning("smart_audit: skipping metric row with error: %s", m["error"])
            continue

        cid   = m["campaign_id"]
        cname = m["campaign_name"]
        targets = _cpa_target(cname)
        cost  = m.get("cost_mxn", 0)
        conv  = m.get("conversions", 0)
        cpa   = m.get("cpa_mxn")

        c_issues:    List[dict] = []
        c_proposals: List[dict] = []

        # Para campañas Local: extraer acciones físicas (Directions + Store visits)
        _local_actions = {}
        if "local" in cname.lower():
            _local_actions = _fetch_local_actions(client, target_id, cid)

        # ── Check 1: Performance ──────────────────────────────────────────────
        if cost == 0:
            c_issues.append({
                "check":       "performance",
                "signal":      "SMART_P0",
                "severity":    "warning",
                "description": f"Sin gasto en los últimos {m['period_days']} días",
            })
        elif conv == 0:
            c_issues.append({
                "check":       "performance",
                "signal":      "SMART_P1",
                "severity":    "warning",
                "description": f"Sin conversiones en {m['period_days']} días (gasto: ${cost:.0f} MXN)",
            })
        elif cpa is not None:
            if cpa > targets["critical"]:
                c_issues.append({
                    "check":           "performance",
                    "signal":          "SMART_P2",
                    "severity":        "critical",
                    "description":     f"CPA crítico: ${cpa:.0f} MXN (máximo aceptable: ${targets['critical']} MXN)",
                    "cpa_mxn":         cpa,
                    "target_critical": targets["critical"],
                })
            elif cpa > targets["max"]:
                c_issues.append({
                    "check":       "performance",
                    "signal":      "SMART_P3",
                    "severity":    "warning",
                    "description": f"CPA sobre máximo: ${cpa:.0f} MXN (target ideal: ${targets['ideal']} MXN)",
                    "cpa_mxn":     cpa,
                    "target_max":  targets["max"],
                })

        # ── Check 2: Keyword theme quality ────────────────────────────────────
        theme_entries = themes_by_id.get(cid, [])
        themes        = [e["theme"] for e in theme_entries]   # solo textos, para compatibilidad

        # Capa 1: lista estática — captura casos obvios sin costo de API
        _static_bad = {
            e["theme"] for e in theme_entries
            if e["theme"].strip().lower() in _IRRELEVANT_THEMES
        }

        # Capa 2: LLM semántico — solo para temas que la lista estática no captura
        _llm_bad: set = set()
        _unchecked = [
            e["theme"] for e in theme_entries
            if e["theme"].strip().lower() not in _IRRELEVANT_THEMES
        ]
        if _unchecked and _llm_eval_enabled:
            _llm_result = _evaluate_themes_with_llm(_unchecked)
            _llm_bad    = set(_llm_result)
            if _llm_bad:
                logger.info(
                    "Campaña '%s' — LLM detectó %d temas adicionales irrelevantes: %s",
                    cname, len(_llm_bad), list(_llm_bad),
                )

        # Unión: cualquier tema marcado por cualquiera de las dos capas
        _all_bad = _static_bad | _llm_bad
        irrelevant_entries = [
            e for e in theme_entries
            if e["theme"] in _all_bad
        ]
        irrelevant = [e["theme"] for e in irrelevant_entries]

        if irrelevant:
            c_issues.append({
                "check":             "keyword_themes",
                "signal":            "SMART_KT1",
                "severity":          "warning",
                "description":       f"{len(irrelevant)} tema(s) irrelevante(s) de {len(themes)} totales",
                "irrelevant_themes": irrelevant,
                "total_themes":      len(themes),
            })
            c_proposals.append({
                "type":             "smart_theme_cleanup",
                "campaign_id":      cid,
                "campaign_name":    cname,
                "action":           "Eliminar temas irrelevantes de Smart Campaign",
                "themes_to_remove": irrelevant,
                # Incluye resource_names para que main.py pueda ejecutar REMOVE via API
                "themes_to_remove_with_resources": irrelevant_entries,
                "total_themes_before": len(themes),
                "reason": (
                    f"Temas fuera de contexto para restaurante tailandés detectados: "
                    f"{', '.join(irrelevant[:5])}. "
                    "Pueden generar impresiones ante búsquedas de empleo, cursos o cocina china."
                ),
                "urgency":      "normal",
                "auto_execute": True,   # ahora se ejecuta si SMART_THEME_REMOVAL_ENABLED=true
            })

        # ── Check 3: Landing / setting ────────────────────────────────────────
        # Campañas "Local" apuntan al perfil de Google Maps, no tienen web — se omite la validación.
        _is_local_campaign = "local" in cname.lower()

        setting   = settings_by_id.get(cid, {})
        final_url = setting.get("final_url", "")

        if _is_local_campaign:
            pass  # final_url vacía es esperada para campañas de tráfico peatonal
        elif not final_url:
            c_issues.append({
                "check":       "landing",
                "signal":      "SMART_L1",
                "severity":    "warning",
                "description": (
                    "final_url vacía en smart_campaign_setting — "
                    "la landing de esta campaña no está configurada en la API. "
                    "Verificar manualmente en Google Ads → Campaña → Configuración."
                ),
            })
        elif _EXPECTED_DOMAIN not in final_url:
            c_issues.append({
                "check":       "landing",
                "signal":      "SMART_L2",
                "severity":    "warning",
                "description": f"final_url inesperada: '{final_url}' — no apunta a {_EXPECTED_DOMAIN}",
                "final_url":   final_url,
            })

        campaigns.append({
            "campaign_id":          cid,
            "campaign_name":        cname,
            "type":                 "SMART",
            "metrics_7d": {
                "cost_mxn":    cost,
                "conversions": conv,
                "cpa_mxn":     cpa,
                "ctr":         m.get("ctr"),
                "clicks":      m.get("clicks"),
                "impressions": m.get("impressions"),
            },
            "cpa_targets":          targets,
            "keyword_themes_total": len(themes),
            "keyword_themes_bad":   len(irrelevant),
            "final_url":            final_url,
            "issues":               c_issues,
            "proposals":            c_proposals,
            "issues_count":         len(c_issues),
            # Acciones físicas solo disponibles para campañas Local (Google Maps)
            "local_directions_count": _local_actions.get("local_directions_count"),
        })

        all_issues.extend(c_issues)
        proposals.extend(c_proposals)

    critical = sum(1 for i in all_issues if i.get("severity") == "critical")
    warnings = sum(1 for i in all_issues if i.get("severity") == "warning")

    # ── Tabla de cobertura para el correo ─────────────────────────────────────
    coverage = {
        "type":                "SMART",
        "auditable":           True,
        "checks_run":          ["performance", "keyword_themes", "landing"],
        "not_applicable":      ["keyword_view"],   # por diseño de Google, no limitación del módulo
        "api_limitations":     ["conversions en smart_campaign_search_term_view no soportado"],
        "campaigns_audited":   len(campaigns),
    }

    return {
        "campaigns":      campaigns,
        "issues":         all_issues,
        "proposals":      proposals,
        "audit_coverage": coverage,
        "summary": {
            "campaigns_audited":    len(campaigns),
            "issues_total":         len(all_issues),
            "issues_critical":      critical,
            "issues_warning":       warnings,
            "proposals_generated":  len(proposals),
        },
    }
