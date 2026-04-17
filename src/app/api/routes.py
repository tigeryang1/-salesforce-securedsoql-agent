from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from app.config import get_settings
from app.graph.builder import build_agent_graph
from app.models.requests import ApprovalRequest, RunRequest
from app.models.responses import AgentResponse
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner, build_chat_model
from app.services.mcp_transport import build_streamable_http_adapter
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


settings = get_settings()
app = FastAPI(title="Salesforce SecuredSOQL Agent", version="0.1.0")
app.state.draft_store = {}


def require_api_token(authorization: str | None = Header(default=None)) -> str:
    expected = settings.agent_api_token
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid bearer token.")
    return authorization


def build_demo_adapter() -> InMemorySalesforceToolAdapter:
    def query_handler(query: str) -> QueryResult:
        normalized = query.lower()
        if "from account where name like '%nike%'" in normalized:
            return QueryResult(
                success=True,
                records=[{"Id": "001000000000000AAA", "Name": "Nike", "Industry": "Retail"}],
                record_count=1,
                returned_fields=["Id", "Name", "Industry"],
            )
        if "from account where name like '%acme%'" in normalized:
            return QueryResult(
                success=True,
                records=[{"Id": "001000000000000BBB", "Name": "Acme", "Industry": "Retail"}],
                record_count=1,
                returned_fields=["Id", "Name", "Industry"],
            )
        if "from contact" in normalized:
            return QueryResult(
                success=True,
                records=[{
                    "Id": "003000000000000AAA",
                    "Name": "Jane Smith",
                    "Email": "jane.smith@example.com",
                    "Phone": "555-0100",
                    "Title": "VP Marketing",
                    "AccountId": "001000000000000AAA",
                }],
                record_count=1,
                returned_fields=["Id", "Name", "Email", "Phone", "Title", "AccountId"],
            )
        if "from opportunity" in normalized:
            return QueryResult(
                success=True,
                records=[{
                    "Id": "006000000000000AAA",
                    "Name": "Acme Q1 Deal",
                    "StageName": "Proposal",
                    "Amount": "250000",
                    "CloseDate": "2026-03-31",
                    "AccountId": "001000000000000AAA",
                }],
                record_count=1,
                returned_fields=["Id", "Name", "StageName", "Amount", "CloseDate", "AccountId"],
            )
        if "from account_plan__c" in normalized:
            return QueryResult(
                success=True,
                records=[
                    {
                        "Annual_Pinterest_Goals_Strategy__c": "Grow upper funnel demand",
                        "Business_Challenges_Priorities__c": "Improve measurement confidence",
                        "Opportunity_for_Growth__c": "Expand shopping campaigns",
                        "This_Year_Annual_Spend_Est__c": "100000",
                    }
                ],
                record_count=1,
                returned_fields=[
                    "Annual_Pinterest_Goals_Strategy__c",
                    "Business_Challenges_Priorities__c",
                    "Opportunity_for_Growth__c",
                    "This_Year_Annual_Spend_Est__c",
                ],
            )
        return QueryResult(
            success=True,
            records=[{"Id": "001000000000000BBB", "Name": "Acme", "Industry": "Retail"}],
            record_count=1,
            returned_fields=["Id", "Name", "Industry"],
        )

    return InMemorySalesforceToolAdapter(
        describes={
            "Account": ObjectDescription(
                name="Account",
                label="Account",
                key_prefix="001",
                fields=[
                    FieldDescription(name="Id", label="Account ID", type="id"),
                    FieldDescription(name="Name", label="Account Name", type="string"),
                    FieldDescription(name="Industry", label="Industry", type="string"),
                    FieldDescription(name="OwnerId", label="Owner", type="reference", reference_to=["User"]),
                    FieldDescription(name="CreatedDate", label="Created Date", type="datetime"),
                ],
            ),
            "Contact": ObjectDescription(
                name="Contact",
                label="Contact",
                key_prefix="003",
                fields=[
                    FieldDescription(name="Id", label="Contact ID", type="id"),
                    FieldDescription(name="Name", label="Full Name", type="string"),
                    FieldDescription(name="Email", label="Email", type="email"),
                    FieldDescription(name="Phone", label="Phone", type="phone"),
                    FieldDescription(name="Title", label="Title", type="string"),
                    FieldDescription(name="AccountId", label="Account ID", type="reference", reference_to=["Account"]),
                ],
            ),
            "Opportunity": ObjectDescription(
                name="Opportunity",
                label="Opportunity",
                key_prefix="006",
                fields=[
                    FieldDescription(name="Id", label="Opportunity ID", type="id"),
                    FieldDescription(name="Name", label="Opportunity Name", type="string"),
                    FieldDescription(name="StageName", label="Stage", type="picklist"),
                    FieldDescription(name="Amount", label="Amount", type="currency"),
                    FieldDescription(name="CloseDate", label="Close Date", type="date"),
                    FieldDescription(name="AccountId", label="Account ID", type="reference", reference_to=["Account"]),
                ],
            ),
            "Account_Plan__c": ObjectDescription(
                name="Account_Plan__c",
                label="Account Plan",
                key_prefix="a01",
                fields=[
                    FieldDescription(name="AccountPlan__c", label="Account", type="reference", reference_to=["Account"]),
                    FieldDescription(name="Plan_Year__c", label="Plan Year", type="picklist"),
                    FieldDescription(name="Annual_Pinterest_Goals_Strategy__c", label="Goals Strategy", type="textarea"),
                    FieldDescription(name="Business_Challenges_Priorities__c", label="Business Priorities", type="textarea"),
                    FieldDescription(name="Opportunity_for_Growth__c", label="Growth Opportunities", type="textarea"),
                    FieldDescription(name="This_Year_Annual_Spend_Est__c", label="Annual Spend", type="currency"),
                ],
            ),
        },
        query_handler=query_handler,
        upload_handler=lambda _payload: UploadResult(
            success=True,
            action="upserted",
            record_id="a01000000000000AAA",
        ),
    )


async def build_graph(*, use_demo_adapter: bool, mcp_url: str | None, session_token: str | None):
    if use_demo_adapter:
        adapter = build_demo_adapter()
    else:
        if not mcp_url:
            mcp_url = settings.default_mcp_url
        if not session_token:
            session_token = settings.default_session_token
        adapter = await build_streamable_http_adapter(mcp_url=mcp_url, session_token=session_token)
    reasoner = _build_reasoner()
    return build_agent_graph(adapter=adapter, reasoner=reasoner)


def _build_reasoner() -> AgentReasoner:
    model_name = settings.agent_model
    if not model_name:
        return AgentReasoner(model=None)
    try:
        return AgentReasoner(model=build_chat_model(model_name))
    except Exception:
        return AgentReasoner(model=None)


def merge_account_plan_draft(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any] | None:
    if not existing and not incoming:
        return None
    merged: dict[str, Any] = {}
    for payload in (existing or {}, incoming or {}):
        for key, value in payload.items():
            if value not in (None, ""):
                merged[key] = value
    return merged


def should_persist_draft(intent: str, state: dict[str, Any]) -> bool:
    return intent == "upload_account_plan" and state.get("account_plan_data") is not None


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "model": settings.agent_model}


@app.post("/run", response_model=AgentResponse)
async def run_agent(
    request: RunRequest,
    _: str = Depends(require_api_token),
) -> AgentResponse:
    stored_draft = app.state.draft_store.get(request.session_id)
    merged_payload = merge_account_plan_draft(stored_draft, request.account_plan_data)
    graph = await build_graph(
        use_demo_adapter=request.use_demo_adapter,
        mcp_url=request.mcp_url,
        session_token=request.session_token,
    )
    state = await graph.ainvoke(
        {
            "user_input": request.user_input,
            "soql_query": request.soql_query,
            "target_object": request.sobject_name,
            "account_plan_data": merged_payload,
            "approved": request.approved,
            "retry_count": 0,
            "security_notes": [],
        }
    )
    if should_persist_draft(state.get("intent", "unknown"), state):
        if state.get("status") == "uploaded":
            app.state.draft_store.pop(request.session_id, None)
        else:
            app.state.draft_store[request.session_id] = state.get("account_plan_data") or {}
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
    stored_draft = app.state.draft_store.get(request.session_id)
    merged_payload = merge_account_plan_draft(stored_draft, request.account_plan_data)
    graph = await build_graph(
        use_demo_adapter=request.use_demo_adapter,
        mcp_url=request.mcp_url,
        session_token=request.session_token,
    )
    state = await graph.ainvoke(
        {
            "user_input": request.user_input,
            "account_plan_data": merged_payload,
            "approved": request.approved,
            "retry_count": 0,
            "security_notes": [],
        }
    )
    app.state.draft_store.pop(request.session_id, None)
    return AgentResponse(
        status=state.get("status", "completed"),
        intent=state.get("intent", "unknown"),
        message=state.get("final_response", ""),
        data=dict(state),
    )
