"""Aplicação FastAPI do PokéGarden.

Camada puramente HTTP: valida a entrada, chama ``agent.run_chat`` e mapeia o
``status`` do resultado para o código HTTP. Este módulo NÃO importa o OpenAI SDK
nem o cliente da PokéAPI — toda a orquestração vive em ``pokegarden.agent``.

As rotas ``GET /tools`` e ``GET /tools/{name}`` são determinísticas: leem o
catálogo diretamente, sem LLM e sem consumir tokens.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

import agent, catalog
from schemas import ChatRequest, ChatResponse
from config import settings

app = FastAPI(title="PokéGarden")

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


@app.get("/health")
def health() -> dict[str, str]:
    """Endpoint de liveness: indica que o serviço está no ar.

    Não depende de serviços externos, servindo como sinal barato para
    probes de deploy, orquestradores e load balancers.
    """
    return {"status": "ok"}


@app.get("/tools")
def list_tools(query: str | None = Query(default=None)) -> list[dict]:
    """Lista ou pesquisa tools habilitadas (determinístico, sem LLM, sem tokens)."""
    if query:
        return catalog.search_tools(query)
    return catalog.list_enabled()


@app.get("/tools/{name}")
def tool_schema(name: str) -> dict:
    """Retorna o contrato de uma tool habilitada (determinístico, sem LLM).

    Tool inexistente ou desabilitada resulta em HTTP 404 documentado.
    """
    try:
        return catalog.get_tool_schema(name)
    except (catalog.ToolNotFound, catalog.ToolDisabled):
        raise HTTPException(status_code=404, detail=f"Tool '{name}' não encontrada ou desabilitada.")


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={404: {}, 422: {}, 500: {}},
)
def chat(request: ChatRequest) -> JSONResponse:
    """Executa o fluxo do agente para a mensagem e mapeia o status para HTTP."""
    if len(request.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=f"message excede o tamanho máximo de {settings.max_message_chars} caracteres.",
        )

    result = agent.run_chat(request.message)
    body = ChatResponse(
        request_id=result.request_id,
        status=result.status,
        answer=result.answer,
        sources=result.sources,
        tools_used=result.tools_used,
        warnings=result.warnings,
    )
    http_status = _STATUS_HTTP.get(result.status, 500)
    return JSONResponse(status_code=http_status, content=body.model_dump())
