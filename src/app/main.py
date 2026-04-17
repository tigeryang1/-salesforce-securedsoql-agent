from __future__ import annotations

import argparse
import asyncio
import json

from app.agent_service import AgentSessionService
from app.config import get_settings
from app.services.mcp_transport import build_streamable_http_adapter


async def _run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, dest="user_input")
    parser.add_argument("--session-id", default="cli")
    parser.add_argument("--soql")
    parser.add_argument("--object")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--account-plan-json")
    parser.add_argument("--mcp-url")
    parser.add_argument("--session-token")
    parser.add_argument("--use-demo-adapter", action="store_true")
    parser.add_argument("--smoke-live-mcp", action="store_true")
    args = parser.parse_args()

    payload = None
    if args.account_plan_json:
        payload = json.loads(args.account_plan_json)

    if args.smoke_live_mcp:
        if not args.mcp_url:
            raise ValueError("--smoke-live-mcp requires --mcp-url")
        adapter = await build_streamable_http_adapter(
            mcp_url=args.mcp_url,
            session_token=args.session_token or "change-me",
        )
        description = await adapter.describe_salesforce_object("Account")
        print(json.dumps({"status": "ok", "object": description.name, "field_count": len(description.fields)}, indent=2))
        return

    settings = get_settings()
    service = AgentSessionService(settings)
    if args.approved:
        result = await service.approve(
            user_input=args.user_input,
            session_id=args.session_id,
            account_plan_data=payload,
            use_demo_adapter=args.use_demo_adapter or not args.mcp_url,
            mcp_url=args.mcp_url,
            session_token=args.session_token,
        )
    else:
        result = await service.run(
            user_input=args.user_input,
            session_id=args.session_id,
            soql_query=args.soql,
            sobject_name=args.object,
            account_plan_data=payload,
            approved=False,
            use_demo_adapter=args.use_demo_adapter or not args.mcp_url,
            mcp_url=args.mcp_url,
            session_token=args.session_token,
        )
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
