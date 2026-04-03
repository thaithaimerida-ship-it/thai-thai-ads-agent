"""
Tests del clasificador de riesgo — 5 casos simulados con thresholds por tipo de campaña.
Ejecutar desde la raíz del proyecto:
    py -3.14 tests/test_risk_classifier.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.risk_classifier import (
    classify_action,
    get_campaign_type,
    get_campaign_thresholds,
    RISK_OBSERVE, RISK_EXECUTE, RISK_PROPOSE, RISK_BLOCK,
)

LEVEL_LABELS = {
    RISK_OBSERVE: "0 - OBSERVAR",
    RISK_EXECUTE: "1 - EJECUTAR",
    RISK_PROPOSE: "2 - PROPONER",
    RISK_BLOCK:   "3 - BLOQUEAR",
}

FINAL_ACTION_LABELS = {
    RISK_OBSERVE: "Registrar como 'observe'. Sin correo, sin cambio en Ads.",
    RISK_EXECUTE: "Registrar como 'dry_run_execute'. En prod: bloquear keyword en Ads.",
    RISK_PROPOSE: "Registrar como 'proposed'. Correo con botones de aprobacion.",
    RISK_BLOCK:   "Registrar como 'blocked'. Escalar. Sin ejecucion.",
}

TEST_CASES = [
    {
        "nombre": "Caso 1 - Desperdicio claro en Delivery ($120, 0 conv)",
        "action_type": "block_keyword",
        "keyword_data": {
            "text": "comida asiatica merida",
            "keyword": "comida asiatica merida",
            "campaign_id": "22839241090",
            "campaign_name": "Thai Merida - Delivery",
            "spend": 120.00,
            "conversions": 0,
            "impressions": 850,
        },
        "campaign_data": {
            "id": "22839241090",
            "name": "Thai Merida - Delivery",
            "days_active": 30,
            "learning_status": "",
        },
    },
    {
        "nombre": "Caso 2 - Gasto bajo en Reservaciones ($65, 0 conv, umbral=$90)",
        "action_type": "block_keyword",
        "keyword_data": {
            "text": "cena romantica merida",
            "keyword": "cena romantica merida",
            "campaign_id": "99999999",
            "campaign_name": "Thai Merida - Reservaciones",
            "spend": 65.00,
            "conversions": 0,
            "impressions": 200,
        },
        "campaign_data": {
            "id": "99999999",
            "name": "Thai Merida - Reservaciones",
            "days_active": 20,
            "learning_status": "",
        },
    },
    {
        "nombre": "Caso 3 - Keyword estrategica protegida ($250, 0 conv)",
        "action_type": "block_keyword",
        "keyword_data": {
            "text": "restaurante thai merida",
            "keyword": "restaurante thai merida",
            "campaign_id": "22612348265",
            "campaign_name": "Thai Merida - Local",
            "spend": 250.00,
            "conversions": 0,
            "impressions": 1200,
        },
        "campaign_data": {
            "id": "22612348265",
            "name": "Thai Merida - Local",
            "days_active": 45,
            "learning_status": "",
        },
    },
    {
        "nombre": "Caso 4 - Campana nueva en aprendizaje ($85, 0 conv, 8 dias activa)",
        "action_type": "block_keyword",
        "keyword_data": {
            "text": "reservar mesa merida",
            "keyword": "reservar mesa merida",
            "campaign_id": "99999999",
            "campaign_name": "Thai Merida - Reservaciones",
            "spend": 85.00,
            "conversions": 0,
            "impressions": 300,
        },
        "campaign_data": {
            "id": "99999999",
            "name": "Thai Merida - Reservaciones",
            "days_active": 8,
            "learning_status": "",
        },
    },
    {
        "nombre": "Caso 5 - CPA critico en Delivery ($310, 1 conv, limite=$80)",
        "action_type": "block_keyword",
        "keyword_data": {
            "text": "cena merida fin de semana",
            "keyword": "cena merida fin de semana",
            "campaign_id": "22839241090",
            "campaign_name": "Thai Merida - Delivery",
            "spend": 310.00,
            "conversions": 1,
            "impressions": 900,
        },
        "campaign_data": {
            "id": "22839241090",
            "name": "Thai Merida - Delivery",
            "days_active": 30,
            "learning_status": "",
        },
    },
]


def run_tests():
    print()
    print("=" * 70)
    print("CLASIFICADOR DE RIESGO - 5 CASOS CON THRESHOLDS POR CAMPANA")
    print("=" * 70)

    for case in TEST_CASES:
        c = classify_action(
            case["action_type"],
            case["keyword_data"],
            case["campaign_data"],
        )

        campaign_name = case["keyword_data"]["campaign_name"]
        campaign_id = case["keyword_data"]["campaign_id"]
        sp = case["keyword_data"]["spend"]
        cv = case["keyword_data"]["conversions"]
        cpa = round(sp / cv, 2) if cv > 0 else None

        campaign_type = get_campaign_type(campaign_name, campaign_id)
        thresholds = get_campaign_thresholds(campaign_name, campaign_id)

        print()
        print("-" * 70)
        print(f"  {case['nombre']}")
        print("-" * 70)
        print("  INPUT")
        print(f"    keyword        : '{case['keyword_data']['text']}'")
        print(f"    campana        : {campaign_name}")
        print(f"    tipo detectado : {campaign_type}")
        print(f"    gasto          : ${sp:.2f} MXN  (umbral tipo: ${thresholds['min_spend_to_block']:.0f})")
        print(f"    conversiones   : {cv}")
        if cpa:
            print(f"    CPA            : ${cpa:.2f}  (critico tipo: ${thresholds['cpa_critical']:.0f})")
        else:
            print(f"    CPA            : N/A (0 conversiones)")
        print(f"    impresiones    : {case['keyword_data']['impressions']}")
        print(f"    dias activa    : {case['campaign_data']['days_active']}")
        print()
        print("  CLASIFICACION")
        print(f"    risk_level       : {LEVEL_LABELS[c.risk_level]}")
        print(f"    urgency          : {c.urgency.upper()}")
        print(f"    auto_eligible    : {'SI' if c.can_auto_execute else 'NO'}")
        print(f"    requires_approval: {'SI' if c.requires_approval else 'NO'}")
        print(f"    protected        : {'SI' if c.protected else 'NO'}")
        print(f"    learning_phase   : {'SI' if c.learning_phase else 'NO'}")
        print(f"    block_reason     : {c.block_reason}")
        print()
        print("  ACCION FINAL (dry-run)")
        print(f"    {FINAL_ACTION_LABELS[c.risk_level]}")
        print()
        print("  JUSTIFICACION")
        print(f"    {c.reason}")

    print()
    print("=" * 70)
    print("  Fin. AUTO_EXECUTE_ENABLED=false (default seguro).")
    print("=" * 70)
    print()


if __name__ == "__main__":
    run_tests()
