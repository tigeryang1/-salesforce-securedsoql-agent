from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.services.contracts import (
    FieldDescription,
    ObjectDescription,
    QueryResult,
    SalesforceToolAdapter,
    UploadResult,
)
from app.utils.security import extract_selected_fields


class CallableSalesforceToolAdapter(SalesforceToolAdapter):
    """Thin adapter around async callables that talk to the actual MCP transport."""

    def __init__(
        self,
        *,
        describe_fn: Callable[[str], Awaitable[dict[str, Any]]],
        query_fn: Callable[[str], Awaitable[dict[str, Any]]],
        upload_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self._describe_fn = describe_fn
        self._query_fn = query_fn
        self._upload_fn = upload_fn

    async def describe_salesforce_object(self, sobject_name: str) -> ObjectDescription:
        raw = await self._describe_fn(sobject_name)
        fields = [
            FieldDescription(
                name=item["name"],
                label=item.get("label", item["name"]),
                type=item.get("type", "string"),
                reference_to=item.get("referenceTo", []),
            )
            for item in raw.get("fields", [])
        ]
        return ObjectDescription(
            name=raw["name"],
            label=raw.get("label", raw["name"]),
            key_prefix=raw.get("keyPrefix"),
            fields=fields,
        )

    async def query_salesforce(self, soql_query: str) -> QueryResult:
        raw = await self._query_fn(soql_query)
        requested_fields = extract_selected_fields(soql_query)
        records = raw.get("records", [])
        returned_fields = sorted({key for row in records for key in row.keys()})
        filtered_fields = (
            [field for field in requested_fields if field not in returned_fields]
            if records
            else []
        )
        security_notes = []
        if filtered_fields:
            security_notes.append(
                "Some requested fields were omitted by Salesforce security policy."
            )
        return QueryResult(
            success=bool(raw.get("success")),
            records=records,
            record_count=int(raw.get("recordCount", 0)),
            timestamp=raw.get("timestamp"),
            error=raw.get("error"),
            status_code=raw.get("statusCode"),
            requested_fields=requested_fields,
            returned_fields=returned_fields,
            filtered_fields=filtered_fields,
            soql_query=soql_query,
            security_notes=security_notes,
        )

    async def upload_account_plan(self, account_plan_data: dict[str, Any]) -> UploadResult:
        raw = await self._upload_fn(account_plan_data)
        return UploadResult(
            success=bool(raw.get("success")),
            record_id=raw.get("id") or raw.get("recordId"),
            action=raw.get("action"),
            error=raw.get("error"),
            status_code=raw.get("statusCode"),
            raw=raw,
        )


class InMemorySalesforceToolAdapter(SalesforceToolAdapter):
    """Simple adapter for tests and local graph development."""

    def __init__(
        self,
        *,
        describes: dict[str, ObjectDescription] | None = None,
        query_handler: Callable[[str], QueryResult] | None = None,
        upload_handler: Callable[[dict[str, Any]], UploadResult] | None = None,
    ) -> None:
        self._describes = describes or {}
        self._query_handler = query_handler or (lambda _query: QueryResult(success=True))
        self._upload_handler = upload_handler or (
            lambda _payload: UploadResult(success=True, action="created", record_id="a01234567890123456")
        )

    async def describe_salesforce_object(self, sobject_name: str) -> ObjectDescription:
        return self._describes[sobject_name]

    async def query_salesforce(self, soql_query: str) -> QueryResult:
        result = self._query_handler(soql_query)
        if not result.requested_fields:
            result.requested_fields = extract_selected_fields(soql_query)
        if not result.filtered_fields and result.requested_fields and result.returned_fields:
            result.filtered_fields = [field for field in result.requested_fields if field not in result.returned_fields]
        result.soql_query = soql_query
        return result

    async def upload_account_plan(self, account_plan_data: dict[str, Any]) -> UploadResult:
        return self._upload_handler(account_plan_data)
