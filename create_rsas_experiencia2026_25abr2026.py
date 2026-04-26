"""
QW9 - Crear 2 RSAs mejorados en Comida Autentica y Turistas (Ingles).
Los RSAs existentes se mantienen ENABLED. Google rota y aprende.
Solo crea, no modifica ni pausa nada existente.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from engine.ads_client import get_ads_client
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "4021070209"
CAMPAIGN_NAME = "Thai Mérida - Experiencia 2026"

REPORT_PATH = os.path.join(
    os.path.dirname(__file__),
    "reports",
    "create_rsas_experiencia2026_25abr2026.md",
)

# Configuracion de los 2 RSAs nuevos
NEW_RSAS = [
    {
        "ag_name": "Comida Auténtica",
        "path1": "Restaurante",
        "path2": "Thai-Merida",
        "headlines": [
            "Comida Tailandesa Auténtica",
            "Sabores de Tailandia",
            "Pad Thai Real en Mérida",
            "Curry Thai Auténtico",
            "Cocina Thai Tradicional",
            "Thai Food en Mérida",
            "El Mejor Thai de Yucatán",
            "Platillos Tailandeses Reales",
            "Menú Thai Completo",
            "Cocina Thai Artesanal",
            "Curries Hechos Desde Cero",
            "Thai Dumplings Caseros",
            "Reserva Tu Mesa Hoy",
            "Mérida Norte: Calle 30",
            "Sabor Thai en Mérida Centro",
        ],
        "descriptions": [
            "Pad Thai, curries y más platillos auténticos de Tailandia en Mérida.",
            "Ingredientes originales y recetas tradicionales tailandesas. ¡Visítanos!",
            "La cocina tailandesa más auténtica de Yucatán. Mar-Dom, 13 a 21 horas.",
            "Pad Thai, Thai Dumplings, Curry de Cacahuate. Cocina artesanal hecha desde cero.",
        ],
    },
    {
        "ag_name": "Turistas (Inglés)",
        "path1": "Thai-Restaurant",
        "path2": "Merida",
        "headlines": [
            "Thai Restaurant Merida",
            "Authentic Thai Food Merida",
            "Best Thai in Mérida",
            "Thai Thai Merida Mexico",
            "Real Thai Cuisine Yucatan",
            "Thai Dining in Merida",
            "Visit Thai Thai Merida",
            "Thai Food Near You Merida",
            "Dine Thai in Merida MX",
            "Handmade Thai Cuisine",
            "Authentic Pad Thai Mérida",
            "Fresh Curries Made Daily",
            "Book Your Thai Experience",
            "Modern Thai Atmosphere",
            "Try Our Butterfly Tea Latte",
        ],
        "descriptions": [
            "Authentic Thai cuisine in the heart of Mérida. Open Tue-Sun 1pm to 9pm.",
            "Discover real Thai flavors in Yucatán. Book your table at Thai Thai Mérida.",
            "Best Thai restaurant in Mérida, Mexico. Traditional recipes, great atmosphere.",
            "Pad Thai, Thai Dumplings, Peanut Curry. Handmade artisan cuisine in Mérida Norte.",
        ],
    },
]

FALLBACK_URL = "https://thaithaimerida.com/"


def q(ga, query):
    return list(ga.search(customer_id=CUSTOMER_ID, query=query))


def validate_assets(rsa_cfg):
    errors = []
    for i, h in enumerate(rsa_cfg["headlines"], 1):
        if len(h) > 30:
            errors.append(f"Headline {i} demasiado larga ({len(h)} chars > 30): '{h}'")
    for i, d in enumerate(rsa_cfg["descriptions"], 1):
        if len(d) > 90:
            errors.append(f"Description {i} demasiado larga ({len(d)} chars > 90): '{d}'")
    return errors


def run():
    run_ts = datetime.now()
    client = get_ads_client()
    ga = client.get_service("GoogleAdsService")
    aga_service = client.get_service("AdGroupAdService")

    # -- 1. Validacion de longitudes -----------------------------------------
    print("1. Validando longitudes de assets...")
    all_valid = True
    for cfg in NEW_RSAS:
        errs = validate_assets(cfg)
        if errs:
            for e in errs:
                print(f"   ERROR VALIDACION [{cfg['ag_name']}]: {e}")
            all_valid = False
        else:
            print(f"   OK: '{cfg['ag_name']}' — {len(cfg['headlines'])} headlines, {len(cfg['descriptions'])} descriptions")

    if not all_valid:
        print("   Deteniendo ejecucion por errores de validacion.")
        return

    # -- 2. Obtener ad_group IDs y Final URLs de RSAs existentes ------------
    print("\n2. Consultando ad groups y URLs existentes...")
    ag_names_gaql = ", ".join(f"'{cfg['ag_name']}'" for cfg in NEW_RSAS)
    rows_ag = q(ga, f"""
        SELECT
          ad_group.id,
          ad_group.name,
          ad_group.resource_name,
          ad_group_ad.ad.id,
          ad_group_ad.ad.final_urls,
          ad_group_ad.status,
          ad_group_ad.ad.type
        FROM ad_group_ad
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND ad_group.name IN ({ag_names_gaql})
          AND ad_group_ad.status = 'ENABLED'
          AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    """)

    ag_info = {}  # ag_name -> {id, resource_name, final_url, rsa_count, existing_ad_ids}
    for r in rows_ag:
        ag_name = r.ad_group.name
        if ag_name not in ag_info:
            ag_info[ag_name] = {
                "id": str(r.ad_group.id),
                "resource_name": r.ad_group.resource_name,
                "final_url": FALLBACK_URL,
                "rsa_count": 0,
                "existing_ad_ids": [],
            }
        ag_info[ag_name]["rsa_count"] += 1
        ag_info[ag_name]["existing_ad_ids"].append(str(r.ad_group_ad.ad.id))
        if r.ad_group_ad.ad.final_urls:
            ag_info[ag_name]["final_url"] = r.ad_group_ad.ad.final_urls[0]

    for ag_name, info in ag_info.items():
        print(f"   '{ag_name}' | ID: {info['id']} | RSAs ENABLED: {info['rsa_count']} | URL: {info['final_url']}")
        if info["rsa_count"] >= 3:
            print(f"   ADVERTENCIA: ya tiene {info['rsa_count']} RSAs — Google permite max 3 por ad group")

    # -- 3. Construir operaciones --------------------------------------------
    print("\n3. Construyendo operaciones de creacion...")
    ops = []
    op_meta = []  # (ag_name, cfg)

    for cfg in NEW_RSAS:
        ag_name = cfg["ag_name"]
        if ag_name not in ag_info:
            print(f"   ERROR: ad group '{ag_name}' no encontrado en la cuenta.")
            continue

        info = ag_info[ag_name]
        op = client.get_type("AdGroupAdOperation")
        aga = op.create
        aga.ad_group = info["resource_name"]
        aga.status = client.enums.AdGroupAdStatusEnum.ENABLED

        ad = aga.ad
        ad.final_urls.append(info["final_url"])

        rsa = ad.responsive_search_ad
        rsa.path1 = cfg["path1"]
        rsa.path2 = cfg["path2"]

        for text in cfg["headlines"]:
            asset = client.get_type("AdTextAsset")
            asset.text = text
            # sin pinned_field — Google rota libremente
            rsa.headlines.append(asset)

        for text in cfg["descriptions"]:
            asset = client.get_type("AdTextAsset")
            asset.text = text
            rsa.descriptions.append(asset)

        ops.append(op)
        op_meta.append((ag_name, cfg, info))
        print(f"   + '{ag_name}': {len(cfg['headlines'])} headlines, {len(cfg['descriptions'])} desc, path={cfg['path1']}/{cfg['path2']}")

    if not ops:
        print("   No hay operaciones que ejecutar.")
        return

    # -- 4. Ejecutar mutacion ------------------------------------------------
    print(f"\n4. Ejecutando mutate_ad_group_ads ({len(ops)} operaciones)...")
    results = []

    try:
        request = client.get_type("MutateAdGroupAdsRequest")
        request.customer_id = CUSTOMER_ID
        request.partial_failure = True
        for op in ops:
            request.operations.append(op)

        resp = aga_service.mutate_ad_group_ads(request=request)

        # Parsear errores parciales
        partial_errors = {}
        if resp.partial_failure_error and resp.partial_failure_error.details:
            try:
                for detail in resp.partial_failure_error.details:
                    failure = client.get_type("GoogleAdsFailure")
                    detail_msg = type(failure).FromString(detail.value)
                    for err in detail_msg.errors:
                        if err.location.field_path_elements:
                            idx = err.location.field_path_elements[0].index
                            partial_errors[idx] = err.message
            except Exception:
                pass

        for i, (ag_name, cfg, info) in enumerate(op_meta):
            if i in partial_errors:
                err_msg = partial_errors[i]
                print(f"   ERROR [{ag_name}]: {err_msg}")
                results.append({"ag_name": ag_name, "cfg": cfg, "info": info,
                                 "status": "ERROR", "new_ad_id": None, "error": err_msg})
            else:
                new_resource = resp.results[i].resource_name if i < len(resp.results) else "—"
                new_ad_id = new_resource.split("~")[-1] if "~" in new_resource else "—"
                print(f"   OK [{ag_name}]: nuevo Ad ID = {new_ad_id}")
                results.append({"ag_name": ag_name, "cfg": cfg, "info": info,
                                 "status": "OK", "new_ad_id": new_ad_id, "error": None})

    except GoogleAdsException as ex:
        err_msgs = [f"{e.error_code}: {e.message}" for e in ex.failure.errors]
        err_str = "; ".join(err_msgs)
        print(f"   GoogleAdsException: {err_str}")
        for ag_name, cfg, info in op_meta:
            results.append({"ag_name": ag_name, "cfg": cfg, "info": info,
                             "status": "ERROR", "new_ad_id": None, "error": err_str})
    except Exception as ex:
        err_str = str(ex)
        print(f"   Error inesperado: {err_str}")
        for ag_name, cfg, info in op_meta:
            results.append({"ag_name": ag_name, "cfg": cfg, "info": info,
                             "status": "ERROR", "new_ad_id": None, "error": err_str})

    # -- 5. Verificacion post-mutacion ---------------------------------------
    print("\n5. Verificacion post-mutacion...")
    rows_after = q(ga, f"""
        SELECT
          ad_group.name,
          ad_group_ad.ad.id,
          ad_group_ad.ad.responsive_search_ad.path1,
          ad_group_ad.ad.responsive_search_ad.path2,
          ad_group_ad.ad_strength,
          ad_group_ad.status
        FROM ad_group_ad
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND ad_group.name IN ({ag_names_gaql})
          AND ad_group_ad.status = 'ENABLED'
          AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    """)

    after_state = {}
    for r in rows_after:
        ag_name = r.ad_group.name
        if ag_name not in after_state:
            after_state[ag_name] = []
        after_state[ag_name].append({
            "ad_id": str(r.ad_group_ad.ad.id),
            "path1": r.ad_group_ad.ad.responsive_search_ad.path1,
            "path2": r.ad_group_ad.ad.responsive_search_ad.path2,
            "strength": r.ad_group_ad.ad_strength.name,
        })
        print(f"   '{ag_name}' | Ad {r.ad_group_ad.ad.id} | path={r.ad_group_ad.ad.responsive_search_ad.path1}/{r.ad_group_ad.ad.responsive_search_ad.path2} | strength={r.ad_group_ad.ad_strength.name}")

    ok = sum(1 for r in results if r["status"] == "OK")
    err = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\n{'='*60}")
    print(f"RESUMEN: {ok} RSAs creados | {err} errores")
    print(f"{'='*60}\n")

    generate_report(run_ts, results, after_state)
    print(f"Reporte guardado: {REPORT_PATH}")


def generate_report(ts, results, after_state):
    lines = []
    lines.append("# QW9: Creacion RSAs Mejorados — Thai Merida Experiencia 2026")
    lines.append("")
    lines.append(f"**Fecha/hora:** {ts.strftime('%d de %B de %Y, %H:%M:%S')}  ")
    lines.append(f"**Cuenta:** 4021070209  ")
    lines.append(f"**Campaña:** Thai Merida - Experiencia 2026  ")
    lines.append(f"**Operacion:** `AdGroupAdService.mutate_ad_group_ads` — solo CREATE  ")
    lines.append(f"**RSAs existentes:** mantenidos ENABLED sin modificacion  ")
    lines.append("")

    ok_count = sum(1 for r in results if r["status"] == "OK")
    err_count = sum(1 for r in results if r["status"] == "ERROR")
    estado = "EXITOSO" if err_count == 0 else f"PARCIAL — {err_count} errores"
    lines.append(f"**Estado:** {estado}  ")
    lines.append(f"**RSAs creados:** {ok_count} de {len(results)}  ")
    lines.append("")

    for res in results:
        ag = res["ag_name"]
        cfg = res["cfg"]
        info = res["info"]
        lines.append(f"## Ad Group: {ag}")
        lines.append("")

        # Estado
        lines.append("### Resultado")
        lines.append("")
        lines.append("| Campo | Valor |")
        lines.append("|-------|-------|")
        lines.append(f"| Ad group ID | {info['id']} |")
        for old_id in info["existing_ad_ids"]:
            lines.append(f"| Ad ID (existente, mantenido) | {old_id} |")
        if res["status"] == "OK":
            lines.append(f"| Ad ID (nuevo creado) | {res['new_ad_id']} |")
            lines.append(f"| Estado | CREADO EXITOSAMENTE |")
        else:
            lines.append(f"| Estado | ERROR: {res['error']} |")
        lines.append(f"| Final URL | {info['final_url']} |")
        lines.append(f"| Path | {cfg['path1']}/{cfg['path2']} |")
        lines.append("")

        # Headlines
        lines.append("### Headlines del RSA Nuevo (15)")
        lines.append("")
        lines.append("| # | Texto | Chars |")
        lines.append("|---|-------|:-----:|")
        for i, h in enumerate(cfg["headlines"], 1):
            lines.append(f"| {i} | {h} | {len(h)} |")
        lines.append("")

        # Descriptions
        lines.append("### Descriptions del RSA Nuevo (4)")
        lines.append("")
        lines.append("| # | Texto | Chars |")
        lines.append("|---|-------|:-----:|")
        for i, d in enumerate(cfg["descriptions"], 1):
            lines.append(f"| {i} | {d} | {len(d)} |")
        lines.append("")

        # Estado post
        ag_after = after_state.get(ag, [])
        if ag_after:
            lines.append("### Confirmacion Post-Mutacion")
            lines.append("")
            lines.append("| Ad ID | Path | Ad Strength |")
            lines.append("|-------|------|:-----------:|")
            for a in ag_after:
                path = f"{a['path1']}/{a['path2']}" if a["path1"] else "(sin path)"
                lines.append(f"| {a['ad_id']} | {path} | {a['strength']} |")
            lines.append("")

        if res["status"] == "ERROR":
            lines.append(f"> **Error:** `{res['error']}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("## Proximos Pasos")
    lines.append("")
    lines.append("### Cronograma de evaluacion")
    lines.append("")
    lines.append("| Fecha | Accion |")
    lines.append("|-------|--------|")
    lines.append("| ~10 may 2026 (14 dias) | Revisar Ad Strength de los RSAs nuevos en Google Ads UI |")
    lines.append("| ~25 may 2026 (30 dias) | Re-correr `_diag_rsas_experiencia2026.py` para ver performance labels |")
    lines.append("| ~25 may 2026 | Si nuevo RSA muestra GOOD o EXCELLENT, evaluar pausar el viejo |")
    lines.append("| ~25 jun 2026 | Re-evaluar ad schedule con mayor volumen de conversiones |")
    lines.append("")
    lines.append("### Senales para pausar el RSA viejo")
    lines.append("")
    lines.append("- RSA nuevo tiene Ad Strength GOOD o EXCELLENT")
    lines.append("- RSA nuevo tiene CTR >= RSA viejo en el mismo periodo")
    lines.append("- Al menos 30 dias de datos comparativos")
    lines.append("")
    lines.append("### Display paths agregados")
    lines.append("")
    lines.append("Los RSAs existentes no tenian display path configurado.")
    lines.append("Los nuevos RSAs incluyen paths especificos:")
    lines.append("- Comida Autentica: `/Restaurante/Thai-Merida`")
    lines.append("- Turistas (Ingles): `/Thai-Restaurant/Merida`")
    lines.append("")
    lines.append("Esto mejora el CTR al hacer la URL visible mas relevante para la busqueda.")
    lines.append("")
    lines.append("---")
    lines.append("_Solo se crearon nuevos RSAs. No se modifico ni pauso ningun RSA existente._")
    lines.append("_No se toco bidding, presupuesto, schedule, geo, audiencias ni otras campanas._")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run()
