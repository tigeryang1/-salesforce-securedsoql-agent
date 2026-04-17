from __future__ import annotations

from app.graph.state import AgentState
from app.services.contracts import SalesforceToolAdapter
from app.services.entity_resolution import is_unambiguous_best_match, rank_account_matches
from app.utils.salesforce_ids import looks_like_salesforce_id


def make_resolve_account_node(adapter: SalesforceToolAdapter):
    async def resolve_account_node(state: AgentState) -> AgentState:
        payload = state.get("account_plan_data") or {}
        existing_account_id = payload.get("AccountPlan__c")
        if existing_account_id and looks_like_salesforce_id(str(existing_account_id)):
            return {
                "resolved_account_id": str(existing_account_id),
                "resolved_account_name": state.get("account_name"),
            }

        account_name = state.get("account_name")
        if not account_name:
            return {}

        safe_account_name = account_name.replace("'", "\\'")
        exact_result = await adapter.query_salesforce(
            f"SELECT Id, Name, Industry FROM Account WHERE Name = '{safe_account_name}' LIMIT 5"
        )
        if not exact_result.success:
            return {
                "status": "error",
                "query_error": exact_result.error,
                "query_status_code": exact_result.status_code,
            }
        records = exact_result.records
        if not records:
            fuzzy_result = await adapter.query_salesforce(
                f"SELECT Id, Name, Industry FROM Account WHERE Name LIKE '%{safe_account_name}%' LIMIT 5"
            )
            if not fuzzy_result.success:
                return {
                    "status": "error",
                    "query_error": fuzzy_result.error,
                    "query_status_code": fuzzy_result.status_code,
                }
            records = fuzzy_result.records

        if not records:
            return {
                "status": "needs_input",
                "missing_inputs": ["account_name"],
                "guidance": [
                    *state.get("guidance", []),
                    f"I could not resolve `{account_name}` to an accessible Account record.",
                ],
                "candidate_accounts": [],
            }

        ranked_records = rank_account_matches(account_name, records)
        if len(ranked_records) > 1 and not is_unambiguous_best_match(account_name, ranked_records):
            return {
                "status": "needs_input",
                "missing_inputs": ["account_selection"],
                "guidance": [
                    *state.get("guidance", []),
                    f"I found multiple Account matches for `{account_name}`. Choose one before I continue.",
                ],
                "candidate_accounts": ranked_records,
            }

        record = ranked_records[0]
        return {
            "resolved_account_id": record.get("Id"),
            "resolved_account_name": record.get("Name"),
            "candidate_accounts": ranked_records,
            "guidance": [
                *state.get("guidance", []),
                f"I resolved the request to Account `{record.get('Name')}`.",
            ],
        }

    return resolve_account_node
