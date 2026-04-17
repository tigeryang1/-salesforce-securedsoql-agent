from __future__ import annotations

from app.graph.state import AgentState
from app.services.business_guide import choose_schema_fields
from app.services.contracts import SalesforceToolAdapter


def make_schema_node(adapter: SalesforceToolAdapter):
    async def schema_node(state: AgentState) -> AgentState:
        target_object = state.get("target_object")
        if not target_object:
            return {}
        schema = await adapter.describe_salesforce_object(target_object)
        schema_fields = [
            {
                "name": field.name,
                "label": field.label,
                "type": field.type,
                "reference_to": field.reference_to,
            }
            for field in schema.fields
        ]
        selected_fields = choose_schema_fields(
            schema_fields=schema_fields,
            business_terms=state.get("business_terms", []),
            preferred_fields=state.get("candidate_fields", []),
            target_object=target_object,
        )
        return {
            "schema_label": schema.label,
            "schema_fields": schema_fields,
            "candidate_fields": selected_fields,
        }

    return schema_node
