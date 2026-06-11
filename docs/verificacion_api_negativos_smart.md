# Verificación: negativos en campañas Smart vía Google Ads API (v23)

**Fecha:** 2026-06-11 · **Conclusión:** no hay API confiable para negativos en Smart →
el agente devuelve `manual_required` y manda la receta por correo (Fase B1).

## Qué revisé

1. **`CampaignCriterionService` (negative keyword)** — `engine/ads_client.add_negative_keyword`
   ya documenta y RECHAZA Smart: `_NEGATIVE_KEYWORD_UNSUPPORTED_CHANNELS = {"SMART"}`
   (`engine/ads_client.py:747`). Smart **acepta** la mutación `campaign_criterion` negativa
   sin error, pero el matching algorithm **la ignora** (no-op silencioso). Registrar eso como
   "éxito" sería un falso positivo, por eso la función lo rechaza.

2. **`CampaignCriterion.keyword_theme` (`add_smart_campaign_theme`)** —
   `engine/ads_client.py:1039` usa `criterion.keyword_theme.free_form_keyword_theme`. Esto es
   un **theme POSITIVO** (targeting: amplía a quién se le muestra), NO un negativo. No existe un
   `negative=True` equivalente para keyword themes en v23. Usarlo para "bloquear" haría lo
   contrario de lo deseado (agregaría targeting).

3. **`SmartCampaignSettingService`** — gestiona settings de la Smart campaign (perfil de negocio,
   ad schedule, teléfono, landing), pero **no** expone un campo de "negative keyword theme" en v23.

4. **Doc de referencia:** Google Ads API — Smart Campaigns overview
   (`https://developers.google.com/google-ads/api/docs/smart-campaigns/overview`) y
   `CampaignCriterion` / `KeywordThemeConstant`. Confirman que los keyword themes de Smart son
   de targeting positivo; el control de negativos en Smart se hace **en la UI de Google Ads**.

## Decisión

- SEARCH (Delivery Search / Experiencia 2026): negativo **EXACT** vía `add_negative_keyword`.
- SMART (Local / Delivery): `negativos_apply.aplicar_en_campana` devuelve **`manual_required`**
  (cuando pasa la guarda de marca) — jamás una mutación equivocada. El correo de confirmación
  trae la receta: theme a pegar + ruta *Campaña → Palabras clave → Temas de palabras clave
  negativas → Agregar*. El log lo marca `pending_manual`.

## TODO — re-verificar en futuras versiones de la API

- [ ] Revisar en **v24+** si Google habilita negativos en Smart vía API: un flag `negative` en
      `keyword_theme`, un campo nuevo en `SmartCampaignSettingService`, o un recurso dedicado.
- [ ] Si se habilita: reemplazar el `manual_required` de `engine/negativos_apply.aplicar_en_campana`
      (rama SMART) por la mutación real, manteniendo la guarda de marca/categoría y el gating
      `DRY_RUN_NEGATIVOS`.
- [ ] Fuente a vigilar: release notes de la Google Ads API y la doc de `CampaignCriterion`.
