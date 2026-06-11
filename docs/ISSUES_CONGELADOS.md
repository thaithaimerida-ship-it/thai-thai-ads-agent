# Issues congelados — Contrato visual v6.2

> Regla suprema anti-deriva: el contrato v6.2 es especificación literal. Lo que aquí
> se anota NO se implementa distinto — se implementa COMO DICE EL CONTRATO. Esta lista
> es solo memoria de cosas a revisar con Hugo en una fase futura.

## Anotaciones (implementadas como dice el contrato, no "mejoradas")
- **A3 salud "provisional"**: el contrato pide "señales + CTR vs su propio promedio de
  30 días, tres valores distintos". Implementado con ratios 7d-vs-30d reales (no clon de
  50). Si los datos de 30d faltan para una campaña, el ratio cae a 1.0 y el valor sigue
  siendo distinto por el CTR; no se clona un neutral. (Posible mejora futura: ponderar
  por volumen — NO implementada, fuera del contrato.)
- **A5 reseñas**: el contrato pide alerta roja solo para **≤3★** y botón IA solo para 5★.
  El builder calcula `requieren_atencion` ≤4★ (dato), pero el renderer muestra en rojo
  solo ≤3★ tal como exige el contrato. La 4★ con crítica no se renderiza como alerta.
- **A9 Search Console**: el contrato dice "(7 días)". Ventana cambiada a 7 días
  (terminando 3 días atrás por el lag de Search Console).
- **A12 separador de miles**: aplicado a TODOS los enteros vía `_int_text`.
- **Render de referencia ausente**: `docs/contrato_v6_2/` NO existe en el repo, así que no
  hubo imagen contra la cual comparar píxel a píxel. Implementé al pie del spec ESCRITO
  (A1-A11 + V-1..V-7) y auto-revisé el screenshot móvil sección por sección contra esa
  descripción de formato. Si Hugo sube el render congelado, se re-compara visualmente.

## Correcciones v6.2 ronda 2 (V-1..V-7) — formato
- V-1 anuncios: smart auto-ads (sin headline o campaña smart) resumidos en una línea;
  search deduplicados por título (×N variantes); jamás "(sin título)" (filtrado también
  en "los que más producen").
- V-2 caballos: tarjeta con borde + tabla 2 filas (etiquetas arriba, valores abajo).
- V-3 $/conv. y CPA 💰: dos decimales fijos (`_money2`).
- V-4 reseñas: mini-barras horizontales (tabla con celdas de color) por nivel 5★/4★/≤3★.
- V-5 búsquedas: microcopy literal del contrato.
- V-6 título: "Thai Thai Monitor" sin emoji.
- V-7 Maps: 4 métricas en la línea secundaria; Search Console no lista queries con 0 clics.
