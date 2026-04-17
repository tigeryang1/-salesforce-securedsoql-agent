import asyncio

from app.graph.builder import build_agent_graph
from app.graph.nodes.query_execute import classify_query_error
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult
from app.services.llm import AgentReasoner, _compose_error_message
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


# --- classify_query_error unit tests ---


def test_classify_inference_attack() -> None:
    assert classify_query_error("Inference attack detected for field Email") == "inference_attack"


def test_classify_object_not_allowed() -> None:
    assert classify_query_error("Object CustomObj__c is not permitted for querying") == "object_not_allowed"


def test_classify_no_access() -> None:
    assert classify_query_error("User does not have permission to access Account") == "no_access"


def test_classify_invalid_email() -> None:
    assert classify_query_error("Invalid email format: not-an-email") == "invalid_email"


def test_classify_user_not_found() -> None:
    assert classify_query_error("No user found with email test@example.com") == "user_not_found"


def test_classify_missing_parameter() -> None:
    assert classify_query_error("Missing required parameter: soql") == "missing_parameter"


def test_classify_unknown_error() -> None:
    assert classify_query_error("Something unexpected happened") == "unknown"


def test_classify_none_error() -> None:
    assert classify_query_error(None) == "unknown"


# --- _compose_error_message unit tests ---


def test_error_message_object_not_allowed() -> None:
    msg = _compose_error_message({"query_error_type": "object_not_allowed", "query_error": "not permitted"})
    assert "not available for querying" in msg


def test_error_message_no_access() -> None:
    msg = _compose_error_message({"query_error_type": "no_access", "query_error": "no permission"})
    assert "do not have permission" in msg


def test_error_message_invalid_email() -> None:
    msg = _compose_error_message({"query_error_type": "invalid_email"})
    assert "not in a valid format" in msg


def test_error_message_user_not_found() -> None:
    msg = _compose_error_message({"query_error_type": "user_not_found"})
    assert "No active Salesforce user" in msg


def test_error_message_missing_parameter() -> None:
    msg = _compose_error_message({"query_error_type": "missing_parameter"})
    assert "missing a required parameter" in msg


def test_error_message_inference_attack() -> None:
    msg = _compose_error_message({"query_error_type": "inference_attack"})
    assert "restricted field" in msg


def test_error_message_unknown_with_raw_error() -> None:
    msg = _compose_error_message({"query_error_type": "unknown", "query_error": "Timeout exceeded"})
    assert "Timeout exceeded" in msg


def test_error_message_unknown_without_raw_error() -> None:
    msg = _compose_error_message({"query_error_type": "unknown"})
    assert "unexpected error" in msg


# --- AgentReasoner._compose_fallback_response integration ---


def test_fallback_response_uses_error_message_for_query_error_status() -> None:
    reasoner = AgentReasoner(model=None)
    msg = reasoner._compose_fallback_response({
        "status": "query_error",
        "intent": "query",
        "query_error_type": "object_not_allowed",
        "query_error": "CustomObj__c is not permitted for querying",
    })
    assert "not available for querying" in msg


def test_fallback_response_uses_error_message_for_error_status() -> None:
    reasoner = AgentReasoner(model=None)
    msg = reasoner._compose_fallback_response({
        "status": "error",
        "intent": "query",
        "query_error_type": "no_access",
        "query_error": "User does not have permission",
    })
    assert "do not have permission" in msg


def test_fallback_response_still_works_for_non_error_statuses() -> None:
    reasoner = AgentReasoner(model=None)
    msg = reasoner._compose_fallback_response({
        "status": "completed",
        "intent": "describe",
        "target_object": "Account",
        "schema_fields": [{"name": "Id"}, {"name": "Name"}],
    })
    assert "Described Account with 2 fields" in msg


# --- End-to-end graph test: error type flows through to final_response ---


def _build_error_graph(error_text, status_code=403):
    adapter = InMemorySalesforceToolAdapter(
        describes={
            "Account": ObjectDescription(
                name="Account", label="Account", key_prefix="001",
                fields=[
                    FieldDescription(name="Id", label="ID", type="id"),
                    FieldDescription(name="Name", label="Name", type="string"),
                ],
            ),
        },
        query_handler=lambda q: QueryResult(success=False, error=error_text, status_code=status_code),
    )
    return build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))


def _invoke_with_error(error_text, status_code=403):
    graph = _build_error_graph(error_text, status_code)
    return asyncio.run(graph.ainvoke({
        "user_input": "Find account",
        "soql_query": "SELECT Id, Name FROM Account LIMIT 5",
        "approved": False,
        "retry_count": 0,
        "security_notes": [],
    }))


def test_graph_object_not_allowed_produces_targeted_message() -> None:
    state = _invoke_with_error("Object Account is not permitted for querying")
    assert state.get("query_error_type") == "object_not_allowed"
    assert "not available for querying" in state["final_response"]


def test_graph_no_access_produces_targeted_message() -> None:
    state = _invoke_with_error("User does not have permission to access Account")
    assert state.get("query_error_type") == "no_access"
    assert "do not have permission" in state["final_response"]


def test_graph_user_not_found_produces_targeted_message() -> None:
    state = _invoke_with_error("No user found with email ghost@example.com")
    assert state.get("query_error_type") == "user_not_found"
    assert "No active Salesforce user" in state["final_response"]


def test_graph_invalid_email_produces_targeted_message() -> None:
    state = _invoke_with_error("Invalid email format: not-an-email")
    assert state.get("query_error_type") == "invalid_email"
    assert "not in a valid format" in state["final_response"]


def test_graph_unknown_error_includes_raw_text() -> None:
    state = _invoke_with_error("Something completely unexpected")
    assert state.get("query_error_type") == "unknown"
    assert "Something completely unexpected" in state["final_response"]
