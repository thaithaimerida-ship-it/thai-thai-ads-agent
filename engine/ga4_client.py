"""
GA4 API Client - Lectura de eventos de conversión
Conecta con Google Analytics 4 para obtener datos reales de la landing page
"""

import os
from datetime import datetime, timedelta
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric
)
def get_ga4_client():
    """Inicializa cliente de GA4 usando Service Account."""
    from engine.credentials import get_credentials
    creds = get_credentials(scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    if creds is None:
        raise RuntimeError(
            "Credenciales GA4 no disponibles. "
            "Configura GOOGLE_CREDENTIALS_JSON (env var) o GA4_CREDENTIALS_PATH (archivo)."
        )
    return BetaAnalyticsDataClient(credentials=creds)

def fetch_ga4_events(property_id: str = None, days: int = 7) -> dict:
    """
    Obtiene eventos de conversión de los últimos N días.
    
    Args:
        property_id: ID de la propiedad GA4 (ej: "528379219")
        days: Días hacia atrás para consultar (default: 7)
    
    Returns:
        dict con conteo de eventos por tipo
    """
    if not property_id:
        property_id = os.getenv("GA4_PROPERTY_ID")
    
    if not property_id:
        raise ValueError("GA4_PROPERTY_ID no configurado en .env")
    
    client = get_ga4_client()
    
    # Rango de fechas
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Configurar request
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )],
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")]
    )
    
    # Ejecutar query
    try:
        response = client.run_report(request)
    except Exception as e:
        print(f"[ERROR] Falló consulta a GA4: {e}")
        return {"error": str(e)}
    
    # Parsear resultados
    events = {}
    
    for row in response.rows:
        event_name = row.dimension_values[0].value
        event_count = int(row.metric_values[0].value)
        events[event_name] = event_count
    
    return events

def fetch_ga4_events_detailed(property_id: str = None, days: int = 7) -> dict:
    """
    Versión detallada: incluye dimensiones adicionales (página, dispositivo, etc.)
    
    Returns:
        dict con eventos segmentados por dimensión
    """
    if not property_id:
        property_id = os.getenv("GA4_PROPERTY_ID")
    
    client = get_ga4_client()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )],
        dimensions=[
            Dimension(name="eventName"),
            Dimension(name="deviceCategory"),
            Dimension(name="hour")  # Hora del día (0-23)
        ],
        metrics=[
            Metric(name="eventCount"),
            Metric(name="totalUsers"),
            Metric(name="sessions")
        ]
    )

    try:
        response = client.run_report(request)
    except Exception as e:
        print(f"[ERROR] Falló consulta detallada a GA4: {e}")
        return {"error": str(e)}

    # Estructura de datos más rica
    detailed_data = {
        "events_by_name": {},
        "events_by_device": {"desktop": 0, "mobile": 0, "tablet": 0},
        "events_by_hour": {str(h): 0 for h in range(24)},
        "total_sessions": 0,
        "conversion_funnel": {}
    }
    
    for row in response.rows:
        event_name = row.dimension_values[0].value
        device = row.dimension_values[1].value
        hour = row.dimension_values[2].value
        event_count = int(row.metric_values[0].value)
        sessions_count = int(row.metric_values[2].value) if len(row.metric_values) > 2 else 0

        # Acumular por nombre
        if event_name not in detailed_data["events_by_name"]:
            detailed_data["events_by_name"][event_name] = 0
        detailed_data["events_by_name"][event_name] += event_count

        # Acumular por dispositivo
        if device in detailed_data["events_by_device"]:
            detailed_data["events_by_device"][device] += event_count

        # Acumular por hora
        if hour in detailed_data["events_by_hour"]:
            detailed_data["events_by_hour"][hour] += event_count

        # Acumular sesiones totales
        detailed_data["total_sessions"] += sessions_count
    
    # Calcular embudo de conversión
    events_by_name = detailed_data["events_by_name"]
    
    page_views = events_by_name.get("page_view", 0)
    click_pedir = events_by_name.get("click_pedir_online", 0)
    click_reservar = events_by_name.get("click_reservar", 0)
    reserva_completada = events_by_name.get("reserva_completada", 0)
    
    detailed_data["conversion_funnel"] = {
        "page_view": page_views,
        "click_pedir_online": click_pedir,
        "click_reservar": click_reservar,
        "reserva_completada": reserva_completada,
        "abandono_modal": click_reservar - reserva_completada if click_reservar > 0 else 0,
        "conversion_rate_pedir": round((click_pedir / page_views * 100), 2) if page_views > 0 else 0,
        "conversion_rate_reservar": round((reserva_completada / click_reservar * 100), 2) if click_reservar > 0 else 0
    }
    
    return detailed_data

def get_peak_hours(property_id: str = None, days: int = 7) -> list:
    """
    Identifica las 3 horas con más conversiones.
    Útil para ajustar presupuestos por horario.
    
    Returns:
        list de tuplas (hora, conversiones) ordenadas por conversiones desc
    """
    detailed = fetch_ga4_events_detailed(property_id, days)
    
    if "error" in detailed:
        return []
    
    events_by_hour = detailed["events_by_hour"]
    sorted_hours = sorted(events_by_hour.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_hours[:3]

if __name__ == "__main__":
    """
    Script de prueba - ejecuta con:
    python -m engine.ga4_client
    """
    print("\n🔍 PROBANDO CONEXIÓN A GA4...\n")
    
    # Test 1: Eventos básicos
    print("📊 Obteniendo eventos (últimos 7 días)...")
    events = fetch_ga4_events(days=7)
    
    if "error" in events:
        print(f"❌ Error: {events['error']}")
    else:
        print("✅ Eventos obtenidos:")
        for event_name, count in events.items():
            print(f"   {event_name}: {count}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Datos detallados
    print("📊 Obteniendo datos detallados...")
    detailed = fetch_ga4_events_detailed(days=7)
    
    if "error" in detailed:
        print(f"❌ Error: {detailed['error']}")
    else:
        print("✅ Embudo de conversión:")
        funnel = detailed["conversion_funnel"]
        print(f"   Page Views: {funnel['page_view']}")
        print(f"   Click Pedir Online: {funnel['click_pedir_online']}")
        print(f"   Click Reservar: {funnel['click_reservar']}")
        print(f"   Reserva Completada: {funnel['reserva_completada']}")
        print(f"   Abandono Modal: {funnel['abandono_modal']}")
        print(f"   Conversion Rate Pedir: {funnel['conversion_rate_pedir']}%")
        print(f"   Conversion Rate Reservar: {funnel['conversion_rate_reservar']}%")
        
        print("\n✅ Eventos por dispositivo:")
        for device, count in detailed["events_by_device"].items():
            print(f"   {device}: {count}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: Horas pico
    print("⏰ Identificando horas pico...")
    peak_hours = get_peak_hours(days=7)
    
    if peak_hours:
        print("✅ Top 3 horas con más conversiones:")
        for hour, count in peak_hours:
            print(f"   {hour}:00 hrs → {count} eventos")
    
    print("\n✅ CONEXIÓN GA4 EXITOSA\n")
