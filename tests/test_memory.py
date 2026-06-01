from __future__ import annotations

import sqlite3

import engine.memory as memory_module
from engine.memory import MemorySystem, get_recent_actions_with_outcomes


def _memory(tmp_path) -> MemorySystem:
    return MemorySystem(db_path=str(tmp_path / "memory.db"))


def _decision(memory: MemorySystem, *, keyword="pad thai", campaign_id="123", executed=False) -> int:
    return memory.record_autonomous_decision(
        action_type="negative",
        risk_level=2,
        urgency="normal",
        decision="proposed",
        campaign_id=campaign_id,
        campaign_name="Thai Merida",
        keyword=keyword,
        evidence={"reason": "test"},
        executed=executed,
    )


def test_sweep_expired_proposals_marks_only_old_pending(tmp_path, monkeypatch):
    monkeypatch.setattr("config.agent_config.PROPOSAL_EXPIRY_HOURS", 24)
    memory = _memory(tmp_path)
    old_id = _decision(memory, keyword="old")
    fresh_id = _decision(memory, keyword="fresh")
    with sqlite3.connect(memory.db_path) as conn:
        conn.execute(
            "UPDATE autonomous_decisions SET created_at = datetime('now', '-25 hours') WHERE id = ?",
            (old_id,),
        )
        conn.execute(
            "UPDATE autonomous_decisions SET created_at = datetime('now', '-1 hours') WHERE id = ?",
            (fresh_id,),
        )

    assert memory.sweep_expired_proposals() == 1

    with sqlite3.connect(memory.db_path) as conn:
        old_row = conn.execute(
            "SELECT postponed_at FROM autonomous_decisions WHERE id = ?",
            (old_id,),
        ).fetchone()
        fresh_row = conn.execute(
            "SELECT postponed_at FROM autonomous_decisions WHERE id = ?",
            (fresh_id,),
        ).fetchone()
    assert old_row[0] is not None
    assert fresh_row[0] is None


def test_has_pending_proposal_respects_expiry_window(tmp_path, monkeypatch):
    monkeypatch.setattr("config.agent_config.PROPOSAL_EXPIRY_HOURS", 24)
    memory = _memory(tmp_path)
    _decision(memory, keyword="active", campaign_id="123")
    expired_id = _decision(memory, keyword="expired", campaign_id="123")
    with sqlite3.connect(memory.db_path) as conn:
        conn.execute(
            "UPDATE autonomous_decisions SET created_at = datetime('now', '-25 hours') WHERE id = ?",
            (expired_id,),
        )

    assert memory.has_pending_proposal("active", "123") is True
    assert memory.has_pending_proposal("expired", "123") is False


def test_mark_proposals_sent_updates_only_given_ids_and_casts_to_int(tmp_path):
    memory = _memory(tmp_path)
    first_id = _decision(memory, keyword="first")
    second_id = _decision(memory, keyword="second")
    third_id = _decision(memory, keyword="third")

    memory.mark_proposals_sent([str(first_id), second_id])

    with sqlite3.connect(memory.db_path) as conn:
        rows = conn.execute(
            "SELECT id, proposal_sent FROM autonomous_decisions ORDER BY id"
        ).fetchall()
    assert rows == [(first_id, 1), (second_id, 1), (third_id, 0)]


def test_mark_proposals_sent_empty_list_does_not_execute_sql(tmp_path, monkeypatch):
    memory = _memory(tmp_path)
    calls = []

    class GuardConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            calls.append("execute")
            raise AssertionError("empty mark_proposals_sent must not execute SQL")

    monkeypatch.setattr(memory_module.sqlite3, "connect", lambda _path: GuardConnection())

    memory.mark_proposals_sent([])

    assert calls == []


def test_get_recent_actions_with_outcomes_accepts_numeric_string_days(tmp_path, monkeypatch):
    memory = _memory(tmp_path)
    monkeypatch.setattr(memory_module, "get_db_path", lambda: memory.db_path)
    decision_id = memory.record_autonomous_decision(
        action_type="budget_action",
        risk_level=2,
        urgency="normal",
        decision="executed",
        campaign_id="123",
        campaign_name="Delivery",
        evidence={"current_budget_mxn": 50.0},
        executed=True,
    )
    with sqlite3.connect(memory.db_path) as conn:
        conn.execute(
            "UPDATE autonomous_decisions SET created_at = datetime('now', '-1 days') WHERE id = ?",
            (decision_id,),
        )

    rows = get_recent_actions_with_outcomes(days="2")

    assert len(rows) == 1
    assert rows[0]["action_type"] == "budget_action"
    assert rows[0]["campaign_name"] == "Delivery"


def test_get_recent_actions_with_outcomes_invalid_days_returns_empty(tmp_path, monkeypatch):
    memory = _memory(tmp_path)
    monkeypatch.setattr(memory_module, "get_db_path", lambda: memory.db_path)

    assert get_recent_actions_with_outcomes(days="not-a-number") == []
