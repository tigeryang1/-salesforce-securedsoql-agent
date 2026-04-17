from __future__ import annotations

import argparse
import asyncio
import json
import os

from app.graph.builder import build_agent_graph
from app.services.contracts import FieldDescription, ObjectDescription, QueryResult, UploadResult
from app.services.llm import AgentReasoner, build_chat_model
from app.services.mcp_transport import build_streamable_http_adapter
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


def build_demo_graph():
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
                        "Annual_Pinterest_Goals_Strategy__c": "Grow demand",
                        "Business_Challenges_Priorities__c": "Improve efficiency",
                        "This_Year_Annual_Spend_Est__c": "100000",
                    }
                ],
                record_count=1,
                returned_fields=[
                    "Annual_Pinterest_Goals_Strategy__c",
                    "Business_Challenges_Priorities__c",
                    "This_Year_Annual_Spend_Est__c",
                ],
            )
        return QueryResult(
            success=True,
            records=[{"Id": "001000000000000AAA", "Name": "Acme", "Industry": "Retail"}],
            record_count=1,
            returned_fields=["Id", "Name", "Industry"],
        )

    adapter = InMemorySalesforceToolAdapter(
        describes={
            "Account": ObjectDescription(
                name="Account",
                label="Account",
                key_prefix="001",
                fields=[
                    FieldDescription(name="Id", label="Account ID", type="id"),
                    FieldDescription(name="Name", label="Account Name", type="string"),
                    FieldDescription(name="Industry", label="Industry", type="string"),
                    FieldDescription(name="OwnerId", label="Owner", type="reference", reference_to=["User"]),
                    FieldDescription(name="CreatedDate", label="Created Date", type="datetime"),
                ],
            ),
            "Account_Plan__c": ObjectDescription(
                name="Account_Plan__c",
                label="Account Plan",
                key_prefix="a01",
                fields=[
                    FieldDescription(name="AccountPlan__c", label="Account", type="reference", reference_to=["Account"]),
                    FieldDescription(name="Plan_Year__c", label="Plan Year", type="picklist"),
                    FieldDescription(name="Annual_Pinterest_Goals_Strategy__c", label="Goals Strategy", type="textarea"),
                    FieldDescription(name="Business_Challenges_Priorities__c", label="Business Priorities", type="textarea"),
                    FieldDescription(name="Q1_Spend_Estimate__c", label="Q1 Spend", type="currency"),
                    FieldDescription(name="Q2_Spend_Estimate__c", label="Q2 Spend", type="currency"),
                    FieldDescription(name="Q3_Spend_Estimate__c", label="Q3 Spend", type="currency"),
                    FieldDescription(name="Q4_Spend_Estimate__c", label="Q4 Spend", type="currency"),
                    FieldDescription(name="This_Year_Annual_Spend_Est__c", label="Annual Spend", type="currency"),
                ],
            ),
        },
        query_handler=query_handler,
        upload_handler=lambda _payload: UploadResult(
            success=True,
            action="upserted",
            record_id="a01000000000000AAA",
        ),
    )
    return build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=None))


async def _run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, dest="user_input")
    parser.add_argument("--soql")
    parser.add_argument("--object")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--account-plan-json")
    parser.add_argument("--mcp-url")
    parser.add_argument("--session-token")
    parser.add_argument("--use-demo-adapter", action="store_true")
    parser.add_argument("--smoke-live-mcp", action="store_true")
    args = parser.parse_args()

    payload = None
    if args.account_plan_json:
        payload = json.loads(args.account_plan_json)

    if args.smoke_live_mcp:
        if not args.mcp_url:
            raise ValueError("--smoke-live-mcp requires --mcp-url")
        adapter = await build_streamable_http_adapter(
            mcp_url=args.mcp_url,
            session_token=args.session_token or "change-me",
        )
        description = await adapter.describe_salesforce_object("Account")
        print(json.dumps({"status": "ok", "object": description.name, "field_count": len(description.fields)}, indent=2))
        return

    if args.use_demo_adapter or not args.mcp_url:
        graph = build_demo_graph()
    else:
        adapter = await build_streamable_http_adapter(
            mcp_url=args.mcp_url,
            session_token=args.session_token or "change-me",
        )
        model_name = os.environ.get("AGENT_MODEL", "")
        try:
            model = build_chat_model(model_name) if model_name else None
        except Exception:
            model = None
        graph = build_agent_graph(adapter=adapter, reasoner=AgentReasoner(model=model))
    result = await graph.ainvoke(
        {
            "user_input": args.user_input,
            "soql_query": args.soql,
            "target_object": args.object,
            "account_plan_data": payload,
            "approved": args.approved,
            "retry_count": 0,
            "security_notes": [],
        }
    )
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
