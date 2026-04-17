from __future__ import annotations

from app.graph.state import AgentState
from app.services.contracts import SalesforceToolAdapter


def make_write_execute_node(adapter: SalesforceToolAdapter):
    async def write_execute_node(state: AgentState) -> AgentState:
        payload = state.get("account_plan_data") or {}
        result = await adapter.upload_account_plan(payload)
        if not result.success:
            return {
                "status": "error",
                "query_error": result.error or "Upload failed.",
                "query_status_code": result.status_code,
            }
        return {
            "status": "uploaded",
            "upload_action": result.action or "updated",
            "upload_record_id": result.record_id,
        }

    return write_execute_node
