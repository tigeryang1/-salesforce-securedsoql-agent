from app.services.contracts import QueryResult
from app.services.salesforce_tools import InMemorySalesforceToolAdapter


async def _query(adapter: InMemorySalesforceToolAdapter):
    return await adapter.query_salesforce("SELECT Id, Name, Email FROM Contact LIMIT 10")


def test_filtered_fields_are_detected() -> None:
    adapter = InMemorySalesforceToolAdapter(
        query_handler=lambda _query: QueryResult(
            success=True,
            records=[{"Id": "003000000000000AAA", "Name": "Ada"}],
            record_count=1,
            returned_fields=["Id", "Name"],
        )
    )
    result = __import__("asyncio").run(_query(adapter))
    assert result.filtered_fields == ["Email"]
