# Solução — PokéGarden

Assistente conversacional de Pokémon orquestrado pelo **OpenAI Agents SDK** sobre
a **PokéAPI**, seguindo Clean Architecture e TDD. Este documento cobre
instalação, execução, exemplos e limitações conhecidas.

## Instalação

Pré-requisitos: **Python 3.12** e, opcionalmente, `make`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # ou: pip install -r requirements.txt
cp .env.example .env         # preencha OPENAI_API_KEY
```

As variáveis de ambiente estão documentadas em [`.env.example`](.env.example).
Apenas `OPENAI_API_KEY` é obrigatória para o fluxo conversacional completo; os
testes e as avaliações offline rodam sem chave.

## Execução

```bash
make run                           # http://localhost:8000
# ou manualmente:
uvicorn --app-dir src main:app --reload
```

Verificação rápida:

```bash
curl http://localhost:8000/health         # {"status":"ok"}
```

Documentação interativa: <http://localhost:8000/docs>.

## Exemplos

```bash
# Pergunta em linguagem natural
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "fale sobre o Pikachu"}'

# Catálogo determinístico de tools habilitadas
curl http://localhost:8000/tools
curl http://localhost:8000/tools/get_pokemon
```

A resposta de `/chat` traz `request_id`, `status` (`ok` | `partial` |
`unsupported`), `answer`, `sources`, `tools_used` e `warnings`. Os erros `404`
(`status: not_found`) e `500` (`status: error`) usam os schemas `NotFoundError`
e `InternalServerError` (`status`, `detail`, `request_id`), os mesmos de
`/tools/{name}`. Falhas nunca retornam `200` de falso sucesso.

## Logs e cache

Eventos JSON (uma linha cada) em stderr e, com `LOG_FILE`, também em arquivo
(ex.: `logs/pokegarden.jsonl`). Todos trazem `ts`, `event` e `request_id`.

| Evento | Quando | Campos principais |
| --- | --- | --- |
| `chat.start` / `chat.end` | início/fim de `/chat` | `model`, `status`, `duration_ms`, `tool_calls`, `cache_hits`/`cache_misses`, `llm_requests`, `input_tokens`/`output_tokens`/`total_tokens` (`null` se o SDK não informar, nunca 0) |
| `chat.failure` | exceção no Runner | `error`, `detail` |
| `discovery.search` / `discovery.schema` | descoberta | `query`, `results` / `tool`, `version`, `result` |
| `tool.call` | cada `run_tool` | `tool`, `version`, `args`, `result`, `error_code`, `duration_ms`, `cache_hits`, `cache_misses`, `http_requests` |
| `cache.hit` / `cache.miss` | leitura do cache | `key`, `age_s`; `reason` = `absent` \| `expired` \| `corrupt` |
| `cache.write` | após GET bem-sucedido | `key`, `url`, `collected_at` |
| `http.request` / `http.retry` / `http.unavailable` | cada GET real | `url`, `attempt`, `status`, `duration_ms` / `wait_s` / `attempts` |

Como conferir o cache: `grep '"cache\.' logs/pokegarden.jsonl`. Um hit não gera
`http.request` e mantém o `collected_at` original. Depois de um GET, o recurso é
gravado sob o nome **e** o id (`pokemon/pikachu` e `pokemon/25`), com a mesma
origem e data de coleta. Assim, consultar por ID reaproveita a consulta por nome.

## Testes e avaliação

```bash
make test        # suíte offline (pytest, sem rede)
make eval        # casos E01–E12 offline: pytest + Runner real com modelo roteirizado
make eval-live   # casos marcados como live, com o modelo e a PokéAPI reais
```

Os casos, os modos de execução e as limitações estão em [`evals/`](evals/). O
relatório por caso (`pass`/`fail`/`not_run`, modo, motivo, duração e evidências)
fica em [`evidence/evals/`](evidence/evals/).

## Limitações conhecidas

- **Único host**: apenas a PokéAPI é alcançável; hosts e redirects fora da
  origem são rejeitados por padrão.
- **Escopo de domínio**: a tool de domínio disponível é `get_pokemon`; outras
  consultas podem retornar `unsupported`.
- **Dependência de rede/chave**: o fluxo `/chat` requer `OPENAI_API_KEY` e
  acesso de saída à PokéAPI; testes e evals são offline por fixtures.
- **Cache local**: respostas da PokéAPI são cacheadas por `CACHE_TTL_SECONDS`;
  dados podem ficar defasados dentro desse intervalo.
