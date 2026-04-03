# Módulo GEO — Especificación Oficial del MVP

## Propósito

El módulo GEO audita que cada campaña activa esté configurada con el geotargeting correcto según su objetivo de negocio.

El problema que resuelve es concreto: una campaña con geotargeting incorrecto puede gastar presupuesto mostrando anuncios a personas que nunca irán al restaurante, nunca pedirán delivery a domicilio, o nunca harán una reserva. Es desperdicio silencioso que los reportes de rendimiento no detectan directamente.

El módulo no solo detecta errores. También define qué es "correcto" para cada campaña según su objetivo, persiste validaciones humanas, y distingue entre certeza real y apariencia de certeza.

---

## Arquitectura: dos capas de auditoría

El módulo opera en dos capas independientes.

### Capa 1 — Auditoría por location_id

Detecta problemas básicos de geotargeting evaluando los `location_id` configurados en `campaign_criterion`.

**Señales:**

- **GEO1** — la campaña tiene al menos una ubicación no permitida por `location_id`. Ejemplo: `Ciudad Victoria` en vez de `Mérida`. Este es el error más grave: dinero siendo gastado en la ubicación equivocada. Se genera correo de alerta con link de aprobación.
- **GEO0** — la campaña no tiene ninguna restricción geográfica explícita por `location_id`. Puede significar que usa PROXIMITY (radio), o que no tiene geo en absoluto. Es una señal de aviso, no necesariamente un error crítico.
- **OK** — los location_ids son correctos por API. Para campañas SMART, esto no garantiza que la UI Express refleje lo mismo.

### Capa 2 — Auditoría por política de objetivo

Evalúa cada campaña contra su política de negocio específica, no solo contra una lista de IDs permitidos.

**Señales adicionales:**

- **WRONG_TYPE_LOC_FOR_PROX** — la campaña usa LOCATION pero la política exige PROXIMITY (radio). Error de tipo de targeting.
- **WRONG_TYPE_PROX_FOR_LOC** — la campaña usa PROXIMITY pero la política exige LOCATION estricta.
- **PROX_RADIUS_EXCEEDED** — tiene PROXIMITY pero el radio supera el máximo permitido por la política.
- **PROX_RADIUS_INSUFFICIENT** — tiene PROXIMITY pero el radio es menor al mínimo requerido para cobertura funcional.
- **POLICY_UNDEFINED** — la campaña no tiene política asignada. Ninguna acción automática puede ejecutarse sin política.
- **OK** — cumple su política. Para campañas SMART, el estado final depende además de la validación de UI.

---

## Políticas de objetivo

Las políticas están definidas en `config/agent_config.py` bajo `GEO_OBJECTIVE_POLICIES`. Cada campaña tiene un objetivo asignado en `CAMPAIGN_GEO_OBJECTIVES`.

| Campaña | Objetivo | Tipo esperado | Radio | Centro | Autofix |
|---------|---------|---------------|-------|--------|---------|
| Thai Mérida - Delivery | DELIVERY | PROXIMITY | ≤ 8 km | Restaurante | Sí |
| Thai Mérida - Reservaciones | RESERVACIONES | LOCATION | — | ID 1010205 (Mérida) | No |
| Thai Mérida - Local | LOCAL_DISCOVERY | LOCATION_OR_PROXIMITY | 10–50 km | Restaurante | No |

**Tipo `LOCATION_OR_PROXIMITY`:** acepta equivalencia funcional. Una campaña LOCAL_DISCOVERY puede usar `LOCATION 1010205` o `PROXIMITY` centrado en el restaurante con radio entre 10 y 50 km. Esta equivalencia fue aprobada explícitamente para el objetivo de descubrimiento local, donde ambos mecanismos cubren funcionalmente el mismo mercado.

El centro de referencia para todas las políticas de PROXIMITY es la dirección exacta del restaurante:
- **Calle 30 No. 351, Col. Emiliano Zapata Norte, Mérida, Yucatán**
- lat `21.008815`, lng `-89.612673`

---

## Modelo de tres estados para campañas SMART

Las campañas SMART ("Campañas inteligentes") tienen una UI Express en `express/settings?tab=geo` que opera sobre una capa interna no accesible vía GAQL estándar.

Esto significa que el agente puede leer y modificar `campaign_criterion`, pero no puede confirmar si la UI Express refleja esos cambios. Son dos superficies desacopladas.

Por eso, para campañas SMART cada resultado reporta tres estados simultáneos:

### `api_state`
Lo que devuelve `campaign_criterion`. Lo que el agente puede leer y escribir.

| Valor | Significado |
|-------|-------------|
| `correct` | la API muestra configuración correcta |
| `geo1_incorrect` | la API muestra ubicación incorrecta |
| `geo0_no_restriction` | la API no muestra restricción geográfica |
| `wrong_type_loc_for_prox` / `wrong_type_prox_for_loc` | tipo incorrecto según política |
| `prox_radius_exceeded` / `prox_radius_insufficient` | radio fuera de rango |

### `ui_state`
Lo que muestra la UI Express de Google Ads. **Solo un humano puede confirmar este campo.**

| Valor | Significado |
|-------|-------------|
| `unknown` | nunca validado manualmente |
| `correct` | confirmado correcto por humano |
| `incorrect:<ciudad>` | confirmado incorrecto, con descripción de lo observado |

Este campo nunca puede resolverse solo con datos de API. Siempre inicia como `unknown`.

### `final_operational_state`
El estado real del negocio, combinando las dos capas anteriores.

| Valor | Condición |
|-------|-----------|
| `verified` | `api_state=correct` Y `ui_state=correct` |
| `unverified` | `api_state=correct` Y `ui_state=unknown` |
| `inconsistent` | `api_state=correct` Y `ui_state=incorrect:*` |
| `geo_issue` | `api_state` tiene cualquier señal de error |

**Regla fundamental:** una campaña SMART solo se considera resuelta cuando `final_operational_state == "verified"`. El `api_state=correct` por sí solo no es suficiente.

Para campañas no-SMART (SEARCH, DISPLAY, etc.), la UI sí refleja `campaign_criterion`, por lo que `api_state=correct` equivale directamente a `verified`.

---

## Validaciones humanas de UI

### Propósito

Cuando un humano inspecciona la UI Express y confirma que el geo está correcto, esa confirmación puede persistirse para que el agente no repita indefinidamente la misma alerta de `unverified`.

Esta capa está implementada en `engine/geo_ui_validator.py`. Los registros se guardan en `data/geo_ui_validations.json`.

### Cuándo una validación eleva `unverified → verified`

Se cumplen **todas** las siguientes condiciones:

1. La entrada tiene `final_operational_state == "unverified"`.
2. Existe un registro en `geo_ui_validations.json` para ese `campaign_id`.
3. El registro tiene `ui_validated_by_human: true`.
4. El registro tiene `ui_state: "correct"`.
5. Si el registro incluye `geo_snapshot` y se pasan los `geo_criteria` actuales: el snapshot guardado debe coincidir con el estado geo actual (dentro de tolerancias).

Si todas las condiciones se cumplen, el agente actualiza la entrada:
- `ui_state = "correct"`
- `final_operational_state = "verified"`
- Se agregan `ui_validated_by_human`, `ui_validated_at`, `ui_validation_source`.

### Cuándo una validación queda `stale`

Una validación se marca como stale (`ui_validation_stale: true`) si:

- Tiene `geo_snapshot` guardado.
- Se pasan los `geo_criteria` actuales al aplicar validaciones.
- El estado geo actual **no coincide** con el snapshot dentro de las tolerancias.

Cuando una validación es stale:
- La entrada permanece en `final_operational_state = "unverified"`.
- Se agrega `ui_validation_stale: true` al resultado.
- El registro en disco **no se modifica automáticamente** — requiere una nueva validación humana.

Esto evita falsos `verified` cuando la campaña fue reconfigurada después de la última validación.

### El `geo_snapshot`

El snapshot es un dict compacto que captura el estado geo de la campaña en el momento de la validación. Se guarda junto al registro de validación en `geo_ui_validations.json`.

**Campos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `targeting_type` | str | `"LOCATION"` / `"PROXIMITY"` / `"BOTH"` / `"NONE"` |
| `location_ids` | list[str] | IDs de ubicaciones activas, ordenados |
| `proximity_radius_km` | float \| null | Radio en kilómetros |
| `proximity_center_lat` | float \| null | Latitud del centro |
| `proximity_center_lng` | float \| null | Longitud del centro |
| `objective_type` | str | Política asignada a la campaña (ej. `"LOCAL_DISCOVERY"`) |

Se construye con `_build_geo_snapshot(criteria_entry, objective_type)` en `geo_ui_validator.py`.

### Tolerancias de `_snapshot_matches()`

| Campo | Tolerancia | Equivale a |
|-------|------------|------------|
| `targeting_type` | exacto | — |
| `location_ids` | exacto | — |
| `objective_type` | exacto | — |
| `proximity_radius_km` | ± 0.5 km | margen de redondeo de API |
| `proximity_center_lat` | ± 0.001 grados | ~111 metros |
| `proximity_center_lng` | ± 0.001 grados | ~111 metros |

Las tolerancias de coordenadas (~111 m) están calibradas para absorber diferencias de redondeo entre la API de Google Ads (valores en micro_degrees) y los valores almacenados, sin ignorar desplazamientos reales del centro.

### Compatibilidad hacia atrás

- Si una validación **no tiene `geo_snapshot`**: se eleva sin verificar staleness. Esto mantiene compatibilidad con registros anteriores a esta funcionalidad.
- Si `geo_criteria` **no se pasa** a `apply_ui_validations()`: no se verifica staleness. Se eleva normalmente.

Esto significa que la detección de staleness es opt-in: solo activa cuando el sistema tiene todos los datos necesarios para comparar.

---

## Integración en el ciclo de auditoría

El módulo GEO se ejecuta en cada ciclo de auditoría completa en `main.py`. El orden es:

```
1. fetch_campaign_geo_criteria()       → obtiene el estado real desde la API
2. detect_geo_issues()                 → Capa 1: GEO1/GEO0 por location_id
   └─ GEO1 → genera correo de alerta
3. detect_geo_issues_by_policy()       → Capa 2: señales de política por objetivo
4. load_ui_validations()               → carga registros de validación humana
5. apply_ui_validations(..., geo_criteria)  → Capa 3: eleva unverified o marca stale
6. geo_audit_result["policy_audit"]    → resultado consolidado para reporte semanal
```

El resultado consolidado incluye:
- `issues` — campañas con señal de problema activa
- `correct` — campañas conformes (con `verified`, `unverified`, o stale según sea el caso)
- `summary` — conteos por estado para el reporte semanal

---

## Integración en el reporte semanal

El reporte semanal incluye un bloque GEO que muestra el estado de geotargeting de todas las campañas evaluadas.

Ver `docs/weekly-report-spec.md`, Sección 8: Bloque GEO.

Resumen del comportamiento esperado:

- Campañas con `verified`: aparecen como resueltas, sin necesidad de acción.
- Campañas con `unverified`: se muestran con aviso de pendiente de validación manual.
- Campañas con `ui_validation_stale: true`: se muestran con aviso de que la validación previa quedó desactualizada por cambio en geo.
- Campañas con `geo_issue`: se muestran como problema activo con señal específica.

---

## Estado del módulo: MVP consolidado

El módulo GEO está consolidado para el MVP del agente Thai Thai.

### Qué está implementado y es oficial

- Auditoría Capa 1: `detect_geo_issues()` — GEO1/GEO0 por location_id.
- Auditoría Capa 2: `detect_geo_issues_by_policy()` — cumplimiento contra política de negocio.
- Tres políticas definidas: DELIVERY (PROXIMITY ≤8 km), RESERVACIONES (LOCATION 1010205), LOCAL_DISCOVERY (LOCATION_OR_PROXIMITY, 10–50 km).
- Modelo de tres estados para campañas SMART: `api_state`, `ui_state`, `final_operational_state`.
- Persistencia de validaciones humanas: `data/geo_ui_validations.json`.
- Detección de staleness por snapshot: `_build_geo_snapshot()`, `_snapshot_matches()`.
- Validación activa: Thai Mérida - Local (22612348265) registrada como `verified` al 2026-03-27.
- Integración en ciclo de auditoría y reporte semanal.
- Cobertura de tests: 60 tests pasando (29 en `test_geo_auditor.py`, 31 en `test_geo_ui_validator.py`).

### Pendientes futuros — opcionales, no bloqueantes

Estas funcionalidades mejorarían el módulo pero no son necesarias para el MVP operacional:

| Pendiente | Descripción | Prioridad |
|-----------|-------------|-----------|
| Renovación automática de snapshot | Cuando el agente detecta que `api_state=correct` y el humano valida la UI, guardar el nuevo snapshot automáticamente vía `/validate-geo-ui` endpoint | Baja |
| Alerta explícita por stale en correo | Enviar notificación específica cuando una validación quede stale (hoy solo aparece en reporte semanal) | Baja |
| Política para nuevas campañas | Si se detecta una campaña sin política asignada (POLICY_UNDEFINED), sugerir automáticamente la política más probable según nombre y tipo | Media |
| Validación de centro de PROXIMITY | Comparar el centro del PROXIMITY contra las coordenadas del restaurante como parte de la auditoría Capa 2, no solo del snapshot | Media |
| UI de validación | Un endpoint GET `/geo-status` con tabla de estados, botón de marcar como validado para uso desde móvil | Baja |

Ninguno de estos pendientes bloquea el funcionamiento actual ni la calidad del reporte semanal.

---

## Archivos relevantes

| Archivo | Rol |
|---------|-----|
| `engine/geo_auditor.py` | Funciones puras de auditoría (Capas 1 y 2). Sin llamadas a API ni I/O. |
| `engine/geo_ui_validator.py` | Persistencia y aplicación de validaciones humanas (Capa 3). |
| `config/agent_config.py` | `GEO_OBJECTIVE_POLICIES`, `CAMPAIGN_GEO_OBJECTIVES`, coordenadas del restaurante. |
| `data/geo_ui_validations.json` | Registro de validaciones humanas con snapshots. |
| `tests/test_geo_auditor.py` | 29 tests de las Capas 1 y 2. |
| `tests/test_geo_ui_validator.py` | 31 tests de la Capa 3 (validaciones, snapshots, staleness). |
| `main.py` | Integración en ciclo de auditoría y endpoint `/weekly`. |
| `engine/email_reporter.py` | Renderizado del bloque GEO en el reporte HTML semanal. |
