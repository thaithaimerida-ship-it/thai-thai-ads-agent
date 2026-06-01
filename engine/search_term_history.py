"""
Historial de search terms — Fase 2 (acumulación / recurrencia).

NO reclasifica (la clasificación por contenido es Fase 1, congelada en
engine.search_term_classifier). Fase 2 solo persiste snapshots diarios de la
lista COMPLETA de términos ya clasificados y agrega ventanas 7/30/90 días para
re-priorizar rojos recurrentes/acumulados de bajo gasto que no entran al
top-100 diario del reporte.

Reglas duras (heredadas de Fase 1, no se relajan):
  - auto_apply SIEMPRE False (rojo = candidato a revisión, no aplicación).
  - suggested_match_type nunca BROAD.
  - blancos NUNCA suben a rojo; amarillos no sugieren negativo; curry sin negativo.

Almacenamiento: tabla search_term_snapshots en el SQLite del agente
(engine.db_sync.get_db_path), persistido a GCS vía db_sync.upload_to_gcs().

Protección del histórico (AJUSTE B):
  - Antes de escribir se intenta download_from_gcs() (no-op si local ya tiene datos).
  - Si el DB está corrupto (PRAGMA integrity_check != ok) -> aborta y NO sube a GCS.
  - DB fresco/vacío VÁLIDO -> crea schema y continúa (no se considera corrupto).
  - Si terms vacío -> no escribe.
Atomicidad (AJUSTE C): INSERT OR IGNORE + prune en una transacción; upload_to_gcs
después, en try/except (si falla: log y continúa, no rompe el reporte/auditoría).
Fechas (AJUSTE A): snapshot_date y cutoffs se calculan en America/Merida en
Python (NUNCA date('now') de SQLite, que es UTC).
"""
import logging
import sqlite3
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    _MERIDA = ZoneInfo("America/Merida")
except Exception:  # pragma: no cover
    _MERIDA = None

from engine.db_sync import get_db_path, upload_to_gcs, download_from_gcs
from engine.search_term_classifier import _normalize

try:
    from config.agent_config import (
        SEARCH_TERM_HISTORY_RETENTION_DAYS as _RETENTION,
        SEARCH_TERM_ACCUM_MIN_DISTINCT_DAYS_30D as _MIN_DAYS_30D,
        SEARCH_TERM_ACCUM_MIN_DISTINCT_WEEKS_90D as _MIN_WEEKS_90D,
        SEARCH_TERM_ACCUM_MIN_COST_30D as _MIN_COST_30D,
        SEARCH_TERM_ACCUMULATED_MAX_ROWS as _MAX_ROWS,
    )
except Exception:  # fallback defensivo si config no disponible
    _RETENTION, _MIN_DAYS_30D, _MIN_WEEKS_90D, _MIN_COST_30D, _MAX_ROWS = 120, 3, 2, 15.0, 10

logger = logging.getLogger(__name__)

_TABLE = "search_term_snapshots"


# ── Fechas (America/Merida) ───────────────────────────────────────────────────
def _merida_today() -> str:
    """YYYY-MM-DD en America/Merida. NUNCA date('now') de SQLite (UTC)."""
    now = datetime.now(_MERIDA) if _MERIDA else datetime.utcnow()
    return now.strftime("%Y-%m-%d")


def _window_cutoffs(today: str) -> dict:
    """Fechas límite (inclusivas) de las ventanas, calculadas en Python."""
    d = datetime.strptime(today, "%Y-%m-%d")
    return {
        "d7":  (d - timedelta(days=6)).strftime("%Y-%m-%d"),
        "d30": (d - timedelta(days=29)).strftime("%Y-%m-%d"),
        "d90": (d - timedelta(days=89)).strftime("%Y-%m-%d"),
    }


# ── Esquema / validación ──────────────────────────────────────────────────────
def _ensure_schema(conn) -> None:
    # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
    # nosemgrep
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date         TEXT NOT NULL,
            campaign_id           TEXT NOT NULL,
            campaign_name         TEXT,
            query_raw             TEXT NOT NULL,
            query_norm            TEXT NOT NULL,
            classification        TEXT NOT NULL,
            confidence            TEXT,
            false_positive_risk   TEXT,
            suggested_negative    TEXT,
            suggested_match_type  TEXT,
            cost                  REAL DEFAULT 0,
            conversions           REAL DEFAULT 0,
            clicks                INTEGER DEFAULT 0,
            impressions           INTEGER DEFAULT 0,
            created_at            TEXT,
            UNIQUE(snapshot_date, campaign_id, query_norm)
        )
    """)
    # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
    # nosemgrep
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sts_date  ON {_TABLE}(snapshot_date)")
    # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
    # nosemgrep
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sts_norm  ON {_TABLE}(query_norm)")
    # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
    # nosemgrep
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sts_class ON {_TABLE}(classification)")


def _db_is_valid(conn) -> bool:
    """PRAGMA integrity_check. Un DB fresco/vacío es VÁLIDO (no corrupto)."""
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    except Exception:
        return False


def _table_exists(conn) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (_TABLE,)
        ).fetchone()
        return row is not None
    except Exception:
        return False


# ── Escritura (snapshot diario) ───────────────────────────────────────────────
def snapshot_terms(terms, snapshot_date=None, db_path=None, retention_days=None) -> dict:
    """Persiste la lista COMPLETA de términos ya clasificados del día.

    Cada term: dict con query/query_raw, classification, confidence,
    false_positive_risk, suggested_negative, suggested_match_type, cost,
    conversions, clicks, impressions, campaign_id, campaign_name.

    Devuelve {inserted, ignored, pruned, gcs_synced, skipped_reason}.
    """
    res = {"inserted": 0, "ignored": 0, "pruned": 0, "gcs_synced": False, "skipped_reason": None}
    if not terms:
        res["skipped_reason"] = "no_terms"
        return res

    snapshot_date = snapshot_date or _merida_today()
    db_path = db_path or get_db_path()
    retention_days = _RETENTION if retention_days is None else retention_days

    # AJUSTE B: asegurar histórico remoto presente antes de escribir (no-op si local ya tiene datos)
    try:
        download_from_gcs()
    except Exception as e:
        logger.warning("snapshot_terms: download_from_gcs fallo (continuo): %s", e)

    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        res["skipped_reason"] = f"db_open_failed:{e}"
        return res

    try:
        # AJUSTE B: DB corrupto -> abortar, NO subir a GCS (preserva histórico remoto)
        if not _db_is_valid(conn):
            res["skipped_reason"] = "db_invalid"
            logger.error("snapshot_terms: DB inválido (integrity_check) — aborta sin subir a GCS")
            return res

        _ensure_schema(conn)  # DB fresco/vacío válido -> crea schema y continúa (AJUSTE A)
        now_iso = datetime.now(_MERIDA).isoformat() if _MERIDA else datetime.utcnow().isoformat()

        with conn:  # transacción (AJUSTE C)
            for t in terms:
                raw = t.get("query_raw") or t.get("query") or ""
                # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
                # nosemgrep
                cur = conn.execute(
                    f"""INSERT OR IGNORE INTO {_TABLE}
                        (snapshot_date, campaign_id, campaign_name, query_raw, query_norm,
                         classification, confidence, false_positive_risk, suggested_negative,
                         suggested_match_type, cost, conversions, clicks, impressions, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snapshot_date, str(t.get("campaign_id", "")), t.get("campaign_name", ""),
                     raw, _normalize(raw), t.get("classification", "blanco"),
                     t.get("confidence"), t.get("false_positive_risk"), t.get("suggested_negative"),
                     t.get("suggested_match_type"), float(t.get("cost", 0) or 0),
                     float(t.get("conversions", 0) or 0), int(t.get("clicks", 0) or 0),
                     int(t.get("impressions", 0) or 0), now_iso),
                )
                if cur.rowcount == 1:
                    res["inserted"] += 1
                else:
                    res["ignored"] += 1  # dedup: ya existía (date, campaign, query_norm)
            res["pruned"] = prune_old(conn, retention_days, today=snapshot_date)
    except Exception as e:
        res["skipped_reason"] = f"write_failed:{e}"
        logger.error("snapshot_terms: fallo escribiendo (no sube a GCS): %s", e)
        conn.close()
        return res
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # AJUSTE C: upload guard — si falla, log y continúa
    try:
        res["gcs_synced"] = bool(upload_to_gcs())
    except Exception as e:
        logger.warning("snapshot_terms: upload_to_gcs fallo (continuo): %s", e)
    return res


def prune_old(conn, retention_days=None, today=None) -> int:
    """DELETE filas con snapshot_date < today - retention_days (fechas Mérida)."""
    retention_days = _RETENTION if retention_days is None else retention_days
    today = today or _merida_today()
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
    # nosemgrep
    cur = conn.execute(f"DELETE FROM {_TABLE} WHERE snapshot_date < ?", (cutoff,))
    return cur.rowcount or 0


# ── Lectura / agregación ──────────────────────────────────────────────────────
def aggregate_windows(query_norms=None, db_path=None, today=None) -> dict:
    """Agrega ventanas 7/30/90d. Devuelve {query_norm: {...métricas...}}.

    AJUSTE C: si query_norms es lista vacía -> {} (sin SQL IN () inválido).
    Si query_norms es None -> agrega todos los de los últimos 90 días.
    Si el DB no existe/corrupto/sin tabla -> {} (graceful).
    """
    if query_norms is not None and len(query_norms) == 0:
        return {}

    db_path = db_path or get_db_path()
    today = today or _merida_today()
    cut = _window_cutoffs(today)

    try:
        conn = sqlite3.connect(db_path)
    except Exception:
        return {}
    try:
        if not _table_exists(conn):
            return {}
        # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
        # nosemgrep
        sql = f"""
            SELECT query_norm,
                   SUM(CASE WHEN snapshot_date >= ? THEN cost ELSE 0 END) AS cost_7d,
                   SUM(CASE WHEN snapshot_date >= ? THEN cost ELSE 0 END) AS cost_30d,
                   SUM(cost) AS cost_90d,
                   COUNT(DISTINCT CASE WHEN snapshot_date >= ? THEN snapshot_date END) AS distinct_days_30d,
                   COUNT(DISTINCT strftime('%Y-%W', snapshot_date)) AS distinct_weeks_90d,
                   MIN(snapshot_date) AS first_seen, MAX(snapshot_date) AS last_seen
              FROM {_TABLE}
             WHERE snapshot_date >= ?
        """
        params = [cut["d7"], cut["d30"], cut["d30"], cut["d90"]]
        if query_norms is not None:
            placeholders = ",".join("?" for _ in query_norms)
            sql += f" AND query_norm IN ({placeholders})"
            params.extend(query_norms)
        sql += " GROUP BY query_norm"
        out = {}
        # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
        # nosemgrep
        for r in conn.execute(sql, params).fetchall():
            out[r[0]] = {
                "cost_7d": round(r[1] or 0, 2), "cost_30d": round(r[2] or 0, 2),
                "cost_90d": round(r[3] or 0, 2), "distinct_days_30d": r[4] or 0,
                "distinct_weeks_90d": r[5] or 0, "first_seen": r[6], "last_seen": r[7],
            }
        return out
    except Exception as e:
        logger.warning("aggregate_windows: %s", e)
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def accumulated_reds(db_path=None, limit=None, today=None, today_top100_norms=None) -> list:
    """Rojos recurrentes/acumulados (regla de prioridad). Top `limit` por cost_30d.

    REGLA: classification=='rojo' Y (distinct_days_30d >= MIN_DAYS
           OR distinct_weeks_90d >= MIN_WEEKS OR cost_30d >= MIN_COST).
    Cada item: auto_apply False, suggested_match_type nunca BROAD, in_today_top100,
    top_campaign_name + campaign_names, reason_accumulated (armado aquí, AJUSTE 2).
    """
    limit = _MAX_ROWS if limit is None else limit
    db_path = db_path or get_db_path()
    today = today or _merida_today()
    cut = _window_cutoffs(today)
    today_top100_norms = set(today_top100_norms or [])

    try:
        conn = sqlite3.connect(db_path)
    except Exception:
        return []
    try:
        if not _table_exists(conn):
            return []
        # Agrega solo filas rojas; toma el suggested_negative/match más reciente por query.
        # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
        # nosemgrep
        sql = f"""
            SELECT query_norm,
                   SUM(CASE WHEN snapshot_date >= ? THEN cost ELSE 0 END) AS cost_7d,
                   SUM(CASE WHEN snapshot_date >= ? THEN cost ELSE 0 END) AS cost_30d,
                   SUM(cost) AS cost_90d,
                   COUNT(DISTINCT CASE WHEN snapshot_date >= ? THEN snapshot_date END) AS distinct_days_30d,
                   COUNT(DISTINCT strftime('%Y-%W', snapshot_date)) AS distinct_weeks_90d,
                   MIN(snapshot_date) AS first_seen, MAX(snapshot_date) AS last_seen,
                   MAX(query_raw) AS query_raw
              FROM {_TABLE}
             WHERE classification = 'rojo' AND snapshot_date >= ?
             GROUP BY query_norm
        """
        params = [cut["d7"], cut["d30"], cut["d30"], cut["d90"]]
        # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
        # nosemgrep
        rows = conn.execute(sql, params).fetchall()

        items = []
        for r in rows:
            qn, c7, c30, c90, dd30, dw90, fseen, lseen, qraw = r
            c7, c30, c90, dd30, dw90 = round(c7 or 0, 2), round(c30 or 0, 2), round(c90 or 0, 2), dd30 or 0, dw90 or 0
            if not (dd30 >= _MIN_DAYS_30D or dw90 >= _MIN_WEEKS_90D or c30 >= _MIN_COST_30D):
                continue
            # detalle más reciente (suggested_negative/match) + campañas
            # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
            # nosemgrep
            det = conn.execute(
                f"""SELECT suggested_negative, suggested_match_type, confidence, false_positive_risk
                      FROM {_TABLE} WHERE query_norm=? AND classification='rojo'
                     ORDER BY snapshot_date DESC LIMIT 1""", (qn,)).fetchone()
            sugg_neg, sugg_match, conf, fp = (det or (None, None, None, None))
            if sugg_match == "BROAD":  # invariante duro
                sugg_match = "PHRASE"
            # nosemgrep: _TABLE is a hardcoded internal identifier; all user-controlled values are parameterized.
            # nosemgrep
            camps = conn.execute(
                f"""SELECT campaign_name, SUM(cost) c FROM {_TABLE}
                     WHERE query_norm=? AND classification='rojo' AND snapshot_date >= ?
                     GROUP BY campaign_name ORDER BY c DESC""", (qn, cut["d90"])).fetchall()
            campaign_names = [c[0] for c in camps if c[0]]
            top_campaign = campaign_names[0] if campaign_names else None

            reason = (f"{dd30} días en 30d · ${c30:.2f} acumulado · {dw90} semanas")
            items.append({
                "query": qraw or qn,
                "classification": "rojo",
                "confidence": conf,
                "false_positive_risk": fp,
                "suggested_negative": sugg_neg,
                "suggested_match_type": sugg_match,   # nunca BROAD
                "cost_7d": c7, "cost_30d": c30, "cost_90d": c90,
                "distinct_days_30d": dd30, "distinct_weeks_90d": dw90,
                "recurrent": dw90 >= _MIN_WEEKS_90D,
                "reason_accumulated": reason,
                "first_seen": fseen, "last_seen": lseen,
                "top_campaign_name": top_campaign,
                "campaign_names": campaign_names,
                "in_today_top100": qn in today_top100_norms,
                "auto_apply": False,    # invariante duro
            })
        items.sort(key=lambda x: x["cost_30d"], reverse=True)
        return items[:limit]
    except Exception as e:
        logger.warning("accumulated_reds: %s", e)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
