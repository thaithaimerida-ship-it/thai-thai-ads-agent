"""
Thai Thai Ads Agent — Configuración de Autonomía
Thresholds, whitelists y parámetros configurables para el clasificador de riesgo.

Editar este archivo para ajustar el comportamiento del agente sin tocar lógica.
"""

import os as _os

# ============================================================================
# THRESHOLDS DE DECISIÓN AUTOMÁTICA
# ============================================================================

# Gasto mínimo (MXN) en una keyword para considerarla candidata a bloqueo automático
# Si el gasto está por debajo de este umbral, el agente observa en lugar de actuar
KEYWORD_MIN_SPEND_TO_BLOCK = 70.0

# Ventana de tiempo (días) que debe haber transcurrido con gasto antes de bloquear
# Evita actuar en keywords demasiado nuevas
KEYWORD_MIN_EVIDENCE_DAYS = 7

# Cambio máximo de presupuesto (%) que el agente puede auto-ejecutar sin aprobación.
# Por encima de este % se clasifica como riesgo medio (RISK_PROPOSE).
BUDGET_CHANGE_MAX_PCT_MEDIUM_RISK = 20.0

# Cambio de presupuesto (%) por encima del cual la urgencia sube a HIGH (sigue siendo RISK_PROPOSE).
# El agente nunca ejecuta cambios >40% automáticamente.
BUDGET_CHANGE_MAX_PCT_HIGH_RISK = 40.0

# ============================================================================
# PRESUPUESTO MENSUAL — GUARDRAIL DE GASTO
# ============================================================================

# Presupuesto mensual total de Google Ads (MXN).
# El agente verifica que ninguna auto-ejecución lo supere antes de ejecutar.
MONTHLY_ADS_BUDGET_MXN = 10_000.0

# Presupuesto diario objetivo (MXN) — referencia para escalar proporcionalmente.
# 10000 / 30 = 333.33 → redondeado a 333.
DAILY_ADS_BUDGET_TARGET_MXN = 333.0

# CPA máximo permitido antes de que el agente considere una keyword como desperdicio
# Se combina con KEYWORD_MIN_SPEND_TO_BLOCK
KEYWORD_MAX_CPA_TO_BLOCK = 0  # 0 = solo bloquear con 0 conversiones

# Número de keywords que se pueden bloquear en un solo ciclo sin pedir aprobación
# Si hay más candidatos, se agrupan y se proponen para aprobación
KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE = 1

# ============================================================================
# CPA TARGETS Y THRESHOLDS POR TIPO DE CAMPAÑA
# Valores alineados con CLAUDE.md (CPA Targets — Thai Thai).
# El clasificador usa estos valores en lugar de un umbral global.
# ============================================================================

CAMPAIGN_TYPE_CONFIG = {
    "delivery": {
        "cpa_ideal":          25.0,   # CPA ideal — campaña sana
        "cpa_max":            45.0,   # CPA máximo tolerable
        "cpa_critical":       80.0,   # CPA crítico — escalar urgente
        "min_spend_to_block": 70.0,   # Gasto mínimo para bloqueo automático
        # AG1: delivery tiene volumen alto y ROI esperado rápido — actuar antes
        "ag1_min_spend":           100.0,
        "ag1_min_clicks":          20,
        "ag1_min_days_protection": 14,
    },
    "reservaciones": {
        "cpa_ideal":          50.0,
        "cpa_max":            85.0,
        "cpa_critical":      120.0,
        "min_spend_to_block": 90.0,   # Más conservador — campaña en etapa temprana
        # AG1: reservaciones tiene bajo volumen y conversión de mayor valor — ser conservador
        # El CVR natural es menor; actuar demasiado pronto puede eliminar grupos que maduran lento
        "ag1_min_spend":           150.0,
        "ag1_min_clicks":          35,
        "ag1_min_days_protection": 30,  # Doble de protección — más tiempo de calentamiento
    },
    "local": {
        "cpa_ideal":          35.0,
        "cpa_max":            60.0,
        "cpa_critical":      100.0,
        "min_spend_to_block": 70.0,
        # AG1: igual al default — comportamiento intermedio sin razón para cambiar
        "ag1_min_spend":           120.0,
        "ag1_min_clicks":          25,
        "ag1_min_days_protection": 14,
    },
    "default": {
        "cpa_ideal":          35.0,
        "cpa_max":            60.0,
        "cpa_critical":      100.0,
        "min_spend_to_block": 70.0,   # Coincide con KEYWORD_MIN_SPEND_TO_BLOCK global
        # AG1: coincide con las constantes globales — fallback cuando el tipo no se resuelve
        "ag1_min_spend":           120.0,
        "ag1_min_clicks":          25,
        "ag1_min_days_protection": 14,
    },
}

# Mapeo explícito por campaign_id — permite override sin depender del nombre.
# Usar cuando dos campañas tienen nombres similares o cuando el nombre cambie.
# Formato: {"campaign_id_string": "tipo"}
# Ejemplo: {"22612348265": "local", "22839241090": "delivery"}
CAMPAIGN_ID_TYPE_MAP: dict = {
    # Dejar vacío por ahora. El clasificador cae al match por nombre si no hay entrada aquí.
    # "22612348265": "local",
    # "22839241090": "delivery",
}

# ============================================================================
# FASE SMALL MODE: CLASIFICACIÓN FUNCIONAL DINÁMICA
# Base estructural para cuentas pequeñas. En Fase 1 NO cambia la ejecución real;
# solo deja lista la capa de clasificación y etiquetado preparatorio.
# ============================================================================

SMALL_MODE_ENABLED = _os.getenv("SMALL_MODE_ENABLED", "true").lower() == "true"

SMALL_MODE_CONFIDENCE_MIN = 0.70
SMALL_MODE_CONFIDENCE_GAP_MIN = 0.15
SMALL_MODE_SHORT_WINDOW_DAYS = 7
SMALL_MODE_LONG_WINDOW_DAYS = 28
SMALL_MODE_COOLDOWN_HOURS = 48

SMALL_MODE_MAX_SCALE_PCT = 10.0
SMALL_MODE_MAX_REDUCE_PCT = 10.0
SMALL_MODE_MAX_REDUCE_LOCAL_PCT = 8.0
SMALL_MODE_MAX_SCALE_EXPERIENCE_PCT = 8.0
SMALL_MODE_MAX_REDUCE_EXPERIENCE_PCT = 8.0
SMALL_MODE_MIN_POSITIVE_SIGNALS = 2

SMALL_MODE_ENTRY_MAX_CONVERSIONS = 3
SMALL_MODE_ENTRY_MAX_CLICKS = 120
SMALL_MODE_ENTRY_MIN_COST_RATIO = 0.70

SMALL_MODE_ROLLBACK_CPA_WORSEN_PCT = 25.0
SMALL_MODE_ROLLBACK_CVR_DROP_PCT = 20.0
SMALL_MODE_ROLLBACK_COST_INCREASE_PCT = 15.0

SMALL_MODE_DECISION_PRIORITY = {
    "no_action_risk": 1,
    "hold": 2,
    "rollback_micro": 3,
    "reduce_micro": 4,
    "scale_micro": 5,
    "add_keywords_small": 5,
}

SMALL_MODE_CATEGORY_LIMITS = {
    "local_visit": {
        "scale_pct": SMALL_MODE_MAX_SCALE_PCT,
        "reduce_pct": SMALL_MODE_MAX_REDUCE_LOCAL_PCT,
    },
    "delivery_order": {
        "scale_pct": SMALL_MODE_MAX_SCALE_PCT,
        "reduce_pct": SMALL_MODE_MAX_REDUCE_PCT,
    },
    "reservation_intent": {
        "scale_pct": SMALL_MODE_MAX_SCALE_PCT,
        "reduce_pct": SMALL_MODE_MAX_REDUCE_PCT,
    },
    "experience_discovery": {
        "scale_pct": SMALL_MODE_MAX_SCALE_EXPERIENCE_PCT,
        "reduce_pct": SMALL_MODE_MAX_REDUCE_EXPERIENCE_PCT,
    },
    "generic_search": {
        "scale_pct": 0.0,
        "reduce_pct": 0.0,
    },
    "unknown_safe": {
        "scale_pct": 0.0,
        "reduce_pct": 0.0,
    },
}

FUNCTIONAL_CATEGORY_DEFAULT = "unknown_safe"
FUNCTIONAL_CATEGORIES = (
    "local_visit",
    "delivery_order",
    "reservation_intent",
    "experience_discovery",
    "generic_search",
    "unknown_safe",
)

# Señales compactas para clasificación dinámica.
# Fase 1 usa principalmente nombre + channel type si existe; otras señales quedan
# soportadas de forma opcional para fases posteriores sin romper la estructura.
FUNCTIONAL_CATEGORY_SIGNALS = {
    "local_visit": {
        "name_keywords": ("local", "maps", "ubicacion", "cómo llegar", "como llegar", "visita"),
        "required_channel_types": (),
        "default_weight": 0.80,
    },
    "delivery_order": {
        "name_keywords": ("delivery", "domicilio", "pedir", "pedido", "gloria food", "online"),
        "required_channel_types": (),
        "default_weight": 0.95,
    },
    "reservation_intent": {
        "name_keywords": ("reserva", "reservaciones", "booking", "book", "mesa"),
        "required_channel_types": ("SEARCH",),
        "default_weight": 1.00,
    },
    "experience_discovery": {
        "name_keywords": ("experiencia", "experience", "brand", "descubre", "thai"),
        "required_channel_types": ("SEARCH",),
        "default_weight": 0.70,
    },
    "generic_search": {
        "name_keywords": (),
        "required_channel_types": ("SEARCH",),
        "default_weight": 0.72,
    },
}

# ============================================================================
# PROTECCIÓN DE FASE DE APRENDIZAJE
# ============================================================================

# Días mínimos que debe llevar una campaña activa antes de permitir ejecución automática
# Las campañas más nuevas se tratan como en aprendizaje
CAMPAIGN_MIN_DAYS_BEFORE_AUTO_ACTION = 14

# Señal que indica que una campaña está en aprendizaje (string en el status de Google Ads)
# El agente revisa este estado antes de actuar
LEARNING_PHASE_STATUS_SIGNALS = ["LEARNING", "aprendizaje", "learning"]

# ============================================================================
# KEYWORDS ESTRATÉGICAS PROTEGIDAS
# Estas keywords nunca se bloquean automáticamente aunque tengan gasto sin conversiones.
# El agente puede proponer su revisión, pero no ejecutar.
# ============================================================================

PROTECTED_KEYWORDS = []
# Hugo decidió que el agente sea 100% autónomo en keywords.
# Si necesita proteger alguna en el futuro, agregarla aquí.

# ============================================================================
# CAMPAÑAS PROTEGIDAS
# Estas campañas no reciben acciones automáticas de ningún tipo.
# Solo se puede proponer cambios para aprobación.
# ============================================================================

PROTECTED_CAMPAIGN_NAMES = [
    # Lista vacía por ahora — se agrega por nombre parcial (case-insensitive)
    # Ejemplo: "reservaciones" protegería "Thai Mérida - Reservaciones"
]

PROTECTED_CAMPAIGN_IDS = [
    # Lista vacía por ahora — se agrega el ID de campaña como string
    # Ejemplo: "22612348265"
]

# ============================================================================
# CLASIFICACIÓN DE URGENCIA
# ============================================================================

# Umbral de caída de conversiones (%) en una semana para disparar urgencia crítica
CONVERSION_DROP_CRITICAL_PCT = 70

# Umbral de gasto anormal (multiplicador del promedio semanal) para urgencia crítica
SPEND_ANOMALY_MULTIPLIER_CRITICAL = 2.5

# ============================================================================
# VENTANA DE EVIDENCIA
# ============================================================================

# Días de datos necesarios para que una señal sea considerada "suficiente" para actuar
EVIDENCE_WINDOW_DAYS = 7

# Mínimo de impresiones para que una keyword tenga evidencia suficiente
KEYWORD_MIN_IMPRESSIONS_FOR_EVIDENCE = 100

# ============================================================================
# COMPORTAMIENTO DE PROPUESTAS
# ============================================================================

# Máximo de propuestas que se pueden incluir en un correo de aprobación
MAX_PROPOSALS_PER_EMAIL = 3

# Horas de vigencia de una propuesta antes de que expire automáticamente (postponed)
PROPOSAL_EXPIRY_HOURS = 72

# ============================================================================
# FASE 3A: TRACKING CRÍTICO — THRESHOLDS DE DETECCIÓN
#
# El agente compara métricas de la semana actual vs la semana anterior a nivel
# de cuenta completa. Si detecta señales de problema, envía una alerta
# automáticamente (RISK_EXECUTE = enviar alerta, NO mutar Google Ads).
# ============================================================================

# Clicks mínimos en la semana actual para que una campaña cuente en señales A y B.
# Evita ruido de campañas con tráfico casi nulo.
TRACKING_MIN_CLICKS_FOR_SIGNAL = 10

# Caída porcentual de CVR (0.0–1.0) para activar Señal A.
# 0.70 = 70 % de caída en tasa de conversión semana sobre semana.
TRACKING_CVR_DROP_THRESHOLD = 0.70

# Número mínimo de campañas afectadas para que la señal sea global (A y B).
# Si solo una campaña muestra el problema, se clasifica como ruido, no falla global.
TRACKING_MIN_CAMPAIGNS_AFFECTED = 2

# Horas mínimas entre alertas de tracking del mismo tipo (de-duplicación).
# Evita inundar el correo si el agente corre cada hora.
TRACKING_ALERT_DEDUP_HOURS = 24

# Clicks mínimos totales en la cuenta para activar Señal C.
# Condición de volumen: si hay < N clicks no es posible distinguir falla de tráfico bajo.
TRACKING_MIN_CLICKS_SIGNAL_C = 20

# ============================================================================
# FASE 3B: LANDING CHECKER — THRESHOLDS
#
# Checks basados en requests HTTP. Sin Playwright ni DOM inspection.
# El sitio es SPA Vite+React — los CTAs no existen en el HTML estático,
# por lo que S3_CTA_MISSING está excluido de este MVP.
#
# Señales implementadas:
#   S1_DOWN        — landing no carga / status incorrecto (≥2 de 3 intentos)
#   S2_SLOW        — tiempo de respuesta > umbral (warn o critical)
#   S4_LINK_BROKEN — enlace Gloria Food no accesible (HEAD + fallback GET)
#
# Solo se envía email para severidad 'critical'. 'warning' se registra
# en SQLite y en el response pero no genera correo.
# ============================================================================

# URL de la landing principal
LANDING_URL = "https://thaithaimerida.com"

# URL del flujo de pedidos (Gloria Food) — se verifica con HEAD + fallback GET
LANDING_CONVERSION_URL = "https://www.restaurantlogin.com/api/fb/_y5_p1_j"

# Tiempo de respuesta (segundos) a partir del cual se dispara S2 con severidad warning
LANDING_TIMEOUT_WARN_S = 8.0

# Tiempo de respuesta (segundos) a partir del cual S2 se convierte en critical
LANDING_TIMEOUT_CRITICAL_S = 20.0

# Número de intentos antes de confirmar S1_DOWN
LANDING_RETRY_COUNT = 3

# Segundos de espera entre reintentos de S1.
# Sobrescribible vía variable de entorno para desarrollo sin tocar producción:
#   set LANDING_RETRY_DELAY_S=1    (PowerShell/cmd — dev local)
#   export LANDING_RETRY_DELAY_S=1 (bash)
# En Cloud Run sin la variable → usa el default de producción (15s).
LANDING_RETRY_DELAY_S = float(_os.getenv("LANDING_RETRY_DELAY_S", "15"))

# Horas mínimas entre alertas de landing del mismo tipo (de-duplicación).
# Más corto que tracking (4h vs 24h) porque landing caída tiene impacto inmediato.
LANDING_ALERT_DEDUP_HOURS = 4

# Status codes HTTP considerados "up" para la landing
LANDING_OK_STATUS_CODES = [200, 301, 302]

# ============================================================================
# CONFIGURACIÓN EMAIL — SMTP Gmail (Fase 2)
# Requiere una App Password de Gmail (no la contraseña normal).
# Generarla en: Google Account → Seguridad → Contraseñas de aplicación
# Setear en el entorno como GMAIL_APP_PASSWORD (16 chars sin espacios).
# ============================================================================

EMAIL_SMTP_HOST  = "smtp.gmail.com"
EMAIL_SMTP_PORT  = 587                                    # STARTTLS
EMAIL_FROM       = "administracion@thaithaimerida.com.mx"
EMAIL_FROM_NAME  = "Thai Thai Ads Agent"
EMAIL_TO         = _os.getenv("EMAIL_TO", "administracion@thaithaimerida.com.mx")

# App Password — solo desde variable de entorno, nunca hardcodeado
GMAIL_APP_PASSWORD = _os.getenv("GMAIL_APP_PASSWORD", "")

# ============================================================================
# FASE 4: DETECTOR DE AD GROUPS CON BAJA EFICIENCIA
#
# MVP: solo Señal AG1 — gasto relevante con cero conversiones.
# AG2 (CPA relativo) y AG3 (CTR bajo) quedan fuera de este MVP.
# No hay autoejecución en esta fase — todo es RISK_PROPOSE.
# ============================================================================

# Ventana de análisis (días) — más amplia que keywords para reducir ruido semanal
ADGROUP_EVIDENCE_WINDOW_DAYS = 14

# Gasto mínimo (MXN) en el ad group para considerarlo candidato
# Umbral más alto que keywords porque un ad group agrupa varias keywords
ADGROUP_MIN_SPEND_TO_PROPOSE = 120.0

# Clicks mínimos en la ventana para que la señal AG1 sea válida
ADGROUP_MIN_CLICKS_FOR_SIGNAL = 25

# Máximo de propuestas de ad group que se generan en un ciclo
ADGROUP_MAX_PROPOSALS_PER_CYCLE = 2

# ============================================================================
# FASE 4B: PAUSA AUTOMÁTICA DE AD GROUPS VÍA API
#
# Interruptor explícito — default False si la variable de entorno no existe.
# Para activar: set ADGROUP_PAUSE_ENABLED=true (Cloud Run) o
#               export ADGROUP_PAUSE_ENABLED=true (bash local)
# ADGROUP_PAUSE_ALLOW_IDS queda solo como variable de entorno (no aquí)
# para facilitar el primer test controlado sin re-deploy.
# ============================================================================

# Si False, la aprobación queda registrada pero NO se ejecuta la pausa vía API.
ADGROUP_PAUSE_ENABLED = _os.getenv("ADGROUP_PAUSE_ENABLED", "false").lower() == "true"

# ============================================================================
# FASE 6B.1: EJECUCIÓN DE CAMBIOS DE PRESUPUESTO VÍA API
#
# Interruptor explícito — default False. Nunca activar sin haber verificado
# el flujo completo en dry-run primero.
#
# Para activar:
#   set BUDGET_CHANGE_ENABLED=true          (PowerShell/cmd)
#   export BUDGET_CHANGE_ENABLED=true       (bash)
#
# Para restringir a campañas específicas (primer test controlado):
#   set BUDGET_CHANGE_ALLOW_IDS=22839241090,22612348265
#   export BUDGET_CHANGE_ALLOW_IDS=22839241090
#   Lista vacía = sin restricción de ID (solo controlada por BUDGET_CHANGE_ENABLED).
#
# Flujo: aprobación → verify_budget_still_actionable() → update_campaign_budget() API
# NO hay autoejecución — requiere aprobación explícita del operador en cada caso.
# ============================================================================

# Kill switch: False por defecto. Solo desde variable de entorno.
BUDGET_CHANGE_ENABLED = _os.getenv("BUDGET_CHANGE_ENABLED", "false").lower() == "true"

# Whitelist de campaign_ids permitidos para ejecución real.
# Vacío = cualquier campaña permitida (una vez que BUDGET_CHANGE_ENABLED=true).
# Usar para el primer test controlado: BUDGET_CHANGE_ALLOW_IDS=<campaign_id>
_raw_allow_ids = _os.getenv("BUDGET_CHANGE_ALLOW_IDS", "")
BUDGET_CHANGE_ALLOW_IDS: set = {s.strip() for s in _raw_allow_ids.split(",") if s.strip()}

# Reducción máxima permitida en una sola ejecución (%).
# Evita cortes agresivos que dejan la campaña sin presupuesto para convertir.
BUDGET_CHANGE_MAX_REDUCTION_PCT = 60.0

# Presupuesto diario mínimo absoluto (MXN/día).
# No se ejecutará ningún cambio que deje el presupuesto por debajo de este valor.
BUDGET_CHANGE_MIN_DAILY_MXN = 20.0

# Tolerancia de deriva (G_drift): si el presupuesto actual ya bajó más de este %
# respecto al presupuesto registrado en la propuesta, bloquear ejecución.
# Protege contra doble corte cuando el operador ya hizo el cambio manualmente.
BUDGET_CHANGE_DRIFT_TOLERANCE_PCT = 0.10

# URL base para los links de aprobación en el correo
# En Cloud Run: https://thai-thai-ads-agent-624172071613.us-central1.run.app
# En local: http://localhost:8080
APPROVAL_BASE_URL = _os.getenv(
    "CLOUD_RUN_BASE_URL",
    "https://thai-thai-ads-agent-safxqpxa6q-uc.a.run.app",
)

# ============================================================================
# FASE GEO: AUDITORÍA DE GEOTARGETING
#
# Detecta campañas activas con segmentación geográfica incorrecta o ausente.
# GEO1 — campaña tiene al menos una ubicación NO permitida.
# GEO0 — campaña no tiene ninguna restricción geográfica explícita.
#
# Para activar la autocorrección vía API tras aprobación:
#   $env:GEO_AUTOFIX_ENABLED = "true"                 (PowerShell)
#   export GEO_AUTOFIX_ENABLED=true                   (bash)
#
# Para restringir a campañas específicas en el primer test controlado:
#   $env:GEO_AUTOFIX_ALLOW_IDS = "22839241090"        (PowerShell)
#   export GEO_AUTOFIX_ALLOW_IDS=22839241090          (bash)
# ============================================================================

# Habilita la auditoría de geotargeting en el ciclo de auditoría.
# Cambiar a False para deshabilitar completamente sin tocar código.
GEO_AUDIT_ENABLED = _os.getenv("GEO_AUDIT_ENABLED", "true").lower() == "true"

# Location IDs permitidos para Thai Thai.
# 1010182 = Ciudad Victoria, Tamaulipas, México — INCORRECTO, no usar.
# 1010205 = Mérida, Yucatán, México — ID correcto y único permitido.
#           Verificado 2026-03-27 via diag_geo_ids.py: canonical='Merida,Yucatan,Mexico'
_raw_geo_allowed = _os.getenv("GEO_ALLOWED_LOCATION_IDS", "1010205")
DEFAULT_ALLOWED_LOCATION_IDS: set = {s.strip() for s in _raw_geo_allowed.split(",") if s.strip()}

# Substring canónico que debe estar presente en el nombre que devuelve la API.
# Usado por _verify_geo_id_is_allowed() para bloquear IDs que no sean Mérida.
MERIDA_LOCATION_CANONICAL_CONTAINS: str = _os.getenv("MERIDA_LOCATION_CANONICAL_CONTAINS", "Merida")

# Kill switch para autocorrección vía API (default False — requiere aprobación + switch activo).
GEO_AUTOFIX_ENABLED = _os.getenv("GEO_AUTOFIX_ENABLED", "false").lower() == "true"

# ============================================================================
# FASE SMART CLEANUP: ELIMINACIÓN AUTÓNOMA DE TEMAS IRRELEVANTES
#
# Kill switch activo por defecto (True) — el análisis ya valida la guarda de
# SMART_THEME_MIN_REMAINING temas antes de ejecutar cualquier mutación.
#
# Flujo:
#   1. smart_campaign_auditor detecta SMART_KT1 (temas irrelevantes)
#   2. Si SMART_THEME_REMOVAL_ENABLED=True y quedan >= SMART_THEME_MIN_REMAINING
#      temas tras eliminar los basura → ejecuta remove_smart_campaign_theme()
#   3. Si la guarda falla → registra la detección sin ejecutar + alerta en correo
#
# Para desactivar temporalmente:
#   Cloud Run: SMART_THEME_REMOVAL_ENABLED=false
#   Local:     export SMART_THEME_REMOVAL_ENABLED=false
# ============================================================================
SMART_THEME_REMOVAL_ENABLED: bool = (
    _os.getenv("SMART_THEME_REMOVAL_ENABLED", "true").lower() == "true"
)
# Guarda de seguridad: mínimo de temas que deben quedar activos tras la limpieza.
# Si la campaña quedaría con menos de este número, NO se elimina nada.
SMART_THEME_MIN_REMAINING: int = int(_os.getenv("SMART_THEME_MIN_REMAINING", "5"))

# ============================================================================
# SMART CAMPAIGNS — EVALUACIÓN SEMÁNTICA DE TEMAS VÍA LLM
#
# Cuando está activo, los keyword themes que NO están en _IRRELEVANT_THEMES
# son enviados a Claude API (Haiku) para evaluación semántica en contexto.
# El LLM conoce que Thai Thai es un restaurante tailandés en Mérida, Yucatán,
# con servicios de Delivery (Gloria Food) y Reservaciones.
#
# Si la API de Anthropic falla, el agente continúa usando solo la lista estática.
# Esto garantiza que una falla de red no detenga la auditoría.
#
# Para desactivar:
#   Cloud Run: SMART_LLM_THEME_EVAL_ENABLED=false
# ============================================================================
SMART_LLM_THEME_EVAL_ENABLED: bool = (
    _os.getenv("SMART_LLM_THEME_EVAL_ENABLED", "true").lower() == "true"
)

# Whitelist de campaign_ids permitidos para autocorrección real.
# Vacío = cualquier campaña permitida (una vez que GEO_AUTOFIX_ENABLED=true).
_raw_geo_allow_ids = _os.getenv("GEO_AUTOFIX_ALLOW_IDS", "")
GEO_AUTOFIX_ALLOW_IDS: set = {s.strip() for s in _raw_geo_allow_ids.split(",") if s.strip()}

# Tipos de campaña excluidos de la auditoría geo (la API no permite mutar sus criterios geo).
GEO_EXCLUDED_CHANNEL_TYPES: set = {"PERFORMANCE_MAX", "LOCAL_SERVICES"}

# ── Centro geográfico de Mérida (centro histórico — referencia general) ──────
MERIDA_CENTER_LAT: float = 20.9674
MERIDA_CENTER_LNG: float = -89.5926

# ── Ubicación física del restaurante Thai Thai ────────────────────────────────
# Dirección: Calle 30 No. 351, Col. Emiliano Zapata Norte, Mérida, Yucatán
# Fuente: Google Maps + Wanderlog (verificado 2026-03-27)
# Diferencia vs centro histórico: ~5.05 km al noroeste.
# Para PROXIMITY de delivery, este es el centro correcto — no el centro de la ciudad.
THAI_THAI_RESTAURANT_LAT: float = 21.008815
THAI_THAI_RESTAURANT_LNG: float = -89.612673
THAI_THAI_RESTAURANT_ADDRESS: str = "Calle 30 No. 351, Col. Emiliano Zapata Norte, Mérida, Yucatán"

# ── Políticas GEO por objetivo de negocio ────────────────────────────────────
# Pregunta guía: "¿Esta campaña busca que el cliente visite el restaurante
#                 o que el restaurante llegue al cliente?"
#   → DELIVERY:       el restaurante llega al cliente → PROXIMITY radio corto
#   → RESERVACIONES:  el cliente llega al restaurante → LOCATION ciudad
#
# Campos por política:
#   expected_targeting_type   : "PROXIMITY" | "LOCATION" | None (sin política definida)
#   max_radius_km             : radio máximo permitido para PROXIMITY (None si no aplica)
#   expected_center_lat/lng   : centro esperado para validar PROXIMITY
#   expected_center_mode      : "exact_business_address" — el centro debe ser la dirección
#                               real del negocio, no un punto genérico de la ciudad
#   expected_center_address   : dirección legible del centro esperado (para logs y reportes)
#   allowed_location_ids      : set de IDs válidos para política LOCATION
#   ui_validation_required    : True para campañas SMART donde Express UI puede diferir del API
#   autofix_allowed           : False si no hay política clara — nunca autofix sin política
#   description               : descripción legible del objetivo
GEO_OBJECTIVE_POLICIES: dict = {
    "DELIVERY": {
        "objective_type":          "DELIVERY",
        "expected_targeting_type": "PROXIMITY",
        "max_radius_km":           8.0,
        "expected_center_lat":     THAI_THAI_RESTAURANT_LAT,
        "expected_center_lng":     THAI_THAI_RESTAURANT_LNG,
        "expected_center_mode":    "exact_business_address",
        "expected_center_address": THAI_THAI_RESTAURANT_ADDRESS,
        "allowed_location_ids":    set(),
        "ui_validation_required":  False,
        "autofix_allowed":         True,
        "description":             "Delivery: pedidos con entrega — PROXIMITY radio ≤8 km centrado en el restaurante (Calle 30 #351, Emiliano Zapata Norte)",
    },
    "RESERVACIONES": {
        "objective_type":          "RESERVACIONES",
        "expected_targeting_type": "LOCATION",
        "max_radius_km":           None,
        "expected_center_lat":     None,
        "expected_center_lng":     None,
        "allowed_location_ids":    {"1010205"},
        "ui_validation_required":  False,
        "autofix_allowed":         True,
        "description":             "Reservaciones: visitas al restaurante — LOCATION 1010205 (Mérida, Yucatán)",
    },
    "LOCAL_DISCOVERY": {
        "objective_type":          "LOCAL_DISCOVERY",
        # Acepta LOCATION 1010205 o PROXIMITY centrado en el restaurante con
        # radio suficiente para cobertura funcional de Mérida.
        # Equivalencia funcional aprobada: el objetivo es descubrimiento local —
        # no importa el mecanismo técnico siempre que cubra la ciudad.
        "expected_targeting_type": "LOCATION_OR_PROXIMITY",
        "max_radius_km":           50.0,   # techo: evitar targeting de todo Yucatán
        "min_radius_km":           15.0,   # piso: cobertura mínima funcional de Mérida (ajustado desde 10km)
        "expected_center_lat":     THAI_THAI_RESTAURANT_LAT,
        "expected_center_lng":     THAI_THAI_RESTAURANT_LNG,
        "expected_center_mode":    "exact_business_address",
        "expected_center_address": THAI_THAI_RESTAURANT_ADDRESS,
        "allowed_location_ids":    {"1010205"},
        # SMART campaign: Express UI controla el geo real.
        # ui_validation_required=True — api_state no es fuente de verdad final.
        # autofix_allowed=False — correcciones en SMART requieren validación humana.
        "ui_validation_required":  True,
        "autofix_allowed":         False,
        "description":             "Local/Visitas: atraer personas de Mérida — acepta LOCATION 1010205 o PROXIMITY (10–50 km centrado en restaurante). Equivalencia funcional aprobada para objetivo de descubrimiento local.",
    },
    "OTRO": {
        "objective_type":          "OTRO",
        "expected_targeting_type": None,
        "max_radius_km":           None,
        "expected_center_lat":     None,
        "expected_center_lng":     None,
        "allowed_location_ids":    set(),
        "ui_validation_required":  True,
        "autofix_allowed":         False,
        "description":             "Objetivo no clasificado — requiere definición explícita antes de cualquier acción",
    },
}

# ── Mapeo de campañas a su objetivo de negocio ────────────────────────────────
# Actualizar cuando se agreguen o reclasifiquen campañas.
CAMPAIGN_GEO_OBJECTIVES: dict = {
    "22839241090": "DELIVERY",        # Thai Mérida - Delivery
    "23680871468": "RESERVACIONES",   # Thai Mérida - Reservaciones
    "22612348265": "LOCAL_DISCOVERY", # Thai Mérida - Local (objetivo por confirmar)
    "23730364039": "LOCAL_DISCOVERY", # Thai Mérida - Experiencia 2026 (radio 15km restaurante)
}

# Horas mínimas entre alertas de geo del mismo tipo (de-duplicación).
GEO_ALERT_DEDUP_HOURS = 72

# ============================================================================
# FASE 6A: SALUD DE CAMPAÑAS (Campaign Health)
#
# MVP: CH1 (CPA crítico) + CH3 (campaña sin conversiones con gasto relevante).
# CH2 (caída de CVR semana a semana) se implementa en Fase 6A.1.
# No hay autoejecución — todo es RISK_PROPOSE, capa de observación pura.
# ============================================================================

# ============================================================================
# CAMPAÑAS A PAUSAR EN CADA CICLO DE AUDITORÍA
# {campaign_id: campaign_name} — el agente las pausa si están ENABLED.
# Dejar vacío {} para no pausar ninguna.
# ============================================================================
CAMPAIGNS_TO_PAUSE: dict = {
    # "23680871468": "Thai Mérida - Reservaciones",  # Desactivado 2026-04-10 — Hugo la reactivó
}

CAMPAIGN_HEALTH_CONFIG = {
    # CH1: CPA real de la campaña supera el umbral crítico por tipo.
    # El cpa_critical de cada tipo se toma de CAMPAIGN_TYPE_CONFIG.
    "ch1": {
        "min_conversions_for_cpa": 2,    # Con < 2 conv el CPA es matemáticamente inestable
        "evidence_window_days": 14,
    },
    # CH3: Campaña con 0 conversiones y gasto relevante en la ventana.
    # Thresholds más altos que AG1 porque agrupa varios ad grupos.
    # Reservaciones: umbral conservador y protección doble (30 días, igual que AG1).
    "ch3": {
        "evidence_window_days": 14,
        "by_type": {
            "delivery":      {"min_spend": 300.0, "min_days_active": 14},
            "reservaciones": {"min_spend": 450.0, "min_days_active": 30},
            "local":         {"min_spend": 350.0, "min_days_active": 14},
            "default":       {"min_spend": 350.0, "min_days_active": 14},
        },
    },
    # BA1: CPA crítico con gasto relevante en ventana — propone reducción de presupuesto.
    # Guarda de gasto mínimo: evita proponer cambios de presupuesto con evidencia escasa.
    # Reservaciones: umbral conservador — menor volumen, conversiones de mayor valor.
    # No hay autoejecución — la aprobación registra; el operador hace el cambio en Google Ads.
    # Silencio post-aprobación: técnica 6B.1 pendiente — sin re-propuesta hasta próximo ciclo.
    "ba1": {
        "evidence_window_days": 14,
        "min_conversions": 2,            # Con < 2 conv el CPA es matemáticamente inestable
        "budget_floor_pct": 0.30,        # No sugerir por debajo del 30% del presupuesto actual
        "by_type": {
            "delivery":      {"min_spend_window": 200.0, "min_days_active": 14},
            "reservaciones": {"min_spend_window": 350.0, "min_days_active": 30},
            "local":         {"min_spend_window": 250.0, "min_days_active": 14},
            "default":       {"min_spend_window": 250.0, "min_days_active": 14},
        },
    },
    # BA2: Campaña con CPA ideal + presupuesto saturado → propone escalar inversión.
    # "Pisar el acelerador": detecta campañas que ya probaron ser rentables y están
    # limitadas por presupuesto (utilization_rate >= umbral), no por falta de demanda.
    #
    # Dos sub-señales:
    #   BA2_REALLOC — escalar usando fondos liberados por BA1 (costo neto = $0)
    #   BA2_SCALE   — escalar requiriendo nueva inversión (requiere aprobación explícita)
    #
    # Guardrails:
    #   - min_days_active: campaña suficientemente madura (evita escalar en periodo de aprendizaje)
    #   - min_conversions: evidencia estadística mínima de rentabilidad
    #   - utilization_threshold: proxy de saturación (cost_period / budget_period)
    #   - max_scale_pct: límite de escala para evitar saltos bruscos
    #   - max_scale_abs_mxn: techo absoluto por propuesta en MXN
    "ba2": {
        "evidence_window_days": 14,
        "min_conversions": 3,            # Más exigente que BA1 — solo escalar con evidencia sólida
        "utilization_threshold": 0.85,   # >= 85% del presupuesto período = limitado por budget
        "max_scale_pct": 0.30,           # Máximo +30% del presupuesto actual por propuesta
        "max_scale_abs_mxn": 80.0,       # Techo absoluto diario (+$80 MXN/día máximo)
        "by_type": {
            "delivery":      {"min_days_active": 14},
            "reservaciones": {"min_days_active": 30},
            "local":         {"min_days_active": 14},
            "default":       {"min_days_active": 14},
        },
    },
}
