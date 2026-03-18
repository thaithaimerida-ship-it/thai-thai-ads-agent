-- Thai Thai Ads Agent - Memory System Database Schema
-- Sistema de memoria persistente para aprendizaje autónomo

-- Tabla de decisiones tomadas por el agente
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    decision_type TEXT NOT NULL, -- 'block_keyword', 'new_campaign', 'budget_adjust', 'bid_adjust'
    action_data TEXT NOT NULL, -- JSON con detalles de la acción
    reason TEXT, -- Explicación del razonamiento
    confidence_score REAL, -- 0-100, confianza en la decisión
    expected_impact TEXT, -- JSON con métricas esperadas
    context_snapshot TEXT, -- JSON con estado del sistema al momento
    executed BOOLEAN DEFAULT 0, -- Si se ejecutó o fue simulación
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de resultados observados después de decisiones
CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    days_after INTEGER NOT NULL, -- Días transcurridos (típicamente 7)
    metrics_before TEXT, -- JSON con métricas antes de la decisión
    metrics_after TEXT, -- JSON con métricas después
    variance_pct REAL, -- Porcentaje de variación vs esperado
    success BOOLEAN, -- Si alcanzó el objetivo
    learnings TEXT, -- Insights extraídos
    measured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);

-- Tabla de patrones detectados
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL, -- 'temporal', 'keyword', 'audience', 'creative'
    pattern_data TEXT NOT NULL, -- JSON con detalles del patrón
    confidence REAL, -- Confianza estadística (0-1)
    occurrences INTEGER DEFAULT 1, -- Veces que se ha observado
    success_rate REAL, -- Tasa de éxito cuando se aplica
    last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de predicciones generadas
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_type TEXT NOT NULL, -- 'conversions', 'cpa', 'spend', 'trend'
    target_date DATE, -- Fecha objetivo de la predicción
    predicted_value REAL,
    actual_value REAL, -- Se llena cuando ocurre
    accuracy_pct REAL, -- Precisión de la predicción
    model_used TEXT, -- 'regression', 'ai_analysis', 'historical_avg'
    input_data TEXT, -- JSON con datos usados
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de recomendaciones estratégicas generadas
CREATE TABLE IF NOT EXISTS strategy_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_type TEXT NOT NULL, -- 'new_campaign', 'optimization', 'alert', 'opportunity'
    title TEXT NOT NULL,
    description TEXT,
    impact_estimate TEXT, -- JSON: {conversions_increase: X, revenue_increase: Y}
    investment_required REAL,
    confidence_level REAL, -- 0-100
    supporting_data TEXT, -- JSON con evidencia
    status TEXT DEFAULT 'pending', -- 'pending', 'executed', 'dismissed', 'simulated'
    priority TEXT, -- 'critical', 'high', 'medium', 'low'
    executed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de simulaciones ejecutadas
CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_name TEXT,
    parameters TEXT NOT NULL, -- JSON con parámetros ajustados
    predicted_outcome TEXT, -- JSON con resultados esperados
    comparison_baseline TEXT, -- JSON con datos actuales para comparar
    user_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de contexto de mercado histórico
CREATE TABLE IF NOT EXISTS market_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    day_of_week INTEGER, -- 0-6 (Domingo-Sábado)
    is_weekend BOOLEAN,
    is_holiday BOOLEAN,
    special_event TEXT, -- Día de las madres, San Valentín, etc.
    search_volume_index REAL, -- Volumen relativo de búsquedas
    competition_level TEXT, -- 'low', 'medium', 'high'
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Tabla de aprendizajes consolidados
CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_type TEXT NOT NULL, -- 'best_practice', 'anti_pattern', 'insight'
    title TEXT NOT NULL,
    description TEXT,
    evidence_count INTEGER DEFAULT 1, -- Número de evidencias que lo soportan
    confidence REAL, -- 0-100
    applicable_contexts TEXT, -- JSON con contextos donde aplica
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_reinforced DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Índices para optimizar consultas
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON decision_outcomes(decision_id);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON patterns(confidence);
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(target_date);
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON strategy_recommendations(status);
CREATE INDEX IF NOT EXISTS idx_recommendations_priority ON strategy_recommendations(priority);
CREATE INDEX IF NOT EXISTS idx_market_date ON market_context(date);

-- Vista consolidada de performance de decisiones
CREATE VIEW IF NOT EXISTS decision_performance AS
SELECT 
    d.id,
    d.decision_type,
    d.timestamp,
    d.confidence_score,
    d.executed,
    o.success,
    o.variance_pct,
    o.measured_at,
    CASE 
        WHEN o.success = 1 THEN 'success'
        WHEN o.success = 0 THEN 'failure'
        ELSE 'pending'
    END as outcome_status
FROM decisions d
LEFT JOIN decision_outcomes o ON d.id = o.decision_id;

-- Vista de patrones de alto rendimiento
CREATE VIEW IF NOT EXISTS high_performing_patterns AS
SELECT 
    pattern_type,
    pattern_data,
    confidence,
    occurrences,
    success_rate
FROM patterns
WHERE success_rate > 0.7 AND occurrences >= 3
ORDER BY success_rate DESC, confidence DESC;
