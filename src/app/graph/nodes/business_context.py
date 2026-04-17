from __future__ import annotations

from app.graph.state import AgentState
from app.services.business_guide import interpret_business_request
from app.services.llm import AgentReasoner


def make_business_context_node(reasoner: AgentReasoner):
    def business_context_node(state: AgentState) -> AgentState:
        interpretation = interpret_business_request(
            state["user_input"], model=reasoner.model,
        )
        updates: AgentState = {
            "business_goal": interpretation.business_goal,
            "business_terms": interpretation.business_terms,
            "candidate_fields": interpretation.candidate_fields,
            "account_name": interpretation.account_name,
            "guidance": [*state.get("guidance", []), *interpretation.guidance],
        }
        current_target = state.get("target_object")
        known_objects = {"Account", "Contact", "Opportunity", "Account_Plan__c"}
        if interpretation.target_object and (not current_target or current_target not in known_objects):
            updates["target_object"] = interpretation.target_object
        return updates

    return business_context_node
