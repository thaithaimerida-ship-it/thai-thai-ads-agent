"""
Thai Thai Ads Agent - Prediction Engine
Motor de predicción basado en regresión lineal, análisis de tendencias y IA

Capacidades:
- Predicción de conversiones futuras
- Proyección de CPA
- Detección de tendencias estacionales
- Análisis de horas/días pico
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import statistics

class PredictionEngine:
    """
    Motor de predicción para métricas de campañas.
    Usa regresión simple y análisis estadístico.
    """
    
    def __init__(self):
        pass
    
    def predict_conversions(
        self,
        historical_data: List[Dict],
        days_ahead: int = 7
    ) -> Dict:
        """
        Predice conversiones para los próximos N días.
        
        Args:
            historical_data: Lista de {date, conversions, spend}
            days_ahead: Días a proyectar
            
        Returns:
            {predicted_conversions, confidence, trend}
        """
        if len(historical_data) < 3:
            return {
                'predicted_conversions': 0,
                'confidence': 0,
                'trend': 'insufficient_data',
                'method': 'none'
            }
        
        # Extraer serie temporal de conversiones
        conversions_series = [d['conversions'] for d in historical_data]
        
        # Calcular tendencia con regresión lineal simple
        n = len(conversions_series)
        x = list(range(n))
        y = conversions_series
        
        # Pendiente y ordenada
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        
        intercept = y_mean - slope * x_mean
        
        # Proyectar días_ahead
        future_x = n + days_ahead - 1
        predicted = slope * future_x + intercept
        predicted = max(0, predicted)  # No predicciones negativas
        
        # Calcular confianza basada en R²
        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        confidence = max(0, min(100, r_squared * 100))
        
        # Determinar tendencia
        if slope > 0.1:
            trend = 'growing'
        elif slope < -0.1:
            trend = 'declining'
        else:
            trend = 'stable'
        
        return {
            'predicted_conversions': round(predicted, 1),
            'confidence': round(confidence, 1),
            'trend': trend,
            'slope': slope,
            'method': 'linear_regression'
        }
    
    def predict_cpa(
        self,
        historical_data: List[Dict],
        target_conversions: Optional[int] = None
    ) -> Dict:
        """
        Predice CPA futuro basado en tendencias históricas.
        
        Args:
            historical_data: Lista de {date, cpa, conversions, spend}
            target_conversions: Conversiones objetivo (opcional)
            
        Returns:
            {predicted_cpa, confidence, recommendation}
        """
        if len(historical_data) < 3:
            return {
                'predicted_cpa': 0,
                'confidence': 0,
                'recommendation': 'Necesitas más datos históricos'
            }
        
        # Extraer CPAs
        cpa_series = [d.get('cpa', 0) for d in historical_data]
        recent_cpa_avg = statistics.mean(cpa_series[-7:])  # Últimos 7 días
        
        # Detectar volatilidad
        cpa_stdev = statistics.stdev(cpa_series) if len(cpa_series) > 1 else 0
        coefficient_of_variation = (cpa_stdev / recent_cpa_avg) if recent_cpa_avg > 0 else 0
        
        # Confianza inversa a la volatilidad
        confidence = max(0, 100 - (coefficient_of_variation * 100))
        
        # Recomendación
        CPA_TARGET = 15.0
        if recent_cpa_avg < CPA_TARGET:
            recommendation = "CPA por debajo del target. Considerar escalar presupuesto."
        elif recent_cpa_avg < CPA_TARGET * 1.2:
            recommendation = "CPA aceptable. Monitorear de cerca."
        else:
            recommendation = "CPA por encima del target. Optimización urgente requerida."
        
        return {
            'predicted_cpa': round(recent_cpa_avg, 2),
            'confidence': round(confidence, 1),
            'volatility': round(coefficient_of_variation, 3),
            'recommendation': recommendation,
            'target': CPA_TARGET
        }
    
    def detect_peak_hours(
        self,
        hourly_data: Dict[int, int]
    ) -> List[Dict]:
        """
        Identifica las horas pico de conversiones.
        
        Args:
            hourly_data: {hour: events_count}
            
        Returns:
            Lista de {hour, events, percentile}
        """
        if not hourly_data:
            return []
        
        # Ordenar por eventos
        sorted_hours = sorted(hourly_data.items(), key=lambda x: x[1], reverse=True)
        
        total_events = sum(hourly_data.values())
        
        peak_hours = []
        for hour, events in sorted_hours[:5]:  # Top 5 horas
            percentile = (events / total_events * 100) if total_events > 0 else 0
            peak_hours.append({
                'hour': hour,
                'events': events,
                'percentile': round(percentile, 1)
            })
        
        return peak_hours
    
    def detect_seasonality(
        self,
        daily_data: List[Dict]
    ) -> Dict:
        """
        Detecta patrones estacionales (día de semana, tendencias semanales).
        
        Args:
            daily_data: Lista de {date, conversions}
            
        Returns:
            {best_day_of_week, worst_day_of_week, weekend_vs_weekday}
        """
        if len(daily_data) < 7:
            return {
                'best_day': None,
                'worst_day': None,
                'pattern': 'insufficient_data'
            }
        
        # Agrupar por día de la semana
        by_day_of_week = {i: [] for i in range(7)}  # 0=Lunes, 6=Domingo
        
        for item in daily_data:
            date_obj = datetime.fromisoformat(item['date'])
            day_of_week = date_obj.weekday()
            by_day_of_week[day_of_week].append(item['conversions'])
        
        # Promedios por día
        day_averages = {}
        day_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        
        for day, conversions in by_day_of_week.items():
            if conversions:
                day_averages[day_names[day]] = statistics.mean(conversions)
        
        if not day_averages:
            return {'pattern': 'no_pattern_detected'}
        
        # Mejor y peor día
        best_day = max(day_averages, key=day_averages.get)
        worst_day = min(day_averages, key=day_averages.get)
        
        # Fin de semana vs entre semana
        weekend_avg = statistics.mean(
            by_day_of_week[5] + by_day_of_week[6]
        ) if by_day_of_week[5] or by_day_of_week[6] else 0
        
        weekday_avg = statistics.mean(
            [conv for day in range(5) for conv in by_day_of_week[day]]
        ) if any(by_day_of_week[day] for day in range(5)) else 0
        
        if weekend_avg > weekday_avg * 1.2:
            pattern = 'weekend_dominant'
        elif weekday_avg > weekend_avg * 1.2:
            pattern = 'weekday_dominant'
        else:
            pattern = 'balanced'
        
        return {
            'best_day': best_day,
            'worst_day': worst_day,
            'pattern': pattern,
            'day_averages': day_averages,
            'weekend_avg': round(weekend_avg, 1),
            'weekday_avg': round(weekday_avg, 1)
        }
    
    def simulate_budget_change(
        self,
        current_metrics: Dict,
        budget_change_pct: float
    ) -> Dict:
        """
        Simula el impacto de cambiar el presupuesto.
        
        Args:
            current_metrics: {spend, conversions, cpa}
            budget_change_pct: Cambio en % (ej: 20 para +20%, -10 para -10%)
            
        Returns:
            {projected_spend, projected_conversions, projected_cpa}
        """
        current_spend = current_metrics.get('spend', 0)
        current_conversions = current_metrics.get('conversions', 0)
        current_cpa = current_metrics.get('cpa', 0)
        
        # Proyección lineal (asume eficiencia constante)
        projected_spend = current_spend * (1 + budget_change_pct / 100)
        
        # Modelo con rendimientos decrecientes
        # A mayor escala, la eficiencia baja ligeramente
        efficiency_factor = 1 - (abs(budget_change_pct) / 100 * 0.1)  # Pérdida del 10% por cada 100% de cambio
        
        projected_conversions = current_conversions * (1 + budget_change_pct / 100 * efficiency_factor)
        projected_cpa = projected_spend / projected_conversions if projected_conversions > 0 else 0
        
        return {
            'current': {
                'spend': round(current_spend, 2),
                'conversions': round(current_conversions, 1),
                'cpa': round(current_cpa, 2)
            },
            'projected': {
                'spend': round(projected_spend, 2),
                'conversions': round(projected_conversions, 1),
                'cpa': round(projected_cpa, 2)
            },
            'delta': {
                'spend': round(projected_spend - current_spend, 2),
                'conversions': round(projected_conversions - current_conversions, 1),
                'cpa': round(projected_cpa - current_cpa, 2)
            },
            'efficiency_impact': round((1 - efficiency_factor) * 100, 1)
        }
    
    def calculate_confidence_score(
        self,
        data_points: int,
        variance: float,
        pattern_match: bool = False
    ) -> float:
        """
        Calcula score de confianza para una predicción.
        
        Args:
            data_points: Número de puntos de datos usados
            variance: Varianza en los datos (0-1)
            pattern_match: Si coincide con patrones conocidos
            
        Returns:
            Score de confianza (0-100)
        """
        # Base: más datos = más confianza
        data_score = min(100, (data_points / 30) * 50)  # 30 días = 50 puntos
        
        # Penalización por varianza alta
        variance_penalty = variance * 30
        
        # Bonus por pattern match
        pattern_bonus = 20 if pattern_match else 0
        
        confidence = data_score - variance_penalty + pattern_bonus
        return max(0, min(100, confidence))


# Singleton instance
_prediction_engine = None

def get_prediction_engine() -> PredictionEngine:
    """Obtiene instancia singleton del motor de predicción"""
    global _prediction_engine
    if _prediction_engine is None:
        _prediction_engine = PredictionEngine()
    return _prediction_engine
