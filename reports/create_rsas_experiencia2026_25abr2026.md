# QW9: Creacion RSAs Mejorados — Thai Merida Experiencia 2026

**Fecha/hora:** 25 de April de 2026, 22:46:48  
**Cuenta:** 4021070209  
**Campaña:** Thai Merida - Experiencia 2026  
**Operacion:** `AdGroupAdService.mutate_ad_group_ads` — solo CREATE  
**RSAs existentes:** mantenidos ENABLED sin modificacion  

**Estado:** EXITOSO  
**RSAs creados:** 2 de 2  

## Ad Group: Comida Auténtica

### Resultado

| Campo | Valor |
|-------|-------|
| Ad group ID | 195552527936 |
| Ad ID (existente, mantenido) | 804020249717 |
| Ad ID (nuevo creado) | 806786186626 |
| Estado | CREADO EXITOSAMENTE |
| Final URL | https://www.thaithaimerida.com |
| Path | Restaurante/Thai-Merida |

### Headlines del RSA Nuevo (15)

| # | Texto | Chars |
|---|-------|:-----:|
| 1 | Comida Tailandesa Auténtica | 27 |
| 2 | Sabores de Tailandia | 20 |
| 3 | Pad Thai Real en Mérida | 23 |
| 4 | Curry Thai Auténtico | 20 |
| 5 | Cocina Thai Tradicional | 23 |
| 6 | Thai Food en Mérida | 19 |
| 7 | El Mejor Thai de Yucatán | 24 |
| 8 | Platillos Tailandeses Reales | 28 |
| 9 | Menú Thai Completo | 18 |
| 10 | Cocina Thai Artesanal | 21 |
| 11 | Curries Hechos Desde Cero | 25 |
| 12 | Thai Dumplings Caseros | 22 |
| 13 | Reserva Tu Mesa Hoy | 19 |
| 14 | Mérida Norte: Calle 30 | 22 |
| 15 | Sabor Thai en Mérida Centro | 27 |

### Descriptions del RSA Nuevo (4)

| # | Texto | Chars |
|---|-------|:-----:|
| 1 | Pad Thai, curries y más platillos auténticos de Tailandia en Mérida. | 68 |
| 2 | Ingredientes originales y recetas tradicionales tailandesas. ¡Visítanos! | 72 |
| 3 | La cocina tailandesa más auténtica de Yucatán. Mar-Dom, 13 a 21 horas. | 70 |
| 4 | Pad Thai, Thai Dumplings, Curry de Cacahuate. Cocina artesanal hecha desde cero. | 80 |

### Confirmacion Post-Mutacion

| Ad ID | Path | Ad Strength |
|-------|------|:-----------:|
| 804020249717 | (sin path) | AVERAGE |
| 806786186626 | Restaurante/Thai-Merida | PENDING |

---

## Ad Group: Turistas (Inglés)

### Resultado

| Campo | Valor |
|-------|-------|
| Ad group ID | 192324817342 |
| Ad ID (existente, mantenido) | 803942233183 |
| Ad ID (nuevo creado) | 806786186629 |
| Estado | CREADO EXITOSAMENTE |
| Final URL | https://www.thaithaimerida.com |
| Path | Thai-Restaurant/Merida |

### Headlines del RSA Nuevo (15)

| # | Texto | Chars |
|---|-------|:-----:|
| 1 | Thai Restaurant Merida | 22 |
| 2 | Authentic Thai Food Merida | 26 |
| 3 | Best Thai in Mérida | 19 |
| 4 | Thai Thai Merida Mexico | 23 |
| 5 | Real Thai Cuisine Yucatan | 25 |
| 6 | Thai Dining in Merida | 21 |
| 7 | Visit Thai Thai Merida | 22 |
| 8 | Thai Food Near You Merida | 25 |
| 9 | Dine Thai in Merida MX | 22 |
| 10 | Handmade Thai Cuisine | 21 |
| 11 | Authentic Pad Thai Mérida | 25 |
| 12 | Fresh Curries Made Daily | 24 |
| 13 | Book Your Thai Experience | 25 |
| 14 | Modern Thai Atmosphere | 22 |
| 15 | Try Our Butterfly Tea Latte | 27 |

### Descriptions del RSA Nuevo (4)

| # | Texto | Chars |
|---|-------|:-----:|
| 1 | Authentic Thai cuisine in the heart of Mérida. Open Tue-Sun 1pm to 9pm. | 71 |
| 2 | Discover real Thai flavors in Yucatán. Book your table at Thai Thai Mérida. | 75 |
| 3 | Best Thai restaurant in Mérida, Mexico. Traditional recipes, great atmosphere. | 78 |
| 4 | Pad Thai, Thai Dumplings, Peanut Curry. Handmade artisan cuisine in Mérida Norte. | 81 |

### Confirmacion Post-Mutacion

| Ad ID | Path | Ad Strength |
|-------|------|:-----------:|
| 803942233183 | (sin path) | POOR |
| 806786186629 | Thai-Restaurant/Merida | PENDING |

---

## Proximos Pasos

### Cronograma de evaluacion

| Fecha | Accion |
|-------|--------|
| ~10 may 2026 (14 dias) | Revisar Ad Strength de los RSAs nuevos en Google Ads UI |
| ~25 may 2026 (30 dias) | Re-correr `_diag_rsas_experiencia2026.py` para ver performance labels |
| ~25 may 2026 | Si nuevo RSA muestra GOOD o EXCELLENT, evaluar pausar el viejo |
| ~25 jun 2026 | Re-evaluar ad schedule con mayor volumen de conversiones |

### Senales para pausar el RSA viejo

- RSA nuevo tiene Ad Strength GOOD o EXCELLENT
- RSA nuevo tiene CTR >= RSA viejo en el mismo periodo
- Al menos 30 dias de datos comparativos

### Display paths agregados

Los RSAs existentes no tenian display path configurado.
Los nuevos RSAs incluyen paths especificos:
- Comida Autentica: `/Restaurante/Thai-Merida`
- Turistas (Ingles): `/Thai-Restaurant/Merida`

Esto mejora el CTR al hacer la URL visible mas relevante para la busqueda.

---
_Solo se crearon nuevos RSAs. No se modifico ni pauso ningun RSA existente._
_No se toco bidding, presupuesto, schedule, geo, audiencias ni otras campanas._