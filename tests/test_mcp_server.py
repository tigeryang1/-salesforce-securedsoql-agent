import asyncio
import json

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from app.mcp_server import (
    account_plan_guided,
    approve_account_plan,
    get_agent_state,
    list_draft_sessions,
    read_draft_session_legacy,
    read_draft_session,
    reset_agent,
    run_langgraph_agent,
    salesforce_query_guided,
    service,
)


def test_run_langgraph_agent_tool_supports_multi_turn_session() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="mcp-1",
        )
    )
    access_key = first["session_access_key"]
    second = asyncio.run(
        run_langgraph_agent(
            prompt="Main strategy is upper funnel growth",
            session_id="mcp-1",
            account_plan_data={"Annual_Pinterest_Goals_Strategy__c": "Upper funnel growth"},
            session_access_key=access_key,
        )
    )

    assert first["status"] == "needs_input"
    assert second["data"]["account_plan_data"]["Plan_Year__c"] == "2026"
    assert second["data"]["account_plan_data"]["Annual_Pinterest_Goals_Strategy__c"] == "Upper funnel growth"


def test_get_and_reset_agent_state_tools() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="mcp-2",
        )
    )
    access_key = first["session_access_key"]
    state = asyncio.run(get_agent_state("mcp-2", access_key))
    assert state["account_plan_data"] is not None
    assert state["session_config"] is not None

    reset = asyncio.run(reset_agent("mcp-2", access_key))
    assert reset["reset"] is True
    cleared = asyncio.run(get_agent_state("mcp-2", access_key))
    assert cleared["account_plan_data"] is None


def test_approve_account_plan_tool_uploads_after_drafting() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="mcp-3",
        )
    )
    result = asyncio.run(
        approve_account_plan(
            session_id="mcp-3",
            account_plan_data={
                "AccountPlan__c": "001000000000000AAA",
                "Plan_Year__c": "2026",
            },
            session_access_key=first["session_access_key"],
        )
    )
    assert result["status"] == "uploaded"
    assert result["data"]["upload_record_id"] == "a01000000000000AAA"

    cleared = asyncio.run(get_agent_state("mcp-3", first["session_access_key"]))
    assert cleared["account_plan_data"] is None


def test_approve_account_plan_keeps_state_if_not_uploaded() -> None:
    service._draft_store["mcp-4"] = {"AccountPlan__c": "001000000000000AAA"}  # type: ignore[attr-defined]
    service._session_config_store["mcp-4"] = {  # type: ignore[attr-defined]
        "use_demo_adapter": True,
        "mcp_url": None,
        "session_token": None,
    }
    service._session_access_store["mcp-4"] = "access-mcp-4"  # type: ignore[attr-defined]

    original_approve = service.approve

    async def fake_approve(**kwargs):
        return {
            "status": "needs_input",
            "intent": "upload_account_plan",
            "account_plan_data": {"AccountPlan__c": "001000000000000AAA"},
            "final_response": "still incomplete",
        }

    service.approve = fake_approve  # type: ignore[method-assign]
    result = asyncio.run(
        approve_account_plan(
            session_id="mcp-4",
            account_plan_data={"AccountPlan__c": "001000000000000AAA"},
            session_access_key="access-mcp-4",
        )
    )
    service.approve = original_approve  # type: ignore[method-assign]
    assert result["status"] == "needs_input"
    persisted = asyncio.run(get_agent_state("mcp-4", "access-mcp-4"))
    assert persisted["account_plan_data"] is not None


# ============================================================================
# Resource Tests
# ============================================================================


def test_list_draft_sessions_resource_shows_active_sessions() -> None:
    asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="resource-1",
        )
    )
    asyncio.run(
        run_langgraph_agent(
            prompt="Show me accounts",
            session_id="resource-2",
        )
    )

    result = asyncio.run(list_draft_sessions())
    data = json.loads(result)

    assert data["enumeration_enabled"] is False
    assert "session_resource_template" in data


def test_read_draft_session_resource_returns_full_state() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="resource-3",
        )
    )

    result = asyncio.run(read_draft_session("resource-3", first["session_access_key"]))
    data = json.loads(result)

    assert data["session_id"] == "resource-3"
    assert data["account_plan_data"] is not None
    assert data["account_plan_data"]["Plan_Year__c"] == "2026"
    assert data["last_state"] is not None
    assert data["session_config"] is not None


def test_read_draft_session_resource_for_nonexistent_session() -> None:
    result = asyncio.run(read_draft_session("nonexistent-session", "missing-key"))
    data = json.loads(result)

    assert data["error"] == "No active draft is available for this session."
    assert data["session_id"] == "nonexistent-session"


def test_legacy_session_resource_requires_access_key() -> None:
    result = asyncio.run(read_draft_session_legacy("legacy-session"))
    data = json.loads(result)

    assert "session_access_key is required" in data["error"]


def test_existing_session_access_requires_key() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="protected-1",
        )
    )

    with pytest.raises(Exception):
        asyncio.run(get_agent_state("protected-1", "wrong-key"))

    state = asyncio.run(get_agent_state("protected-1", first["session_access_key"]))
    assert state["account_plan_data"] is not None


# ============================================================================
# Prompt Tests
# ============================================================================


def test_salesforce_query_guided_prompt_generates_guidance() -> None:
    result = asyncio.run(salesforce_query_guided())

    assert "Salesforce Query Guide" in result
    assert "Security Features" in result
    assert "Field filtering" in result
    assert "Natural Language Queries" in result
    assert "run_langgraph_agent" in result


def test_salesforce_query_guided_prompt_with_parameters() -> None:
    result = asyncio.run(
        salesforce_query_guided(
            object_type="Account",
            user_goal="Find high-value accounts",
        )
    )

    assert "You're querying: Account" in result
    assert "Your goal: Find high-value accounts" in result


def test_account_plan_guided_prompt_generates_guidance() -> None:
    result = asyncio.run(account_plan_guided())

    assert "Account Plan Creation Guide" in result
    assert "Executive Summary" in result
    assert "Quarterly Planning" in result
    assert "Revenue Goals" in result
    assert "Progressive Drafting" in result
    assert "What company is this plan for?" in result


def test_account_plan_guided_prompt_with_parameters() -> None:
    result = asyncio.run(
        account_plan_guided(
            account_name="Nike",
            plan_year="2026",
        )
    )

    assert "Creating plan: Nike - 2026" in result
    assert "What information do you have about this account?" in result
