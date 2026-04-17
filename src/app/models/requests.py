from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    user_input: str = Field(..., description="Natural-language request for the agent")
    session_id: str = Field(default="default", description="Conversation or draft session identifier")
    soql_query: str | None = Field(default=None, description="Explicit SOQL to execute")
    sobject_name: str | None = Field(default=None, description="Explicit Salesforce object to describe")
    account_plan_data: dict[str, Any] | None = Field(
        default=None,
        description="Explicit Account_Plan__c payload for upload",
    )
    mcp_url: str | None = Field(default=None, description="Streamable HTTP endpoint for the Salesforce MCP server")
    session_token: str | None = Field(default=None, description="Bearer token forwarded to the MCP server")
    use_demo_adapter: bool = Field(default=True, description="Use the local demo adapter instead of the real MCP server")
    approved: bool = Field(default=False, description="Whether the caller approved a pending write")


class ApprovalRequest(BaseModel):
    user_input: str
    session_id: str = "default"
    account_plan_data: dict[str, Any] | None = None
    mcp_url: str | None = None
    session_token: str | None = None
    use_demo_adapter: bool = True
    approved: bool = True
