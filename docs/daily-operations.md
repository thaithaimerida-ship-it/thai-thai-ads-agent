# Operación Diaria — Thai Thai Ads Agent

## Propósito

Este documento define cómo el sistema opera de forma continua entre reportes semanales, qué visibilidad proporciona cada día, y qué eventos generan alerta inmediata.

El objetivo no es aumentar la autonomía del sistema. Los candados y guardas de seguridad existentes se conservan intactos. El objetivo es eliminar el punto ciego entre reportes: saber cada día que el sistema corrió, qué revisó, y si ocurrió algo relevante.

---

## Arquitectura de operación continua

```
Cloud Scheduler (diario, 9:00 am Mérida)
  └─→ POST /run-autonomous-audit
        ├─ Fase 3A: Tracking Detection
        ├─ Fase 3B: Landing Health
        ├─ Fase 3C: Keyword Analysis + auto-bloqueo si RISK_EXECUTE
        ├─ Fase 4: Ad Group Performance
        ├─ Fase 5: Observation Layer
        ├─ Fase 6B: Budget Actions (BA1)
        ├─ Módulo GEO: Geo Audit + Policy Audit + UI Validations
        └─ Capa de Visibilidad:
             ├─ record_run() → data/system_activity.json
             └─ send_daily_summary_email() → administracion@thaithaimerida.com.mx

Cloud Scheduler (lunes, 8:00 am Mérida)
  └─→ POST /send-weekly-report
        └─ Reporte ejecutivo completo por email
```

---

## Configuración de Cloud Scheduler

### Job existente (reporte semanal)
- **Nombre:** `reporte-semanal-lunes`
- **Schedule:** `0 14 * * 1` (lunes 8am Mérida = 14:00 UTC, sin horario de verano)
- **URL:** `POST https://thai-thai-ads-agent-624172071613.us-central1.run.app/send-weekly-report`

### Job requerido (auditoría diaria) — crear manualmente en GCP Console
- **Nombre:** `auditoria-diaria`
- **Schedule:** `0 15 * * *` (todos los días 9am Mérida = 15:00 UTC)
- **URL:** `POST https://thai-thai-ads-agent-624172071613.us-central1.run.app/run-autonomous-audit`
- **Method:** POST
- **Body:** (vacío)
- **Headers:** `Content-Type: application/json`
- **Región:** us-central1
- **Service account:** la misma que usa el job semanal

**Cómo crearlo:**
1. GCP Console → Cloud Scheduler → Create Job
2. Nombre: `auditoria-diaria`
3. Región: us-central1
4. Frequency: `0 15 * * *`
5. Timezone: UTC
6. Target: HTTP
7. URL: `https://thai-thai-ads-agent-624172071613.us-central1.run.app/run-autonomous-audit`
8. HTTP Method: POST
9. Auth header: OIDC token (mismo service account que el job semanal)

---

## Módulos que corren diariamente

Cada corrida de `/run-autonomous-audit` ejecuta estos módulos en orden:

| Fase | Módulo | Qué hace | Puede ejecutar cambios |
|------|--------|----------|----------------------|
| 3A | Tracking Detection | Compara métricas actuales vs semana anterior. Detecta caídas anómalas de conversiones. | No — solo alerta por email |
| 3B | Landing Health | Verifica que thaithaimerida.com y Gloria Food respondan correctamente. | No — solo alerta por email |
| 3C | Keyword Analysis | Clasifica keywords por riesgo. Auto-bloquea las de RISK_EXECUTE si `AUTO_EXECUTE_ENABLED=true`. | Sí (sujeto a guarda) |
| 4 | Ad Group Performance | Analiza grupos de anuncios con bajo rendimiento. Propone pausas para aprobación. | No — solo propone |
| 5 | Observation Layer | Registra campañas en aprendizaje y patrones en observación. | No |
| 6B | Budget Actions (BA1) | Detecta campañas con CPA crítico. Propone ajuste de presupuesto para aprobación. | No — solo propone |
| GEO | Geo Audit | Audita geotargeting (Capas 1, 2 y 3). Propone corrección GEO1 para aprobación. | No — solo propone |

**Candados activos:**
- `AUTO_EXECUTE_ENABLED` — bloquea toda ejecución automática si está en `false` (default en producción: revisar)
- `KEYWORD_AUTO_BLOCK_MAX_PER_CYCLE` — límite de bloqueos automáticos por ciclo
- `GEO_AUDIT_ENABLED` — activa/desactiva el módulo GEO
- Candado de propuesta activa: no se generan propuestas duplicadas si ya existe una pendiente de aprobación
- Dedup de alertas por horas: `TRACKING_ALERT_DEDUP_HOURS`, `LANDING_ALERT_DEDUP_HOURS`, `GEO_ALERT_DEDUP_HOURS`

---

## Resumen diario de actividad

Después de cada corrida, se envía un correo a `administracion@thaithaimerida.com.mx` con el resumen del día.

**Cuándo se envía:**
- Siempre, al final de `/run-autonomous-audit`.
- Excepción: si ya se envió un resumen en las últimas 12 horas (dedup de seguridad por si el scheduler corre dos veces).

**Asunto del correo:**
```
[Thai Thai Agente] Actividad diaria — Sin cambios · viernes 27 de marzo de 2026 a las 09:00 hrs (Mérida)
```

**Resultado general posible:**
| Valor | Significado |
|-------|-------------|
| `Sin cambios` | El sistema revisó todo y no encontró nada que requiera atención. Operación normal. |
| `Con cambios` | Se ejecutó al menos un cambio automático (ej. bloqueo de keyword). |
| `Con alertas` | Se detectó algo que requiere atención: tracking caído, landing down, GEO1 activo, propuesta urgente. |
| `Con errores` | Algún módulo falló durante la ejecución. |

**Campos del resumen:**
- Fecha y hora de ejecución (hora Mérida)
- Módulos ejecutados
- Entidades revisadas (keywords + campañas evaluadas)
- Issues detectados (con detalle: tracking, landing, GEO)
- Autoajustes ejecutados (cambios reales en Google Ads)
- Bloqueados por guarda de seguridad (propuestas con RISK_BLOCK, protected keywords/campaigns)
- Pendientes de validación humana (keywords pendientes, BA1 pendientes, GEO sin verificar)
- Errores de ejecución si existieron

El resumen diario **no reemplaza** el reporte semanal. Es una confirmación de operación y una señal temprana de problemas, no un análisis ejecutivo.

---

## Alertas inmediatas

Las alertas inmediatas son independientes del resumen diario. Se disparan cuando ocurre un evento específico, sin esperar al final del ciclo.

| Evento | Canal | Cuándo se dispara |
|--------|-------|-------------------|
| Caída anormal de conversiones (tracking) | Email | `detect_tracking_signals()` detecta señal crítica o warning |
| Landing caída o Gloria Food no responde | Email | `check_landing_health()` detecta severity=critical |
| GEO1 activo en alguna campaña | Email con link de aprobación | `detect_geo_issues()` encuentra IDs no permitidos |
| Keyword de alto gasto candidata a bloqueo | Email con link de aprobación | `classify_action()` devuelve RISK_PROPOSE |
| CPA crítico en campaña (BA1) | Email con link de aprobación | `detect_budget_opportunities()` genera propuesta |
| Ad group con bajo rendimiento | Email con link de aprobación | Análisis de grupo de anuncios genera propuesta |

**Lo que NO genera alerta inmediata:**
- Campañas `unverified` de UI SMART (solo aparece en resumen diario y semanal)
- Variaciones normales de métricas
- Observaciones en campañas en aprendizaje
- GEO0 (sin restricción geográfica) cuando hay PROXIMITY — solo aviso informativo

**Dedup de alertas:**
Ninguna alerta se envía más de una vez dentro de su ventana de deduplicación configurada. Esto evita flood de correos si el scheduler corre el endpoint varias veces.

---

## Visibilidad del último trabajo realizado

El sistema mantiene `data/system_activity.json` con el historial de las últimas 30 corridas y cuatro "pins" de rápido acceso:

| Pin | Descripción |
|-----|-------------|
| `last_successful_run` | Última corrida que terminó sin errores |
| `last_run_with_errors` | Última corrida donde algún módulo tuvo error |
| `last_change_applied` | Última corrida donde se ejecutó un cambio real en Google Ads |
| `last_block_by_security` | Última corrida donde una guarda de seguridad bloqueó una acción |

**Endpoints de consulta:**
```
GET /last-activity        → último run + pins de eventos relevantes
GET /activity-log?n=14    → historial de las últimas 14 corridas
```

**Ejemplo de respuesta de /last-activity:**
```json
{
  "status": "ok",
  "latest_run": {
    "run_id": "audit_20260327_090000",
    "timestamp_merida": "2026-03-27 09:00",
    "result_class": "sin_cambios",
    "campaigns_reviewed": 47,
    "issues_detected": 0,
    "changes_executed": 0,
    "blocked_by_guard": 0,
    "human_pending": 1,
    "errors": [],
    "modules": ["tracking","landing","keywords","adgroups","observation","budget_ba1","geo"]
  },
  "last_successful_run": { ... },
  "last_change_applied": null,
  "last_block_by_security": { ... },
  "run_count": 7
}
```

---

## Regla de intervención conservadora

El sistema sigue el principio de intervención mínima definido en `docs/autonomy-policy.md`:

- **Observación diaria**: todos los módulos se ejecutan diariamente y registran su estado.
- **Cambios automáticos**: solo ocurren para acciones de bajo riesgo con evidencia clara (RISK_EXECUTE con `AUTO_EXECUTE_ENABLED=true`).
- **Propuestas**: los módulos de análisis generan propuestas para aprobación, no las ejecutan.
- **Estabilidad**: no se interviene en campañas en aprendizaje salvo problema crítico.
- **Candados intactos**: ninguno de los candados existentes se modifica por esta capa de visibilidad.

La visibilidad diaria es completamente aditiva: no cambia ninguna lógica de decisión del sistema, solo agrega persistencia y notificación al final del ciclo.

---

## Referencia de archivos

| Archivo | Rol |
|---------|-----|
| `engine/activity_log.py` | Persistencia de historial de corridas y derivación de resúmenes |
| `data/system_activity.json` | Historial de las últimas 30 corridas + pins de eventos relevantes |
| `engine/email_sender.py` → `send_daily_summary_email()` | Email de heartbeat diario |
| `main.py` → `/run-autonomous-audit` | Endpoint principal del ciclo diario |
| `main.py` → `/last-activity` | Endpoint de consulta del estado más reciente |
| `main.py` → `/activity-log` | Endpoint de consulta del historial |
| `docs/autonomy-policy.md` | Política de autonomía y guardas de seguridad |
| `docs/weekly-report-spec.md` | Especificación del reporte semanal |
| `docs/geo-module.md` | Especificación del módulo GEO |
