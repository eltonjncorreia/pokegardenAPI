# 🌱 PokéGarden

Assistente Pokémon construído com **OpenAI Agents SDK** + **PokéAPI**, seguindo
**Clean Architecture**, **TDD** e type hints.

> **Status:** agente conversacional de ponta a ponta no ar — `POST /chat` com
> descoberta dinâmica de tools, gating em código e a tool de domínio
> `get_pokemon` orquestrada pelo OpenAI Agents SDK.

---

## ✅ Pré-requisitos

- **Python 3.12** (fixado via [pyenv](https://github.com/pyenv/pyenv) em `.python-version`)
- `make` (opcional, mas recomendado)

---

## 🚀 Configuração

```bash
# 1. Garantir o Python 3.12 (pyenv lê o .python-version automaticamente)
pyenv install -s 3.12
pyenv local 3.12.10

# 2. Criar e ativar o ambiente virtual
python -m venv .venv
source .venv/bin/activate

# 3. Instalar as dependências
pip install -r requirements.txt

# 4. Configurar as variáveis de ambiente
cp .env.example .env
# edite o .env e preencha OPENAI_API_KEY
```

### Variáveis de ambiente (`.env`)

| Variável           | Descrição                               | Padrão                        |
| ------------------ | --------------------------------------- | ----------------------------- |
| `OPENAI_API_KEY`     | Chave da API da OpenAI (usada pelo agente)   | *(vazio)*                   |
| `OPENAI_MODEL`       | Modelo usado pelo agente                     | `gpt-4o-mini`               |
| `POKEAPI_BASE_URL`   | URL base da PokéAPI                          | `https://pokeapi.co/api/v2` |
| `CACHE_DIR`          | Diretório de cache local                     | `.cache`                    |
| `CACHE_TTL_SECONDS`  | Expiração (s) das entradas de cache          | `86400`                     |
| `LOG_LEVEL`          | Nível de log (`DEBUG`/`INFO`/`WARNING`)      | `INFO`                      |
| `POKEGARDEN_TOOLS_PROFILE` | Perfil de tools: `B` = todas; `A` = sem `get_evolution_chain` | `B`        |

---

## ▶️ Como executar

Com o `Makefile` (limpa caches `__pycache__`/pytest antes de rodar):

```bash
make run     # sobe o servidor FastAPI (http://localhost:8000)
make test    # roda a suíte de testes
make clean   # remove caches do Python e de testes
```

Ou manualmente:

```bash
uvicorn --app-dir src main:app --reload
pytest
```

Verificando que está no ar:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Documentação interativa da API: <http://localhost:8000/docs>

---

## 🧠 Como o agente funciona

O PokéGarden é um **assistente conversacional de Pokémon** orquestrado de verdade
pelo **OpenAI Agents SDK** (`Agent` + `Runner`). O diferencial não é "chamar
tools", e sim **como** elas são descobertas e liberadas:

- **Descoberta dinâmica** — o modelo começa vendo apenas três tools genéricas:
  `search_tools(query)`, `get_tool_schema(name)` e `run_tool(name, args)`. Os
  `input_schema`/`output_schema` das tools de domínio **não** ficam no prompt nem
  na lista inicial; só são revelados quando o modelo pede com `get_tool_schema`.
- **Gating em código** — tool inexistente, desabilitada ou não liberada na
  requisição é bloqueada dentro de `run_tool`, nunca pelas instruções do prompt.
- **Validação de schema** — os argumentos são validados contra o `input_schema`
  da tool antes de executá-la.
- **Proveniência do runtime** — `status`, `sources` e `tools_used` são derivados
  dos eventos do run, **não** do texto do modelo.
- **Fronteiras de segurança** — só a PokéAPI é alcançável (hosts e redirects fora
  da origem são rejeitados); nenhuma tool expõe `eval`/shell/import/fs/env; cada
  requisição tem budgets (turnos, chamadas de tool, requisições HTTP, deadline).

```
POST /chat {"message"}
  └─► AgentOrchestrator (Agent + Runner, budget por requisição)
        modelo vê: search_tools · get_tool_schema · run_tool
          run_tool ─► [existe? habilitada/liberada? valida schema?] ─► get_pokemon
                        └─► PokeAPIGateway ─► HttpClient (só PokéAPI) ─► SqliteCache/PokéAPI
  └─► runtime deriva status/sources/tools_used/warnings ─► ChatResponseDTO
```

### Endpoints

| Método | Rota               | Descrição                                                        |
| ------ | ------------------ | ---------------------------------------------------------------- |
| `POST` | `/chat`            | Pergunta em linguagem natural; responde `request_id`, `status`, `answer`, `sources`, `tools_used`, `warnings`. |
| `GET`  | `/tools?query=...` | Lista/busca determinística das tools **habilitadas**.            |
| `GET`  | `/tools/{name}`    | Contrato (`input_schema`/`output_schema`) da tool, ou `404` se ausente/desabilitada. |
| `GET`  | `/health`          | Health check (inalterado).                                       |

O `status` é um de `ok`, `partial`, `not_found`, `unsupported` ou `error` —
falhas nunca retornam um `200` de falso sucesso.

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "fale sobre o Pikachu"}'
```

As regras de negócio vivem na camada de **domínio**, isoladas de I/O — o que
mantém tudo testável sem rede.

---

## 🗂️ Estrutura (Clean Architecture)

```
src/
├── main.py       # Instância FastAPI + endpoints (/chat, /tools, /health)
├── agent.py      # Orquestração com OpenAI Agents SDK (Agent + Runner, budgets)
├── catalog.py    # Catálogo de tools (descoberta dinâmica e gating)
├── tools.py      # Tools de domínio (ex.: get_pokemon)
├── pokeapi.py    # Cliente/gateway da PokéAPI (único host alcançável + cache)
├── models.py     # Entidades de domínio (Pokemon, Provenance)
├── schemas.py    # DTOs Pydantic da API (ChatRequest/ChatResponse)
└── config.py     # Settings via .env (pydantic-settings)
tests/            # Testes offline e fixtures (sem rede)
evals/            # Casos e comando de avaliação
docs/             # Decisões de arquitetura (docs/arquitetura.md)
evidence/         # Relatórios e exemplos sanitizados
```

Detalhes de instalação, execução, exemplos e limitações: [SOLUCAO.md](SOLUCAO.md).
Decisões e evolução da arquitetura: [docs/arquitetura.md](docs/arquitetura.md).

A direção das dependências aponta sempre **para dentro**: `domain` não depende de
ninguém; `application` depende só de `domain`; `adapters`/`infrastructure`
dependem para dentro; `main.py` compõe tudo.

---

## 🧪 Como testar

### 1. Testes automatizados (offline)

Não precisam de internet nem de `OPENAI_API_KEY`: a PokéAPI e o modelo são
simulados com fakes/monkeypatch, e o cache usa um diretório temporário.

```bash
make test                 # limpa caches e roda tudo
pytest -q                 # equivalente, sem limpar caches
pytest --cov=src --cov-report=term-missing   # com cobertura
```

Rodando por área:

| Arquivo                  | O que cobre                                                                 |
| ------------------------ | --------------------------------------------------------------------------- |
| `tests/test_pokeapi.py`  | Cliente da PokéAPI: nome = id, cache SQLite (hit, TTL, persistência após reinício), 404 sem retry, retry em 5xx/429/timeout, JSON inválido, origem e redirects bloqueados, orçamento HTTP |
| `tests/test_catalog.py`  | Catálogo (3.3): `register`/duplicado, busca por nome/descrição/tag, `set_enabled`, perfis A/B, gating (desabilitada, não descoberta, sem handler), validação de args e agente com tool indisponível |
| `tests/test_tools.py`    | Tools de domínio: `get_pokemon`, `compare_pokemon`, `get_type_matchups`, `get_evolution_chain` |
| `tests/test_api.py`      | Endpoints `/chat` (status → HTTP, envelope, tamanho da mensagem), `/tools` e proveniência do runtime |
| `tests/test_health.py`   | `/health`                                                                   |

```bash
pytest tests/test_catalog.py -q                   # um arquivo
pytest -q -k "e07 or http_budget or indisponivel" # cenários por nome
```

Verificação de tipos (opcional, `pip install mypy`):

```bash
mypy src
```

### 2. Testando o catálogo na mão (sem chave da OpenAI)

As rotas `/tools` leem o catálogo direto, sem LLM. Suba o servidor com
`make run` e:

```bash
curl http://localhost:8000/tools                    # todas as tools habilitadas
curl "http://localhost:8000/tools?query=evolution"  # busca lexical
curl http://localhost:8000/tools/get_pokemon        # contrato (input/output schema)
curl -i http://localhost:8000/tools/nao_existe      # 404
```

Perfil **A** (sem `get_evolution_chain`) para ver uma tool desabilitada:

```bash
POKEGARDEN_TOOLS_PROFILE=A make run
curl "http://localhost:8000/tools?query=evolution"  # []
curl -i http://localhost:8000/tools/get_evolution_chain   # 404
```

### 3. Testando o agente de ponta a ponta (precisa de `OPENAI_API_KEY`)

Com a chave no `.env` e o servidor rodando:

```bash
# ok: descobre e executa get_pokemon (sources com url e collected_at)
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Quais os tipos e a velocidade do Pikachu?"}'

# not_found (HTTP 404): Pokémon inexistente
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Quais os tipos do Pokémon xyzabc?"}'

# unsupported (HTTP 422): pergunta ambígua
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Quem ganha, Pikachu ou Charmander?"}'
```

Com `POKEGARDEN_TOOLS_PROFILE=A`, pergunte sobre evolução ("Como o Eevee
evolui?"): o agente não acha a tool e responde que a capacidade não está
disponível, sem inventar dados.

Repetir a mesma pergunta mostra o cache funcionando: a segunda resposta volta
com `"cached": true` e o mesmo `collected_at` da primeira coleta.
