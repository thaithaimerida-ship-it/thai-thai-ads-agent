# Diagnóstico — Pipeline de Conversiones GloriaFood

> Fecha: 2026-06-10 · Cuenta 402-107-0209 · Read-only (sin tocar código).
> Contradicción a resolver: la DB marca **7 conversiones subidas (7 días)**, pero Google
> Ads muestra **0** en "Pedido GloriaFood Online" (UPLOAD_CLICKS).

## Flujo real (pedido → webhook → DB → upload → ¿dónde aterriza?)

```
Pedido en GloriaFood (iframe embebido en thaithaimerida.com)
   │  El checkout vive en el iframe de GloriaFood. NO se captura gclid.
   ▼
GloriaFood "Accepted Orders API"  ──POST──►  /webhook/gloriafood  (Cloud Run, FastAPI)
   │  valida master key (GLORIAFOOD_MASTER_KEY)
   ▼
_parse_order(): order_id, total_price, items, nombre, TELÉFONO, EMAIL, tipo, pago
   │            (NO hay gclid / click id en el payload ni en la tabla)
   │
   ├─►(1) _log_order_to_db()  →  SQLite `gloriafood_orders` (+ sync a GCS)     [DATO COMPLETO ✓]
   │
   ├─►(2) _send_google_ads_conversion():
   │        • busca conversion_action por nombre = "Pedido GloriaFood Online"
   │          → id 7572944047 (UPLOAD_CLICKS, ENABLED)
   │        • arma ClickConversion con user_identifiers = SHA256(email) + SHA256(phone)
   │          → Enhanced Conversions for Leads, SIN gclid
   │        • upload_click_conversions(partial_failure=True)
   │        • respuesta SIN partial_failure_error  →  marca conversion_sent = 1
   │          (logs Cloud Run: "[CONV ...] Enhanced Conversion enviada: $X"; CERO "PARTIAL FAILURE")
   │
   └─►(3) _send_meta_capi_purchase()  →  Meta Conversions API (Purchase)   [otra vía; no afecta Ads]

Google Ads:
   ✔ Ingiere el upload sin error (la API lo "acepta")
   ✘ NO lo atribuye / NO lo cuenta  →  "Pedido GloriaFood Online" = 0 conversiones en 90d
```

## Respuestas a las preguntas

**a) ¿A dónde se suben las 7? ¿Qué marca `conversion_sent`?**
- Se suben a **Google Ads**, conversion_action **id 7572944047 "Pedido GloriaFood Online"**
  (UPLOAD_CLICKS) — confirmado en los logs ("conversion action encontrada:
  .../conversionActions/7572944047"). En paralelo, cada pedido **también** dispara
  **Meta CAPI** (`_send_meta_capi_purchase`), pero eso no toca Google Ads.
- **`conversion_sent=1` marca INTENTO ACEPTADO, no conversión contada.** El código pone
  el flag cuando `upload_click_conversions` regresa **sin** `partial_failure_error`
  (gloriafood_webhook.py: tras el upload, si no hay error parcial → log "enviada" →
  `UPDATE ... conversion_sent=1`). Es "la API recibió el upload", no "Google la atribuyó".

**b) ¿La tabla guarda gclid / click id?**
- **No.** Los campos son order_id, total, tipo, pago, nombre, teléfono, email, items,
  timestamps, conversion_sent. **No hay gclid ni ningún click id.**
- El upload se hace con **Enhanced Conversions for Leads** (email/teléfono hasheados).
  Google **solo** contaría esa conversión si esos identificadores hasheados machearan a un
  usuario de Google que **hizo clic en un anuncio de Thai Thai**. Los pedidos GloriaFood
  vienen mayormente de **orgánico / Maps / directo** (sin clic de anuncio macheable) →
  **no hay a qué atribuir** → 0 contadas.

**c) Respuestas de la API en logs (Cloud Run, últimos uploads):**
- Todos los uploads loguean **"Enhanced Conversion enviada: $X MXN"** y agregan email +
  phone identifier. **CERO ocurrencias de "PARTIAL FAILURE".** → La API **acepta** los
  uploads (no los rechaza). El problema no es rechazo: es **falta de atribución** aguas abajo.

**d) ¿Qué conversion_action_id alimenta "Pedido completado Gloria Food" (las 3)?**
- **id 7543665061 — status = REMOVED** (WEBPAGE, origin WEBSITE). Las **3 conversiones de
  90d son históricas** (de antes de eliminarla). **NO es el destino de los uploads** ni una
  vía viva. (Igual "Compra" id 7521296332 = REMOVED, su 1 conversión es histórica.)
- El destino real de los uploads es **7572944047** (ENABLED), que tiene **0 atribuidas**.

## VEREDICTO — dónde se pierde la conversión

**Se pierde en la ATRIBUCIÓN, no en el envío.** El webhook envía y la API **acepta** (logs
sin errores, `conversion_sent=1`), pero Google **no cuenta** la conversión porque:
1. **No hay gclid** (la tabla no lo guarda; el iframe de GloriaFood no lo expone).
2. El match por **Enhanced Conversions for Leads** (email/teléfono hasheados) **no encuentra
   un clic de anuncio** asociado — los pedidos son orgánicos/Maps/directo.

Por eso `money=$0` en el digest es **realidad estructural conocida**, no un bug del monitor:
el pipeline "pedido → DB" funciona perfecto (13 pedidos/$6,910 en 7 días, datos completos),
pero el tramo "upload → atribución en Ads" **nunca va a contar** sin un clic de anuncio real
detrás de cada pedido. **El reemplazo correcto es la tienda en línea propia con tracking
nativo** (gclid + evento de compra propio), no seguir insistiendo en el UPLOAD_CLICKS.

> Nota: `conversion_sent=1` es engañoso como métrica de "conversiones logradas" — solo
> significa "upload aceptado". Para medir conversiones reales de Ads hay que mirar el
> reporte de la conversion_action (que da 0), no el flag de la DB.
