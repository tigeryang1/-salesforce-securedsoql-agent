from __future__ import annotations

from app.graph.state import AgentState
from app.utils.security import extract_from_object


def planning_node(state: AgentState) -> AgentState:
    if state.get("intent") == "query" and state.get("soql_query") and not state.get("target_object"):
        return {"target_object": extract_from_object(state["soql_query"])}
    if state.get("intent") == "query" and not state.get("target_object"):
        return {"target_object": "Account"}
    if state.get("intent") == "upload_account_plan" and not state.get("target_object"):
        return {"target_object": "Account_Plan__c"}
    return {}
