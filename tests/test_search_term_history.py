import sys, os, re, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import engine.search_term_history as h
from engine.search_term_classifier import classify_search_term

TODAY = "2026-05-22"


@pytest.fixture(autouse=True)
def _no_gcs(monkeypatch):
    """Aísla los tests de GCS (sin red ni credenciales)."""
    monkeypatch.setattr(h, "download_from_gcs", lambda: False)
    monkeypatch.setattr(h, "upload_to_gcs", lambda: False)


def _term(query, classification="rojo", cost=1.0, suggested_negative="x",
          match="PHRASE", campaign="Thai Mérida - Local", campaign_id="111", conv=0.0):
    return {
        "query": query, "classification": classification, "confidence": "alta",
        "false_positive_risk": "bajo", "suggested_negative": suggested_negative,
        "suggested_match_type": match, "cost": cost, "conversions": conv,
        "clicks": 1, "impressions": 10, "campaign_id": campaign_id, "campaign_name": campaign,
    }


def _db(tmp_path):
    return str(tmp_path / "hist.db")


def _days_before(n):
    from datetime import datetime, timedelta
    return (datetime.strptime(TODAY, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")


# ── AJUSTE A: fecha Mérida ────────────────────────────────────────────────────
def test_merida_date_format():
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", h._merida_today())


# ── dedup / INSERT OR IGNORE ──────────────────────────────────────────────────
def test_compensatoria_no_duplica(tmp_path):
    db = _db(tmp_path)
    r1 = h.snapshot_terms([_term("querreke")], snapshot_date=TODAY, db_path=db)
    r2 = h.snapshot_terms([_term("querreke")], snapshot_date=TODAY, db_path=db)
    assert r1["inserted"] == 1
    assert r2["inserted"] == 0 and r2["ignored"] == 1
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM search_term_snapshots").fetchone()[0] == 1


def test_insert_or_ignore_conserva_primera(tmp_path):
    db = _db(tmp_path)
    h.snapshot_terms([_term("querreke", cost=1.0)], snapshot_date=TODAY, db_path=db)
    h.snapshot_terms([_term("querreke", cost=99.0)], snapshot_date=TODAY, db_path=db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT cost FROM search_term_snapshots").fetchone()[0] == 1.0


# ── AJUSTE C / storage vacío ──────────────────────────────────────────────────
def test_db_vacio_no_crashea(tmp_path):
    db = _db(tmp_path)
    h.snapshot_terms([_term("x")], snapshot_date=TODAY, db_path=db)  # crea schema
    # query_norms vacío -> {} sin SQL inválido
    assert h.aggregate_windows([], db_path=db, today=TODAY) == {}
    # DB sin filas relevantes
    assert h.accumulated_reds(db_path=str(tmp_path / "nope.db"), today=TODAY) == []


def test_aggregate_empty_norms_no_sql_error(tmp_path):
    db = _db(tmp_path)
    h.snapshot_terms([_term("querreke")], snapshot_date=TODAY, db_path=db)
    assert h.aggregate_windows([], db_path=db, today=TODAY) == {}


# ── AJUSTE B: DB corrupto no sube a GCS ───────────────────────────────────────
def test_db_corrupto_no_sube_gcs(tmp_path, monkeypatch):
    db = str(tmp_path / "corrupt.db")
    with open(db, "wb") as f:
        f.write(b"esto no es una base de datos sqlite")
    called = {"upload": False}
    monkeypatch.setattr(h, "upload_to_gcs", lambda: called.__setitem__("upload", True) or True)
    res = h.snapshot_terms([_term("querreke")], snapshot_date=TODAY, db_path=db)
    assert res["skipped_reason"] == "db_invalid"
    assert res["gcs_synced"] is False
    assert called["upload"] is False  # NO intentó subir


# ── anti-falso-positivo ───────────────────────────────────────────────────────
def test_blanco_recurrente_no_sube_a_rojo(tmp_path):
    db = _db(tmp_path)
    for n in range(10):
        h.snapshot_terms([_term("comida economica", classification="blanco", suggested_negative=None)],
                         snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY)
    assert all(a["query"] != "comida economica" for a in accs)


def test_amarillo_recurrente_no_en_accumulated(tmp_path):
    db = _db(tmp_path)
    for n in range(10):
        h.snapshot_terms([_term("comida asiatica", classification="amarillo", suggested_negative=None)],
                         snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY)
    assert all(a["query"] != "comida asiatica" for a in accs)


def test_curry_recurrente_sin_negativo(tmp_path):
    db = _db(tmp_path)
    c = classify_search_term("curry")
    assert c["classification"] == "amarillo" and c["suggested_negative"] is None
    for n in range(8):
        t = _term("curry", classification=c["classification"],
                  suggested_negative=c["suggested_negative"], match=c["suggested_match_type"])
        h.snapshot_terms([t], snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY)
    assert all(a["query"] != "curry" for a in accs)  # amarillo nunca entra a accumulated_reds


# ── acumulación de rojos ──────────────────────────────────────────────────────
def test_rojo_bajo_gasto_3_dias_en_accumulated(tmp_path):
    db = _db(tmp_path)
    for n in (0, 1, 2):  # 3 días distintos, $1 c/u
        h.snapshot_terms([_term("receta pad thai", classification="rojo", cost=1.0,
                                 suggested_negative="receta", match="PHRASE")],
                         snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY)
    hit = [a for a in accs if a["query"] == "receta pad thai"]
    assert len(hit) == 1
    assert hit[0]["distinct_days_30d"] == 3
    assert hit[0]["cost_30d"] == 3.0


def test_rojo_fuera_top100_aparece_por_historico(tmp_path):
    db = _db(tmp_path)
    for n in (0, 1, 2):
        h.snapshot_terms([_term("hacienda teya", classification="rojo", cost=0.5,
                                 suggested_negative="hacienda teya", match="EXACT")],
                         snapshot_date=_days_before(n), db_path=db)
    # today_top100_norms NO contiene el término (estuvo fuera del top-100 del día)
    accs = h.accumulated_reds(db_path=db, today=TODAY, today_top100_norms=["otra cosa"])
    hit = [a for a in accs if a["query"] == "hacienda teya"]
    assert len(hit) == 1
    assert hit[0]["in_today_top100"] is False
    assert hit[0]["suggested_match_type"] == "EXACT"


def test_window_aggregation(tmp_path):
    db = _db(tmp_path)
    h.snapshot_terms([_term("receta", cost=10.0)], snapshot_date=_days_before(0), db_path=db)   # 7d/30d/90d
    h.snapshot_terms([_term("receta", cost=20.0)], snapshot_date=_days_before(10), db_path=db)  # 30d/90d
    h.snapshot_terms([_term("receta", cost=40.0)], snapshot_date=_days_before(60), db_path=db)  # 90d
    agg = h.aggregate_windows(["receta"], db_path=db, today=TODAY)["receta"]
    assert agg["cost_7d"] == 10.0
    assert agg["cost_30d"] == 30.0
    assert agg["cost_90d"] == 70.0
    assert agg["distinct_days_30d"] == 2


def test_prune_120_dias(tmp_path):
    db = _db(tmp_path)
    h.snapshot_terms([_term("viejo")], snapshot_date=_days_before(200), db_path=db)
    h.snapshot_terms([_term("nuevo")], snapshot_date=_days_before(1), db_path=db)
    conn = sqlite3.connect(db)
    rows = [r[0] for r in conn.execute("SELECT query_raw FROM search_term_snapshots").fetchall()]
    assert "viejo" not in rows and "nuevo" in rows  # 'viejo' (200d) podado por retención 120


# ── invariantes duros ─────────────────────────────────────────────────────────
def test_accumulated_invariants(tmp_path):
    db = _db(tmp_path)
    for n in range(4):
        h.snapshot_terms([_term("receta de pad thai casero", classification="rojo", cost=5.0,
                                 suggested_negative="receta", match="BROAD")],  # simula match malo
                         snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY)
    assert len(accs) >= 1
    for a in accs:
        assert a["auto_apply"] is False
        assert a["suggested_match_type"] != "BROAD"   # normalizado a PHRASE
        assert a["classification"] == "rojo"
        assert "top_campaign_name" in a and "campaign_names" in a


def test_accumulated_max_rows(tmp_path):
    db = _db(tmp_path)
    for i in range(20):
        for n in (0, 1, 2):
            h.snapshot_terms([_term(f"receta variante {i}", classification="rojo", cost=2.0,
                                     suggested_negative="receta", match="PHRASE")],
                             snapshot_date=_days_before(n), db_path=db)
    accs = h.accumulated_reds(db_path=db, today=TODAY, limit=10)
    assert len(accs) <= 10
