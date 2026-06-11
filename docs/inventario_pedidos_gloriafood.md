# Inventario de Pedidos GloriaFood (read-only)

> Fecha: 2026-06-10 · Insumo para el proyecto de tienda en línea propia.
> Solo conteos y estructura — NO se exportaron datos personales al repo.

## Dónde están guardados
- **SQLite, tabla `gloriafood_orders`** — la escribe `routes/gloriafood_webhook.py`
  (`_log_order_to_db`) vía `engine.memory` / `engine.db_sync.get_db_path()`.
- **Persistencia canónica = DB de Cloud Run sincronizada a GCS** (`db_sync.upload_to_gcs`
  tras cada pedido). NO es Supabase (el proyecto `oghtjvvasdhbjbuemhks` no recibe pedidos;
  el webhook usa SQLite).
- Endpoints de lectura en prod: `GET /webhook/gloriafood/stats` (7 días),
  `/webhook/gloriafood/debug-fields` (presencia de campos, sin valores).

## Cuántos pedidos / desde cuándo
- **Prod (7 días, vía `/stats`):** **13 pedidos**, **$6,910 MXN**, **7 conversiones
  subidas a Ads** (Enhanced Conversions).
- **No hay endpoint de conteo histórico total** (solo ventana 7d). El acumulado completo
  vive en la DB de GCS; para el conteo total habría que añadir un endpoint o leer el GCS.
- Copia local del repo (`_runtime_thai_thai_memory.db`): **1 pedido** (2026-04-13, dev) —
  NO representativo de prod. `thai_thai_memory.db` y el `get_db_path()` local: sin la tabla.

## Qué campos se guardan
`gloriafood_order_id` (UNIQUE), `total_price_mxn`, `order_type` (delivery/pickup),
`payment_method`, `client_name`, `client_phone`, `client_email`,
`items_json` (lista name/quantity/price) + `items_count`, `accepted_at`, `received_at`,
`conversion_sent` (0/1).

## Estado del dato
- **Completo**: los pedidos recientes traen nombre, teléfono, email e items (confirmado
  vía `/debug-fields`). Buena calidad para CRM / tienda online.
- **Sin duplicados**: `gloriafood_order_id UNIQUE` + `INSERT OR IGNORE` deduplican.
- **conversion_sent**: 7 de 13 subieron a Ads, pero esas conversiones **no quedan
  atribuidas** (la UPLOAD_CLICKS "Pedido GloriaFood Online" da 0 en 90d — ver
  `diagnostico_dinero.md`). El dato del pedido en sí (cliente, monto, items) **sí está
  completo y es la base sólida para la tienda en línea propia**.

## Recomendación para la tienda online
Estos pedidos (cliente + teléfono + email + items + montos) son un dataset limpio y
deduplicado para sembrar el catálogo, la base de clientes recurrentes y el tracking
nativo de conversiones que reemplazará la medición no-confiable de GloriaFood.
