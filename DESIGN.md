# Salesforce SecuredSOQL Agent Design

## Overview

This project implements a LangGraph-based Salesforce agent that sits between a caller and a Salesforce MCP server. The agent is designed around the behavior of a SecuredSOQL query surface rather than generic Salesforce assumptions. Its main responsibilities are:

- route requests into object description, secure querying, or account-plan upload flows
- surface security-filtered data transparently instead of inventing missing fields
- recover from SecuredSOQL inference-attack failures when possible
- guide business users through multi-turn account-plan drafting before write approval

The primary runtime surfaces are the FastAPI application in `src/app/api/routes.py` and the CLI entry point in `src/app/main.py`.

## Goals

1. Provide a single agent entry point for three MCP tools: `describe_salesforce_object`, `query_salesforce`, and `upload_account_plan`.
2. Keep orchestration logic stable across demo and live MCP integrations by isolating transport behind a small adapter contract.
3. Make security behavior explicit by detecting filtered fields, respecting row-level visibility, and handling restricted filter failures.
4. Support business-language interactions for account understanding and account-plan drafting.
5. Block writes until payload validation and explicit user approval succeed.

## Non-Goals

- Acting as a general-purpose Salesforce analyst across the full object model.
- Persisting drafts durably across API process restarts.
- Replacing Salesforce authorization or bypassing MCP server security decisions.
- Performing autonomous writes without a human approval step.

## System Context

The system has four major layers:

1. API and CLI entry points accept user input, auth context, and optional session state.
2. The LangGraph workflow in `src/app/graph/builder.py` routes each request through intent classification, retrieval, validation, and response composition.
3. Service modules provide transport, business heuristics, validation, summarization, and entity resolution.
4. The Salesforce MCP server remains the source of truth for schema, query execution, and account-plan upload behavior.

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

#### Error taxonomy

| Error text | Meaning | Agent handling |
|---|---|---|
| `Inference attack detected` on field X | Restricted field used in WHERE/ORDER BY | Remove the field from the clause, retry once |
| `not permitted for querying` | Object is not allowlisted | Report to caller, do not retry |
| `does not have permission` | User lacks access to the object | Report to caller, do not retry |
| `Missing required parameter` | Missing `soql` or `targetUserEmail` | Programming error in the agent |
| `Invalid email format` | Bad email value | Report to caller |
| `No user found with email` | Email does not exist or user is inactive | Report to caller |

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
| Object not allowlisted / no permission | `query_execute` sets `status=error` and routes to `respond` | `src/app/graph/nodes/query_execute.py` |
| Describe reflects integration-user FLS | Agent uses describe for field discovery, then detects per-user filtering at query time | `schema` node + adapter |
| Upsert with quarterly validation | `validate_account_plan_payload()` enforces sum and ID rules before approval | `src/app/services/account_plan.py` |
| Upload requires approval | `approval_node` blocks execution until `approved=True` | `src/app/graph/nodes/approval.py` |

## High-Level Architecture

### Entry points

- `src/app/api/routes.py`
  - exposes `GET /healthz`
  - exposes `POST /run` for describe, query, and draft-building flows
  - exposes `POST /approve` for approval-gated writes
  - enforces bearer-token auth with `require_api_token()`
  - stores partial account-plan drafts in `app.state.draft_store`
- `src/app/main.py`
  - provides a local CLI for demo mode and live MCP smoke tests

### Orchestration layer

`build_agent_graph()` in `src/app/graph/builder.py` composes the end-to-end workflow from these nodes:

- `intent`
- `business_context`
- `planning`
- `resolve_account`
- `schema`
- `soql_builder`
- `query_execute`
- `recovery`
- `normalize`
- `write_validate`
- `approval`
- `write_execute`
- `respond`

The shared graph contract is the `AgentState` typed dict in `src/app/graph/state.py`. It carries user input, resolved account information, query results, security notes, draft metadata, validation state, approval state, and the final response message.

### Adapter and integration layer

The graph depends on the `SalesforceToolAdapter` protocol in `src/app/services/contracts.py`, which defines three async operations:

- `describe_salesforce_object()`
- `query_salesforce()`
- `upload_account_plan()`

There are two concrete adapter paths:

- `CallableSalesforceToolAdapter` in `src/app/services/salesforce_tools.py` wraps the live MCP transport.
- `InMemorySalesforceToolAdapter` in the same file supports tests and local development.

The live transport is constructed by `build_streamable_http_adapter()` in `src/app/services/mcp_transport.py`, which:

- connects to the configured MCP endpoint over streamable HTTP
- injects `Authorization: Bearer <session_token>`
- verifies that the server exposes all three required tools before continuing

### Reasoning and business logic

- `src/app/services/llm.py`
  - contains `AgentReasoner`
  - classifies intent with lightweight rules and optional model support
  - composes final user-facing responses
- `src/app/services/account_plan.py`
  - builds progressively enriched account-plan drafts
  - calculates readiness score and label
  - generates upload previews and next-question guidance
  - validates required fields, quarterly totals, and Salesforce ID formats
- `src/app/services/entity_resolution.py`
  - ranks account matches by normalized name similarity
  - decides whether a best match is unambiguous

## Request Flow

### Read flow

The standard read path is:

`intent -> business_context -> planning -> resolve_account -> schema -> soql_builder -> query_execute -> normalize -> respond`

Key characteristics:

- `intent` distinguishes describe, query, and upload-account-plan requests.
- `resolve_account` allows business-language prompts such as customer names to resolve into an account before querying.
- `schema` is invoked before non-trivial querying so query construction is grounded in available fields.
- `query_execute` always checks logical query success, not just transport success.
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
- Drafts can remain in `needs_input` state while still accumulating useful partial information.
- Valid payloads do not execute immediately; they first move to `needs_approval`.
- `approval_node` gates writes so uploads only happen after explicit approval.

## Drafting and Session Model

The API layer supports multi-turn account-plan drafting through `session_id`.

In `src/app/api/routes.py`:

- `merge_account_plan_draft()` merges non-empty incoming fields onto the stored draft
- `should_persist_draft()` keeps draft memory only for the `upload_account_plan` intent
- successful upload clears the stored draft

This design favors a simple user experience for guided drafting, but the storage is process-local memory only. It is not durable and is not shared across workers.

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

### Write safety

Write safety relies on multiple checkpoints:

1. Account resolution before payload construction.
2. Payload validation in `validate_account_plan_payload()` — required fields, quarterly-sum consistency, and 18-character Salesforce ID format checks.
3. Draft readiness scoring and upload preview generation.
4. Explicit approval before upload (the `approval` node blocks execution until `approved=True`).

## Configuration and Operations

Runtime configuration lives in `src/app/config.py`.

Important settings:

- `AGENT_MODEL`
- `AGENT_API_TOKEN`
- `HOST`
- `PORT`
- `MCP_URL`
- `SESSION_TOKEN`

The current default model string is `openai:gpt-5.4-mini`, but the API and CLI currently instantiate `AgentReasoner(model=None)`, so the system mostly operates on deterministic heuristics and fallback responses unless model wiring is expanded later.

## Testing Strategy

The test suite under `tests/` focuses on behavioral contracts rather than implementation details. Covered areas include:

- graph routing
- filtered-field detection
- inference-attack recovery
- account resolution
- MCP transport mapping
- account-plan validation
- draft memory behavior
- business-guided flows

This test shape matches the architecture: thin transport mapping, explicit orchestration, and domain-specific safety logic.

## Key Design Trade-Offs

### Strengths

- Clear separation between orchestration and transport.
- Strong handling of SecuredSOQL-specific failure modes.
- Business-user-friendly drafting flow without exposing raw Salesforce concepts by default.
- Approval-gated writes reduce the chance of accidental mutation.

### Constraints

- Draft persistence is ephemeral.
- The object model and heuristics are strongest around `Account` and `Account_Plan__c`.
- Intent classification and response composition are still mostly rule-based.
- The system is limited to the current three-tool MCP surface.

## Recommended Future Evolution

1. Replace in-memory draft storage with durable shared persistence.
2. Promote model-backed reasoning from optional scaffolding to a first-class runtime path.
3. Expand schema-aware query planning beyond the current strongest object flows.
4. Add richer observability around graph state transitions, recovery retries, and approval outcomes.
5. Version the MCP contract explicitly so agent behavior can evolve safely with server changes.
