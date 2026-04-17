from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.agent_service import AgentSessionService, merge_account_plan_draft
from app.config import get_settings


settings = get_settings()
service = AgentSessionService(settings)
mcp = FastMCP(
    name="Salesforce SecuredSOQL LangGraph Agent",
    instructions=(
        "Use this server to run a LangGraph-based Salesforce business agent. "
        "Prefer reusing the same session_id for multi-turn drafting."
    ),
)


@mcp.tool()
async def run_langgraph_agent(
    prompt: str,
    session_id: str,
    context: dict[str, Any] | None = None,
    soql_query: str | None = None,
    sobject_name: str | None = None,
    account_plan_data: dict[str, Any] | None = None,
    approved: bool = False,
    use_demo_adapter: bool = True,
    mcp_url: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    merged_plan_data = merge_account_plan_draft(context, account_plan_data)
    state = await service.run(
        user_input=prompt,
        session_id=session_id,
        soql_query=soql_query,
        sobject_name=sobject_name,
        account_plan_data=merged_plan_data,
        approved=approved,
        use_demo_adapter=use_demo_adapter,
        mcp_url=mcp_url,
        session_token=session_token,
    )
    return {
        "status": state.get("status", "completed"),
        "intent": state.get("intent", "unknown"),
        "message": state.get("final_response", ""),
        "data": state,
    }


@mcp.tool()
async def approve_account_plan(
    session_id: str,
    user_input: str = "Approve and upload the account plan",
    account_plan_data: dict[str, Any] | None = None,
    use_demo_adapter: bool = True,
    mcp_url: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    state = await service.approve(
        user_input=user_input,
        session_id=session_id,
        account_plan_data=account_plan_data,
        use_demo_adapter=use_demo_adapter,
        mcp_url=mcp_url,
        session_token=session_token,
    )
    return {
        "status": state.get("status", "completed"),
        "intent": state.get("intent", "unknown"),
        "message": state.get("final_response", ""),
        "data": state,
    }


@mcp.tool()
def get_agent_state(session_id: str) -> dict[str, Any]:
    return service.get_state(session_id)


@mcp.tool()
def reset_agent(session_id: str) -> dict[str, Any]:
    return service.reset(session_id)


if __name__ == "__main__":
    mcp.run()
