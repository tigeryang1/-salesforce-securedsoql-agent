# Salesforce SecuredSOQL Agent Design

## Overview

This project implements a LangGraph-based Salesforce agent that can be accessed through three runtime surfaces: a FastAPI HTTP server, an outer MCP server, and a CLI. All three surfaces share a single `AgentSessionService` that owns session state and delegates to a LangGraph workflow. The workflow mediates access to an inner Salesforce MCP server that exposes a SecuredSOQL query surface.

The agent's main responsibilities are:

- route requests into object description, secure querying, or account-plan upload flows across four Salesforce objects (Account, Contact, Opportunity, Account_Plan__c)
- surface security-filtered data transparently instead of inventing missing fields
- classify MCP errors into structured types and present user-friendly messages
- recover from SecuredSOQL inference-attack failures when possible
- guide business users through multi-turn account-plan drafting across 12 sections before write approval
- use LLM-backed reasoning when a model is configured, with automatic fallback to deterministic heuristics
- expose itself as an MCP server so other AI agents can use the LangGraph runtime as a tool

## Goals

1. Provide a single agent entry point for three MCP tools: `describe_salesforce_object`, `query_salesforce`, and `upload_account_plan`.
2. Expose the agent through multiple surfaces (HTTP API, MCP server, CLI) without duplicating workflow logic.
3. Keep orchestration logic stable across demo and live MCP integrations by isolating transport behind a small adapter contract.
4. Make security behavior explicit by detecting filtered fields, respecting row-level visibility, classifying error types, and handling restricted filter failures.
5. Support business-language interactions across Account, Contact, Opportunity, and Account_Plan__c objects.
6. Block writes until payload validation and explicit user approval succeed.
7. Operate in both LLM-backed and heuristic-only modes with graceful degradation.

## Non-Goals

- Acting as a general-purpose Salesforce analyst across the full object model.
- Persisting drafts durably across API process restarts.
- Replacing Salesforce authorization or bypassing MCP server security decisions.
- Performing autonomous writes without a human approval step.

## System Context

The system has five major layers:

1. **Three entry surfaces** accept user input, auth context, and optional session state:
   - FastAPI HTTP server (`src/app/api/routes.py`) — for direct API consumers
   - Outer MCP server (`src/app/mcp_server.py`) — for other AI agents connecting over MCP
   - CLI (`src/app/main.py`) — for local development and smoke testing
2. **Shared service layer** (`src/app/agent_service.py`) — `AgentSessionService` owns draft persistence, session state, graph construction, and model wiring. All three entry surfaces delegate to this service.
3. **LangGraph workflow** (`src/app/graph/builder.py`) — routes each request through intent classification, business context extraction, retrieval, validation, and response composition.
4. **Service modules** provide transport, LLM reasoning, business heuristics, error classification, validation, summarization, and entity resolution.
5. **Inner Salesforce MCP server** remains the source of truth for schema, query execution, and account-plan upload behavior.

## MCP Server Contract

The target MCP server (`salesforce`) is exposed over Streamable HTTP and provides exactly three tools. The entire agent is designed around the specific behaviors documented here; standard Salesforce SOQL assumptions do not apply.

### `describe_salesforce_object`

Calls the `McpSObjectDescribe` Apex REST API. Applies the same authorization checks as `query_salesforce` (caller permission, object allowlist, target-user object read access) and writes audit metadata to `MCP_API_Log__c`.

Important distinction: field-level describe reflects the **integration user**, not user-specific FLS impersonation. This means the describe result may list fields that are subsequently filtered when queried for a specific target user.

Input: `sobject_name` (required).

Response shape:

- Object-level: `name`, `label`, `keyPrefix`
- Per-field: `name`, `label`, `type`
- For reference/lookup fields: `referenceTo` array with referenced object names

### `query_salesforce`

Executes SOQL through a custom SecuredSOQL API that enforces four security layers. This is the core read surface and the primary source of safety-related complexity in the agent.

Input: `soql_query` (required). Only `SELECT`, `WHERE`, `ORDER BY`, `LIMIT`, and `OFFSET` are supported (no subqueries).

Annotation: `readOnlyHint: true`.

#### Security layers

1. **Custom Permission** — caller must have `SecuredSOQL_API_Access`.
2. **Object Allowlist** — only explicitly allowlisted objects can be queried.
3. **Field-Level Security + PII Policy** — PII/restricted fields in `SELECT` are silently removed (query succeeds with fewer fields); PII/restricted fields in `WHERE` or `ORDER BY` block the entire query (inference protection).
4. **Row-Level Security** — records not accessible to the target user are filtered; the returned count may be less than `LIMIT`.

#### Response format

Differs from standard Salesforce API responses:

- Success: `{"success": true, "records": [...], "recordCount": N, "timestamp": "..."}`
- Error: `{"success": false, "error": "...", "statusCode": 403, "timestamp": "..."}`
- Records have no `attributes` wrapper.
- No `done` field; all accessible records are returned in one call (no pagination).

#### Error taxonomy and classification

The agent classifies every MCP error into a structured type using pattern matching in `classify_query_error()` (`src/app/graph/nodes/query_execute.py`). Each type maps to a user-friendly message in `_ERROR_MESSAGES` (`src/app/services/llm.py`).

| Error text | Classified type | User-facing message | Agent handling |
|---|---|---|---|
| `Inference attack detected` on field X | `inference_attack` | Explains field was blocked in filter/sort | Remove field from clause, retry once |
| `not permitted for querying` | `object_not_allowed` | Object not available for querying | Report to caller, do not retry |
| `does not have permission` | `no_access` | User lacks permission | Report to caller, do not retry |
| `Missing required parameter` | `missing_parameter` | Internal issue, rephrase request | Programming error in agent |
| `Invalid email format` | `invalid_email` | Check email format | Report to caller |
| `No user found with email` | `user_not_found` | Email not found or inactive | Report to caller |
| (unrecognized) | `unknown` | Shows raw error text | Report to caller |

The `query_error_type` field on `AgentState` carries the classified type through the graph so the response layer can select the appropriate message without re-parsing error text.

#### Agent-critical behaviors

- Always check `success` first, not just HTTP status.
- Compare requested versus returned fields to detect silent filtering.
- Do not assume more records exist when count is less than `LIMIT`.
- Never hallucinate or infer values for filtered fields.

### `upload_account_plan`

Creates or updates an `Account_Plan__c` record using Account + Plan Year upsert logic. The MCP server handles create-if-new / update-if-exists automatically.

Annotation: `readOnlyHint: false`.

Input: `account_plan_data` (required object).

#### Required fields

- `AccountPlan__c` — reference to Account (18-character Salesforce ID)
- `Plan_Year__c` — picklist value (e.g. `"2026"`)

#### Available fields by category

**Basic Information:** `AccountPlan__c`, `Plan_Year__c`, `Plan_Quarter__c`, `Name`

**Executive Summary:** `Annual_Pinterest_Goals_Strategy__c`

**Client Objectives:** `CEO_Strategic_Priorities__c`, `Business_Challenges_Priorities__c`, `Recent_News__c`

**Media / Marketing:** `Pinterest_Account_Health__c`, `CMO_Marketing_Goals_Approach__c`, `Measurement__c`, `Creative_Strategy__c`, `Agency__c`

**Planned Key Moments:** `Q1_Events__c`, `Q2_Events__c`, `Q3_Events__c`, `Q4_Events__c`

**Value Proposition:** `Opportunity_for_Growth__c`, `Keys_to_Unlocking_Growth__c`

**Strategies and Tactics:** `Biggest_Opportunities_to_unlock_growth__c`, `Q1_Objectives__c`, `Q2_Objectives__c`, `Q3_Objectives__c`, `Q4_Objectives__c`

**Revenue Goals:** `This_Year_Annual_Spend_Est__c`, `Plan_Year_Goals__c`, `Q1_Spend_Estimate__c`, `Q2_Spend_Estimate__c`, `Q3_Spend_Estimate__c`, `Q4_Spend_Estimate__c`

**Leadership:** `Other_Asks__c`, `Leadership__c`, `Relationship_Map__c`, `Primary_Contact__c`, `Budget_Decision_Maker__c`, `Highest_Level_of_Contact__c`

**Competitive:** `Competitive_Landscape__c`, `Competitor_1__c` through `Competitor_3__c` with notes

**Problem Statements:** Q1–Q4 `Problem_Statement_for_Product_MSI__c` with category picklists

**Measurement Vendors:** `Measurement_Vendors__c`, `Q2_Measurement_Vendors__c` through `Q4_Measurement_Vendors__c`

**Review Cadence:** `Planning_Cadence__c`, `Touchbase_Frequency__c`, Q1–Q4 `Upcoming_Meetings__c`

#### Validation rules

- Quarterly spend estimates (`Q1–Q4_Spend_Estimate__c`) must sum to `This_Year_Annual_Spend_Est__c`.
- Reference fields require valid 18-character Salesforce IDs.

### How the agent maps to this contract

Each MCP tool behavior is handled by a specific part of the graph:

| MCP behavior | Agent component | Location |
|---|---|---|
| Silent field filtering in SELECT | `CallableSalesforceToolAdapter.query_salesforce()` compares requested vs returned fields | `src/app/services/salesforce_tools.py` |
| Inference-attack block | `recovery_node` parses the error, strips the blocked field, retries once | `src/app/graph/nodes/recovery.py` |
| Row-level record filtering | `normalize_node` reports the actual accessible count without assuming more exist | `src/app/graph/nodes/normalize.py` |
| Object not allowlisted / no permission | `query_execute` classifies the error type and routes to `respond` with a targeted message | `src/app/graph/nodes/query_execute.py` |
| Describe reflects integration-user FLS | Agent uses describe for field discovery, then detects per-user filtering at query time | `schema` node + adapter |
| Upsert with quarterly validation | `validate_account_plan_payload()` enforces sum and ID rules before approval | `src/app/services/account_plan.py` |
| Upload requires approval | `approval_node` blocks execution until `approved=True` | `src/app/graph/nodes/approval.py` |

## High-Level Architecture

### Shared service layer

`AgentSessionService` in `src/app/agent_service.py` is the single owner of agent runtime logic. It provides:

- `run()` — merges stored drafts with incoming data, builds the graph, invokes it, and persists session state
- `approve()` — convenience method that calls `run()` with `approved=True` and clears the draft on completion
- `get_state()` — returns the current draft and last execution state for a session
- `reset()` — clears all session data

The service owns two in-memory stores:
- `_draft_store` — partial account-plan payloads keyed by `session_id`
- `_last_state_store` — the full graph output from the most recent execution

Graph construction (`_build_graph()`) builds the adapter (demo or live MCP) and reasoner (LLM or heuristic) on each call, then compiles the LangGraph workflow. Model wiring uses `_build_reasoner()` which reads `AGENT_MODEL` from settings and falls back to heuristic mode if the model fails to load.

### Entry surfaces

All three surfaces delegate to `AgentSessionService` — none contains workflow logic.

**FastAPI HTTP server** (`src/app/api/routes.py`):
- `GET /healthz` — health check
- `POST /run` — describe, query, and draft-building flows
- `POST /approve` — approval-gated writes
- bearer-token auth via `require_api_token()`
- creates its own `AgentSessionService` instance at startup

**Outer MCP server** (`src/app/mcp_server.py`):
- Built on `FastMCP` from the `mcp` package
- Exposes 4 tools: `run_langgraph_agent`, `approve_account_plan`, `get_agent_state`, `reset_agent`
- Intentionally thin (~90 lines) — each tool is a direct delegation to `AgentSessionService`
- Supports a `context` parameter that merges into `account_plan_data` for flexible calling agents
- Run with `python -m app.mcp_server`

**CLI** (`src/app/main.py`):
- Argparse-based entry point for demo mode and live MCP smoke tests
- Reads `AGENT_MODEL` from environment
- Constructs its own reasoner and graph (does not use `AgentSessionService` since it is single-shot)

### Orchestration layer

`build_agent_graph()` in `src/app/graph/builder.py` composes the end-to-end workflow from these nodes:

- `intent` — classifies intent using LLM or heuristics via `AgentReasoner`
- `business_context` — extracts business terms, target object, and account name using LLM or heuristics
- `planning` — resolves default target object when not already set
- `resolve_account` — resolves business-language account names to Salesforce Account records
- `schema` — fetches object metadata via `describe_salesforce_object`
- `soql_builder` — constructs SOQL from schema fields and business context
- `query_execute` — executes SOQL, classifies errors into structured types
- `recovery` — strips blocked fields from inference-attack errors and retries
- `normalize` — processes raw query results into business-facing output
- `write_validate` — validates account-plan payload with 12-section readiness scoring
- `approval` — gates writes until explicit user approval
- `write_execute` — uploads the validated account plan via MCP
- `respond` — composes the final user-facing response using LLM or fallback templates

The shared graph contract is the `AgentState` typed dict in `src/app/graph/state.py`. It carries user input, resolved account information, query results, error classification (`query_error_type`), security notes, draft metadata, validation state, approval state, and the final response message.

### Adapter and integration layer

The graph depends on the `SalesforceToolAdapter` protocol in `src/app/services/contracts.py`, which defines three async operations:

- `describe_salesforce_object()`
- `query_salesforce()`
- `upload_account_plan()`

There are two concrete adapter paths:

- `CallableSalesforceToolAdapter` in `src/app/services/salesforce_tools.py` wraps the live MCP transport.
- `InMemorySalesforceToolAdapter` in the same file supports tests and local development. It includes demo data for Account, Contact, Opportunity, and Account_Plan__c objects.

The live transport is constructed by `build_streamable_http_adapter()` in `src/app/services/mcp_transport.py`, which:

- connects to the configured MCP endpoint over streamable HTTP
- injects `Authorization: Bearer <session_token>`
- verifies that the server exposes all three required tools before continuing

### Reasoning layer

`AgentReasoner` in `src/app/services/llm.py` provides dual-mode reasoning:

**LLM-backed mode** (when `AGENT_MODEL` is configured):
- `_llm_classify_intent()` — prompts the model with structured JSON output to classify intent as `describe`, `query`, or `upload_account_plan` and identify the target Salesforce object
- `_llm_interpret()` in `business_guide.py` — prompts the model to extract account name, target object, and matching business terms from natural language
- `compose_response()` — asks the model to summarize execution results into a concise message

**Heuristic mode** (when `AGENT_MODEL` is empty or model fails to load):
- `_heuristic_classify_intent()` — keyword-based intent classification
- `_heuristic_interpret()` in `business_guide.py` — signal-set matching for target object detection and business-term extraction
- `_compose_fallback_response()` — template-based response composition with structured error messages

Both modes share the same fallback chain: LLM is attempted first, and any exception (network, parsing, API key) silently falls back to heuristics. This ensures the agent always produces a response.

Model construction uses `build_chat_model()` which supports `openai:` and `gemini:` prefixes for model names.

### Business context and object support

The `business_guide.py` module maps natural language to Salesforce objects and fields:

**Object detection via signal sets:**

| Object | Signal terms |
|---|---|
| `Account_Plan__c` | account plan, plan, growth opportunities, spend, leadership, events, tactics, competitive, measurement, ... |
| `Contact` | contact, contacts, people, person, email, phone, decision maker, stakeholder |
| `Opportunity` | opportunity, opportunities, deal, deals, pipeline, revenue, close date, stage, forecast |
| `Account` | account, customer, client, advertiser, brand |

Signal matching follows a priority order: Account_Plan__c > Contact > Opportunity > Account. This ensures that specific business terms like "spend" or "competitive" route to the account-plan flow rather than a generic account lookup.

**Business-term-to-field mapping:**

`BUSINESS_FIELD_MAP` maps 21 business terms (priorities, goals, strategy, spend, leadership, competitive, events, tactics, creative, agency, marketing, cadence, meetings, problems, vendors, etc.) to their corresponding Salesforce API field names.

**Default field lists per object:**

| Object | Default fields |
|---|---|
| `Account` | Id, Name, Industry, OwnerId, CreatedDate |
| `Contact` | Id, Name, Email, Phone, Title, AccountId |
| `Opportunity` | Id, Name, StageName, Amount, CloseDate, AccountId |
| `Account_Plan__c` | AccountPlan__c, Plan_Year__c, Annual_Pinterest_Goals_Strategy__c, Business_Challenges_Priorities__c, Opportunity_for_Growth__c, This_Year_Annual_Spend_Est__c, Leadership__c, Competitive_Landscape__c |

### Summarization layer

`summary.py` produces structured business summaries for query results. Each supported object has tailored summary groups:

- **Account_Plan__c** — 12 groups: Goals, Challenges, Growth opportunities, Media/Marketing, Key moments, Tactics, Spend, Stakeholders, Competitive context, Measurement vendors, Review cadence, Recent news
- **Contact** — 5 groups: Name, Title, Email, Phone, Account
- **Opportunity** — 5 groups: Opportunity, Stage, Amount, Close date, Account
- **Account** — 2 groups: Account, Industry

### Error handling layer

Error handling follows a classify-then-message pattern:

1. `classify_query_error()` in `query_execute.py` matches raw MCP error text against known patterns and returns a structured error type string.
2. The classified type is stored as `query_error_type` on `AgentState`.
3. `_compose_error_message()` in `llm.py` maps the type to a user-friendly message from `_ERROR_MESSAGES`, falling back to the raw error text for unrecognized types.

This design separates error classification (transport-layer concern) from message composition (presentation-layer concern).

## Request Flow

### Read flow

The standard read path is:

`intent -> business_context -> planning -> resolve_account -> schema -> soql_builder -> query_execute -> normalize -> respond`

Key characteristics:

- `intent` classifies the request using LLM or heuristics. Deterministic rules take priority for unambiguous signals (e.g. presence of `soql_query` or `account_plan_data`).
- `business_context` extracts business terms, account name, and target object using LLM or heuristic signal matching. It supports all four objects: Account, Contact, Opportunity, and Account_Plan__c.
- `resolve_account` allows business-language prompts such as customer names to resolve into an account before querying.
- `schema` is invoked before non-trivial querying so query construction is grounded in available fields.
- `query_execute` always checks logical query success, classifies any error into a structured type, and reports it through `query_error_type`.
- `normalize` turns raw query output into safer business-facing output and carries forward security notes.

### Recovery flow

If `query_execute` detects a query failure containing `Inference attack detected`, routing moves to `recovery` and then retries `query_execute`.

`recovery_node()` in `src/app/graph/nodes/recovery.py`:

- extracts the blocked field from the MCP error text
- removes that field from `WHERE` or `ORDER BY`
- increments `retry_count`
- appends a security note explaining what was removed

The retry budget is intentionally limited to one recovery attempt.

### Write flow

The write path is:

`intent -> business_context -> planning -> resolve_account -> write_validate -> approval -> write_execute -> respond`

Key characteristics:

- `write_validate_node()` enriches the payload with inferred account and plan-year values when possible.
- Drafts are scored across 12 sections with weighted readiness calculation.
- Drafts can remain in `needs_input` state while still accumulating useful partial information.
- Valid payloads do not execute immediately; they first move to `needs_approval`.
- `approval_node` gates writes so uploads only happen after explicit approval.

## Account-Plan Drafting Model

### 12-section structure

The account-plan draft in `src/app/services/account_plan.py` is organized into 12 progressively fillable sections:

| Section | Key fields | Weight |
|---|---|---|
| Foundation | AccountPlan__c, Plan_Year__c | 25% |
| Strategy | Annual_Pinterest_Goals_Strategy__c, Business_Challenges_Priorities__c, Opportunity_for_Growth__c | 20% |
| Client objectives | CEO_Strategic_Priorities__c, Recent_News__c | 5% |
| Media / Marketing | Pinterest_Account_Health__c, CMO_Marketing_Goals_Approach__c, Measurement__c, Creative_Strategy__c, Agency__c | 5% |
| Key moments | Q1–Q4_Events__c | 5% |
| Value proposition | Opportunity_for_Growth__c, Keys_to_Unlocking_Growth__c | 5% |
| Tactics | Biggest_Opportunities_to_unlock_growth__c, Q1–Q4_Objectives__c | 5% |
| Spend plan | This_Year_Annual_Spend_Est__c, Plan_Year_Goals__c, Q1–Q4_Spend_Estimate__c | 15% |
| Stakeholders | Leadership__c, Relationship_Map__c, Primary_Contact__c, Budget_Decision_Maker__c, Highest_Level_of_Contact__c | 5% |
| Competitive | Competitive_Landscape__c, Competitor_1–3__c | 3% |
| Measurement vendors | Measurement_Vendors__c, Q2–Q4_Measurement_Vendors__c | 3% |
| Review cadence | Planning_Cadence__c, Touchbase_Frequency__c, Q1–Q4_Upcoming_Meetings__c | 4% |

### Readiness scoring

The readiness score is the weighted sum of completed sections. Labels are:

- `early` — 0–39%
- `partial` — 40–69%
- `almost_ready` — 70–89%
- `ready` — 90–100%

### Guided drafting

`recommend_next_question()` provides 49 context-sensitive prompts across all 12 sections to guide users through the drafting process. The agent selects the most relevant next question based on which sections are incomplete.

### Upload preview

`_build_upload_preview()` generates a human-readable summary of the payload that will be written, covering all populated fields across all 12 categories.

## Drafting and Session Model

Both the FastAPI server and the outer MCP server support multi-turn account-plan drafting through `session_id`. Session management is centralized in `AgentSessionService` (`src/app/agent_service.py`):

- `merge_account_plan_draft()` merges non-empty incoming fields onto the stored draft
- `should_persist_draft()` keeps draft memory only for the `upload_account_plan` intent
- successful upload clears the stored draft
- `get_state()` exposes the current draft and last execution state for inspection
- `reset()` clears all session data for a given session

This design favors a simple user experience for guided drafting, but the storage is process-local memory only. It is not durable and is not shared across workers or across the different entry surfaces if they run in separate processes.

## Security and Safety Design

The project is explicitly designed to preserve all four SecuredSOQL security layers rather than hide them.

### Agent-level auth

- API access is protected by a configured bearer token via `AGENT_API_TOKEN`.
- MCP calls carry a separate bearer token via `SESSION_TOKEN` or the request payload; this token is what the MCP server uses for JWT-based caller identification.

### Layer 3 handling: field-level security and PII policy

The SecuredSOQL server silently removes PII/restricted fields from `SELECT` and blocks queries that use them in `WHERE` or `ORDER BY`. The agent handles both sides:

**Silent field filtering.** `CallableSalesforceToolAdapter.query_salesforce()` compares requested fields with actually returned fields. Any requested field missing from the returned records is treated as filtered by Salesforce security policy and recorded in `filtered_fields` and `security_notes`. The response layer is forbidden from inferring or hallucinating hidden data.

**Inference-attack blocking.** When the MCP server returns an `Inference attack detected` error, `recovery_node` extracts the blocked field from the error text, removes it from the `WHERE` or `ORDER BY` clause, and retries the query once. The removal is reported through `security_notes` so the caller can understand why the retried query differs from the original.

### Layer 4 handling: row-level security

The returned record count may be less than `LIMIT` because the server filters rows the target user cannot see. The `normalize` node reports the actual accessible count and never assumes additional records exist beyond what was returned.

### Describe vs query FLS gap

`describe_salesforce_object` returns field metadata scoped to the integration user, not the target user. This means describe may list fields that are subsequently filtered during query execution. The agent accounts for this by always comparing requested versus returned fields at query time rather than trusting the describe result as a guarantee of visibility.

### Error transparency

All query errors are classified into structured types and presented to the user with clear, actionable messages. The agent never silently swallows errors or presents generic failure messages when a specific explanation is available.

### Write safety

Write safety relies on multiple checkpoints:

1. Account resolution before payload construction.
2. Payload validation in `validate_account_plan_payload()` — required fields, quarterly-sum consistency, and 18-character Salesforce ID format checks.
3. Draft readiness scoring across 12 weighted sections with upload preview generation.
4. Explicit approval before upload (the `approval` node blocks execution until `approved=True`).

## Configuration and Operations

Runtime configuration lives in `src/app/config.py`.

Important settings:

| Variable | Purpose | Default |
|---|---|---|
| `AGENT_MODEL` | LLM for intent classification and response composition. Empty = heuristic-only mode. Supports `openai:` and `gemini:` prefixes. | `openai:gpt-4o-mini` |
| `AGENT_API_TOKEN` | Bearer token for API authentication | `change-me` |
| `HOST` | Server bind address | `127.0.0.1` |
| `PORT` | Server bind port | `8081` |
| `MCP_URL` | Salesforce MCP server endpoint | `http://127.0.0.1:8000/mcp` |
| `SESSION_TOKEN` | Bearer token for MCP server authentication | `change-me` |
| `OPENAI_API_KEY` | OpenAI API key (required when using `openai:` model prefix) | — |
| `GEMINI_API_KEY` | Google API key (required when using `gemini:` model prefix) | — |

When `AGENT_MODEL` is configured and the corresponding API key is available, the agent uses LLM-backed intent classification, business context extraction, and response composition. If the model fails to load or any LLM call fails at runtime, the agent silently falls back to heuristic mode.

## Testing Strategy

The test suite under `tests/` contains 98 tests across 12 files, covering behavioral contracts rather than implementation details:

| Area | Test file | Coverage |
|---|---|---|
| Graph routing and recovery | `test_graph_routing.py` | Inference-attack retry, approval gating, upload execution |
| Filtered-field detection | `test_field_filter_detection.py` | Silent field removal by SecuredSOQL |
| Account resolution | `test_entity_resolution.py` | Ambiguous account matching |
| MCP transport mapping | `test_mcp_transport.py` | Tool discovery and adapter construction |
| Account-plan validation | `test_account_plan_validation.py` | Required fields and quarterly sum checks |
| Draft memory | `test_draft_memory.py` | Multi-turn draft merging and scoring |
| Business-guided flows | `test_business_guided_mode.py` | Business-language to Salesforce field mapping |
| Expanded draft sections | `test_expanded_draft_sections.py` | All 12 sections, readiness scoring, next-question prompts, upload preview |
| Error classification | `test_error_classification.py` | Error type classification, user-facing messages, end-to-end error flows |
| Contact and Opportunity | `test_contact_opportunity.py` | Signal detection, default fields, summary groups, graph describe/query, heuristic fallback |
| Agent session service | `test_agent_service.py` | Multi-turn draft merging via service, session reset, `merge_account_plan_draft` helper |
| MCP server wrapper | `test_mcp_server.py` | Multi-turn session through MCP tools, `get_agent_state`, `reset_agent` |

All tests run with `model=None` (heuristic mode) to ensure deterministic, fast execution without API dependencies.

## Key Design Trade-Offs

### Strengths

- Three entry surfaces (API, MCP server, CLI) share a single `AgentSessionService` with no logic duplication.
- The outer MCP server is intentionally thin — a clean wrapping pattern for agent-as-a-tool composition.
- Clear separation between orchestration and transport.
- Strong handling of SecuredSOQL-specific failure modes with structured error classification.
- Dual-mode reasoning (LLM + heuristic) with graceful degradation.
- Four-object support (Account, Contact, Opportunity, Account_Plan__c) with tailored field defaults and summarization.
- Comprehensive 12-section account-plan drafting with weighted readiness scoring.
- Business-user-friendly interactions without exposing raw Salesforce concepts by default.
- Approval-gated writes reduce the chance of accidental mutation.

### Constraints

- Draft persistence is ephemeral (process-local memory only). This matters more now that three surfaces could run in separate processes.
- The graph is rebuilt on every request; could be cached for the same adapter configuration.
- The system is limited to the current three-tool inner MCP surface.
- LLM-backed mode requires external API keys and adds latency.
- Contact and Opportunity support covers describe and query flows but not write flows.

## Recommended Future Evolution

1. Replace in-memory draft storage with durable shared persistence for multi-worker deployments.
2. Add richer observability around graph state transitions, recovery retries, error classification, and approval outcomes.
3. Version the MCP contract explicitly so agent behavior can evolve safely with server changes.
4. Extend write support to additional objects beyond Account_Plan__c as the MCP server surface expands.
5. Add streaming response support for long-running queries and LLM-backed composition.
