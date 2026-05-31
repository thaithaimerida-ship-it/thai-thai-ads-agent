import sqlite3
import os
import sys
import json
from types import SimpleNamespace
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
    budget_operation = MagicMock()
    request = SimpleNamespace(customer_id="", operations=[], validate_only=None)
    mock_client.get_type.side_effect = [budget_operation, request]
    mock_service.mutate_campaign_budgets.return_value = MagicMock(
        results=[MagicMock(resource_name="customers/123/campaignBudgets/789")]
    )

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123", 50_000_000
    )
    assert result["status"] == "success"
    mock_service.mutate_campaign_budgets.assert_called_once()
    kwargs = mock_service.mutate_campaign_budgets.call_args.kwargs
    assert set(kwargs) == {"request"}
    assert kwargs["request"].validate_only is False


def test_update_campaign_budget_validate_only_true_propagates_in_request():
    """validate_only=True debe pasarse dentro del request y reflejarse en el return.

    Este es el modo dry-run del ritual ads-mutation-dry-run: la API valida la
    operación pero NO la aplica. Lo usan routes/presupuestos y el subagente
    budget-mutation-reviewer audita que esté presente antes del apply real.
    """
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    budget_operation = MagicMock()
    request = SimpleNamespace(customer_id="", operations=[], validate_only=None)
    mock_client.get_type.side_effect = [budget_operation, request]
    mock_service.mutate_campaign_budgets.return_value = MagicMock(
        results=[MagicMock(resource_name="customers/123/campaignBudgets/789")]
    )

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123",
        50_000_000, validate_only=True,
    )

    assert result["status"] == "success"
    assert result["validate_only"] is True
    kwargs = mock_service.mutate_campaign_budgets.call_args.kwargs
    assert set(kwargs) == {"request"}
    assert kwargs["request"].customer_id == "4021070209"
    assert kwargs["request"].operations == [budget_operation]
    assert kwargs["request"].validate_only is True


def test_update_campaign_budget_validate_only_empty_results_is_success():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    budget_operation = MagicMock()
    request = SimpleNamespace(customer_id="", operations=[], validate_only=None)
    mock_client.get_type.side_effect = [budget_operation, request]
    mock_service.mutate_campaign_budgets.return_value = MagicMock(results=[])

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123",
        50_000_000, validate_only=True,
    )

    assert result["status"] == "success"
    assert result["validate_only"] is True
    assert result["message"] == "validate_only_ok"
    assert result["resource_name"] is None


def test_update_campaign_budget_real_mutate_empty_results_is_traceable_success():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    budget_operation = MagicMock()
    request = SimpleNamespace(customer_id="", operations=[], validate_only=None)
    mock_client.get_type.side_effect = [budget_operation, request]
    mock_service.mutate_campaign_budgets.return_value = MagicMock(results=[])

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123",
        50_000_000, validate_only=False,
    )

    assert result["status"] == "success"
    assert result["validate_only"] is False
    assert result["message"] == "mutate_ok_no_resource_name"
    assert result["resource_name"] is None


def test_update_campaign_budget_preserves_validate_only_on_exception():
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    budget_operation = MagicMock()
    request = SimpleNamespace(customer_id="", operations=[], validate_only=None)
    mock_client.get_type.side_effect = [budget_operation, request]
    mock_service.mutate_campaign_budgets.side_effect = RuntimeError("boom")

    from engine.ads_client import update_campaign_budget
    result = update_campaign_budget(
        mock_client, "4021070209", "customers/4021070209/campaignBudgets/123",
        50_000_000, validate_only=True,
    )

    assert result["status"] == "error"
    assert result["validate_only"] is True
    assert "boom" in result["message"]


# ── TASK 6 ──────────────────────────────────────────────────────────────────

def test_fetch_campaign_budget_info_returns_campaign_status_and_budget_contract():
    from engine.ads_client import fetch_campaign_budget_info

    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    row = SimpleNamespace(
        campaign=SimpleNamespace(
            id=22839241090,
            name="Thai Mérida - Delivery",
            status=SimpleNamespace(name="ENABLED"),
        ),
        campaign_budget=SimpleNamespace(
            amount_micros=50_000_000,
            resource_name="customers/4021070209/campaignBudgets/999",
            explicitly_shared=False,
        ),
    )
    mock_service.search.return_value = [row]

    result = fetch_campaign_budget_info(mock_client, "4021070209", "22839241090")

    assert result == {
        "campaign_id": 22839241090,
        "campaign_name": "Thai Mérida - Delivery",
        "campaign_status": "ENABLED",
        "budget_resource_name": "customers/4021070209/campaignBudgets/999",
        "current_daily_budget_mxn": 50.0,
        "budget_explicitly_shared": False,
    }
    query = mock_service.search.call_args.kwargs["query"]
    assert "campaign.status" in query
    assert "campaign_budget.explicitly_shared" in query


def test_fetch_campaign_budget_info_returns_shared_budget_flag():
    from engine.ads_client import fetch_campaign_budget_info

    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    row = SimpleNamespace(
        campaign=SimpleNamespace(
            id=22839241090,
            name="Thai Mérida - Delivery",
            status=SimpleNamespace(name="ENABLED"),
        ),
        campaign_budget=SimpleNamespace(
            amount_micros=50_000_000,
            resource_name="customers/4021070209/campaignBudgets/999",
            explicitly_shared=True,
        ),
    )
    mock_service.search.return_value = [row]

    result = fetch_campaign_budget_info(mock_client, "4021070209", "22839241090")

    assert result["campaign_status"] == "ENABLED"
    assert result["budget_explicitly_shared"] is True


def test_disable_protected_conversion_rejected():
    from engine.ads_client import disable_conversion_action

    mock_client = MagicMock()
    result = disable_conversion_action(mock_client, "4021070209", "999", "reserva_completada_directa")
    assert result["status"] == "rejected"
    mock_client.get_service.assert_not_called()


def test_add_negative_keyword_rejects_smart_campaign():
    """Smart Campaigns NO deben aceptar negative keywords via CampaignCriterionService.

    Sin este guard, la mutación se persiste como criterion pero el matching
    algorithm la ignora silenciosamente — fallos invisibles. Ver query GAQL
    sobre Local 22612348265: 245 negativos registrados, comportamiento incierto.
    """
    from engine.ads_client import add_negative_keyword
    mock_client = MagicMock()
    mock_row = MagicMock()
    mock_row.campaign.advertising_channel_type.name = "SMART"
    ga_service = MagicMock()
    ga_service.search.return_value = [mock_row]
    mock_client.get_service.return_value = ga_service

    result = add_negative_keyword(mock_client, "4021070209", "22612348265", "sushi")
    assert result["status"] == "rejected"
    assert result["reason"] == "unsupported_channel_for_negative_keyword"
    assert result["channel"] == "SMART"
    # CRÍTICO: get_type (que devolvería CampaignCriterionOperation) nunca debe
    # llamarse — la guardia debe abortar antes.
    mock_client.get_type.assert_not_called()


def test_add_negative_keyword_allows_search_campaign():
    """SEARCH campaigns sí deben aceptar negative keywords normalmente."""
    from engine.ads_client import add_negative_keyword
    mock_client = MagicMock()

    mock_row = MagicMock()
    mock_row.campaign.advertising_channel_type.name = "SEARCH"

    ga_service_mock = MagicMock()
    ga_service_mock.search.return_value = [mock_row]
    crit_service_mock = MagicMock()
    campaign_service_mock = MagicMock()
    campaign_service_mock.campaign_path.return_value = "customers/4021070209/campaigns/23730364039"

    def get_service_side_effect(name):
        if name == "GoogleAdsService":
            return ga_service_mock
        if name == "CampaignCriterionService":
            return crit_service_mock
        if name == "CampaignService":
            return campaign_service_mock
        return MagicMock()
    mock_client.get_service.side_effect = get_service_side_effect
    mock_client.get_type.return_value = MagicMock()
    mock_client.enums.KeywordMatchTypeEnum.BROAD = MagicMock()

    result = add_negative_keyword(mock_client, "4021070209", "23730364039", "sushi")
    assert result["status"] == "success"
    assert result["keyword"] == "sushi"
    assert result["match_type"] == "BROAD"
    assert result["channel"] == "SEARCH"
    crit_service_mock.mutate_campaign_criteria.assert_called_once()


def test_disable_primary_conversions_rejected():
    """click_pedir_online y click_whatsapp son Primarias del CLAUDE.md (NO TOCAR).

    Sin estos asserts, una regresión silenciosa en PROTECTED_CONVERSIONS dejaría
    al motor LLM y a cualquier endpoint con permiso desactivar conversiones de
    dinero real. Cubre los 2 nombres snake_case con los que estas conversiones
    viven en Google Ads (el check substring case-insensitive no cubre variantes
    con espacios — se documentó la limitación en disable_conversion_action).
    """
    from engine.ads_client import disable_conversion_action
    mock_client = MagicMock()
    for name in ("click_pedir_online", "click_whatsapp"):
        result = disable_conversion_action(mock_client, "4021070209", "999", name)
        assert result["status"] == "rejected", f"'{name}' should be protected"
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


# ── TASK 8 ──────────────────────────────────────────────────────────────────

def test_create_rsa_requires_min_headlines():
    from unittest.mock import MagicMock
    from engine.ads_client import create_rsa
    mock_client = MagicMock()
    result = create_rsa(mock_client, "4021070209", "customers/123/adGroups/456",
                        headlines=["A", "B"], descriptions=["D1", "D2"])
    assert result["status"] == "error"
    assert "mínimo" in result["message"]

def test_create_rsa_requires_min_descriptions():
    from unittest.mock import MagicMock
    from engine.ads_client import create_rsa
    mock_client = MagicMock()
    result = create_rsa(mock_client, "4021070209", "customers/123/adGroups/456",
                        headlines=["A", "B", "C"], descriptions=["D1"])
    assert result["status"] == "error"
    assert "mínimo" in result["message"]


# ── MICRO-FASE match_type ─────────────────────────────────────────────────────
# Justificación (regla de testing del proyecto): add_negative_keyword toca la
# Google Ads API y aplica negativos a campañas reales. El match type determina
# cuánto bloquea cada negativo (EXACT < PHRASE < BROAD), así que un mapeo
# incorrecto puede sobre-bloquear tráfico válido. Tests obligatorios.

def _make_search_client(match_sentinels):
    """Construye un mock client de campaña SEARCH (acepta negativos).

    match_sentinels: dict {"EXACT": obj, "PHRASE": obj, "BROAD": obj} para poder
    afirmar EXACTAMENTE qué miembro del enum se asignó al criterion.
    """
    mock_client = MagicMock()

    mock_row = MagicMock()
    mock_row.campaign.advertising_channel_type.name = "SEARCH"
    ga_service_mock = MagicMock()
    ga_service_mock.search.return_value = [mock_row]
    crit_service_mock = MagicMock()
    campaign_service_mock = MagicMock()
    campaign_service_mock.campaign_path.return_value = "customers/4021070209/campaigns/23730364039"

    def get_service_side_effect(name):
        if name == "GoogleAdsService":
            return ga_service_mock
        if name == "CampaignCriterionService":
            return crit_service_mock
        if name == "CampaignService":
            return campaign_service_mock
        return MagicMock()

    mock_client.get_service.side_effect = get_service_side_effect
    mock_client.get_type.return_value = MagicMock()
    for name, sentinel in match_sentinels.items():
        setattr(mock_client.enums.KeywordMatchTypeEnum, name, sentinel)
    return mock_client, crit_service_mock


def test_add_negative_keyword_exact_aplica_exact():
    """match_type='EXACT' → el criterion recibe el enum EXACT y el return lo refleja."""
    from engine.ads_client import add_negative_keyword
    exact = object()
    mock_client, crit = _make_search_client({"EXACT": exact})
    op = mock_client.get_type.return_value

    result = add_negative_keyword(mock_client, "4021070209", "23730364039",
                                  "querreke", match_type="EXACT")

    assert result["status"] == "success"
    assert result["match_type"] == "EXACT"
    assert op.create.keyword.match_type is exact
    crit.mutate_campaign_criteria.assert_called_once()


def test_add_negative_keyword_phrase_aplica_phrase():
    """match_type='PHRASE' → el criterion recibe el enum PHRASE."""
    from engine.ads_client import add_negative_keyword
    phrase = object()
    mock_client, crit = _make_search_client({"PHRASE": phrase})
    op = mock_client.get_type.return_value

    result = add_negative_keyword(mock_client, "4021070209", "23730364039",
                                  "muay thai", match_type="PHRASE")

    assert result["status"] == "success"
    assert result["match_type"] == "PHRASE"
    assert op.create.keyword.match_type is phrase
    crit.mutate_campaign_criteria.assert_called_once()


def test_add_negative_keyword_match_type_invalido_rechazado():
    """Un match_type fuera de {EXACT,PHRASE,BROAD} se rechaza SIN mutar."""
    from engine.ads_client import add_negative_keyword
    mock_client, crit = _make_search_client({})

    result = add_negative_keyword(mock_client, "4021070209", "23730364039",
                                  "sushi", match_type="FUZZY")

    assert result["status"] == "rejected"
    assert result["reason"] == "invalid_match_type"
    crit.mutate_campaign_criteria.assert_not_called()


def test_add_negative_keyword_default_sigue_broad_retrocompat():
    """Sin match_type (llamadores legacy con 4 args) → default BROAD, sin cambios."""
    from engine.ads_client import add_negative_keyword
    broad = object()
    mock_client, crit = _make_search_client({"BROAD": broad})
    op = mock_client.get_type.return_value

    result = add_negative_keyword(mock_client, "4021070209", "23730364039", "ramen")

    assert result["status"] == "success"
    assert result["match_type"] == "BROAD"
    assert op.create.keyword.match_type is broad
    crit.mutate_campaign_criteria.assert_called_once()
