# Reparar A2 — Search Console (0 impresiones / 0 clics)

> Fecha: 2026-06-10 · Modo seguro: read-only, sin mutaciones.

## ✅ RESUELTO (2026-06-10)
Hugo agregó el service account `thai-thai-ga4-reader@thai-thai-ads-master-agent.iam.gserviceaccount.com`
con permiso **Total** a la propiedad **URL-prefix** `https://thaithaimerida.com/` (la de
dominio existe pero está **SIN VERIFICAR** — NO usar `sc-domain:`, apunta a propiedad muerta).
La query real está cableada en `engine/monitor_sources.build_search_console_context()`
(`searchanalytics.query`, scope `webmasters.readonly`). **Verificado en vivo:** 1,252
impresiones · 20 clics · CTR 1.6% · posición 5.9 · top queries "thai thai"/"thai thai merida".
En prod: confirmar que la **Search Console API** esté habilitada en el proyecto
`thai-thai-ads-master-agent` al desplegar.

---

### Contexto original del diagnóstico (histórico)

## Diagnóstico

**La causa NO es "propiedad mal configurada que devuelve 0". La causa es que la
integración de Search Console NO EXISTE todavía en el repo.**

Verificado:
- No hay módulo de Search Console en el código (`engine/`, `routes/`): cero
  referencias reales a `webmasters` / `searchanalytics` / `searchconsole`.
- No hay credenciales de Search Console en `.env` (no existe `GSC_*` ni scope
  `webmasters`).
- El digest del PR #5 todavía no expone un bloque `search_console`.

Por eso cualquier "Search Console" hoy muestra ceros: **no está cableado**. El sitio
sí tiene actividad real (≈19.5K vistas en Maps), así que mostrar ceros sería mentir.

**Contrato mientras esté roto/ausente:** el digest devuelve
`search_console.data_broken = true` y el correo muestra **"en reparación"** —
JAMÁS ceros como si fueran datos. (Esto se implementa en B6/Renderer de esta fase.)

## Qué hace falta para que funcione (acción de Hugo en consolas Google)

La cuenta de servicio que ya usamos para GA4 es:

```
thai-thai-ga4-reader@thai-thai-ads-master-agent.iam.gserviceaccount.com
(project: thai-thai-ads-master-agent)
```

### Paso 1 — Habilitar la API
1. GCP Console → proyecto `thai-thai-ads-master-agent`.
2. APIs & Services → **Enable** → "Google Search Console API"
   (`searchconsole.googleapis.com`).

### Paso 2 — Dar acceso del service account a la propiedad
1. Abrir [Google Search Console](https://search.google.com/search-console).
2. Confirmar **qué tipo de propiedad** existe para el sitio. Hay dos posibles y
   son DISTINTAS (consultar la equivocada devuelve 0):
   - **Dominio**: identificador `sc-domain:thaithaimerida.com`
   - **Prefijo de URL**: identificador `https://thaithaimerida.com/`
   > Recomendado: usar la propiedad de **Dominio** si existe (cubre http/https,
   > www y no-www). Anotar el identificador exacto que aparezca.
3. En esa propiedad → Configuración → **Usuarios y permisos** → Agregar usuario:
   - Email: `thai-thai-ga4-reader@thai-thai-ads-master-agent.iam.gserviceaccount.com`
   - Permiso: **Restringido** (lectura) es suficiente para Search Analytics.

### Paso 3 — Confirmar el scope OAuth/credencial
- La integración debe pedir el scope de solo lectura:
  `https://www.googleapis.com/auth/webmasters.readonly`.
- Se reutiliza el JSON del service account (`ga4-credentials.json` /
  `GA4_CREDENTIALS_PATH`); no se necesitan credenciales nuevas, solo el acceso del
  Paso 2 + la API del Paso 1.

### Paso 4 — Avisar a Claude el identificador exacto de la propiedad
Una vez hechos los pasos 1-3, pasar a Claude el **identificador exacto** de la
propiedad (`sc-domain:thaithaimerida.com` o `https://thaithaimerida.com/`) para
cablear la query `searchanalytics.query` y validar contra datos reales.

## Causas probables ordenadas (si tras cablear sigue dando 0)
1. **Propiedad equivocada** (dominio vs URL-prefix): el caso más común. Verificar
   con el identificador exacto.
2. **Service account sin permiso** en la propiedad correcta (Paso 2 incompleto).
3. **API no habilitada** en el proyecto (Paso 1).
4. **Ventana de fechas**: Search Console tiene ~2-3 días de retraso; pedir datos de
   "ayer" puede salir vacío. Usar ventanas que terminen hace ≥3 días.
5. **Sitio sin verificación** en esa propiedad.

## Estado para esta fase
- B6 implementa el bloque `search_console` con `data_broken=true` por defecto
  (datos reales solo cuando Hugo complete los pasos 1-4).
- El renderer muestra "Search Console — en reparación", nunca ceros.
- No se cablea la query real hasta tener el identificador exacto de propiedad +
  acceso confirmado (acción de Hugo).
