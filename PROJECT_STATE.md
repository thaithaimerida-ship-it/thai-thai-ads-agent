# PROJECT_STATE

## Objetivo del sistema
Agente auditor/autónomo de Google Ads para Thai Thai Mérida.

Debe poder:
- auditar campañas
- detectar problemas
- reducir presupuesto
- revertir
- pausar
- escalar
- redistribuir
- enviar correo diario
- reflejar negocio real desde Google Sheets

## Arquitectura base
- Backend en Cloud Run
- Cloud Build para deploy
- Google Ads API
- Google Sheets para negocio
- correo diario con resumen del agente
- trabajo de desarrollo en VS Code

## Regla crítica de contexto
Siempre distinguir entre:
1. diagnosticado
2. corregido en código
3. desplegado en producción
4. validado en corrida real

Nunca mezclar estas cuatro capas.

## Regla de trabajo para cualquier agente de código
Antes de tocar nada:
1. leer PROJECT_STATE.md
2. leer CURRENT_STATUS.md
3. leer NEXT_STEPS.md
4. resumir el estado actual en 10 bullets
5. decir qué NO va a volver a diagnosticar
6. proponer un siguiente paso mínimo
7. no editar nada hasta que el resumen sea aprobado

## Restricciones
- cambios quirúrgicos
- no tocar módulos no relacionados
- no hacer refactors amplios sin permiso
- no asumir que algo está roto sin evidencia
- no volver a abrir bugs ya corregidos sin prueba nueva