from __future__ import annotations

import re

from app.graph.state import AgentState
from app.utils.security import remove_field_from_where_or_order_by


INFERENCE_RE = re.compile(r"Inference attack detected.*?field[:\s]+([A-Za-z0-9_]+)", re.IGNORECASE)


def recovery_node(state: AgentState) -> AgentState:
    query_error = state.get("query_error") or ""
    retry_count = state.get("retry_count", 0)
    if retry_count >= 1:
        return {"status": "error"}
    if "Inference attack detected" not in query_error:
        return {"status": "error"}

    match = INFERENCE_RE.search(query_error)
    if not match or not state.get("soql_query"):
        return {"status": "error"}

    blocked_field = match.group(1)
    recovered = remove_field_from_where_or_order_by(state["soql_query"], blocked_field)
    return {
        "recovered_soql_query": recovered,
        "retry_count": retry_count + 1,
        "status": "retrying",
        "security_notes": [
            *state.get("security_notes", []),
            f"Removed restricted field `{blocked_field}` from WHERE/ORDER BY and retried.",
        ],
    }
