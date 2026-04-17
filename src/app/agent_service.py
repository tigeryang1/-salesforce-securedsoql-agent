from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
from app.graph.builder import build_agent_graph
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner, build_chat_model
from app.services.mcp_transport import build_streamable_http_adapter
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


class AgentSessionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._draft_store: dict[str, dict[str, Any]] = {}
        self._last_state_store: dict[str, dict[str, Any]] = {}
        self._session_config_store: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def run(
        self,
        *,
        user_input: str,
        session_id: str,
        soql_query: str | None = None,
        sobject_name: str | None = None,
        account_plan_data: dict[str, Any] | None = None,
        approved: bool = False,
        use_demo_adapter: bool = True,
        mcp_url: str | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        lock = await self._session_lock(session_id)
        async with lock:
            return await self._run_unlocked(
                user_input=user_input,
                session_id=session_id,
                soql_query=soql_query,
                sobject_name=sobject_name,
                account_plan_data=account_plan_data,
                approved=approved,
                use_demo_adapter=use_demo_adapter,
                mcp_url=mcp_url,
                session_token=session_token,
            )

    async def _run_unlocked(
        self,
        *,
        user_input: str,
        session_id: str,
        soql_query: str | None = None,
        sobject_name: str | None = None,
        account_plan_data: dict[str, Any] | None = None,
        approved: bool = False,
        use_demo_adapter: bool = True,
        mcp_url: str | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        stored_draft = self._draft_store.get(session_id)
        merged_payload = merge_account_plan_draft(stored_draft, account_plan_data)
        session_config = self._effective_session_config(
            session_id=session_id,
            use_demo_adapter=use_demo_adapter,
            mcp_url=mcp_url,
            session_token=session_token,
        )
        graph = await self._build_graph(
            use_demo_adapter=session_config["use_demo_adapter"],
            mcp_url=session_config["mcp_url"],
            session_token=session_config["session_token"],
        )
        logger.info("session=%s running graph (demo=%s)", session_id, session_config["use_demo_adapter"])
        state = await graph.ainvoke(
            {
                "user_input": user_input,
                "soql_query": soql_query,
                "target_object": sobject_name,
                "account_plan_data": merged_payload,
                "approved": approved,
                "retry_count": 0,
                "security_notes": [],
            }
        )
        logger.info(
            "session=%s finished intent=%s status=%s",
            session_id, state.get("intent"), state.get("status"),
        )
        self._last_state_store[session_id] = dict(state)
        self._session_config_store[session_id] = dict(session_config)
        if should_persist_draft(state.get("intent", "unknown"), state):
            if state.get("status") == "uploaded":
                self._draft_store.pop(session_id, None)
                self._session_config_store.pop(session_id, None)
            else:
                self._draft_store[session_id] = deepcopy(state.get("account_plan_data") or {})
        return dict(state)

    async def approve(
        self,
        *,
        user_input: str,
        session_id: str,
        account_plan_data: dict[str, Any] | None = None,
        use_demo_adapter: bool = True,
        mcp_url: str | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        lock = await self._session_lock(session_id)
        async with lock:
            stored_draft = self._draft_store.get(session_id)
            merged_payload = merge_account_plan_draft(stored_draft, account_plan_data)
            session_config = self._effective_session_config(
                session_id=session_id,
                use_demo_adapter=use_demo_adapter,
                mcp_url=mcp_url,
                session_token=session_token,
            )
            state = await self._run_unlocked(
                user_input=user_input,
                session_id=session_id,
                account_plan_data=merged_payload,
                approved=True,
                use_demo_adapter=session_config["use_demo_adapter"],
                mcp_url=session_config["mcp_url"],
                session_token=session_config["session_token"],
            )
            if state.get("status") == "uploaded":
                self._draft_store.pop(session_id, None)
                self._session_config_store.pop(session_id, None)
            return state

    async def get_state(self, session_id: str) -> dict[str, Any]:
        lock = await self._session_lock(session_id)
        async with lock:
            config = deepcopy(self._session_config_store.get(session_id))
            return {
                "session_id": session_id,
                "account_plan_data": deepcopy(self._draft_store.get(session_id)),
                "last_state": deepcopy(self._last_state_store.get(session_id)),
                "session_config": _redact_session_config(config) if config else None,
            }

    async def reset(self, session_id: str) -> dict[str, Any]:
        lock = await self._session_lock(session_id)
        async with lock:
            logger.info("session=%s resetting", session_id)
            removed_draft = self._draft_store.pop(session_id, None)
            removed_state = self._last_state_store.pop(session_id, None)
            removed_config = self._session_config_store.pop(session_id, None)
            return {
                "session_id": session_id,
                "reset": True,
                "had_draft": removed_draft is not None,
                "had_state": removed_state is not None,
                "had_config": removed_config is not None,
            }

    def _effective_session_config(
        self,
        *,
        session_id: str,
        use_demo_adapter: bool,
        mcp_url: str | None,
        session_token: str | None,
    ) -> dict[str, Any]:
        stored = self._session_config_store.get(session_id, {})
        explicit_live = not use_demo_adapter or bool(mcp_url) or bool(session_token)
        if stored and not explicit_live:
            return {
                "use_demo_adapter": stored.get("use_demo_adapter", True),
                "mcp_url": stored.get("mcp_url"),
                "session_token": stored.get("session_token"),
            }
        return {
            "use_demo_adapter": use_demo_adapter,
            "mcp_url": mcp_url,
            "session_token": session_token,
        }

    async def _build_graph(
        self,
        *,
        use_demo_adapter: bool,
        mcp_url: str | None,
        session_token: str | None,
    ):
        if use_demo_adapter:
            adapter = build_demo_adapter()
        else:
            if not mcp_url:
                mcp_url = self.settings.default_mcp_url
            if not session_token:
                session_token = self.settings.default_session_token
            adapter = await build_streamable_http_adapter(mcp_url=mcp_url, session_token=session_token)
        reasoner = _build_reasoner(self.settings)
        return build_agent_graph(adapter=adapter, reasoner=reasoner)


def _build_reasoner(settings: Settings) -> AgentReasoner:
    model_name = settings.agent_model
    if not model_name:
        logger.info("no AGENT_MODEL configured, using heuristic-only mode")
        return AgentReasoner(model=None)
    try:
        return AgentReasoner(model=build_chat_model(model_name))
    except Exception:
        logger.warning("failed to load model %r, falling back to heuristic mode", model_name, exc_info=True)
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


def _redact_session_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "use_demo_adapter": config.get("use_demo_adapter"),
        "mcp_url": config.get("mcp_url"),
        "has_session_token": bool(config.get("session_token")),
    }


def build_demo_adapter() -> InMemorySalesforceToolAdapter:
    def query_handler(query: str) -> QueryResult:
        normalized = query.lower()
        if "from account where name like '%nike%'" in normalized or "from account where name = 'nike'" in normalized:
            return QueryResult(
                success=True,
                records=[{"Id": "001000000000000AAA", "Name": "Nike", "Industry": "Retail"}],
                record_count=1,
                returned_fields=["Id", "Name", "Industry"],
            )
        if "from account where name like '%acme%'" in normalized or "from account where name = 'acme'" in normalized:
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
