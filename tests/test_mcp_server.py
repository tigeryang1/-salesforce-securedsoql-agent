import asyncio

from app.mcp_server import get_agent_state, reset_agent, run_langgraph_agent, service


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
    state = get_agent_state("mcp-2")
    assert state["account_plan_data"] is not None

    reset = reset_agent("mcp-2")
    assert reset["reset"] is True
    cleared = get_agent_state("mcp-2")
    assert cleared["account_plan_data"] is None
