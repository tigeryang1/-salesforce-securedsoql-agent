from app.services.account_plan import validate_account_plan_payload


def test_account_plan_validation_requires_ids_and_balanced_spend() -> None:
    result = validate_account_plan_payload(
        {
            "AccountPlan__c": "bad-id",
            "Plan_Year__c": "2026",
            "This_Year_Annual_Spend_Est__c": "100",
            "Q1_Spend_Estimate__c": "25",
            "Q2_Spend_Estimate__c": "25",
            "Q3_Spend_Estimate__c": "25",
            "Q4_Spend_Estimate__c": "20",
        }
    )

    assert result.valid is False
    assert any("18-character Salesforce ID" in error for error in result.errors)
    assert any("Quarterly spend estimates" in error for error in result.errors)
