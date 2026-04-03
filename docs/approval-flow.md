# Approval Flow — Thai Thai Ads Agent

## Propósito
Este documento define cómo debe funcionar el flujo de aprobación humana dentro de Thai Thai Ads Agent.

La meta es que el agente sea semi-autónomo:
- ejecute solo lo de bajo riesgo
- pida aprobación solo cuando realmente haga falta
- avise con urgencia solo ante incidentes críticos
- reduzca carga mental para Hugo en lugar de generarle más trabajo

El flujo de aprobación no debe convertir al usuario en operador manual de cada detalle.
Debe existir solo para cambios con impacto relevante, riesgo medio o riesgo alto.

---

## Principio general
El agente no debe pedir permiso por todo.
Debe pedir aprobación solo cuando:

- el cambio tenga riesgo medio o alto
- el impacto potencial sea relevante
- el cambio afecte presupuesto, estructura, aprendizaje, conversión o medición
- el juicio humano agregue valor real

Todo lo demás debe resolverse por observación o autoejecución.

---

## Canales permitidos

### 1. Email normal
Usar para:
- reporte semanal
- solicitudes normales de aprobación
- seguimiento de propuestas no urgentes
- resumen de acciones ejecutadas

Este es el canal principal.

---

### 2. Email urgente
Usar solo para incidentes críticos o aprobaciones extraordinarias sensibles fuera del ciclo semanal.

Debe verse claramente como urgente:
- asunto con prefijo fuerte
- texto breve y visible
- prioridad clara
- explicación concreta de por qué importa

No usar este canal para observaciones menores ni recomendaciones rutinarias.

---

## Canales no usados por ahora
- WhatsApp no se usará como canal de aprobación
- WhatsApp no se usará como canal operativo regular
- Si en el futuro se agrega otro canal, deberá respetar esta misma política

---

## Tipos de correo

## A. Correo semanal ejecutivo
### Cuándo se envía
- lunes
- 8:00 am
- hora Mérida

### Para qué sirve
- resumir el estado general
- mostrar acciones automáticas ejecutadas
- presentar hasta 3 aprobaciones relevantes
- dejar clara una sola prioridad principal

### Qué debe incluir
1. resumen ejecutivo
2. estado general
3. acciones ejecutadas automáticamente
4. acciones listas para aprobación
5. riesgos abiertos
6. siguiente mejor acción

### Regla
Este correo debe ser suficiente para que Hugo entienda la semana y tome decisiones sin entrar al dashboard.

---

## B. Correo de aprobación
### Cuándo se envía
Cuando el agente detecta una acción de riesgo medio o alto que:
- no debe ejecutar solo
- no conviene esperar necesariamente hasta el siguiente lunes
- requiere criterio o autorización humana

### Cuándo NO se envía
- si la acción es de bajo riesgo
- si la evidencia es insuficiente
- si la situación todavía debe observarse
- si el tema puede esperar al reporte semanal sin costo importante

### Regla de frecuencia
No abusar de este correo.

Objetivo:
- máximo 1 ciclo principal de aprobaciones por semana
- evitar múltiples correos separados por cambios pequeños
- agrupar aprobaciones cuando sea posible

El agente no debe convertir a Hugo en aprobador constante.

---

## C. Correo urgente
### Cuándo se envía
Solo si ocurre algo con impacto real y prioridad alta, por ejemplo:
- tracking crítico roto
- landing caída
- CTA principal o formulario fallando
- gasto anormal sin retorno
- discrepancia severa que comprometa decisiones
- incidente operativo serio
- cambio de riesgo medio/alto que no puede esperar sin costo claro

### Regla
El correo urgente es un canal de excepción, no de operación normal.

No usarlo para:
- pequeñas anomalías
- señales ambiguas
- recomendaciones interesantes pero no urgentes
- resúmenes
- propuestas que pueden esperar al lunes

---

## Política de aprobación

### Qué sí requiere aprobación
- mover presupuesto entre campañas
- pausar grupos de anuncios
- cambios relevantes en assets o mensajes
- cambios relevantes en landing page
- acciones con efecto visible sobre cobertura o conversión
- cambios estructurales o estratégicos
- cambios sensibles en tracking o medición
- cualquier acción clasificada como riesgo medio o alto

### Qué no requiere aprobación
- acciones de bajo riesgo permitidas por política
- acciones reversibles y locales con evidencia fuerte
- registro de observaciones
- reportes automáticos
- alertas críticas
- housekeeping técnico sin impacto operativo relevante

---

## Regla de calidad para toda solicitud de aprobación
Toda solicitud de aprobación debe explicar claramente:

1. **Qué propone hacer**
2. **Por qué lo propone**
3. **Qué evidencia lo respalda**
4. **Qué mejoraría si se aprueba**
5. **Qué riesgo existe**
6. **Qué tan reversible es**
7. **Qué recomienda el agente**

Si una solicitud no responde estas siete cosas, no está lista para enviarse.

---

## Formato obligatorio del correo de aprobación

### Asunto
Debe ser claro, corto y accionable.

Formato sugerido:
- `[APROBACIÓN REQUERIDA] <acción concreta>`
- `[APROBACIÓN REQUERIDA] Reasignar presupuesto de Delivery a Local`
- `[APROBACIÓN REQUERIDA] Pausar grupo de anuncios con baja eficiencia`

No usar asuntos vagos como:
- "Revisión"
- "Sugerencia"
- "Cambios posibles"
- "Actualización"

---

### Cuerpo del correo
Toda solicitud debe seguir esta estructura:

#### 1. Acción propuesta
Qué quiere hacer exactamente el agente.

#### 2. Por qué
Qué problema o oportunidad detectó.

#### 3. Evidencia
Qué señales o datos respaldan la recomendación.

#### 4. Qué mejoraría
Qué impacto positivo espera si se aprueba.

#### 5. Riesgo
Qué riesgo tiene hacer este cambio.

#### 6. Reversibilidad
Si se puede revertir fácilmente o no.

#### 7. Recomendación del agente
Debe terminar con una postura clara:
- aprobar
- no aprobar todavía
- observar primero

#### 8. Respuesta esperada
Debe indicar exactamente cómo responder.

---

## Formato obligatorio del correo urgente

### Asunto
Debe comenzar con:
- `[URGENTE]`

Ejemplos:
- `[URGENTE] Posible falla en landing page`
- `[URGENTE] Tracking crítico roto`
- `[URGENTE] Gasto anormal sin retorno`

### Cuerpo
Debe ser corto, directo y con prioridad alta.

Estructura:
1. problema detectado
2. por qué importa
3. evidencia
4. impacto probable
5. acción sugerida o siguiente paso

### Regla visual
Si el diseño HTML del correo lo permite:
- usar encabezado rojo o bloque destacado
- mantener el texto corto
- poner arriba la prioridad
- evitar texto largo

---

## Regla de agrupación
Si existen varias aprobaciones no urgentes en una misma ventana, el agente debe agruparlas en un solo correo en vez de mandar múltiples correos separados.

### Objetivo
Reducir interrupciones y evitar fatiga de aprobación.

### Regla práctica
- agrupar siempre que sea razonable
- ordenar por prioridad
- máximo 3 aprobaciones principales por correo, salvo situación extraordinaria

---

## Regla de priorización
Si hay varias propuestas, el agente debe priorizar por este orden:

1. proteger medición y tracking
2. proteger conversión y landing
3. cortar desperdicio evidente
4. mover presupuesto hacia mejor retorno
5. mejoras secundarias de optimización

---

## Regla de caducidad
Cada solicitud de aprobación debe indicar si:
- puede esperar al siguiente ciclo semanal
- conviene resolverla dentro de 24 horas
- requiere decisión más rápida por costo de oportunidad o riesgo

Esto evita que todas las aprobaciones parezcan igual de urgentes.

---

## Mecanismo de aprobación — MVP

### Mecanismo oficial (activo)
El agente envía un correo con botones de acción generados como links de URL.

Cada propuesta incluye dos links directos:
- `✅ APROBAR` → `https://<cloud-run-url>/approve?d=<token>&action=approve`
- `❌ RECHAZAR` → `https://<cloud-run-url>/approve?d=<token>&action=reject`

Hugo hace clic en el link correspondiente.
El agente registra la decisión y ejecuta o descarta la acción.
No se requiere redactar ningún texto.

### Ventana de tiempo
Cada propuesta tiene una ventana de vigencia.
Si no se aprueba ni rechaza dentro del plazo, el agente registra la acción como `postponed` automáticamente.

### Regla
El mecanismo de URL-click es el único mecanismo de aprobación implementado en el MVP.
Es simple, robusto y no depende de parsear texto libre.

---

## Formato de respuesta del usuario (MVP)

No se redactan respuestas.
La acción es un clic en el link del correo.

No existe en el MVP:
- responder `APROBAR` por texto
- responder `RECHAZAR` por texto
- responder `POSPONER` por texto

---

## Formato de respuesta por texto (feature futura — no implementada)

En versiones futuras, podría habilitarse la posibilidad de responder directamente al correo con texto plano.

Formato contemplado para esa versión futura:
- `APROBAR`
- `RECHAZAR`
- `POSPONER`

Si hay múltiples acciones en un mismo correo:
- `APROBAR 1`
- `RECHAZAR 2`
- `APROBAR 1 Y 3`
- `POSPONER TODAS`

Esta funcionalidad requeriría un parser de respuestas de email y está fuera del alcance del MVP.

---

## Interpretación de respuesta (MVP — via URL-click)
### approve
El agente queda autorizado para ejecutar la acción descrita.
Registra `approved_at` y ejecuta inmediatamente.

### reject
La acción no se ejecuta.
El agente registra `rejected_at` y no insiste salvo nueva evidencia relevante.

### postponed (automático por timeout)
La acción no se ejecuta todavía.
El agente registra `postponed_at` y la reevalúa en el siguiente ciclo.

---

## Regla de no insistencia
Si Hugo rechaza una propuesta, el agente no debe volver a empujar la misma idea a menos que:
- cambie el contexto
- aparezca nueva evidencia fuerte
- aumente significativamente el impacto esperado
- el riesgo cambie

Esto evita correos repetitivos y molestos.

---

## Regla de claridad de impacto
Toda aprobación debe traducirse a lenguaje de negocio.

No basta con decir:
- "mejorará eficiencia"

Debe decir algo más concreto, por ejemplo:
- "podría mejorar la distribución del gasto semanal"
- "podría reducir desperdicio en tráfico de baja intención"
- "podría proteger conversiones evitando seguir enviando tráfico a una landing con falla"
- "podría mejorar retorno esperado sin tocar estructura central"

---

## Regla de carga mental
El sistema está bien diseñado si Hugo:
- recibe pocos correos
- entiende rápido por qué importa una propuesta
- sabe qué mejoraría
- puede aprobar o rechazar en segundos
- no siente que el agente le está delegando trabajo de análisis

El sistema está mal diseñado si:
- llegan demasiados correos
- las propuestas son ambiguas
- hay que leer demasiado para entender
- el agente manda ideas pero no decisiones claras
- Hugo siente que se volvió operador manual del sistema

---

## Plantilla de correo de aprobación

### Asunto
`[APROBACIÓN REQUERIDA] <acción concreta>`

### Cuerpo
**Acción propuesta**
[qué quiere hacer]

**Por qué**
[problema u oportunidad detectada]

**Evidencia**
[datos o señales principales]

**Qué mejoraría**
[beneficio esperado]

**Riesgo**
[bajo/medio/alto + explicación breve]

**Reversibilidad**
[alta/media/baja + explicación breve]

**Recomendación del agente**
[aprobar / observar / no aprobar todavía]

**Respuesta esperada**
Responder con: `APROBAR`, `RECHAZAR` o `POSPONER`

---

## Plantilla de correo urgente

### Asunto
`[URGENTE] <problema crítico>`

### Cuerpo
**Problema detectado**
[qué está pasando]

**Por qué importa**
[impacto probable]

**Evidencia**
[señales principales]

**Acción sugerida**
[siguiente paso]

**Nivel de prioridad**
Alto

---

## Regla final
El flujo de aprobación debe proteger control humano donde importa, sin destruir la autonomía útil del agente.

La aprobación humana debe ser la excepción estratégica, no la operación diaria.

El agente debe resolver solo lo que pueda resolver con seguridad, y pedir autorización solo cuando el beneficio de la supervisión humana supere el costo de la interrupción.
