"""Aplicação FastAPI do PokéGarden.

Camada puramente HTTP: valida a entrada, chama ``agent.run_chat`` e mapeia o
``status`` do resultado para o código HTTP. Este módulo NÃO importa o OpenAI SDK
nem o cliente da PokéAPI — toda a orquestração vive em ``pokegarden.agent``.

As rotas ``GET /tools`` e ``GET /tools/{name}`` são determinísticas: leem o
catálogo diretamente, sem LLM e sem consumir tokens. Como o catálogo só muda
em deploy/troca de perfil, elas enviam ``Cache-Control: max-age``.
"""

import logging

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

import agent, catalog
from models import ToolManifest
from obs import log_event
from schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    InternalServerError,
    NotFoundError,
)
from config import settings

app = FastAPI(title="PokéGarden")

# Documentação OpenAPI dos erros comuns, reutilizada em ``responses=`` das rotas.
_NOT_FOUND = {404: {"model": NotFoundError, "description": "Recurso não encontrado (tool ou Pokémon)."}}
_INTERNAL_ERROR = {500: {"model": InternalServerError, "description": "Falha no servidor ou PokéAPI indisponível."}}


def _error_response(status_code: int, error: NotFoundError | InternalServerError) -> JSONResponse:
    """Serializa um erro documentado (omite ``request_id`` quando ausente)."""
    return JSONResponse(status_code=status_code, content=error.model_dump(exclude_none=True))


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Qualquer exceção não tratada vira um 500 JSON documentado (sem stack trace)."""
    log_event("http.unhandled_error", level=logging.ERROR, path=request.url.path, error=type(exc).__name__)
    return _error_response(500, InternalServerError(detail="Erro interno inesperado."))


# Mapeamento centralizado status -> código HTTP.
# ok/partial -> 200; not_found -> 404; unsupported -> 422; error -> 5xx.
# Validação e indisponibilidade nunca retornam 200 com aparência de sucesso.
_STATUS_HTTP = {
    "ok": 200,
    "partial": 200,
    "not_found": 404,
    "unsupported": 422,
    "error": 500,
}


@app.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    """Endpoint de liveness: indica que o serviço está no ar.

    Não depende de serviços externos, servindo como sinal barato para
    probes de deploy, orquestradores e load balancers.
    """
    return {"status": "ok"}


def _set_tools_cache_headers(response: Response) -> None:
    """Permite cache do catálogo pelo cliente/proxies (só respostas de sucesso)."""
    response.headers["Cache-Control"] = f"public, max-age={settings.tools_cache_max_age_seconds}"


@app.get("/tools", response_model=list[ToolManifest], responses=_INTERNAL_ERROR)
def list_tools(response: Response, query: str | None = Query(default=None)) -> list[dict]:
    """Lista ou pesquisa tools habilitadas (determinístico, sem LLM, sem tokens)."""
    _set_tools_cache_headers(response)
    if query:
        return catalog.search_tools(query)
    return catalog.list_enabled()


@app.get(
    "/tools/{name}",
    response_model=ToolManifest,
    responses={**_NOT_FOUND, **_INTERNAL_ERROR},
)
def tool_schema(name: str, response: Response) -> dict | JSONResponse:
    """Retorna o contrato de uma tool habilitada (determinístico, sem LLM).

    Tool inexistente ou desabilitada resulta em HTTP 404 documentado, sem
    ``Cache-Control`` (o header só vale para a resposta de sucesso).
    """
    try:
        schema = catalog.get_tool_schema(name)
    except (catalog.ToolNotFound, catalog.ToolDisabled):
        return _error_response(404, NotFoundError(detail=f"Tool '{name}' não encontrada ou desabilitada."))
    _set_tools_cache_headers(response)
    return schema


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        **_NOT_FOUND,
        422: {
            "model": ChatResponse | ErrorResponse,
            "description": "Pergunta fora do escopo (`status: unsupported`, envelope do chat) "
            "ou `message` acima do tamanho máximo (`detail`). Corpo malformado segue o "
            "erro de validação padrão do FastAPI.",
        },
        **_INTERNAL_ERROR,
    },
)
def chat(request: ChatRequest) -> JSONResponse:
    """Executa o fluxo do agente para a mensagem e mapeia o status para HTTP."""
    if len(request.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=f"message excede o tamanho máximo de {settings.max_message_chars} caracteres.",
        )

    result = agent.run_chat(request.message)
    http_status = _STATUS_HTTP.get(result.status, 500)
    if http_status == 404:
        return _error_response(404, NotFoundError(detail=result.answer, request_id=result.request_id))
    if http_status >= 500:
        return _error_response(http_status, InternalServerError(detail=result.answer, request_id=result.request_id))

    body = ChatResponse(
        request_id=result.request_id,
        status=result.status,
        answer=result.answer,
        sources=result.sources,
        tools_used=result.tools_used,
        warnings=result.warnings,
    )
    return JSONResponse(status_code=http_status, content=body.model_dump())
