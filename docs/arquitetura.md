# Arquitetura — decisões e evolução

Este documento registra as decisões de arquitetura do PokéGarden e a evolução
pretendida em direção ao "Garden" (múltiplas tools/domínios).

## Princípios

- **Clean Architecture**: regras de negócio isoladas de I/O, testáveis sem rede.
- **TDD**: a suíte em `tests/` roda offline via fixtures e monkeypatch.
- **Type hints + Pydantic**: contratos explícitos nas fronteiras (DTOs e settings).

## Camadas (layout atual `src/`)

| Módulo        | Papel                                                                 |
| ------------- | --------------------------------------------------------------------- |
| `models.py`   | Domínio puro — entidades/value objects (`Pokemon`, `Provenance`).     |
| `tools.py`    | Tools de domínio (ex.: `get_pokemon`), sem acoplamento ao transporte. |
| `catalog.py`  | Catálogo: descoberta dinâmica e gating das tools.                     |
| `agent.py`    | Orquestração com OpenAI Agents SDK (`Agent` + `Runner`), com budgets. |
| `pokeapi.py`  | Gateway da PokéAPI: único host alcançável, cache e proveniência.      |
| `schemas.py`  | DTOs da API (`ChatRequest`/`ChatResponse`).                           |
| `config.py`   | Settings via `.env` (pydantic-settings).                              |
| `main.py`     | Adapter HTTP (FastAPI): `/chat`, `/tools`, `/tools/{name}`, `/health`.|

## Decisões-chave

1. **Descoberta dinâmica de tools** — o modelo vê apenas `search_tools`,
   `get_tool_schema` e `run_tool`; schemas de domínio só são revelados sob
   demanda. Mantém o prompt enxuto e permite crescer o catálogo sem reescrevê-lo.
2. **Gating em código, não no prompt** — tool inexistente, desabilitada ou não
   liberada é bloqueada dentro de `run_tool`. Segurança não depende de instruções.
3. **Proveniência derivada do runtime** — `status`, `sources` e `tools_used` vêm
   dos eventos do run, não do texto do modelo.
4. **Fronteiras de segurança** — só a PokéAPI é alcançável; sem `eval`/shell/fs/env
   nas tools; budgets por requisição (turnos, chamadas de tool, HTTP, deadline).
5. **Status honesto** — falhas mapeiam para 404/422/5xx; nunca `200` de falso
   sucesso.

## Catálogo e descoberta de tools (requisito 3.3)

**Peças** (`catalog.py`):

- `ToolManifest` (`models.py`): `name`, `version`, `description`, `tags`,
  `input_schema`, `output_schema` (sucesso **ou** erro, via `oneOf`) e `enabled`.
- `ToolCatalog`: manifestos em memória, por nome. `register` (recusa nome
  repetido), `search_tools` (substring em nome/descrição/tags, só habilitadas,
  ordenada por nome; consulta vazia = todas), `get_tool_schema`, `set_enabled`.
- `HANDLERS`: a única lista de código executável. O catálogo não guarda funções.
- Perfis `A`/`B` (`POKEGARDEN_TOOLS_PROFILE`, padrão `B`) definem o `enabled`
  de cada tool: `B` = todas, `A` = sem `get_evolution_chain`.
  `get_catalog()` cria um catálogo por perfil, uma vez por processo.

**Fluxo em uma requisição** (`agent.py`):

1. O modelo começa só com `search_tools`, `get_tool_schema` e `run_tool`.
2. `search_tools` / `get_tool_schema` devolvem o contrato e marcam a tool como
   **descoberta** em `RequestContext.discovered`.
3. `run_tool` → `catalog.execute_tool`, que barra em código, nesta ordem:
   existe → habilitada → descoberta nesta requisição → tem handler → args válidos
   pelo `input_schema` (`jsonschema`). Só então chama a função real.
4. Erros voltam ao modelo como `{"error": <código>, "detail"?}`, com os códigos
   listados em `catalog.ERROR_CODES` (ex.: `not_found` para 404 da PokéAPI).

**Estado da descoberta:** vive só no `RequestContext`, criado a cada `run_chat`.
O catálogo é compartilhado, mas não guarda nada da requisição. Uma requisição
não enxerga o que outra descobriu.

**Limites** (`config.py`, valem para a requisição inteira):

| Limite               | Padrão | Onde é checado                          | Ao esgotar                                  |
| -------------------- | ------ | --------------------------------------- | ------------------------------------------- |
| `max_turns`          | 6      | `Runner.run_sync`                       | Runner falha → resposta `error`/`partial`   |
| `request_deadline_s` | 20 s   | antes de cada `run_tool`                | `deadline_exceeded` → resposta `partial`    |
| `max_tool_calls`     | 8      | antes de cada `run_tool`                | `tool_call_budget_exceeded` → `partial`     |
| `max_http_requests`  | 12     | antes de cada GET na PokéAPI (com retries; cache hit não conta) | `http_budget_exceeded` → `partial` |
| `max_tool_output_bytes` | 8192 | saída de tool para o modelo            | truncada com aviso `…[saída truncada]`      |
| `max_message_chars`  | 2000   | `POST /chat`                            | HTTP 422                                    |

**Adicionar uma tool:** um `ToolManifest` em `MANIFESTS`, a função em `HANDLERS`
e o nome no(s) perfil(is) em `PROFILES`.

## Evolução para o Garden

- Adicionar novas tools de domínio registrando-as no `catalog.py`, sem alterar o
  contrato das três tools genéricas.
- Permitir múltiplos gateways mantendo a regra de host allowlist por tool.
- Expandir `evals/` com casos por domínio para medir regressões ao crescer o
  catálogo.
