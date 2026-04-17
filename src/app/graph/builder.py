from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.approval import approval_node
from app.graph.nodes.business_context import make_business_context_node
from app.graph.nodes.intent import make_intent_node
from app.graph.nodes.normalize import normalize_node
from app.graph.nodes.planning import planning_node
from app.graph.nodes.query_execute import make_query_execute_node
from app.graph.nodes.resolve_account import make_resolve_account_node
from app.graph.nodes.recovery import recovery_node
from app.graph.nodes.respond import make_respond_node
from app.graph.nodes.schema import make_schema_node
from app.graph.nodes.soql_builder import soql_builder_node
from app.graph.nodes.write_execute import make_write_execute_node
from app.graph.nodes.write_validate import write_validate_node
from app.graph.state import AgentState
from app.services.contracts import SalesforceToolAdapter
from app.services.llm import AgentReasoner


def build_agent_graph(*, adapter: SalesforceToolAdapter, reasoner: AgentReasoner):
    graph = StateGraph(AgentState)

    graph.add_node("intent", make_intent_node(reasoner))
    graph.add_node("business_context", make_business_context_node(reasoner))
    graph.add_node("planning", planning_node)
    graph.add_node("resolve_account", make_resolve_account_node(adapter))
    graph.add_node("schema", make_schema_node(adapter))
    graph.add_node("soql_builder", soql_builder_node)
    graph.add_node("query_execute", make_query_execute_node(adapter))
    graph.add_node("recovery", recovery_node)
    graph.add_node("normalize", normalize_node)
    graph.add_node("write_validate", write_validate_node)
    graph.add_node("approval", approval_node)
    graph.add_node("write_execute", make_write_execute_node(adapter))
    graph.add_node("respond", make_respond_node(reasoner))

    graph.add_edge(START, "intent")
    graph.add_edge("intent", "business_context")
    graph.add_edge("business_context", "planning")

    graph.add_conditional_edges(
        "planning",
        route_from_planning,
        {
            "describe": "schema",
            "query": "resolve_account",
            "upload_account_plan": "resolve_account",
        },
    )
    graph.add_conditional_edges(
        "resolve_account",
        route_after_account_resolution,
        {
            "schema": "schema",
            "write_validate": "write_validate",
            "respond": "respond",
        },
    )
    graph.add_conditional_edges(
        "schema",
        route_after_schema,
        {
            "describe": "respond",
            "query": "soql_builder",
        },
    )
    graph.add_edge("soql_builder", "query_execute")
    graph.add_conditional_edges(
        "query_execute",
        route_after_query,
        {
            "normalize": "normalize",
            "recovery": "recovery",
            "respond": "respond",
        },
    )
    graph.add_edge("recovery", "query_execute")
    graph.add_edge("normalize", "respond")
    graph.add_conditional_edges(
        "write_validate",
        route_after_write_validation,
        {
            "approval": "approval",
            "respond": "respond",
        },
    )
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "write_execute": "write_execute",
            "respond": "respond",
        },
    )
    graph.add_edge("write_execute", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


def route_from_planning(state: AgentState) -> str:
    return state.get("intent", "query")


def route_after_schema(state: AgentState) -> str:
    return "describe" if state.get("intent") == "describe" else "query"


def route_after_account_resolution(state: AgentState) -> str:
    if state.get("status") == "needs_input" or state.get("status") == "error":
        return "respond"
    if state.get("intent") == "upload_account_plan":
        return "write_validate"
    return "schema"


def route_after_query(state: AgentState) -> str:
    if state.get("status") == "query_error" and "Inference attack detected" in (state.get("query_error") or ""):
        return "recovery"
    if state.get("status") == "queried":
        return "normalize"
    return "respond"


def route_after_write_validation(state: AgentState) -> str:
    if state.get("status") == "validated":
        return "approval"
    return "respond"


def route_after_approval(state: AgentState) -> str:
    if state.get("status") == "approved":
        return "write_execute"
    return "respond"
