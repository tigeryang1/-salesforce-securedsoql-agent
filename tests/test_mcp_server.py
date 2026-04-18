import asyncio
import json

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from app.mcp_server import (
    approve_account_plan,
    get_agent_state,
    list_draft_sessions,
    read_draft_session,
    reset_agent,
    run_langgraph_agent,
    salesforce_query_guided,
    account_plan_guided,
    service,
)


def test_run_langgraph_agent_tool_supports_multi_turn_session() -> None:
    first = asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="mcp-1",
        )
    )
    second = asyncio.run(
        run_langgraph_agent(
            prompt="Main strategy is upper funnel growth",
            session_id="mcp-1",
            account_plan_data={"Annual_Pinterest_Goals_Strategy__c": "Upper funnel growth"},
        )
    )

    assert first["status"] == "needs_input"
    assert second["data"]["account_plan_data"]["Plan_Year__c"] == "2026"
    assert second["data"]["account_plan_data"]["Annual_Pinterest_Goals_Strategy__c"] == "Upper funnel growth"


def test_get_and_reset_agent_state_tools() -> None:
    asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="mcp-2",
        )
    )
    state = asyncio.run(get_agent_state("mcp-2"))
    assert state["account_plan_data"] is not None
    assert state["session_config"] is not None

    reset = asyncio.run(reset_agent("mcp-2"))
    assert reset["reset"] is True
    cleared = asyncio.run(get_agent_state("mcp-2"))
    assert cleared["account_plan_data"] is None


def test_approve_account_plan_tool_uploads_after_drafting() -> None:
    asyncio.run(
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
        )
    )
    assert result["status"] == "uploaded"
    assert result["data"]["upload_record_id"] == "a01000000000000AAA"

    cleared = asyncio.run(get_agent_state("mcp-3"))
    assert cleared["account_plan_data"] is None


def test_approve_account_plan_keeps_state_if_not_uploaded() -> None:
    service._draft_store["mcp-4"] = {"AccountPlan__c": "001000000000000AAA"}  # type: ignore[attr-defined]
    service._session_config_store["mcp-4"] = {  # type: ignore[attr-defined]
        "use_demo_adapter": True,
        "mcp_url": None,
        "session_token": None,
    }

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
        )
    )
    service.approve = original_approve  # type: ignore[method-assign]
    assert result["status"] == "needs_input"
    persisted = asyncio.run(get_agent_state("mcp-4"))
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

    assert "sessions" in data
    assert "total_count" in data
    assert data["total_count"] >= 2

    session_ids = [s["session_id"] for s in data["sessions"]]
    assert "resource-1" in session_ids
    assert "resource-2" in session_ids

    # Find resource-1 and check it has draft
    resource_1 = next(s for s in data["sessions"] if s["session_id"] == "resource-1")
    assert resource_1["has_draft"] is True
    assert resource_1["last_intent"] == "upload_account_plan"


def test_read_draft_session_resource_returns_full_state() -> None:
    asyncio.run(
        run_langgraph_agent(
            prompt="Help me prepare a 2026 account plan for Nike",
            session_id="resource-3",
        )
    )

    result = asyncio.run(read_draft_session("resource-3"))
    data = json.loads(result)

    assert data["session_id"] == "resource-3"
    assert data["account_plan_data"] is not None
    assert data["account_plan_data"]["Plan_Year__c"] == "2026"
    assert data["last_state"] is not None
    assert data["session_config"] is not None


def test_read_draft_session_resource_for_nonexistent_session() -> None:
    result = asyncio.run(read_draft_session("nonexistent-session"))
    data = json.loads(result)

    assert data["session_id"] == "nonexistent-session"
    assert data["account_plan_data"] is None
    assert data["last_state"] is None


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
