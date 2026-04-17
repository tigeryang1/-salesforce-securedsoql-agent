from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.services.business_guide import extract_account_name
from app.services.summary import summarize_query_result


def build_chat_model(model_name: str) -> BaseChatModel:
    if model_name.startswith("openai:"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_name.split(":", 1)[1], temperature=0)
    if model_name.startswith("gemini:"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_name.split(":", 1)[1], temperature=0)
    raise ValueError(f"Unsupported model prefix in `{model_name}`.")


@dataclass(slots=True)
class IntentDecision:
    intent: str
    target_object: str | None = None
    needs_schema: bool = False


class AgentReasoner:
    def __init__(self, model: BaseChatModel | None = None) -> None:
        self.model = model

    def classify_intent(
        self,
        *,
        user_input: str,
        soql_query: str | None,
        sobject_name: str | None,
        account_plan_data: dict[str, Any] | None,
    ) -> IntentDecision:
        if account_plan_data:
            return IntentDecision(intent="upload_account_plan", target_object="Account_Plan__c", needs_schema=False)
        if soql_query:
            return IntentDecision(intent="query", needs_schema=True)
        if sobject_name:
            return IntentDecision(intent="describe", target_object=sobject_name, needs_schema=True)

        lowered = user_input.lower()
        if "account plan" in lowered and any(word in lowered for word in ("upload", "create", "update", "save")):
            return IntentDecision(intent="upload_account_plan", target_object="Account_Plan__c", needs_schema=False)
        if any(word in lowered for word in ("prepare", "draft", "build")) and "account plan" in lowered:
            return IntentDecision(intent="upload_account_plan", target_object="Account_Plan__c", needs_schema=False)
        if "describe" in lowered or "fields" in lowered or "schema" in lowered:
            return IntentDecision(intent="describe", target_object=_extract_guess_from_text(user_input), needs_schema=True)
        return IntentDecision(intent="query", target_object=_extract_guess_from_text(user_input), needs_schema=True)

    def compose_response(self, state: dict[str, Any]) -> str:
        if self.model is None:
            return self._compose_fallback_response(state)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Salesforce agent. Be concise. Never invent filtered or missing fields.",
                ),
                (
                    "human",
                    "Summarize this execution result as JSON with a single key `message`.\n{payload}",
                ),
            ]
        )
        chain = prompt | self.model
        response = chain.invoke({"payload": json.dumps(state, default=str)})
        content = getattr(response, "content", "")
        try:
            parsed = json.loads(content)
            return parsed["message"]
        except Exception:
            return self._compose_fallback_response(state)

    def _compose_fallback_response(self, state: dict[str, Any]) -> str:
        status = state.get("status", "completed")
        intent = state.get("intent", "unknown")
        if status == "needs_approval":
            preview = state.get("upload_preview")
            score = state.get("readiness_score")
            label = state.get("readiness_label")
            base = "Account plan payload is valid, but write execution is blocked until approval is granted."
            if preview and score is not None and label:
                return f"{base} Readiness: {score}% ({label}). Preview: {preview}."
            return base
        if status == "needs_input":
            guidance = " ".join(state.get("guidance", []))
            missing_inputs = state.get("missing_inputs", [])
            draft_sections = state.get("draft_sections", [])
            score = state.get("readiness_score")
            label = state.get("readiness_label")
            next_question = state.get("next_question")
            if state.get("candidate_accounts"):
                names = ", ".join(item.get("Name", "Unknown") for item in state["candidate_accounts"])
                return f"{guidance} I need you to choose one of these accounts: {names}."
            if draft_sections:
                incomplete = ", ".join(section["name"] for section in draft_sections if not section["complete"])
                if missing_inputs:
                    readiness = f" Readiness is {score}% ({label})." if score is not None and label else ""
                    next_step = f" Next question: {next_question}" if next_question else ""
                    return (
                        f"{guidance} Draft status: incomplete sections are {incomplete}. "
                        f"I still need: {', '.join(missing_inputs)}.{readiness}{next_step}"
                    )
            if missing_inputs:
                return f"{guidance} I still need: {', '.join(missing_inputs)}."
            return guidance or "I need a bit more business context before I can continue."
        if intent == "describe":
            target = state.get("target_object") or "object"
            fields = state.get("schema_fields", [])
            return f"Described {target} with {len(fields)} fields."
        if intent == "query":
            count = state.get("record_count", 0)
            filtered_fields = state.get("filtered_fields", [])
            account = state.get("resolved_account_name")
            prefix = f"For {account}, " if account else ""
            summary = state.get("business_summary") or summarize_query_result(state)
            if filtered_fields:
                if summary:
                    return (
                        f"{prefix}{summary}. Query returned {count} accessible records. "
                        f"Filtered fields: {', '.join(filtered_fields)}."
                    )
                return (
                    f"{prefix}query returned {count} accessible records. "
                    f"Filtered fields: {', '.join(filtered_fields)}."
                )
            if summary:
                return f"{prefix}{summary}. Query returned {count} accessible records."
            return f"{prefix}query returned {count} accessible records."
        if intent == "upload_account_plan":
            action = state.get("upload_action", "updated")
            record_id = state.get("upload_record_id", "unknown")
            preview = state.get("upload_preview")
            if preview:
                return f"Account plan {action} successfully with record id {record_id}. Uploaded: {preview}."
            return f"Account plan {action} successfully with record id {record_id}."
        return "Completed request."


def _extract_guess_from_text(user_input: str) -> str | None:
    account_name = extract_account_name(user_input)
    if account_name in {"Account", "Contact", "Opportunity"}:
        return account_name
    ignored = {
        "Show",
        "Help",
        "Find",
        "Create",
        "Update",
        "Prepare",
        "Build",
        "List",
        "Get",
    }
    tokens = user_input.replace("?", " ").replace(",", " ").split()
    for token in tokens:
        if token in ignored:
            continue
        if token[:1].isupper() and any(char.islower() for char in token):
            return token
    return None
