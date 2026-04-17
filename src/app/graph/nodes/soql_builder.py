from __future__ import annotations

from app.graph.state import AgentState


def soql_builder_node(state: AgentState) -> AgentState:
    if state.get("soql_query"):
        return {}

    target_object = state.get("target_object")
    schema_fields = state.get("schema_fields", [])
    if not target_object or not schema_fields:
        return {
            "status": "error",
            "query_error": "Unable to construct SOQL without an object and schema.",
        }

    available_fields = {item["name"] for item in schema_fields}
    selected = [field for field in state.get("candidate_fields", []) if field in available_fields]
    if not selected:
        selected = [field["name"] for field in schema_fields[:5]]

    where_clause = ""
    if target_object == "Account_Plan__c" and state.get("resolved_account_id"):
        where_clause = f" WHERE AccountPlan__c = '{state['resolved_account_id']}'"
    elif target_object == "Account" and state.get("account_name"):
        account_name = state["account_name"].replace("'", "''")
        where_clause = f" WHERE Name LIKE '%{account_name}%'"

    soql_query = f"SELECT {', '.join(selected)} FROM {target_object}{where_clause} LIMIT 10"
    return {"soql_query": soql_query}
