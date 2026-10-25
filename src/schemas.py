"""Schemas da API (stub de contrato — implementado por add-chat-agent)."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "partial", "not_found", "unsupported", "error"]


class HealthResponse(BaseModel):
    """Resposta do probe de liveness."""

    status: Literal["ok"] = Field(description="Sempre `ok` quando o processo está no ar.")


class ErrorResponse(BaseModel):
    """Erro HTTP simples (formato padrão do ``HTTPException`` do FastAPI)."""

    detail: str = Field(description="Mensagem legível descrevendo o erro.")


class NotFoundError(BaseModel):
    """404: o recurso pedido (tool ou Pokémon) não existe ou está desabilitado."""

    status: Literal["not_found"] = "not_found"
    detail: str = Field(description="Qual recurso não foi encontrado.", examples=["Tool 'nope' não encontrada ou desabilitada."])
    request_id: str | None = Field(default=None, description="Presente no `/chat`; correlaciona com os logs.")


class InternalServerError(BaseModel):
    """500: falha no servidor ou PokéAPI indisponível; detalhes ficam só nos logs."""

    status: Literal["error"] = "error"
    detail: str = Field(description="Mensagem legível, sem stack trace.", examples=["Erro interno inesperado."])
    request_id: str | None = Field(default=None, description="Presente no `/chat`; correlaciona com os logs.")


class ChatRequest(BaseModel):
    """Mensagem em linguagem natural enviada ao agente."""

    message: str = Field(description="Pergunta do usuário sobre Pokémon.", examples=["Qual o tipo do Pikachu?"])


class Source(BaseModel):
    """Proveniência de um dado usado na resposta."""

    tool: str = Field(description="Tool que coletou o dado.")
    url: str | None = Field(description="URL do recurso na PokéAPI.")
    collected_at: str | None = Field(description="Data/hora da coleta original (ISO-8601).")
    cached: bool = Field(description="`true` se o dado veio do cache local, `false` se da rede.")


class ChatResponse(BaseModel):
    """Envelope de resposta do ``/chat`` (200 e 422 de pergunta fora do escopo)."""

    request_id: str = Field(description="Identificador único da requisição (correlaciona logs).")
    status: Status = Field(description="Resultado do fluxo: ok/partial → 200, not_found → 404, unsupported → 422, error → 500.")
    answer: str = Field(description="Resposta em linguagem natural.")
    sources: list[Source] = Field(description="Fontes consultadas, com proveniência.")
    tools_used: list[str] = Field(description="Tools executadas, em ordem.")
    warnings: list[str] = Field(description="Avisos não fatais (ex.: dados parciais).")

