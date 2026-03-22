# Design Spec: Restructura de Campañas + Tracking Fix
**Fecha:** 2026-03-22
**Proyecto:** Thai Thai Ads Agent
**Customer ID:** 4021070209

---

## Objetivo

Corregir el tracking roto entre Google Ads y GA4, restructurar las 2 campañas existentes con objetivos específicos, crear 1 nueva campaña de Reservaciones (tipo Search), y construir todas las capacidades de escritura que el agente necesita para ejecutar esto y mantenerlo autónomamente.

---

## Problemas que resuelve

1. **Tracking roto:** 2,770 clics de Google Ads llegan como "Direct" en GA4 → auto-tagging desactivado
2. **Conversiones falsas:** Google Ads reporta 791 conversiones; GA4 registra 11 reales → micro-conversiones incorrectas activas
3. **Sin separación por objetivo:** 2 campañas mezclan delivery + reservas + local
4. **Geo incorrecto:** Tráfico de USA y zonas fuera del área de servicio
5. **CPA targets incorrectos en código:** $15 genérico vs reales por tipo de campaña
6. **Sin capacidades de escritura:** El agente solo puede agregar negative keywords

---

## Arquitectura de la solución

### Parte 1 — Nuevas funciones en `engine/ads_client.py`

| Función | API Service | Notas de implementación |
|---|---|---|
| `enable_auto_tagging(client, customer_id)` | CustomerService | Requiere `customer` resource name + `update_mask` con campo `auto_tagging_enabled` |
| `update_campaign_name(client, customer_id, campaign_id, new_name)` | CampaignService | Mutate con update_mask |
| `update_campaign_location(client, customer_id, campaign_id, location_id)` | CampaignCriterionService | Para geo por ciudad (criterion type: LOCATION) |
| `update_campaign_proximity(client, customer_id, campaign_id, lat, lng, radius_km)` | CampaignCriterionService | Para geo por radio (criterion type: PROXIMITY) — distinto a LOCATION |
| `update_campaign_budget(client, customer_id, budget_resource_name, budget_micros)` | CampaignBudgetService | budget_micros = MXN × 1,000,000 |
| `create_search_campaign(client, customer_id, name, budget_micros, target_cpa_micros, geo_type, geo_value)` | CampaignBudgetService → CampaignService | Operación en 2 pasos: 1) crear budget, 2) crear campaign referenciando budget |
| `create_ad_group(client, customer_id, campaign_resource_name, name, cpc_bid_micros)` | AdGroupService | Requerido antes de agregar keywords o ads |
| `create_rsa(client, customer_id, ad_group_resource_name, headlines, descriptions)` | AdGroupAdService | Responsive Search Ad — mínimo 3 headlines, 2 descriptions |
| `add_keyword_to_ad_group(client, customer_id, ad_group_resource_name, keyword_text, match_type)` | AdGroupCriterionService | match_type: EXACT o BROAD |
| `update_ad_schedule(client, customer_id, campaign_id, day, start_hour, end_hour, bid_modifier)` | CampaignCriterionService | Criterion type: AD_SCHEDULE |
| `fetch_conversion_actions(client, customer_id)` | GoogleAdsService | Lista todas las conversiones activas |
| `disable_conversion_action(client, customer_id, conversion_action_id)` | ConversionActionService | Solo ejecutar con lista de IDs aprobada explícitamente — NUNCA por nombre |
| `log_agent_action(action_type, target, details_before, details_after, status, api_response)` | SQLite local | Registra toda acción con antes/después |

**Regla de micros:** `MXN × 1,000,000 = micros`
- $50 MXN = 50,000,000 micros
- $70 MXN = 70,000,000 micros
- $100 MXN = 100,000,000 micros

### Parte 2 — Nuevos endpoints en `main.py`

| Endpoint | Método | Qué hace |
|---|---|---|
| `POST /fix-tracking` | POST | Activa auto-tagging. Lista conversiones y devuelve propuesta de cuáles desactivar — requiere aprobación explícita antes de ejecutar |
| `POST /fix-tracking/confirm` | POST | Recibe IDs aprobados por el usuario y ejecuta la desactivación |
| `POST /restructure-campaigns` | POST | Rename + geo + budget de las 2 campañas existentes |
| `POST /create-reservations-campaign` | POST | Crea campaign + budget + ad group + RSA + keywords para Reservaciones |
| `POST /update-ad-schedule` | POST | Aplica programación horaria basada en heatmap a las 3 campañas |
| `GET /audit-log` | GET | Historial de acciones. Params: `?limit=50&action_type=rename_campaign` |

### Parte 3 — Correcciones en `engine/analyzer.py`

Actualizar `_calculate_success_score()` para usar CPA target por tipo de campaña detectado por nombre:

```python
def _get_cpa_targets(campaign_name: str) -> dict:
    name = campaign_name.lower()
    if "delivery" in name:
        return {"ideal": 25, "max": 45, "critical": 80}
    elif "reserva" in name:
        return {"ideal": 50, "max": 85, "critical": 120}
    else:  # local / brand
        return {"ideal": 35, "max": 60, "critical": 100}
```

### Parte 4 — Tabla `agent_actions` en SQLite

```sql
CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT,
    details_before TEXT,
    details_after TEXT,
    status TEXT NOT NULL,       -- 'success' | 'failed' | 'requires_manual'
    google_ads_response TEXT
);
```

---

## Plan de ejecución — 4 pasos ordenados

### Paso 1: Fix de tracking (ejecutar primero)

1. Llamar `enable_auto_tagging()` con field_mask `auto_tagging_enabled` → cuenta `4021070209`
2. Llamar `fetch_conversion_actions()` → listar todas con sus IDs
3. Endpoint `/fix-tracking` devuelve propuesta al usuario: qué conversiones desactivar (con sus IDs)
4. Usuario confirma vía `/fix-tracking/confirm` con los IDs aprobados
5. **Protección:** `reserva_completada` y `pedido_completado_gloria_food` están en lista negra — NUNCA se desactivan
6. Log de cada acción

### Paso 2: Restructura de campañas existentes

**Thai Mérida** (ID: 22612348265) → Thai Mérida - Local
- Rename
- Geo: location_id `1010182` (Ciudad de Mérida) — criterion type LOCATION
- Budget: $50 MXN/día (50,000,000 micros)

**Restaurant Thai On Line** (ID: 22839241090) → Thai Mérida - Delivery
- Rename
- Geo: proximity lat `20.9674`, lng `-89.5926`, radio 8km — criterion type PROXIMITY
- Budget: $100 MXN/día (100,000,000 micros)

### Paso 3: Crear campaña nueva — Thai Mérida - Reservaciones (Search)

Operaciones en orden:
1. `create_campaign_budget` → $70 MXN/día (70,000,000 micros) → obtener `budget_resource_name`
2. `create_search_campaign` → nombre, budget, Target CPA $65 MXN (65,000,000 micros), geo proximity 30km
3. `create_ad_group` → "Reservaciones - General", CPC bid $20 MXN
4. `create_rsa` con:
   - Headlines (15 max): "Restaurante Thai en Mérida", "Reserva tu Mesa Hoy", "Cocina Artesanal Tailandesa", "Thai Thai Mérida", "Sabor Auténtico de Tailandia", ...
   - Descriptions (4 max): "Experimenta la cocina tailandesa artesanal. Reserva en línea fácil y rápido.", "Ingredientes frescos, recetas auténticas. Tu mesa te espera en Thai Thai Mérida."
5. `add_keyword_to_ad_group` para cada keyword de Reservaciones (ver lista abajo)
6. Agregar negative keywords: a domicilio, delivery, receta, masaje, spa, gratis, rappi, uber eats

**Keywords Reservaciones:**
- `restaurante thai mérida` — EXACT
- `thai thai mérida` — EXACT
- `reservar restaurante mérida` — BROAD
- `cena romántica mérida` — BROAD
- `restaurante tailandés mérida` — EXACT
- `mejor restaurante thai mérida` — EXACT

### Paso 4: Programación horaria (las 3 campañas)

Basado en heatmap del agente:
- **Lun-Dom 6am-11pm:** activo (bid modifier 0)
- **12pm-2pm:** bid modifier +20% (pico almuerzo)
- **6pm-9pm:** bid modifier +15% (pico cena)
- **11pm-5am:** eliminar criterio / bid modifier -100% (sin demanda)

---

## Reglas de seguridad del agente

1. **Conversiones protegidas** (NUNCA desactivar): `reserva_completada`, `pedido_completado_gloria_food`, `click_pedir_online`
2. **Aprobación requerida** antes de desactivar cualquier conversión
3. **Log obligatorio** de cada mutación — si falla el log, no ejecutar la acción
4. **Rollback info:** guardar estado anterior en `details_before` para poder revertir manualmente

---

## Lo que requiere acción manual del usuario (~10 min)

1. Confirmar lista de conversiones a desactivar en `/fix-tracking`
2. Verificar link GA4 ↔ Google Ads en UI: Google Ads → Herramientas → Conversiones → importadas de GA4
3. Verificar link en GA4 Admin: Administrador → Vinculación de Google Ads → confirmar cuenta activa

---

## Archivos modificados

- `engine/ads_client.py` — agregar 13 funciones
- `engine/analyzer.py` — actualizar CPA targets por tipo de campaña
- `main.py` — agregar 6 endpoints
- `database/schema.sql` (o init en main.py) — nueva tabla `agent_actions`

---

## Criterios de éxito

- [ ] GA4 muestra tráfico de Paid Search (no Direct) dentro de 48h de activar auto-tagging
- [ ] 3 campañas activas con nombres correctos en Google Ads
- [ ] Geo: Delivery 8km, Reservaciones 30km, Local ciudad de Mérida
- [ ] CPA targets correctos en el dashboard por tipo de campaña
- [ ] Audit log con paginación disponible en `/audit-log`
- [ ] Conversiones reales activas: solo `reserva_completada` + `pedido_completado_gloria_food` + `click_pedir_online`
- [ ] Ad schedule aplicado a las 3 campañas
