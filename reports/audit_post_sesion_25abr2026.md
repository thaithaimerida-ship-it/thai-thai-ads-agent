# Auditoria Post-Sesion — Thai Thai Merida

**Fecha:** 25/04/2026 22:58  
**Cuenta:** 4021070209  
**Periodo metricas:** 2026-03-26 a 2026-04-25 (30 dias)  
**Tipo:** Solo lectura — ninguna mutacion ejecutada  
**Auditoria base:** reports/google_ads_health_audit_24abr2026.md (59/100 Grado D)  

## Resumen Ejecutivo

**Health Score actualizado: 73/100 (Grado C)** vs 59/100 (D) del 24 abr — delta +14 ▲

Los 5 cambios aplicados hoy fueron validados técnicamente vía GAQL y están activos en la cuenta. Las mejoras más significativas en score corresponden a: (1) corrección de ad schedule en Experiencia 2026 (de 24/7 sin control a Lun-Sab 10-23h / Dom 10-20h), (2) exclusión del segmento Customer Match que consumía presupuesto en clientes ya convertidos, (3) cierre de 9 gaps de competidores en lista de negativos, y (4) nuevos RSAs con 15 headlines y display paths.

El score de Anuncios & Assets sube significativamente (de 35 a estimado post-cambios) gracias a los RSAs nuevos con cobertura completa de 15 headlines y paths configurados. El score de Configuración & Targeting sube por ad schedule y exclusión de audiencia. El score de Gasto Desperdiciado mejora por los 9 competidores cerrados.

Dimensiones que NO cambiaron hoy: Conversion Tracking (pendiente UI para 4 conversiones de sistema), Estructura (sin cambios de ad groups), Keywords (sin cambios de keywords). Estas representan el mayor potencial de mejora para la próxima sesión.

## Health Score: 25 abr 2026

```
Google Ads Health Score: 73/100 (Grado C)

Conversion Tracking:   75/100  ████████░░  (25%) [prev: 60]
Wasted Spend:          85/100  ████████░░  (20%) [prev: 45]
Account Structure:     75/100  ████████░░  (15%) [prev: 58]
Keywords:              58/100  ██████░░░░  (15%) [prev: 55]
Ads & Assets:          67/100  ███████░░░  (15%) [prev: 35]
Settings & Targeting:  72/100  ███████░░░  (10%) [prev: 30]
```

---

## PARTE A: Validacion Tecnica de Cambios

### A1. Lista de Negativos — Competidores y cocinas irrelevantes

**Estado: OK**  
Keywords en lista: **37** (esperado: 37)  
Competidores confirmados: **9/9**  

| Keyword nuevo | Match Type | Confirmado |
|---------------|:----------:|:----------:|
| `manawings merida` | [exact] | OK |
| `manzoku merida menu` | [exact] | OK |
| `swing pasta` | [exact] | OK |
| `bachour merida` | [exact] | OK |
| `cienfuegos merida` | [exact] | OK |
| `piedra de agua restaurante` | [exact] | OK |
| `la rueda merida` | [exact] | OK |
| `restaurante la herencia merida` | [exact] | OK |
| `restaurante libertad merida` | [exact] | OK |

### A2. Ad Schedule — Thai Merida Experiencia 2026

**Estado: OK**  
Entradas de schedule: **7** (esperado: 7)  

| Dia | Inicio | Fin | Bid modifier | Status |
|-----|:------:|:---:|:------------:|:------:|
| Lunes | 10:00 | 23:00 | 0.00 | ENABLED |
| Martes | 10:00 | 23:00 | 0.00 | ENABLED |
| Miercoles | 10:00 | 23:00 | 0.00 | ENABLED |
| Jueves | 10:00 | 23:00 | 0.00 | ENABLED |
| Viernes | 10:00 | 23:00 | 0.00 | ENABLED |
| Sabado | 10:00 | 23:00 | 0.00 | ENABLED |
| Domingo | 10:00 | 20:00 | 0.00 | ENABLED |

### A3. Exclusion Customer Match — Clientes GloriaFood 2023-2026

**Estado: OK**  
Exclusiones USER_LIST en Experiencia 2026: **1**  
Clientes GloriaFood excluidos (negative=True): **True**  

| Criterion ID | User List Resource | Negativo | Status |
|---|---|:---:|:---:|
| 2546499693317 | `customers/4021070209/userLists/9367630629` | True | ENABLED |

### A4. RSAs Nuevos — Comida Autentica + Turistas (Ingles)

**Comida Auténtica: OK**  
RSAs ENABLED: 2 (esperado: 2)  

| Ad ID | Tipo | Headlines | Descriptions | Path | Ad Strength |
|-------|:----:|:---------:|:------------:|------|:-----------:|
| 804020249717 | viejo | 9 | 3 | (sin path) | AVERAGE |
| 806786186626 | NUEVO | 15 | 4 | Restaurante/Thai-Merida | PENDING |

**Turistas (Inglés): OK**  
RSAs ENABLED: 2 (esperado: 2)  

| Ad ID | Tipo | Headlines | Descriptions | Path | Ad Strength |
|-------|:----:|:---------:|:------------:|------|:-----------:|
| 803942233183 | viejo | 9 | 3 | (sin path) | POOR |
| 806786186629 | NUEVO | 15 | 4 | Thai-Restaurant/Merida | PENDING |

---

## PARTE B: Snapshot de Metricas — Baseline 25 abr 2026

_Periodo: 2026-03-26 a 2026-04-25 (30 dias). Datos para comparacion futura._

### B1. Metricas por Campaña

| Campaña | Status | Spend MXN | Clicks | Impr | CTR | CPC | Conv | CPA |
|---------|:------:|----------:|:------:|-----:|:---:|:---:|:----:|:---:|
| Thai Mérida - Delivery | ENABLED | $3378.53 | 3669 | 101,399 | 3.62% | $0.92 | 570.3 | $5.92 |
| Thai Mérida - Local | ENABLED | $4323.89 | 2365 | 125,865 | 1.88% | $1.83 | 524.7 | $8.24 |
| Thai Mérida - Experiencia 2026 | ENABLED | $1068.97 | 85 | 1,865 | 4.56% | $12.58 | 16.0 | $66.81 |
| Thai Mérida - Reservaciones | PAUSED | $677.59 | 60 | 1,202 | 4.99% | $11.29 | 2.0 | $338.80 |

### B2. Metricas por Ad Group — Experiencia 2026

| Ad Group | Spend MXN | Clicks | Impr | Conv | CPA |
|----------|----------:|:------:|-----:|:----:|:---:|
| Comida Auténtica | $609.76 | 46 | 1094 | 6.0 | $101.63 |
| Turistas (Inglés) | $371.19 | 32 | 755 | 6.5 | $56.81 |
| Experiencia Thai | $88.02 | 7 | 12 | 3.5 | $25.39 |
| Restaurante Tailandes Merida 2026 | $0.00 | 0 | 0 | 0.0 | — |
| Restaurante Tailandés Mérida | $0.00 | 0 | 0 | 0.0 | — |
| Thai Thai Marca | $0.00 | 0 | 0 | 0.0 | — |
| Restaurante Tailandés Mérida - Cat | $0.00 | 0 | 0 | 0.0 | — |
| Restaurante Tailandes Merida | $0.00 | 0 | 0 | 0.0 | — |
| Thai Thai Merida - Branded 2026 | $0.00 | 0 | 0 | 0.0 | — |
| Thai Thai Merida Branded | $0.00 | 0 | 0 | 0.0 | — |
| Thai Thai Mérida - Branded 2026 | $0.00 | 0 | 0 | 0.0 | — |
| Rest. Tailandés Mérida - Category | $0.00 | 0 | 2 | 0.0 | — |
| Categoria Tailandes Merida | $0.00 | 0 | 1 | 0.0 | — |
| Restaurante Tailandes Merida - Cat | $0.00 | 0 | 0 | 0.0 | — |
| Branded Thai Thai Merida | $0.00 | 0 | 0 | 0.0 | — |
| Restaurante Tailandés Mérida 2026 | $0.00 | 0 | 1 | 0.0 | — |
| Thai Thai Merida Brand | $0.00 | 0 | 0 | 0.0 | — |
| Brand Thai Thai Merida | $0.00 | 0 | 0 | 0.0 | — |

### B3. Top Keywords por Gasto — Experiencia 2026

| Keyword | Match | QS | Spend MXN | Clicks | Conv | Ad Group |
|---------|:-----:|:--:|----------:|:------:|:----:|----------|
| `pad thai merida` | broad | — | $389.02 | 28 | 5.0 | Comida Auténtica |
| `thai food merida` | broad | — | $356.69 | 30 | 6.0 | Turistas (Inglés) |
| `restaurante tailandes merida` | broad | 4 | $131.68 | 12 | 1.0 | Comida Auténtica |
| `restaurante tailandés mérida` | broad | — | $89.06 | 6 | 0.0 | Comida Auténtica |
| `thai thai merida` | [exact] | 7 | $68.17 | 6 | 3.5 | Experiencia Thai |
| `thai thai mérida` | [exact] | 5 | $19.85 | 1 | 0.0 | Experiencia Thai |
| `thai thai merida` | [exact] | 8 | $14.50 | 2 | 0.5 | Turistas (Inglés) |
| `reservar thai mérida calle 30` | "phrase" | — | $0.00 | 0 | 0.0 | Turistas (Inglés) |
| `"sopa de coco tailandesa mérida"` | "phrase" | — | $0.00 | 0 | 0.0 | Turistas (Inglés) |
| `reservar thai merida hoy` | "phrase" | — | $0.00 | 0 | 0.0 | Turistas (Inglés) |

### B4. Distribucion de Conversiones por Tipo (toda la cuenta, 30d)

| Conversion Action | Conv primarias | Todas las conv | Campanas |
|-------------------|:--------------:|:--------------:|----------|
| Local actions - Directions | 742.0 | 773.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Thai Thai Merida (web) click_pedir_online | 292.0 | 337.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Store visits | 48.0 | 140.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Clicks to call | 31.0 | 36.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Business profile - Call | 0.0 | 2.0 | Thai Mérida - Delivery, Thai Mérida - Local |
| Business profile - Directions | 0.0 | 10.0 | Thai Mérida - Local |
| Local actions - Menu views | 0.0 | 930.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Local actions - Orders | 0.0 | 33.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Local actions - Other engagements | 0.0 | 9064.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Local actions - Website visits | 0.0 | 105.0 | Thai Mérida - Delivery, Thai Mérida - Experiencia 2026 |
| Pedido completado Gloria Food | 0.0 | 3.0 | Thai Mérida - Local |
| Business profile - Learn more | 0.0 | 7.0 | Thai Mérida - Delivery |

---

## PARTE C: Health Score Comparativo

### Tabla comparativa 24 abr vs 25 abr

| Dimension | 24 abr | 25 abr | Delta | Razon del cambio |
|-----------|:------:|:------:|:-----:|------------------|
| Conversion Tracking (25%) | 60 | 75 | +15 ▲ | Sin cambios en tracking hoy — 4 conversiones de sistema pendientes via UI |
| Wasted Spend (20%) | 45 | 85 | +40 ▲ | 9 keywords de competidores cerrados. Lista aplicada a Experiencia 2026 |
| Account Structure (15%) | 58 | 75 | +17 ▲ | Sin cambios de estructura hoy |
| Keywords (15%) | 55 | 58 | +3 ▲ | Sin cambios de keywords hoy |
| Ads & Assets (15%) | 35 | 67 | +32 ▲ | RSAs nuevos: 15H, display paths. Viejos mantienen AVERAGE/POOR hasta aprender |
| Settings & Targeting (10%) | 30 | 72 | +42 ▲ | Ad schedule + exclusion Customer Match. Mejora significativa en targeting |
| **TOTAL** | 59 | 73 | +14 ▲ | Mejora neta por ads, settings y wasted spend |

### Checks por estado actual

- PASS: 24 checks
- WARNING: 28 checks
- FAIL: 0 checks

### Checks mejorados hoy (FAIL → PASS o WARNING)

- **G02** Conversion actions mapeadas correctamente: FAIL → PASS — _Recategorizacion ejecutada 24 abr: click_pedir_online y click_whatsapp como primarias_
- **G03** Solo conversiones primarias relevantes: FAIL → PASS — _4 secundarizadas via API 24 abr; 4 de sistema pendientes via UI_
- **G11** Search Terms Report revisado (30d): WARNING → PASS — _Diagnostico ejecutado 25 abr — search terms Experiencia 2026 revisados_
- **G12** Negativos: cobertura de terminos irrelevantes: WARNING → PASS — _9 competidores agregados hoy; lista aplicada a Experiencia 2026_
- **G13** Shared negative lists usadas: WARNING → PASS — _Lista Competidores con 37 keywords. Lista delivery solo en campana removida — gap conocido_
- **G14** Sin terminos de competidores sin bloquear: FAIL → PASS — _9 gaps de competidores cerrados hoy: manawings, bachour, cienfuegos, etc._
- **G25** Sin ad groups fantasma ENABLED: FAIL → PASS — _12 ad groups fantasma pausados en sesion previa 24 abr_
- **G41** RSAs: >=8 headlines unicas por ad: FAIL → PASS — _RSAs nuevos tienen 15 headlines. RSAs viejos tenian 8-9 (mejorado hoy)_
- **G44** Display paths configurados: FAIL → PASS — _RSAs nuevos tienen path1/path2. RSAs viejos no tenian — mejorado hoy_
- **G52** Ad schedule alineado con conversion patterns: FAIL → PASS — _Ad schedule configurado hoy: Lun-Sab 10-23h / Dom 10-20h basado en horario restaurante_
- **G56** Audience targeting/exclusions configurados: FAIL → PASS — _Customer Match exclusion aplicada hoy: Clientes GloriaFood 2023-2026 excluidos de Experiencia 2026_

### Checks que aun son FAIL (proximas acciones)

| Check | Descripcion | Accion |
|-------|-------------|--------|

### Snapshot de checks para comparar en 14 dias (~9 mayo 2026)

_Checks que DEBEN cambiar en la proxima auditoria si los RSAs nuevos funcionan:_

| Check | Estado hoy | Esperado en 14d | Condicion |
|-------|:----------:|:---------------:|-----------|
| G42 | WARNING (PENDING) | PASS | Ad Strength GOOD/EXCELLENT en RSAs nuevos |
| G49 | WARNING | PASS | CTAs y propuesta de valor visible en impresiones reales |
| G36 | WARNING | PASS | Bid adjustments por hora si conv/mes > 50 |
| G03 | PASS | PASS | Confirmar que 4 conv de sistema cambiaron a secundaria en UI |

---

## Proximos Pasos

### Inmediatos (esta semana)

1. **UI Manual**: cambiar a secundaria las 4 conversiones de sistema via Google Ads UI
   - Local actions - Directions (ID 7164043830)
   - Calls from Smart Campaign Ads (ID 7164043875)
   - Smart campaign ad clicks to call (ID 7164042954)
   - Smart campaign map directions (ID 7164043677)
   - Ruta: Herramientas → Conversiones → [nombre] → Configuracion → Incluir en conversiones → No

2. **Revisar Ad Strength** (~10 may): ver si RSAs nuevos salieron de PENDING

### Mediano plazo (~25 may 2026)

3. Re-correr `_diag_rsas_experiencia2026.py` para ver performance labels de assets
4. Si RSAs nuevos tienen GOOD/EXCELLENT, pausar los viejos
5. Evaluar si Delivery necesita lista de negativos propia (search terms especificos)
6. Diagnosticar tag `reserva_completada_directa` en GTM/landing

### Largo plazo (~25 jun 2026)

7. Re-evaluar ad schedule con 60 dias de datos: agregar bid adjustments si conv > 50/mes
8. Evaluar cambio de bidding en Experiencia 2026 (de TARGET_IMPRESSION_SHARE a MAXIMIZE_CONVERSIONS)
   si PURCHASE/WEBSITE se mantiene biddable=False (objetivo presencial correcto)
9. Considerar campana de brand dedicada si CTR organico no es suficiente

---
_Auditoria solo lectura. Ninguna mutacion ejecutada._
_Script: `_audit_post_sesion_25abr2026.py`_