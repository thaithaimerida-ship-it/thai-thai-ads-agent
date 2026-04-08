# Thai Thai Ads Agent — CLAUDE.md

## Qué hace
FastAPI (Python 3.13) — agente semi-autónomo de optimización para Google Ads + GA4 + Sheets del restaurante Thai Thai Mérida. El cerebro de decisión es Claude Haiku 4.5 (decisiones de presupuesto y keywords). Claude Sonnet 4.6 se usa para análisis e insights narrativos.

## Principio de negocio
Este proyecto no busca recortar gasto por defecto. Busca detectar:
- Desperdicio real
- Oportunidades de reubicación de presupuesto
- Problemas de conversión
- Fallas de landing page
- Campañas que merecen más inversión

Toda recomendación debe responder: **¿Dónde está el siguiente peso mejor invertido?**

---

## Estado post-sesión — 7 abril 2026

### Sub-agentes activos (5 funcionando)
| Sub-agente | Archivo | Estado |
|---|---|---|
| Auditor | `agents/auditor.py` | ✅ Activo — Fases 3A-7B + GEO + SMART + **6D Quality/Creative** |
| Executor | `agents/executor.py` | ✅ Activo — block_keyword, update_budget, pause_adgroup, add_keyword, remove_theme, **add_ad_headlines, add_ad_descriptions, remove_ad_asset** |
| Strategist | `agents/strategist.py` | ✅ Activo |
| Reporter | `agents/reporter.py` | ✅ Activo — snapshots GCS |
| Builder | `agents/builder.py` | ✅ Activo — crea campañas desde lenguaje natural |

### Decision Engine — Claude Haiku
Dos funciones en `engine/decision_engine.py`:

1. **`get_budget_decisions(campaigns, negocio_data, ga4_data, quality_findings)`** — Haiku decide escalar/reducir/hold por campaña cruzando Ads + Sheets + GA4 + **Quality Score + Ad Strength + Impression Share**. Guardrails: ±20% max, $20 mín/día, cap $8,000/mes, confianza ≥ 70%.

   **Prompt jerarquizado en 4 bloques** (orden de prioridad):
   - Bloque 1 — REALIDAD DEL NEGOCIO ⭐ (Sheets + Ocupación) — si contradice Ads, Sheets gana
   - Bloque 2 — SALUD DEL SISTEMA (GA4 + Landing) — si la web no convierte, no escalar
   - Bloque 3 — RENDIMIENTO PUBLICITARIO (Campañas + Presupuesto)
   - Bloque 4 — CALIDAD DE ANUNCIOS (Quality Score + Ad Strength + IS) — explica el "por qué"

   **Reglas causales 8-12**: hold si AD_STRENGTH_POOR, scale si LOST_IS_BUDGET, hold si QS_LANDING_WEAK.
   **Regla 13**: cada decisión DEBE estar respaldada por ≥3 fuentes distintas. El JSON incluye campo `"sources": [...]`.

2. **`get_keyword_decisions(campaigns, current_keywords, suggested_keywords, negocio_data, search_ad_groups)`** — Haiku decide qué keywords agregar a campañas Search cruzando keywords actuales + sugerencias del Keyword Planner. Guardrails: máx 5 por ciclo, confianza ≥ 75%, solo campañas Search, no duplicar existentes.

### Remediación Creativa Autónoma — Claude Sonnet 4.6
`engine/creative_remediation.py` — Cuando el Auditor detecta Ad Strength POOR/AVERAGE:
1. Sonnet genera headlines (≤30 chars) y descriptions (≤90 chars) basados en keywords ganadoras + contexto del negocio
2. Executor los agrega automáticamente al RSA existente
3. Al día siguiente, si Google rechazó un headline → Executor lo elimina → Sonnet genera reemplazo
4. Guardrails: máx 5 headlines + 2 descriptions por ciclo, no duplicar existentes

### Fase 6D — Quality & Creative Health (nueva 7 abril 2026)
Lee 3 fuentes nuevas de Google Ads API y clasifica 11 tipos de findings:
- **Quality Score**: QS_LOW (<4), QS_CREATIVE_WEAK, QS_LANDING_WEAK, QS_CTR_WEAK
- **Ad Health**: AD_STRENGTH_POOR, AD_STRENGTH_AVERAGE, AD_DISAPPROVED, AD_IN_REVIEW
- **Impression Share**: LOW_IMPRESSION_SHARE (<30%), LOST_IS_RANK_HIGH (>30%), LOST_IS_BUDGET_HIGH (>20%)
- Findings alimentan a Haiku (reglas causales) y al correo diario

### 12 consultas GAQL activas
| # | Función | Qué consulta |
|---|---|---|
| 1 | `fetch_campaign_data` | Gasto, conversiones, clicks, impressiones, presupuesto |
| 2 | `fetch_keyword_data` | Keywords con métricas |
| 3 | `fetch_search_term_data` | Search terms que activaron anuncios |
| 4 | `fetch_search_ad_groups` | Ad groups activos en campañas Search |
| 5 | `fetch_campaign_metrics_range` | Comparativo semana vs semana (tracking) |
| 6 | `fetch_adgroup_metrics` | Métricas por ad group |
| 7 | `fetch_campaign_budget_info` | Presupuesto actual por campaña |
| 8 | `fetch_campaign_geo_criteria` | Geo targeting por campaña |
| 9 | `fetch_conversion_actions` | Acciones de conversión activas |
| 10 | `fetch_keyword_quality_scores` | **Quality Score 1-10 + creative/landing/CTR** |
| 11 | `fetch_ad_health` | **Ad Strength, approval status, headlines/descriptions** |
| 12 | `fetch_impression_share` | **IS%, perdido por rank, perdido por budget** |

### Auto-ejecución activa
- `AUTO_EXECUTE_ENABLED=true` — kill switch global
- `BUDGET_CHANGE_ENABLED=true` — kill switch de presupuestos
- **Fase 6B.AUTO**: ejecuta propuestas BA1 (reducción) ≤20% sin aprobación
- **Fase 6C.AUTO**: ejecuta propuestas BA2 (escala) ≤20% sin aprobación
- **Fase 6D**: remediación creativa autónoma (agrega headlines/descriptions, elimina rechazados)
- **Fase 7**: presupuestos via Claude Haiku — ejecuta si confianza ≥ 70%
- **Fase 7B**: keywords via Claude Haiku + Keyword Planner — ejecuta si confianza ≥ 75%

### Google Sheets — Cortes de Caja (ÚNICA fuente de ventas)
`engine/sheets_client.py` lee SOLO `Cortes_de_Caja` (no toca Ingresos_BD — esa pestaña es solo contable):
- Efectivo (col F), Tarjeta (col G), Plataformas (col H), Propinas (col I, negativo)
- Venta Total del Día = Efectivo + Tarjeta + Plataformas + Propinas
- Comensales (col J), objetivos de ventas y equilibrio
- `resumen_negocio_para_agente(days=N)` — función canónica, 100% Cortes_de_Caja

### Correo diario — Secciones
1. **Movimiento en la Web (GA4 24h)** — usuarios, clicks pedir/reservar
2. **Salud de Canales** — cards: Google Ads 24h, Landing, Comensales, **Venta Total**
3. **Gasto por Campaña (24h)** — tabla con gasto/conv/CPA por campaña individual
4. **Desglose de Ventas del Día** — Efectivo/Tarjeta/Plataformas/Propinas/Total (Cortes_de_Caja)
5. **🎨 Salud de Anuncios y Calidad** — Quality Score, Ad Strength, Impression Share, acciones creativas
6. **Propuestas** — keywords, presupuestos, geo (con botones Aprobar/Rechazar)
7. **Decisiones AI** — Haiku budget/keywords ejecutadas
8. **Lectura del Agente** — insight cruzado Ads+GA4+Sheets generado por Haiku
9. **Contexto del día** — ocupación histórica del día de la semana

### Blended ROAS implementado
ROI cruzado en `engine/budget_actions.py` y `engine/budget_scale.py`:
- Local/default: `venta_local_total / ads_cost`
- Delivery: `venta_plataformas_bruto / ads_cost` (Cortes_de_Caja col H)
- BA1 protege campañas si ROI ≥ 3x (local) o ≥ 5x (delivery)
- BA2 escala campañas con ROI alto aunque Ads muestre 0 conversiones

### Presupuesto dinámico por ocupación
`sheets_client.get_occupancy_by_day_of_week(weeks=8)` — Haiku recibe ocupación histórica por día:
- Días de ocupación BAJA → considerar subir presupuesto campañas locales
- Días de ocupación ALTA → mantener, restaurante llena naturalmente
- Solo aplica a campañas Local/Experiencia, no Delivery/Reservaciones

---

## Producción

- **URL**: `https://thai-thai-ads-agent-624172071613.us-central1.run.app`
- Usar servicio `thai-thai-ads-agent` (NO `thai-thai-agent` — servicio fantasma)
- Cold start ~2 min en primera llamada del día — normal

### Cloud Scheduler (America/Merida)
| Job | Horario | Función |
|---|---|---|
| `auditoria-diaria` | 7:00 am lunes–domingo | Auditoría autónoma + correo diario |
| `auditoria-compensatoria` | 11:00 am lunes–domingo | Solo corre si la de 7am falló |
| `reporte-semanal-lunes` | 8:00 am lunes | Reporte ejecutivo semanal |

### Cloud Build
Auto-deploy conectado al repo GitHub. Cada `git push` a `main` dispara build + deploy automático (~5 min). No se necesita deploy manual salvo para env vars.

### Deploy de env vars — REGLA CRÍTICA
```bash
# CORRECTO — aditivo, no destruye otras vars
gcloud run services update thai-thai-ads-agent \
  --region us-central1 \
  --update-env-vars "KEY=value"

# Para valores con espacios (Gmail app password):
gcloud run services update thai-thai-ads-agent \
  --region us-central1 \
  --update-env-vars "^;^KEY=value with spaces"

# NUNCA USAR -- borra TODAS las env vars existentes
# --env-vars-file  ← PROHIBIDO
```

---

## Env vars en Cloud Run (producción)

| Variable | Descripción |
|---|---|
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth2 token (renovar si expires) |
| `GOOGLE_ADS_CLIENT_ID` | OAuth2 client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth2 client secret |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Dev token Google Ads |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC: `4093352643` |
| `GOOGLE_ADS_TARGET_CUSTOMER_ID` | Cuenta Thai Thai: `4021070209` |
| `GOOGLE_CREDENTIALS_JSON` | Service account JSON (compacto, no base64) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | `17LNxz8jXPWF9G2d0Rwa1Mzw-6s1brtJzYufnyOI42FI` |
| `ANTHROPIC_API_KEY` | Claude API key |
| `GMAIL_APP_PASSWORD` | App password Gmail (sin espacios) |
| `EMAIL_SENDER` | `administracion@thaithaimerida.com.mx` |
| `EMAIL_RESTAURANT` | `administracion@thaithaimerida.com.mx` |
| `EMAIL_REPORT_TO` | `administracion@thaithaimerida.com.mx` |
| `GA4_PROPERTY_ID` | `528379219` |
| `AUTO_EXECUTE_ENABLED` | `true` |
| `BUDGET_CHANGE_ENABLED` | `true` |
| `CALLMEBOT_PHONE` | `5219999317457` |
| `CALLMEBOT_APIKEY` | `8710152` |

### Renovar refresh token Google Ads
Si aparece `invalid_grant` en logs:
```bash
# IMPORTANTE: Usar cuenta thaithaimerida@gmail.com (está en test users)
# client_id correcto: 624172071613-96hda5g04ka5cioror2nje2lcuongapt.apps.googleusercontent.com

# 1. Abrir URL en navegador con cuenta thaithaimerida@gmail.com:
https://accounts.google.com/o/oauth2/auth?client_id=624172071613-96hda5g04ka5cioror2nje2lcuongapt.apps.googleusercontent.com&redirect_uri=urn:ietf:wg:oauth:2.0:oob&scope=https://www.googleapis.com/auth/adwords&response_type=code&access_type=offline&prompt=consent

# 2. Intercambiar código:
curl -X POST https://oauth2.googleapis.com/token \
  -d "code=CÓDIGO_AQUÍ" \
  -d "client_id=624172071613-96hda5g04ka5cioror2nje2lcuongapt.apps.googleusercontent.com" \
  -d "client_secret=GOCSPX-XXXXXXXXX" \
  -d "redirect_uri=urn:ietf:wg:oauth:2.0:oob" \
  -d "grant_type=authorization_code"

# 3. Actualizar en Cloud Run y google-ads.yaml:
gcloud run services update thai-thai-ads-agent --region us-central1 \
  --update-env-vars "GOOGLE_ADS_REFRESH_TOKEN=nuevo_token"
```

---

## Estructura del proyecto

```
agents/
  auditor.py             ← ciclo completo de auditoría (Fases 3A-7B + GEO + SMART + 6D Quality/Creative)
  executor.py            ← ejecuta acciones en Google Ads API (keywords, budget, adgroups, headlines, descriptions)
  strategist.py          ← análisis y propuestas
  reporter.py            ← reportes y snapshots GCS
  builder.py             ← crea campañas desde lenguaje natural
engine/
  ads_client.py          ← Google Ads API — 12 queries GAQL + mutations (budget, keywords, RSA assets, geo)
  creative_remediation.py ← Sonnet 4.6 genera headlines/descriptions para anuncios POOR/AVERAGE
  credentials.py         ← loader centralizado de service account (GOOGLE_CREDENTIALS_JSON o archivo)
  decision_engine.py     ← Claude Haiku: budget + keywords + diagnóstico causal (quality_findings)
  budget_actions.py      ← BA1: detectar campañas para reducir (con ROI real de Sheets)
  budget_scale.py        ← BA2: detectar campañas para escalar (Vía 1 Ads + Vía 2 Sheets)
  campaign_health.py     ← CH1/CH3: CPA crítico y campañas sin conversiones
  risk_classifier.py     ← RISK_EXECUTE / RISK_PROPOSE / RISK_OBSERVE / RISK_BLOCK
  keyword_planner.py     ← sugerencias de keywords via Google Ads API
  ga4_client.py          ← datos GA4
  sheets_client.py       ← Google Sheets (Cortes_de_Caja ÚNICO — no toca Ingresos_BD)
  memory.py              ← SQLite (dedup, historial, propuestas)
  db_sync.py             ← sincroniza SQLite ↔ GCS
  email_sender.py        ← correo diario + correo semanal + alertas + sección Salud de Anuncios
  activity_log.py        ← registro de runs
  landing_page_auditor.py
  analyzer.py
  normalizer.py
config/
  agent_config.py        ← umbrales, caps, CPA targets, kill switches
routes/
  reservations.py        ← POST/GET /reservations
  analysis.py            ← /analyze-keywords, /analyze-campaigns-detailed, /insights, etc.
  tracking.py            ← /fix-tracking, /audit-log
  approvals.py           ← /approve-proposals, /approve
  reports.py             ← /send-weekly-report
  ecosystem.py           ← /ecosystem/ads-summary, /ecosystem/business-metrics, /ecosystem/health
  keywords.py            ← /keyword-research
  campaigns.py           ← /restructure-campaigns, /create-reservations-campaign
  builder.py             ← /build-campaign, /deploy-campaign, /pending-configs
main.py                  ← FastAPI (~535 líneas): /health, /mission-control, /dashboard-snapshot,
                            /run-autonomous-audit, /run-compensatory-audit
```

---

## Campañas activas

| Campaña | ID | Presupuesto | Tipo |
|---|---|---|---|
| Thai Mérida - Local | 22612348265 | ~$267/día | Smart (Maps/offline) |
| Thai Mérida - Delivery | 22839241090 | ~$267/día | Smart (Gloria Food) |
| Thai Mérida - Reservaciones | 23680871468 | variable | Search (keywords manuales) |
| Thai Mérida - Experiencia 2026 | 23730364039 | variable | Search |

**Nota sobre Local**: 0 conversiones en Google Ads es NORMAL — mide "cómo llegar" en Maps, no compras web. La evidencia real son los comensales en Sheets. El agente ya protege esta campaña de reducciones incorrectas.

## CPA targets
| Objetivo | Ideal | Máximo | Crítico |
|---|---|---|---|
| Delivery (Gloria Food) | $25 MXN | $45 MXN | >$80 MXN |
| Reserva online | $50 MXN | $85 MXN | >$120 MXN |
| General | $35 MXN | $60 MXN | >$100 MXN |

---

## Correr el backend local
```bash
PYTHONIOENCODING=utf-8 C:\Users\usuario\AppData\Roaming\Python\Python314\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8080
```

---

## IDs críticos

| Dato | Valor |
|---|---|
| Google Ads customer ID | `4021070209` |
| Google Ads MCC | `4093352643` |
| GA4 Property | `528379219` |
| Google Ads conversion ID | `AW-17126999855` |
| GTM Container | `GTM-5CRD9SKL` |
| Spreadsheet Cortes_de_Caja | `17LNxz8jXPWF9G2d0Rwa1Mzw-6s1brtJzYufnyOI42FI` |
| Cloud Run URL | `https://thai-thai-ads-agent-624172071613.us-central1.run.app` |
| Email operativo | `administracion@thaithaimerida.com.mx` |
| CallMeBot phone | `5219999317457` |
| CallMeBot apikey | `8710152` |

---

## Google Ads API v23 — Gotchas
- `client.get_type("FieldMask")` inválido → usar `update_mask.paths[:] = [...]`
- Smart campaigns: no soportan ad schedule ni múltiples proximity criteria via API
- System conversions: `MUTATE_NOT_ALLOWED` → cambiar a "Acción secundaria" manualmente en UI
- `contains_eu_political_advertising`: ENUM `=3`, no bool
- Geo en Smart campaigns: hacer UPDATE in-place si remove falla silencioso
- `budget.name` necesita timestamp para evitar `DUPLICATE_NAME` en re-runs
- `load_from_dict` no acepta campo `token_uri` — omitirlo siempre
- `verify_budget_still_actionable()` y `log_agent_action()` tienen firmas distintas a como las llama el Executor — bugs conocidos, no críticos

---

## ROADMAP — Fases pendientes

### Fase 2 — Programa de Lealtad (no iniciado)
- Captura de datos de clientes (nombre, email, visitas)
- Sistema de puntos por visita
- Integración con reservaciones
- Notificaciones WhatsApp/email a clientes frecuentes

### Fase 3 — Mejora de Imágenes con AI (no iniciado)
- Replicate.com para mejorar fotos de platillos
- Prompt: fotografía gastronómica premium, fondo oscuro, detalle macro
- Output: imágenes para Google Business, ads, landing page
- `REPLICATE_API_TOKEN` ya está en `.env` (vacío, activar al implementar)

### Fase 4 — Firebase (no iniciado)
- Reemplazar SQLite por Firebase Firestore
- Persistencia cross-instancias sin GCS sync
- Historial de reservaciones en tiempo real
- Dashboard live para Hugo

### Fase 5 — Automatización Completa de Reporting
- Reporte semanal con comparativo semana anterior
- Alertas WhatsApp solo ante incidentes críticos (no reportes normales)
- Dashboard Streamlit con datos en vivo
- Integración con thai-thai-dashboard (Google Apps Script)

---

## Reglas de testing
- Tests solo para funciones que tocan **dinero real** o **Google Ads API**
- No se requieren tests para UI ni endpoints de solo lectura
- Antes de tocar `engine/ads_client.py` — revisar `docs/risk-matrix.md`

---

## Documentación operativa crítica

Antes de implementar lógica de ejecución automática, alertas, aprobaciones o reporting:

| Archivo | Revisar antes de... |
|---|---|
| `docs/risk-matrix.md` | Implementar lógica de ejecución automática o escalamiento |
| `docs/autonomy-policy.md` | Implementar lógica de autonomía, escalamiento o aprobación |
| `docs/weekly-report-spec.md` | Modificar lógica de reporting o resumen ejecutivo |
| `docs/approval-flow.md` | Implementar correos de aprobación o parsing APROBAR/RECHAZAR |

---

## Modelo de autonomía por niveles

### Nivel 0 — Observación
Señal detectada, sin acción. Usar cuando hay poca data, señal ambigua, campaña en aprendizaje, o hace falta acumular evidencia.

### Nivel 1 — Acción automática (RISK_EXECUTE)
El agente ejecuta sin pedir permiso cuando: evidencia clara, cambio ≤20%, reversible, impacto limitado.

Ejemplos: pausar keyword con gasto desperdiciado, ajustar presupuesto ≤20%, agregar keyword Search.

### Nivel 2 — Propuesta (RISK_PROPOSE)
Prepara propuesta completa pero no ejecuta. Cambios >20%, impacto relevante, tradeoff real.

### Nivel 3 — Bloqueado (RISK_BLOCK)
Nunca ejecutar automáticamente: cambios de bidding strategy, activar/desactivar campañas, cambios estructurales.

---

## Política de alertas

**WhatsApp solo para excepciones críticas** — no reportes normales:
- Caída abrupta de conversiones
- Landing rota
- Tracking roto
- Gasto anormal sin valor

**Correo diario** (7am): resumen de auditoría, cambios ejecutados, propuestas, alertas GEO.

**Correo semanal** (lunes 8am): reporte ejecutivo con comparativo, acciones tomadas, riesgos abiertos, recomendación principal.

---

## Rol del agente
Thai Thai Ads Agent es un operador **autónomo** de crecimiento rentable para Google Ads y conversión web.

Opera en 4 capas de inteligencia:
1. **Financiera** — presupuestos, CPA, ROI cruzado con ventas reales
2. **Keywords** — bloquear desperdicio, agregar keywords con Keyword Planner + Haiku
3. **Calidad** — Quality Score, Impression Share, diagnóstico causal (tracking → landing → anuncio → rank → budget)
4. **Creativa** — detectar anuncios débiles, generar copy con Sonnet, autocorregir rechazos

**El éxito se mide por cuánto trabajo útil resuelve, cuánto desperdicio evita, cuánta estabilidad protege y qué tan bien ayuda a invertir mejor el siguiente peso.**

Si hay duda entre "hacer más análisis" o "resolver un problema operativo real" → priorizar el problema operativo.

Si hay duda entre "hacer un cambio llamativo" o "proteger estabilidad" → priorizar estabilidad.
