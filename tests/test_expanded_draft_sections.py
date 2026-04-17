from app.services.account_plan import build_account_plan_draft, recommend_next_question
from app.services.business_guide import interpret_business_request
from app.services.summary import summarize_query_result


FOUNDATION_PAYLOAD = {
    "AccountPlan__c": "001000000000000AAA",
    "Plan_Year__c": "2026",
}


def _draft(**extra):
    payload = {**FOUNDATION_PAYLOAD, **extra}
    return build_account_plan_draft(
        payload=payload,
        user_input="Create a 2026 account plan",
        resolved_account_id="001000000000000AAA",
        resolved_account_name="Nike",
    )


def _section_by_name(draft, name):
    return next(s for s in draft.draft_sections if s["name"] == name)


# --- Section existence and count ---

def test_draft_has_all_twelve_sections() -> None:
    draft = _draft()
    names = [s["name"] for s in draft.draft_sections]
    expected = [
        "foundation", "strategy", "client_objectives", "media_marketing",
        "key_moments", "value_proposition", "tactics", "spend_plan",
        "stakeholders", "competitive", "measurement_vendors", "review_cadence",
    ]
    assert names == expected


# --- Individual section completeness ---

def test_foundation_complete_with_both_required_fields() -> None:
    draft = _draft()
    assert _section_by_name(draft, "foundation")["complete"] is True


def test_strategy_incomplete_when_empty() -> None:
    draft = _draft()
    section = _section_by_name(draft, "strategy")
    assert section["complete"] is False
    assert "goals_or_strategy" in section["missing_inputs"]


def test_strategy_complete_with_any_field() -> None:
    draft = _draft(Annual_Pinterest_Goals_Strategy__c="Grow awareness")
    assert _section_by_name(draft, "strategy")["complete"] is True


def test_client_objectives_complete_with_ceo_priorities() -> None:
    draft = _draft(CEO_Strategic_Priorities__c="Expand digital")
    assert _section_by_name(draft, "client_objectives")["complete"] is True


def test_media_marketing_complete_with_any_field() -> None:
    draft = _draft(Creative_Strategy__c="Video-first")
    assert _section_by_name(draft, "media_marketing")["complete"] is True


def test_key_moments_complete_with_any_event() -> None:
    draft = _draft(Q1_Events__c="Product launch")
    assert _section_by_name(draft, "key_moments")["complete"] is True


def test_value_proposition_complete_with_keys_to_growth() -> None:
    draft = _draft(Keys_to_Unlocking_Growth__c="Shopping expansion")
    assert _section_by_name(draft, "value_proposition")["complete"] is True


def test_tactics_complete_with_quarterly_objectives() -> None:
    draft = _draft(Q2_Objectives__c="Scale campaigns")
    assert _section_by_name(draft, "tactics")["complete"] is True


def test_spend_plan_includes_revenue_goals() -> None:
    draft = _draft(Plan_Year_Goals__c="500k")
    section = _section_by_name(draft, "spend_plan")
    assert section["complete"] is True
    assert "revenue_goals" in section["filled_inputs"]


def test_stakeholders_includes_expanded_fields() -> None:
    draft = _draft(Relationship_Map__c="Jane -> Mark -> VP")
    section = _section_by_name(draft, "stakeholders")
    assert section["complete"] is True
    assert "relationship_map" in section["filled_inputs"]


def test_competitive_section() -> None:
    draft = _draft(Competitive_Landscape__c="Google dominates search")
    assert _section_by_name(draft, "competitive")["complete"] is True


def test_measurement_vendors_section() -> None:
    draft = _draft(Measurement_Vendors__c="Nielsen")
    assert _section_by_name(draft, "measurement_vendors")["complete"] is True


def test_review_cadence_section() -> None:
    draft = _draft(Planning_Cadence__c="Quarterly")
    assert _section_by_name(draft, "review_cadence")["complete"] is True


# --- Scoring ---

def test_foundation_only_scores_25() -> None:
    draft = _draft()
    assert draft.readiness_score == 25
    assert draft.readiness_label == "early"


def test_foundation_plus_strategy_scores_45() -> None:
    draft = _draft(
        Annual_Pinterest_Goals_Strategy__c="Grow upper funnel",
        Business_Challenges_Priorities__c="Measurement confidence",
        Opportunity_for_Growth__c="Shopping campaigns",
    )
    assert draft.readiness_score == 45
    assert draft.readiness_label == "partial"


def test_nearly_complete_plan_scores_almost_ready() -> None:
    draft = _draft(
        Annual_Pinterest_Goals_Strategy__c="Grow",
        Business_Challenges_Priorities__c="Measurement",
        Opportunity_for_Growth__c="Shopping",
        This_Year_Annual_Spend_Est__c="100000",
        Q1_Spend_Estimate__c="25000",
        Q2_Spend_Estimate__c="25000",
        Q3_Spend_Estimate__c="25000",
        Q4_Spend_Estimate__c="25000",
        Leadership__c="Jane Doe",
        Primary_Contact__c="001000000000000BBB",
    )
    assert draft.readiness_score >= 60
    assert draft.readiness_label in ("partial", "almost_ready")


def test_fully_complete_plan_scores_ready() -> None:
    draft = _draft(
        Annual_Pinterest_Goals_Strategy__c="Grow",
        Business_Challenges_Priorities__c="Measurement",
        Opportunity_for_Growth__c="Shopping",
        CEO_Strategic_Priorities__c="Digital transformation",
        Recent_News__c="Q4 earnings up",
        Pinterest_Account_Health__c="Healthy",
        CMO_Marketing_Goals_Approach__c="Brand awareness",
        Measurement__c="Incrementality studies",
        Creative_Strategy__c="Video-first",
        Agency__c="WPP",
        Q1_Events__c="CES", Q2_Events__c="Cannes",
        Q3_Events__c="Back to school", Q4_Events__c="Holiday",
        Keys_to_Unlocking_Growth__c="Shopping",
        Biggest_Opportunities_to_unlock_growth__c="Full funnel",
        Q1_Objectives__c="Awareness", Q2_Objectives__c="Consideration",
        Q3_Objectives__c="Conversion", Q4_Objectives__c="Retention",
        This_Year_Annual_Spend_Est__c="100000",
        Plan_Year_Goals__c="120000",
        Q1_Spend_Estimate__c="25000", Q2_Spend_Estimate__c="25000",
        Q3_Spend_Estimate__c="25000", Q4_Spend_Estimate__c="25000",
        Leadership__c="Jane", Relationship_Map__c="Jane -> Mark",
        Primary_Contact__c="001000000000000BBB",
        Budget_Decision_Maker__c="001000000000000CCC",
        Highest_Level_of_Contact__c="001000000000000DDD",
        Other_Asks__c="None",
        Competitive_Landscape__c="Google, Meta",
        Competitor_1__c="001000000000000EEE",
        Competitor_2__c="001000000000000FFF",
        Competitor_3__c="001000000000000GGG",
        Measurement_Vendors__c="Nielsen",
        Q2_Measurement_Vendors__c="IRI",
        Q3_Measurement_Vendors__c="Comscore",
        Q4_Measurement_Vendors__c="Nielsen",
        Planning_Cadence__c="Monthly",
        Touchbase_Frequency__c="Bi-weekly",
        Q1_Upcoming_Meetings__c="Jan review",
        Q2_Upcoming_Meetings__c="Apr QBR",
        Q3_Upcoming_Meetings__c="Jul planning",
        Q4_Upcoming_Meetings__c="Oct preview",
    )
    assert draft.readiness_score == 100
    assert draft.readiness_label == "ready"


# --- Next-question prompts ---

def test_next_question_for_new_sections() -> None:
    draft = _draft(
        Annual_Pinterest_Goals_Strategy__c="Grow",
        Business_Challenges_Priorities__c="Measurement",
        Opportunity_for_Growth__c="Shopping",
        This_Year_Annual_Spend_Est__c="100000",
        Q1_Spend_Estimate__c="25000", Q2_Spend_Estimate__c="25000",
        Q3_Spend_Estimate__c="25000", Q4_Spend_Estimate__c="25000",
        Leadership__c="Jane",
        Primary_Contact__c="001000000000000BBB",
        Budget_Decision_Maker__c="001000000000000CCC",
    )
    assert draft.next_question is not None
    assert "growth" in draft.next_question.lower() or "keys" in draft.next_question.lower() or "marketing" in draft.next_question.lower() or "creative" in draft.next_question.lower() or "competitive" in draft.next_question.lower()


def test_recommend_next_question_returns_new_section_prompts() -> None:
    sections = [
        {"name": "foundation", "complete": True, "filled_inputs": ["account", "plan_year"], "missing_inputs": []},
        {"name": "strategy", "complete": True, "filled_inputs": ["goals_or_strategy"], "missing_inputs": []},
        {"name": "client_objectives", "complete": False, "filled_inputs": [], "missing_inputs": ["ceo_priorities", "recent_news"]},
    ]
    result = recommend_next_question(sections, ["ceo_priorities", "recent_news"])
    assert result is not None
    assert "CEO" in result or "executive" in result


# --- Upload preview ---

def test_upload_preview_includes_new_fields() -> None:
    draft = _draft(
        Annual_Pinterest_Goals_Strategy__c="Grow",
        CEO_Strategic_Priorities__c="Digital",
        CMO_Marketing_Goals_Approach__c="Brand awareness",
        Creative_Strategy__c="Video",
        Keys_to_Unlocking_Growth__c="Shopping",
        Competitive_Landscape__c="Google",
        Planning_Cadence__c="Monthly",
    )
    preview = draft.upload_preview
    assert "CEO priorities: Digital" in preview
    assert "Marketing goals: Brand awareness" in preview
    assert "Creative strategy: Video" in preview
    assert "Keys to growth: Shopping" in preview
    assert "Competitive landscape: Google" in preview
    assert "Planning cadence: Monthly" in preview


# --- Business guide new terms ---

def test_business_guide_maps_events_to_fields() -> None:
    result = interpret_business_request("Show me the key events for Nike")
    assert "Q1_Events__c" in result.candidate_fields
    assert result.target_object == "Account_Plan__c"


def test_business_guide_maps_tactics_to_fields() -> None:
    result = interpret_business_request("What are the quarterly tactics for Acme?")
    assert "Q1_Objectives__c" in result.candidate_fields


def test_business_guide_maps_creative_to_field() -> None:
    result = interpret_business_request("Show me the creative strategy for Nike")
    assert "Creative_Strategy__c" in result.candidate_fields


def test_business_guide_maps_meetings_to_fields() -> None:
    result = interpret_business_request("What meetings are coming up for Nike?")
    assert "Q1_Upcoming_Meetings__c" in result.candidate_fields
    assert result.target_object == "Account_Plan__c"


def test_business_guide_maps_cadence_to_fields() -> None:
    result = interpret_business_request("What is the planning cadence for this account?")
    assert "Planning_Cadence__c" in result.candidate_fields


def test_business_guide_maps_competitive_to_fields() -> None:
    result = interpret_business_request("Show me the competitive landscape for Nike")
    assert "Competitive_Landscape__c" in result.candidate_fields


# --- Summary new groups ---

def test_summary_includes_media_marketing_group() -> None:
    result = summarize_query_result({
        "target_object": "Account_Plan__c",
        "records": [{
            "CMO_Marketing_Goals_Approach__c": "Brand",
            "Creative_Strategy__c": "Video",
        }],
    })
    assert result is not None
    assert "Media/Marketing" in result
    assert "Brand" in result


def test_summary_includes_key_moments_group() -> None:
    result = summarize_query_result({
        "target_object": "Account_Plan__c",
        "records": [{"Q1_Events__c": "CES", "Q3_Events__c": "Back to school"}],
    })
    assert result is not None
    assert "Key moments" in result


def test_summary_includes_tactics_group() -> None:
    result = summarize_query_result({
        "target_object": "Account_Plan__c",
        "records": [{"Q1_Objectives__c": "Awareness"}],
    })
    assert result is not None
    assert "Tactics" in result


def test_summary_includes_review_cadence_group() -> None:
    result = summarize_query_result({
        "target_object": "Account_Plan__c",
        "records": [{"Planning_Cadence__c": "Monthly"}],
    })
    assert result is not None
    assert "Review cadence" in result
