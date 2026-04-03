# Thai Thai Super Agent — Design Spec
**Date:** 2026-03-22
**Status:** Approved for implementation

---

## Vision

Transform the Thai Thai Ads Agent from a Google Ads optimizer into a full business intelligence agent that acts as a Senior Growth Marketing Strategist for a Thai restaurant in Mérida, México. The agent analyzes all business data sources, generates actionable proposals, and executes approved changes autonomously.

---

## Autonomy Model

**Semi-autonomous (B):** The agent proposes, the owner approves with one click, the agent executes.

- Agent NEVER executes without explicit approval
- Small adjustments (keywords, bid modifiers) bundled into weekly proposals
- Large changes (new campaigns, budget >20% change) flagged with extra context
- All executed actions logged to audit trail

---

## Architecture

```
DATA LAYER
├── Google Ads API          (campaigns, keywords, spend, conversions)
├── GA4 API                 (traffic, events, bounce rate, landing page)
├── Google Sheets API       (comensales, ingresos, gastos, punto equilibrio)
├── Landing Page Code       (thai-thai web project — structure, speed, UX)
└── SQLite Memory           (decisions, outcomes, patterns, learnings)

AI BRAIN
├── Claude Sonnet 4.6       (analysis, strategy, writing, vision evaluation)
└── OpenAI DALL-E/GPT-4o    (image enhancement with owner's existing prompt)

OUTPUT LAYER
├── Email (Monday)          (executive summary + detail + approval link)
└── Dashboard (web)         (real-time monitoring + approval interface)
```

---

## Data Sources

### Google Ads (existing)
- Campaign performance: spend, conversions, CPA, CTR, impressions
- Keyword performance: search terms, quality scores
- Ad schedule performance: hour-by-hour click data

### GA4 (existing, disconnected from analysis)
- Traffic by channel (Direct, Paid Search, Organic)
- Landing page metrics: bounce rate, session duration, scroll depth
- Conversion events: reserva_completada, click_pedir_online

### Google Sheets (new)
- Daily diners (actual vs. target for sales goal and break-even)
- Revenue: gross and net
- Expenses: accounting and financial categories
- Sales by channel: POS terminal, delivery platform, cash, transfer

### Landing Page (new)
- Code analysis: load speed, mobile UX, CTA placement, form friction
- GA4 correlation: CTR vs. conversion rate gap detection

### SQLite Memory (existing, disconnected)
- Decision history with outcomes
- Patterns (what works, what doesn't)
- Learnings (high-confidence rules derived from data)

---

## AI Brain

### Primary: Claude Sonnet 4.6
- **Model ID:** `claude-sonnet-4-6`
- **API Key:** `ANTHROPIC_API_KEY` in `.env`
- **Replaces:** GPT-4o-mini in `engine/analyzer.py`
- **Capabilities used:**
  - Campaign analysis and strategy
  - Executive email writing (Spanish, business-appropriate)
  - Photo evaluation (vision) — does this photo work for an ad?
  - Landing page audit — code + metrics correlation
  - Memory-informed reasoning — learns from past decisions

### Secondary: OpenAI (existing)
- **Purpose:** Image enhancement only
- **Flow:** Claude evaluates photo → if improvement needed → OpenAI + owner's prompt → enhanced photo

---

## Prompt Design (expanded from 77 → 500+ lines)

### Sections:
1. **Identity & Role** — Senior Growth Marketing Strategist for Thai Thai Mérida
2. **Business Context** — Restaurant details, ticket promedio, target customer, seasonality in Mérida
3. **Campaign Knowledge** — Current 3 campaigns, their goals, CPA targets, geo targeting
4. **Decision Rules** — When to propose scaling, pausing, restructuring
5. **Memory Integration** — How to use past decisions and learnings
6. **Data Hierarchy** — Google Sheets data overrides ad platform data for business truth
7. **Output Format** — Strict JSON schema for proposals + human-readable summaries
8. **Writing Style** — Email tone: executive, clear, no jargon, actionable

---

## Monday Email

### Structure:
```
Subject: Thai Thai Ads — Reporte Semana [N] | Éxito [X]%

RESUMEN EJECUTIVO
3-5 sentences any person can understand. No jargon.
"Esta semana gastamos $X, tuvimos Y comensales reales,
el punto de equilibrio fue superado Z días de 7."

MÉTRICAS CLAVE
| Campaña        | Gasto  | Conv. | CPA   | Tendencia |
|----------------|--------|-------|-------|-----------|
| Local          | $X     | X     | $X    | ↑ / ↓    |
| Delivery       | $X     | X     | $X    | ↑ / ↓    |
| Reservaciones  | $X     | X     | $X    | ↑ / ↓    |

NEGOCIO REAL (Google Sheets)
- Comensales: X actual vs. Y objetivo
- Ingresos: $X bruto / $Y neto
- Canal principal: [Delivery/Presencial/Plataforma]

PROPUESTAS ESTA SEMANA
1. [Propuesta concreta] → Impacto estimado: [resultado]
   Razón: [explicación en 1 línea]

2. [Propuesta concreta] → Impacto estimado: [resultado]

3. [Propuesta concreta] → Impacto estimado: [resultado]

[APROBAR TODAS] [SELECCIONAR] [VER DASHBOARD]
```

---

## Dashboard

### Panels:
1. **Mission Control** — Semáforo general, spend today, alerts
2. **Campañas** — Cards por campaña con métricas en tiempo real
3. **Negocio Real** — Comensales vs. objetivo, ingresos del día
4. **Landing Page** — Score de conversión, alertas de UX
5. **Propuestas Pendientes** — Aprobación con 1 clic
6. **Historial** — Decisiones ejecutadas y sus resultados

---

## Image Pipeline

```
Google Drive folder
    ↓
Claude Sonnet (vision) evaluates each photo:
  - "APTA: buena iluminación, plato visible, no texto encima"
  - "NO APTA: borrosa, fondo desordenado"
  - "MEJORAR: buen plato pero iluminación baja"
    ↓ (if MEJORAR)
OpenAI API + owner's enhancement prompt
    ↓
Enhanced photo saved locally
    ↓
Used in Google Ads image extensions or RSA
```

---

## Implementation Phases

### Phase 1 (Week 3) — The Brain
- [ ] Replace GPT-4o-mini with Claude Sonnet in `engine/analyzer.py`
- [ ] Expand prompt to 500+ lines with full business context
- [ ] Connect SQLite memory to analysis loop
- [ ] Integrate GA4 data into analysis context
- [ ] Connect Google Sheets API (comensales + ingresos)
- [ ] Add landing page audit (code analysis + GA4 correlation)
- [ ] Add `anthropic` to requirements.txt

### Phase 2 (Week 4) — Communication
- [ ] Build Monday email module with Gmail SMTP (already configured)
- [ ] Build approval link system (unique token per proposal)
- [ ] Build dashboard with all 6 panels
- [ ] Connect dashboard approval to Google Ads execution

### Phase 3 (After) — Visual
- [ ] Google Drive API integration
- [ ] Claude vision photo evaluation
- [ ] OpenAI image enhancement pipeline
- [ ] Instagram Phase 2 (Meta Business API)

---

## Business Intelligence Unlocked

| Metric | Before | After |
|--------|--------|-------|
| Cost per real diner | ❌ | ✅ Ads spend ÷ Sheets comensales |
| Days above break-even | ❌ | ✅ Sheets objective vs. actual |
| Revenue by channel | ❌ | ✅ POS + platform + cash |
| Landing page friction | ❌ | ✅ CTR vs. conversion gap |
| Ad photo quality | ❌ | ✅ Claude vision evaluation |
| Learning from past decisions | ❌ | ✅ Memory connected |

---

## Technical Constraints

- Google Ads API v23 — Smart campaigns reject bid modifiers (documented)
- GA4 Data API — 24-48h data delay (use for weekly reports, not real-time)
- Google Sheets API — requires Service Account credentials (separate from GA4)
- OpenAI image API — GPT-4o vision for enhancement with owner's stored prompt
- Email — Gmail SMTP already configured in `.env`, scheduled Monday 9 AM CST
- Budget guardrail — agent NEVER proposes more than 30% budget change in one week
- Proposals per email — maximum 5 proposals, ranked by estimated impact
- Rollback — if execution fails mid-way, log error + notify via email, no partial state

---

## New .env Variables Required

```
ANTHROPIC_API_KEY=...                    # Claude Sonnet brain
GOOGLE_SHEETS_SPREADSHEET_ID=...        # ID of the business data sheet
GOOGLE_SHEETS_CREDENTIALS_PATH=...      # Service account JSON for Sheets
OPENAI_IMAGE_PROMPT=...                 # Owner's image enhancement prompt
```

---

## Google Sheets Schema

Expected sheet structure (owner confirms or adjusts):
- **Sheet "Diario"**: Date | Comensales_Real | Comensales_Obj_Ventas | Comensales_Obj_Equilibrio | Ingresos_Bruto | Ingresos_Neto
- **Sheet "Canales"**: Date | Terminal_POS | Plataforma_Delivery | Efectivo | Transferencia
- **Sheet "Gastos"**: Date | Categoria | Monto_Bruto | Monto_Neto

---

## Landing Page Friction Thresholds

| CTR (Ads) | Conv. Rate (GA4) | Gap | Status | Action |
|-----------|-----------------|-----|--------|--------|
| Any | >3% | — | Good | No action |
| >2% | <1% | >1% | Warning | Audit CTA placement |
| >2% | <0.5% | >1.5% | Critical | Full landing page audit |

Landing page score = 100 - (gap * 30), capped 0-100.

---

## Decision Rules (Budget Guardrails)

- Scale: CPA < ideal target for 7+ days → propose +20% budget
- Pause: 0 conversions for 7 days AND spend > $200 → propose pause
- Max single change: 30% of current daily budget
- Max total weekly change across all campaigns: $100 MXN
- Never touch Smart campaign bid modifiers via API (documented limitation)
