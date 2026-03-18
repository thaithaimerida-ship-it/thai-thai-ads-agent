"""
Thai Thai Ads Agent - Strategy Generator
Generador autónomo de estrategias y recomendaciones

Capacidades:
- Generación de ideas de nuevas campañas
- Detección de oportunidades de mercado
- Recomendaciones de optimización
- Análisis de competencia (futuro)
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
import os

class StrategyGenerator:
    """
    Generador de estrategias basado en análisis de datos y patrones.
    Integra con sistema de memoria para aprender de decisiones pasadas.
    """
    
    def __init__(self):
        self.CPA_TARGET = 15.0
        self.MIN_CONFIDENCE = 70.0
    
    def generate_campaign_ideas(
        self,
        current_campaigns: List[Dict],
        ga4_data: Dict,
        market_trends: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Genera ideas de nuevas campañas basadas en:
        - Gaps en cobertura actual
        - Tendencias de GA4
        - Búsquedas con alto volumen
        
        Returns:
            Lista de recomendaciones con formato:
            {
                title, description, budget_suggested, keywords,
                confidence, expected_impact
            }
        """
        recommendations = []
        
        # Analizar eventos de GA4 para detectar intereses
        events = ga4_data.get('events_by_name', {})
        
        # Oportunidad 1: Si hay muchos clicks en "Pedir Online" pero pocas conversiones
        pedir_clicks = events.get('click_pedir_online', 0)
        reservas = events.get('reserva_completada', 0)
        
        if pedir_clicks > 10 and reservas < pedir_clicks * 0.3:
            recommendations.append({
                'type': 'new_campaign',
                'title': 'Campaña de Delivery Optimizada',
                'description': 'Detectamos alto interés en pedidos online pero baja conversión. '
                               'Campaña enfocada en delivery con landing page optimizada y promoción de "Envío Gratis".',
                'budget_suggested': 500.0,
                'keywords': ['thai delivery', 'comida thai a domicilio', 'thai food delivery merida'],
                'confidence': 75.0,
                'expected_impact': {
                    'conversions_increase': 15,
                    'cpa_target': 12.0
                },
                'priority': 'high',
                'reasoning': f'Alto interés ({pedir_clicks} clicks) pero solo {reservas} conversiones. '
                             'Oportunidad de capturar demanda no satisfecha.'
            })
        
        # Oportunidad 2: Horarios pico sin campañas optimizadas
        peak_hours = self._analyze_peak_hours(ga4_data.get('events_by_hour', {}))
        if peak_hours:
            top_hour = peak_hours[0]
            recommendations.append({
                'type': 'optimization',
                'title': f'Optimización de Presupuesto por Horario',
                'description': f'Detectamos que las {top_hour["hour"]}:00 hrs genera {top_hour["percentile"]}% '
                               f'de los eventos. Ajustar presupuesto para maximizar ROI en horas pico.',
                'budget_suggested': 0,  # Es redistribución
                'action_required': 'Aumentar pujas en horario 14:00-17:00 en 30%',
                'confidence': 80.0,
                'expected_impact': {
                    'cpa_reduction': 2.5,
                    'conversions_increase': 8
                },
                'priority': 'medium',
                'reasoning': 'Concentración de actividad permite optimización temporal de pujas.'
            })
        
        # Oportunidad 3: Nicho vegetariano/vegano (si no existe campaña)
        if not self._campaign_exists(current_campaigns, 'vegan'):
            recommendations.append({
                'type': 'new_campaign',
                'title': 'Campaña "Thai Vegano"',
                'description': 'Creciente demanda de opciones veganas. Campaña específica con keywords '
                               'de nicho y creativos enfocados en platos vegetarianos.',
                'budget_suggested': 300.0,
                'keywords': ['thai vegano merida', 'comida thai vegetariana', 'pad thai vegano'],
                'confidence': 65.0,
                'expected_impact': {
                    'conversions_increase': 10,
                    'cpa_target': 14.0
                },
                'priority': 'medium',
                'reasoning': 'Tendencia de búsqueda creciente en nicho vegano/vegetariano. '
                             'Competencia baja, potencial de captura de mercado.'
            })
        
        # Oportunidad 4: Dispositivos móviles (si performance es buena)
        devices = ga4_data.get('events_by_device', {})
        mobile_events = devices.get('mobile', 0)
        total_events = sum(devices.values()) or 1
        mobile_pct = (mobile_events / total_events) * 100
        
        if mobile_pct > 40:
            recommendations.append({
                'type': 'optimization',
                'title': 'Ajuste de Pujas por Dispositivo',
                'description': f'{mobile_pct:.1f}% de los eventos vienen de móvil. '
                               'Incrementar pujas móviles para capturar mejor este segmento.',
                'budget_suggested': 0,
                'action_required': 'Modificador de puja móvil: +25%',
                'confidence': 85.0,
                'expected_impact': {
                    'conversions_increase': 12,
                    'mobile_cpa': 13.5
                },
                'priority': 'high',
                'reasoning': 'Alto volumen de tráfico móvil con potencial de conversión.'
            })
        
        # Ordenar por prioridad y confianza
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(
            key=lambda x: (priority_order.get(x.get('priority', 'low'), 3), -x['confidence'])
        )
        
        return recommendations
    
    def _analyze_peak_hours(self, hourly_data: Dict[str, int]) -> List[Dict]:
        """Analiza horas pico de actividad"""
        if not hourly_data:
            return []
        
        sorted_hours = sorted(hourly_data.items(), key=lambda x: int(x[1]), reverse=True)
        total = sum(hourly_data.values()) or 1
        
        peak_hours = []
        for hour, events in sorted_hours[:3]:
            peak_hours.append({
                'hour': int(hour),
                'events': events,
                'percentile': round((events / total) * 100, 1)
            })
        
        return peak_hours
    
    def _campaign_exists(self, campaigns: List[Dict], keyword: str) -> bool:
        """Verifica si ya existe una campaña con keyword específico"""
        for camp in campaigns:
            if keyword.lower() in camp.get('campaign_name', '').lower():
                return True
        return False
    
    def analyze_waste_opportunities(
        self,
        campaigns: List[Dict],
        search_terms: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Detecta oportunidades de reducción de desperdicio.
        
        Returns:
            Lista de alertas y acciones sugeridas
        """
        opportunities = []
        
        # Detectar campañas con CPA alto
        for camp in campaigns:
            if camp.get('cpa', 0) > self.CPA_TARGET * 1.5:
                opportunities.append({
                    'type': 'alert',
                    'title': f'CPA Crítico en "{camp["campaign_name"]}"',
                    'description': f'CPA de ${camp["cpa"]:.2f} está 50% por encima del target.',
                    'action_required': 'Auditoría urgente de keywords y creativos',
                    'confidence': 95.0,
                    'priority': 'critical',
                    'expected_savings': camp['spend'] * 0.3  # Potencial ahorro del 30%
                })
        
        # Detectar gasto en campañas removidas (gasto fantasma)
        for camp in campaigns:
            if camp.get('status') == 'REMOVED' and camp.get('spend', 0) > 0:
                opportunities.append({
                    'type': 'alert',
                    'title': 'Gasto Fantasma Detectado',
                    'description': f'Campaña "{camp["campaign_name"]}" está REMOVED pero '
                                   f'sigue generando gasto de ${camp["spend"]:.2f}',
                    'action_required': 'Solicitar reembolso inmediato a Google Ads',
                    'confidence': 100.0,
                    'priority': 'critical',
                    'expected_savings': camp['spend']
                })
        
        return opportunities
    
    def generate_creative_suggestions(
        self,
        campaign_name: str,
        current_ctr: float,
        industry_benchmark_ctr: float = 2.0
    ) -> Dict:
        """
        Genera sugerencias de mejora de creativos.
        
        Args:
            campaign_name: Nombre de la campaña
            current_ctr: CTR actual (%)
            industry_benchmark_ctr: CTR benchmark de la industria
            
        Returns:
            Recomendaciones de copy y creativos
        """
        if current_ctr < industry_benchmark_ctr * 0.7:
            urgency = 'high'
            message = 'CTR significativamente bajo. Renovación urgente de creativos.'
        elif current_ctr < industry_benchmark_ctr:
            urgency = 'medium'
            message = 'CTR por debajo del promedio. Optimización recomendada.'
        else:
            urgency = 'low'
            message = 'CTR saludable. Continuar con A/B testing.'
        
        suggestions = {
            'urgency': urgency,
            'message': message,
            'copy_ideas': [
                'Incluir precio o promoción en headline',
                'Agregar urgencia: "Hoy", "Ahora", "Última oportunidad"',
                'Destacar diferenciador: "Auténtico Thai", "Chef Tailandés"',
                'Call-to-action directo: "Reserva Ya", "Pide Ahora"'
            ],
            'asset_recommendations': [
                'Fotos de alta calidad de platos signature',
                'Video corto del proceso de cocina',
                'Testimoniales de clientes',
                'Foto del chef o del restaurante'
            ],
            'expected_ctr_lift': round((industry_benchmark_ctr - current_ctr) / current_ctr * 100, 1)
        }
        
        return suggestions
    
    def calculate_recommendation_confidence(
        self,
        data_quality: float,  # 0-1
        pattern_match: bool,
        historical_success_rate: Optional[float] = None
    ) -> float:
        """
        Calcula nivel de confianza en una recomendación.
        
        Args:
            data_quality: Calidad de los datos (0-1)
            pattern_match: Si coincide con patrones conocidos
            historical_success_rate: Tasa de éxito histórica de recomendaciones similares
            
        Returns:
            Confianza en % (0-100)
        """
        base_confidence = data_quality * 60  # Máx 60 puntos por calidad de datos
        
        if pattern_match:
            base_confidence += 20
        
        if historical_success_rate is not None:
            base_confidence += historical_success_rate * 20  # Máx 20 puntos por historial
        
        return min(100, max(0, base_confidence))
    
    def generate_keyword_expansion_ideas(
        self,
        current_keywords: List[str],
        performance_data: Dict
    ) -> List[Dict]:
        """
        Genera ideas de expansión de keywords basadas en performance.
        
        Args:
            current_keywords: Keywords actuales
            performance_data: Métricas de performance
            
        Returns:
            Lista de keywords sugeridas con justificación
        """
        suggestions = []
        
        # Keywords de proximidad geográfica
        geo_modifiers = ['merida', 'norte merida', 'centro merida', 'cerca de mi']
        base_terms = ['thai', 'comida thai', 'restaurante thai']
        
        for base in base_terms:
            for geo in geo_modifiers:
                full_keyword = f'{base} {geo}'
                if full_keyword not in current_keywords:
                    suggestions.append({
                        'keyword': full_keyword,
                        'match_type': 'phrase',
                        'rationale': 'Captura búsquedas con intención local',
                        'expected_cpa': self.CPA_TARGET * 0.9,  # Mejor CPA esperado
                        'priority': 'high'
                    })
        
        # Keywords de platos específicos
        dish_keywords = [
            'pad thai merida',
            'curry thai',
            'tom yum',
            'massaman curry',
            'thai fried rice'
        ]
        
        for dish in dish_keywords:
            if dish not in current_keywords:
                suggestions.append({
                    'keyword': dish,
                    'match_type': 'phrase',
                    'rationale': 'Alta intención de compra - búsqueda específica de plato',
                    'expected_cpa': self.CPA_TARGET,
                    'priority': 'medium'
                })
        
        return suggestions[:10]  # Top 10 sugerencias


# Singleton instance
_strategy_generator = None

def get_strategy_generator() -> StrategyGenerator:
    """Obtiene instancia singleton del generador de estrategias"""
    global _strategy_generator
    if _strategy_generator is None:
        _strategy_generator = StrategyGenerator()
    return _strategy_generator
