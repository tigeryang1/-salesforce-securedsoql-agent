from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.services.salesforce_tools import CallableSalesforceToolAdapter

logger = logging.getLogger(__name__)


async def build_streamable_http_adapter(
    *,
    mcp_url: str,
    session_token: str,
    client_factory: Callable[..., Awaitable[Any]] | None = None,
) -> CallableSalesforceToolAdapter:
    if client_factory is None:
        client_factory = _default_client_factory

    client = await client_factory(mcp_url=mcp_url, session_token=session_token)
    tools = await client.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    required = {
        "describe_salesforce_object",
        "query_salesforce",
        "upload_account_plan",
    }
    missing = sorted(required - set(tools_by_name))
    if missing:
        raise ValueError(f"MCP server is missing required tools: {', '.join(missing)}")
    logger.info("connected to MCP server at %s with %d tools", mcp_url, len(tools))

    async def describe_fn(sobject_name: str) -> dict[str, Any]:
        return await tools_by_name["describe_salesforce_object"].ainvoke({"sobject_name": sobject_name})

    async def query_fn(soql_query: str) -> dict[str, Any]:
        return await tools_by_name["query_salesforce"].ainvoke({"soql_query": soql_query})

    async def upload_fn(account_plan_data: dict[str, Any]) -> dict[str, Any]:
        return await tools_by_name["upload_account_plan"].ainvoke({"account_plan_data": account_plan_data})

    return CallableSalesforceToolAdapter(
        describe_fn=describe_fn,
        query_fn=query_fn,
        upload_fn=upload_fn,
    )


async def _default_client_factory(*, mcp_url: str, session_token: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient(
        {
            "salesforce": {
                "transport": "streamable_http",
                "url": mcp_url,
                "headers": {"Authorization": f"Bearer {session_token}"},
            }
        }
    )
