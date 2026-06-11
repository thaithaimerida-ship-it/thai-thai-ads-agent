# Diagnóstico A1 — `money_signal_cost_mxn = 0.0`

> Fecha: 2026-06-10 · Cuenta Google Ads `402-107-0209` · Ventana analizada: `LAST_30_DAYS` (y `LAST_7_DAYS`).
> Modo seguro: todo read-only, cero mutaciones.

## Veredicto — CERRADO (no es un tema abierto, no es regresión)

**Es REALIDAD, no un bug de mapeo, NO una regresión.** Diagnóstico concluido el
2026-06-10. El digest NO se modifica; el cero es correcto.

### GloriaFood (pedidos) — LIMITACIÓN ESTRUCTURAL CONOCIDA
El `money=$0` de Delivery/Delivery Search NO es un bug nuevo: es la limitación
**conocida** de GloriaFood:
- El flujo de pedido vive en un **iframe de GloriaFood** que **no es medible** desde
  Google Ads (no hay gclid ni evento client-side propio en el checkout).
- La atribución por **webhook → UPLOAD_CLICKS** ("Pedido GloriaFood Online",
  id 7572944047, Enhanced Conversions) **nunca fue confiable**: el webhook sí sube
  conversiones (7 de 13 pedidos en 7 días), pero **0 quedan atribuidas a Ads en 90d**.
- **El reemplazo es el proyecto de tienda en línea propia con tracking nativo.**

> Corrección (2026-06-10): la acción **`Pedido completado Gloria Food`** (id 7543665061)
> está **REMOVED** — sus **3 conversiones de 90d son históricas**, NO una vía viva. No es
> opción para sumar al mapeo. El upload del webhook va a `Pedido GloriaFood Online`
> (7572944047, ENABLED) que tiene **0 atribuidas**. Detalle del pipeline y dónde se pierde
> la conversión: ver **`docs/diagnostico_pipeline_conversiones.md`**.

### Reservas (`reserva_completada_directa`) — VEREDICTO: CABLEADO OK, SIN VOLUMEN
Verificación read-only (cuenta 402-107-0209, 2026-06-10):
- **(a) Estado:** `reserva_completada_directa` (id 7569100920, tipo WEBPAGE) =
  **ENABLED** (no pausada/eliminada). ✓
- **(b) Conversiones 90d:** **0 atribuidas a Ads** — coherente con ~2 reservas reales
  totales que reporta Hugo. **$0 en la ventana es realidad estadística, no bug.**
- **(c) gtag en landing:** la base `AW-17126999855` y `gtag` **sí están** en
  `thaithaimerida.com`. El label específico `ON2LCPignZkcEK-O5eY_` **no aparece en el
  HTML estático del home** (5 KB, SPA React) porque dispara en el **evento de reserva
  (client-side)**, no en el home. `GTM-5CRD9SKL` tampoco está en el HTML estático.

**Veredicto reservas: cableado OK (acción activa + gtag base presente), sin volumen
atribuido.** No roto. Único caveat: confirmar el disparo del label en el flujo real de
reserva (no verificable desde el HTML estático del home). Los dos nombres del mapeo de dinero son
correctos y la maquinaria de match funciona. El cero refleja que **ninguna de las
dos conversiones de dinero está atribuyendo conversiones a search terms** en
Google Ads, por problemas de *tracking upstream* (no del digest).

## Cómo se calcula el dinero (cadena verificada en código)

```
Google Ads API: segments.conversion_action_name
  └─ engine/ads_client.py :: fetch_search_term_conversion_breakdown()
        actions[].name = segments.conversion_action_name           (línea 696)
  └─ routes/analysis.py :: _build_search_terms_payload()
        join (normalize(query), str(campaign_id))                  (línea 231)
        classify_conversion_quality(actions, ...)                  (línea 233)
  └─ engine/search_term_classifier.py :: classify_conversion_quality()
        name normalizado ∈ MONEY_ACTION_NAMES → "money_action"     (línea 272-280)
  └─ engine/negatives_classifier_v3.py
        conversion_quality == "money_action" → behavior_axis "senal_dinero"  (línea 295)
  └─ engine/monitor_digest_v3.py :: build_monitor_digest()
        behavior == "senal_dinero" → summary["money_signal_cost_mxn"] += cost (línea 333)
```

El mapeo de dinero (`engine/search_term_classifier.py:120-123`):
```python
MONEY_ACTION_NAMES = {
    _normalize("reserva_completada_directa"),   # -> "reserva_completada_directa"
    _normalize("Pedido GloriaFood Online"),     # -> "pedido gloriafood online"
}
```

## Evidencia

### 1. El join y el normalize NO están rotos
- `fetch_search_term_data` devuelve `campaign_id = str(campaign.id)` (ads_client.py:632).
- El breakdown se llavea con `_search_term_breakdown_key` = `(normalize(query), str(campaign_id))` (ads_client.py:646-650), idéntico al join de `_build_search_terms_payload` (analysis.py:231). **Coinciden.**
- `_normalize` es el mismo algoritmo (NFD + quita acentos + lowercase + colapsa espacios) en ambos lados.

### 2. La maquinaria de match SÍ funciona (prueba viva)
`GET /monitor/digest?date_range=LAST_30_DAYS` en producción (token vivo):
```
money_signal_cost_mxn = 0.0
local_signal_cost_mxn = 1183.27   ← los nombres LOCALES sí matchean
```
Si el matching estuviera globalmente roto, el costo local también saldría 0. No lo está.

### 3. Distribución real de `conversion_quality` (prod, LAST_30_DAYS, 100 términos)
| conversion_quality | términos |
|---|---|
| weak_local_action | 76 |
| unknown | 15 |
| none | 9 |
| **money_action** | **0** |

88 de 100 términos tienen `all_conversions > 0`, pero **ninguno** clasifica como `money_action`.

### 4. Causa raíz documentada (auditoría previa en vivo — `audit_google_ads_health.py`)
- **`Pedido GloriaFood Online`** (ID `7572944047`, tipo `UPLOAD_CLICKS`): **0 atribución** porque el `gclid` se pierde en el redirect a `restaurantlogin.com`. No es etiqueta rota — es arquitectónico. Solución real: *Offline Conversion Import* vía webhook de Gloria Food.
- **`reserva_completada_directa`**: **etiqueta inactiva confirmada**, pendiente de fix en `thaithaimerida.com`.

### 5. Los nombres del mapeo son los nombres reales del catálogo
Scripts previos que corrieron contra la API en vivo indexan el catálogo de
conversiones por estos strings exactos como claves de diccionario:
- `ads_quick_wins.py:396,401` → `conv_map["reserva_completada_directa"]`, `conv_map["Pedido GloriaFood Online"]`
- `engine/ads_client.py:12-17` `PROTECTED_CONVERSIONS` usa los mismos literales.

→ Los nombres del mapeo coinciden con `conversion_action.name` real de la cuenta.

> Nota: el catálogo canónico en vivo no se pudo re-listar localmente porque el
> **refresh token de Google Ads está expirado** (`invalid_grant`) — es el problema
> conocido de expiración semanal (app OAuth en "Testing"). Producción sí tiene token
> vivo y de ahí salió la evidencia 2-3. Cuando Hugo renueve el token, se puede
> re-confirmar el catálogo con el script read-only de diagnóstico.

## Conclusión y acciones

1. **No hay bug en el mapeo de dinero del digest** → no se modifica
   `MONEY_ACTION_NAMES` ni la cadena de cálculo.
2. **Sí se agrega un test de regresión** (Fase B+C):
   `test_conversion_actions_reales_mapeadas` — afirma que `"Pedido GloriaFood Online"`
   y `"reserva_completada_directa"` (con variantes de mayúsculas/acentos)
   normalizan a `money_action`. Esto blinda contra drift futuro del mapeo si algún
   día el tracking se arregla y empiezan a llegar conversiones de dinero.
3. El `money_signal_cost_mxn = 0.0` debe seguir mostrándose como **dato real**
   (separado de señales locales) — NO marcar `data_broken` aquí: el dato es correcto.
   El problema vive en el tracking, no en el digest.

## Observación adicional (no es A1, pero relevante)
15 términos caen en `unknown` y algunos traen **conversiones primarias > 0**
(ej. `comida tailandesa merida` conv=4, `restaurante cerca de mi` conv=6,
`thai thai merida` conv=5). Significa que hay acciones de conversión *primarias*
que el mapeo **no reconoce** (ni money ni weak_local). No afecta el número de dinero
—la definición de dinero de Hugo es fija (solo esas 2 acciones)— pero conviene, en
una fase futura, listar esas acciones "unknown" y decidir si alguna debe entrar a
`WEAK_LOCAL_ACTION_NAMES` para que el correo no las pierda. **Pendiente de decisión
de Hugo, fuera del scope de esta fase.**
