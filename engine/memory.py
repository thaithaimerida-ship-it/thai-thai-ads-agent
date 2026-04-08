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

from engine.db_sync import get_db_path

class MemorySystem:
    """
    Sistema de memoria persistente con SQLite.
    Implementa compactación de contexto para evitar degradación del razonamiento.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or get_db_path()
        self._init_database()
    
    def _init_database(self):
        """Inicializa la base de datos con el schema"""
        schema_path = Path(__file__).parent.parent / "database" / "schema.sql"

        with sqlite3.connect(self.db_path) as conn:
            # Tabla de decisiones autónomas (Phase 1A) — no altera tablas existentes
            self._create_autonomous_decisions_table(conn)

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
    
    def _create_autonomous_decisions_table(self, conn: sqlite3.Connection):
        """
        Crea la tabla autonomous_decisions para el sistema de autonomía por niveles.
        Tabla nueva — no altera ni toca las tablas existentes (decisions, patterns, etc.)
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_decisions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                session_id       TEXT,
                action_type      TEXT    NOT NULL,
                risk_level       INTEGER NOT NULL,
                urgency          TEXT    NOT NULL DEFAULT 'normal',
                campaign_id      TEXT,
                campaign_name    TEXT,
                keyword          TEXT,
                evidence_json    TEXT,
                decision         TEXT    NOT NULL,
                executed         INTEGER NOT NULL DEFAULT 0,
                proposal_sent    INTEGER NOT NULL DEFAULT 0,
                approval_token   TEXT,
                approved_at      TEXT,
                rejected_at      TEXT,
                postponed_at     TEXT,
                learning_phase_protected INTEGER NOT NULL DEFAULT 0,
                whitelisted      INTEGER NOT NULL DEFAULT 0
            )
        """)

    def record_autonomous_decision(
        self,
        action_type: str,
        risk_level: int,
        urgency: str,
        decision: str,
        campaign_id: str = None,
        campaign_name: str = None,
        keyword: str = None,
        evidence: dict = None,
        session_id: str = None,
        approval_token: str = None,
        executed: bool = False,
        proposal_sent: bool = False,
        learning_phase_protected: bool = False,
        whitelisted: bool = False,
    ) -> int:
        """
        Registra una decisión del sistema de autonomía por niveles.

        Args:
            action_type: Tipo de acción ('block_keyword', 'pause_ad_group', etc.)
            risk_level: 0=observar, 1=ejecutar, 2=proponer, 3=bloquear
            urgency: 'normal', 'urgent', 'critical'
            decision: 'observe', 'executed', 'proposed', 'blocked'
            approval_token: Token único para los links de aprobación por email

        Returns:
            ID del registro creado
        """
        import json as _json
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO autonomous_decisions
                (action_type, risk_level, urgency, decision,
                 campaign_id, campaign_name, keyword, evidence_json,
                 session_id, approval_token, executed, proposal_sent,
                 learning_phase_protected, whitelisted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_type,
                risk_level,
                urgency,
                decision,
                campaign_id,
                campaign_name,
                keyword,
                _json.dumps(evidence) if evidence else None,
                session_id,
                approval_token,
                1 if executed else 0,
                1 if proposal_sent else 0,
                1 if learning_phase_protected else 0,
                1 if whitelisted else 0,
            ))
            return cursor.lastrowid

    def mark_autonomous_decision_approved(self, decision_id: int) -> None:
        """Marca una decisión autónoma como aprobada."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE autonomous_decisions SET approved_at = datetime('now') WHERE id = ?",
                (decision_id,)
            )

    def mark_autonomous_decision_rejected(self, decision_id: int) -> None:
        """Marca una decisión autónoma como rechazada."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE autonomous_decisions SET rejected_at = datetime('now') WHERE id = ?",
                (decision_id,)
            )

    def mark_autonomous_decision_postponed(self, decision_id: int) -> None:
        """Marca una decisión autónoma como pospuesta."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE autonomous_decisions SET postponed_at = datetime('now') WHERE id = ?",
                (decision_id,)
            )

    # ------------------------------------------------------------------ Fase 2

    def sweep_expired_proposals(self) -> int:
        """
        Marca como 'postponed' todas las propuestas que superaron PROPOSAL_EXPIRY_HOURS
        sin recibir respuesta.

        Retorna el número de propuestas expiradas en este sweep.
        """
        from config.agent_config import PROPOSAL_EXPIRY_HOURS
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"""
                UPDATE autonomous_decisions
                SET postponed_at = datetime('now')
                WHERE decision = 'proposed'
                  AND approved_at   IS NULL
                  AND rejected_at   IS NULL
                  AND postponed_at  IS NULL
                  AND datetime(created_at, '+{PROPOSAL_EXPIRY_HOURS} hours') < datetime('now')
            """)
            return cursor.rowcount

    def has_pending_proposal(self, keyword: str, campaign_id: str) -> bool:
        """
        Retorna True si ya existe una propuesta activa (enviada pero sin respuesta
        y no expirada) para este par (keyword, campaign_id).

        Evita crear duplicados en ciclos consecutivos mientras la propuesta
        original sigue vigente.
        """
        from config.agent_config import PROPOSAL_EXPIRY_HOURS
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(f"""
                SELECT id FROM autonomous_decisions
                WHERE decision    = 'proposed'
                  AND keyword     = ?
                  AND campaign_id = ?
                  AND approved_at  IS NULL
                  AND rejected_at  IS NULL
                  AND postponed_at IS NULL
                  AND datetime(created_at, '+{PROPOSAL_EXPIRY_HOURS} hours') >= datetime('now')
                LIMIT 1
            """, (keyword, str(campaign_id))).fetchone()
            return row is not None

    def mark_proposals_sent(self, decision_ids: list) -> None:
        """
        Marca proposal_sent=1 solo para los IDs explícitamente recibidos.
        Solo se llama con las propuestas realmente incluidas en el correo
        priorizado (máximo MAX_PROPOSALS_PER_EMAIL).
        """
        if not decision_ids:
            return
        placeholders = ",".join("?" * len(decision_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE autonomous_decisions SET proposal_sent = 1 WHERE id IN ({placeholders})",
                decision_ids,
            )

    def get_decision_by_token(self, token: str) -> dict | None:
        """
        Retorna la fila completa de autonomous_decisions para un approval_token.
        Retorna None si el token no existe.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM autonomous_decisions WHERE approval_token = ?",
                (token,)
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------ Fase 4

    def has_recent_adgroup_proposal(self, adgroup_id: str, campaign_id: str) -> bool:
        """
        Retorna True si ya existe una propuesta activa (enviada pero sin respuesta
        y no expirada) para este ad group en esta campaña.

        Convención MVP: el ad group se identifica mediante el campo `keyword`
        usando el prefijo 'adgroup:{adgroup_id}'. Esta convención evita agregar
        columnas nuevas al schema y mantiene compatibilidad con has_pending_proposal().

        Args:
            adgroup_id : ID del ad group en Google Ads (string)
            campaign_id: ID de la campaña padre (string)

        Reutiliza has_pending_proposal() con la clave 'adgroup:{adgroup_id}'.
        """
        return self.has_pending_proposal(
            keyword=f"adgroup:{adgroup_id}",
            campaign_id=campaign_id,
        )

    def mark_adgroup_paused(self, decision_id: int, verify_data: dict) -> None:
        """
        Marca un ad group como pausado exitosamente vía API.

        Actualiza: approved_at=now, executed=1.
        Agrega a evidence_json (ajuste #2 del usuario):
          approve_outcome              : 'execution_done'
          verify_adgroup_still_pausable: bool (resultado de la verificación)
          verify_checked_at            : ISO timestamp de la verificación
          ad_group_status              : estado del ad group al verificar
          enabled_adgroups_in_campaign : conteo de grupos ENABLED al verificar
          guard_triggered              : '' (ninguna guarda activada en este path)
        """
        import json as _json
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            evidence = _json.loads(row[0]) if row and row[0] else {}
            evidence.update({
                "approve_outcome": "execution_done",
                "verify_adgroup_still_pausable": verify_data.get("ok", True),
                "verify_checked_at": verify_data.get("verify_checked_at", ""),
                "ad_group_status": verify_data.get("ad_group_status", ""),
                "enabled_adgroups_in_campaign": verify_data.get("enabled_adgroups_in_campaign", 0),
                "guard_triggered": verify_data.get("guard", ""),
            })
            conn.execute("""
                UPDATE autonomous_decisions
                SET approved_at   = datetime('now'),
                    executed      = 1,
                    evidence_json = ?
                WHERE id = ?
            """, (_json.dumps(evidence, ensure_ascii=False), decision_id))

    def mark_adgroup_approved_blocked(
        self,
        decision_id: int,
        reason: str,
        approve_outcome: str,
        verify_data: dict | None = None,
    ) -> None:
        """
        Registra que la aprobación fue recibida pero la ejecución quedó bloqueada.

        Casos de uso:
          - ADGROUP_PAUSE_ENABLED=false → approve_outcome='approved_registered', reason='pause_disabled'
          - Guarda G1/G2 fallida        → approve_outcome='approved_blocked',    reason=<texto guarda>

        Actualiza: approved_at=now, executed=0.
        Agrega a evidence_json (ajuste #2 del usuario):
          approve_outcome              : 'approved_registered' | 'approved_blocked'
          execution_block_reason       : razón del bloqueo (string)
          verify_adgroup_still_pausable: bool (si se ejecutó verificación)
          verify_checked_at            : ISO timestamp (si disponible)
          ad_group_status              : estado del ad group (si disponible)
          enabled_adgroups_in_campaign : conteo (si disponible)
          guard_triggered              : código de guarda ('G1', 'G2', o '')
        """
        import json as _json
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            evidence = _json.loads(row[0]) if row and row[0] else {}
            evidence.update({
                "approve_outcome": approve_outcome,
                "execution_block_reason": reason,
            })
            if verify_data:
                evidence.update({
                    "verify_adgroup_still_pausable": verify_data.get("ok", False),
                    "verify_checked_at": verify_data.get("verify_checked_at", ""),
                    "ad_group_status": verify_data.get("ad_group_status", ""),
                    "enabled_adgroups_in_campaign": verify_data.get("enabled_adgroups_in_campaign", 0),
                    "guard_triggered": verify_data.get("guard", ""),
                })
            conn.execute("""
                UPDATE autonomous_decisions
                SET approved_at   = datetime('now'),
                    executed      = 0,
                    evidence_json = ?
                WHERE id = ?
            """, (_json.dumps(evidence, ensure_ascii=False), decision_id))

    def mark_budget_changed(
        self,
        decision_id: int,
        verify_data: dict,
        new_budget_mxn: float,
    ) -> None:
        """
        Marca que el presupuesto fue cambiado exitosamente vía API (Fase 6B.1).

        Actualiza: approved_at=now, executed=1.
        Agrega a evidence_json:
          approve_outcome         : 'execution_done'
          verify_checked_at       : ISO timestamp de la verificación
          current_budget_mxn      : presupuesto actual re-fetched antes de ejecutar
          new_budget_mxn          : presupuesto resultante después de la mutación
          reduction_pct_actual    : reducción real ejecutada (%)
          campaign_status         : estado de la campaña al verificar
          budget_explicitly_shared: si el presupuesto era compartido
          guard_triggered         : '' (ninguna guarda activada en este path)
        """
        import json as _json
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            evidence = _json.loads(row[0]) if row and row[0] else {}
            evidence.update({
                "approve_outcome":          "execution_done",
                "verify_checked_at":        verify_data.get("verify_checked_at", ""),
                "current_budget_mxn":       verify_data.get("current_budget_mxn", 0.0),
                "new_budget_mxn":           new_budget_mxn,
                "reduction_pct_actual":     verify_data.get("reduction_pct_actual", 0.0),
                "campaign_status":          verify_data.get("campaign_status", ""),
                "budget_explicitly_shared": verify_data.get("budget_explicitly_shared", False),
                "guard_triggered":          "",
            })
            conn.execute("""
                UPDATE autonomous_decisions
                SET approved_at   = datetime('now'),
                    executed      = 1,
                    evidence_json = ?
                WHERE id = ?
            """, (_json.dumps(evidence, ensure_ascii=False), decision_id))

    def mark_budget_approved_blocked(
        self,
        decision_id: int,
        reason: str,
        approve_outcome: str,
        verify_data: dict | None = None,
    ) -> None:
        """
        Registra que la aprobación fue recibida pero la ejecución no ocurrió (Fase 6B.1).

        Estados posibles (approve_outcome):
          'approved_registered'   — kill switch off; ejecución manual requerida
          'approved_dry_run_ok'   — kill switch off pero todas las guardas pasarían
          'approved_blocked'      — kill switch on pero una guarda bloqueó la ejecución
          'approved_exec_error'   — guardas pasaron pero la API rechazó la mutación

        Actualiza: approved_at=now, executed=0.
        Agrega a evidence_json: approve_outcome, execution_block_reason, y datos del verify.
        """
        import json as _json
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT evidence_json FROM autonomous_decisions WHERE id = ?",
                (decision_id,)
            ).fetchone()
            evidence = _json.loads(row[0]) if row and row[0] else {}
            evidence.update({
                "approve_outcome":       approve_outcome,
                "execution_block_reason": reason,
            })
            if verify_data:
                evidence.update({
                    "verify_checked_at":        verify_data.get("verify_checked_at", ""),
                    "current_budget_mxn":       verify_data.get("current_budget_mxn", 0.0),
                    "reduction_pct_actual":     verify_data.get("reduction_pct_actual", 0.0),
                    "campaign_status":          verify_data.get("campaign_status", ""),
                    "budget_explicitly_shared": verify_data.get("budget_explicitly_shared", False),
                    "guard_triggered":          verify_data.get("guard", ""),
                })
            conn.execute("""
                UPDATE autonomous_decisions
                SET approved_at   = datetime('now'),
                    executed      = 0,
                    evidence_json = ?
                WHERE id = ?
            """, (_json.dumps(evidence, ensure_ascii=False), decision_id))

    # ------------------------------------------------------------------ /Fase 4

    # ------------------------------------------------------------------ Fase 3A

    def has_recent_alert(self, action_type: str, hours: int) -> bool:
        """
        Retorna True si ya existe un registro de alerta del mismo tipo enviado
        en las últimas `hours` horas.

        Usado para de-duplicar alertas de tracking — evita enviar la misma
        alerta varias veces si el agente corre cada hora.

        Args:
            action_type : tipo de acción a buscar (p. ej. 'tracking_alert')
            hours       : ventana de deduplicación en horas
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id FROM autonomous_decisions
                WHERE action_type = ?
                  AND decision IN ('alert_sent', 'dry_run_alert')
                  AND datetime(created_at, ? || ' hours') >= datetime('now')
                LIMIT 1
                """,
                (action_type, f"+{hours}"),
            ).fetchone()
            return row is not None

    # ------------------------------------------------------------------ /Fase 3A

    # ------------------------------------------------------------------ /Fase 2

    def get_pending_autonomous_decisions(self, days: int = 7) -> list:
        """
        Retorna decisiones propuestas que aún no tienen respuesta (ni aprobadas, ni rechazadas, ni pospuestas).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM autonomous_decisions
                WHERE decision = 'proposed'
                  AND approved_at IS NULL
                  AND rejected_at IS NULL
                  AND postponed_at IS NULL
                  AND created_at >= datetime('now', ? || ' days')
                ORDER BY created_at DESC
            """, (f"-{days}",)).fetchall()
            return [dict(r) for r in rows]

    def get_autonomous_decisions_log(self, days: int = 30) -> list:
        """Retorna historial completo de decisiones autónomas."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM autonomous_decisions
                WHERE created_at >= datetime('now', ? || ' days')
                ORDER BY created_at DESC
            """, (f"-{days}",)).fetchall()
            return [dict(r) for r in rows]

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


# ── Memoria de acciones recientes para contexto de Haiku ──────────────────────

_BUDGET_ACTION_TYPES = (
    "budget_auto_executed",
    "budget_scale_auto_executed",
    "ai_budget_decision",
    "budget_action",
)


def get_recent_actions_with_outcomes(days: int = 2) -> list:
    """
    Retorna acciones de presupuesto ejecutadas en las últimas N días.
    Usado para dar contexto de memoria a Haiku antes de cada decisión.

    Args:
        days: Ventana de tiempo en días (default 2 = últimas 48h).

    Returns:
        Lista de hasta 10 dicts con:
        {action_type, campaign_name, keyword, evidence, created_at, decision}
        Si falla la consulta: lista vacía (nunca lanza excepción).
    """
    try:
        db_path = get_db_path()
        placeholders = ",".join("?" * len(_BUDGET_ACTION_TYPES))
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT action_type, campaign_name, keyword,
                       evidence_json, created_at, decision
                FROM autonomous_decisions
                WHERE action_type IN ({placeholders})
                  AND decision IN ('auto_executed', 'approved', 'executed')
                  AND created_at >= datetime('now', ? || ' days')
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (*_BUDGET_ACTION_TYPES, f"-{days}"),
            ).fetchall()

        result = []
        for row in rows:
            evidence: dict = {}
            if row["evidence_json"]:
                try:
                    evidence = json.loads(row["evidence_json"])
                except Exception:
                    pass
            result.append({
                "action_type":   row["action_type"],
                "campaign_name": row["campaign_name"] or "—",
                "keyword":       row["keyword"],
                "evidence":      evidence,
                "created_at":    row["created_at"],
                "decision":      row["decision"],
            })
        return result

    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).warning(
            "get_recent_actions_with_outcomes: error consultando SQLite — %s", exc
        )
        return []
