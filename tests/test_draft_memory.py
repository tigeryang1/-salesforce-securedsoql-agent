from app.api.routes import merge_account_plan_draft
from app.services.account_plan import build_account_plan_draft


def test_merge_account_plan_draft_preserves_existing_values() -> None:
    merged = merge_account_plan_draft(
        {"AccountPlan__c": "001000000000000AAA", "Plan_Year__c": "2026"},
        {"Annual_Pinterest_Goals_Strategy__c": "Grow awareness"},
    )
    assert merged == {
        "AccountPlan__c": "001000000000000AAA",
        "Plan_Year__c": "2026",
        "Annual_Pinterest_Goals_Strategy__c": "Grow awareness",
    }


def test_build_account_plan_draft_produces_next_question_and_weighted_score() -> None:
    draft = build_account_plan_draft(
        payload={"AccountPlan__c": "001000000000000AAA", "Plan_Year__c": "2026"},
        user_input="Create a 2026 account plan",
        resolved_account_id="001000000000000AAA",
        resolved_account_name="Nike",
    )
    assert draft.readiness_score == 40
    assert draft.readiness_label == "partial"
    assert draft.next_question == "What are the main goals or strategy themes for this account?"
