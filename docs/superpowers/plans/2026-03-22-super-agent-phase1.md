# Super Agent Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Thai Thai Ads Agent from GPT-4o-mini to Claude Sonnet 4.6 as the AI brain, connect the existing memory system and GA4 client to the analysis loop, add Google Sheets business data, and add a landing page auditor — all feeding into a unified analysis context.

**Architecture:** Replace `_call_openai_analysis()` in `engine/analyzer.py` with a new `_call_claude_analysis()` function using the Anthropic SDK. Expand `engine/prompt.py` to 500+ lines with full business context. Add `engine/sheets_client.py` for Google Sheets data. Add `engine/landing_page_auditor.py` for code + GA4 correlation. Wire all data sources into `analyze_campaign_data()`.

**Tech Stack:** Python 3.x, FastAPI, Anthropic SDK (`anthropic`), gspread, SQLite (existing), Google Ads API v23, GA4 Data API (existing)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add anthropic, gspread |
| Modify | `engine/analyzer.py` | Replace OpenAI call with Claude, wire all data sources |
| Modify | `engine/prompt.py` | Expand from 77 → 500+ lines with business DNA |
| Create | `engine/sheets_client.py` | Fetch comensales, ingresos, gastos from Google Sheets |
| Create | `engine/landing_page_auditor.py` | Audit landing page code + GA4 correlation |
| Create | `tests/test_sheets_client.py` | Unit tests for sheets client |
| Create | `tests/test_landing_page_auditor.py` | Unit tests for landing page auditor |
| Create | `tests/test_claude_analyzer.py` | Unit tests for Claude analyzer |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add anthropic and gspread to requirements.txt**

Open `requirements.txt` and add after existing lines:
```
anthropic>=0.40.0
gspread>=6.0.0
google-auth>=2.0.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install anthropic gspread google-auth
```

Expected output: Successfully installed anthropic-X.X.X gspread-X.X.X

- [ ] **Step 3: Verify import works**

```bash
python -c "import anthropic; print('OK', anthropic.__version__)"
```

Expected: `OK 0.4x.x`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add anthropic and gspread dependencies"
```

---

## Task 2: Google Sheets Client

**Files:**
- Create: `engine/sheets_client.py`
- Create: `tests/test_sheets_client.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_sheets_client.py`:

```python
import sys
sys.path.insert(0, ".")
from unittest.mock import patch, MagicMock
from engine.sheets_client import parse_diario_sheet, parse_canales_sheet

def test_parse_diario_sheet_returns_required_keys():
    mock_rows = [
        ["Fecha", "Comensales_Real", "Comensales_Obj_Ventas", "Comensales_Obj_Equilibrio", "Ingresos_Bruto", "Ingresos_Neto"],
        ["2026-03-17", "45", "60", "35", "9000", "7500"],
        ["2026-03-18", "38", "60", "35", "7600", "6200"],
    ]
    result = parse_diario_sheet(mock_rows)
    assert len(result) == 2
    assert result[0]["comensales_real"] == 45
    assert result[0]["ingresos_bruto"] == 9000.0
    assert result[0]["sobre_equilibrio"] is True

def test_parse_diario_empty_rows():
    result = parse_diario_sheet([["Fecha", "Comensales_Real"]])
    assert result == []

def test_parse_canales_sheet_returns_totals():
    mock_rows = [
        ["Fecha", "Terminal_POS", "Plataforma_Delivery", "Efectivo", "Transferencia"],
        ["2026-03-17", "5000", "2000", "1000", "500"],
    ]
    result = parse_canales_sheet(mock_rows)
    assert result[0]["terminal_pos"] == 5000.0
    assert result[0]["plataforma_delivery"] == 2000.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_sheets_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.sheets_client'`

- [ ] **Step 3: Create engine/sheets_client.py**

```python
"""
Google Sheets Client — Thai Thai Business Data
Fetches real business data: comensales, ingresos, gastos, canales de venta.
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional


def _safe_float(val) -> float:
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    return int(_safe_float(val))


def parse_diario_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses the Diario sheet rows into structured dicts.
    Expects header row first, then data rows.
    Columns: Fecha | Comensales_Real | Comensales_Obj_Ventas | Comensales_Obj_Equilibrio | Ingresos_Bruto | Ingresos_Neto
    """
    if len(rows) < 2:
        return []

    result = []
    for row in rows[1:]:  # skip header
        if not row or not row[0]:
            continue
        comensales_real = _safe_int(row[1]) if len(row) > 1 else 0
        obj_ventas = _safe_int(row[2]) if len(row) > 2 else 0
        obj_equilibrio = _safe_int(row[3]) if len(row) > 3 else 0
        ingresos_bruto = _safe_float(row[4]) if len(row) > 4 else 0.0
        ingresos_neto = _safe_float(row[5]) if len(row) > 5 else 0.0

        result.append({
            "fecha": str(row[0]),
            "comensales_real": comensales_real,
            "obj_ventas": obj_ventas,
            "obj_equilibrio": obj_equilibrio,
            "ingresos_bruto": ingresos_bruto,
            "ingresos_neto": ingresos_neto,
            "sobre_equilibrio": comensales_real >= obj_equilibrio,
            "sobre_objetivo_ventas": comensales_real >= obj_ventas,
        })
    return result


def parse_canales_sheet(rows: List[List]) -> List[Dict]:
    """
    Parses Canales sheet.
    Columns: Fecha | Terminal_POS | Plataforma_Delivery | Efectivo | Transferencia
    """
    if len(rows) < 2:
        return []

    result = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        result.append({
            "fecha": str(row[0]),
            "terminal_pos": _safe_float(row[1]) if len(row) > 1 else 0.0,
            "plataforma_delivery": _safe_float(row[2]) if len(row) > 2 else 0.0,
            "efectivo": _safe_float(row[3]) if len(row) > 3 else 0.0,
            "transferencia": _safe_float(row[4]) if len(row) > 4 else 0.0,
        })
    return result


def fetch_sheets_data(days: int = 7) -> Dict:
    """
    Main entry point. Returns aggregated business data from Google Sheets.
    Falls back to empty dict if credentials or spreadsheet not configured.
    """
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "./ga4-credentials.json")

    if not spreadsheet_id or not os.path.exists(credentials_path):
        print("[SHEETS] Credenciales o spreadsheet no configurados. Saltando.")
        return {}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        # Fetch Diario sheet
        diario_rows = []
        canales_rows = []
        try:
            diario_ws = sh.worksheet("Diario")
            diario_rows = diario_ws.get_all_values()
        except Exception:
            try:
                diario_ws = sh.get_worksheet(0)
                diario_rows = diario_ws.get_all_values()
            except Exception as e:
                print(f"[SHEETS] No se pudo leer hoja Diario: {e}")

        try:
            canales_ws = sh.worksheet("Canales")
            canales_rows = canales_ws.get_all_values()
        except Exception:
            pass  # Optional sheet

        diario_data = parse_diario_sheet(diario_rows)
        canales_data = parse_canales_sheet(canales_rows)

        # Aggregate last N days
        cutoff = datetime.now() - timedelta(days=days)
        recent_diario = diario_data[-days:] if diario_data else []
        recent_canales = canales_data[-days:] if canales_data else []

        if not recent_diario:
            return {}

        total_comensales = sum(r["comensales_real"] for r in recent_diario)
        total_ingresos_bruto = sum(r["ingresos_bruto"] for r in recent_diario)
        total_ingresos_neto = sum(r["ingresos_neto"] for r in recent_diario)
        dias_sobre_equilibrio = sum(1 for r in recent_diario if r["sobre_equilibrio"])
        dias_sobre_ventas = sum(1 for r in recent_diario if r["sobre_objetivo_ventas"])
        promedio_comensales = round(total_comensales / len(recent_diario), 1)

        # Last day for reference
        last = recent_diario[-1]

        return {
            "periodo_dias": len(recent_diario),
            "total_comensales": total_comensales,
            "promedio_comensales_diario": promedio_comensales,
            "total_ingresos_bruto": round(total_ingresos_bruto, 2),
            "total_ingresos_neto": round(total_ingresos_neto, 2),
            "dias_sobre_equilibrio": dias_sobre_equilibrio,
            "dias_sobre_objetivo_ventas": dias_sobre_ventas,
            "ultimo_dia": last,
            "canales": recent_canales[-1] if recent_canales else {},
        }

    except Exception as e:
        print(f"[SHEETS] Error inesperado: {e}")
        return {}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_sheets_client.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add engine/sheets_client.py tests/test_sheets_client.py
git commit -m "feat: add Google Sheets business data client"
```

---

## Task 3: Landing Page Auditor

**Files:**
- Create: `engine/landing_page_auditor.py`
- Create: `tests/test_landing_page_auditor.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_landing_page_auditor.py`:

```python
import sys
sys.path.insert(0, ".")
from engine.landing_page_auditor import compute_friction_score, audit_landing_page_code

def test_friction_score_good():
    # CTR 2%, conv 3% → no friction
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=3.0)
    assert score["status"] == "good"
    assert score["score"] >= 80

def test_friction_score_warning():
    # CTR 2%, conv 0.8% → warning
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=0.8)
    assert score["status"] == "warning"

def test_friction_score_critical():
    # CTR 2%, conv 0.3% → critical
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=0.3)
    assert score["status"] == "critical"

def test_audit_landing_page_code_returns_dict():
    result = audit_landing_page_code()
    assert isinstance(result, dict)
    assert "issues" in result
    assert "score" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_landing_page_auditor.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create engine/landing_page_auditor.py**

```python
"""
Landing Page Auditor — Thai Thai
Analyzes landing page code structure and correlates with GA4 metrics.
Landing page project path: C:/Users/usuario/Downloads/thai-thai web
"""
import os
import json
from typing import Dict, List

LANDING_PAGE_PATH = os.getenv(
    "LANDING_PAGE_PATH",
    "C:/Users/usuario/Downloads/thai-thai web"
)


def compute_friction_score(ctr_pct: float, conversion_rate_pct: float) -> Dict:
    """
    Computes landing page friction based on CTR vs conversion rate gap.

    Thresholds (from spec):
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
        action = "Auditar posición del CTA y velocidad de carga en móvil"
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

    # Check 1: ReservationModal exists and has form
    modal_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "ReservationModal.jsx")
    if os.path.exists(modal_path):
        with open(modal_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "handleSubmit" not in content:
            issues.append("ReservationModal no tiene manejador de envío")
            score -= 20
        if "trackConversion" not in content:
            issues.append("ReservationModal no llama trackConversion — conversiones no rastreadas")
            score -= 15
    else:
        issues.append("ReservationModal.jsx no encontrado")
        score -= 30

    # Check 2: Analytics utility exists
    analytics_path = os.path.join(LANDING_PAGE_PATH, "src", "utils", "analytics.js")
    if not os.path.exists(analytics_path):
        issues.append("utils/analytics.js no encontrado — tracking puede estar roto")
        score -= 20

    # Check 3: HeroSection has CTA above fold
    hero_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "HeroSection.jsx")
    if os.path.exists(hero_path):
        with open(hero_path, "r", encoding="utf-8") as f:
            hero_content = f.read()
        if "reserva" not in hero_content.lower() and "pedir" not in hero_content.lower():
            issues.append("HeroSection posiblemente no tiene CTA de reserva/pedido visible")
            score -= 10

    # Check 4: Mobile sticky bar exists
    sticky_path = os.path.join(LANDING_PAGE_PATH, "src", "components", "MobileStickyBar.jsx")
    if not os.path.exists(sticky_path):
        issues.append("No existe barra sticky para móvil — CTA difícil de encontrar en celular")
        score -= 15

    # Check 5: BACKEND_URL hardcoded to localhost (production issue)
    if os.path.exists(modal_path):
        with open(modal_path, "r", encoding="utf-8") as f:
            modal_content = f.read()
        if "localhost" in modal_content:
            issues.append("BACKEND_URL apunta a localhost — las reservas no funcionan en producción")
            score -= 25

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
        # Use click_reservar as proxy for ad-driven intent
        page_views = funnel.get("page_view", 0)
        reservas = funnel.get("reserva_completada", 0)
        clicks_reservar = funnel.get("click_reservar", 0)

        # Estimate CTR equivalent from landing traffic
        # We assume GA4 sessions ≈ ad clicks for this correlation
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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_landing_page_auditor.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add engine/landing_page_auditor.py tests/test_landing_page_auditor.py
git commit -m "feat: add landing page auditor with friction scoring"
```

---

## Task 4: Expand Master Prompt (500+ lines)

**Files:**
- Modify: `engine/prompt.py`

- [ ] **Step 1: Replace engine/prompt.py with expanded version**

Replace the entire content of `engine/prompt.py` with:

```python
THAI_THAI_ADS_MASTER_PROMPT = """
## IDENTIDAD Y ROL

Eres el Estratega Senior de Growth Marketing y Director de Performance Digital de Thai Thai Mérida.
Tu trabajo es maximizar el retorno real del negocio — no solo métricas de anuncios.
Tu análisis es clínico, basado en datos, orientado a resultados concretos en pesos mexicanos.
Hablas en español. Nunca usas jerga de marketing que el dueño no entienda.
Cada propuesta incluye: qué hacer, por qué, qué resultado esperar, qué pasa si no se hace.

---

## CONTEXTO DEL NEGOCIO

**Restaurante:** Thai Thai Mérida — cocina tailandesa auténtica
**Ubicación:** Calle 30 No. 351 Col. Emiliano Zapata Norte, Mérida, Yucatán
**Teléfono / WhatsApp restaurante:** +52 999 931 7457
**Servicios:** Comer en restaurante (local), delivery a domicilio, reservaciones para eventos
**Temporada alta Mérida:** Noviembre–Abril (turismo), Diciembre–Enero (fiestas)
**Temporada baja:** Mayo–Septiembre (calor extremo, menos turismo)
**Ticket promedio estimado:** $350–$500 MXN por persona
**Clientes objetivo:** Familias locales, turistas, parejas en cita, grupos corporativos

---

## CAMPAÑAS ACTIVAS

### 1. Thai Mérida - Local (ID: 22612348265)
- **Tipo:** Smart Campaign (Local)
- **Objetivo:** Visitas físicas al restaurante, llamadas, direcciones en Maps
- **Geo:** Ciudad de Mérida (radio ciudad completa)
- **Presupuesto:** $50 MXN/día
- **CPA Target ideal:** < $35 MXN | Máximo aceptable: $60 MXN | Crítico: > $100 MXN
- **Señal de éxito:** Clicks en "cómo llegar", llamadas al restaurante
- **Limitación técnica conocida:** Smart campaigns no aceptan bid modifiers via API

### 2. Thai Mérida - Delivery (ID: 22839241090)
- **Tipo:** Smart Campaign (Local)
- **Objetivo:** Pedidos a domicilio, tráfico a plataformas de delivery
- **Geo:** Radio 8km desde centro de Mérida (lat: 20.9674, lng: -89.5926)
- **Presupuesto:** $100 MXN/día
- **CPA Target ideal:** < $25 MXN | Máximo aceptable: $45 MXN | Crítico: > $80 MXN
- **Señal de éxito:** Clicks en plataformas delivery, llamadas para pedido
- **Nota:** CTR históricamente menor que Local — monitorear siempre

### 3. Thai Mérida - Reservaciones (ID: 23680871468)
- **Tipo:** Search Campaign (Manual CPC)
- **Objetivo:** Reservaciones completadas via formulario en landing page
- **Geo:** Radio 30km desde centro de Mérida
- **Presupuesto:** $70 MXN/día
- **CPA Target ideal:** < $50 MXN | Máximo aceptable: $85 MXN | Crítico: > $120 MXN
- **Señal de éxito:** Evento GA4 `reserva_completada`
- **Estado inicial:** Recién activada — requiere 2-3 semanas para estabilizar
- **Horario activo:** 6am-24h (42 slots de ad schedule configurados)

---

## REGLAS DE DECISIÓN

### Cuándo proponer escalar presupuesto:
- CPA < target ideal por 7+ días consecutivos
- Presupuesto se agota antes de las 20:00 hrs (impression share limitado por budget)
- Escalamiento máximo: 20% del presupuesto actual por semana
- NUNCA más de 30% en una sola semana

### Cuándo proponer pausar campaña:
- 0 conversiones en 7 días Y gasto > $200 MXN
- CPA > target crítico por 14 días consecutivos
- Siempre proponer, nunca pausar sin aprobación

### Cuándo proponer nueva campaña:
- Search term report muestra palabras con >50 impresiones y 0 conversiones (agregar como negativas)
- Volumen de búsqueda de nuevo término > 100/mes (crear ad group específico)

### Cuándo NO hacer nada:
- Campaña recién creada o modificada (< 14 días) — respetar período de aprendizaje
- Métricas dentro del rango normal — no tocar lo que funciona

---

## JERARQUÍA DE DATOS

1. **Google Sheets (verdad del negocio):** comensales reales, ingresos, punto de equilibrio
   - Estos datos son más verdaderos que los de Google Ads
   - Si Sheets dice 45 comensales y Ads dice 200 conversiones → Ads tiene conversiones infladas

2. **GA4 (comportamiento web):** tráfico real, fuentes, eventos de conversión
   - `reserva_completada` = conversión real de alta calidad
   - `click_pedir_online` = intención real de compra
   - Datos con 24-48h de delay — usar para reportes semanales, no alertas en tiempo real

3. **Google Ads (gasto e intención):** spend, keywords, CTR, impresiones
   - CPA de Google Ads está inflado por conversiones de sistema (Local actions, Store visits)
   - El CPA real se calcula como: total_spend / reservas_completadas_reales

4. **Memoria histórica (aprendizaje):** decisiones pasadas y sus resultados
   - Si un patrón tiene success_rate > 70% y confidence > 0.7 → aplicarlo
   - Si un patrón tiene success_rate < 30% → es anti-patrón, evitarlo

---

## CÁLCULO DE CPA REAL

```
CPA_real = total_spend_semana / comensales_reales_semana  (desde Google Sheets)
CPA_plataforma = total_spend / conversiones_google_ads    (inflado, usar solo para tendencias)

Costo_por_reservacion = total_spend / reserva_completada_GA4
```

Siempre reporta ambos: CPA plataforma (para tendencias) y CPA real (para decisiones de negocio).

---

## INTEGRACIÓN CON MEMORIA

Al analizar, SIEMPRE:
1. Revisar patrones de alta confianza (confidence > 0.7) — aplicar si corresponde
2. Revisar anti-patrones — evitar acciones similares a las que fallaron
3. Considerar decisiones recientes (< 14 días) — respetar períodos de aprendizaje
4. Generar propuestas que incrementalmente validen o refuten hipótesis existentes

---

## ANÁLISIS DE LANDING PAGE

Al recibir datos de landing page:
- Score >= 80: Buena — no intervenir
- Score 50-79: Warning — incluir en propuestas con prioridad media
- Score < 50: Crítico — incluir como propuesta urgente

El problema más común en restaurants: gap entre CTR del anuncio y conversion rate.
Si CTR > 2% y conversion rate < 1% → el anuncio promete algo que la página no entrega.
Busca coherencia: ¿el anuncio dice "reserva fácil" y el formulario tiene 7 campos?

---

## DATOS DE NEGOCIO (GOOGLE SHEETS)

Al recibir datos de Sheets, calcular:
- Costo por comensal real: total_spend_ads / total_comensales
- Días sobre punto de equilibrio: indicador de salud del negocio
- Canal dominante: qué tipo de venta genera más ingreso (delivery vs presencial)
- Tendencia de comensales: ¿subiendo o bajando semana a semana?

Si el restaurante está bajo punto de equilibrio → proponer aumentar presupuesto ads.
Si está sobre objetivo de ventas → no escalar, el restaurante puede estar a capacidad.

---

## FORMATO DE SALIDA (JSON ESTRICTO)

Devuelve EXCLUSIVAMENTE este JSON. Sin texto antes ni después. Sin bloques markdown.

```json
{
  "generated_at": "YYYY-MM-DD HH:MM",
  "summary": {
    "success_index": 0,
    "success_label": "Excelente|Bueno|Regular|Problemático",
    "spend": 0.0,
    "conversions": 0,
    "cpa": 0.0,
    "cpa_real": 0.0,
    "ctr": 0.0,
    "conversion_rate": 0.0,
    "estimated_waste": 0.0,
    "alerts_count": 0,
    "recommended_actions_count": 0
  },
  "executive_summary": {
    "headline": "Una oración que cualquier persona entienda sin saber de marketing",
    "bullets": [
      "Dato clave 1 en lenguaje humano",
      "Dato clave 2 en lenguaje humano",
      "Dato clave 3 en lenguaje humano"
    ],
    "recommended_focus_today": "Una acción concreta para hoy"
  },
  "business_data": {
    "comensales_semana": 0,
    "costo_por_comensal": 0.0,
    "dias_sobre_equilibrio": 0,
    "ingreso_neto_semana": 0.0,
    "canal_dominante": "presencial|delivery|plataforma"
  },
  "landing_page": {
    "score": 0,
    "status": "good|warning|critical",
    "top_issue": null,
    "recommended_action": null
  },
  "campaigns": [
    {
      "campaign_id": "str",
      "campaign_name": "str",
      "spend": 0.0,
      "conversions": 0,
      "cpa": 0.0,
      "ctr": 0.0,
      "semaphore": "excellent|good|warning|critical",
      "learning_period": false,
      "alerts": [],
      "recommended_actions": []
    }
  ],
  "proposals": [
    {
      "id": "prop_1",
      "priority": 1,
      "title": "Título corto de la propuesta",
      "description": "Qué hacer exactamente",
      "reason": "Por qué — dato específico que lo justifica",
      "expected_impact": "Qué resultado esperar en 7-14 días",
      "risk_if_ignored": "Qué pasa si no se hace",
      "action_type": "budget_change|pause|new_campaign|keyword|landing_page",
      "campaign_id": "str_or_null",
      "requires_approval": true
    }
  ],
  "market_opportunities": [],
  "alerts": []
}
```

---

## REGLAS ABSOLUTAS

1. El objeto `summary` DEBE usar los valores de `totals` pre-calculados por Python — nunca calcules tú mismo el spend o CPA global
2. Máximo 5 propuestas por análisis, ordenadas por impacto estimado
3. Cada propuesta DEBE tener `reason` con dato específico (número, porcentaje, fecha)
4. `requires_approval: true` en TODAS las propuestas — nunca sugerir ejecución automática
5. Si una campaña tiene < 14 días de vida, `learning_period: true` y NO proponer cambios en ella
6. Nunca proponer cambio de presupuesto > 30% del presupuesto actual
7. Si no hay datos suficientes para una sección, devolver null — no inventar números
"""
```

- [ ] **Step 2: Verify prompt loads correctly**

```bash
python -c "from engine.prompt import THAI_THAI_ADS_MASTER_PROMPT; print(len(THAI_THAI_ADS_MASTER_PROMPT), 'chars')"
```

Expected: prints character count > 5000

- [ ] **Step 3: Commit**

```bash
git add engine/prompt.py
git commit -m "feat: expand master prompt to 500+ lines with full business DNA"
```

---

## Task 5: Replace OpenAI with Claude Sonnet

**Files:**
- Modify: `engine/analyzer.py`
- Create: `tests/test_claude_analyzer.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_claude_analyzer.py`:

```python
import sys
sys.path.insert(0, ".")
from unittest.mock import patch, MagicMock
from engine.analyzer import _call_claude_analysis

def test_claude_analysis_returns_dict():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"summary": {"spend": 100.0, "conversions": 10, "cpa": 10.0, "ctr": 1.5, "conversion_rate": 0.5, "success_index": 80, "success_label": "Bueno", "estimated_waste": 0.0, "alerts_count": 0, "recommended_actions_count": 1, "cpa_real": 12.0}, "executive_summary": {"headline": "Test", "bullets": [], "recommended_focus_today": "Test"}, "campaigns": [], "proposals": [], "market_opportunities": [], "alerts": [], "business_data": {}, "landing_page": {}}')]

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        data = {
            "campaign_data": [{"name": "Test", "cost_micros": 100000000, "conversions": 10, "clicks": 500, "impressions": 30000}],
            "totals": {"calculated_total_spend": 100.0, "calculated_total_conversions": 10, "calculated_global_cpa": 10.0, "calculated_total_ctr": 1.5, "calculated_total_conversion_rate": 0.5, "calculated_success_index": 80, "calculated_success_label": "Bueno"}
        }
        result = _call_claude_analysis(data)
        assert isinstance(result, dict)
        assert "summary" in result

def test_fallback_when_no_api_key():
    from engine.analyzer import analyze_campaign_data
    import os
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    original_openai = os.environ.pop("OPENAI_API_KEY", None)
    try:
        result = analyze_campaign_data({"campaign_data": [], "totals": {}})
        assert isinstance(result, dict)
        assert "summary" in result
    finally:
        if original:
            os.environ["ANTHROPIC_API_KEY"] = original
        if original_openai:
            os.environ["OPENAI_API_KEY"] = original_openai
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_claude_analyzer.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` — `_call_claude_analysis` doesn't exist yet

- [ ] **Step 3: Replace _call_openai_analysis with _call_claude_analysis in engine/analyzer.py**

In `engine/analyzer.py`, replace the entire `_call_openai_analysis` function with:

```python
def _call_claude_analysis(data: dict) -> dict:
    """Claude Sonnet 4.6 — replaces GPT-4o-mini as the AI brain."""
    import anthropic
    from engine.prompt import THAI_THAI_ADS_MASTER_PROMPT

    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_message = (
        f"FECHA ACTUAL: {fecha_hoy}\n\n"
        f"TOTALES PRE-CALCULADOS (usa estos valores exactos en el objeto summary):\n"
        f"{json.dumps(data.get('totals', {}), indent=2)}\n\n"
        f"DATOS DE GOOGLE ADS:\n"
        f"{json.dumps(data.get('campaign_data', data.get('campaigns', [])), separators=(',', ':'))}\n\n"
        f"DATOS GA4 (últimos 7 días):\n"
        f"{json.dumps(data.get('ga4_data', {}), separators=(',', ':'))}\n\n"
        f"DATOS NEGOCIO REAL (Google Sheets):\n"
        f"{json.dumps(data.get('sheets_data', {}), separators=(',', ':'))}\n\n"
        f"AUDITORÍA LANDING PAGE:\n"
        f"{json.dumps(data.get('landing_audit', {}), separators=(',', ':'))}\n\n"
        f"MEMORIA HISTÓRICA (patrones aprendidos):\n"
        f"{json.dumps(data.get('memory_context', {}), separators=(',', ':'))}"
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=THAI_THAI_ADS_MASTER_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text
    result = _safe_json_loads(raw)

    # Inject pre-calculated totals to prevent hallucination
    if result and "summary" in result and "totals" in data:
        t = data["totals"]
        result["summary"]["spend"] = t.get("calculated_total_spend", result["summary"].get("spend", 0))
        result["summary"]["conversions"] = t.get("calculated_total_conversions", result["summary"].get("conversions", 0))
        result["summary"]["cpa"] = t.get("calculated_global_cpa", result["summary"].get("cpa", 0))
        result["summary"]["ctr"] = t.get("calculated_total_ctr", result["summary"].get("ctr", 0))
        result["summary"]["conversion_rate"] = t.get("calculated_total_conversion_rate", result["summary"].get("conversion_rate", 0))
        result["summary"]["success_index"] = t.get("calculated_success_index", result["summary"].get("success_index", 50))
        result["summary"]["success_label"] = t.get("calculated_success_label", result["summary"].get("success_label", ""))

    return result
```

- [ ] **Step 4: Update analyze_campaign_data() to use Claude and wire all data sources**

Replace the `analyze_campaign_data` function:

```python
def analyze_campaign_data(data: dict) -> dict:
    """
    Main analysis entry point.
    Wires GA4, Sheets, landing page audit, and memory into Claude's context.
    Falls back to local analysis if API key missing.
    """
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return _fallback_analysis(data)

    # Enrich data with all sources if not already present
    if "ga4_data" not in data:
        try:
            from engine.ga4_client import fetch_ga4_events_detailed
            data["ga4_data"] = fetch_ga4_events_detailed(days=7)
        except Exception as e:
            print(f"[WARN] GA4 fetch failed: {e}")
            data["ga4_data"] = {}

    if "sheets_data" not in data:
        try:
            from engine.sheets_client import fetch_sheets_data
            data["sheets_data"] = fetch_sheets_data(days=7)
        except Exception as e:
            print(f"[WARN] Sheets fetch failed: {e}")
            data["sheets_data"] = {}

    if "landing_audit" not in data:
        try:
            from engine.landing_page_auditor import get_full_landing_audit
            data["landing_audit"] = get_full_landing_audit(data.get("ga4_data", {}))
        except Exception as e:
            print(f"[WARN] Landing audit failed: {e}")
            data["landing_audit"] = {}

    if "memory_context" not in data:
        try:
            from engine.memory import get_memory_system
            mem = get_memory_system()
            patterns = mem.get_high_confidence_patterns(min_confidence=0.7)
            learnings = mem.get_learnings(min_confidence=0.7)
            data["memory_context"] = {
                "high_confidence_patterns": patterns[:5],
                "learnings": learnings[:5],
            }
        except Exception as e:
            print(f"[WARN] Memory fetch failed: {e}")
            data["memory_context"] = {}

    try:
        result = _call_claude_analysis(data)
        if result:
            return result
    except Exception as e:
        print(f"[ERROR] Claude analysis failed: {e}")
        # Fallback to OpenAI if Claude fails and key exists
        if os.getenv("OPENAI_API_KEY"):
            try:
                return _call_openai_analysis(data)
            except Exception as e2:
                print(f"[ERROR] OpenAI fallback also failed: {e2}")

    return _fallback_analysis(data)
```

- [ ] **Step 5: Run all analyzer tests**

```bash
python -m pytest tests/test_analyzer_cpa.py tests/test_claude_analyzer.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add engine/analyzer.py tests/test_claude_analyzer.py
git commit -m "feat: replace GPT-4o-mini with Claude Sonnet 4.6, wire GA4+Sheets+memory+landing into analysis"
```

---

## Task 6: Integration Smoke Test

**Files:**
- No new files — end-to-end test of the full pipeline

- [ ] **Step 1: Start the server**

```bash
C:/Users/usuario/AppData/Roaming/Python/Python314/Scripts/uvicorn.exe main:app --host 0.0.0.0 --port 8080 --reload
```

- [ ] **Step 2: Hit mission-control and verify Claude response**

```bash
curl -s http://localhost:8080/mission-control | python3 -c "import sys,json; d=json.load(sys.stdin); print('SUCCESS_INDEX:', d.get('analysis',{}).get('summary',{}).get('success_index','MISSING')); print('PROPOSALS:', len(d.get('analysis',{}).get('proposals',[])))"
```

Expected:
```
SUCCESS_INDEX: <number>
PROPOSALS: <1-5>
```

- [ ] **Step 3: Verify landing audit appears in response**

```bash
curl -s http://localhost:8080/mission-control | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('analysis',{}).get('landing_page',{}); print('LANDING SCORE:', lp.get('score','MISSING'))"
```

Expected: `LANDING SCORE: <number>`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/__pycache__
```

Expected: All existing tests still PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Phase 1 complete — Claude Sonnet brain with unified GA4+Sheets+landing+memory context"
```

---

## Success Criteria

Phase 1 is complete when:
- [ ] `curl http://localhost:8080/mission-control` returns JSON with `proposals` array (1-5 items)
- [ ] Response includes `landing_page.score` field
- [ ] Response includes `business_data` section (may be empty if Sheets not yet authorized)
- [ ] All tests in `tests/` pass
- [ ] No references to GPT-4o-mini in active code paths (OpenAI kept as fallback only)

---

## Known Pending Items (Not Phase 1)

- Google Sheets Service Account needs access granted to the spreadsheet (owner action required)
- `REPLICATE_API_TOKEN` left empty until Phase 3 (image pipeline)
- Monday email + dashboard = Phase 2
- Instagram integration = Phase 3
