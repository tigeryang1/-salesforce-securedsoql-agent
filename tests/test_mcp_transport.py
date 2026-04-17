import asyncio

from app.services.contracts import ObjectDescription
from app.services.mcp_transport import build_streamable_http_adapter


class FakeTool:
    def __init__(self, name: str, result):
        self.name = name
        self._result = result

    async def ainvoke(self, payload):
        if callable(self._result):
            return self._result(payload)
        return self._result


class FakeClient:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self):
        return self._tools


async def fake_client_factory(*, mcp_url: str, session_token: str):
    return FakeClient(
        [
            FakeTool(
                "describe_salesforce_object",
                {
                    "name": "Account",
                    "label": "Account",
                    "fields": [{"name": "Id", "label": "Account ID", "type": "id"}],
                },
            ),
            FakeTool(
                "query_salesforce",
                {
                    "success": True,
                    "records": [{"Id": "001000000000000AAA"}],
                    "recordCount": 1,
                },
            ),
            FakeTool(
                "upload_account_plan",
                {"success": True, "recordId": "a01000000000000AAA", "action": "upserted"},
            ),
        ]
    )


def test_build_streamable_http_adapter_maps_tools() -> None:
    adapter = asyncio.run(
        build_streamable_http_adapter(
            mcp_url="http://127.0.0.1:8000/mcp",
            session_token="tok_demo",
            client_factory=fake_client_factory,
        )
    )

    description = asyncio.run(adapter.describe_salesforce_object("Account"))
    query_result = asyncio.run(adapter.query_salesforce("SELECT Id FROM Account LIMIT 1"))
    upload_result = asyncio.run(adapter.upload_account_plan({"AccountPlan__c": "001000000000000AAA", "Plan_Year__c": "2026"}))

    assert description.name == "Account"
    assert description.fields[0].name == "Id"
    assert query_result.success is True
    assert query_result.record_count == 1
    assert upload_result.record_id == "a01000000000000AAA"
