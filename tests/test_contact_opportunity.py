"""Tests for Contact and Opportunity object support (Phase 5)
and LLM-backed reasoning fallback (Phase 4)."""

import asyncio

from app.graph.builder import build_agent_graph
from app.services.business_guide import (
    CONTACT_SIGNALS,
    OPPORTUNITY_SIGNALS,
    _default_fields_for_object,
    _detect_target_object,
    _heuristic_interpret,
    interpret_business_request,
)
from app.services.contracts import (
    FieldDescription,
    ObjectDescription,
    QueryResult,
    UploadResult,
)
from app.services.llm import AgentReasoner
from app.services.salesforce_tools import InMemorySalesforceToolAdapter
from app.services.summary import summarize_query_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_multi_object_adapter(query_handler=None):
    return InMemorySalesforceToolAdapter(
        describes={
            "Account": ObjectDescription(
                name="Account", label="Account", key_prefix="001",
                fields=[
                    FieldDescription(name="Id", label="ID", type="id"),
                    FieldDescription(name="Name", label="Name", type="string"),
                    FieldDescription(name="Industry", label="Industry", type="string"),
                ],
            ),
            "Contact": ObjectDescription(
                name="Contact", label="Contact", key_prefix="003",
                fields=[
                    FieldDescription(name="Id", label="ID", type="id"),
                    FieldDescription(name="Name", label="Full Name", type="string"),
                    FieldDescription(name="Email", label="Email", type="email"),
                    FieldDescription(name="Phone", label="Phone", type="phone"),
                    FieldDescription(name="Title", label="Title", type="string"),
                    FieldDescription(name="AccountId", label="Account ID", type="reference", reference_to=["Account"]),
                ],
            ),
            "Opportunity": ObjectDescription(
                name="Opportunity", label="Opportunity", key_prefix="006",
                fields=[
                    FieldDescription(name="Id", label="ID", type="id"),
                    FieldDescription(name="Name", label="Name", type="string"),
                    FieldDescription(name="StageName", label="Stage", type="picklist"),
                    FieldDescription(name="Amount", label="Amount", type="currency"),
                    FieldDescription(name="CloseDate", label="Close Date", type="date"),
                    FieldDescription(name="AccountId", label="Account ID", type="reference", reference_to=["Account"]),
                ],
            ),
            "Account_Plan__c": ObjectDescription(
                name="Account_Plan__c", label="Account Plan", key_prefix="a01",
                fields=[
                    FieldDescription(name="AccountPlan__c", label="Account", type="reference"),
                    FieldDescription(name="Plan_Year__c", label="Plan Year", type="picklist"),
                ],
            ),
        },
        query_handler=query_handler,
        upload_handler=lambda _: UploadResult(success=True, action="upserted", record_id="a01x"),
    )


def _build_graph(query_handler=None):
    adapter = _build_multi_object_adapter(query_handler)
    return build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))


# ---------------------------------------------------------------------------
# Phase 5a: Signal detection
# ---------------------------------------------------------------------------

class TestContactOpportunitySignals:
    def test_contact_signals_exist(self):
        assert "contact" in CONTACT_SIGNALS
        assert "email" in CONTACT_SIGNALS
        assert "stakeholder" in CONTACT_SIGNALS

    def test_opportunity_signals_exist(self):
        assert "opportunity" in OPPORTUNITY_SIGNALS
        assert "deal" in OPPORTUNITY_SIGNALS
        assert "pipeline" in OPPORTUNITY_SIGNALS

    def test_detect_contact(self):
        assert _detect_target_object("show me contacts for nike") == "Contact"
        assert _detect_target_object("find the email for the decision maker") == "Contact"

    def test_detect_opportunity(self):
        assert _detect_target_object("show open deals") == "Opportunity"
        assert _detect_target_object("what is the pipeline for acme?") == "Opportunity"

    def test_detect_account_still_works(self):
        assert _detect_target_object("find the customer account") == "Account"

    def test_detect_account_plan_still_works(self):
        assert _detect_target_object("show the account plan goals") == "Account_Plan__c"

    def test_detect_none_for_ambiguous(self):
        assert _detect_target_object("hello world") is None


# ---------------------------------------------------------------------------
# Phase 5a: Business interpretation for Contact / Opportunity
# ---------------------------------------------------------------------------

class TestBusinessInterpretation:
    def test_interpret_contact_request(self):
        result = interpret_business_request("Find contacts at Nike")
        assert result.target_object == "Contact"

    def test_interpret_opportunity_request(self):
        result = interpret_business_request("Show me open deals for Acme")
        assert result.target_object == "Opportunity"

    def test_interpret_still_returns_account(self):
        result = interpret_business_request("Find the customer account for Nike")
        assert result.target_object == "Account"

    def test_heuristic_interpret_contact(self):
        result = _heuristic_interpret("Show contacts at Nike")
        assert result.target_object == "Contact"


# ---------------------------------------------------------------------------
# Phase 5b: Default fields
# ---------------------------------------------------------------------------

class TestDefaultFields:
    def test_contact_default_fields(self):
        fields = _default_fields_for_object("Contact")
        assert "Id" in fields
        assert "Name" in fields
        assert "Email" in fields
        assert "Phone" in fields
        assert "Title" in fields
        assert "AccountId" in fields

    def test_opportunity_default_fields(self):
        fields = _default_fields_for_object("Opportunity")
        assert "Id" in fields
        assert "Name" in fields
        assert "StageName" in fields
        assert "Amount" in fields
        assert "CloseDate" in fields
        assert "AccountId" in fields

    def test_account_default_fields_unchanged(self):
        fields = _default_fields_for_object("Account")
        assert "Id" in fields
        assert "Name" in fields


# ---------------------------------------------------------------------------
# Phase 5c: Summary groups
# ---------------------------------------------------------------------------

class TestSummaryGroups:
    def test_contact_summary(self):
        state = {
            "target_object": "Contact",
            "records": [{
                "Name": "Jane Smith",
                "Email": "jane@example.com",
                "Title": "VP Marketing",
            }],
        }
        result = summarize_query_result(state)
        assert result is not None
        assert "Jane Smith" in result
        assert "jane@example.com" in result
        assert "VP Marketing" in result

    def test_opportunity_summary(self):
        state = {
            "target_object": "Opportunity",
            "records": [{
                "Name": "Q1 Deal",
                "StageName": "Proposal",
                "Amount": "250000",
            }],
        }
        result = summarize_query_result(state)
        assert result is not None
        assert "Q1 Deal" in result
        assert "Proposal" in result
        assert "250000" in result

    def test_contact_summary_empty_records(self):
        state = {"target_object": "Contact", "records": []}
        assert summarize_query_result(state) is None

    def test_opportunity_summary_empty_records(self):
        state = {"target_object": "Opportunity", "records": []}
        assert summarize_query_result(state) is None


# ---------------------------------------------------------------------------
# Phase 5d: End-to-end graph tests
# ---------------------------------------------------------------------------

class TestContactGraph:
    def test_describe_contact(self):
        graph = _build_graph()
        state = asyncio.run(graph.ainvoke({
            "user_input": "Describe Contact",
            "target_object": "Contact",
            "approved": False,
            "retry_count": 0,
            "security_notes": [],
        }))
        assert state["intent"] == "describe"
        assert state["target_object"] == "Contact"
        assert len(state.get("schema_fields", [])) > 0

    def test_query_contact(self):
        def handler(query: str) -> QueryResult:
            return QueryResult(
                success=True,
                records=[{"Id": "003x", "Name": "Alice", "Email": "alice@co.com"}],
                record_count=1,
                returned_fields=["Id", "Name", "Email"],
            )

        graph = _build_graph(query_handler=handler)
        state = asyncio.run(graph.ainvoke({
            "user_input": "Find contacts at Acme",
            "soql_query": "SELECT Id, Name, Email FROM Contact LIMIT 5",
            "approved": False,
            "retry_count": 0,
            "security_notes": [],
        }))
        assert state["record_count"] == 1
        assert state["records"][0]["Name"] == "Alice"


class TestOpportunityGraph:
    def test_describe_opportunity(self):
        graph = _build_graph()
        state = asyncio.run(graph.ainvoke({
            "user_input": "Describe Opportunity",
            "target_object": "Opportunity",
            "approved": False,
            "retry_count": 0,
            "security_notes": [],
        }))
        assert state["intent"] == "describe"
        assert state["target_object"] == "Opportunity"
        assert len(state.get("schema_fields", [])) > 0

    def test_query_opportunity(self):
        def handler(query: str) -> QueryResult:
            return QueryResult(
                success=True,
                records=[{"Id": "006x", "Name": "Big Deal", "StageName": "Closed Won", "Amount": "500000"}],
                record_count=1,
                returned_fields=["Id", "Name", "StageName", "Amount"],
            )

        graph = _build_graph(query_handler=handler)
        state = asyncio.run(graph.ainvoke({
            "user_input": "Show deals for Acme",
            "soql_query": "SELECT Id, Name, StageName, Amount FROM Opportunity LIMIT 5",
            "approved": False,
            "retry_count": 0,
            "security_notes": [],
        }))
        assert state["record_count"] == 1
        assert state["records"][0]["StageName"] == "Closed Won"


# ---------------------------------------------------------------------------
# Phase 4: Heuristic fallback (model=None) still works
# ---------------------------------------------------------------------------

class TestHeuristicFallback:
    def test_classify_intent_query_without_model(self):
        reasoner = AgentReasoner(model=None)
        decision = reasoner.classify_intent(
            user_input="Show accounts",
            soql_query=None,
            sobject_name=None,
            account_plan_data=None,
        )
        assert decision.intent == "query"

    def test_classify_intent_describe_without_model(self):
        reasoner = AgentReasoner(model=None)
        decision = reasoner.classify_intent(
            user_input="Describe the schema for Contact",
            soql_query=None,
            sobject_name=None,
            account_plan_data=None,
        )
        assert decision.intent == "describe"

    def test_classify_intent_upload_without_model(self):
        reasoner = AgentReasoner(model=None)
        decision = reasoner.classify_intent(
            user_input="Create account plan for Nike",
            soql_query=None,
            sobject_name=None,
            account_plan_data=None,
        )
        assert decision.intent == "upload_account_plan"

    def test_compose_response_without_model(self):
        reasoner = AgentReasoner(model=None)
        result = reasoner.compose_response({"status": "completed", "intent": "query", "record_count": 3})
        assert "3" in result

    def test_business_interpret_without_model(self):
        result = interpret_business_request("Show spend for Nike", model=None)
        assert "spend" in result.business_terms
        assert result.account_name == "Nike"
