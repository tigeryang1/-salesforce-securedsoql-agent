from __future__ import annotations

from app.graph.state import AgentState
from app.services.contracts import SalesforceToolAdapter


def make_query_execute_node(adapter: SalesforceToolAdapter):
    async def query_execute_node(state: AgentState) -> AgentState:
        query = state.get("recovered_soql_query") or state.get("soql_query")
        if not query:
            return {"status": "error", "query_error": "No SOQL query available."}

        result = await adapter.query_salesforce(query)
        if not result.success:
            return {
                "status": "query_error",
                "query_error": result.error,
                "query_status_code": result.status_code,
            }

        return {
            "status": "queried",
            "records": result.records,
            "record_count": result.record_count,
            "filtered_fields": result.filtered_fields,
            "security_notes": result.security_notes,
        }

    return query_execute_node
