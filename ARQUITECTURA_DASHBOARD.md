# Arquitectura del Dashboard — Thai Thai Ads Agent

**Revisión activa**: `00085-htj` · **Fecha**: 2026-03-30

---

## 1. Origen de datos del dashboard

El dashboard en `/dashboard` consume tres endpoints al cargar:

| Endpoint | Fuente real | Latencia típica |
|---|---|---|
| `/dashboard-snapshot` | JSON en GCS (lectura de archivo) | ~300–450ms |
| `/history?days=30` | SQLite en Cloud Run | ~80ms |
| `/reservations` | SQLite en Cloud Run | ~80ms |

Los datos de campañas, keywords, GA4 y landing page **no se consultan en vivo al cargar el dashboard**. Vienen del snapshot pre-calculado en GCS.

---

## 2. Rol de `/dashboard-snapshot`

Endpoint de solo lectura. Lee el archivo `snapshots/dashboard_snapshot.json` desde el bucket `thai-thai-agent-data` en GCS y lo devuelve directamente.

- Si el objeto existe → HTTP 200 + JSON completo del último Mission Control
- Si el objeto no existe → HTTP 503 + `{"status": "no_snapshot"}`

No llama a ninguna API externa. No accede a Google Ads. No ejecuta lógica de negocio. Su único trabajo es deserializar y retornar el JSON guardado.

---

## 3. Rol de `/mission-control`

Endpoint costoso (90–120 segundos en producción). Ejecuta el ciclo completo:

1. Llama a Google Ads API → campañas, keywords, search terms
2. Llama a GA4 API → eventos por hora, funnel de conversión
3. Ejecuta todos los Skills (waste detector, agent decisioner, hour optimizer, landing health, promotion suggester)
4. Llama a Claude Sonnet para análisis ejecutivo
5. Construye el dict `_result` con todos los datos
6. **Al final, llama `_save_mc_snapshot(_result)`** → escribe el resultado en GCS
7. Retorna `_result` al caller

Este endpoint es el único que actualiza el snapshot en GCS. El dashboard solo lo llama cuando el usuario presiona "Actualizar".

---

## 4. Cuándo se actualiza el snapshot

El snapshot en GCS se actualiza en exactamente tres situaciones:

| Situación | Cómo | Frecuencia |
|---|---|---|
| Usuario presiona "Actualizar" | `loadAll(true)` → llama `/mission-control` | Manual, bajo demanda |
| Auditoría diaria automática | `_run_audit_task` llama `await mission_control_data()` al final | Diaria a las 7am hora Mérida |
| Corrida compensatoria | Mismo mecanismo que auditoría diaria | Si la corrida de 7am falló |

No hay ningún otro código que llame a `_save_mc_snapshot()`.

---

## 5. Dónde se persiste el snapshot

- **GCS bucket**: `thai-thai-agent-data` (proyecto `thai-thai-ads-master-agent`, region `us-central1`)
- **Object path**: `snapshots/dashboard_snapshot.json`
- **Formato**: JSON con todos los campos del Mission Control + campo adicional `_snapshot_saved_at` con timestamp ISO-8601 (`"%Y-%m-%dT%H:%M:%S"`)
- **Autenticación**: Cuenta de servicio `624172071613-compute@developer.gserviceaccount.com`, inyectada automáticamente en Cloud Run. No requiere variables de entorno adicionales.
- **Durabilidad**: Persiste indefinidamente entre reemplazos de instancias, cold starts y redeploys. No se borra automáticamente.

---

## 6. Comportamiento en carga inicial del dashboard

```
Usuario abre /dashboard
    ↓
loadAll() ← sin argumento → forceRefresh = undefined (falsy)
    ↓
mcEndpoint = '/dashboard-snapshot'
    ↓
Promise.all([
    GET /dashboard-snapshot,
    GET /history?days=30,
    GET /reservations
])
    ↓
¿mc.status === 'no_snapshot'?
    SÍ → toast("Sin datos previos. Presiona Actualizar para cargar.") + return
    NO → renderizar dashboard con datos del snapshot
```

**No hay llamada a Google Ads en la carga inicial bajo ninguna circunstancia.**

El toast de "sin datos" solo aparece si el bucket GCS no tiene el objeto todavía (primera vez tras un deploy a una instancia nueva que nunca ejecutó auditoría). En producción normal esto no ocurre porque la auditoría diaria mantiene el snapshot fresco.

---

## 7. Riesgos y mejoras futuras

### Riesgos activos

| Riesgo | Prob. | Impacto | Mitigación actual |
|---|---|---|---|
| Snapshot desactualizado si falla auditoría 7am y compensatoria | Baja | Medio | Corrida compensatoria + correo de incidente |
| Latencia GCS en cold start (~300ms extra vs. disco local) | Alta | Bajo | Aceptable; dominada por red de todas formas |
| Costo GCS por lecturas frecuentes (countdown cada 5min) | Baja | Bajo | 10KB por lectura, volumen insignificante |
| Snapshot con datos de >24h si el agente no corrió | Baja | Medio | `_snapshot_saved_at` visible en el dashboard avisa al usuario |

### Mejoras futuras (no implementadas)

1. **Cache en memoria dentro del contenedor**: Si el mismo contenedor sirve múltiples requests en poco tiempo (Fluid Compute), cachear el snapshot en una variable global con TTL de 5 minutos evitaría llamadas repetidas a GCS. Actualmente cada request a `/dashboard-snapshot` hace una llamada a GCS.

2. **Tablas como cards en mobile**: El `overflow-x:auto` en `.tbl-wrap` es contención funcional, no UX óptima. Las tablas `#roi-channels`, `#campaigns-table` y `#waste-table` son candidatas a convertirse en bloques apilados en pantallas ≤480px.

3. **Indicador visual de frescura del snapshot**: El campo `_snapshot_saved_at` está disponible, pero no hay distinción visual si el snapshot tiene más de X horas. Un badge de color (verde/amarillo/rojo según antigüedad) mejoraría la confianza del operador.

4. **Versionado del snapshot en GCS**: Activar object versioning en el bucket permitiría hacer rollback al snapshot anterior si una auditoría genera datos corruptos.

5. **Snapshot por sección**: Actualmente todo el Mission Control (~11KB) está en un solo JSON. Si el tamaño crece, separar en múltiples objetos GCS (uno por sección) permitiría invalidaciones parciales.
