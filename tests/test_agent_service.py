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
    assert service.get_state("nike-2")["session_config"] is None


def test_merge_account_plan_draft_helper() -> None:
    merged = merge_account_plan_draft(
        {"Plan_Year__c": "2026"},
        {"Annual_Pinterest_Goals_Strategy__c": "Grow consideration"},
    )
    assert merged == {
        "Plan_Year__c": "2026",
        "Annual_Pinterest_Goals_Strategy__c": "Grow consideration",
    }


def test_approve_does_not_clear_draft_when_upload_does_not_happen() -> None:
    service = build_service()
    service._draft_store["nike-3"] = {"AccountPlan__c": "001000000000000AAA"}  # type: ignore[attr-defined]
    service._session_config_store["nike-3"] = {  # type: ignore[attr-defined]
        "use_demo_adapter": True,
        "mcp_url": None,
        "session_token": None,
    }
    service._last_state_store["nike-3"] = {"status": "needs_input"}  # type: ignore[attr-defined]

    async def fake_run(**kwargs):
        return {
            "status": "needs_input",
            "intent": "upload_account_plan",
            "account_plan_data": {"AccountPlan__c": "001000000000000AAA"},
            "final_response": "still incomplete",
        }

    service.run = fake_run  # type: ignore[method-assign]
    state = asyncio.run(
        service.approve(
            user_input="Approve and upload the account plan",
            session_id="nike-3",
            account_plan_data={"AccountPlan__c": "001000000000000AAA"},
            use_demo_adapter=True,
        )
    )

    assert state["status"] == "needs_input"
    persisted = service.get_state("nike-3")
    assert persisted["account_plan_data"] is not None
    assert persisted["session_config"]["use_demo_adapter"] is True


def test_service_reuses_live_session_config_on_approve() -> None:
    service = build_service()
    captured: list[dict[str, Any]] = []

    async def fake_build_graph(*, use_demo_adapter: bool, mcp_url: str | None, session_token: str | None):
        captured.append(
            {
                "use_demo_adapter": use_demo_adapter,
                "mcp_url": mcp_url,
                "session_token": session_token,
            }
        )

        class FakeGraph:
            async def ainvoke(self, payload):
                return {
                    "intent": "upload_account_plan",
                    "status": "needs_input",
                    "account_plan_data": payload.get("account_plan_data") or {},
                    "final_response": "stub",
                }

        return FakeGraph()

    service._build_graph = fake_build_graph  # type: ignore[method-assign]

    asyncio.run(
        service.run(
            user_input="Start live session",
            session_id="nike-live",
            account_plan_data={"AccountPlan__c": "001000000000000AAA"},
            use_demo_adapter=False,
            mcp_url="http://127.0.0.1:9000/mcp",
            session_token="tok-live",
        )
    )
    asyncio.run(
        service.approve(
            user_input="Approve now",
            session_id="nike-live",
            account_plan_data={"Plan_Year__c": "2026"},
        )
    )

    assert captured[0]["use_demo_adapter"] is False
    assert captured[1]["use_demo_adapter"] is False
    assert captured[1]["mcp_url"] == "http://127.0.0.1:9000/mcp"
    assert captured[1]["session_token"] == "tok-live"
