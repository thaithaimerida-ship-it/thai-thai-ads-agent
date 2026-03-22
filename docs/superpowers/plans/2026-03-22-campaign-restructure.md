# Campaign Restructure + Tracking Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir capacidades de escritura en el agente de Google Ads, corregir el tracking roto (auto-tagging), restructurar 2 campañas existentes con objetivos específicos, crear 1 campaña nueva de Reservaciones (Search), y registrar cada acción en un audit log.

**Architecture:** Se agregan 13 funciones de escritura a `engine/ads_client.py` usando la Google Ads Python library. Seis nuevos endpoints en `main.py` orquestan estas funciones con flujo de aprobación para acciones destructivas. Una nueva tabla SQLite `agent_actions` registra todo.

**Tech Stack:** Python 3.11, FastAPI, Google Ads Python Library v24+, SQLite (`thai_thai_memory.db`), pytest

---

## File Map

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `engine/ads_client.py` | Modificar | Agregar 13 funciones de escritura a Google Ads API |
| `engine/analyzer.py` | Modificar | CPA targets por tipo de campaña (líneas 30-41) |
| `main.py` | Modificar | Agregar 6 endpoints + tabla agent_actions en init_db() |
| `tests/test_ads_client_write.py` | Crear | Tests unitarios para funciones de escritura (mock API) |
| `tests/test_analyzer_cpa.py` | Crear | Tests para lógica de CPA targets |
| `tests/test_endpoints_campaigns.py` | Crear | Tests de integración para nuevos endpoints |

---

## Task 1: Tabla agent_actions en SQLite

**Files:**
- Modify: `main.py:113-135` (función `init_db`)

- [ ] **Step 1: Agregar CREATE TABLE a init_db()**

En `main.py`, dentro de `init_db()`, agregar después del commit de `reservations`:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        action_type TEXT NOT NULL,
        target TEXT,
        details_before TEXT,
        details_after TEXT,
        status TEXT NOT NULL,
        google_ads_response TEXT
    )
""")
conn.commit()
```

- [ ] **Step 2: Verificar que el servidor arranca sin error**

```bash
cd "c:\Users\usuario\Downloads\thai-thai-ads-agent"
curl http://localhost:8000/health
```
Expected: `{"status":"ok",...}`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add agent_actions audit table to SQLite"
```

---

## Task 2: Fix CPA targets en analyzer.py

**Files:**
- Modify: `engine/analyzer.py:30-41`
- Create: `tests/test_analyzer_cpa.py`

- [ ] **Step 1: Escribir tests que fallan**

Crear `tests/test_analyzer_cpa.py`:

```python
import sys
sys.path.insert(0, ".")
from engine.analyzer import _get_cpa_targets, _calculate_success_score_v2

def test_delivery_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Delivery")
    assert targets["ideal"] == 25
    assert targets["max"] == 45
    assert targets["critical"] == 80

def test_reservaciones_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Reservaciones")
    assert targets["ideal"] == 50
    assert targets["max"] == 85
    assert targets["critical"] == 120

def test_local_cpa_targets():
    targets = _get_cpa_targets("Thai Mérida - Local")
    assert targets["ideal"] == 35
    assert targets["max"] == 60
    assert targets["critical"] == 100

def test_delivery_score_excellent():
    # CPA $20 para delivery → excelente (bajo ideal $25)
    score = _calculate_success_score_v2(cpa=20, has_conversions=True, campaign_name="Thai Mérida - Delivery")
    assert score >= 90

def test_reservaciones_score_critical():
    # CPA $130 para reservaciones → crítico (sobre $120)
    score = _calculate_success_score_v2(cpa=130, has_conversions=True, campaign_name="Thai Mérida - Reservaciones")
    assert score <= 25
```

- [ ] **Step 2: Correr tests — deben fallar**

```bash
cd "c:\Users\usuario\Downloads\thai-thai-ads-agent"
python -m pytest tests/test_analyzer_cpa.py -v
```
Expected: `ImportError` o `AttributeError` (funciones no existen aún)

- [ ] **Step 3: Agregar funciones a analyzer.py**

Al inicio de `engine/analyzer.py`, agregar:

```python
def _get_cpa_targets(campaign_name: str) -> dict:
    """Retorna CPA targets según tipo de campaña detectado por nombre."""
    name = campaign_name.lower()
    if "delivery" in name:
        return {"ideal": 25, "max": 45, "critical": 80}
    elif "reserva" in name:
        return {"ideal": 50, "max": 85, "critical": 120}
    else:  # local / brand / default
        return {"ideal": 35, "max": 60, "critical": 100}

def _calculate_success_score_v2(cpa: float, has_conversions: bool, campaign_name: str = "") -> int:
    """Score por campaña usando CPA targets reales por tipo."""
    if not has_conversions:
        return 20
    targets = _get_cpa_targets(campaign_name)
    if cpa <= targets["ideal"]:
        return 95
    elif cpa <= targets["max"]:
        return 75
    elif cpa <= targets["critical"]:
        return 45
    else:
        return 20
```

- [ ] **Step 4: Reemplazar llamadas a _calculate_success_score en analyzer.py**

Buscar en `engine/analyzer.py` todas las llamadas a `_calculate_success_score(cpa, has_conversions)` y reemplazarlas por `_calculate_success_score_v2(cpa, has_conversions, campaign_name)`, pasando el nombre de campaña disponible en el contexto. Si alguna llamada no tiene el nombre de campaña disponible, usar `""` como fallback (aplica targets de Local).

- [ ] **Step 5: Correr tests — deben pasar**

```bash
python -m pytest tests/test_analyzer_cpa.py -v
```
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add engine/analyzer.py tests/test_analyzer_cpa.py
git commit -m "feat: add per-campaign-type CPA targets to analyzer"
```

---

## Task 3: log_agent_action + enable_auto_tagging

**Files:**
- Modify: `engine/ads_client.py`
- Create: `tests/test_ads_client_write.py`

- [ ] **Step 1: Escribir test para log_agent_action**

Crear `tests/test_ads_client_write.py`:

```python
import sqlite3, os, sys, json
sys.path.insert(0, ".")

# Usar DB de test separada
TEST_DB = "test_thai_thai.db"

def setup_test_db():
    conn = sqlite3.connect(TEST_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT,
            details_before TEXT,
            details_after TEXT,
            status TEXT NOT NULL,
            google_ads_response TEXT
        )
    """)
    conn.commit()
    conn.close()

def test_log_agent_action_success():
    setup_test_db()
    from engine.ads_client import log_agent_action
    log_agent_action(
        action_type="rename_campaign",
        target="Thai Mérida",
        details_before={"name": "Thai Mérida"},
        details_after={"name": "Thai Mérida - Local"},
        status="success",
        google_ads_response={"resource_name": "customers/4021070209/campaigns/22612348265"},
        db_path=TEST_DB
    )
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT * FROM agent_actions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row[3] == "rename_campaign"  # action_type
    assert row[7] == "success"          # status
    os.remove(TEST_DB)
```

- [ ] **Step 2: Correr test — debe fallar**

```bash
python -m pytest tests/test_ads_client_write.py::test_log_agent_action_success -v
```
Expected: `ImportError`

- [ ] **Step 3: Implementar log_agent_action en ads_client.py**

Al final de `engine/ads_client.py`, agregar:

```python
import sqlite3
from datetime import datetime

def log_agent_action(action_type: str, target: str, details_before: dict,
                     details_after: dict, status: str, google_ads_response: dict = None,
                     db_path: str = "thai_thai_memory.db"):
    """Registra toda acción ejecutada en Google Ads en el audit log."""
    import json
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO agent_actions (timestamp, action_type, target, details_before, details_after, status, google_ads_response)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        action_type,
        target,
        json.dumps(details_before, ensure_ascii=False),
        json.dumps(details_after, ensure_ascii=False),
        status,
        json.dumps(google_ads_response, ensure_ascii=False) if google_ads_response else None
    ))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Implementar enable_auto_tagging**

```python
def enable_auto_tagging(client: GoogleAdsClient, customer_id: str) -> dict:
    """Activa auto-tagging en la cuenta para que GA4 atribuya clics correctamente."""
    try:
        customer_service = client.get_service("CustomerService")
        customer_operation = client.get_type("CustomerOperation")

        customer = customer_operation.update
        customer.resource_name = customer_service.customer_path(customer_id)
        customer.auto_tagging_enabled = True

        field_mask = client.get_type("FieldMask")
        field_mask.paths.append("auto_tagging_enabled")
        customer_operation.update_mask.CopyFrom(field_mask)

        response = customer_service.mutate_customer(
            customer_id=customer_id,
            operation=customer_operation
        )
        return {"status": "success", "resource_name": response.resource_name}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 5: Correr tests**

```bash
python -m pytest tests/test_ads_client_write.py -v
```
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add engine/ads_client.py tests/test_ads_client_write.py
git commit -m "feat: add log_agent_action and enable_auto_tagging"
```

---

## Task 4: update_campaign_name + update_campaign_budget

**Files:**
- Modify: `engine/ads_client.py`
- Modify: `tests/test_ads_client_write.py`

- [ ] **Step 1: Agregar tests (mocked)**

En `tests/test_ads_client_write.py`, agregar:

```python
from unittest.mock import MagicMock, patch

def test_update_campaign_name_calls_mutate():
    with patch("engine.ads_client.GoogleAdsClient") as MockClient:
        mock_client = MockClient.return_value
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        mock_client.get_type.return_value = MagicMock()
        mock_service.mutate_campaigns.return_value = MagicMock(results=[MagicMock(resource_name="customers/123/campaigns/456")])

        from engine.ads_client import update_campaign_name
        result = update_campaign_name(mock_client, "4021070209", "22612348265", "Thai Mérida - Local")
        assert result["status"] == "success"
        mock_service.mutate_campaigns.assert_called_once()
```

- [ ] **Step 2: Implementar update_campaign_name**

```python
def update_campaign_name(client: GoogleAdsClient, customer_id: str, campaign_id: str, new_name: str) -> dict:
    """Renombra una campaña existente."""
    try:
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")

        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        campaign.name = new_name

        campaign_operation.update_mask.paths.append("name")

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 3: Implementar update_campaign_budget**

```python
def update_campaign_budget(client: GoogleAdsClient, customer_id: str,
                           budget_resource_name: str, budget_micros: int) -> dict:
    """Actualiza el presupuesto diario de una campaña. budget_micros = MXN × 1,000,000"""
    try:
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")

        budget = budget_operation.update
        budget.resource_name = budget_resource_name
        budget.amount_micros = budget_micros

        budget_operation.update_mask.paths.append("amount_micros")

        response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 4: Correr tests**

```bash
python -m pytest tests/test_ads_client_write.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add engine/ads_client.py tests/test_ads_client_write.py
git commit -m "feat: add update_campaign_name and update_campaign_budget"
```

---

## Task 5: Geo targeting — location y proximity

**Files:**
- Modify: `engine/ads_client.py`

- [ ] **Step 1: Implementar update_campaign_location (por ciudad)**

```python
def update_campaign_location(client: GoogleAdsClient, customer_id: str,
                              campaign_id: str, location_id: str) -> dict:
    """Restringe campaña a una ciudad/región por location_id (criterion type: LOCATION).
    Mérida, Yucatán location_id: '1010182'
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        criterion_operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")
        geo_target_service = client.get_service("GeoTargetConstantService")

        criterion = criterion_operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.location.geo_target_constant = geo_target_service.geo_target_constant_path(location_id)

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[criterion_operation]
        )
        return {"status": "success", "location_id": location_id}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 2: Implementar update_campaign_proximity (por radio km)**

```python
def update_campaign_proximity(client: GoogleAdsClient, customer_id: str,
                               campaign_id: str, lat: float, lng: float, radius_km: float) -> dict:
    """Restringe campaña por radio desde coordenadas (criterion type: PROXIMITY).
    Centro Mérida: lat=20.9674, lng=-89.5926
    Delivery: radius_km=8, Reservaciones: radius_km=30
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        criterion_operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")

        criterion = criterion_operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.proximity.address.city_name = "Mérida"
        criterion.proximity.address.country_code = "MX"
        criterion.proximity.geo_point.longitude_in_micro_degrees = int(lng * 1_000_000)
        criterion.proximity.geo_point.latitude_in_micro_degrees = int(lat * 1_000_000)
        criterion.proximity.radius = radius_km
        criterion.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[criterion_operation]
        )
        return {"status": "success", "radius_km": radius_km}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 3: Commit**

```bash
git add engine/ads_client.py
git commit -m "feat: add location and proximity geo targeting functions"
```

---

## Task 6: Conversion actions — fetch y disable

**Files:**
- Modify: `engine/ads_client.py`

```python
# Lista negra de conversiones protegidas — NUNCA desactivar
PROTECTED_CONVERSIONS = {"reserva_completada", "pedido_completado_gloria_food", "click_pedir_online"}
```

- [ ] **Step 1: Implementar fetch_conversion_actions**

```python
def fetch_conversion_actions(client: GoogleAdsClient, customer_id: str) -> list:
    """Lista todas las conversiones activas con sus IDs y nombres."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT conversion_action.id, conversion_action.name, conversion_action.status
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        return [{"id": str(row.conversion_action.id),
                 "name": row.conversion_action.name,
                 "status": row.conversion_action.status.name,
                 "protected": row.conversion_action.name in PROTECTED_CONVERSIONS}
                for row in response]
    except GoogleAPIError as e:
        return []
```

- [ ] **Step 2: Implementar disable_conversion_action con safety guard**

```python
def disable_conversion_action(client: GoogleAdsClient, customer_id: str,
                               conversion_action_id: str, conversion_name: str) -> dict:
    """Desactiva una conversión. RECHAZA si el nombre está en PROTECTED_CONVERSIONS."""
    if conversion_name in PROTECTED_CONVERSIONS:
        return {"status": "rejected", "reason": f"'{conversion_name}' está protegida y no puede desactivarse"}

    try:
        ca_service = client.get_service("ConversionActionService")
        ca_operation = client.get_type("ConversionActionOperation")

        ca = ca_operation.update
        ca.resource_name = ca_service.conversion_action_path(customer_id, conversion_action_id)
        ca.status = client.enums.ConversionActionStatusEnum.HIDDEN

        ca_operation.update_mask.paths.append("status")

        response = ca_service.mutate_conversion_actions(
            customer_id=customer_id,
            operations=[ca_operation]
        )
        return {"status": "success", "conversion_action_id": conversion_action_id}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 3: Test del safety guard**

En `tests/test_ads_client_write.py`, agregar:

```python
def test_disable_protected_conversion_rejected():
    from unittest.mock import MagicMock
    from engine.ads_client import disable_conversion_action

    mock_client = MagicMock()
    result = disable_conversion_action(mock_client, "4021070209", "999", "reserva_completada")
    assert result["status"] == "rejected"
    mock_client.get_service.assert_not_called()  # No debe llegar a la API
```

- [ ] **Step 4: Correr test**

```bash
python -m pytest tests/test_ads_client_write.py::test_disable_protected_conversion_rejected -v
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add engine/ads_client.py tests/test_ads_client_write.py
git commit -m "feat: add fetch/disable conversion actions with safety guard"
```

---

## Task 7: create_search_campaign (multi-step)

**Files:**
- Modify: `engine/ads_client.py`

- [ ] **Step 1: Implementar create_search_campaign**

```python
def create_search_campaign(client: GoogleAdsClient, customer_id: str,
                            name: str, budget_micros: int,
                            target_cpa_micros: int) -> dict:
    """
    Crea campaña Search en 2 pasos:
    1) CampaignBudget, 2) Campaign con Target CPA.
    Retorna resource_names de budget y campaign.
    """
    try:
        # Paso 1: Crear budget
        budget_service = client.get_service("CampaignBudgetService")
        budget_operation = client.get_type("CampaignBudgetOperation")

        budget = budget_operation.create
        budget.name = f"Budget - {name}"
        budget.amount_micros = budget_micros
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

        budget_response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        budget_resource = budget_response.results[0].resource_name

        # Paso 2: Crear campaign
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")

        campaign = campaign_operation.create
        campaign.name = name
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        campaign.status = client.enums.CampaignStatusEnum.PAUSED  # Arrancar pausada para revisar antes de activar
        campaign.campaign_budget = budget_resource
        campaign.target_cpa.target_cpa_micros = target_cpa_micros
        campaign.network_settings.target_google_search = True
        campaign.network_settings.target_search_network = True
        campaign.network_settings.target_content_network = False

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )
        campaign_resource = campaign_response.results[0].resource_name

        return {"status": "success", "budget_resource": budget_resource, "campaign_resource": campaign_resource}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

**Nota:** La campaña se crea en estado `PAUSED`. Activar manualmente después de revisar.

- [ ] **Step 2: Commit**

```bash
git add engine/ads_client.py
git commit -m "feat: add create_search_campaign (budget + campaign two-step)"
```

---

## Task 8: create_ad_group + create_rsa + add_keyword_to_ad_group

**Files:**
- Modify: `engine/ads_client.py`

- [ ] **Step 1: Implementar create_ad_group**

```python
def create_ad_group(client: GoogleAdsClient, customer_id: str,
                    campaign_resource_name: str, name: str,
                    cpc_bid_micros: int = 20_000_000) -> dict:
    """Crea ad group dentro de una campaña. cpc_bid_micros default = $20 MXN"""
    try:
        ad_group_service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")

        ad_group = operation.create
        ad_group.name = name
        ad_group.campaign = campaign_resource_name
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        ad_group.cpc_bid_micros = cpc_bid_micros

        response = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[operation])
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 2: Implementar create_rsa**

```python
def create_rsa(client: GoogleAdsClient, customer_id: str,
               ad_group_resource_name: str, headlines: list, descriptions: list,
               final_url: str = "https://www.thaithaimerida.com") -> dict:
    """Crea Responsive Search Ad. Requiere mínimo 3 headlines y 2 descriptions."""
    if len(headlines) < 3 or len(descriptions) < 2:
        return {"status": "error", "message": "RSA requiere mínimo 3 headlines y 2 descriptions"}
    try:
        ad_group_ad_service = client.get_service("AdGroupAdService")
        operation = client.get_type("AdGroupAdOperation")

        ad_group_ad = operation.create
        ad_group_ad.ad_group = ad_group_resource_name
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

        rsa = ad_group_ad.ad.responsive_search_ad
        for text in headlines[:15]:
            asset = client.get_type("AdTextAsset")
            asset.text = text[:30]  # Max 30 chars por headline
            rsa.headlines.append(asset)
        for text in descriptions[:4]:
            asset = client.get_type("AdTextAsset")
            asset.text = text[:90]  # Max 90 chars por description
            rsa.descriptions.append(asset)

        ad_group_ad.ad.final_urls.append(final_url)

        response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id, operations=[operation])
        return {"status": "success", "resource_name": response.results[0].resource_name}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 3: Implementar add_keyword_to_ad_group**

```python
def add_keyword_to_ad_group(client: GoogleAdsClient, customer_id: str,
                             ad_group_resource_name: str, keyword_text: str,
                             match_type: str = "EXACT") -> dict:
    """Agrega keyword a un ad group. match_type: 'EXACT' o 'BROAD'"""
    try:
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")

        criterion = operation.create
        criterion.ad_group = ad_group_resource_name
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match_type)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "keyword": keyword_text, "match_type": match_type}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 4: Commit**

```bash
git add engine/ads_client.py
git commit -m "feat: add create_ad_group, create_rsa, add_keyword_to_ad_group"
```

---

## Task 9: update_ad_schedule

**Files:**
- Modify: `engine/ads_client.py`

- [ ] **Step 1: Implementar update_ad_schedule**

```python
def update_ad_schedule(client: GoogleAdsClient, customer_id: str, campaign_id: str,
                       day_of_week: str, start_hour: int, end_hour: int,
                       bid_modifier: float = 0.0) -> dict:
    """
    Configura horario de anuncios para un día/hora.
    day_of_week: 'MONDAY','TUESDAY',...,'SUNDAY'
    bid_modifier: 0.0 = normal, 0.20 = +20%, -1.0 = pausar
    """
    try:
        criterion_service = client.get_service("CampaignCriterionService")
        operation = client.get_type("CampaignCriterionOperation")
        campaign_service = client.get_service("CampaignService")

        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.bid_modifier = 1.0 + bid_modifier  # API espera multiplicador (1.2 = +20%)
        criterion.ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, day_of_week)
        criterion.ad_schedule.start_hour = start_hour
        criterion.ad_schedule.end_hour = end_hour
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[operation]
        )
        return {"status": "success", "day": day_of_week, "hours": f"{start_hour}-{end_hour}"}
    except GoogleAPIError as e:
        return {"status": "error", "message": str(e)}
```

- [ ] **Step 2: Commit**

```bash
git add engine/ads_client.py
git commit -m "feat: add update_ad_schedule"
```

---

## Task 10: Endpoints /fix-tracking y /fix-tracking/confirm

**Files:**
- Modify: `main.py`
- Modify: `tests/test_endpoints_campaigns.py`

- [ ] **Step 1: Crear tests/test_endpoints_campaigns.py**

```python
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, ".")
from main import app

client = TestClient(app)

def test_audit_log_returns_list():
    response = client.get("/audit-log")
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data
    assert isinstance(data["actions"], list)

def test_audit_log_accepts_limit_param():
    response = client.get("/audit-log?limit=5")
    assert response.status_code == 200
```

- [ ] **Step 2: Agregar modelos Pydantic en main.py**

```python
class FixTrackingConfirmRequest(BaseModel):
    conversion_action_ids: List[str]  # IDs aprobados por el usuario para desactivar
```

- [ ] **Step 3: Agregar endpoint /fix-tracking en main.py**

```python
@app.post("/fix-tracking")
async def fix_tracking():
    """
    Paso 1: Activa auto-tagging.
    Paso 2: Lista conversiones y propone cuáles desactivar (requiere confirmación).
    """
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import enable_auto_tagging, fetch_conversion_actions, log_agent_action

    # Paso 1: Auto-tagging
    auto_tag_result = enable_auto_tagging(client, customer_id)
    log_agent_action("enable_auto_tagging", f"cuenta {customer_id}", {},
                     {"auto_tagging_enabled": True}, auto_tag_result["status"], auto_tag_result)

    # Paso 2: Listar conversiones
    conversions = fetch_conversion_actions(client, customer_id)
    to_disable = [c for c in conversions if not c["protected"]]

    return {
        "auto_tagging": auto_tag_result,
        "conversions_found": conversions,
        "proposed_to_disable": to_disable,
        "protected": [c for c in conversions if c["protected"]],
        "next_step": "POST /fix-tracking/confirm con los IDs que apruebas desactivar"
    }
```

- [ ] **Step 4: Agregar endpoint /fix-tracking/confirm**

```python
@app.post("/fix-tracking/confirm")
async def fix_tracking_confirm(request: FixTrackingConfirmRequest):
    """Desactiva las conversiones aprobadas por el usuario."""
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
    client = modules["get_ads_client"]()

    from engine.ads_client import fetch_conversion_actions, disable_conversion_action, log_agent_action

    all_conversions = {c["id"]: c["name"] for c in fetch_conversion_actions(client, customer_id)}
    results = []

    for ca_id in request.conversion_action_ids:
        name = all_conversions.get(ca_id, "unknown")
        result = disable_conversion_action(client, customer_id, ca_id, name)
        log_agent_action("disable_conversion", name, {"status": "ENABLED"},
                         {"status": "HIDDEN"}, result["status"], result)
        results.append({"id": ca_id, "name": name, "result": result})

    return {"results": results}
```

- [ ] **Step 5: Correr tests**

```bash
python -m pytest tests/test_endpoints_campaigns.py -v
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_endpoints_campaigns.py
git commit -m "feat: add /fix-tracking and /fix-tracking/confirm endpoints"
```

---

## Task 11: Endpoint /restructure-campaigns

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Implementar endpoint**

```python
@app.post("/restructure-campaigns")
async def restructure_campaigns():
    """
    Restructura las 2 campañas existentes:
    - Thai Mérida (22612348265) → Thai Mérida - Local (geo: Mérida ciudad, $50/día)
    - Restaurant Thai On Line (22839241090) → Thai Mérida - Delivery (geo: 8km, $100/día)
    """
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = "4021070209"
    client = modules["get_ads_client"]()

    from engine.ads_client import (update_campaign_name, update_campaign_location,
                                    update_campaign_proximity, update_campaign_budget,
                                    log_agent_action)

    # Obtener resource names de los budgets actuales para actualizarlos
    ga_service = client.get_service("GoogleAdsService")
    budget_query = """
        SELECT campaign.id, campaign.campaign_budget
        FROM campaign
        WHERE campaign.id IN (22612348265, 22839241090)
    """
    budget_map = {}
    for row in ga_service.search(customer_id=customer_id, query=budget_query):
        budget_map[str(row.campaign.id)] = row.campaign.campaign_budget

    results = []

    # --- Thai Mérida → Local ($50/día) ---
    r1 = update_campaign_name(client, customer_id, "22612348265", "Thai Mérida - Local")
    log_agent_action("rename_campaign", "Thai Mérida", {"name": "Thai Mérida"},
                     {"name": "Thai Mérida - Local"}, r1["status"], r1)

    r2 = update_campaign_location(client, customer_id, "22612348265", "1010182")
    log_agent_action("update_geo", "Thai Mérida - Local", {}, {"location": "Mérida ciudad"}, r2["status"], r2)

    r3 = update_campaign_budget(client, customer_id, budget_map["22612348265"], 50_000_000)
    log_agent_action("update_budget", "Thai Mérida - Local", {}, {"budget_day_mxn": 50}, r3["status"], r3)

    results.append({"campaign": "Thai Mérida - Local", "rename": r1, "geo": r2, "budget": r3})

    # --- Restaurant Thai On Line → Delivery ($100/día) ---
    r4 = update_campaign_name(client, customer_id, "22839241090", "Thai Mérida - Delivery")
    log_agent_action("rename_campaign", "Restaurant Thai On Line",
                     {"name": "Restaurant Thai On Line"}, {"name": "Thai Mérida - Delivery"}, r4["status"], r4)

    r5 = update_campaign_proximity(client, customer_id, "22839241090",
                                    lat=20.9674, lng=-89.5926, radius_km=8.0)
    log_agent_action("update_geo", "Thai Mérida - Delivery", {},
                     {"proximity_km": 8, "center": "Mérida"}, r5["status"], r5)

    r6 = update_campaign_budget(client, customer_id, budget_map["22839241090"], 100_000_000)
    log_agent_action("update_budget", "Thai Mérida - Delivery", {}, {"budget_day_mxn": 100}, r6["status"], r6)

    results.append({"campaign": "Thai Mérida - Delivery", "rename": r4, "geo": r5, "budget": r6})

    return {"status": "success", "results": results}
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add /restructure-campaigns endpoint"
```

---

## Task 12: Endpoint /create-reservations-campaign

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Implementar endpoint**

```python
@app.post("/create-reservations-campaign")
async def create_reservations_campaign():
    """
    Crea campaña Search 'Thai Mérida - Reservaciones':
    Budget $70/día, Target CPA $65, geo 30km, ad group + RSA + keywords.
    Se crea en estado PAUSED — activar manualmente tras revisión.
    """
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = "4021070209"
    client = modules["get_ads_client"]()

    from engine.ads_client import (create_search_campaign, create_ad_group, create_rsa,
                                    add_keyword_to_ad_group, update_campaign_proximity,
                                    add_negative_keyword, log_agent_action)

    # 1. Crear campaña
    campaign_result = create_search_campaign(
        client, customer_id,
        name="Thai Mérida - Reservaciones",
        budget_micros=70_000_000,      # $70 MXN/día
        target_cpa_micros=65_000_000   # Target CPA $65 MXN
    )
    if campaign_result["status"] != "success":
        raise HTTPException(status_code=500, detail=campaign_result)

    campaign_resource = campaign_result["campaign_resource"]
    log_agent_action("create_campaign", "Thai Mérida - Reservaciones", {},
                     {"budget_day": 70, "target_cpa": 65}, "success", campaign_result)

    # 2. Geo: 30km desde centro de Mérida
    # Extraer campaign_id del resource_name
    campaign_id = campaign_resource.split("/")[-1]
    update_campaign_proximity(client, customer_id, campaign_id, lat=20.9674, lng=-89.5926, radius_km=30.0)

    # 3. Crear ad group
    ad_group_result = create_ad_group(client, customer_id, campaign_resource,
                                       "Reservaciones - General", cpc_bid_micros=20_000_000)
    ad_group_resource = ad_group_result["resource_name"]

    # 4. Crear RSA
    headlines = [
        "Restaurante Thai en Mérida",
        "Reserva tu Mesa Hoy",
        "Cocina Artesanal Tailandesa",
        "Thai Thai Mérida",
        "Sabor Auténtico de Tailandia",
        "Cena Especial en Mérida",
        "El Mejor Thai de Yucatán",
        "Reservaciones en Línea",
        "Ingredientes Frescos y Auténticos",
        "Experiencia Culinaria Única"
    ]
    descriptions = [
        "Experimenta la cocina tailandesa artesanal. Reserva tu mesa en línea fácil y rápido.",
        "Ingredientes frescos, recetas auténticas. Tu mesa te espera en Thai Thai Mérida.",
        "Del wok a tu mesa. Sabores tailandeses únicos en el corazón de Mérida.",
        "Reserva ahora y vive una experiencia culinaria tailandesa inigualable."
    ]
    create_rsa(client, customer_id, ad_group_resource, headlines, descriptions)

    # 5. Agregar keywords positivas
    keywords = [
        ("restaurante thai mérida", "EXACT"),
        ("thai thai mérida", "EXACT"),
        ("reservar restaurante mérida", "BROAD"),
        ("cena romántica mérida", "BROAD"),
        ("restaurante tailandés mérida", "EXACT"),
        ("mejor restaurante thai mérida", "EXACT"),
    ]
    for kw_text, match_type in keywords:
        add_keyword_to_ad_group(client, customer_id, ad_group_resource, kw_text, match_type)

    # 6. Agregar negative keywords
    negative_kws = ["a domicilio", "delivery", "receta", "masaje", "spa", "gratis", "rappi", "uber eats"]
    for nkw in negative_kws:
        add_negative_keyword(client, customer_id, campaign_id, nkw)

    return {
        "status": "success",
        "campaign": "Thai Mérida - Reservaciones",
        "campaign_resource": campaign_resource,
        "note": "Campaña creada en PAUSED. Revisar en Google Ads UI y activar manualmente."
    }
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add /create-reservations-campaign endpoint"
```

---

## Task 13: Endpoint /update-ad-schedule y /audit-log

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Implementar /update-ad-schedule**

```python
@app.post("/update-ad-schedule")
async def update_ad_schedule_all():
    """
    Aplica programación horaria basada en heatmap a las 3 campañas.
    El ID de Reservaciones se obtiene dinámicamente consultando Google Ads.
    NOTA: La API no permite slots que crucen medianoche — la pausa nocturna
    se divide en dos slots: 23-24 y 0-6.
    """
    modules = get_engine_modules()
    if not modules:
        raise HTTPException(status_code=503, detail="Engine no disponible")

    customer_id = "4021070209"
    client = modules["get_ads_client"]()
    from engine.ads_client import update_ad_schedule, log_agent_action

    # Obtener ID de Reservaciones dinámicamente
    ga_service = client.get_service("GoogleAdsService")
    campaign_query = """
        SELECT campaign.id, campaign.name FROM campaign
        WHERE campaign.status = 'ENABLED' OR campaign.status = 'PAUSED'
    """
    campaign_ids = {}
    for row in ga_service.search(customer_id=customer_id, query=campaign_query):
        name = row.campaign.name.lower()
        if "local" in name:
            campaign_ids["local"] = str(row.campaign.id)
        elif "delivery" in name:
            campaign_ids["delivery"] = str(row.campaign.id)
        elif "reserva" in name:
            campaign_ids["reservaciones"] = str(row.campaign.id)

    results = []
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    for campaign_key, campaign_id in campaign_ids.items():
        for day in days:
            r1 = update_ad_schedule(client, customer_id, campaign_id, day, 12, 14, 0.20)   # +20% almuerzo
            r2 = update_ad_schedule(client, customer_id, campaign_id, day, 18, 21, 0.15)   # +15% cena
            r3 = update_ad_schedule(client, customer_id, campaign_id, day, 23, 24, -1.0)   # Pausa nocturna slot 1
            r4 = update_ad_schedule(client, customer_id, campaign_id, day, 0, 6, -1.0)     # Pausa nocturna slot 2
            results.append({"campaign": campaign_key, "day": day,
                            "lunch": r1, "dinner": r2, "night_23_24": r3, "night_0_6": r4})

        log_agent_action("update_ad_schedule", campaign_key, {}, {"schedule": "heatmap-based"}, "success")

    return {"status": "success", "campaigns_found": list(campaign_ids.keys()), "results": results}
```

- [ ] **Step 2: Implementar /audit-log**

```python
@app.get("/audit-log")
async def get_audit_log(limit: int = 50, action_type: Optional[str] = None):
    """Retorna historial de acciones ejecutadas por el agente."""
    import sqlite3, json
    conn = sqlite3.connect("thai_thai_memory.db")
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM agent_actions"
    params = []
    if action_type:
        query += " WHERE action_type = ?"
        params.append(action_type)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "total": len(rows),
        "actions": [dict(r) for r in rows]
    }
```

- [ ] **Step 3: Correr todos los tests**

```bash
python -m pytest tests/ -v
```
Expected: Todos los tests pasan

- [ ] **Step 4: Commit final**

```bash
git add main.py
git commit -m "feat: add /update-ad-schedule and /audit-log endpoints"
```

---

## Orden de ejecución en producción

Una vez implementado todo, ejecutar en este orden:

1. `POST /fix-tracking` → revisar propuesta de conversiones
2. `POST /fix-tracking/confirm` con IDs aprobados
3. `POST /restructure-campaigns` → renombrar + geo campañas existentes
4. `POST /create-reservations-campaign` → crear campaña nueva (queda PAUSED)
5. Revisar campaña en Google Ads UI → activar manualmente
6. `POST /update-ad-schedule` → aplicar horarios
7. `GET /audit-log` → verificar que todo quedó registrado
8. Esperar 48h → verificar GA4 muestra "Paid Search" en lugar de "Direct"
