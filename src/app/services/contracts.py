from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class FieldDescription:
    name: str
    label: str
    type: str
    reference_to: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ObjectDescription:
    name: str
    label: str
    key_prefix: str | None
    fields: list[FieldDescription]


@dataclass(slots=True)
class QueryResult:
    success: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    record_count: int = 0
    timestamp: str | None = None
    error: str | None = None
    status_code: int | None = None
    requested_fields: list[str] = field(default_factory=list)
    returned_fields: list[str] = field(default_factory=list)
    filtered_fields: list[str] = field(default_factory=list)
    soql_query: str | None = None
    security_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UploadResult:
    success: bool
    record_id: str | None = None
    action: str | None = None
    error: str | None = None
    status_code: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SalesforceToolAdapter(Protocol):
    async def describe_salesforce_object(self, sobject_name: str) -> ObjectDescription:
        ...

    async def query_salesforce(self, soql_query: str) -> QueryResult:
        ...

    async def upload_account_plan(self, account_plan_data: dict[str, Any]) -> UploadResult:
        ...
