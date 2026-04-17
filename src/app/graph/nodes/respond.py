from __future__ import annotations

from app.graph.state import AgentState
from app.services.llm import AgentReasoner


def make_respond_node(reasoner: AgentReasoner):
    def respond_node(state: AgentState) -> AgentState:
        message = reasoner.compose_response(dict(state))
        return {"final_response": message}

    return respond_node
