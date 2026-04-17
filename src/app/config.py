from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    agent_model: str = os.getenv("AGENT_MODEL", "openai:gpt-4o-mini")
    agent_api_token: str = os.getenv("AGENT_API_TOKEN", "change-me")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8081"))
    default_mcp_url: str = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
    default_session_token: str = os.getenv("SESSION_TOKEN", "change-me")


def get_settings() -> Settings:
    return Settings()
