from __future__ import annotations

from typing import Any


FIELD_LABELS = {
    "Name": "Account",
    "Industry": "Industry",
    "Annual_Pinterest_Goals_Strategy__c": "Goals",
    "Business_Challenges_Priorities__c": "Challenges",
    "Opportunity_for_Growth__c": "Growth opportunities",
    "Keys_to_Unlocking_Growth__c": "Unlocks",
    "Biggest_Opportunities_to_unlock_growth__c": "Biggest opportunities",
    "CEO_Strategic_Priorities__c": "CEO priorities",
    "Recent_News__c": "Recent news",
    "Pinterest_Account_Health__c": "Account health",
    "CMO_Marketing_Goals_Approach__c": "Marketing goals",
    "Measurement__c": "Measurement",
    "Creative_Strategy__c": "Creative strategy",
    "Agency__c": "Agency",
    "Q1_Events__c": "Q1 events",
    "Q2_Events__c": "Q2 events",
    "Q3_Events__c": "Q3 events",
    "Q4_Events__c": "Q4 events",
    "Q1_Objectives__c": "Q1 objectives",
    "Q2_Objectives__c": "Q2 objectives",
    "Q3_Objectives__c": "Q3 objectives",
    "Q4_Objectives__c": "Q4 objectives",
    "This_Year_Annual_Spend_Est__c": "Annual spend",
    "Plan_Year_Goals__c": "Revenue goals",
    "Q1_Spend_Estimate__c": "Q1 spend",
    "Q2_Spend_Estimate__c": "Q2 spend",
    "Q3_Spend_Estimate__c": "Q3 spend",
    "Q4_Spend_Estimate__c": "Q4 spend",
    "Leadership__c": "Leadership",
    "Relationship_Map__c": "Relationship map",
    "Primary_Contact__c": "Primary contact",
    "Budget_Decision_Maker__c": "Budget decision maker",
    "Highest_Level_of_Contact__c": "Executive contact",
    "Other_Asks__c": "Other asks",
    "Competitive_Landscape__c": "Competitive landscape",
    "Competitor_1__c": "Competitor 1",
    "Competitor_2__c": "Competitor 2",
    "Competitor_3__c": "Competitor 3",
    "Measurement_Vendors__c": "Measurement vendors",
    "Q2_Measurement_Vendors__c": "Q2 vendors",
    "Q3_Measurement_Vendors__c": "Q3 vendors",
    "Q4_Measurement_Vendors__c": "Q4 vendors",
    "Planning_Cadence__c": "Planning cadence",
    "Touchbase_Frequency__c": "Touchbase frequency",
    "Q1_Upcoming_Meetings__c": "Q1 meetings",
    "Q2_Upcoming_Meetings__c": "Q2 meetings",
    "Q3_Upcoming_Meetings__c": "Q3 meetings",
    "Q4_Upcoming_Meetings__c": "Q4 meetings",
    "Email": "Email",
    "Phone": "Phone",
    "Title": "Title",
    "AccountId": "Account",
    "StageName": "Stage",
    "Amount": "Amount",
    "CloseDate": "Close date",
    "Probability": "Probability",
    "ForecastCategory": "Forecast",
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
            ("Challenges", ["Business_Challenges_Priorities__c", "CEO_Strategic_Priorities__c"]),
            ("Growth opportunities", ["Opportunity_for_Growth__c", "Keys_to_Unlocking_Growth__c", "Biggest_Opportunities_to_unlock_growth__c"]),
            ("Media/Marketing", ["Pinterest_Account_Health__c", "CMO_Marketing_Goals_Approach__c", "Measurement__c", "Creative_Strategy__c", "Agency__c"]),
            ("Key moments", ["Q1_Events__c", "Q2_Events__c", "Q3_Events__c", "Q4_Events__c"]),
            ("Tactics", ["Q1_Objectives__c", "Q2_Objectives__c", "Q3_Objectives__c", "Q4_Objectives__c"]),
            ("Spend", ["This_Year_Annual_Spend_Est__c", "Q1_Spend_Estimate__c", "Q2_Spend_Estimate__c", "Q3_Spend_Estimate__c", "Q4_Spend_Estimate__c"]),
            ("Stakeholders", ["Leadership__c", "Relationship_Map__c", "Primary_Contact__c", "Budget_Decision_Maker__c", "Highest_Level_of_Contact__c"]),
            ("Competitive context", ["Competitive_Landscape__c", "Competitor_1__c", "Competitor_2__c", "Competitor_3__c"]),
            ("Measurement vendors", ["Measurement_Vendors__c", "Q2_Measurement_Vendors__c", "Q3_Measurement_Vendors__c", "Q4_Measurement_Vendors__c"]),
            ("Review cadence", ["Planning_Cadence__c", "Touchbase_Frequency__c", "Q1_Upcoming_Meetings__c", "Q2_Upcoming_Meetings__c", "Q3_Upcoming_Meetings__c", "Q4_Upcoming_Meetings__c"]),
            ("Recent news", ["Recent_News__c"]),
        ]
        parts = _render_groups(first, groups)
        if parts:
            return " | ".join(parts)
    if target_object == "Contact":
        groups = [
            ("Name", ["Name"]),
            ("Title", ["Title"]),
            ("Email", ["Email"]),
            ("Phone", ["Phone"]),
            ("Account", ["AccountId"]),
        ]
        parts = _render_groups(first, groups)
        if parts:
            return " | ".join(parts)
    if target_object == "Opportunity":
        groups = [
            ("Opportunity", ["Name"]),
            ("Stage", ["StageName"]),
            ("Amount", ["Amount"]),
            ("Close date", ["CloseDate"]),
            ("Account", ["AccountId"]),
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
