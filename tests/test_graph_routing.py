import asyncio

from app.graph.builder import build_agent_graph
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


def build_graph(query_handler=None, upload_handler=None):
    adapter = InMemorySalesforceToolAdapter(
        describes={
            "Account": ObjectDescription(
                name="Account",
                label="Account",
                key_prefix="001",
                fields=[
                    FieldDescription(name="Id", label="ID", type="id"),
                    FieldDescription(name="Name", label="Name", type="string"),
                    FieldDescription(name="Industry", label="Industry", type="string"),
                ],
            ),
            "Account_Plan__c": ObjectDescription(
                name="Account_Plan__c",
                label="Account Plan",
                key_prefix="a01",
                fields=[
                    FieldDescription(name="AccountPlan__c", label="Account", type="reference"),
                    FieldDescription(name="Plan_Year__c", label="Plan Year", type="picklist"),
                ],
            ),
        },
        query_handler=query_handler,
        upload_handler=upload_handler,
    )
    return build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))


def test_inference_error_retries_without_blocked_field() -> None:
    calls: list[str] = []

    def query_handler(query: str) -> QueryResult:
        calls.append(query)
        if len(calls) == 1:
            return QueryResult(
                success=False,
                error="Inference attack detected for field Email",
                status_code=403,
            )
        return QueryResult(
            success=True,
            records=[{"Id": "001000000000000AAA", "Name": "Acme"}],
            record_count=1,
            returned_fields=["Id", "Name"],
        )

    graph = build_graph(query_handler=query_handler)
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Find account",
                "soql_query": "SELECT Id, Name FROM Account WHERE Email = 'test@example.com' LIMIT 1",
                "approved": False,
                "retry_count": 0,
                "security_notes": [],
            }
        )
    )

    assert len(calls) == 2
    assert "Email" not in calls[1]
    assert state["record_count"] == 1


def test_upload_requires_approval() -> None:
    graph = build_graph(
        upload_handler=lambda payload: UploadResult(success=True, action="upserted", record_id="a01000000000000AAA")
    )
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Upload account plan",
                "account_plan_data": {
                    "AccountPlan__c": "001000000000000AAA",
                    "Plan_Year__c": "2026",
                },
                "approved": False,
                "retry_count": 0,
                "security_notes": [],
            }
        )
    )

    assert state["status"] == "needs_approval"
    assert state["intent"] == "upload_account_plan"
    assert state["readiness_score"] == 25
    assert "Plan year: 2026" in state["upload_preview"]


def test_upload_executes_after_approval() -> None:
    graph = build_graph(
        upload_handler=lambda payload: UploadResult(success=True, action="upserted", record_id="a01000000000000AAA")
    )
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Upload account plan",
                "account_plan_data": {
                    "AccountPlan__c": "001000000000000AAA",
                    "Plan_Year__c": "2026",
                },
                "approved": True,
                "retry_count": 0,
                "security_notes": [],
            }
        )
    )

    assert state["status"] == "uploaded"
    assert state["upload_record_id"] == "a01000000000000AAA"
    assert "Uploaded: Account: 001000000000000AAA" in state["final_response"]
