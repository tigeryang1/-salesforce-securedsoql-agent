from __future__ import annotations

import json
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
        "Prefer reusing the same session_id for multi-turn drafting. "
        "Use resources to inspect draft state without modifying it. "
        "Use prompts for guided workflows."
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
async def get_agent_state(session_id: str) -> dict[str, Any]:
    return await service.get_state(session_id)


@mcp.tool()
async def reset_agent(session_id: str) -> dict[str, Any]:
    return await service.reset(session_id)


# ============================================================================
# MCP Resources - Read-only access to draft state
# ============================================================================


@mcp.resource("draft://sessions")
async def list_draft_sessions() -> str:
    """List all active draft sessions.

    Returns a JSON array with session summaries including:
    - session_id
    - has_draft (boolean)
    - has_state (boolean)
    - last_intent (if available)
    - last_status (if available)
    """
    sessions_summary = []

    # Get all unique session IDs from all stores
    all_session_ids = set()
    all_session_ids.update(service._draft_store.keys())
    all_session_ids.update(service._last_state_store.keys())
    all_session_ids.update(service._session_config_store.keys())

    for session_id in sorted(all_session_ids):
        draft = service._draft_store.get(session_id)
        state = service._last_state_store.get(session_id)

        summary = {
            "session_id": session_id,
            "has_draft": draft is not None,
            "draft_field_count": len(draft) if draft else 0,
            "has_state": state is not None,
            "last_intent": state.get("intent") if state else None,
            "last_status": state.get("status") if state else None,
        }
        sessions_summary.append(summary)

    return json.dumps({
        "sessions": sessions_summary,
        "total_count": len(sessions_summary),
    }, indent=2)


@mcp.resource("draft://sessions/{session_id}")
async def read_draft_session(session_id: str) -> str:
    """Read the full state of a specific draft session.

    Returns detailed information about the session including:
    - session_id
    - account_plan_data (current draft)
    - last_state (last execution result)
    - session_config (MCP connection settings, redacted)
    """
    state = await service.get_state(session_id)
    return json.dumps(state, indent=2, default=str)


# ============================================================================
# MCP Prompts - Guided workflows
# ============================================================================


@mcp.prompt()
async def salesforce_query_guided(
    object_type: str = "",
    user_goal: str = "",
) -> str:
    """Interactive guide for Salesforce queries with security awareness.

    Helps users construct secure queries with automatic handling of:
    - Field-level security filtering
    - Inference attack protection
    - Row-level security transparency

    Args:
        object_type: Salesforce object to query (e.g., "Account")
        user_goal: What the user wants to find (e.g., "accounts in California")
    """
    parts = [
        "# Salesforce Query Guide",
        "",
        "I'll help you query Salesforce data securely using the SecuredSOQL agent.",
        "",
        "## Security Features",
        "",
        "This agent automatically handles:",
        "- **Field filtering**: Restricted fields are silently removed from results",
        "- **Inference protection**: Restricted fields in WHERE/ORDER BY are detected and removed",
        "- **Row-level security**: You'll see only the records you have access to",
        "",
    ]

    if object_type:
        parts.extend([
            f"## You're querying: {object_type}",
            "",
        ])

    if user_goal:
        parts.extend([
            f"## Your goal: {user_goal}",
            "",
        ])

    parts.extend([
        "## What You Can Do",
        "",
        "1. **Natural Language Queries**",
        '   Example: "Show me all accounts in California with revenue over $1M"',
        "",
        "2. **Object Exploration**",
        '   Example: "Describe the Account object"',
        "",
        "3. **Direct SOQL**",
        '   Example: "SELECT Name, Industry FROM Account WHERE State = \'CA\' LIMIT 10"',
        "",
        "4. **Company Lookup**",
        '   Example: "Find the Nike account"',
        "",
        "## Getting Started",
        "",
        "Use the `run_langgraph_agent` tool with:",
        "- `prompt`: Your query or request",
        "- `session_id`: A unique identifier for this session",
        "- `sobject_name`: (optional) Specific object to query",
        "",
        "What would you like to query?",
    ])

    return "\n".join(parts)


@mcp.prompt()
async def account_plan_guided(
    account_name: str = "",
    plan_year: str = "",
) -> str:
    """Step-by-step guide for creating comprehensive account plans.

    Walks users through creating multi-dimensional account plans including:
    - Executive summary and strategy
    - Client objectives and priorities
    - Marketing approach
    - Quarterly planning and revenue goals
    - Leadership and relationships
    - Competitive landscape

    Args:
        account_name: Company name for the plan (e.g., "Nike")
        plan_year: Target fiscal year (e.g., "2026")
    """
    parts = [
        "# Account Plan Creation Guide",
        "",
        "I'll guide you through creating a comprehensive Salesforce account plan.",
        "",
    ]

    if account_name and plan_year:
        parts.extend([
            f"## Creating plan: {account_name} - {plan_year}",
            "",
        ])
    elif account_name:
        parts.extend([
            f"## Creating plan for: {account_name}",
            "",
        ])
    elif plan_year:
        parts.extend([
            f"## Creating plan for fiscal year: {plan_year}",
            "",
        ])

    parts.extend([
        "## Plan Sections",
        "",
        "### 1. Executive Summary",
        "- Annual goals and strategy",
        "- Value proposition",
        "- Growth opportunities",
        "",
        "### 2. Client Understanding",
        "- CEO strategic priorities",
        "- Business challenges",
        "- Recent news and developments",
        "",
        "### 3. Marketing Strategy",
        "- Account health",
        "- CMO goals and approach",
        "- Measurement and creative strategy",
        "- Agency relationships",
        "",
        "### 4. Quarterly Planning",
        "- Q1-Q4 objectives",
        "- Key events per quarter",
        "- Problem statements",
        "",
        "### 5. Revenue Goals",
        "- Annual spend estimate",
        "- Quarterly breakdown (must sum to annual)",
        "",
        "### 6. Leadership & Relationships",
        "- Primary contacts",
        "- Decision makers",
        "- Relationship mapping",
        "",
        "### 7. Competitive Landscape",
        "- Top 3 competitors",
        "- Competitive positioning",
        "",
        "### 8. Measurement & Cadence",
        "- Measurement vendors",
        "- Meeting frequency",
        "",
        "## How It Works",
        "",
        "1. **Progressive Drafting**: Provide information as you have it",
        "2. **Readiness Tracking**: See completion progress",
        "3. **Validation**: Automatic checks for required fields",
        "4. **Approval Required**: Explicit approval before upload",
        "",
        "## Getting Started",
        "",
        "Use the `run_langgraph_agent` tool with:",
        "- `prompt`: Your input or answers",
        "- `session_id`: Unique session ID (reuse for multi-turn)",
        "- `account_plan_data`: (optional) Specific field values",
        "",
    ])

    if not account_name:
        parts.append("**First step**: What company is this plan for?")
    elif not plan_year:
        parts.append("**Next step**: What fiscal year is this plan for?")
    else:
        parts.append("**Let's begin**: What information do you have about this account?")

    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run()
