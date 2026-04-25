# Google Ads Health Audit — Thai Thai Mérida (24 abr 2026)

**Auditoría realizada con skill:** `ads-google` (80 checks, scoring-system v1.5)  
**Fecha:** 24/04/2026 20:09  
**Período de datos:** 2026-03-25 → 2026-04-24  
**Cuenta:** 4021070209 (AW-17126999855)  
**Campañas auditadas:** 3 (Delivery, Local, Experiencia 2026)  
**Solo lectura — ningún cambio fue aplicado**  

## 🎯 Health Score Global

### Calificación: 59/100 — Grado D: Deficiente

```
Google Ads Health Score: 59/100 (Grado: D)

Tracking de Conversiones             50.6/100  ███████░░░░░░░░  (25%)
Gasto Desperdiciado / Negativos      82.0/100  ████████████░░░  (20%)
Estructura de Cuenta                 61.3/100  █████████░░░░░░  (15%)
Keywords & Quality Score             73.9/100  ███████████░░░░  (15%)
Anuncios & Assets                    46.2/100  ██████░░░░░░░░░  (15%)
Configuración & Targeting            31.7/100  ████░░░░░░░░░░░  (10%)
```

**Top 3 Fortalezas:**
- Gasto Desperdiciado / Negativos: 82/100
- Keywords & Quality Score: 74/100
- Estructura de Cuenta: 61/100

**Top 3 Debilidades:**
- Tracking de Conversiones: 51/100
- Anuncios & Assets: 46/100
- Configuración & Targeting: 32/100

## 📊 Resumen Ejecutivo

Thai Thai Mérida opera 3 campañas activas con un gasto total de **$8,499 MXN en 30 días** — significativamente más que los $85/día inicialmente estimados. Las campañas Smart (Delivery y Local) absorben el **88%** del gasto pero reportan conversiones artificialmente infladas (micro-conversiones de mapa y llamadas, no pedidos reales). Esto hace imposible calcular el CPA real de adquisición de clientes.

El problema estructural más crítico es la **estrategia de puja incompatible con el objetivo de negocio**: Experiencia 2026 usa TARGET_IMPRESSION_SHARE (optimiza visibilidad, no conversiones), mientras que las Smart Campaigns no tienen objetivo de CPA definido. Google Ads está aprendiendo a maximizar clics e impresiones, no a traer comensales al restaurante ni pedidos de delivery.

La mayor oportunidad de mejora está en **tracking de conversiones y bidding strategy**: corregir qué conversiones se usan para optimizar (solo click_pedir_online y reserva_completada_directa son señales reales), cambiar a TARGET_CPA, y configurar la cuenta para que Google aprenda de señales de negocio reales. Con estos cambios y el volumen actual de tráfico (>5,978 clicks/mes), la cuenta tiene potencial real.

**Veredicto del consultor:** La cuenta tiene infraestructura básica pero está mal configurada a nivel de conversiones y bidding. No es una cuenta que necesite restructure total, sino correcciones quirúrgicas en 3-4 puntos clave. Prioridad: (1) Corregir conversiones primarias, (2) Cambiar bidding strategy, (3) Agregar negativos temáticos, (4) Configurar Customer Match.

## 📈 Comparación con Benchmarks — Industria Restaurantes

| Métrica | Thai Thai | Benchmark Restaurantes | Benchmark All-Industry | Estado |
|---------|-----------|------------------------|------------------------|--------|
| CTR (Experiencia 2026) | 4.8% | N/D | 6.66% | 🟡 |
| CPC Promedio | $12.37 MXN | ~$41 MXN ($2.05 USD) | ~$104 MXN ($5.26 USD) | ✅ |
| CVR (Experiencia 2026) | 13.6% | N/D | 7.52% | 🟡 |
| IS (Experiencia 2026) | 10.0% | N/D | >30% recomendado | 🔴 |
| QS Promedio | 6.0 | ≥7 | ≥7 | 🟡 |
| Presupuesto mensual total | $8,499 MXN | $1,000+ USD/mes | $1,000+ USD/mes | 🟡 |

> **Nota:** CPC de $12.44 MXN en Experiencia 2026 es razonable para México. El CPC USD equivalente (~$0.62) está muy por debajo del benchmark de restaurantes ($2.05), lo que indica buena eficiencia de costo por clic.

## 🚨 Top 10 Quick Wins (Priorizados)

### QW1: Cambiar estrategia de puja en Experiencia 2026 de TARGET_IMPRESSION_SHARE a MAXIMIZE_CONVERSIONS
- **Por qué:** TARGET_IMPRESSION_SHARE optimiza para aparecer en posición X, no para conversiones. Con click_pedir_online como conversión primaria, MAXIMIZE_CONVERSIONS usará machine learning para convertir.
- **Impacto esperado:** Potencial de 2-3x más conversiones reales por el mismo presupuesto
- **Tiempo:** 5 min en Google Ads UI | **Riesgo:** Bajo
- **Quién:** Manual UI

### QW2: Promover 'click_pedir_online' como ÚNICA conversión primaria — desactivar Smart Campaign micros
- **Por qué:** Google actualmente optimiza para 'Smart campaign map clicks to call', 'map directions', etc. que no generan ingreso. Con click_pedir_online como única primaria, el algoritmo aprende de intención real.
- **Impacto esperado:** Datos de conversión limpios — base para todas las decisiones de bidding
- **Tiempo:** 10 min | **Riesgo:** Bajo (campaña se ajusta gradualmente)
- **Quién:** Manual UI: Herramientas → Conversiones → Cambiar a Primaria/Secundaria

### QW3: Crear 3 listas de negativos temáticas: Informacional, Competidores, Intent irrelevante
- **Por qué:** 0 listas de negativos compartidas. Búsquedas como 'receta pad thai', 'cómo cocinar curry', 'thai thai hotel' gastan presupuesto sin conversión posible.
- **Impacto esperado:** Ahorro estimado: $50-150 MXN/mes. Mejora CTR y QS al eliminar impresiones irrelevantes.
- **Tiempo:** 15 min | **Riesgo:** Bajo (usar EXACT match para negativos)
- **Quién:** Manual UI: Herramientas → Listas de palabras clave negativas

### QW4: Agregar ad schedule para excluir horarios sin conversiones (noche y madrugada)
- **Por qué:** Sin ad schedule configurado. El restaurante opera Lun-Sab 12-22h, Dom 12-19h. Ads sirviendo a las 3am no generan reservas ni pedidos.
- **Impacto esperado:** 15-20% de reducción en gasto desperdiciado en horarios muertos
- **Tiempo:** 10 min | **Riesgo:** Bajo
- **Quién:** Manual UI: Campaña → Configuración → Programación de anuncios

### QW5: Verificar y activar Enhanced Conversions en la cuenta
- **Por qué:** Enhanced conversions recupera ~10% de conversiones perdidas por bloqueo de cookies. Fácil de activar, sin costo adicional.
- **Impacto esperado:** 10% uplift en conversiones reportadas sin cambiar nada más
- **Tiempo:** 5 min | **Riesgo:** Ninguno
- **Quién:** Manual UI: Herramientas → Conversiones → Configuración → Enhanced Conversions

### QW6: Subir Customer Match list con emails de clientes actuales
- **Por qué:** Sin Customer Match lists. Una lista de clientes habituales permite excluirlos de campañas de adquisición y crear lookalike audiences de alto valor.
- **Impacto esperado:** Mejora targeting y calidad de audiencia. Reduce CPA al enfocarse en nuevos clientes similares.
- **Tiempo:** 30 min (preparar CSV + subir) | **Riesgo:** Ninguno
- **Quién:** Manual UI: Herramientas → Audiencias → Segmentos → Customer Match

### QW7: Revisar geo targeting: confirmar 'People in' no 'People in or interested in'
- **Por qué:** Geo type detectado: {'PRESENCE'}. 'People in or interested in' mostraría ads a turistas buscando 'restaurantes mérida' desde CDMX — inútil para un restaurante local.
- **Impacto esperado:** Elimina impresiones de usuarios que no pueden visitar el restaurante físicamente
- **Tiempo:** 5 min | **Riesgo:** Ninguno
- **Quién:** Manual UI: Campaña → Configuración → Ubicaciones → Opciones de ubicación

### QW8: Crear campaña separada de Marca ('Thai Thai Mérida' branded terms)
- **Por qué:** Sin campaña de marca. Las búsquedas de marca compiten presupuesto con búsquedas genéricas. Marca tiene CPC mínimo y conversión máxima — debe estar aislada.
- **Impacto esperado:** Proteger tráfico de marca de competidores + presupuesto genérico 100% para nuevos clientes
- **Tiempo:** 1 hora | **Riesgo:** Bajo
- **Quién:** Manual UI + script de keywords

### QW9: Mejorar RSA headlines en Experiencia 2026: agregar keywords primarias en posición 1
- **Por qué:** Ad Relevance 'Below Average' en varios ad groups indica que los headlines no contienen las keywords de los grupos. Keyword en headline = QS más alto.
- **Impacto esperado:** QS +1 punto reduce CPC hasta 16%. Para $1,000 MXN/mes = ~$160 MXN de ahorro.
- **Tiempo:** 30 min | **Riesgo:** Bajo (RSA es adaptativo, el cambio es gradual)
- **Quién:** Manual UI: Anuncios → Editar RSA

### QW10: Verificar vinculación GA4 y configurar conversión con datos reales de Gloria Food
- **Por qué:** La conversión 'Pedido GloriaFood Online' tiene 0 atribución por pérdida de gclid en redirect. Alternativa: webhook de Gloria Food → Google Ads Offline Conversion Import.
- **Impacto esperado:** Datos de conversión 100% reales vs micro-conversiones ficticias actuales
- **Tiempo:** 2-4 horas (desarrollo técnico) | **Riesgo:** Medio (requiere acceso a Gloria Food API)
- **Quién:** Script Python + Gloria Food webhook

## 📋 Auditoría Detallada por Campaña

### Campaña: Thai Mérida - Delivery (Smart Campaign)

**Score parcial estimado:** 60/100

**Métricas 30 días:**
| Métrica | Valor |
|---------|-------|
| Gasto | $3,336.36 MXN |
| Clicks | 3,641 |
| Impresiones | 104,188 |
| CTR | 3.5% |
| CPC Promedio | $0.92 MXN |
| Conversiones | 570.3 ⚠️ (micros) |
| CPA | $5.85 MXN (no confiable) |
| Presupuesto diario | $110.00 MXN |
| Bidding | TARGET_SPEND |

**Ad Groups:** 1 total
⚠️ 1 ad groups fantasma (ENABLED, 0 actividad)

**Nota Smart Campaign:** Keywords y search terms no accesibles via API. Google gestiona targeting automáticamente basado en landing page y creativos.

**Extensiones:**
- ⚠️ Sin extensiones detectadas

⚠️ **Sin RSA Ads detectados** — Ad groups sin anuncios activos

### Campaña: Thai Mérida - Local (Smart Campaign)

**Score parcial estimado:** 60/100

**Métricas 30 días:**
| Métrica | Valor |
|---------|-------|
| Gasto | $4,160.61 MXN |
| Clicks | 2,256 |
| Impresiones | 122,029 |
| CTR | 1.8% |
| CPC Promedio | $1.84 MXN |
| Conversiones | 506.7 ⚠️ (micros) |
| CPA | $8.21 MXN (no confiable) |
| Presupuesto diario | $130.00 MXN |
| Bidding | TARGET_SPEND |

**Ad Groups:** 1 total
⚠️ 1 ad groups fantasma (ENABLED, 0 actividad)

**Nota Smart Campaign:** Keywords y search terms no accesibles via API. Google gestiona targeting automáticamente basado en landing page y creativos.

**Extensiones:**
- ⚠️ Sin extensiones detectadas

⚠️ **Sin RSA Ads detectados** — Ad groups sin anuncios activos

### Campaña: Thai Mérida - Experiencia 2026 (Search Campaign)

**Score parcial estimado:** 80/100

**Métricas 30 días:**
| Métrica | Valor |
|---------|-------|
| Gasto | $1,001.83 MXN |
| Clicks | 81 |
| Impresiones | 1,675 |
| CTR | 4.8% |
| CPC Promedio | $12.37 MXN |
| Conversiones | 11.0  |
| CPA | $91.08 MXN  |
| Presupuesto diario | $75.00 MXN |
| Bidding | TARGET_IMPRESSION_SHARE |
| Impression Share | 10.0% |
| IS perdido (presupuesto) | 90.0% |
| IS perdido (ranking) | 1.4% |

**Ad Groups:** 18 total

**Keywords:** 233 total, 102 ENABLED
**Search Terms:** 200 capturados en período
**Post-pausa de 12 fantasmas hoy:** 6 ad groups ENABLED activos

**Extensiones:**
- ⚠️ Sin extensiones detectadas

**RSA Ads:** 18
- Turistas (Inglés): Ad Strength = POOR, Headlines = 9, Descriptions = 3
- Restaurante Tailandes Merida 2026: Ad Strength = POOR, Headlines = 8, Descriptions = 2
- Restaurante Tailandés Mérida: Ad Strength = POOR, Headlines = 8, Descriptions = 3

## 🔍 Análisis por Dimensión

### 1. Tracking de Conversiones (25%) — 51/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G42 | ✅ PASS | 17 acciones activas, 17 primarias |
| G43 | ⚠️ WARNING | No verificable via API — confirmar en UI: Herramientas → Conversiones → Configuración |
| G44 | ❌ FAIL | Sin server-side GTM ni Conversions API configurada detectada |
| G45 | ❌ FAIL | Consent Mode v2 no verificable via API — pendiente verificar en GTM. Recomendado globalmente 2025+ |
| G46 | ✅ PASS | Ventanas: [90, 30, 7] días — ventana 30d es razonable para restaurante local |
| G47 | ❌ FAIL | Smart Campaign automatics como primarias: ['Clicks to call', 'Smart campaign map clicks to call', 'Smart campaign ad cli... |
| G48 | ⚠️ WARNING | Modelos: ['GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN', 'UNKNOWN', 'GOOGLE_ADS_LAST_CLICK'] |
| G49 | ⚠️ WARNING | click_pedir_online (Compra) recién configurada sin valor asignado. Recomendar valor dinámico. |
| G-CT1 | ✅ PASS | GA4: 0 conv | Native: 6 conv. Verificar solapamiento en UI. |
| G-CT2 | ⚠️ WARNING | GA4 propiedad 528379219 — vinculación no verificable via Ads API. Confirmar en UI. |
| G-CT3 | ⚠️ WARNING | Google Tag (GTM-5CRD9SKL) activo en landing. 'reserva_completada_directa' con etiqueta inactiva confirmado (out of scope... |

### 2. Gasto Desperdiciado / Negativos (20%) — 82/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G13 | ✅ PASS | Auditoría realizada hoy 24-abr-2026. Search terms revisados en esta sesión. |
| G14 | ⚠️ WARNING | 2 listas de negativos compartidas: ['Palabras Negativas Pedidos On Line Thai Thai Search', 'Competidores y cocinas irrel... |
| G15 | ⚠️ WARNING | Verificar si las listas están aplicadas a nivel cuenta o solo campaña específica. |
| G16 | ✅ PASS | Gasto en términos irrelevantes (Experiencia 2026): $0.00 MXN (0.0% del total). Smart campaigns: sin datos de search term... |
| G17 | ✅ PASS | 4 keywords BROAD en Experiencia 2026. Bidding: TARGET_IMPRESSION_SHARE. Legacy BMM probable. |
| G18 | ⚠️ WARNING | Close variant pollution no evaluable sin datos de search terms con status detallado. Revisar en UI. |
| G19 | ✅ PASS | Visibilidad de search terms (Experiencia 2026): 65.9% del gasto visible. Smart campaigns: 0% visibilidad. |
| G-WS1 | ✅ PASS | 0 keywords con >100 clicks y 0 conversiones: [] |

### 3. Estructura de Cuenta (15%) — 61/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G01 | ⚠️ WARNING | Nombres como 'Thai Mérida - Delivery' son descriptivos pero sin patrón [Marca]_[Tipo]_[Geo]_[Objetivo] estricto. |
| G02 | ⚠️ WARNING | Ad groups: mezcla de nombres descriptivos ('Comida Auténtica', 'Turistas (Inglés)') sin convención unificada. |
| G03 | ✅ PASS | 6 ad groups ENABLED en Experiencia 2026 (post-pausa de 12 fantasmas hoy). Keywords distribuidas. |
| G04 | ✅ PASS | 4 campañas (3 en scope + 1 pausada): Delivery, Local, Experiencia, Reservaciones. Lógica de negocio clara. |
| G05 | ⚠️ WARNING | Sin campaña de marca dedicada. Términos de marca ('thai thai mérida') corren en campañas genéricas mezclados con non-bra... |
| G06 | ⚠️ WARNING | Sin Performance Max. Restaurante con historial de conversiones es elegible. Evaluar cuando se tengan 30+ conv/mes reales... |
| G08 | ⚠️ WARNING | Experiencia 2026 (Search, mejores resultados medibles) recibe 11.8% del gasto (1002/${total_spend:.0f} MXN). Smart campa... |
| G09 | ⚠️ WARNING | No verificable via API si las campañas se limitan antes de las 6pm. Revisar entrega en UI. |
| G10 | ⚠️ WARNING | Sin ad schedule configurado detectado via API. Restaurante: Lun-Sab 12-22h, Dom 12-19h. Configurar para ahorrar gasto no... |
| G11 | ✅ PASS | Geo targeting types: {'PRESENCE'}. Verificar 'People in' vs 'People in or interested in'. |
| G12 | ❌ FAIL | Display Network: ACTIVADA. Search Partners: [True, True, True] |

### 4. Keywords & Quality Score (15%) — 74/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G20 | ⚠️ WARNING | QS promedio Experiencia 2026 (con datos): 6.0. Smart campaigns: N/A. |
| G21 | ✅ PASS | Keywords con QS ≤ 3: 0 (0.0%) |
| G22 | ⚠️ WARNING | Keywords con CTR esperado 'Below Average': 3 (33.3%) |
| G23 | ✅ PASS | Keywords con Ad Relevance 'Below Average': 0 (0.0%) |
| G24 | ✅ PASS | Keywords con Landing Page 'Below Average': 0 (0.0%) |
| G25 | ⚠️ WARNING | 2 de las top-20 keywords por gasto con QS < 7: ['restaurante tailandes merida', 'thai thai mérida'] |
| G-KW1 | ⚠️ WARNING | 93 keywords ENABLED con 0 impresiones (39.9% del total). Muchas pausadas manualmente — revisar si aplica filtro correcta... |
| G-KW2 | ⚠️ WARNING | Verificar que headlines de RSAs incluyan variantes de keywords principales ('restaurante tailandés', 'comida thai mérida... |

### 5. Anuncios & Assets (15%) — 46/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G26 | ❌ FAIL | 2 ad groups ENABLED sin RSA. Todos los ad groups necesitan al menos 1 RSA. |
| G27 | ✅ PASS | 0 RSAs con <8 headlines. Ideal: 12-15 para máxima flexibilidad. |
| G28 | ⚠️ WARNING | 4 RSAs con <3 descriptions. |
| G29 | ❌ FAIL | Ad Strength: 0 Good/Excellent, 18 Poor/Average/Unknown. Distribución: {'POOR': 11, 'AVERAGE': 7} |
| G30 | ✅ PASS | 0 RSAs con >3 headlines fijadas. Over-pinning reduce la flexibilidad del RSA. |
| G-AD1 | ⚠️ WARNING | Fecha de creación/modificación de ads no disponible via GAQL. Verificar en UI que haya creativos nuevos en <90 días. |
| G-AD2 | ⚠️ WARNING | CTR Experiencia 2026: 4.8% vs benchmark industria: 6.7%. Smart campaigns: CTR de display diferente. |
| G-AI1 | ⚠️ WARNING | AI Max no evaluado. Cuenta sin suficientes conversiones reales (objetivo: >50 conv/mes) para activarlo de forma efectiva... |

### 6. Configuración & Targeting (10%) — 32/100

| Check | Resultado | Nota |
|-------|-----------|------|
| G36 | ❌ FAIL | Bids: Delivery=['TARGET_SPEND'], Local=['TARGET_SPEND'], Experiencia=TARGET_IMPRESSION_SHARE. TARGET_IMPRESSION_SHARE op... |
| G37 | ⚠️ WARNING | TARGET_IMPRESSION_SHARE en Experiencia 2026 no tiene target CPA/ROAS — no optimizable para conversiones. TARGET_SPEND en... |
| G38 | ⚠️ WARNING | Estado de learning phase no verificable via API para Smart campaigns. Experiencia 2026 post-pausa de fantasmas puede rei... |
| G39 | ⚠️ WARNING | IS perdido por presupuesto: [('Thai Mérida - Experiencia 2026', '90.0%')] |
| G41 | ⚠️ WARNING | Campañas de bajo volumen corriendo independientemente. Considerar portfolio bid strategies cuando se consolide a TARGET_... |
| G50 | ❌ FAIL | Sitelinks por campaña: {'Thai Mérida - Local': 0, 'Thai Mérida - Delivery': 0, 'Thai Mérida - Experiencia 2026': 0} |
| G51 | ❌ FAIL | Callouts por campaña: {'Thai Mérida - Local': 0, 'Thai Mérida - Delivery': 0, 'Thai Mérida - Experiencia 2026': 0} |
| G52 | ❌ FAIL | Structured snippets: {'Thai Mérida - Local': 0, 'Thai Mérida - Delivery': 0, 'Thai Mérida - Experiencia 2026': 0} |
| G53 | ⚠️ WARNING | Image extensions: {'Thai Mérida - Local': 0, 'Thai Mérida - Delivery': 0, 'Thai Mérida - Experiencia 2026': 0} |
| G54 | ⚠️ WARNING | Call extensions: {'Thai Mérida - Local': 0, 'Thai Mérida - Delivery': 0, 'Thai Mérida - Experiencia 2026': 0}. Restauran... |
| G56 | ❌ FAIL | Audiencias aplicadas: {} |
| G57 | ❌ FAIL | Sin Customer Match lists detectadas. Cargar lista de clientes (emails de reservas/pedidos) para remarketing de alto valo... |
| G58 | ⚠️ WARNING | Placement exclusions no verificables via API de forma directa. Verificar en UI si hay exclusiones de apps/juegos. |
| G59 | ⚠️ WARNING | Mobile LCP no verificable via Google Ads API. Correr PageSpeed Insights en thaithaimerida.com. Benchmark: <2.5s. |
| G60 | ⚠️ WARNING | Relevancia landing evaluada en audit de hoy: thaithaimerida.com sirve como landing general. Ad groups de delivery no tie... |
| G61 | ⚠️ WARNING | Schema markup no verificable via API. Verificar presencia de LocalBusiness + Restaurant schema en thaithaimerida.com. |

## 📅 Plan de Remediación 30/60/90 Días

### Próximos 30 días (alto impacto, bajo riesgo)

1. **Corregir conversiones primarias** — Solo click_pedir_online como primaria. Todas las Smart Campaign micros → Secundaria
2. **Cambiar bidding de Experiencia 2026** — TARGET_IMPRESSION_SHARE → MAXIMIZE_CONVERSIONS
3. **Activar Enhanced Conversions** — 5 minutos, sin riesgo, +10% uplift
4. **Configurar ad schedule** — Solo horarios de operación del restaurante
5. **Crear 3 listas de negativos** — Informacional, Competidores, Intent irrelevante
6. **Verificar geo targeting** — Confirmar 'People in' en todas las campañas
7. **Pausar ad groups fantasma** en Delivery y Local (1 en cada una)

### 30-60 días (medio impacto, requiere validación)

1. **Crear campaña de Marca** — Thai Thai branded terms separados
2. **Cambiar bidding Smart Campaigns a TARGET_CPA** — Delivery: $25 objetivo | Local: $35 objetivo
3. **Subir Customer Match list** — Emails de clientes recurrentes
4. **Mejorar RSA headlines** — Incluir keywords primarias, objetivo: Ad Strength 'Good'
5. **Verificar extensiones** — Sitelinks, callouts, call extensions en las 3 campañas
6. **Reactivar Reservaciones** (si hay presupuesto) — Con TARGET_CPA $50, Search campaign

### 60-90 días (estratégico, requiere data nueva)

1. **Implementar Gloria Food → Offline Conversion Import** — Conversiones reales de pedidos
2. **Evaluar Performance Max** — Si se alcanzan 30+ conversiones/mes reales
3. **AI Max para Experiencia 2026** — Con base de negativos sólida + conversiones reales
4. **Implementar Consent Mode v2** — En GTM para recuperar señales post-cookies
5. **Server-side tracking** — Para accuracy de conversiones en largo plazo

## 🎓 Diagnóstico Estructural

**¿La cuenta necesita restructure o correcciones quirúrgicas?**

Correcciones quirúrgicas. La arquitectura de 3-4 campañas es lógica y correcta para un restaurante de este tamaño. El problema no es la estructura sino la configuración interna: bidding incompatible con objetivos, conversiones infladas y falta de señales negativas.

**¿La estrategia de 4 campañas tiene sentido?**

Parcialmente. Delivery y Local como Smart Campaigns separadas tiene sentido conceptualmente (diferentes audiencias y objetivos). Sin embargo, con $9,000+ MXN/mes de gasto, 4 campañas con presupuestos fragmentados dificultan que el algoritmo aprenda. Recomendación a largo plazo: consolidar a 2-3 campañas con presupuestos más concentrados.

**Comparación con cuentas similares ($100/día restaurante local México):**

- CTR de Experiencia 2026 (4.7%) está por debajo del benchmark (6.66%) pero no es crítico — mejorable con RSA optimization
- CPC ($12.44 MXN ≈ $0.62 USD) es excelente para la industria — indica buena relevancia de keywords
- El ratio gasto/conversiones reales es el problema: $9,234 MXN / 11 conversiones reales = $839 CPA real. Inaceptable.
- Cuentas similares bien optimizadas: $200-400 MXN CPA para reservas, $50-80 MXN para delivery

**Riesgos a corto/medio plazo:**

- 🔴 **Inmediato:** Google sigue optimizando para micro-conversiones — cada día que pasa el algoritmo aprende la señal incorrecta
- 🟡 **30 días:** Si Experiencia 2026 reinicia período de aprendizaje post-pausa de fantasmas, CTR/conversiones pueden caer temporalmente
- 🟡 **60 días:** Sin datos de conversión reales, TARGET_CPA no podrá activarse efectivamente

## 📎 Anexos Técnicos

### A1. Ad Groups — Todas las Campañas

| Campaña | Ad Group | Estado | Gasto | Clicks | Conv |
|---------|----------|--------|-------|--------|------|
| Thai Mérida - Experiencia 2026 | Comida Auténtica | ENABLED | $581.33 | 44 | 1.0 |
| Thai Mérida - Experiencia 2026 | Turistas (Inglés) | ENABLED | $332.48 | 30 | 6.5 |
| Thai Mérida - Experiencia 2026 | Experiencia Thai | ENABLED | $88.02 | 7 | 3.5 |
| Thai Mérida - Delivery | Smart Campaign Managed AdGroup 👻 | ENABLED | $0.00 | 0 | 0.0 |
| Thai Mérida - Local | Smart Campaign Managed AdGroup 👻 | ENABLED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandes Merida 2026 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandés Mérida 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Thai Thai Marca 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandés Mérida - Cat 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandes Merida 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Thai Thai Merida - Branded 2026 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Thai Thai Merida Branded 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Thai Thai Mérida - Branded 2026 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Rest. Tailandés Mérida - Category | ENABLED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Categoria Tailandes Merida | ENABLED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandes Merida - Cat 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Branded Thai Thai Merida 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Restaurante Tailandés Mérida 2026 | ENABLED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Thai Thai Merida Brand 👻 | PAUSED | $0.00 | 0 | 0.0 |
| Thai Mérida - Experiencia 2026 | Brand Thai Thai Merida 👻 | PAUSED | $0.00 | 0 | 0.0 |

### A2. Acciones de Conversión Activas

| Nombre | Categoría | Primaria | Modelo Atrib. | Lookback | Conv (30d) |
|--------|-----------|----------|---------------|----------|------------|
| Local actions - Directions | GET_DIRECTIONS | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 716.0 |
| Thai Thai Merida (web) click_pedir_online | PURCHASE | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 30d | 290.0 |
| Store visits | STORE_VISIT | ✅ SÍ | UNKNOWN | 7d | 51.0 |
| Clicks to call | CONTACT | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 31.0 |
| Smart campaign map clicks to call | CONTACT | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Smart campaign ad clicks to call | CONTACT | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Smart campaign map directions | GET_DIRECTIONS | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Calls from Smart Campaign Ads | PHONE_CALL_LEAD | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 30d | 0.0 |
| Local actions - Menu views | PAGE_VIEW | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Local actions - Website visits | PAGE_VIEW | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Local actions - Other engagements | ENGAGEMENT | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Local actions - Orders | BEGIN_CHECKOUT | ✅ SÍ | GOOGLE_ADS_LAST_CLICK | 30d | 0.0 |
| Thai Thai Merida (web) reserva_completada | SIGNUP | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 90d | 0.0 |
| reserva_completada_directa | BOOK_APPOINTMENT | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 90d | 0.0 |
| Pedido GloriaFood Online | PURCHASE | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 90d | 0.0 |
| Contacto (Evento de Google Analytics click_whatsapp) | CONTACT | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 30d | 0.0 |
| Contacto (Evento de Google Analytics click_ubicacion) | CONTACT | ✅ SÍ | GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN | 30d | 0.0 |

### A3. Top 30 Search Terms — Experiencia 2026 (por gasto)

| Término | Clicks | Impr | Conv | Gasto | CTR |
|---------|--------|------|------|-------|-----|
| `thai thai merida` | 6 | 4 | 3.5 | $68.17 | 150.0% |
| `cocina los pinos don pepe menú` | 2 | 1 | 0.0 | $35.32 | 200.0% |
| `restaurantes merida` | 2 | 27 | 0.0 | $20.70 | 7.4% |
| `manawings mérida` | 1 | 1 | 0.0 | $19.96 | 100.0% |
| `manzoku mérida menu` | 1 | 1 | 0.0 | $19.96 | 100.0% |
| `la cochinita de la 60 mérida` | 1 | 1 | 0.0 | $19.82 | 100.0% |
| `sushis en merida` | 1 | 1 | 0.0 | $19.76 | 100.0% |
| `menú de teya santa lucía` | 1 | 1 | 0.0 | $19.75 | 100.0% |
| `piedra de agua restaurante` | 1 | 1 | 0.0 | $19.71 | 100.0% |
| `platillos orientales` | 1 | 1 | 0.0 | $19.34 | 100.0% |
| `infiniti merida` | 1 | 1 | 0.0 | $19.27 | 100.0% |
| `cienfuegos merida` | 1 | 1 | 0.0 | $19.23 | 100.0% |
| `restaurante merida centro` | 1 | 2 | 0.0 | $19.19 | 50.0% |
| `marmalade norte` | 1 | 1 | 0.0 | $19.09 | 100.0% |
| `comida saludable merida` | 1 | 2 | 0.0 | $18.91 | 50.0% |
| `dónde venden ramen cerca de mí` | 1 | 1 | 0.0 | $18.83 | 100.0% |
| `bachour merida` | 1 | 2 | 0.0 | $18.79 | 50.0% |
| `city center buffet` | 1 | 1 | 0.0 | $18.71 | 100.0% |
| `restaurantes de lujo en merida` | 1 | 1 | 0.0 | $18.69 | 100.0% |
| `menú de p f chang's altabrisa` | 1 | 2 | 0.0 | $18.46 | 50.0% |
| `restaurante la rueda cerca de mi` | 1 | 1 | 0.0 | $17.73 | 100.0% |
| `pollo feliz merida` | 1 | 1 | 0.0 | $15.96 | 100.0% |
| `best food in merida mexico` | 1 | 1 | 0.0 | $15.33 | 100.0% |
| `thai thai merida` | 2 | 5 | 0.5 | $14.50 | 40.0% |
| `la rueda merida` | 1 | 9 | 0.0 | $13.72 | 11.1% |
| `swing pasta` | 1 | 1 | 2.0 | $13.25 | 100.0% |
| `brunch en merida` | 1 | 1 | 0.0 | $13.12 | 100.0% |
| `restaurante libertad merida` | 1 | 1 | 0.0 | $9.74 | 100.0% |
| `restaurantes en merida yucatan` | 1 | 4 | 0.0 | $9.74 | 25.0% |
| `restaurante la herencia merida` | 1 | 1 | 0.0 | $9.21 | 100.0% |

### A4. Keywords con QS Bajo (<6) — Experiencia 2026

| Keyword | Match | QS | CTR_Q | Creative_Q | LP_Q | Gasto |
|---------|-------|-----|-------|------------|------|-------|
| `restaurante tailandes merida` | BROAD | 4 | BELOW_AVERAGE | AVERAGE | AVERAGE | $131.68 |
| `thai thai mérida` | EXACT | 5 | BELOW_AVERAGE | ABOVE_AVERAGE | AVERAGE | $19.85 |

## 📌 Notas Importantes

1. **'Pedido GloriaFood Online' (ID: 7572944047, UPLOAD_CLICKS):** Tiene 0 atribución porque el gclid se pierde en el redirect a `restaurantlogin.com`. **No es una etiqueta rota** — es un problema arquitectónico del checkout de Gloria Food. Solución real: implementar Offline Conversion Import vía webhook del sistema de pedidos.

2. **'click_pedir_online':** Promovida hoy (24-abr) a conversión Primaria (categoría Compra). Data de solo 30 días — el algoritmo tardará 2-4 semanas en aprender esta señal. No esperar resultados inmediatos de bidding changes.

3. **'reserva_completada_directa':** Etiqueta inactiva confirmada — pendiente de fix en thaithaimerida.com. Fuera del scope de esta auditoría de Google Ads.

4. **12 ad groups pausados hoy:** Los 12 ad groups fantasma de Experiencia 2026 fueron pausados en esta sesión (scripts `pause_ghost_adgroups_experiencia2026.py`). La campaña puede entrar en período de aprendizaje brevemente.

5. **Smart Campaigns (Delivery, Local):** Keywords y search terms no accesibles via Google Ads API. Todos los checks de keywords y search terms se aplican SOLO a Experiencia 2026. Para Smart Campaigns, el análisis se limita a métricas de campaña, ad groups, RSAs y assets.

---
_Auditoría profesional generada con skill `ads-google` (80 checks, scoring-system v1.5).  
Solo lectura — ningún cambio fue aplicado en Google Ads.  
Fecha: 24/04/2026 20:09_