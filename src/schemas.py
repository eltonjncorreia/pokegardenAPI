"""Schemas da API (stub de contrato — implementado por add-chat-agent)."""

from typing import Literal

from pydantic import BaseModel

Status = Literal["ok", "partial", "not_found", "unsupported", "error"]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    request_id: str
    status: Status
    answer: str
    sources: list[dict]
    tools_used: list[str]
    warnings: list[str]
