import asyncio

from app.agent_service import AgentSessionService, merge_account_plan_draft
from app.config import Settings


def build_service() -> AgentSessionService:
    return AgentSessionService(Settings(agent_model="", agent_api_token="test", host="127.0.0.1", port=8081))


def test_agent_service_merges_partial_draft_state() -> None:
    service = build_service()

    first = asyncio.run(
        service.run(
            user_input="Help me prepare a 2026 account plan for Nike",
            session_id="nike-1",
            use_demo_adapter=True,
        )
    )
    second = asyncio.run(
        service.run(
            user_input="The strategy is to grow consideration",
            session_id="nike-1",
            account_plan_data={"Annual_Pinterest_Goals_Strategy__c": "Grow consideration"},
            use_demo_adapter=True,
        )
    )

    assert first["status"] == "needs_input"
    assert second["account_plan_data"]["Plan_Year__c"] == "2026"
    assert second["account_plan_data"]["Annual_Pinterest_Goals_Strategy__c"] == "Grow consideration"
    state = service.get_state("nike-1")
    assert state["account_plan_data"]["Annual_Pinterest_Goals_Strategy__c"] == "Grow consideration"


def test_agent_service_reset_clears_session() -> None:
    service = build_service()
    asyncio.run(
        service.run(
            user_input="Help me prepare a 2026 account plan for Nike",
            session_id="nike-2",
            use_demo_adapter=True,
        )
    )
    reset = service.reset("nike-2")
    assert reset["reset"] is True
    assert service.get_state("nike-2")["account_plan_data"] is None


def test_merge_account_plan_draft_helper() -> None:
    merged = merge_account_plan_draft(
        {"Plan_Year__c": "2026"},
        {"Annual_Pinterest_Goals_Strategy__c": "Grow consideration"},
    )
    assert merged == {
        "Plan_Year__c": "2026",
        "Annual_Pinterest_Goals_Strategy__c": "Grow consideration",
    }
