# Salesforce SecuredSOQL Agent

Standalone LangGraph agent for the Salesforce MCP server described in the prompt.

## What it does

- Routes requests into `describe`, `query`, or `upload_account_plan`
- Describes objects before non-trivial querying
- Handles SecuredSOQL-specific failures like inference-attack blocks
- Detects silently filtered fields by comparing requested vs returned fields
- Requires explicit approval before write execution

## MCP server description

This project targets a Salesforce MCP server exposed over Streamable HTTP with three tools:

1. `describe_salesforce_object`
   Describes a Salesforce object and returns its available fields, field types, and lookup targets. This should be used before building SOQL so the agent knows what fields exist and which ones are references.

2. `query_salesforce`
   Executes a query through a custom SecuredSOQL API. This is not standard Salesforce SOQL behavior. The server applies multiple security layers:
   - caller permission check
   - object allowlist enforcement
   - field-level security and PII filtering
   - row-level security filtering

   Important behaviors:
   - always inspect the `success` field, not just transport success
   - requested fields in `SELECT` may be silently removed
   - restricted fields in `WHERE` or `ORDER BY` can block the entire query
   - returned record count can be less than `LIMIT` because inaccessible rows are filtered out

3. `upload_account_plan`
   Creates or updates `Account_Plan__c` records using Account + Plan Year upsert logic. The payload must include:
   - `AccountPlan__c`: 18-character Salesforce Account ID
   - `Plan_Year__c`: plan year value such as `2026`

   Additional server-side expectations:
   - quarterly spend values should sum to the annual spend
   - reference fields must be valid Salesforce IDs

## Why the agent is structured this way

The workflow is intentionally built around the MCP server contract rather than generic Salesforce assumptions:

- `describe` comes before non-trivial querying
- query execution checks `success` explicitly
- missing response fields are treated as security-filtered, never hallucinated
- inference-attack errors trigger a controlled retry path
- writes go through validation and approval before execution

## How end users should use this agent

End users can use the agent in three main ways depending on the task:

1. Discover object structure
   Ask the agent to describe an object when you want to understand what fields are available.

   Examples:
   - "Describe the Account object"
   - "Show me the fields on Account_Plan__c"
   - "What lookup fields exist on Contact?"

2. Query Salesforce data
   Ask the agent a read-only question or provide an explicit SOQL query. The agent will describe the object first when needed, run the query through the SecuredSOQL tool, and report any fields filtered by policy.

   Examples:
   - "Show me 10 Accounts with Id, Name, and Industry"
   - "Find a few Account records created recently"
   - "Run this query: SELECT Id, Name FROM Account LIMIT 5"

   What users should expect:
   - the agent may return fewer rows than the query limit
   - some requested fields may be omitted by security policy
   - if a query uses a restricted field in `WHERE` or `ORDER BY`, the agent may retry with a safer version when possible

3. Create or update an account plan
   Provide account plan data when the goal is to upsert an `Account_Plan__c` record. The agent validates the payload before attempting the write.

   Required fields:
   - `AccountPlan__c`
   - `Plan_Year__c`

   Example payload shape:

```json
{
  "AccountPlan__c": "001000000000000AAA",
  "Plan_Year__c": "2026",
  "This_Year_Annual_Spend_Est__c": "100000",
  "Q1_Spend_Estimate__c": "25000",
  "Q2_Spend_Estimate__c": "25000",
  "Q3_Spend_Estimate__c": "25000",
  "Q4_Spend_Estimate__c": "25000"
}
```

   What users should expect:
   - the agent validates required fields before write execution
   - the write flow pauses for approval
   - the upload only runs after explicit approval

## Business-user guided mode

This project now includes a business-user guidance layer for people who know the customer and business goal, but do not know Salesforce object names or field API names.

What the guided mode does:

- translates business phrases such as `priorities`, `growth opportunities`, `spend`, `leadership`, and `strategy` into likely Salesforce fields
- infers whether the request is better served by `Account` or `Account_Plan__c`
- tries to resolve a company name like `Nike` to an Account record before querying account-plan data
- returns `needs_input` instead of failing hard when the request is missing business-critical information
- tells the user what it inferred and what still needs to be provided
- builds an account-plan draft in business sections such as foundation, strategy, spend plan, and stakeholders
- assigns a draft readiness score before approval
- generates an upload preview so business users can review what will be written
- can accumulate draft data across API calls within the same `session_id`
- recommends the next best business question based on what is still missing

Examples:

- "Show me Nike client priorities and growth opportunities"
- "Help me prepare a 2026 account plan for Nike"
- "What do we know about Acme's strategy and spend?"

Typical guided behavior:

1. The agent extracts the business intent and likely customer name.
2. It resolves the customer to an accessible Salesforce Account when possible.
3. It maps business concepts to a field set on the relevant object.
4. It runs a secure query or prepares an account-plan draft.
5. If information is missing, it responds with what it still needs, such as:
   - account selection
   - plan year
   - quarterly spend breakdown
   - goals or strategy
   - stakeholder context
6. For account-plan workflows, it can carry the partial draft forward when the caller keeps using the same `session_id`.

This mode is still constrained by the current MCP server. It can guide the user using the three existing tools, but it does not invent data and cannot bypass Salesforce security filtering.

## Supported use cases

The agent currently covers the following use cases.

1. Salesforce object discovery

   Example prompts:
   - "Describe the Account object"
   - "What fields are on Account_Plan__c?"
   - "Which lookup fields exist on Contact?"

   Expected behavior:
   - the agent calls `describe_salesforce_object`
   - it returns field names, types, and lookup targets
   - it helps the user understand structure before any query is written

2. Secure read-only Salesforce queries

   Example prompts:
   - "Show me 10 Accounts with Id, Name, and Industry"
   - "Run this query: SELECT Id, Name FROM Account LIMIT 5"
   - "Get a few account plan records for this account"

   Expected behavior:
   - the agent describes the object first when needed
   - it executes the query through `query_salesforce`
   - it checks the `success` field explicitly
   - it explains when fields were filtered or rows were reduced by security policy

3. Query recovery for restricted filters

   Example prompts:
   - a user provides a SOQL query that uses a restricted field in `WHERE`
   - a user provides a SOQL query that uses a restricted field in `ORDER BY`

   Expected behavior:
   - if the server returns an inference-attack error, the agent retries once with the blocked field removed from the filter or ordering clause
   - if recovery is not possible, it returns a clear explanation instead of failing silently

4. Filtered-field transparency

   Example prompts:
   - "Show me Id, Name, and Email for Contacts"
   - "Run this query and tell me what came back"

   Expected behavior:
   - the agent compares requested fields with returned fields
   - missing fields are reported as security-filtered
   - the agent never invents missing values

5. Account plan validation before write

   Example prompts:
   - "Validate this 2026 account plan payload"
   - "Check whether this account plan is ready to upload"

   Expected behavior:
   - the agent validates required fields
   - it checks that quarterly spend totals match the annual spend
   - it checks whether known reference fields look like Salesforce IDs
   - if validation fails, it returns the missing or invalid inputs

6. Approval-gated account plan upload

   Example prompts:
   - "Create this account plan"
   - "Upload the 2026 account plan for this account"

   Expected behavior:
   - the agent validates first
   - if valid, it pauses in `needs_approval`
   - only after approval does it call `upload_account_plan`

7. Business-language account and plan exploration

   Example prompts:
   - "Show me Nike client priorities and growth opportunities"
   - "What do we know about Acme's strategy and spend?"
   - "Show me leadership context for this client"

   Expected behavior:
   - the agent infers the likely business topic
   - it maps business concepts like `priorities`, `growth opportunities`, `spend`, and `leadership` to likely Salesforce fields
   - it chooses the most likely target object, typically `Account` or `Account_Plan__c`
   - it runs a secure query and returns the accessible results

8. Company-name-based account resolution

   Example prompts:
   - "Show me Nike priorities"
   - "Prepare a plan for Acme"

   Expected behavior:
   - the agent tries to resolve the company name to an accessible Salesforce Account
   - if exactly one match is found, it continues automatically
   - if multiple matches are found, it returns `needs_input` and asks the user to choose
   - if no accessible match is found, it tells the user what it could not resolve

9. Guided account-plan preparation for business users

   Example prompts:
   - "Help me prepare a 2026 account plan for Nike"
   - "Create a draft account plan for Acme next year"

   Expected behavior:
   - the agent infers that the user wants an account-plan workflow
   - it resolves the company name when possible
   - it builds a staged draft with sections for:
     - foundation
     - strategy
     - spend plan
     - stakeholders
   - it assigns a readiness score such as `early`, `partial`, `almost_ready`, or `ready`
   - it generates an upload preview summarizing:
     - account
     - plan year
     - key goals or challenges
     - spend details when present
     - completed vs incomplete sections
   - it recommends the next best question to ask the business user
   - it identifies what information is still missing, such as:
     - account selection
     - plan year
     - quarterly spend breakdown
     - goals or strategy
     - leadership or contact context
   - it returns `needs_input` guidance instead of forcing the user to provide raw JSON immediately

11. Business-friendly summaries for accessible account-plan data

   Example prompts:
   - "Summarize Nike's account plan"
   - "Give me the main points for Acme"

   Expected behavior:
   - the agent formats accessible records into business-friendly summaries such as:
     - goals
     - challenges
     - growth opportunities
     - spend
     - leadership context
   - it still reports filtered fields when Salesforce omits data for security reasons

12. Upload readiness review before approval

   Example prompts:
   - "Is this account plan ready to upload?"
   - "What will be written if I approve this plan?"

   Expected behavior:
   - the agent computes a readiness score across draft sections
   - it labels the draft as `early`, `partial`, `almost_ready`, or `ready`
   - it returns an upload preview before write approval
   - if the draft is still thin, it keeps the workflow in `needs_input` instead of advancing too early

13. Persistent draft sessions across API calls

   Example flow:
   - first call: "Start a 2026 account plan for Nike"
   - second call with same `session_id`: provide goals
   - third call with same `session_id`: provide spend targets
   - fourth call with same `session_id`: ask whether it is ready to upload

   Expected behavior:
   - the API merges new account-plan fields into the existing draft for that `session_id`
   - the agent does not require the caller to resend the whole payload every time
   - the stored draft is cleared after a successful approval/upload flow

14. Developer-oriented direct API usage

   Example prompts:
   - explicit `soql_query`
   - explicit `sobject_name`
   - explicit `account_plan_data`

   Expected behavior:
   - the agent supports direct structured inputs through the FastAPI service
   - this path is useful for UI integration, testing, or automation

## Current limitations

- The agent is strongest around `Account` and `Account_Plan__c` use cases.
- It does not yet perform broad multi-object synthesis across many Salesforce entities.
- The business-guided mode now stages draft sections and can persist partial drafts by `session_id`, but it is still not a full conversational planner with sophisticated long-horizon memory.
- The agent is limited to the capabilities of the current MCP server:
  - `describe_salesforce_object`
  - `query_salesforce`
  - `upload_account_plan`

## End-user API flow

If the user is calling the FastAPI service directly:

1. Call `POST /run` for describe, query, or pre-validation of an account plan write.
2. If the response status is `needs_approval`, review the payload and call `POST /approve`.
3. Read the final `message` and structured `data` fields in the response.
4. Reuse the same `session_id` across related account-plan drafting calls if you want the API to accumulate partial plan data.

Typical request examples:

Describe an object:

```json
{
  "user_input": "Describe the Account object",
  "sobject_name": "Account"
}
```

Run a query:

```json
{
  "user_input": "Run an account query",
  "soql_query": "SELECT Id, Name, Industry FROM Account LIMIT 5"
}
```

Validate a write:

```json
{
  "session_id": "nike-plan-2026",
  "user_input": "Create a 2026 account plan",
  "account_plan_data": {
    "AccountPlan__c": "001000000000000AAA",
    "Plan_Year__c": "2026"
  }
}
```

Approve a write:

```json
{
  "session_id": "nike-plan-2026",
  "user_input": "Create a 2026 account plan",
  "approved": true,
  "account_plan_data": {
    "AccountPlan__c": "001000000000000AAA",
    "Plan_Year__c": "2026"
  }
}
```

## Project layout

```text
src/app/
  api/          FastAPI routes
  graph/        LangGraph state + nodes
  services/     MCP adapters, validation, LLM helpers
  utils/        SOQL parsing and Salesforce ID validation
tests/          Focused behavior tests
```

## Install

```powershell
cd C:\Users\tiger\project\salesforce-securedsoql-agent
python -m pip install -e .[dev]
```

## Run the API

```powershell
$env:OPENAI_API_KEY="your_key"
$env:AGENT_API_TOKEN="change-me"
python -m uvicorn app.api.routes:app --host 127.0.0.1 --port 8081
```

## Run the CLI demo

```powershell
python -m app.main --input "Describe the Account object" --object Account
```

## Smoke test a live MCP server

Use the CLI to verify that the live Streamable HTTP MCP endpoint is reachable and exposes the expected Salesforce tools:

```powershell
python -m app.main --smoke-live-mcp --mcp-url "http://127.0.0.1:8000/mcp" --session-token "your_token"
```

This smoke path performs a lightweight `describe_salesforce_object("Account")` call and prints the object name and field count.

## Notes on MCP integration

This project keeps MCP transport behind a thin adapter interface. The graph is fully implemented and tested, and it now includes a real Streamable HTTP adapter path using `langchain-mcp-adapters` for the three required Salesforce tools.
