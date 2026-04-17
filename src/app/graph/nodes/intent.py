from __future__ import annotations

from app.graph.state import AgentState
from app.services.llm import AgentReasoner


def make_intent_node(reasoner: AgentReasoner):
    def intent_node(state: AgentState) -> AgentState:
        decision = reasoner.classify_intent(
            user_input=state["user_input"],
            soql_query=state.get("soql_query"),
            sobject_name=state.get("target_object"),
            account_plan_data=state.get("account_plan_data"),
        )
        return {
            "intent": decision.intent,
            "target_object": state.get("target_object") or decision.target_object,
            "status": "planned",
        }

    return intent_node
