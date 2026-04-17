from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from app.utils.salesforce_ids import looks_like_salesforce_id


REQUIRED_FIELDS = ("AccountPlan__c", "Plan_Year__c")
QUARTER_FIELDS = (
    "Q1_Spend_Estimate__c",
    "Q2_Spend_Estimate__c",
    "Q3_Spend_Estimate__c",
    "Q4_Spend_Estimate__c",
)
REFERENCE_FIELDS = (
    "AccountPlan__c",
    "Primary_Contact__c",
    "Budget_Decision_Maker__c",
    "Highest_Level_of_Contact__c",
    "Competitor_1__c",
    "Competitor_2__c",
    "Competitor_3__c",
)


@dataclass(slots=True)
class AccountPlanValidation:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AccountPlanDraft:
    payload: dict[str, Any]
    draft_sections: list[dict[str, Any]]
    missing_inputs: list[str]
    guidance: list[str]
    readiness_score: int
    readiness_label: str
    upload_preview: str
    next_question: str | None


def _to_decimal(value: Any) -> Decimal:
    if value in (None, "", False):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"Invalid numeric value: {value}") from None


def validate_account_plan_payload(payload: dict[str, Any]) -> AccountPlanValidation:
    errors: list[str] = []

    for field_name in REQUIRED_FIELDS:
        if not payload.get(field_name):
            errors.append(f"Missing required field `{field_name}`.")

    account_id = payload.get("AccountPlan__c")
    if account_id and not looks_like_salesforce_id(str(account_id)):
        errors.append("`AccountPlan__c` must be an 18-character Salesforce ID.")

    annual = payload.get("This_Year_Annual_Spend_Est__c")
    if annual not in (None, ""):
        try:
            annual_value = _to_decimal(annual)
            quarter_total = sum(_to_decimal(payload.get(field_name)) for field_name in QUARTER_FIELDS)
            if quarter_total != annual_value:
                errors.append(
                    "Quarterly spend estimates must sum to `This_Year_Annual_Spend_Est__c`."
                )
        except ValueError as exc:
            errors.append(str(exc))

    for field_name in REFERENCE_FIELDS:
        reference_value = payload.get(field_name)
        if reference_value and not looks_like_salesforce_id(str(reference_value)):
            errors.append(f"`{field_name}` must be an 18-character Salesforce ID.")

    return AccountPlanValidation(valid=not errors, errors=errors)


def build_account_plan_draft(
    *,
    payload: dict[str, Any],
    user_input: str,
    resolved_account_id: str | None,
    resolved_account_name: str | None,
) -> AccountPlanDraft:
    draft_payload = dict(payload)
    guidance: list[str] = []
    if not draft_payload.get("AccountPlan__c") and resolved_account_id:
        draft_payload["AccountPlan__c"] = resolved_account_id
        if resolved_account_name:
            guidance.append(f"I linked the draft to Account `{resolved_account_name}`.")

    if not draft_payload.get("Plan_Year__c"):
        year = _extract_plan_year(user_input)
        if year:
            draft_payload["Plan_Year__c"] = year
            guidance.append(f"I inferred plan year `{year}` from the request.")

    draft_sections = _build_draft_sections(draft_payload)
    missing_inputs: list[str] = []
    for section in draft_sections:
        if not section["complete"]:
            missing_inputs.extend(section["missing_inputs"])
    readiness_score, readiness_label = _score_draft(draft_sections)
    upload_preview = _build_upload_preview(draft_payload, draft_sections, resolved_account_name)
    next_question = recommend_next_question(draft_sections, _unique(missing_inputs))

    return AccountPlanDraft(
        payload=draft_payload,
        draft_sections=draft_sections,
        missing_inputs=_unique(missing_inputs),
        guidance=guidance,
        readiness_score=readiness_score,
        readiness_label=readiness_label,
        upload_preview=upload_preview,
        next_question=next_question,
    )


def _build_draft_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [
        _section(
            "foundation",
            payload,
            {
                "AccountPlan__c": "account",
                "Plan_Year__c": "plan_year",
            },
        ),
        _section(
            "strategy",
            payload,
            {
                "Annual_Pinterest_Goals_Strategy__c": "goals_or_strategy",
                "Business_Challenges_Priorities__c": "client_priorities",
                "Opportunity_for_Growth__c": "growth_opportunities",
            },
            require_any=True,
        ),
        _section(
            "client_objectives",
            payload,
            {
                "CEO_Strategic_Priorities__c": "ceo_priorities",
                "Recent_News__c": "recent_news",
            },
            require_any=True,
        ),
        _section(
            "media_marketing",
            payload,
            {
                "Pinterest_Account_Health__c": "account_health",
                "CMO_Marketing_Goals_Approach__c": "marketing_goals",
                "Measurement__c": "measurement_approach",
                "Creative_Strategy__c": "creative_strategy",
                "Agency__c": "agency",
            },
            require_any=True,
        ),
        _section(
            "key_moments",
            payload,
            {
                "Q1_Events__c": "q1_events",
                "Q2_Events__c": "q2_events",
                "Q3_Events__c": "q3_events",
                "Q4_Events__c": "q4_events",
            },
            require_any=True,
        ),
        _section(
            "value_proposition",
            payload,
            {
                "Keys_to_Unlocking_Growth__c": "keys_to_growth",
                "Biggest_Opportunities_to_unlock_growth__c": "biggest_opportunities",
            },
            require_any=True,
        ),
        _section(
            "tactics",
            payload,
            {
                "Q1_Objectives__c": "q1_objectives",
                "Q2_Objectives__c": "q2_objectives",
                "Q3_Objectives__c": "q3_objectives",
                "Q4_Objectives__c": "q4_objectives",
            },
            require_any=True,
        ),
        _section(
            "spend_plan",
            payload,
            {
                "This_Year_Annual_Spend_Est__c": "annual_spend",
                "Plan_Year_Goals__c": "revenue_goals",
                "Q1_Spend_Estimate__c": "q1_spend",
                "Q2_Spend_Estimate__c": "q2_spend",
                "Q3_Spend_Estimate__c": "q3_spend",
                "Q4_Spend_Estimate__c": "q4_spend",
            },
            require_any=True,
        ),
        _section(
            "stakeholders",
            payload,
            {
                "Leadership__c": "leadership_context",
                "Relationship_Map__c": "relationship_map",
                "Primary_Contact__c": "primary_contact",
                "Budget_Decision_Maker__c": "budget_owner",
                "Highest_Level_of_Contact__c": "executive_contact",
                "Other_Asks__c": "other_asks",
            },
            require_any=True,
        ),
        _section(
            "competitive",
            payload,
            {
                "Competitive_Landscape__c": "competitive_landscape",
                "Competitor_1__c": "competitor_1",
                "Competitor_2__c": "competitor_2",
                "Competitor_3__c": "competitor_3",
            },
            require_any=True,
        ),
        _section(
            "measurement_vendors",
            payload,
            {
                "Measurement_Vendors__c": "measurement_vendors",
                "Q2_Measurement_Vendors__c": "q2_measurement_vendors",
                "Q3_Measurement_Vendors__c": "q3_measurement_vendors",
                "Q4_Measurement_Vendors__c": "q4_measurement_vendors",
            },
            require_any=True,
        ),
        _section(
            "review_cadence",
            payload,
            {
                "Planning_Cadence__c": "planning_cadence",
                "Touchbase_Frequency__c": "touchbase_frequency",
                "Q1_Upcoming_Meetings__c": "q1_meetings",
                "Q2_Upcoming_Meetings__c": "q2_meetings",
                "Q3_Upcoming_Meetings__c": "q3_meetings",
                "Q4_Upcoming_Meetings__c": "q4_meetings",
            },
            require_any=True,
        ),
    ]
    return sections


def _section(
    name: str,
    payload: dict[str, Any],
    fields: dict[str, str],
    *,
    require_any: bool = False,
) -> dict[str, Any]:
    filled = [friendly for field_name, friendly in fields.items() if payload.get(field_name) not in (None, "")]
    if require_any:
        complete = bool(filled)
        missing = [] if complete else list(fields.values())
    else:
        missing = [friendly for field_name, friendly in fields.items() if payload.get(field_name) in (None, "")]
        complete = not missing
    return {
        "name": name,
        "complete": complete,
        "filled_inputs": filled,
        "missing_inputs": missing,
    }


def _extract_plan_year(user_input: str) -> str | None:
    match = re.search(r"\b(20\d{2})\b", user_input)
    if not match:
        return None
    return match.group(1)


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _score_draft(draft_sections: list[dict[str, Any]]) -> tuple[int, str]:
    if not draft_sections:
        return 0, "not_started"
    weights = {
        "foundation": 25,
        "strategy": 20,
        "client_objectives": 3,
        "media_marketing": 5,
        "key_moments": 3,
        "value_proposition": 4,
        "tactics": 5,
        "spend_plan": 15,
        "stakeholders": 10,
        "competitive": 4,
        "measurement_vendors": 3,
        "review_cadence": 3,
    }
    score = 0.0
    for section in draft_sections:
        weight = weights.get(section["name"], 0)
        filled = len(section["filled_inputs"])
        total = filled + len(section["missing_inputs"])
        fraction = 1.0 if total == 0 else filled / total
        score += weight * fraction
    score = int(round(score))
    if score >= 100:
        return score, "ready"
    if score >= 75:
        return score, "almost_ready"
    if score >= 40:
        return score, "partial"
    return score, "early"


def _build_upload_preview(
    payload: dict[str, Any],
    draft_sections: list[dict[str, Any]],
    resolved_account_name: str | None,
) -> str:
    if _is_plausible_account_name(resolved_account_name):
        account_label = resolved_account_name
    else:
        account_label = payload.get("AccountPlan__c", "unknown account")
    sections_complete = [section["name"] for section in draft_sections if section["complete"]]
    sections_incomplete = [section["name"] for section in draft_sections if not section["complete"]]
    parts = [
        f"Account: {account_label}",
        f"Plan year: {payload.get('Plan_Year__c', 'missing')}",
    ]
    _preview_field(parts, payload, "Annual_Pinterest_Goals_Strategy__c", "Goals")
    _preview_field(parts, payload, "Business_Challenges_Priorities__c", "Challenges")
    _preview_field(parts, payload, "Opportunity_for_Growth__c", "Growth opportunities")
    _preview_field(parts, payload, "CEO_Strategic_Priorities__c", "CEO priorities")
    _preview_field(parts, payload, "CMO_Marketing_Goals_Approach__c", "Marketing goals")
    _preview_field(parts, payload, "Creative_Strategy__c", "Creative strategy")
    _preview_field(parts, payload, "Keys_to_Unlocking_Growth__c", "Keys to growth")
    _preview_field(parts, payload, "Biggest_Opportunities_to_unlock_growth__c", "Biggest opportunities")
    _preview_field(parts, payload, "This_Year_Annual_Spend_Est__c", "Annual spend")
    _preview_field(parts, payload, "Competitive_Landscape__c", "Competitive landscape")
    _preview_field(parts, payload, "Planning_Cadence__c", "Planning cadence")
    _preview_field(parts, payload, "Touchbase_Frequency__c", "Touchbase frequency")
    if sections_complete:
        parts.append(f"Completed sections: {', '.join(sections_complete)}")
    if sections_incomplete:
        parts.append(f"Still incomplete: {', '.join(sections_incomplete)}")
    return " | ".join(parts)


def _preview_field(parts: list[str], payload: dict[str, Any], field_name: str, label: str) -> None:
    value = payload.get(field_name)
    if value not in (None, ""):
        parts.append(f"{label}: {value}")


def _is_plausible_account_name(value: str | None) -> bool:
    if not value:
        return False
    ignored = {"upload", "create", "update", "prepare", "build", "show", "help", "find"}
    return value.lower() not in ignored


def recommend_next_question(draft_sections: list[dict[str, Any]], missing_inputs: list[str]) -> str | None:
    prompts = {
        "account": "Which customer account should this plan be tied to?",
        "plan_year": "Which plan year should I use for this account plan?",
        "goals_or_strategy": "What are the main goals or strategy themes for this account?",
        "client_priorities": "What are the client's top business priorities or challenges?",
        "growth_opportunities": "What growth opportunities do you want captured in the plan?",
        "ceo_priorities": "What are the CEO or executive strategic priorities for this client?",
        "recent_news": "Is there any recent client news that should inform the plan?",
        "account_health": "How would you describe the current account health?",
        "marketing_goals": "What are the CMO or marketing team's goals for this client?",
        "measurement_approach": "What measurement approach or KPIs matter most for this account?",
        "creative_strategy": "What is the creative strategy for this client?",
        "agency": "Which agency is involved with this account?",
        "q1_events": "What are the key Q1 events or moments for this client?",
        "q2_events": "What are the key Q2 events or moments?",
        "q3_events": "What are the key Q3 events or moments?",
        "q4_events": "What are the key Q4 events or moments?",
        "keys_to_growth": "What are the keys to unlocking growth for this account?",
        "biggest_opportunities": "What are the biggest opportunities to unlock growth?",
        "q1_objectives": "What are the Q1 strategic objectives?",
        "q2_objectives": "What are the Q2 strategic objectives?",
        "q3_objectives": "What are the Q3 strategic objectives?",
        "q4_objectives": "What are the Q4 strategic objectives?",
        "annual_spend": "What is the annual spend target for this plan?",
        "revenue_goals": "What are the plan-year revenue goals?",
        "q1_spend": "What is the Q1 spend estimate?",
        "q2_spend": "What is the Q2 spend estimate?",
        "q3_spend": "What is the Q3 spend estimate?",
        "q4_spend": "What is the Q4 spend estimate?",
        "leadership_context": "Who are the key stakeholders or leadership contacts for this account?",
        "relationship_map": "Can you describe the key relationships and decision-making structure?",
        "primary_contact": "Who is the primary contact for this account?",
        "budget_owner": "Who is the budget decision maker for this account?",
        "executive_contact": "Who is the highest-level contact at this client?",
        "other_asks": "Are there any other asks or open items for this account?",
        "competitive_landscape": "What does the competitive landscape look like for this account?",
        "competitor_1": "Who is the primary competitor for this account?",
        "competitor_2": "Who is the second competitor?",
        "competitor_3": "Who is the third competitor?",
        "measurement_vendors": "Which measurement vendors are in use for this account?",
        "q2_measurement_vendors": "Are there different measurement vendors planned for Q2?",
        "q3_measurement_vendors": "Are there different measurement vendors planned for Q3?",
        "q4_measurement_vendors": "Are there different measurement vendors planned for Q4?",
        "planning_cadence": "What is the planning review cadence for this account?",
        "touchbase_frequency": "How often do you have touchbase meetings with this client?",
        "q1_meetings": "What meetings are coming up in Q1?",
        "q2_meetings": "What meetings are coming up in Q2?",
        "q3_meetings": "What meetings are coming up in Q3?",
        "q4_meetings": "What meetings are coming up in Q4?",
        "quarterly_spend_breakdown": "Can you provide the quarterly spend breakdown so it matches the annual target?",
        "account_selection": "Which of the matching accounts should I use for this plan?",
    }
    priority = [
        "account_selection",
        "account",
        "plan_year",
        "goals_or_strategy",
        "client_priorities",
        "growth_opportunities",
        "annual_spend",
        "quarterly_spend_breakdown",
        "leadership_context",
        "primary_contact",
        "budget_owner",
        "keys_to_growth",
        "biggest_opportunities",
        "marketing_goals",
        "creative_strategy",
        "competitive_landscape",
        "ceo_priorities",
        "measurement_approach",
        "account_health",
        "planning_cadence",
        "touchbase_frequency",
        "q1_events",
        "q2_events",
        "q3_events",
        "q4_events",
        "q1_objectives",
        "q2_objectives",
        "q3_objectives",
        "q4_objectives",
        "q1_spend",
        "q2_spend",
        "q3_spend",
        "q4_spend",
    ]
    for item in priority:
        if item in missing_inputs:
            return prompts[item]
    for section in draft_sections:
        if not section["complete"] and section["missing_inputs"]:
            first = section["missing_inputs"][0]
            return prompts.get(first)
    return None
