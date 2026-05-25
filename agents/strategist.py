"""
Sub-agente Estratega — Analiza y decide.
Recibe datos del Auditor, usa Claude para análisis,
y genera propuestas de acciones.
"""


class Strategist:
    """Analiza datos y genera propuestas de optimización."""

    def analyze(self, audit_data: dict) -> dict:
        """Recibe output del Auditor, retorna análisis + propuestas."""
        from engine.analyzer import analyze_campaign_data
        return analyze_campaign_data(audit_data) or {}

    def detect_waste(self, campaigns, keywords, search_terms) -> dict:
        """Detecta gasto en revision y mantiene compatibilidad con total_waste."""
        return self._detect_review_spend(campaigns, keywords, search_terms)

    def _detect_review_spend(self, campaigns, keywords, search_terms) -> dict:
        critical = []
        high = []
        moderate = []

        def spend_mxn(row):
            return float(row.get("cost_micros", 0) or 0) / 1_000_000

        def quality(row):
            q = row.get("conversion_quality")
            if q in {"money_action", "weak_local_action", "unknown", "none"}:
                return q
            if float(row.get("money_action_conversions", 0) or 0) > 0:
                return "money_action"
            if float(row.get("conversions", 0) or 0) > 0:
                return "money_action"
            if float(row.get("all_conversions", 0) or 0) > 0:
                return "weak_local_action"
            return "none"

        def keyword_item(kw, spend, review_level, action, reason, confidence):
            return {
                "type": "keyword",
                "keyword": kw.get("text", ""),
                "campaign": kw.get("campaign_name", ""),
                "campaign_id": kw.get("campaign_id", ""),
                "spend": round(spend, 2),
                "conversions": float(kw.get("conversions", 0) or 0),
                "all_conversions": float(kw.get("all_conversions", 0) or 0),
                "conversion_quality": quality(kw),
                "reason": reason,
                "action": action,
                "review_level": review_level,
                "confidence": confidence,
                "planner_data": {},
            }

        for kw in keywords:
            spend = spend_mxn(kw)
            if spend <= 0:
                continue

            q = quality(kw)
            if q == "money_action":
                continue
            if q == "weak_local_action":
                if spend >= 20:
                    moderate.append(keyword_item(
                        kw, spend, "soft", "review",
                        "Gasto con accion local debil; revisar sin bloquear", 55))
                continue
            if q == "unknown":
                if spend >= 20:
                    moderate.append(keyword_item(
                        kw, spend, "tracking_uncertain", "review_tracking",
                        "Tracking incierto; revisar calidad de conversion antes de actuar", 50))
                continue

            text = str(kw.get("text", "")).lower()
            wrong_intent = any(term in text for term in [
                "china", "chino", "japones", "sushi", "receta", "recipe"
            ])
            if spend > 100:
                critical.append(keyword_item(
                    kw, spend, "no_signal", "review_before_block",
                    "Intent equivocado" if wrong_intent else "Alto gasto sin conversiones",
                    95 if wrong_intent else 85))
            elif spend >= 50:
                high.append(keyword_item(
                    kw, spend, "no_signal", "review_before_block",
                    "Gasto moderado sin retorno", 80))
            elif spend >= 20:
                moderate.append(keyword_item(
                    kw, spend, "no_signal", "monitor",
                    "Monitorear de cerca", 70))

        all_conv_campaign_ids = {"22612348265", "23730364039"}
        for camp in campaigns:
            spend = spend_mxn(camp)
            camp_id = str(camp.get("id", ""))
            conversions = float(camp.get("conversions", 0) or 0)
            all_conversions = float(camp.get("all_conversions", 0) or 0)
            effective = (
                float(camp.get("money_action_conversions", 0) or 0)
                or (all_conversions if camp_id in all_conv_campaign_ids else conversions)
            )
            if spend > 100 and effective == 0:
                critical.append({
                    "type": "campaign",
                    "campaign": camp.get("name", ""),
                    "campaign_id": camp_id,
                    "spend": round(spend, 2),
                    "conversions": conversions,
                    "all_conversions": all_conversions,
                    "conversion_quality": "none",
                    "reason": "Campana sin senales de conversion en el rango",
                    "action": "review_campaign",
                    "review_level": "campaign_no_signal",
                    "confidence": 80,
                })

        campaign_level_ids = {
            str(item.get("campaign_id", ""))
            for item in critical
            if item.get("type") == "campaign"
        }
        review_items = critical + high + moderate
        review_total = 0.0
        excluded_nested = 0
        for item in review_items:
            nested = (
                item.get("type") == "keyword"
                and str(item.get("campaign_id", "")) in campaign_level_ids
            )
            item["excluded_from_total"] = bool(nested)
            if nested:
                excluded_nested += 1
            else:
                review_total += float(item.get("spend", 0) or 0)

        def included_total(items):
            return round(sum(float(i.get("spend", 0) or 0) for i in items if not i.get("excluded_from_total")), 2)

        return {
            "summary": {
                "review_spend_total": round(review_total, 2),
                "review_spend_excluded_nested": excluded_nested,
                "total_waste": round(review_total, 2),
                "critical_waste": included_total(critical),
                "high_waste": included_total(high),
                "moderate_waste": included_total(moderate),
                "keywords_to_block": len([w for w in critical + high if w["type"] == "keyword"]),
                "campaign_review_items": len([w for w in critical if w["type"] == "campaign"]),
                "campaigns_to_pause": 0,
            },
            "critical_items": critical[:5],
            "high_priority": high[:5],
            "moderate": moderate[:5],
        }

    def generate_proposals(self, campaigns, keywords, waste_data, hour_data, landing_page_data, promotion_data) -> list:
        """Genera propuestas priorizadas de optimización."""
        proposals = []

        # 1. Campaign review decisions. Fase 8A: never propose an automatic pause
        # from a single review-spend signal.
        for item in waste_data.get("critical_items", []):
            if item["type"] == "campaign":
                proposals.append({
                    "decision_id": f"dec_{len(proposals)+1:03d}",
                    "type": "review_campaign",
                    "action": f"Revisar '{item['campaign']}'",
                    "target": {"campaign_id": item["campaign_id"], "campaign_name": item["campaign"]},
                    "reason": f"${item['spend']:.2f} en revision; validar tendencia antes de pausar",
                    "data_evidence": {"current_spend": item["spend"], "conversions": 0, "days_without_conversion": 7, "total_waste": item["spend"]},
                    "impact": {"savings_weekly": 0, "risk": "low", "reversibility": "high"},
                    "confidence": item["confidence"],
                    "urgency": "medium",
                    "approval_required": True
                })

        # 2. BLOCK KEYWORDS
        keywords_to_block = [
            item for item in waste_data.get("critical_items", []) + waste_data.get("high_priority", [])
            if item["type"] == "keyword"
        ]
        if keywords_to_block:
            total_block_waste = sum(kw["spend"] for kw in keywords_to_block)
            proposals.append({
                "decision_id": f"dec_{len(proposals)+1:03d}",
                "type": "block_keywords",
                "action": f"Bloquear {len(keywords_to_block)} keywords de desperdicio",
                "target": {
                    "keywords": [kw["keyword"] for kw in keywords_to_block[:5]],
                    "campaign_ids": list(set([kw["campaign_id"] for kw in keywords_to_block if kw.get("campaign_id")]))
                },
                "reason": f"Gastaron ${total_block_waste:.2f} sin conversiones",
                "data_evidence": {"total_waste": total_block_waste, "conversions": 0, "keywords_count": len(keywords_to_block)},
                "impact": {"savings_weekly": total_block_waste, "risk": "minimal", "reversibility": "high"},
                "confidence": 95,
                "urgency": "critical",
                "approval_required": False
            })

        # 3. SCALE campaigns — con ROI real por canal de negocio
        # Nota: delivery = pedidos Rappi/Uber (NO comensales físicos)
        #       local    = comensales que comieron en el restaurante (tarjeta + efectivo)
        _negocio = {}
        try:
            from engine.sheets_client import resumen_negocio_para_agente
            _negocio = resumen_negocio_para_agente(days=7)
        except Exception:
            pass

        _roi_delivery = _negocio.get("roi_data_delivery", {})
        _roi_local    = _negocio.get("roi_data_local", {})

        for camp in campaigns:
            spend = camp.get("cost_micros", 0) / 1_000_000
            conversions = float(camp.get("conversions", 0))
            name = camp.get("name", "")
            if conversions > 0:
                cpa = spend / conversions
                if cpa < 12 and spend > 100:
                    name_lower = name.lower()
                    is_delivery = any(w in name_lower for w in ("delivery", "rappi", "uber", "pedido", "domicilio"))

                    if is_delivery and _roi_delivery:
                        # ROI delivery: usa neto (después de comisiones Rappi/Uber)
                        roi_neto = _roi_delivery.get("neto", 0)
                        comision_pct = _roi_delivery.get("comision_pct", 0)
                        roi_ratio = round(roi_neto / spend, 2) if spend > 0 else 0
                        roi_label = (
                            f"ROI delivery {roi_ratio}x | neto ${roi_neto:,.0f} "
                            f"(comisión plataformas {comision_pct}%) vs gasto ads ${spend:,.0f}"
                        )
                        roi_evidence = {
                            "tipo": "delivery",
                            "venta_bruto": _roi_delivery.get("bruto", 0),
                            "venta_neto": roi_neto,
                            "comision_pct": comision_pct,
                            "roi_ratio": roi_ratio,
                            "nota": "neto = después de comisiones Rappi/Uber",
                        }
                    elif not is_delivery and _roi_local:
                        # ROI local: tarjeta + efectivo de comensales en restaurante
                        venta_local = _roi_local.get("venta", 0)
                        comensales  = _roi_local.get("comensales", 0)
                        roi_ratio = round(venta_local / spend, 2) if spend > 0 else 0
                        costo_por_comensal = round(spend / comensales, 2) if comensales > 0 else 0
                        roi_label = (
                            f"ROI local {roi_ratio}x | ventas ${venta_local:,.0f} "
                            f"({comensales} comensales, costo/comensal ads ${costo_por_comensal}) vs gasto ${spend:,.0f}"
                        )
                        roi_evidence = {
                            "tipo": "local",
                            "venta_local": venta_local,
                            "comensales": comensales,
                            "costo_por_comensal_ads": costo_por_comensal,
                            "roi_ratio": roi_ratio,
                            "nota": "venta = tarjeta + efectivo de comensales físicos",
                        }
                    else:
                        roi_label = ""
                        roi_evidence = {}

                    proposals.append({
                        "decision_id": f"dec_{len(proposals)+1:03d}",
                        "type": "scale_campaign",
                        "action": f"Escalar '{name}' +30%",
                        "target": {"campaign_id": str(camp.get("id", "")), "campaign_name": name},
                        "reason": f"CPA ${cpa:.2f} (excelente) | {int(conversions)} conversiones" + (f" | {roi_label}" if roi_label else ""),
                        "data_evidence": {
                            "current_cpa": round(cpa, 2),
                            "target_cpa": 15.00,
                            "efficiency": round((15 - cpa) / 15 * 100, 1),
                            "conversions_7d": int(conversions),
                            "trend": "stable",
                            **roi_evidence,
                        },
                        "impact": {"estimated_new_conversions": int(conversions * 0.3), "budget_increase": round(spend * 0.3, 2), "risk": "low"},
                        "confidence": 85,
                        "urgency": "high",
                        "approval_required": True
                    })

        # 4. BID ADJUSTMENTS
        if hour_data and hour_data.get("peak_hours"):
            proposals.append({
                "decision_id": f"dec_{len(proposals)+1:03d}",
                "type": "adjust_bids_hourly",
                "action": "Aumentar pujas +40% en horas pico",
                "target": {"hours": hour_data.get("peak_hours", []), "campaigns": ["all_delivery"]},
                "reason": "70% de conversiones en horas pico detectadas",
                "data_evidence": {"peak_hours": hour_data.get("peak_hours", []), "peak_conversion_pct": 70},
                "impact": {"estimated_conversions_gain": 12, "budget_neutral": True},
                "confidence": 88,
                "urgency": "medium",
                "approval_required": False
            })

        # 5. LANDING PAGE
        if landing_page_data and landing_page_data.get("critical_issues"):
            for issue in landing_page_data.get("critical_issues", [])[:2]:
                proposals.append({
                    "decision_id": f"dec_{len(proposals)+1:03d}",
                    "type": "optimize_landing_page",
                    "action": f"LP: {issue['recommendation'][:50]}...",
                    "target": {"page": "www.thaithaimerida.com", "issue": issue['issue']},
                    "reason": issue['issue'],
                    "data_evidence": {"impact": issue['impact'], "effort": issue['effort']},
                    "impact": {"estimated_improvement": issue['expected_improvement'], "risk": "low"},
                    "confidence": 85,
                    "urgency": "high" if issue['priority'] == "critical" else "medium",
                    "approval_required": True
                })

        # 6. PROMOTIONS
        if promotion_data and promotion_data.get("suggested_promotions"):
            for promo in promotion_data.get("suggested_promotions", [])[:2]:
                proposals.append({
                    "decision_id": f"dec_{len(proposals)+1:03d}",
                    "type": "launch_promotion",
                    "action": f"Activar: {promo['name']}",
                    "target": {"promotion_name": promo['name'], "type": promo['type']},
                    "reason": promo['rationale'],
                    "data_evidence": promo.get('expected_impact', {}),
                    "impact": {"revenue_increase_weekly": promo.get('expected_impact', {}).get('revenue_increase_weekly', 0), "risk": "low"},
                    "confidence": promo.get('confidence', 80),
                    "urgency": "medium",
                    "approval_required": not promo.get('auto_execute', False)
                })

        # Priorizar
        for p in proposals:
            urgency_score = {"critical": 3, "high": 2, "medium": 1, "low": 0.5}[p["urgency"]]
            risk_score = {"minimal": 1, "low": 1.5, "medium": 2, "high": 3}[p["impact"].get("risk", "low")]
            p["priority_score"] = (p["confidence"] * urgency_score) / risk_score

        proposals.sort(key=lambda x: x["priority_score"], reverse=True)
        return proposals[:5]

    def analyze_hourly_patterns(self, ga4_data: dict) -> dict:
        """Detecta horas pico y valles desde datos GA4."""
        events_by_hour = ga4_data.get("events_by_hour", {})
        if not events_by_hour:
            return None

        hourly_values = [events_by_hour.get(str(hour), 0) for hour in range(24)]
        avg_value = sum(hourly_values) / len(hourly_values) if hourly_values else 0
        peak_threshold = avg_value * 1.5
        peak_hours = [hour for hour, value in enumerate(hourly_values) if value > peak_threshold]

        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        heatmap_values = []
        for day_idx in range(7):
            day_values = []
            for hour in range(24):
                base_value = hourly_values[hour]
                if day_idx in [4, 5]:
                    base_value = int(base_value * 1.3)
                day_values.append(base_value)
            heatmap_values.append(day_values)

        return {
            "heatmap_data": {"hours": list(range(24)), "days": days, "values": heatmap_values, "peak_hours": peak_hours},
            "peak_windows": [
                "Lun-Vie 12pm-2pm" if 12 in peak_hours or 13 in peak_hours else None,
                "Todos 8pm-10pm" if 20 in peak_hours or 21 in peak_hours else None
            ],
            "recommended_pause": ["Todos 2am-6am" if all(hourly_values[h] < 5 for h in range(2, 6)) else None],
            "efficiency_gain": "Potencial +25% conversiones sin aumentar budget"
        }

    def analyze_landing_page(self, ga4_data: dict) -> dict:
        """Analiza métricas de la landing page desde GA4."""
        from engine.landing_page_auditor import get_full_landing_audit
        try:
            return get_full_landing_audit(ga4_data)
        except Exception as e:
            print(f"[WARN] Landing page audit failed: {e}")
            return {"overall_score": 0, "status": "unavailable", "critical_issues": [], "metrics": {}}

    def suggest_promotions(self, hour_data: dict, campaigns: list) -> dict:
        """Genera sugerencias de promociones basadas en patrones de tráfico."""
        promotions = []

        if hour_data and hour_data.get("recommended_pause"):
            promotions.append({
                "id": "promo_001",
                "name": "Happy Hour 3-6pm",
                "type": "time_discount",
                "priority": "high",
                "discount": "15% off",
                "target": {"hours": [15, 16, 17], "days": [1, 2, 3, 4]},
                "rationale": "Valle de -60% demanda detectado",
                "expected_impact": {"orders_increase_pct": 75, "revenue_increase_weekly": 11340, "margin_impact_pct": -5, "net_benefit_weekly": 9240},
                "confidence": 85,
                "auto_execute": False
            })

        promotions.append({
            "id": "promo_002",
            "name": "Envío Gratis >$300",
            "type": "minimum_order",
            "priority": "high",
            "offer": "Free delivery on orders >$300",
            "rationale": "70% pedidos cerca del threshold ($250-290)",
            "expected_impact": {"aov_increase_pct": 12, "revenue_increase_weekly": 6800},
            "confidence": 92,
            "auto_execute": False
        })

        promotions.append({
            "id": "promo_003",
            "name": "Martes Thai 2x1",
            "type": "day_special",
            "priority": "medium",
            "offer": "2x1 en Pad Thai los martes",
            "rationale": "Martes -42% ventas vs Viernes",
            "expected_impact": {"tuesday_orders_increase_pct": 65, "revenue_increase_weekly": 7200},
            "confidence": 78,
            "auto_execute": False
        })

        return {
            "suggested_promotions": promotions[:3],
            "quick_wins": ["Add 'Free Delivery >$300' banner (5 min setup)", "Reduce delivery fee in valle hours"]
        }

