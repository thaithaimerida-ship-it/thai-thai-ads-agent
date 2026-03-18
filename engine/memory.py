"""
Thai Thai Ads Agent - Memory System
Sistema de memoria persistente para aprendizaje autónomo y toma de decisiones

Este módulo gestiona:
- Registro de decisiones y sus resultados
- Detección y almacenamiento de patrones
- Aprendizaje continuo post-optimización
- Contexto histórico de mercado
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

class MemorySystem:
    """
    Sistema de memoria persistente con SQLite.
    Implementa compactación de contexto para evitar degradación del razonamiento.
    """
    
    def __init__(self, db_path: str = "./thai_thai_memory.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Inicializa la base de datos con el schema"""
        schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
        
        with sqlite3.connect(self.db_path) as conn:
            # Si existe el schema SQL, ejecutarlo
            if schema_path.exists():
                with open(schema_path, 'r', encoding='utf-8') as f:
                    conn.executescript(f.read())
            else:
                # Schema inline como fallback
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        decision_type TEXT NOT NULL,
                        action_data TEXT NOT NULL,
                        reason TEXT,
                        confidence_score REAL,
                        expected_impact TEXT,
                        context_snapshot TEXT,
                        executed BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS decision_outcomes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        decision_id INTEGER NOT NULL,
                        days_after INTEGER NOT NULL,
                        metrics_before TEXT,
                        metrics_after TEXT,
                        variance_pct REAL,
                        success BOOLEAN,
                        learnings TEXT,
                        measured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (decision_id) REFERENCES decisions(id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pattern_type TEXT NOT NULL,
                        pattern_data TEXT NOT NULL,
                        confidence REAL,
                        occurrences INTEGER DEFAULT 1,
                        success_rate REAL,
                        last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE TABLE IF NOT EXISTS learnings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        learning_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT,
                        evidence_count INTEGER DEFAULT 1,
                        confidence REAL,
                        applicable_contexts TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_reinforced DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                """)
    
    def record_decision(
        self,
        decision_type: str,
        action_data: Dict,
        reason: str,
        confidence_score: float,
        expected_impact: Dict,
        context_snapshot: Dict,
        executed: bool = False
    ) -> int:
        """
        Registra una decisión tomada por el agente.
        
        Args:
            decision_type: Tipo de decisión ('block_keyword', 'new_campaign', etc.)
            action_data: Detalles de la acción en formato dict
            reason: Explicación del razonamiento (human-readable)
            confidence_score: Confianza en la decisión (0-100)
            expected_impact: Métricas esperadas
            context_snapshot: Estado del sistema al momento
            executed: Si se ejecutó realmente o fue simulación
            
        Returns:
            ID de la decisión registrada
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO decisions 
                (decision_type, action_data, reason, confidence_score, 
                 expected_impact, context_snapshot, executed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_type,
                json.dumps(action_data),
                reason,
                confidence_score,
                json.dumps(expected_impact),
                json.dumps(context_snapshot),
                executed
            ))
            return cursor.lastrowid
    
    def record_outcome(
        self,
        decision_id: int,
        days_after: int,
        metrics_before: Dict,
        metrics_after: Dict,
        success: bool
    ) -> None:
        """
        Registra el resultado de una decisión después de N días.
        Implementa el ciclo de auto-aprendizaje.
        
        Args:
            decision_id: ID de la decisión original
            days_after: Días transcurridos (típicamente 7)
            metrics_before: Métricas antes de la decisión
            metrics_after: Métricas después de la decisión
            success: Si alcanzó el objetivo
        """
        # Calcular variación
        expected_cpa = metrics_before.get('cpa', 0)
        actual_cpa = metrics_after.get('cpa', 0)
        variance_pct = ((actual_cpa - expected_cpa) / expected_cpa * 100) if expected_cpa else 0
        
        # Generar learnings
        learnings = self._generate_learnings(metrics_before, metrics_after, success)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO decision_outcomes 
                (decision_id, days_after, metrics_before, metrics_after, 
                 variance_pct, success, learnings)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_id,
                days_after,
                json.dumps(metrics_before),
                json.dumps(metrics_after),
                variance_pct,
                success,
                learnings
            ))
        
        # Auto-ajuste: si falló, reforzar anti-patrón
        if not success:
            self._record_anti_pattern(decision_id)
    
    def _generate_learnings(
        self,
        before: Dict,
        after: Dict,
        success: bool
    ) -> str:
        """Genera insights a partir de los resultados"""
        learnings = []
        
        # Análisis de CPA
        cpa_before = before.get('cpa', 0)
        cpa_after = after.get('cpa', 0)
        if cpa_after < cpa_before:
            learnings.append(f"CPA mejoró de ${cpa_before:.2f} a ${cpa_after:.2f}")
        elif cpa_after > cpa_before:
            learnings.append(f"CPA empeoró de ${cpa_before:.2f} a ${cpa_after:.2f}")
        
        # Análisis de conversiones
        conv_before = before.get('conversions', 0)
        conv_after = after.get('conversions', 0)
        if conv_after > conv_before:
            learnings.append(f"Conversiones aumentaron de {conv_before} a {conv_after}")
        
        # Conclusión
        if success:
            learnings.append("✅ Decisión efectiva - Reforzar patrón")
        else:
            learnings.append("❌ Decisión inefectiva - Ajustar criterios")
        
        return " | ".join(learnings)
    
    def _record_anti_pattern(self, decision_id: int):
        """Registra un anti-patrón cuando una decisión falla"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Obtener detalles de la decisión
            cursor.execute("""
                SELECT decision_type, action_data, reason
                FROM decisions WHERE id = ?
            """, (decision_id,))
            row = cursor.fetchone()
            
            if row:
                self.record_pattern(
                    pattern_type="anti_pattern",
                    pattern_data={
                        "decision_type": row[0],
                        "action": json.loads(row[1]),
                        "failed_reason": row[2]
                    },
                    confidence=0.7,
                    success_rate=0.0
                )
    
    def record_pattern(
        self,
        pattern_type: str,
        pattern_data: Dict,
        confidence: float,
        success_rate: float = None
    ) -> None:
        """
        Registra un patrón detectado.
        Si ya existe, incrementa occurrences y actualiza success_rate.
        """
        pattern_json = json.dumps(pattern_data, sort_keys=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Verificar si ya existe
            cursor.execute("""
                SELECT id, occurrences, success_rate 
                FROM patterns 
                WHERE pattern_type = ? AND pattern_data = ?
            """, (pattern_type, pattern_json))
            
            existing = cursor.fetchone()
            
            if existing:
                # Actualizar
                new_occurrences = existing[1] + 1
                # Promedio móvil de success_rate
                if success_rate is not None:
                    new_success_rate = (existing[2] * existing[1] + success_rate) / new_occurrences
                else:
                    new_success_rate = existing[2]
                
                cursor.execute("""
                    UPDATE patterns 
                    SET occurrences = ?, 
                        success_rate = ?,
                        confidence = ?,
                        last_observed = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_occurrences, new_success_rate, confidence, existing[0]))
            else:
                # Insertar nuevo
                cursor.execute("""
                    INSERT INTO patterns 
                    (pattern_type, pattern_data, confidence, success_rate)
                    VALUES (?, ?, ?, ?)
                """, (pattern_type, pattern_json, confidence, success_rate or 0.5))
    
    def get_high_confidence_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.7
    ) -> List[Dict]:
        """
        Obtiene patrones de alta confianza para informar futuras decisiones.
        
        Args:
            pattern_type: Filtrar por tipo (opcional)
            min_confidence: Confianza mínima (0-1)
            
        Returns:
            Lista de patrones con sus métricas
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT pattern_type, pattern_data, confidence, 
                       occurrences, success_rate, last_observed
                FROM patterns
                WHERE confidence >= ?
            """
            params = [min_confidence]
            
            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)
            
            query += " ORDER BY success_rate DESC, confidence DESC"
            
            cursor.execute(query, params)
            
            patterns = []
            for row in cursor.fetchall():
                patterns.append({
                    'type': row[0],
                    'data': json.loads(row[1]),
                    'confidence': row[2],
                    'occurrences': row[3],
                    'success_rate': row[4],
                    'last_observed': row[5]
                })
            
            return patterns
    
    def get_decision_history(
        self,
        days: int = 30,
        decision_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Obtiene historial de decisiones con sus resultados.
        
        Args:
            days: Días hacia atrás
            decision_type: Filtrar por tipo (opcional)
            
        Returns:
            Lista de decisiones con outcomes
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    d.id,
                    d.timestamp,
                    d.decision_type,
                    d.action_data,
                    d.reason,
                    d.confidence_score,
                    d.executed,
                    o.success,
                    o.variance_pct,
                    o.learnings
                FROM decisions d
                LEFT JOIN decision_outcomes o ON d.id = o.decision_id
                WHERE d.timestamp >= ?
            """
            params = [cutoff_date.isoformat()]
            
            if decision_type:
                query += " AND d.decision_type = ?"
                params.append(decision_type)
            
            query += " ORDER BY d.timestamp DESC"
            
            cursor.execute(query, params)
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'type': row[2],
                    'action': json.loads(row[3]),
                    'reason': row[4],
                    'confidence': row[5],
                    'executed': bool(row[6]),
                    'success': bool(row[7]) if row[7] is not None else None,
                    'variance_pct': row[8],
                    'learnings': row[9]
                })
            
            return history
    
    def record_learning(
        self,
        learning_type: str,
        title: str,
        description: str,
        confidence: float,
        applicable_contexts: List[str]
    ) -> None:
        """Registra un aprendizaje consolidado"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learnings 
                (learning_type, title, description, confidence, applicable_contexts)
                VALUES (?, ?, ?, ?, ?)
            """, (
                learning_type,
                title,
                description,
                confidence,
                json.dumps(applicable_contexts)
            ))
    
    def get_learnings(self, min_confidence: float = 0.7) -> List[Dict]:
        """Obtiene aprendizajes consolidados de alta confianza"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, description, confidence, evidence_count,
                       applicable_contexts, last_reinforced
                FROM learnings
                WHERE confidence >= ?
                ORDER BY confidence DESC, evidence_count DESC
            """, (min_confidence,))
            
            learnings = []
            for row in cursor.fetchall():
                learnings.append({
                    'title': row[0],
                    'description': row[1],
                    'confidence': row[2],
                    'evidence_count': row[3],
                    'applicable_contexts': json.loads(row[4]),
                    'last_reinforced': row[5]
                })
            
            return learnings
    
    def get_success_rate_by_decision_type(self) -> Dict[str, float]:
        """
        Calcula tasa de éxito por tipo de decisión.
        Útil para ajustar confianza en futuras decisiones.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    d.decision_type,
                    AVG(CASE WHEN o.success = 1 THEN 1.0 ELSE 0.0 END) as success_rate,
                    COUNT(*) as total_decisions
                FROM decisions d
                INNER JOIN decision_outcomes o ON d.id = o.decision_id
                GROUP BY d.decision_type
            """)
            
            rates = {}
            for row in cursor.fetchall():
                rates[row[0]] = {
                    'success_rate': row[1],
                    'total_decisions': row[2]
                }
            
            return rates


# Singleton instance
_memory_system = None

def get_memory_system() -> MemorySystem:
    """Obtiene instancia singleton del sistema de memoria"""
    global _memory_system
    if _memory_system is None:
        _memory_system = MemorySystem()
    return _memory_system
