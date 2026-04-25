# Propuesta: Recategorización de Conversiones Primarias — Thai Thai Mérida
**Fecha:** 24/04/2026  
**Estado:** Pendiente decisión estratégica  
**Cuenta:** 4021070209  
**Solo lectura — ningún cambio aplicado**

---

## 1. Estado Actual de Conversiones PRIMARY

Datos obtenidos via Google Ads API (read-only, 24 abr 2026).

| ID | Nombre | Tipo API | Primaria hoy | Mutable via API | Recomendación |
|----|--------|----------|:------------:|:---------------:|---------------|
| 7543785282 | Thai Thai Merida (web) **click_pedir_online** | GA4_CUSTOM | ✅ SÍ | ✅ sí | **MANTENER PRIMARIA** |
| 7543785279 | Thai Thai Merida (web) **reserva_completada** | GA4_CUSTOM | ✅ SÍ | ✅ sí | ⚠️ **Decisión pendiente #1** |
| 7164043830 | Local actions - Directions | GOOGLE_HOSTED | ✅ SÍ | ❌ sistema | → Secundaria **(requiere UI)** |
| 7164043875 | Calls from Smart Campaign Ads | SMART_CAMPAIGN_TRACKED_CALLS | ✅ SÍ | ❌ sistema | → Secundaria **(requiere UI)** |
| 7164042954 | Smart campaign ad clicks to call | SMART_CAMPAIGN_AD_CLICKS_TO_CALL | ✅ SÍ | ❌ sistema | → Secundaria **(requiere UI)** |
| 7164043677 | Smart campaign map directions | SMART_CAMPAIGN_MAP_DIRECTIONS | ✅ SÍ | ❌ sistema | → Secundaria **(requiere UI)** |
| 7585354790 | Contacto (click_whatsapp) | GA4_CUSTOM | ✅ SÍ | ✅ sí | ⚠️ **Decisión pendiente #2** |
| 7585354793 | Contacto (click_ubicacion) | GA4_CUSTOM | ✅ SÍ | ✅ sí | ⚠️ **Decisión pendiente #2** |
| 7572944047 | Pedido GloriaFood Online | UPLOAD_CLICKS | ✅ SÍ | ✅ sí | → Secundaria via API (0 atribución por gclid) |
| 7569100920 | reserva_completada_directa | WEBPAGE | ✅ SÍ | ✅ sí | → Secundaria via API (tag inactivo confirmado) |

**Conversiones actualmente secundarias** (ya correctas, no requieren cambio):
- `Clicks to call` (GOOGLE_HOSTED) — no
- `Local actions - Menu views` / `Orders` / `Other engagements` / `Website visits` — no
- `Smart campaign map clicks to call` — no
- `Store visits` — no

---

## 2. Decisiones Estratégicas Pendientes

### Decisión #1 — ¿`reserva_completada` (GA4) como conversión primaria?

**Conversión:** `Thai Thai Merida (web) reserva_completada` (ID: 7543785279)  
**Tipo:** GA4_CUSTOM | **Mutable:** sí (API)  
**Conversiones 30d:** no disponible en este diagnóstico (requiere query de métricas)

**Argumento a favor de mantenerla primaria:**
- Es una señal real de negocio: un usuario completó el flujo de reservación
- Permite a Google optimizar para ambos canales de ingreso (delivery + reservas)
- Complementa a `click_pedir_online` sin crear confusión si tiene volumen real

**Argumento a favor de hacerla secundaria (por ahora):**
- Si el volumen es bajo (<5 conv/mes), no aporta señal suficiente al algoritmo
- Dos conversiones primarias con pesos distintos pueden confundir el Smart Bidding
- Safer: arrancar con una sola primaria limpia (`click_pedir_online`) y agregar cuando haya 30+ conv/mes en reservas

**Pregunta para decidir:** ¿Cuántas reservas reales recibes al mes via la landing? ¿Más o menos de 10?

---

### Decisión #2 — ¿`click_whatsapp` y `click_ubicacion` a secundaria?

**Conversiones:**
- `Contacto (Evento de Google Analytics click_whatsapp)` (ID: 7585354790)
- `Contacto (Evento de Google Analytics click_ubicacion)` (ID: 7585354793)  
**Tipo:** GA4_CUSTOM | **Mutable:** sí (API)

**Argumento a favor de hacerlas secundarias:**
- Son señales de engagement (micro-conversiones), no de revenue
- Como primarias, le dicen a Google que un click en WhatsApp vale igual que un pedido real
- Distorsionan el CPA real y confunden el algoritmo de Smart Bidding
- Mejor usarlas en columna "Todas las conversiones" para análisis, no para optimización

**Argumento a favor de mantenerlas primarias:**
- Si WhatsApp es un canal real de reservas/pedidos y cierras ventas por ahí, tiene valor
- `click_ubicacion` podría correlacionar con visitas presenciales reales

**Preguntas para decidir:**
- ¿Recibes pedidos o reservas reales por WhatsApp (no solo consultas)?
- ¿El botón de ubicación lo usan clientes que luego visitan el restaurante, o es tráfico de rebote?

---

## 3. Instrucciones de UI — Conversiones de Sistema (MUTATE_NOT_ALLOWED via API)

Estas 4 conversiones **no pueden modificarse via Google Ads API**. Deben cambiarse manualmente en la interfaz de Google Ads.

### Pasos en Google Ads UI

1. Ir a **[Google Ads](https://ads.google.com)** → cuenta Thai Thai Mérida (402-107-0209)
2. Menú izquierdo → **Herramientas y configuración** (ícono de llave inglesa)
3. Sección "Medición" → **Conversiones**
4. Para cada conversión de la lista de abajo:
   - Hacer click en el nombre de la conversión
   - Ir a pestaña **Configuración**
   - Buscar campo **"Incluir en conversiones"**
   - Cambiar de **"Sí"** a **"No"**
   - Guardar

### Conversiones a cambiar a "No incluir en conversiones" (secundaria):

| Conversión | Por qué cambiar |
|------------|-----------------|
| **Local actions - Directions** | Micro-conversión automática. 716 conv/mes artificiales que sesgan el CPA. Un clic en "cómo llegar" no es una venta. |
| **Calls from Smart Campaign Ads** | Llamadas auto-rastreadas por Smart Campaign. No verificable si generan reserva real. |
| **Smart campaign ad clicks to call** | Click para llamar desde el anuncio. Engagement, no conversión de negocio. |
| **Smart campaign map directions** | Igual que Local actions - Directions. Duplicado de señal artificial. |

> **Nota importante:** Google puede mostrar una advertencia al cambiar estas conversiones. Es normal — la cuenta entrará en un período de re-aprendizaje de 1-2 semanas. El rendimiento puede fluctuar durante ese período. Es el costo de limpiar las señales.

---

## 4. Plan de Ejecución — Próxima Sesión

### Orden recomendado de cambios

| Paso | Acción | Método | Riesgo | Tiempo |
|------|--------|--------|--------|--------|
| 1 | Confirmar decisiones #1 y #2 (reserva + whatsapp) | Conversación | Ninguno | 5 min |
| 2 | Cambiar 4 conversiones de sistema a secundaria | Manual UI | Bajo | 10 min |
| 3 | Cambiar `Pedido GloriaFood Online` a secundaria | Script API | Ninguno | 2 min |
| 4 | Cambiar `reserva_completada_directa` a secundaria | Script API | Ninguno | 2 min |
| 5 | Según decisión #2: cambiar click_whatsapp / click_ubicacion | Script API | Bajo | 2 min |
| 6 | Según decisión #1: mantener o mover reserva_completada | Script API | Medio | 2 min |
| 7 | Verificar resultado final: solo 1-2 conversiones primarias | Read-only API | Ninguno | 3 min |

### Script de mutación listo para ejecutar (pendiente decisiones)

El script se generará en la próxima sesión, una vez confirmadas las decisiones #1 y #2. Usará:
- `ConversionActionService.mutate_conversion_actions()`
- Campo: `include_in_conversions_metric = False`
- `update_mask.paths[:] = ["include_in_conversions_metric"]`
- IDs confirmados en este diagnóstico (ver tabla sección 1)

### Conversiones primarias objetivo (estado final deseado)

```
PRIMARIA ✅  click_pedir_online          (pedidos online reales)
PRIMARIA ✅  reserva_completada          (si volumen ≥ 10/mes — Decisión #1)
SECUNDARIA   reserva_completada_directa  (tag inactivo)
SECUNDARIA   Pedido GloriaFood Online    (0 atribución por gclid)
SECUNDARIA   Local actions - Directions  (micro-conversión artificial)
SECUNDARIA   Calls from Smart Campaign   (micro-conversión artificial)
SECUNDARIA   Smart campaign ad clicks    (micro-conversión artificial)
SECUNDARIA   Smart campaign map dirs     (micro-conversión artificial)
SECUNDARIA   click_whatsapp             (engagement — Decisión #2)
SECUNDARIA   click_ubicacion            (engagement — Decisión #2)
```

---

## 5. Impacto Esperado Post-Cambios

- **CPA real visible:** hoy ~$839 MXN/cliente (inflado por micros). Post-cambio: CPA limpio basado en pedidos y reservas reales.
- **Re-aprendizaje:** 1-2 semanas de período de aprendizaje tras los cambios. CTR y conversiones reportadas caerán — esto es normal y esperado.
- **Bidding:** una vez limpias las conversiones primarias, cambiar Experiencia 2026 de TARGET_IMPRESSION_SHARE a MAXIMIZE_CONVERSIONS (QW1 del health audit).

---

*Próximo paso: responder decisiones #1 y #2 en siguiente sesión para habilitar ejecución.*
