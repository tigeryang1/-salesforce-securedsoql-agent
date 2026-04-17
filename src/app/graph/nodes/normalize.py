from __future__ import annotations

from app.graph.state import AgentState
from app.services.summary import summarize_query_result


def normalize_node(state: AgentState) -> AgentState:
    notes = list(state.get("security_notes", []))
    if state.get("filtered_fields"):
        notes.append(
            "Requested fields missing from the response were treated as security-filtered."
        )
    if state.get("intent") == "query":
        notes.append(
            "Record count may be less than the LIMIT because row-level security can filter rows."
        )
    return {
        "security_notes": notes,
        "status": "normalized",
        "business_summary": summarize_query_result(dict(state)),
    }
