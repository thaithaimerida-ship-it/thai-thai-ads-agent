# Risk Matrix — Thai Thai Ads Agent

## Propósito
Este documento define cómo clasificar el riesgo de una acción dentro de Thai Thai Ads Agent y qué nivel de autonomía corresponde en cada caso.

La meta no es volver al agente tímido ni hiperactivo.
La meta es que actúe con criterio.

Toda acción debe evaluarse según:
1. impacto potencial en rendimiento o estabilidad
2. reversibilidad
3. sensibilidad del sistema afectado
4. claridad de la evidencia
5. probabilidad de dañar aprendizaje, medición o negocio real

---

## Principio general
El agente no debe actuar solo porque detectó una oportunidad.
Debe actuar solo si la combinación de evidencia + bajo riesgo + reversibilidad lo justifica.

Si el riesgo supera la autonomía permitida, debe escalar.
Si la señal es débil, debe observar.
Si el problema es crítico, debe alertar de inmediato y, si corresponde, ejecutar una acción defensiva de bajo riesgo.

---

## Niveles de riesgo

### Riesgo bajo
Una acción es de riesgo bajo cuando:
- su alcance es local y limitado
- es fácilmente reversible o de impacto acotado
- no altera la estructura base de la campaña
- no cambia estrategia de puja
- no modifica budgets globales
- no afecta conversion actions primarias
- existe evidencia clara de que el cambio corrige desperdicio o error puntual

**Autonomía permitida:**
El agente puede ejecutar automáticamente y reportar después.

---

### Riesgo medio
Una acción es de riesgo medio cuando:
- afecta rendimiento visible de una campaña o grupo
- tiene tradeoffs reales
- puede ayudar, pero también puede alterar estabilidad si se ejecuta mal
- requiere juicio contextual de negocio
- toca elementos con impacto importante, pero no irreversible
- necesita validación humana antes de aplicarse

**Autonomía permitida:**
El agente debe preparar la acción completa y pedir aprobación antes de ejecutar.

---

### Riesgo alto
Una acción es de riesgo alto cuando:
- altera estructura o estrategia central
- puede cambiar de forma significativa el aprendizaje algorítmico
- puede afectar medición, tráfico o gasto en escala relevante
- toca configuración crítica o sensible
- es difícil de revertir rápidamente
- un error puede producir daño financiero, operativo o de interpretación

**Autonomía permitida:**
El agente nunca ejecuta sin autorización explícita.

---

## Estados operativos del agente

### Estado 0 — Observar
Usar cuando:
- la evidencia es insuficiente
- la señal es ambigua
- el volumen de datos es bajo
- la campaña está en aprendizaje
- el comportamiento puede ser fluctuación normal

**Resultado esperado:**
No ejecutar ni escalar todavía. Registrar y seguir observando.

---

### Estado 1 — Ejecutar
Usar cuando:
- la acción es de riesgo bajo
- la evidencia es fuerte
- el cambio es reversible o acotado
- no afecta estabilidad estructural

**Resultado esperado:**
Ejecutar automáticamente y dejarlo documentado en reporte/log.

---

### Estado 2 — Proponer para aprobación
Usar cuando:
- la acción es de riesgo medio
- la acción es útil, pero requiere validación humana
- hay impacto visible o sensibilidad importante

**Resultado esperado:**
Preparar propuesta lista para aprobar con justificación, riesgo, impacto esperado y reversibilidad.

---

### Estado 3 — Bloquear y escalar
Usar cuando:
- la acción es de riesgo alto
- requiere autorización explícita
- el daño potencial supera la autonomía permitida

**Resultado esperado:**
No ejecutar. Escalar con explicación clara.

---

## Factores de evaluación

### 1. Impacto potencial
Preguntas guía:
- ¿Puede afectar gasto, tráfico, conversiones o estabilidad de forma visible?
- ¿El impacto es local o sistémico?
- ¿Un error sería pequeño o costoso?

### 2. Reversibilidad
Preguntas guía:
- ¿Se puede revertir rápido?
- ¿La reversión devuelve realmente al estado anterior?
- ¿El aprendizaje perdido se recupera fácilmente o no?

### 3. Claridad de evidencia
Preguntas guía:
- ¿Hay suficiente volumen de datos?
- ¿La señal es clara o discutible?
- ¿Hay consistencia entre Ads, GA4 y lógica de negocio?

### 4. Sensibilidad del área afectada
Áreas sensibles:
- bidding strategy
- budgets
- conversion actions
- tracking
- estructura de campañas
- automatizaciones que tocan dinero real

### 5. Momento del sistema
Preguntas guía:
- ¿La campaña está en aprendizaje?
- ¿Se han hecho cambios recientes?
- ¿Hay suficiente estabilidad para juzgar?

---

## Matriz de decisiones por tipo de acción

## 1. Keywords

### Pausar keyword con gasto claramente desperdiciado y cero conversiones
**Riesgo:** Bajo
**Autonomía:** Ejecutar
**Condiciones mínimas:**
- evidencia suficiente de ineficiencia
- no está en fase demasiado temprana
- no hay señales compensatorias relevantes
- el cambio no afecta estructura central

### Agregar negative keyword obvia
**Riesgo:** Bajo
**Autonomía:** Ejecutar
**Condiciones mínimas:**
- irrelevancia clara
- afecta calidad del tráfico
- cambio local y reversible

### Pausar múltiples keywords simultáneamente
**Riesgo:** Medio
**Autonomía:** Pedir aprobación
**Razón:** El efecto acumulado puede alterar aprendizaje o cobertura.

### Reestructurar estrategia de keywords
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización
**Razón:** Cambio estructural.

---

## 2. Presupuesto

### Reasignar presupuesto pequeño entre campañas
**Riesgo:** Medio
**Autonomía:** Pedir aprobación
**Razón:** Afecta distribución de gasto y aprendizaje.

### Aumentar o reducir presupuesto de una campaña de forma relevante
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización
**Razón:** Impacto financiero y algorítmico importante.

### Congelar gasto por comportamiento anormal extremo
**Riesgo:** Alto, pero con excepción operativa
**Autonomía:** Escalar urgente; solo ejecutar defensivamente si existe política explícita previa
**Razón:** Puede proteger dinero, pero también afectar aprendizaje y delivery.

---

## 3. Campañas y grupos de anuncios

### Pausar grupo de anuncios
**Riesgo:** Medio
**Autonomía:** Pedir aprobación

### Pausar campaña completa
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

### Crear campaña nueva
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

### Cambiar estructura de campañas
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

---

## 4. Bidding y estrategia algorítmica

### Ajustar bidding strategy
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

### Cambiar CPA target o lógica de puja
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

### Sugerir cambio de estrategia de puja
**Riesgo:** Medio como propuesta / Alto como ejecución
**Autonomía:** Proponer, no ejecutar

---

## 5. Conversiones y medición

### Detectar tracking roto
**Riesgo del problema:** Crítico
**Autonomía de acción:** Alertar de inmediato
**Ejecución automática:** Solo medidas seguras de diagnóstico, no cambios estructurales sin aprobación

### Modificar conversion action primaria
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

### Marcar inconsistencia entre Ads y GA4
**Riesgo:** Bajo como observación
**Autonomía:** Registrar y alertar si impacta decisiones

### Cambiar configuración crítica de GTM/medición
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

---

## 6. Landing page y conversión web

### Detectar que la landing está caída
**Riesgo del problema:** Crítico
**Autonomía:** Alertar de inmediato

### Detectar que CTA, formulario o reserva no funciona
**Riesgo del problema:** Crítico
**Autonomía:** Alertar de inmediato

### Cambios menores de texto o UX de bajo impacto
**Riesgo:** Medio
**Autonomía:** Preparar propuesta para aprobación

### Cambios relevantes de estructura, flujo o componentes clave
**Riesgo:** Alto
**Autonomía:** No ejecutar sin autorización

---

## 7. Reportes y alertas

### Enviar reporte semanal
**Riesgo:** Bajo
**Autonomía:** Ejecutar automáticamente

### Enviar alerta por anomalía leve
**Riesgo:** Bajo, pero riesgo de ruido
**Autonomía:** No enviar WhatsApp; registrar en reporte

### Enviar alerta por incidente crítico
**Riesgo del problema:** Crítico
**Autonomía:** Enviar WhatsApp inmediato

---

## Política de alertas críticas

Enviar alerta inmediata por WhatsApp solo si ocurre alguna de estas condiciones:

- caída abrupta y anormal de conversiones
- gasto anormal sin señales de valor
- landing rota
- CTA principal o flujo de reserva roto
- tracking crítico roto
- discrepancia severa entre fuentes de datos que comprometa decisiones
- fallo de ejecución en procesos sensibles
- cualquier incidente que pueda causar pérdida relevante de dinero o demanda

No usar WhatsApp para:
- resúmenes normales
- observaciones ambiguas
- recomendaciones no urgentes
- pequeñas variaciones diarias

---

## Regla especial: campañas en aprendizaje

Si una campaña está en fase de aprendizaje:
- elevar el umbral de intervención
- evitar cambios por señales débiles
- no hacer múltiples ajustes cercanos en el tiempo
- priorizar observación sobre acción
- solo intervenir automáticamente si existe desperdicio extremo, error crítico o problema operacional evidente

---

## Regla especial: evidencia insuficiente

Aunque una acción parezca de bajo riesgo, no debe ejecutarse si:
- no hay suficiente volumen de datos
- la señal es ambigua
- no existe consistencia mínima entre fuentes
- el contexto sugiere que el sistema aún no puede juzgar con confiabilidad

En ese caso, pasar a **Observar**.

---

## Formato esperado para propuestas de riesgo medio o alto

Cuando el agente no pueda ejecutar, debe presentar la propuesta con esta estructura:

1. **Acción propuesta**
2. **Motivo**
3. **Evidencia**
4. **Nivel de riesgo**
5. **Impacto esperado**
6. **Reversibilidad**
7. **Recomendación final**
8. **Si requiere aprobación explícita**

---

## Regla de desempate
Si existe duda entre dos niveles de riesgo, elegir el nivel más conservador.

Si existe duda entre actuar y observar, observar primero, salvo que:
- exista pérdida evidente,
- exista error crítico,
- o la omisión tenga mayor costo que la acción.

---

## Criterio de éxito
La matriz de riesgo es correcta si ayuda a que el agente:
- actúe solo cuando debe
- no moleste a Hugo con cosas menores
- no deje pasar problemas críticos
- no rompa estabilidad por exceso de entusiasmo
- reduzca carga operativa sin perder control
