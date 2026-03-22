import sqlite3
import os
import sys
import json
from unittest.mock import MagicMock

sys.path.insert(0, ".")

TEST_DB = "test_thai_thai.db"


def setup_test_db():
    conn = sqlite3.connect(TEST_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT,
            details_before TEXT,
            details_after TEXT,
            status TEXT NOT NULL,
            google_ads_response TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── TASK 3 ──────────────────────────────────────────────────────────────────

def test_log_agent_action_success():
    setup_test_db()
    from engine.ads_client import log_agent_action
    log_agent_action(
        action_type="rename_campaign",
        target="Thai Merida",
        details_before={"name": "Thai Merida"},
        details_after={"name": "Thai Merida - Local"},
        status="success",
        google_ads_response={"resource_name": "customers/4021070209/campaigns/22612348265"},
        db_path=TEST_DB
    )
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT * FROM agent_actions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    # Column order: id(0), timestamp(1), action_type(2), target(3),
    #               details_before(4), details_after(5), status(6), google_ads_response(7)
    assert row[2] == "rename_campaign"  # action_type
    assert row[6] == "success"          # status
    os.remove(TEST_DB)


# ── TASK 4 ──────────────────────────────────────────────────────────────────

def test_update_campaign_name_calls_mutate():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()
    mock_service.mutate_campaigns.return_value = MagicMock(
        results=[MagicMock(resource_name="customers/123/campaigns/456")]
    )

    from engine.ads_client import update_campaign_name
    result = update_campaign_name(mock_client, "4021070209", "22612348265", "Thai Merida - Local")
    assert result["status"] == "success"
    mock_service.mutate_campaigns.assert_called_once()


def test_update_campaign_budget_calls_mutate():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()
    mock_service.mutate_campaign_budgets.return_value = MagicMock(
        results=[MagicMock(resource_name="customers/123/campaignBudgets/789")]
    )

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123", 50_000_000
    )
    assert result["status"] == "success"
    mock_service.mutate_campaign_budgets.assert_called_once()


# ── TASK 6 ──────────────────────────────────────────────────────────────────

def test_disable_protected_conversion_rejected():
    from engine.ads_client import disable_conversion_action

    mock_client = MagicMock()
    result = disable_conversion_action(mock_client, "4021070209", "999", "reserva_completada")
    assert result["status"] == "rejected"
    mock_client.get_service.assert_not_called()


def test_disable_unprotected_conversion_calls_api():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    mock_client.get_type.return_value = MagicMock()
    mock_service.mutate_conversion_actions.return_value = MagicMock(results=[MagicMock()])

    from engine.ads_client import disable_conversion_action
    result = disable_conversion_action(mock_client, "4021070209", "123", "some_other_conversion")
    assert result["status"] == "success"
    mock_service.mutate_conversion_actions.assert_called_once()
