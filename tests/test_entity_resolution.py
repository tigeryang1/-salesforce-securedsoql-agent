import asyncio

from app.graph.builder import build_agent_graph
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


def test_ambiguous_account_resolution_returns_needs_input() -> None:
    def query_handler(query: str) -> QueryResult:
        normalized = query.lower()
        if "from account where name =" in normalized:
            return QueryResult(success=True, records=[], record_count=0)
        if "from account where name like '%acme%'" in normalized:
            return QueryResult(
                success=True,
                records=[
                    {"Id": "001000000000000AAA", "Name": "Acme Corp", "Industry": "Retail"},
                    {"Id": "001000000000000BBB", "Name": "Acme Holdings", "Industry": "Retail"},
                ],
                record_count=2,
                returned_fields=["Id", "Name", "Industry"],
            )
        return QueryResult(success=True)

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
        upload_handler=lambda payload: UploadResult(success=True, action="upserted", record_id="a01000000000000AAA"),
    )
    graph = build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Show me Acme priorities",
                "approved": False,
                "retry_count": 0,
                "security_notes": [],
                "guidance": [],
            }
        )
    )

    assert state["status"] == "needs_input"
    assert state["missing_inputs"] == ["account_selection"]
    assert len(state["candidate_accounts"]) == 2
