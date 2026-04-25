# Configuracion Ad Schedule — Thai Merida Experiencia 2026

**Fecha/hora:** 25 de April de 2026, 12:30:23  
**Cuenta:** 4021070209  
**Campaña:** Thai Merida - Experiencia 2026  
**Operacion:** `CampaignCriterionService.mutate_campaign_criteria`  
**Bid adjustments:** Ninguno (1.0) — decision consciente por bajo volumen estadistico  

**Estado:** EXITOSO  

## Schedule Anterior

_La campana no tenia ad schedule configurado (activa 24/7 por defecto)._

## Schedule Nuevo Aplicado

_Basado en: Lun-Sab 12-22h / Dom 12-19h (horario restaurante) + 2h planificacion manana + 1h noche._

| Dia | Hora inicio | Hora fin | Bid modifier | Nota |
|-----|:-----------:|:--------:|:------------:|------|
| Lunes | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Martes | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Miercoles | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Jueves | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Viernes | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Sabado | 10:00 | 23:00 | 1.00 | Horario completo con margen planificacion |
| Domingo | 10:00 | 20:00 | 1.00 | Cierre temprano 19h + 1h margen |

## Confirmacion Post-Mutacion (GAQL)

| Dia | Inicio | Fin | Bid modifier | Status |
|-----|:------:|:---:|:------------:|:------:|
| Lunes | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Martes | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Miercoles | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Jueves | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Viernes | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Sabado | 10:00 | 23:00 | 0.00 | ENABLED — OK |
| Domingo | 10:00 | 20:00 | 0.00 | ENABLED — OK |

**Entradas confirmadas:** 7 de 7 esperadas  

> **Nota sobre `modifier=0.00`:** La API de Google Ads devuelve `0.00` cuando no se asigna bid_modifier.
> Significa "sin ajuste" — equivale a 1.0x en la practica. Es correcto.

## Recordatorio: Re-evaluacion en 60 Dias (~25 jun 2026)

**Por que no se aplicaron bid adjustments:**
11 conversiones en 30 dias es insuficiente para validar patrones por hora.
Cada conversion individual mueve el CVR ±15-30 puntos — ruido, no señal.

**Criterio para activar bid adjustments en la proxima revision:**
- 50+ conversiones/mes sostenidas, O
- 10+ conversiones por bloque horario a evaluar

**Proceso de re-evaluacion:**
1. Re-correr `_analisis_horario_experiencia2026.py`
2. Si patron 10-12h y 22-23h es consistente: ajustar -20% y -10% respectivamente
3. Si Experiencia 2026 ya tiene 50+ conv/mes, considerar TARGET_CPA

---
_Solo se modifico ad_schedule en Thai Merida - Experiencia 2026._
_No se toco bidding, presupuesto, geo, audiencias ni otras campanas._