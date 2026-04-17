from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    status: str
    intent: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
