from __future__ import annotations

from app.graph.state import AgentState


def approval_node(state: AgentState) -> AgentState:
    if state.get("approved"):
        return {"status": "approved"}
    return {
        "status": "needs_approval",
        "guidance": [
            *state.get("guidance", []),
            "Review the upload preview before approving the write.",
        ],
    }
