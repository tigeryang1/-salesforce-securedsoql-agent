from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.services.business_guide import extract_account_name
from app.services.summary import summarize_query_result

logger = logging.getLogger(__name__)


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

        if self.model is not None:
            try:
                return self._llm_classify_intent(user_input)
            except Exception:
                logger.warning("LLM intent classification failed, falling back to heuristic", exc_info=True)

        return self._heuristic_classify_intent(user_input)

    def _heuristic_classify_intent(self, user_input: str) -> IntentDecision:
        lowered = user_input.lower()
        if "account plan" in lowered and any(word in lowered for word in ("upload", "create", "update", "save")):
            return IntentDecision(intent="upload_account_plan", target_object="Account_Plan__c", needs_schema=False)
        if any(word in lowered for word in ("prepare", "draft", "build")) and "account plan" in lowered:
            return IntentDecision(intent="upload_account_plan", target_object="Account_Plan__c", needs_schema=False)
        if "describe" in lowered or "fields" in lowered or "schema" in lowered:
            return IntentDecision(intent="describe", target_object=_extract_guess_from_text(user_input), needs_schema=True)
        return IntentDecision(intent="query", target_object=_extract_guess_from_text(user_input), needs_schema=True)

    def _llm_classify_intent(self, user_input: str) -> IntentDecision:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are an intent classifier for a Salesforce agent. "
                "Given a user request, respond with JSON containing:\n"
                '- "intent": one of "describe", "query", or "upload_account_plan"\n'
                '- "target_object": the Salesforce object name (e.g. "Account", "Contact", "Opportunity", "Account_Plan__c") or null\n'
                "Rules:\n"
                '- If the user wants to see object fields or schema, intent is "describe"\n'
                '- If the user wants to read/find/show data, intent is "query"\n'
                '- If the user wants to create/prepare/draft/upload an account plan, intent is "upload_account_plan"\n'
                "Respond with valid JSON only, no extra text.",
            ),
            ("human", "{user_input}"),
        ])
        chain = prompt | self.model
        response = chain.invoke({"user_input": user_input})
        content = getattr(response, "content", "")
        parsed = json.loads(content)
        intent = parsed.get("intent", "query")
        if intent not in ("describe", "query", "upload_account_plan"):
            intent = "query"
        target_object = parsed.get("target_object")
        needs_schema = intent in ("describe", "query")
        return IntentDecision(intent=intent, target_object=target_object, needs_schema=needs_schema)

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
            logger.warning("LLM response composition failed, using fallback", exc_info=True)
            return self._compose_fallback_response(state)

    def _compose_fallback_response(self, state: dict[str, Any]) -> str:
        status = state.get("status", "completed")
        intent = state.get("intent", "unknown")
        if status in ("error", "query_error"):
            return _compose_error_message(state)
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


_ERROR_MESSAGES: dict[str, str] = {
    "object_not_allowed": (
        "This Salesforce object is not available for querying through the SecuredSOQL API. "
        "Try a different object, or use describe to see which objects are accessible."
    ),
    "no_access": (
        "You do not have permission to access this Salesforce object. "
        "Contact your administrator if you believe this is incorrect."
    ),
    "invalid_email": (
        "The email address provided is not in a valid format. "
        "Please check the email and try again."
    ),
    "user_not_found": (
        "No active Salesforce user was found with that email address. "
        "Verify the email belongs to an active user and try again."
    ),
    "missing_parameter": (
        "The query is missing a required parameter. "
        "This is likely an internal issue — please try rephrasing your request."
    ),
    "inference_attack": (
        "The query was blocked because it used a restricted field in a filter or sort clause. "
        "The agent attempted recovery, but the query could not be completed."
    ),
    "missing_query": "No SOQL query was available to execute. Please provide a query or describe your request.",
}


def _compose_error_message(state: dict[str, Any]) -> str:
    error_type = state.get("query_error_type", "unknown")
    raw_error = state.get("query_error") or ""
    message = _ERROR_MESSAGES.get(error_type)
    if message:
        return message
    if raw_error:
        return f"The query failed: {raw_error}"
    return "The request could not be completed due to an unexpected error."


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
