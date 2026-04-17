from __future__ import annotations

import re
from dataclasses import dataclass, field


BUSINESS_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "priorities": ("CEO_Strategic_Priorities__c", "Business_Challenges_Priorities__c"),
    "goals": ("Annual_Pinterest_Goals_Strategy__c", "Plan_Year_Goals__c"),
    "strategy": ("Annual_Pinterest_Goals_Strategy__c", "CMO_Marketing_Goals_Approach__c"),
    "news": ("Recent_News__c",),
    "spend": (
        "This_Year_Annual_Spend_Est__c",
        "Q1_Spend_Estimate__c",
        "Q2_Spend_Estimate__c",
        "Q3_Spend_Estimate__c",
        "Q4_Spend_Estimate__c",
    ),
    "leadership": ("Leadership__c", "Primary_Contact__c", "Budget_Decision_Maker__c", "Highest_Level_of_Contact__c"),
    "opportunities": ("Opportunity_for_Growth__c", "Keys_to_Unlocking_Growth__c", "Biggest_Opportunities_to_unlock_growth__c"),
    "measurement": ("Measurement__c", "Measurement_Vendors__c"),
    "competitive": ("Competitive_Landscape__c", "Competitor_1__c", "Competitor_2__c", "Competitor_3__c"),
    "events": ("Q1_Events__c", "Q2_Events__c", "Q3_Events__c", "Q4_Events__c"),
    "key moments": ("Q1_Events__c", "Q2_Events__c", "Q3_Events__c", "Q4_Events__c"),
    "objectives": ("Q1_Objectives__c", "Q2_Objectives__c", "Q3_Objectives__c", "Q4_Objectives__c"),
    "tactics": ("Biggest_Opportunities_to_unlock_growth__c", "Q1_Objectives__c", "Q2_Objectives__c", "Q3_Objectives__c", "Q4_Objectives__c"),
    "creative": ("Creative_Strategy__c",),
    "agency": ("Agency__c",),
    "health": ("Pinterest_Account_Health__c",),
    "marketing": ("CMO_Marketing_Goals_Approach__c", "Creative_Strategy__c"),
    "cadence": ("Planning_Cadence__c", "Touchbase_Frequency__c"),
    "meetings": ("Q1_Upcoming_Meetings__c", "Q2_Upcoming_Meetings__c", "Q3_Upcoming_Meetings__c", "Q4_Upcoming_Meetings__c"),
    "problems": ("Q1_Problem_Statement_for_Product_MSI__c", "Q2_Problem_Statement_for_Product_MSI__c", "Q3_Problem_Statement_for_Product_MSI__c", "Q4_Problem_Statement_for_Product_MSI__c"),
    "vendors": ("Measurement_Vendors__c", "Q2_Measurement_Vendors__c", "Q3_Measurement_Vendors__c", "Q4_Measurement_Vendors__c"),
    "relationship": ("Relationship_Map__c", "Leadership__c"),
}

ACCOUNT_SIGNALS = ("account", "customer", "client", "advertiser", "brand")
ACCOUNT_PLAN_SIGNALS = (
    "account plan", "plan", "growth opportunities", "client priorities",
    "spend", "leadership", "events", "key moments", "objectives", "tactics",
    "creative", "agency", "cadence", "meetings", "competitive", "measurement",
)


@dataclass(slots=True)
class BusinessInterpretation:
    business_goal: str
    target_object: str | None = None
    business_terms: list[str] = field(default_factory=list)
    candidate_fields: list[str] = field(default_factory=list)
    account_name: str | None = None
    guidance: list[str] = field(default_factory=list)


def interpret_business_request(user_input: str) -> BusinessInterpretation:
    lowered = user_input.lower()
    terms = [term for term in BUSINESS_FIELD_MAP if term in lowered]
    candidate_fields: list[str] = []
    for term in terms:
        for field in BUSINESS_FIELD_MAP[term]:
            if field not in candidate_fields:
                candidate_fields.append(field)

    target_object = None
    if any(signal in lowered for signal in ACCOUNT_PLAN_SIGNALS):
        target_object = "Account_Plan__c"
    elif any(signal in lowered for signal in ACCOUNT_SIGNALS):
        target_object = "Account"

    guidance: list[str] = []
    if terms:
        guidance.append(
            "I translated the business request into Salesforce fields tied to "
            + ", ".join(terms)
            + "."
        )

    account_name = extract_account_name(user_input)
    if account_name:
        guidance.append(f"I inferred `{account_name}` as the customer account to resolve.")

    business_goal = "account_plan_summary" if target_object == "Account_Plan__c" else "account_lookup"
    return BusinessInterpretation(
        business_goal=business_goal,
        target_object=target_object,
        business_terms=terms,
        candidate_fields=candidate_fields,
        account_name=account_name,
        guidance=guidance,
    )


def extract_account_name(user_input: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', user_input)
    for left, right in quoted:
        value = left or right
        if value:
            return value

    cleaned = re.sub(r"[?,.]", " ", user_input)
    tokens = cleaned.split()
    stopwords = {
        "show",
        "help",
        "find",
        "create",
        "update",
        "prepare",
        "account",
        "plan",
        "for",
        "with",
        "and",
        "the",
        "our",
        "client",
        "customer",
        "me",
        "2026",
        "2027",
    }
    candidates = [token for token in tokens if token[:1].isupper() and token.lower() not in stopwords]
    if not candidates:
        return None
    return " ".join(candidates[:2])


def choose_schema_fields(
    *,
    schema_fields: list[dict[str, str]],
    business_terms: list[str],
    preferred_fields: list[str],
    target_object: str | None,
) -> list[str]:
    available_by_name = {field["name"]: field for field in schema_fields}
    selected: list[str] = []

    for field_name in preferred_fields:
        if field_name in available_by_name and field_name not in selected:
            selected.append(field_name)

    label_candidates = {
        term.rstrip("s").replace(" ", "").lower()
        for term in business_terms
    }
    for field in schema_fields:
        normalized_name = field["name"].replace("_", "").lower()
        normalized_label = field["label"].replace(" ", "").replace("/", "").lower()
        if any(token in normalized_name or token in normalized_label for token in label_candidates):
            if field["name"] not in selected:
                selected.append(field["name"])

    default_fields = _default_fields_for_object(target_object)
    for field_name in default_fields:
        if field_name in available_by_name and field_name not in selected:
            selected.append(field_name)

    if not selected:
        selected = [field["name"] for field in schema_fields[:5]]

    return selected[:8]


def _default_fields_for_object(target_object: str | None) -> list[str]:
    if target_object == "Account":
        return ["Id", "Name", "Industry", "OwnerId", "CreatedDate"]
    if target_object == "Account_Plan__c":
        return [
            "AccountPlan__c",
            "Plan_Year__c",
            "Annual_Pinterest_Goals_Strategy__c",
            "Business_Challenges_Priorities__c",
            "Opportunity_for_Growth__c",
            "This_Year_Annual_Spend_Est__c",
            "Leadership__c",
            "Competitive_Landscape__c",
        ]
    return ["Id", "Name"]
