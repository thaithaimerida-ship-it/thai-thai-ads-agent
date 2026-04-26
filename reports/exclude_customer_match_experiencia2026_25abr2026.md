# QW6: Exclusion Customer Match — Thai Merida Experiencia 2026

**Fecha/hora:** 25 de April de 2026, 22:20:19  
**Cuenta:** 4021070209  
**Operacion:** `CampaignCriterionService.mutate_campaign_criteria` — `negative=True`  

**Estado:** EXITOSO — exclusion aplicada y confirmada  

## Segmento Excluido

| Campo | Valor |
|-------|-------|
| Nombre | Clientes GloriaFood 2023-2026 |
| ID | 9367630629 |
| Miembros activos (search) | 100 |
| Resource name | `customers/4021070209/userLists/9367630629` |

## Campaña Afectada

| Campo | Valor |
|-------|-------|
| Nombre | Thai Merida - Experiencia 2026 |
| ID | 23730364039 |
| Resource name | `customers/4021070209/campaigns/23730364039` |
| Tipo | Search (ENABLED) |

## Estado Pre-Mutacion

_Ninguna exclusion/inclusion USER_LIST existente en la campaña._

## Resultado de Mutacion

Exclusion creada exitosamente via `CampaignCriterionOperation.create` con `negative=True`.

| Campo aplicado | Valor |
|----------------|-------|
| campaign | `customers/4021070209/campaigns/23730364039` |
| user_list.user_list | `customers/4021070209/userLists/9367630629` |
| negative | True |

## Confirmacion Post-Mutacion (GAQL)

| Criterio ID | User List | Tipo | Status |
|-------------|-----------|:----:|:------:|
| 2546499693317 | `customers/4021070209/userLists/9367630629` | EXCLUSION | ENABLED |

**Exclusion de 'Clientes GloriaFood 2023-2026': ACTIVA y CONFIRMADA**

## Razon de Negocio

Los 100 clientes activos en 'Clientes GloriaFood 2023-2026' ya conocen Thai Thai.
Experiencia 2026 debe enfocarse en adquisicion de nuevos clientes, no en retargeting.
La exclusion evita gastar presupuesto de adquisicion en audiencias ya convertidas.

**Campanas NO afectadas (decision intencional):**
- Thai Merida - Delivery: puede mostrar a clientes existentes (recompra)
- Thai Merida - Local: Smart Campaign, gestion automatica
- Thai Merida - Reservaciones: PAUSED

---
_Solo se modifico campaign_criterion USER_LIST en Thai Merida - Experiencia 2026._
_No se modifico el user_list, otras campanas, bidding, presupuesto ni geo._