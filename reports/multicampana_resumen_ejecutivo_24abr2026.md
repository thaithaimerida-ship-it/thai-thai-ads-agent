# Resumen Ejecutivo — Audit Multi-Campaña Thai Thai (24 abr 2026)

**Período:** 2026-03-25 → 2026-04-24  
**Cuenta:** 4021070209  
**Campañas auditadas:** 4 (Delivery, Local, Reservaciones, Experiencia 2026)  
**Generado:** 24/04/2026 19:33  

## Estado Actual de las 4 Campañas

| Campaña | Tipo | Estado | Gasto 30d | Clicks | Conv | CPA | Ad Groups | Salud |
|---------|------|--------|-----------|--------|------|-----|-----------|-------|
| Experiencia 2026 | Search | ENABLED | $1001.83 | 81 | 11.0 | $91.08 | 18 (12 pausados hoy) | 🟡 |
| Delivery | Smart | ENABLED | $3336.36 | 3641 | 570.3 | $5.85 | 1 (1 👻) | 🟢 |
| Local | Smart | ENABLED | $4141.72 | 2245 | 506.7 | $8.17 | 1 (1 👻) | 🟢 |
| Reservaciones | Search | PAUSED | $754.28 | 65 | 3.0 | $251.43 | 2 (1 👻) | ⚫ |

**TOTALES:** $9,234.19 MXN gastados | 6,032 clicks | 1091.0 conversiones | CPA global: $8.46 MXN

## Top 5 Hallazgos Críticos

1. **Thai Mérida - Reservaciones está PAUSADA** — No genera tráfico. Decisión urgente: ¿se reactiva o se migran sus keywords a Experiencia 2026? El objetivo de reservas online es el más valioso (CPA objetivo: $50 MXN).

2. **15 ad groups fantasma** en total (4 campañas) — Fragmentación severa del presupuesto. Hoy pausamos los 12 de Experiencia 2026. Revisar las demás campañas para hacer lo mismo.

3. **18 keywords duplicadas entre campañas** — Las campañas compiten entre sí en la misma subasta, inflando CPCs. Ejemplos: `comida tailandesa mérida`, `reservar mesa tailandesa mérida`, `reservar comida tailandesa mérida`

4. **13 conversión(es) primaria(s) con 0 registros** en 30d: Smart campaign map clicks to call, Smart campaign ad clicks to call, Smart campaign map directions — Riesgo crítico: Google no tiene señal para optimizar las campañas Search.


## Acciones Recomendadas — Fase 1 (Alto impacto, riesgo bajo)

> ⚠️ Solo recomendaciones — nada fue ejecutado en esta auditoría.

- **Decidir el futuro de Reservaciones** — Reactivar con TARGET_CPA ($50) o migrar keywords a Experiencia 2026
- **Pausar 1 ad group(s) fantasma en Delivery** — Sin actividad en 30d, consumen presupuesto por fragmentación
- **Pausar 1 ad group(s) fantasma en Local** — Sin actividad en 30d, consumen presupuesto por fragmentación
- **Pausar 1 ad group(s) fantasma en Reservaciones** — Sin actividad en 30d, consumen presupuesto por fragmentación
- **Agregar negativos cruzados entre campañas** para los 18 keywords duplicadas — Elimina canibalización inter-campaña

## Acciones Recomendadas — Fase 2 (Medio impacto, requiere validación)

- **Delivery y Local:** Cambiar de TARGET_SPEND a TARGET_CPA con objetivos claros ($25 para delivery, $35 para local)
- **Delivery:** Verificar integración Gloria Food → conversión → Smart Campaign (el tracking puede estar roto)
- **Consolidación de presupuesto:** Con $85/día fragmentado en 4 campañas, considerar concentrar en 2-3 campañas de mayor ROI

## Acciones Recomendadas — Fase 3 (Necesita más análisis)

- Evaluar si tener Delivery + Local como Smart Campaigns separadas tiene sentido o si una sola campaña Smart cubre ambos objetivos
- Analizar datos de GA4 para confirmar que las conversiones registradas en Google Ads corresponden a pedidos reales
- Revisar la landing de Experiencia 2026 — el CPA de $91 MXN sugiere que la página puede tener problemas de conversión
- Considerar una campaña Performance Max cuando el volumen de conversiones sea suficiente (>50/mes)

## Comparación con Experiencia 2026

**Patrones repetidos en todas las campañas:**

| Problema | Experiencia 2026 | Delivery | Local | Reservaciones |
|----------|------------------|----------|-------|---------------|
| Ad groups fantasma | ✅ Sí (12/18) | ✅ Sí | ✅ Sí | ✅ Sí |
| Keywords duplicadas | ✅ Sí (21) | Smart (N/A) | Smart (N/A) | ❌ No |
| CPA sobre objetivo | ✅ Sí ($91) | ❌ No | ❌ No | N/A (pausada) |
| Conversiones primarias 0 | Parcial | ✅ Sí | ✅ Sí | ✅ Sí |

**Conclusión:** La fragmentación excesiva de ad groups y la falta de datos de conversión suficientes son problemas estructurales en todas las campañas, no aislados a Experiencia 2026.

## Resumen Numérico del Cleanup Potencial

| Métrica | Valor |
|---------|-------|
| Ad groups fantasma (4 campañas) | 15 |
| Ad groups ya pausados hoy (Experiencia 2026) | 12 |
| Keywords duplicadas inter-campaña | 18 |
| Terms de búsqueda candidatos a negativo | 0 |
| Gasto estimado en terms sin conversión | $0.00 MXN |
| Gasto total 30d (4 campañas) | $9,234.19 MXN |
| Conversiones totales 30d | 1091.0 |
| CPA global actual | $8.46 MXN |

**Impacto estimado si se ejecuta Fase 1:**

- Pausar 3 ad groups fantasma adicionales → presupuesto concentrado en grupos activos
- Resolver 18 keywords inter-campaña → reducción de CPCs por eliminación de auto-competencia
- Reactivar Reservaciones con TARGET_CPA → potencial de capturar el intent de reserva de mayor valor

---
_Resumen ejecutivo generado automáticamente. Solo lectura — ningún cambio fue aplicado. 24/04/2026 19:33_