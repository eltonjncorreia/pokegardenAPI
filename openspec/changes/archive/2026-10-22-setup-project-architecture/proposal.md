# Proposal

## Why

O projeto PokéGarden está vazio de código: não há interpretador fixado, dependências, estrutura de pastas nem aplicação FastAPI. Sem essa base (Sessão 1 do plano) nenhuma outra sessão — domínio, use cases, adapters, cache, testes — pode avançar. Esta mudança estabelece o alicerce do projeto e entrega o primeiro sinal observável de que o serviço está de pé: o endpoint `/health`.

## What Changes

- Fixar **Python 3.12** via **pyenv** (`.python-version`) como interpretador base do projeto.
- Criar o venv do projeto e um `requirements.txt` com as dependências core: FastAPI, Uvicorn, OpenAI SDK, requests, Pydantic/pydantic-settings.
- Criar a estrutura de pastas Clean Architecture: `app/domain`, `app/application`, `app/adapters`, `app/infrastructure`, mais `tests/unit` e `tests/integration`.
- Criar a aplicação FastAPI mínima em `app/main.py` com o endpoint **`GET /health`**.
- Adicionar configuração centralizada via Pydantic Settings (`app/infrastructure/config.py`) lendo de `.env`, com `.env.example` documentado (`OPENAI_API_KEY`, `POKEAPI_BASE_URL`, `CACHE_DIR`).
- Adicionar logger configurado e helpers de tratamento de exceção em `app/infrastructure/`.

## Capabilities

### New Capabilities
- `service-health`: expõe o estado operacional do serviço por um endpoint HTTP de health check, usado para readiness/liveness e como primeiro sinal de que a aplicação subiu.

### Modified Capabilities
<!-- Nenhuma: não há specs existentes. -->

## Impact

- **Dependências**: adiciona pyenv (ambiente de dev), FastAPI, Uvicorn, OpenAI SDK, requests, Pydantic/pydantic-settings.
- **Código novo**: `app/` (domain, application, adapters, infrastructure), `app/main.py`, `app/infrastructure/config.py` e `logger`, `tests/`.
- **Configuração**: `.python-version`, `requirements.txt`, `.env.example` (e `.env` local ignorado).
- **APIs**: introduz o endpoint `GET /health`.
- **Sem breaking changes** — projeto greenfield.
