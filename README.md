# Salesforce SecuredSOQL Agent

LangGraph-based agent for a Salesforce MCP server that exposes:

- `describe_salesforce_object`
- `query_salesforce`
- `upload_account_plan`

This project is built around the server's SecuredSOQL behavior rather than generic Salesforce assumptions.

## Quick links

- **MCP Server Guide**: [MCP_GUIDE.md](MCP_GUIDE.md) - Complete guide for using this agent as an MCP server
- **Business-user instructions**: [BUSINESS_USER_GUIDE.md](BUSINESS_USER_GUIDE.md)
- **Design document**: [DESIGN.md](DESIGN.md)
- Source entrypoints:
  - API: [src/app/api/routes.py](src/app/api/routes.py)
  - MCP server: [src/app/mcp_server.py](src/app/mcp_server.py)
  - Shared service: [src/app/agent_service.py](src/app/agent_service.py)
  - CLI: [src/app/main.py](src/app/main.py)
  - Graph: [src/app/graph/builder.py](src/app/graph/builder.py)

## What this agent does

- routes requests into `describe`, `query`, or `upload_account_plan`
- describes objects before non-trivial querying
- handles SecuredSOQL-specific failures like inference-attack blocks
- detects silently filtered fields by comparing requested vs returned fields
- validates account-plan payloads before write execution
- requires approval before upload
- supports business-user-guided account-plan drafting
- supports session-based partial draft accumulation with `session_id`
- can be hosted as an MCP server that wraps the LangGraph runtime directly

## MCP server contract

The target Salesforce MCP server is exposed over Streamable HTTP and provides three tools.

### `describe_salesforce_object`

Used to discover object structure before query construction.

Returns:
- object metadata
- fields
- field types
- lookup/reference targets

### `query_salesforce`

Uses a custom SecuredSOQL API, not standard SOQL execution.

Important behaviors:
- always check `success`, not just transport success
- requested `SELECT` fields may be silently removed
- restricted fields in `WHERE` or `ORDER BY` can block the query
- returned record count can be smaller than `LIMIT` because of row-level security

### `upload_account_plan`

Creates or updates `Account_Plan__c` using Account + Plan Year upsert logic.

Required fields:
- `AccountPlan__c`
- `Plan_Year__c`

Important behaviors:
- quarterly spend should sum to annual spend
- reference fields must contain valid Salesforce IDs

## Design principles

The graph is intentionally structured around the MCP server's constraints:

- `describe` comes before non-trivial querying
- query execution checks `success` explicitly
- missing fields are treated as security-filtered, never hallucinated
- inference-attack errors trigger a controlled retry path
- writes go through validation, readiness review, and approval before upload

## Current capabilities

### Technical flows

- object discovery
- secure read-only querying
- filtered-field transparency
- inference-attack retry for restricted query clauses
- account-plan validation
- approval-gated account-plan upload
- live Streamable HTTP Salesforce MCP adapter path
- outer MCP server wrapper for other AI agents

### Business-user-guided flows

- company-name-based account resolution
- business-language mapping to likely Salesforce fields
- guided account-plan drafting
- readiness scoring
- upload preview before approval
- next-best-question guidance
- session-based draft accumulation

## Project layout

```text
src/app/
  agent_service.py Shared runtime used by API and MCP server
  api/             FastAPI routes
  graph/           LangGraph state + nodes
  mcp_server.py    MCP wrapper that exposes the agent as tools
  models/          API request/response models
  services/        MCP adapters, validation, business logic
  utils/           SOQL parsing and Salesforce helpers
tests/             Behavior-focused tests
```

## Install

```bash
pip install -e ".[dev]"
```

## Run the API

```bash
export OPENAI_API_KEY="your_key"
export AGENT_API_TOKEN="change-me"
python -m uvicorn app.api.routes:app --host 127.0.0.1 --port 8081
```

## Run as an MCP server

This project can also be hosted as its own MCP server. In that mode:

- AI agents connect over MCP protocol (stdio transport)
- The server calls the shared `AgentSessionService`
- The service runs the LangGraph workflow
- The workflow calls the inner Salesforce MCP server when needed

### Quick Start

```bash
python -m app.mcp_server
```

The server uses stdio transport and is compatible with any MCP client.

### MCP Features

**4 Tools:**
- `run_langgraph_agent` — Execute agent with natural language prompts
- `approve_account_plan` — Approve and upload drafted plans
- `get_agent_state` — Inspect session state
- `reset_agent` — Clear session data

**2 Resources:**
- `draft://sessions` — List all active draft sessions
- `draft://sessions/{session_id}` — Read specific draft state

**2 Prompts:**
- `salesforce-query-guided` — Interactive query building guide
- `account-plan-guided` — Step-by-step plan creation guide

### Complete Documentation

See **[MCP_GUIDE.md](MCP_GUIDE.md)** for comprehensive documentation including:
- Setup and configuration
- Tool usage examples
- Resource access patterns
- Multi-turn workflow examples
- Session management
- Security features
- Troubleshooting

The MCP wrapper is intentionally thin. It delegates to [agent_service.py](src/app/agent_service.py) instead of duplicating workflow logic.

## API usage

### `POST /run`

Use this for:
- describe requests
- read-only queries
- draft creation or draft continuation
- pre-validation before approval

Useful request fields:
- `user_input`
- `session_id`
- `sobject_name`
- `soql_query`
- `account_plan_data`
- `use_demo_adapter`
- `mcp_url`
- `session_token`

Example:

```json
{
  "session_id": "nike-plan-2026",
  "user_input": "Help me prepare a 2026 account plan for Nike"
}
```

### `POST /approve`

Use this after a `needs_approval` response.

Example:

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

### Session behavior

If you reuse the same `session_id`, the API merges new `account_plan_data` into the existing draft so callers do not need to resend the entire payload on each step.

## CLI usage

### Demo mode

```bash
python -m app.main --input "Describe the Account object" --object Account --use-demo-adapter
```

### Live MCP smoke test

```bash
python -m app.main --smoke-live-mcp --mcp-url "http://127.0.0.1:8000/mcp" --session-token "your_token"
```

This performs a lightweight `describe_salesforce_object("Account")` call and prints the object name and field count.

## Current limitations

- draft persistence is process-local, not durable storage
- Contact and Opportunity support covers read flows but not write flows
- constrained to the current 3-tool inner Salesforce MCP surface
- graph is rebuilt per request (could be cached)

## Testing

Run:

```bash
pytest -q
```

The test suite covers:
- graph routing
- filtered-field detection
- inference-attack recovery
- account resolution
- MCP adapter mapping
- draft scoring and memory helpers
- shared agent service behavior
- MCP wrapper behavior

## Notes on integration

The MCP transport is isolated behind a thin adapter layer. The project includes:

- a demo in-memory adapter for local development
- a real Streamable HTTP adapter using `langchain-mcp-adapters`

That keeps the graph logic stable while allowing either local testing or live MCP integration.
