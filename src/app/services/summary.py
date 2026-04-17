from __future__ import annotations

from typing import Any


FIELD_LABELS = {
    "Name": "Account",
    "Industry": "Industry",
    "Annual_Pinterest_Goals_Strategy__c": "Goals",
    "Business_Challenges_Priorities__c": "Challenges",
    "Opportunity_for_Growth__c": "Growth opportunities",
    "Keys_to_Unlocking_Growth__c": "Unlocks",
    "This_Year_Annual_Spend_Est__c": "Annual spend",
    "Q1_Spend_Estimate__c": "Q1 spend",
    "Q2_Spend_Estimate__c": "Q2 spend",
    "Q3_Spend_Estimate__c": "Q3 spend",
    "Q4_Spend_Estimate__c": "Q4 spend",
    "Leadership__c": "Leadership",
    "Primary_Contact__c": "Primary contact",
    "Budget_Decision_Maker__c": "Budget decision maker",
    "Competitive_Landscape__c": "Competitive landscape",
    "Recent_News__c": "Recent news",
}


def summarize_query_result(state: dict[str, Any]) -> str | None:
    records = state.get("records") or []
    if not records:
        return None
    first = records[0]
    target_object = state.get("target_object")
    if target_object == "Account_Plan__c":
        groups = [
            ("Goals", ["Annual_Pinterest_Goals_Strategy__c", "Plan_Year_Goals__c"]),
            ("Challenges", ["Business_Challenges_Priorities__c"]),
            ("Growth opportunities", ["Opportunity_for_Growth__c", "Keys_to_Unlocking_Growth__c"]),
            ("Spend", ["This_Year_Annual_Spend_Est__c", "Q1_Spend_Estimate__c", "Q2_Spend_Estimate__c", "Q3_Spend_Estimate__c", "Q4_Spend_Estimate__c"]),
            ("Stakeholders", ["Leadership__c", "Primary_Contact__c", "Budget_Decision_Maker__c"]),
            ("Competitive context", ["Competitive_Landscape__c"]),
            ("Recent news", ["Recent_News__c"]),
        ]
        parts = _render_groups(first, groups)
        if parts:
            return " | ".join(parts)
    if target_object == "Account":
        parts = _render_groups(first, [("Account", ["Name"]), ("Industry", ["Industry"])])
        if parts:
            return " | ".join(parts)
    return None


def _render_groups(record: dict[str, Any], groups: list[tuple[str, list[str]]]) -> list[str]:
    rendered: list[str] = []
    for label, fields in groups:
        values: list[str] = []
        for field_name in fields:
            value = record.get(field_name)
            if value not in (None, ""):
                if len(fields) == 1:
                    values.append(str(value))
                else:
                    values.append(f"{FIELD_LABELS.get(field_name, field_name)}={value}")
        if values:
            rendered.append(f"{label}: {'; '.join(values)}")
    return rendered
