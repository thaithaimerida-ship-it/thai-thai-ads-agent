# Weekly Report Spec — Thai Thai Ads Agent

## Propósito
Este documento define cómo debe construirse el reporte semanal del Thai Thai Ads Agent.

El reporte no existe para mostrar datos por mostrar.
Existe para reducir carga mental, dar visibilidad ejecutiva y facilitar decisiones rápidas y seguras.

El reporte debe permitir que Hugo entienda en pocos minutos:
1. cuál es la situación actual
2. qué cambió frente a la semana anterior
3. qué hizo el agente por su cuenta
4. qué necesita aprobación
5. qué riesgos siguen abiertos
6. cuál es la siguiente mejor acción

---

## Frecuencia y momento de envío
- **Frecuencia:** semanal
- **Día:** lunes
- **Hora:** 8:00 am
- **Zona horaria:** Mérida, Yucatán, México

El reporte debe construirse con una lógica consistente de ventana temporal para evitar comparaciones confusas.

---

## Principio de diseño
El reporte debe comportarse como un **informe ejecutivo operativo**, no como dashboard exportado ni como resumen técnico.

Debe ser:
- claro
- corto pero sustancioso
- accionable
- orientado a decisiones
- centrado en negocio
- libre de ruido innecesario

No debe ser:
- una lista larga de métricas sin interpretación
- una colección de gráficos sin contexto
- una explicación técnica de bajo nivel
- un documento que obligue a Hugo a descubrir solo qué hacer

---

## Preguntas que siempre debe responder

Todo reporte semanal debe responder explícitamente estas preguntas:

1. **¿Cómo estuvo la semana en términos generales?**
2. **¿Qué cambió frente a la semana anterior?**
3. **¿Qué hizo el agente automáticamente?**
4. **¿Qué detectó que necesita aprobación?**
5. **¿Hay algún riesgo, error o anomalía importante?**
6. **¿Cuál es la siguiente mejor acción recomendada?**

Si un reporte no responde estas seis preguntas, está incompleto.

---

## Estructura obligatoria del reporte

## 1. Resumen ejecutivo
Esta sección debe ir al inicio y debe poder leerse en menos de un minuto.

Debe incluir:
- lectura general del estado de la cuenta
- si la semana fue buena, neutra o preocupante
- principal cambio frente a la semana anterior
- principal riesgo u oportunidad
- una frase final con la prioridad número uno

### Formato esperado
- 1 a 3 párrafos cortos
- lenguaje de negocio, no técnico
- conclusión clara

### Ejemplo de intención
- "La cuenta se mantuvo estable, con ligera mejora en CPA de Delivery y sin señales críticas de tracking. El principal foco sigue siendo que Reservaciones aún no genera conversiones, pero esto no se considera anormal por ahora. La prioridad de esta semana es validar si el tráfico de intención alta está llegando correctamente a la landing."

---

## 2. Estado general de la semana
Esta sección resume la salud general del sistema.

Debe incluir:
- gasto total
- conversiones totales
- CPA general
- comparación vs semana anterior
- lectura de tendencia

También debe clasificar campañas en:
- sanas
- en observación
- críticas

### Objetivo
Dar una fotografía clara del momento sin entrar aún a demasiado detalle.

### Reglas
- no mostrar demasiadas métricas irrelevantes
- priorizar las que realmente ayudan a decidir
- si hay inconsistencia de datos, decirlo claramente

---

## 3. Desempeño por campaña
Esta sección debe mostrar lo esencial por campaña, no saturar.

Para cada campaña relevante, incluir:
- nombre
- estado
- gasto
- conversiones
- CPA
- tendencia vs semana anterior
- lectura ejecutiva corta

### Estados sugeridos
- Sana
- En observación
- Presión moderada
- Crítica

### Regla
Cada campaña debe cerrarse con una lectura breve, por ejemplo:
- "Sana y estable"
- "Gasta bien, pero aún necesita más evidencia"
- "Muestra presión en CPA, sin ser crítica"
- "Sin conversiones, pero todavía dentro de comportamiento esperable"
- "Riesgo real de desperdicio"

---

## 4. Acciones ejecutadas automáticamente
Esta sección es obligatoria aunque no haya habido acciones.

Debe incluir:
- qué hizo el agente
- por qué lo hizo
- evidencia utilizada
- impacto esperado
- si la acción es reversible

### Si no hubo acciones
Decirlo explícitamente y explicar por qué.
Ejemplo:
- "No se ejecutaron acciones automáticas esta semana porque no se detectaron oportunidades de bajo riesgo con evidencia suficiente."

### Regla
No esconder acciones automáticas.
Todo cambio ejecutado por el agente debe quedar visible aquí.

---

## 5. Acciones listas para aprobación
Esta sección es una de las más importantes.

Debe contener solo acciones concretas que Hugo pueda aprobar o rechazar.
No debe incluir ideas vagas.

Cada propuesta debe incluir:
1. acción propuesta
2. motivo
3. evidencia
4. nivel de riesgo
5. impacto esperado
6. reversibilidad
7. recomendación final

### Ejemplo de estructura
- **Acción propuesta:** mover parte del presupuesto de campaña A hacia campaña B
- **Motivo:** campaña B mantiene mejor eficiencia y señales más consistentes
- **Evidencia:** menor CPA, mejor estabilidad, mejor relación gasto/conversión
- **Nivel de riesgo:** medio
- **Impacto esperado:** mejor asignación del gasto semanal
- **Reversibilidad:** alta
- **Recomendación:** aprobar si se desea priorizar eficiencia por encima de cobertura

### Regla
Máximo 3 acciones prioritarias por reporte, salvo situación extraordinaria.

---

## 6. Riesgos, anomalías y alertas abiertas
Esta sección debe concentrar lo que sigue preocupando aunque no se haya convertido todavía en acción inmediata.

Puede incluir:
- tracking dudoso
- discrepancias entre Ads y GA4
- landing lenta o inconsistente
- formulario o CTA con señales de falla
- campaña con gasto inmaduro que requiere observación
- caídas raras de señal
- problemas de interpretación de datos

### Regla
Separar claramente:
- problema confirmado
- anomalía en observación
- riesgo potencial

No mezclar todo como si tuviera el mismo peso.

---

## 7. Siguiente mejor acción
El reporte debe cerrar con una sola prioridad principal.

No una lista de diez ideas.
Solo una.

Debe responder:
**¿Qué es lo más importante que conviene hacer ahora?**

### Regla
La recomendación debe ser concreta, priorizada y consistente con la filosofía del agente:
- proteger estabilidad
- evitar desperdicio
- invertir mejor el siguiente peso
- no generar trabajo innecesario

---

## 8. Bloque GEO — Estado de geotargeting

Esta sección es parte oficial del reporte semanal desde el MVP del agente.

Muestra el estado de geotargeting de todas las campañas evaluadas por el módulo GEO.

Su propósito no es técnico. Es dar visibilidad ejecutiva sobre si las campañas están llegando al lugar correcto, y si existe algún riesgo operativo abierto en la capa de geotargeting.

### Qué debe incluir

Para cada campaña evaluada:
- nombre de la campaña
- señal detectada (OK, GEO1, GEO0, WRONG_TYPE_*, PROX_RADIUS_*, POLICY_UNDEFINED)
- estado operacional final (verified, unverified, geo_issue, stale)
- descripción breve del problema o conformidad

### Estados operacionales posibles

| Estado | Significado ejecutivo |
|--------|----------------------|
| `verified` | La campaña está correctamente configurada y ha sido confirmada por humano o por API directamente |
| `unverified` | La API muestra configuración correcta, pero la UI Express de Google Ads aún no ha sido validada manualmente. No es un error activo, pero hay incertidumbre. |
| `stale` | Existía una validación humana previa, pero el geo de la campaña cambió desde entonces. La validación quedó desactualizada. Requiere nueva revisión manual. |
| `geo_issue` | Problema activo: geo incorrecto, tipo equivocado, radio fuera de rango, o sin política asignada. Requiere atención. |

### Reglas de presentación

- **`verified`**: mostrar como resuelto. No requiere atención.
- **`unverified`**: mostrar con aviso de pendiente de validación manual. No es urgente salvo que acumule semanas sin validar.
- **`stale`**: mostrar con aviso de que la validación previa quedó obsoleta. Pedir revisión manual en la próxima semana.
- **`geo_issue`**: mostrar como alerta activa con señal específica. Requiere acción.
- **`POLICY_UNDEFINED`**: mostrar como alerta de configuración: la campaña no tiene política de negocio asignada al agente.

### Regla

Si no hay ningún problema activo, el bloque GEO debe decirlo explícitamente:

> "Todas las campañas evaluadas tienen geotargeting correcto o verificado."

Si hay campañas con señal de problema, cada una debe mostrar qué cambió, qué señal se detectó y qué requiere hacer.

No mezclar `geo_issue` con `unverified` como si tuvieran el mismo peso. Un `unverified` es incertidumbre. Un `geo_issue` es un problema confirmado.

### Referencia técnica

Ver `docs/geo-module.md` para la especificación completa del módulo GEO, incluyendo políticas por objetivo, modelo de tres estados para campañas SMART, lógica de validación humana y detección de staleness.

---

## 9. Anexo opcional de métricas
Solo si hace falta.

Puede incluir:
- tabla resumida
- comparativos semanales
- detalles de campañas
- indicadores secundarios

### Regla
El anexo no debe sustituir el resumen ejecutivo.
Primero claridad. Luego detalle.

---

## Tono del reporte
El tono debe ser:
- ejecutivo
- claro
- breve
- confiado
- útil
- orientado a negocio

No debe sonar:
- académico
- excesivamente técnico
- inflado
- alarmista sin razón
- pasivo

---

## Jerarquía de información
El reporte debe construirse de arriba hacia abajo:

1. conclusión
2. estado general
3. campañas
4. acciones ejecutadas
5. acciones para aprobar
6. riesgos abiertos
7. siguiente mejor acción
8. anexo opcional

Nunca empezar por tablas o datos crudos.

---

## Reglas de redacción
- usar lenguaje de negocio
- explicar antes de detallar
- evitar jerga innecesaria
- evitar métricas sin interpretación
- evitar texto largo sin conclusión
- dejar clara la prioridad principal
- si hay incertidumbre, decirlo explícitamente
- si no hubo cambios, explicarlo como decisión disciplinada, no como omisión

---

## Qué NO debe hacer el reporte
El reporte no debe:
- parecer exportación automática de dashboard
- obligar a Hugo a interpretar solo qué significa cada número
- saturar con demasiadas métricas
- mandar demasiadas propuestas simultáneas
- esconder acciones automáticas
- sonar inteligente pero poco útil
- convertir una semana normal en drama

---

## Casos especiales

### Caso 1 — Semana estable
Si la semana fue estable:
- resaltarlo con serenidad
- no inventar urgencia
- priorizar continuidad y observación disciplinada

### Caso 2 — Semana con incidentes críticos
Si hubo incidentes críticos:
- decirlo desde el resumen ejecutivo
- explicar qué hizo el agente
- señalar qué riesgo sigue abierto
- indicar si se requiere acción inmediata de Hugo

### Caso 3 — Semana con poca data
Si hubo poca data:
- declarar baja confianza
- evitar conclusiones agresivas
- priorizar observación sobre intervención

### Caso 4 — Semana con discrepancias de medición
Si Ads, GA4 o señales del negocio no coinciden:
- declarar la inconsistencia
- bajar confianza de conclusiones
- no recomendar cambios agresivos hasta aclarar medición

---

## Criterios de calidad del reporte
Un reporte semanal es bueno si:
- Hugo entiende la situación en menos de 3 minutos
- queda claro qué hizo el agente
- queda claro qué necesita aprobación
- queda claro qué riesgo sigue abierto
- queda clara una prioridad principal
- no genera carga mental innecesaria

Un reporte es malo si:
- solo lista métricas
- no concluye nada
- propone demasiadas cosas
- mezcla señales débiles con problemas reales
- no distingue entre observación y urgencia

---

## Plantilla esperada del reporte

### 1. Resumen ejecutivo
[lectura general]
[cambio principal]
[riesgo u oportunidad principal]
[prioridad número uno]

### 2. Estado general
- Gasto total:
- Conversiones:
- CPA:
- Cambio vs semana anterior:
- Lectura de tendencia:

### 3. Desempeño por campaña
#### [Nombre campaña]
- Estado:
- Gasto:
- Conversiones:
- CPA:
- Tendencia:
- Lectura:

#### [Nombre campaña]
- Estado:
- Gasto:
- Conversiones:
- CPA:
- Tendencia:
- Lectura:

### 4. Acciones ejecutadas automáticamente
- [acción]
  - motivo:
  - evidencia:
  - impacto esperado:
  - reversible:

### 5. Acciones listas para aprobación
- [acción propuesta]
  - motivo:
  - evidencia:
  - nivel de riesgo:
  - impacto esperado:
  - reversibilidad:
  - recomendación:

### 6. Riesgos, anomalías y alertas abiertas
- [riesgo o anomalía]
  - tipo:
  - estado:
  - impacto potencial:
  - seguimiento sugerido:

### 7. Siguiente mejor acción
- [una sola prioridad principal]

### 8. Bloque GEO — Estado de geotargeting
#### [Nombre campaña]
- Señal:
- Estado operacional:
- Nota:

#### [Nombre campaña]
- Señal:
- Estado operacional:
- Nota:

_(Si todas correctas: "Todas las campañas evaluadas tienen geotargeting correcto o verificado.")_

### 9. Anexo opcional
- [solo si aplica]
