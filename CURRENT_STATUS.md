# CURRENT_STATUS

Fecha de actualización: 2026-04-16

Este archivo separa estrictamente 4 capas:
- `Diagnosticado`
- `Corregido en código`
- `Desplegado`
- `Validado en corrida real`

Si algo no tiene evidencia suficiente, se queda en la capa anterior.

## Resumen ejecutivo

- El proyecto ya tiene backend FastAPI para operar como agente semi-autónomo de Google Ads.
- La base funcional documentada incluye auditoría, decisiones de presupuesto, manejo de keywords, reportería y lectura de negocio desde Google Sheets.
- Hay evidencia documental de despliegue en Cloud Run y ejecución programada con Cloud Scheduler.
- No hay en este archivo evidencia capturada de una corrida real reciente validada de punta a punta.
- No se están reabriendo bugs viejos ya marcados como corregidos sin evidencia nueva.

## 1. Diagnosticado

### Objetivo operativo del sistema
- El agente debe auditar campañas, detectar problemas, reducir presupuesto, revertir, pausar, escalar, redistribuir y enviar correo diario.
- El agente debe reflejar negocio real desde Google Sheets.

### Reglas de contexto
- Se debe separar siempre: `diagnosticado`, `corregido en código`, `desplegado`, `validado en corrida real`.
- No se debe asumir que producción refleja automáticamente lo que existe en código.
- No se debe asumir que una corrida real valida automáticamente toda la lógica.

### Riesgos/documentación abierta ya conocida
- Existen bugs conocidos no críticos documentados en `CLAUDE.md` sobre firmas de `verify_budget_still_actionable()` y `log_agent_action()`.
- Esos bugs quedan registrados como contexto conocido; no se reabren aquí porque no hay evidencia nueva en esta sesión.

## 2. Corregido en código

Según la documentación del repositorio (`CLAUDE.md`), en código ya existe lo siguiente:

### Núcleo del agente
- Sub-agentes activos documentados: `auditor`, `executor`, `strategist`, `reporter`, `builder`.
- Motor de decisiones en `engine/decision_engine.py` para presupuestos y keywords.
- Remediación creativa en `engine/creative_remediation.py`.
- Integración con Google Sheets en `engine/sheets_client.py`.
- Correo diario en `engine/email_sender.py`.

### Capacidades documentadas en código
- Auditoría de campañas y generación de hallazgos.
- Ejecución de acciones sobre Google Ads API.
- Ajustes automáticos de presupuesto con guardrails.
- Decisiones de keywords con guardrails.
- Lectura de ventas y ocupación desde `Cortes_de_Caja`.
- Inclusión de métricas de calidad de anuncios, Quality Score e Impression Share.

### Estado de código que debe tratarse como implementado, no como validado
- Fase `6D` de Quality & Creative Health.
- Auto-ejecución de BA1, BA2 y decisiones de Haiku bajo umbrales de confianza.
- Reportería diaria y semanal.
- Presupuesto dinámico informado por ocupación.

## 3. Desplegado

Según la documentación del repositorio (`CLAUDE.md`), está documentado como desplegado:

- Servicio Cloud Run: `thai-thai-ads-agent`.
- URL de producción: `https://thai-thai-ads-agent-624172071613.us-central1.run.app`
- Cloud Build con auto-deploy desde `main`.
- Cloud Scheduler con jobs `auditoria-diaria`, `auditoria-compensatoria` y `reporte-semanal-lunes`.

Importante:
- Esta capa significa "documentado como desplegado".
- No significa "verificado hoy".

## 4. Validado en corrida real

Sin evidencia registrada en este archivo durante esta sesión.

Por ahora, NO se marca como validado en corrida real:
- que la auditoría diaria haya corrido bien hoy
- que el correo diario se haya enviado bien hoy
- que las decisiones automáticas hayan ejecutado bien hoy
- que Sheets, GA4 y Google Ads estén respondiendo bien hoy
- que Cloud Scheduler esté disparando correctamente hoy

## Estado operativo conservador

La postura actual del proyecto debe ser:
- tratar como `implementado` lo que está documentado en código
- tratar como `desplegado` solo lo documentado como producción
- no promover nada a `validado en corrida real` sin evidencia nueva

## Fuera de alcance en esta actualización

Esta actualización NO hace lo siguiente:
- no cambia lógica del sistema
- no re-diagnostica módulos ya descritos en la documentación
- no reabre bugs viejos sin prueba nueva
- no afirma validación real que no esté evidenciada
