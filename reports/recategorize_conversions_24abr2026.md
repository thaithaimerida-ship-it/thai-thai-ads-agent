# Fase 2 — Recategorización de Conversiones Primarias → Secundarias

**Fecha/hora:** 25 de April de 2026, 11:05:54  
**Cuenta:** 4021070209  
**Campo modificado:** `primary_for_goal` True → False  
**No se modificó:** status, value_settings, counting_type, lookback_window  

## Resultado de Ejecución

| Resultado | Cantidad |
|-----------|----------|
| Cambiadas a secundaria exitosamente | 4 |
| Ya eran secundarias (sin cambio) | 0 |
| No encontradas | 0 |
| Errores | 0 |

## Detalle: 4 Conversiones Objetivo

| Nombre | ID | Tipo | Antes | Después | Resultado |
|--------|----|------|:-----:|:-------:|-----------|
| Thai Thai Merida (web) reserva_completada | 7543785279 | GOOGLE_ANALYTICS_4_CUSTOM | PRIMARIA | secundaria | OK |
| reserva_completada_directa | 7569100920 | WEBPAGE | PRIMARIA | secundaria | OK |
| Contacto (Evento de Google Analytics click_ubicacion) | 7585354793 | GOOGLE_ANALYTICS_4_CUSTOM | PRIMARIA | secundaria | OK |
| Pedido GloriaFood Online | 7572944047 | UPLOAD_CLICKS | PRIMARIA | secundaria | OK |

## Verificación: Conversiones Protegidas (deben mantenerse primarias)

| Nombre | ID | primary_for_goal final | Estado |
|--------|----|:----------------------:|--------|
| Contacto (Evento de Google Analytics click_whatsapp) | 7585354790 | True | ✅ CORRECTO — sigue primaria |
| Thai Thai Merida (web) click_pedir_online | 7543785282 | True | ✅ CORRECTO — sigue primaria |

## Estado Final — Todas las Conversiones ENABLED

_Confirmado via GAQL post-ejecución (ordenado: primarias primero):_

| Nombre | ID | Tipo | primary_for_goal |
|--------|----|------|:----------------:|
| Calls from Smart Campaign Ads | 7164043875 | SMART_CAMPAIGN_TRACKED_CALLS | ✅ PRIMARIA |
| Clicks to call | 7164042669 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Contacto (Evento de Google Analytics click_whatsapp) | 7585354790 | GOOGLE_ANALYTICS_4_CUSTOM | ✅ PRIMARIA |
| Local actions - Directions | 7164043830 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Local actions - Menu views | 7169935844 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Local actions - Orders | 7193495198 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Local actions - Other engagements | 7170100795 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Local actions - Website visits | 7170038126 | GOOGLE_HOSTED | ✅ PRIMARIA |
| Smart campaign ad clicks to call | 7164042954 | SMART_CAMPAIGN_AD_CLICKS_TO_CALL | ✅ PRIMARIA |
| Smart campaign map clicks to call | 7164042951 | SMART_CAMPAIGN_MAP_CLICKS_TO_CALL | ✅ PRIMARIA |
| Smart campaign map directions | 7164043677 | SMART_CAMPAIGN_MAP_DIRECTIONS | ✅ PRIMARIA |
| Store visits | 7230433615 | STORE_VISITS | ✅ PRIMARIA |
| Thai Thai Merida (web) click_pedir_online | 7543785282 | GOOGLE_ANALYTICS_4_CUSTOM | ✅ PRIMARIA |
| Contacto (Evento de Google Analytics click_ubicacion) | 7585354793 | GOOGLE_ANALYTICS_4_CUSTOM | secundaria |
| Pedido GloriaFood Online | 7572944047 | UPLOAD_CLICKS | secundaria |
| Thai Thai Merida (web) reserva_completada | 7543785279 | GOOGLE_ANALYTICS_4_CUSTOM | secundaria |
| reserva_completada_directa | 7569100920 | WEBPAGE | secundaria |

## Pendiente: Conversiones de Sistema (requieren UI manual)

Estas 4 conversiones devuelven `MUTATE_NOT_ALLOWED` via API.
Deben cambiarse manualmente en Google Ads UI:
**Herramientas → Conversiones → [nombre] → Configuración → Incluir en conversiones → No**

| Conversión | Tipo | Razón |
|------------|------|-------|
| Local actions - Directions | GOOGLE_HOSTED | 716 conv/mes artificiales — micro-conversión |
| Calls from Smart Campaign Ads | SMART_CAMPAIGN_TRACKED_CALLS | Llamadas auto-rastreadas, no verificables |
| Smart campaign ad clicks to call | SMART_CAMPAIGN_AD_CLICKS_TO_CALL | Engagement, no conversión de negocio |
| Smart campaign map directions | SMART_CAMPAIGN_MAP_DIRECTIONS | Duplica Local actions - Directions |

---
_Operación completada. Solo se modificó `primary_for_goal` en las conversiones listadas._