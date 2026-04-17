import asyncio

from app.graph.builder import build_agent_graph
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


def build_graph():
    def query_handler(query: str) -> QueryResult:
        normalized = query.lower()
        if "from account where name like '%nike%'" in normalized:
            return QueryResult(
                success=True,
                records=[{"Id": "001000000000000AAA", "Name": "Nike", "Industry": "Retail"}],
                record_count=1,
                returned_fields=["Id", "Name", "Industry"],
            )
        if "from account_plan__c" in normalized:
            return QueryResult(
                success=True,
                records=[
                    {
                        "Business_Challenges_Priorities__c": "Improve measurement confidence",
                        "Opportunity_for_Growth__c": "Expand shopping campaigns",
                    }
                ],
                record_count=1,
                returned_fields=["Business_Challenges_Priorities__c", "Opportunity_for_Growth__c"],
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
                    FieldDescription(name="Business_Challenges_Priorities__c", label="Priorities", type="textarea"),
                    FieldDescription(name="Opportunity_for_Growth__c", label="Growth", type="textarea"),
                ],
            ),
        },
        query_handler=query_handler,
        upload_handler=lambda payload: UploadResult(success=True, action="upserted", record_id="a01000000000000AAA"),
    )
    return build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))


def test_business_query_resolves_account_and_builds_account_plan_query() -> None:
    graph = build_graph()
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Show me Nike client priorities and growth opportunities",
                "approved": False,
                "retry_count": 0,
                "security_notes": [],
                "guidance": [],
            }
        )
    )

    assert state["resolved_account_name"] == "Nike"
    assert state["target_object"] == "Account_Plan__c"
    assert "Business_Challenges_Priorities__c" in state["soql_query"]
    assert state["record_count"] == 1


def test_business_write_returns_guidance_when_required_inputs_are_missing() -> None:
    graph = build_graph()
    state = asyncio.run(
        graph.ainvoke(
            {
                "user_input": "Help me prepare a 2026 account plan for Nike",
                "approved": False,
                "retry_count": 0,
                "security_notes": [],
                "guidance": [],
            }
        )
    )

    assert state["status"] == "needs_input"
    assert "goals_or_strategy" in state["missing_inputs"]
    assert state["account_plan_data"]["Plan_Year__c"] == "2026"
    assert any(section["name"] == "foundation" and section["complete"] for section in state["draft_sections"])
    assert state["readiness_score"] == 25
    assert state["readiness_label"] == "early"
