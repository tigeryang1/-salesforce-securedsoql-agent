from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    intent: Literal["describe", "query", "upload_account_plan", "unknown"]
    status: str
    approved: bool
    soql_query: str | None
    recovered_soql_query: str | None
    target_object: str | None
    account_plan_data: dict[str, Any] | None
    schema_fields: list[dict[str, Any]]
    schema_label: str | None
    record_count: int
    records: list[dict[str, Any]]
    filtered_fields: list[str]
    security_notes: list[str]
    query_error: str | None
    query_status_code: int | None
    retry_count: int
    write_validation_errors: list[str]
    upload_action: str | None
    upload_record_id: str | None
    business_goal: str | None
    business_terms: list[str]
    candidate_fields: list[str]
    account_name: str | None
    resolved_account_id: str | None
    resolved_account_name: str | None
    candidate_accounts: list[dict[str, Any]]
    missing_inputs: list[str]
    guidance: list[str]
    draft_sections: list[dict[str, Any]]
    business_summary: str | None
    readiness_score: int
    readiness_label: str | None
    upload_preview: str | None
    next_question: str | None
    final_response: str
