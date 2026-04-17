import asyncio

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from app.mcp_server import approve_account_plan, get_agent_state, reset_agent, run_langgraph_agent, service


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
