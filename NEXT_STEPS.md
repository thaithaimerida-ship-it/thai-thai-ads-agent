# NEXT_STEPS

Fecha de actualización: 2026-04-16

Objetivo de este archivo:
- definir el siguiente trabajo mínimo
- mantener cambios quirúrgicos
- no mezclar `diagnosticado`, `corregido en código`, `desplegado` y `validado en corrida real`

## Regla de avance

Cada paso debe cerrar explícitamente una sola capa:
- `Diagnosticado`
- `Corregido en código`
- `Desplegado`
- `Validado en corrida real`

No saltar directo a `validado` sin evidencia intermedia.

## Siguiente paso mínimo recomendado

### Paso 1
- Tema: validar una corrida real del flujo principal
- Capa objetivo: `Validado en corrida real`
- Alcance: confirmar evidencia de una ejecución real reciente del agente, sin cambiar lógica

### Qué confirmar
- que el backend responde en producción
- que el job principal sí corrió
- que hubo lectura correcta de Google Ads
- que hubo lectura correcta de Google Sheets
- que el correo diario se generó o intentó generarse

### Qué NO hacer en este paso
- no modificar reglas de presupuesto
- no tocar lógica de decisiones
- no refactorizar
- no reabrir bugs viejos ya corregidos
- no cambiar módulos no relacionados

## Cola mínima después del paso 1

### Paso 2
- Tema: registrar evidencia por capa en `CURRENT_STATUS.md`
- Capa objetivo: actualizar solo estado documental
- Resultado esperado: mover a `Validado en corrida real` únicamente lo que tenga prueba

### Paso 3
- Tema: elegir un solo ajuste quirúrgico si aparece una falla real
- Capa objetivo: `Corregido en código`
- Condición de entrada: debe existir evidencia nueva de fallo actual

## Priorización

Orden recomendado:
1. validar corrida real
2. documentar evidencia real
3. corregir solo si aparece un fallo actual con prueba
4. desplegar solo el ajuste mínimo
5. volver a validar en corrida real

## Criterio de no reabrir

No convertir en trabajo activo:
- bugs históricos ya marcados como corregidos
- dudas generales sobre arquitectura ya definida
- mejoras amplias sin evidencia operativa

## Definición de hecho para el próximo cambio

Solo vale como avance real si queda claro cuál de estas capas cambió:
- `Diagnosticado`
- `Corregido en código`
- `Desplegado`
- `Validado en corrida real`

Si no cambia una de esas capas con evidencia, no cuenta como cierre.
