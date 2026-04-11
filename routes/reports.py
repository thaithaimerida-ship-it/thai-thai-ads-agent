"""
Routes de Reportes — /send-weekly-report.
"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["reports"])


@router.post("/send-weekly-report")
async def send_weekly_report_endpoint(dry_run: bool = False):
    """
    Genera el reporte ejecutivo semanal (Fase 5) y lo envía por email.
    Llamado automáticamente cada lunes por Cloud Scheduler.

    Bloque negocio: ventas netas (Ingresos_BD) + comensales (Cortes_de_Caja).
    Bloque agente:  actividad de los últimos 8 días desde autonomous_decisions.

    Query params:
      ?dry_run=true — retorna el HTML en la respuesta sin enviar correo.
    """
    try:
        from engine.email_reporter import send_weekly_report, build_html_report
        from engine.sheets_client import fetch_week_business_data, fetch_mtd_business_data
        from engine.weekly_supervisor import (
            query_week_activity,
            build_supervisor_data,
            get_next_best_action,
        )
        from engine.memory import get_memory_system as _get_mem

        # 0. Asegurar que la DB esté sincronizada desde GCS antes de consultar
        try:
            from engine.db_sync import download_from_gcs as _dl_db
            _dl_db()
        except Exception as _dl_err:
            print(f"[WEEKLY] db_sync download falló (no crítico): {_dl_err}")

        # 1. Expirar propuestas vencidas antes de armar el reporte
        try:
            _get_mem().sweep_expired_proposals()
        except Exception as _e:
            print(f"[WEEKLY] sweep_expired_proposals falló (no crítico): {_e}")

        # 2. Datos de negocio — Sheets
        week_data = fetch_week_business_data(weeks_ago=1)
        prev_week_data = fetch_week_business_data(weeks_ago=2)
        mtd_data = fetch_mtd_business_data()

        # 3. Actividad del agente — SQLite
        rows = query_week_activity(days=8)
        supervisor_data = build_supervisor_data(rows)
        next_action = get_next_best_action(supervisor_data)

        # 4. Métricas Google Ads — Bloque 3 del reporte
        _target_id_w = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")
        ads_data = None
        try:
            from engine.ads_client import (
                get_ads_client as _get_ads_client_b3,
                fetch_campaign_metrics_range as _fetch_metrics_b3,
            )
            _client_b3 = _get_ads_client_b3()
            _ws_str = week_data["week_start"].strftime("%Y-%m-%d")
            _we_str = week_data["week_end"].strftime("%Y-%m-%d")
            _campaign_rows = _fetch_metrics_b3(_client_b3, _target_id_w, _ws_str, _we_str)
            if _campaign_rows:
                _total_cost   = sum(r["cost_mxn"]   for r in _campaign_rows)
                _total_conv   = sum(r["conversions"] for r in _campaign_rows)
                _total_clicks = sum(r["clicks"]      for r in _campaign_rows)
                ads_data = {
                    "cost_mxn":    round(_total_cost, 2),
                    "conversions": round(_total_conv, 1),
                    "clicks":      _total_clicks,
                    "cpa_mxn":     round(_total_cost / _total_conv, 2) if _total_conv > 0 else None,
                }
                print(f"[WEEKLY] Ads B3: gasto={ads_data['cost_mxn']}, conv={ads_data['conversions']}, CPA={ads_data['cpa_mxn']}")
        except Exception as _ads_exc:
            print(f"[WEEKLY] Google Ads B3 no disponible (no crítico): {_ads_exc}")
            ads_data = None

        # 5. dry_run: devuelve HTML sin enviar correo
        if dry_run:
            html = build_html_report(week_data, prev_week_data, mtd_data, supervisor_data, next_action,
                                     ads_data=ads_data)
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html, status_code=200)

        # 6. Enviar correo
        result = send_weekly_report(week_data, prev_week_data, mtd_data, supervisor_data, next_action,
                                    ads_data=ads_data)

        return {
            "status": "success" if result.get("success") else "error",
            "email": result,
            "week": {
                "start": str(week_data.get("week_start", "")),
                "end": str(week_data.get("week_end", "")),
                "ventas_netas": week_data.get("ventas_netas", 0),
                "comensales": week_data.get("comensales", 0),
            },
            "agent_summary": {
                "total_actions": supervisor_data.get("total_relevant", 0),
                "counts": supervisor_data.get("counts", {}),
            },
        }

    except Exception as e:
        import traceback
        print(f"[WEEKLY] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

