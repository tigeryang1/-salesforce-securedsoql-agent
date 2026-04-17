from __future__ import annotations

import logging

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def approval_node(state: AgentState) -> AgentState:
    if state.get("approved"):
        logger.info("write approved")
        return {"status": "approved"}
    logger.info("write blocked pending approval")
    return {
        "status": "needs_approval",
        "guidance": [
            *state.get("guidance", []),
            "Review the upload preview before approving the write.",
        ],
    }
