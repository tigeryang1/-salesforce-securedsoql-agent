from __future__ import annotations

from app.graph.state import AgentState
from app.services.account_plan import build_account_plan_draft, validate_account_plan_payload


def write_validate_node(state: AgentState) -> AgentState:
    original_payload = dict(state.get("account_plan_data") or {})
    draft = build_account_plan_draft(
        payload=dict(state.get("account_plan_data") or {}),
        user_input=state.get("user_input", ""),
        resolved_account_id=state.get("resolved_account_id"),
        resolved_account_name=state.get("resolved_account_name"),
    )
    payload = draft.payload
    if _needs_business_draft_input(original_payload, draft.draft_sections):
        return {
            "status": "needs_input",
            "write_validation_errors": [],
            "missing_inputs": draft.missing_inputs,
            "account_plan_data": payload,
            "draft_sections": draft.draft_sections,
            "readiness_score": draft.readiness_score,
            "readiness_label": draft.readiness_label,
            "upload_preview": draft.upload_preview,
            "next_question": draft.next_question,
            "guidance": [
                *state.get("guidance", []),
                *draft.guidance,
                "I have the account foundation, but I still need business plan details before this draft should be approved.",
            ],
        }
    validation = validate_account_plan_payload(payload)
    if not validation.valid:
        return {
            "status": "needs_input",
            "write_validation_errors": validation.errors,
            "missing_inputs": _derive_missing_inputs(validation.errors, draft.missing_inputs),
            "account_plan_data": payload,
            "draft_sections": draft.draft_sections,
            "readiness_score": draft.readiness_score,
            "readiness_label": draft.readiness_label,
            "upload_preview": draft.upload_preview,
            "next_question": draft.next_question,
            "guidance": [*state.get("guidance", []), *draft.guidance],
        }
    return {
        "status": "validated",
        "write_validation_errors": [],
        "account_plan_data": payload,
        "draft_sections": draft.draft_sections,
        "readiness_score": draft.readiness_score,
        "readiness_label": draft.readiness_label,
        "upload_preview": draft.upload_preview,
        "next_question": draft.next_question,
        "guidance": [*state.get("guidance", []), *draft.guidance],
    }


def _derive_missing_inputs(errors: list[str], draft_missing_inputs: list[str]) -> list[str]:
    missing_inputs: list[str] = []
    for error in errors:
        if "AccountPlan__c" in error:
            missing_inputs.append("account")
        elif "Plan_Year__c" in error:
            missing_inputs.append("plan_year")
        elif "Quarterly spend estimates" in error:
            missing_inputs.append("quarterly_spend_breakdown")
    for item in draft_missing_inputs:
        if item not in missing_inputs:
            missing_inputs.append(item)
    return missing_inputs


def _needs_business_draft_input(
    original_payload: dict[str, object],
    draft_sections: list[dict[str, object]],
) -> bool:
    if original_payload:
        return False
    non_foundation_sections = [section for section in draft_sections if section["name"] != "foundation"]
    return not any(section["complete"] for section in non_foundation_sections)
