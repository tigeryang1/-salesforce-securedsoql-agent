from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from app.agent_service import AgentSessionService
from app.config import get_settings
from app.models.requests import ApprovalRequest, RunRequest
from app.models.responses import AgentResponse


settings = get_settings()
app = FastAPI(title="Salesforce SecuredSOQL Agent", version="0.1.0")
app.state.agent_service = AgentSessionService(settings)


def require_api_token(authorization: str | None = Header(default=None)) -> str:
    expected = settings.agent_api_token
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid bearer token.")
    return authorization

@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "model": settings.agent_model}


@app.post("/run", response_model=AgentResponse)
async def run_agent(
    request: RunRequest,
    _: str = Depends(require_api_token),
) -> AgentResponse:
    state = await app.state.agent_service.run(
        user_input=request.user_input,
        session_id=request.session_id,
        soql_query=request.soql_query,
        sobject_name=request.sobject_name,
        account_plan_data=request.account_plan_data,
        approved=request.approved,
        session_access_key=request.session_access_key,
        use_demo_adapter=request.use_demo_adapter,
        mcp_url=request.mcp_url,
        session_token=request.session_token,
    )
    return AgentResponse(
        status=state.get("status", "completed"),
        intent=state.get("intent", "unknown"),
        message=state.get("final_response", ""),
        data=dict(state),
    )


@app.post("/approve", response_model=AgentResponse)
async def approve_write(
    request: ApprovalRequest,
    _: str = Depends(require_api_token),
) -> AgentResponse:
    state = await app.state.agent_service.approve(
        user_input=request.user_input,
        session_id=request.session_id,
        account_plan_data=request.account_plan_data,
        session_access_key=request.session_access_key,
        use_demo_adapter=request.use_demo_adapter,
        mcp_url=request.mcp_url,
        session_token=request.session_token,
    )
    return AgentResponse(
        status=state.get("status", "completed"),
        intent=state.get("intent", "unknown"),
        message=state.get("final_response", ""),
        data=dict(state),
    )
