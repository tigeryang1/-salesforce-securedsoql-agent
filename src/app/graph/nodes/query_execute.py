from __future__ import annotations

import logging

from app.graph.state import AgentState
from app.services.contracts import SalesforceToolAdapter

logger = logging.getLogger(__name__)


_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("Inference attack detected", "inference_attack"),
    ("not permitted for querying", "object_not_allowed"),
    ("does not have permission", "no_access"),
    ("Invalid email format", "invalid_email"),
    ("No user found with email", "user_not_found"),
    ("Missing required parameter", "missing_parameter"),
]


def classify_query_error(error_text: str | None) -> str:
    if not error_text:
        return "unknown"
    for pattern, error_type in _ERROR_PATTERNS:
        if pattern in error_text:
            return error_type
    return "unknown"


def make_query_execute_node(adapter: SalesforceToolAdapter):
    async def query_execute_node(state: AgentState) -> AgentState:
        query = state.get("recovered_soql_query") or state.get("soql_query")
        if not query:
            return {"status": "error", "query_error": "No SOQL query available.", "query_error_type": "missing_query"}

        result = await adapter.query_salesforce(query)
        if not result.success:
            error_type = classify_query_error(result.error)
            logger.warning("query failed error_type=%s error=%s", error_type, result.error)
            return {
                "status": "query_error",
                "query_error": result.error,
                "query_error_type": error_type,
                "query_status_code": result.status_code,
            }

        logger.info("query succeeded records=%d", result.record_count)
        return {
            "status": "queried",
            "records": result.records,
            "record_count": result.record_count,
            "filtered_fields": result.filtered_fields,
            "security_notes": result.security_notes,
        }

    return query_execute_node
