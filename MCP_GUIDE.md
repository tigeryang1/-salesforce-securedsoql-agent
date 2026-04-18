# MCP Server Guide

Complete guide for using the Salesforce SecuredSOQL Agent as an MCP server.

## Overview

This agent can run as an **MCP server**, exposing its capabilities to any MCP-compatible client.

### What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) is an open standard for connecting AI applications to external data sources and tools. When this agent runs as an MCP server, AI assistants can:

- Query Salesforce data with automatic security handling
- Create account plans through guided workflows
- Inspect draft state without modifying it
- Follow interactive prompts for complex tasks

## Quick Start

### 1. Install Dependencies

```bash
cd /path/to/salesforce-securedsoql-agent
pip install -e ".[dev]"
```

### 2. Configure Environment

Create or edit `.env`:

```bash
# Optional: LLM for enhanced reasoning
OPENAI_API_KEY=your_openai_key

# Salesforce MCP Backend
DEFAULT_MCP_URL=http://127.0.0.1:8000/mcp
DEFAULT_SESSION_TOKEN=your_salesforce_jwt_token

# Or use demo mode (no Salesforce required)
# Tools will use in-memory demo data
```

### 3. Test the Server

Run directly to verify:

```bash
python -m app.mcp_server
```

The server will start and wait for MCP client connections via stdio.

### 4. Connect MCP Client

Configure your MCP client to connect to the server via stdio transport. The server accepts connections on stdin/stdout and supports the standard MCP protocol.

**Environment variables** can be passed to configure:
- `DEFAULT_MCP_URL` - Salesforce MCP server URL
- `DEFAULT_SESSION_TOKEN` - Salesforce JWT token
- `OPENAI_API_KEY` - (Optional) For enhanced LLM reasoning

## MCP Features

### 🔧 Tools (4)

Tools are executable actions that modify state or retrieve data.

#### 1. `run_langgraph_agent`

Execute the agent with natural language prompts.

**Parameters:**
- `prompt` (required): User's natural language request
- `session_id` (required): Unique session identifier
- `context` (optional): Additional context as a dictionary
- `soql_query` (optional): Explicit SOQL query
- `sobject_name` (optional): Salesforce object name
- `account_plan_data` (optional): Account plan fields
- `approved` (optional): Approval flag (default: false)
- `use_demo_adapter` (optional): Use demo mode (default: true)
- `mcp_url` (optional): Override Salesforce MCP URL
- `session_token` (optional): Override Salesforce JWT token

**Returns:**
```json
{
  "status": "success|needs_input|needs_approval|error|uploaded",
  "intent": "describe|query|upload_account_plan",
  "message": "Human-readable response",
  "data": {
    "records": [...],
    "account_plan_data": {...},
    "filtered_fields": [...],
    "security_notes": [...]
  }
}
```

**Examples:**

```javascript
// Query Salesforce
run_langgraph_agent({
  prompt: "Show me all accounts in California",
  session_id: "my-query-session"
})

// Describe an object
run_langgraph_agent({
  prompt: "Describe the Account object",
  session_id: "describe-session",
  sobject_name: "Account"
})

// Start account plan draft
run_langgraph_agent({
  prompt: "Help me create a 2026 account plan for Nike",
  session_id: "nike-2026"
})

// Continue draft (reuse session_id)
run_langgraph_agent({
  prompt: "The annual spend is $5M",
  session_id: "nike-2026",
  account_plan_data: {
    "This_Year_Annual_Spend_Est__c": "5000000"
  }
})
```

#### 2. `approve_account_plan`

Approve and upload a drafted account plan.

**Parameters:**
- `session_id` (required): Session with existing draft
- `user_input` (optional): Additional approval context
- `account_plan_data` (optional): Final field values
- `use_demo_adapter` (optional): Use demo mode (default: true)
- `mcp_url` (optional): Override Salesforce MCP URL
- `session_token` (optional): Override Salesforce JWT token

**Returns:**
```json
{
  "status": "uploaded|error",
  "intent": "upload_account_plan",
  "message": "Upload confirmation",
  "data": {
    "upload_record_id": "a01...",
    "action": "upserted"
  }
}
```

**Example:**

```javascript
approve_account_plan({
  session_id: "nike-2026",
  user_input: "Approve for upload",
  account_plan_data: {
    "AccountPlan__c": "001000000000000AAA",
    "Plan_Year__c": "2026",
    "This_Year_Annual_Spend_Est__c": "5000000"
  }
})
```

#### 3. `get_agent_state`

Inspect the current state of a session.

**Parameters:**
- `session_id` (required): Session identifier

**Returns:**
```json
{
  "session_id": "nike-2026",
  "account_plan_data": {...},
  "last_state": {...},
  "session_config": {
    "use_demo_adapter": true,
    "mcp_url": "...",
    "has_session_token": true
  }
}
```

**Example:**

```javascript
get_agent_state({
  session_id: "nike-2026"
})
```

#### 4. `reset_agent`

Clear all state for a session.

**Parameters:**
- `session_id` (required): Session identifier

**Returns:**
```json
{
  "session_id": "nike-2026",
  "reset": true,
  "had_draft": true,
  "had_state": true,
  "had_config": true
}
```

**Example:**

```javascript
reset_agent({
  session_id: "nike-2026"
})
```

---

### 📦 Resources (2)

Resources provide read-only access to data without modifying state.

#### 1. `draft://sessions`

List all active draft sessions.

**Returns:**
```json
{
  "sessions": [
    {
      "session_id": "nike-2026",
      "has_draft": true,
      "draft_field_count": 8,
      "has_state": true,
      "last_intent": "upload_account_plan",
      "last_status": "needs_input"
    }
  ],
  "total_count": 1
}
```

**Usage Example:**
```
Read the draft://sessions resource
```

#### 2. `draft://sessions/{session_id}`

Get detailed state for a specific session.

**Returns:**
```json
{
  "session_id": "nike-2026",
  "account_plan_data": {
    "Plan_Year__c": "2026",
    "This_Year_Annual_Spend_Est__c": "5000000"
  },
  "last_state": {...},
  "session_config": {...}
}
```

**Usage Example:**
```
Read the draft://sessions/nike-2026 resource
```

---

### 💬 Prompts (2)

Prompts provide interactive guidance for complex workflows.

#### 1. `salesforce-query-guided`

Interactive guide for Salesforce queries.

**Arguments:**
- `object_type` (optional): Salesforce object to query
- `user_goal` (optional): What user wants to find

**Usage Example:**
```
Use the salesforce-query-guided prompt
```

Or with arguments:
```
Use the salesforce-query-guided prompt with object_type="Account" and user_goal="Find high-value accounts"
```

#### 2. `account-plan-guided`

Step-by-step account plan creation guide.

**Arguments:**
- `account_name` (optional): Company name
- `plan_year` (optional): Target fiscal year

**Usage Example:**
```
Use the account-plan-guided prompt
```

Or with arguments:
```
Use the account-plan-guided prompt with account_name="Nike" and plan_year="2026"
```

---

## Example Workflows

### Workflow 1: Query Salesforce Data

```
User: Use the salesforce-query-guided prompt

Assistant: [Displays interactive guide]

User: Show me all accounts in California with revenue over $1M

Assistant: [Calls run_langgraph_agent tool]

Result:
- Records: [list of matching accounts]
- Security notes: [any filtered fields]
- Status: success
```

### Workflow 2: Create Account Plan

```
User: Use the account-plan-guided prompt with account_name="Nike" and plan_year="2026"

Assistant: [Displays guided workflow]

User: I'll start the draft

Assistant: [Calls run_langgraph_agent with session_id="nike-2026"]

Result: Draft created, status=needs_input

User: The annual spend estimate is $5M across these quarters:
Q1: $1M, Q2: $1.5M, Q3: $1.5M, Q4: $1M

Assistant: [Calls run_langgraph_agent with same session_id and account_plan_data]

Result: Draft updated, status=needs_input

User: [Continues adding information over multiple turns]

Assistant: [Keeps updating draft using same session_id]

Result: Draft at 90% readiness, status=ready_for_approval

User: Approve and upload this plan

Assistant: [Calls approve_account_plan tool]

Result: Account plan uploaded, record_id=a01...
```

### Workflow 3: Inspect Draft State

```
User: What draft sessions are active?

Assistant: [Reads draft://sessions resource]

Result: Shows nike-2026 with 90% readiness

User: Show me the full draft for nike-2026

Assistant: [Reads draft://sessions/nike-2026 resource]

Result: Full draft details with all fields
```

### Workflow 4: Multi-Turn with State

```
User: Start a plan for Acme for 2026
Assistant: [run_langgraph_agent session_id="acme-2026"]
→ Draft created with Plan_Year__c=2026

User: Add annual spend of $2M
Assistant: [run_langgraph_agent session_id="acme-2026"]
→ Draft updated, now has spend + year

User: What's in the acme-2026 draft?
Assistant: [get_agent_state session_id="acme-2026"]
→ Shows: Plan_Year__c=2026, Annual_Spend=$2M

User: Actually, let's start over
Assistant: [reset_agent session_id="acme-2026"]
→ Session cleared

User: Check the draft again
Assistant: [get_agent_state session_id="acme-2026"]
→ Shows: No draft data
```

---

## Session Management

### Session Persistence

Sessions persist **in-memory** for the lifetime of the MCP server process. Each session tracks:

- **Draft data**: Accumulated account plan fields
- **Last execution state**: Full graph output from last run
- **Session config**: MCP URL, session token, demo mode

### Session Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│ 1. First Call                                            │
│    run_langgraph_agent(session_id="new")                │
│    → Creates session with empty draft                    │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│ 2. Subsequent Calls                                      │
│    run_langgraph_agent(session_id="new")                │
│    → Merges new data into existing draft                 │
│    → Reuses session config (MCP URL, token)             │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│ 3. Inspection (Non-Destructive)                         │
│    get_agent_state(session_id="new")                    │
│    OR read resource draft://sessions/new                │
│    → Returns state without modifying                     │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│ 4. Approval & Upload                                     │
│    approve_account_plan(session_id="new")               │
│    → Uploads to Salesforce                              │
│    → Clears draft if successful                         │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│ 5. Manual Reset (Optional)                               │
│    reset_agent(session_id="new")                        │
│    → Clears all session data                            │
└──────────────────────────────────────────────────────────┘
```

### Config Inheritance

Once you provide `mcp_url` and `session_token` to a session, they're remembered:

```javascript
// First call - establish live connection
run_langgraph_agent({
  prompt: "Start plan",
  session_id: "nike-live",
  use_demo_adapter: false,
  mcp_url: "http://127.0.0.1:8000/mcp",
  session_token: "jwt-token-here"
})

// Subsequent calls - config inherited
run_langgraph_agent({
  prompt: "Continue plan",
  session_id: "nike-live"
  // No need to repeat mcp_url or session_token
})

approve_account_plan({
  session_id: "nike-live"
  // Still uses the same live connection
})
```

---

## Demo Mode vs Live Mode

### Demo Mode (Default)

```javascript
run_langgraph_agent({
  prompt: "Show me accounts",
  session_id: "demo-session",
  use_demo_adapter: true  // or omit (default)
})
```

**Characteristics:**
- ✅ No Salesforce connection required
- ✅ Uses in-memory demo data
- ✅ Perfect for testing and development
- ❌ Data is fake (Nike, Acme accounts)
- ❌ Writes don't persist

### Live Mode

```javascript
run_langgraph_agent({
  prompt: "Show me accounts",
  session_id: "live-session",
  use_demo_adapter: false,
  mcp_url: "http://127.0.0.1:8000/mcp",
  session_token: "your-jwt-token"
})
```

**Characteristics:**
- ✅ Real Salesforce data
- ✅ Writes persist to Salesforce
- ✅ Security policies enforced
- ❌ Requires running Salesforce MCP server
- ❌ Requires valid authentication

**Note**: Use `DEFAULT_MCP_URL` and `DEFAULT_SESSION_TOKEN` environment variables to avoid passing credentials in every call.

---

## Security Features

### Automatic Security Handling

The agent automatically handles Salesforce security policies:

#### 1. Field-Level Security (FLS)

**Silent Filtering**: Restricted fields in `SELECT` are removed from results.

```javascript
// You request: SELECT Name, SSN__c FROM Account
// Security filters out SSN__c
// You receive: Name only + security note
```

**Inference Protection**: Restricted fields in `WHERE`/`ORDER BY` block the query.

```javascript
// You request: WHERE SSN__c = '123-45-6789'
// Security detects inference attack
// Agent removes SSN__c and retries: WHERE Name = '...'
```

#### 2. Row-Level Security

Users see only records they have access to.

```javascript
// You request: SELECT Name FROM Account LIMIT 100
// Security filters rows
// You receive: 47 accessible accounts + note about RLS
```

#### 3. Security Transparency

All security actions are reported in `security_notes`:

```json
{
  "status": "success",
  "records": [...],
  "security_notes": [
    "Field 'SSN__c' was filtered by security policy",
    "Removed restricted field 'CreditScore__c' from WHERE clause"
  ],
  "filtered_fields": ["SSN__c", "CreditScore__c"]
}
```

### Never Hallucinated

The agent **never** invents data for filtered fields:

❌ **Wrong**: Filling in fake SSN values  
✅ **Right**: Reporting field was filtered

---

## Troubleshooting

### Server Won't Start

**Symptom**: Error when running `python -m app.mcp_server`

**Solutions**:
1. Check dependencies installed: `pip install -e .`
2. Verify Python 3.11+: `python --version`
3. Check for import errors in output

### MCP Client Not Connecting

**Symptom**: MCP client cannot connect to server

**Solutions**:
1. Verify server is running: `python -m app.mcp_server`
2. Check that client is configured for stdio transport
3. Verify environment variables are set correctly
4. Check server logs (stderr output)

### Connection to Salesforce Fails

**Symptom**: Errors about MCP connection or authentication

**Solutions**:
1. Verify Salesforce MCP server is running: `curl http://127.0.0.1:8000/mcp`
2. Check `DEFAULT_SESSION_TOKEN` is valid (not expired)
3. Use demo mode for testing: `use_demo_adapter: true`
4. Check firewall/network settings

### Session State Lost

**Symptom**: Draft data disappears between calls

**Solutions**:
1. **Use same `session_id`** for all related calls
2. Check MCP server didn't restart (in-memory only)
3. Use `get_agent_state` to verify session exists
4. Check if draft was cleared after successful upload

### Drafts Not Merging

**Symptom**: New fields overwrite old ones

**Solutions**:
1. Verify using same `session_id`
2. Check `account_plan_data` is being passed correctly
3. Use `draft://sessions/{id}` resource to inspect state
4. Ensure not calling `reset_agent` accidentally

---

## Best Practices

### ✅ DO

1. **Reuse session IDs** for multi-turn workflows
2. **Use resources** to inspect state before modifying
3. **Use prompts** for complex workflows (guided experience)
4. **Set demo mode once** per session (config inheritance)
5. **Check `status` field** before proceeding (needs_approval, etc.)
6. **Read security_notes** to understand what was filtered
7. **Use meaningful session IDs** (e.g., "nike-2026-plan")

### ❌ DON'T

1. **Don't** create new session IDs for each call (breaks persistence)
2. **Don't** ignore `status=needs_approval` (writes won't happen)
3. **Don't** assume all requested fields are in results (check filtered_fields)
4. **Don't** retry exact same query on inference attack (agent auto-fixes)
5. **Don't** put sensitive data in session IDs (they're logged)
6. **Don't** rely on sessions across server restarts (in-memory only)

---

## Advanced Topics

### Custom Tool Composition

Combine MCP tools with other MCP servers:

```javascript
// Use filesystem MCP to read data
const data = await read_file("accounts.csv")

// Use Salesforce agent to upload
await run_langgraph_agent({
  prompt: `Upload these accounts: ${data}`,
  session_id: "batch-upload"
})
```

### Parallel Sessions

Each session is independent and thread-safe:

```javascript
// Session 1: Nike plan
run_langgraph_agent({ session_id: "nike-2026", ... })

// Session 2: Acme plan (parallel, no conflict)
run_langgraph_agent({ session_id: "acme-2026", ... })
```

### Programmatic API (Alternative to MCP)

This same agent can run as a FastAPI server:

```bash
python -m uvicorn app.api.routes:app --host 127.0.0.1 --port 8081
```

Then call via HTTP:
```bash
curl -X POST http://127.0.0.1:8081/run \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Show me accounts", "session_id": "api-session"}'
```

---

## Comparison: MCP vs FastAPI

| Aspect | MCP Mode | FastAPI Mode |
|--------|----------|--------------|
| **Transport** | stdio | HTTP REST |
| **Client** | AI assistants | Any HTTP client |
| **Auth** | Process-level | Bearer token |
| **Discovery** | Automatic (tools/resources/prompts) | Manual (docs) |
| **State** | In-memory (per process) | In-memory (per process) |
| **Use Case** | AI-assisted workflows | Programmatic integration |

**Choose MCP when**: Building AI-assisted experiences with MCP-compatible clients  
**Choose FastAPI when**: Building traditional APIs, webhooks, integrations

---

## Additional Resources

- [MCP Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Project README](README.md) - Main documentation
- [DESIGN.md](DESIGN.md) - Technical architecture
- [BUSINESS_USER_GUIDE.md](BUSINESS_USER_GUIDE.md) - Business user workflows

---

## Support

For issues or questions:
1. Check this guide first
2. Check server logs (stderr output)
3. Review [DESIGN.md](DESIGN.md) for architecture details
4. Open an issue in the project repository
