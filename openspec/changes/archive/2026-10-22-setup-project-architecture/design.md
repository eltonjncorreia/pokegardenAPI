# Design

## Context

Projeto greenfield, sem código. O ambiente de dev tem Python 3.10.12 no sistema, mas o plano exige 3.12+ (ver proposal.md — What Changes). A máquina já possui pyenv/nvm instalados em `~/.nvm` (node) e precisamos de uma forma reprodutível de fixar o Python. A arquitetura alvo é Clean Architecture (ver proposal.md — Why).

## Goals / Non-Goals

**Goals**
- Interpretador Python fixado de forma reprodutível em 3.12.
- Esqueleto de pastas que imponha a direção de dependências da Clean Architecture.
- App FastAPI executável com `/health` respondendo.
- Configuração e logging centralizados, prontos para as próximas sessões.

**Non-Goals**
- Entidades de domínio, use cases, gateway PokéAPI, cache (Sessões 2–5).
- Integração real com OpenAI SDK além de instalar a dependência.
- CI/CD, containerização, deploy.

## Decisions

### D1: Python 3.12 via pyenv (`.python-version`)
- **Escolha**: instalar 3.12 com `pyenv install 3.12` e fixar com um `.python-version` na raiz; criar o venv com esse interpretador.
- **Por quê**: pyenv isola a versão por projeto sem mexer no Python do sistema (3.10); `.python-version` torna a escolha versionável e reprodutível.
- **Alternativas**: usar o 3.10 do sistema (rejeitado — abre mão de recursos e diverge do plano); deadsnakes/apt (rejeitado — global, menos isolado); conda (rejeitado — peso desnecessário).

### D2: Direção de dependências da Clean Architecture
- **Escolha**: `domain` não importa de ninguém; `application` importa só de `domain`; `adapters` e `infrastructure` importam para dentro; `main.py` compõe tudo.
- **Por quê**: mantém regras de negócio puras e testáveis sem I/O (habilita o TDD das Sessões 2–3).
- **Alternativas**: estrutura flat (rejeitada — não escala para as 7 sessões).

```
  adapters ---\
               >--> application --> domain
  infra -----/            ^
   main.py --- compõe e injeta ---^
```

### D3: Configuração com pydantic-settings + `.env`
- **Escolha**: `Settings` (pydantic-settings) lê `.env`; `.env.example` documenta as chaves; `.env` fica fora do versionamento.
- **Por quê**: validação tipada das variáveis e padrão explícito (preferência global do usuário por Pydantic/Settings via .env).

### D4: Dependência de servidor
- **Escolha**: incluir `uvicorn` no `requirements.txt` além de FastAPI, para que `/health` seja executável (`uvicorn app.main:app`).
- **Por quê**: FastAPI não serve sozinho; a entrega da Sessão 1 pede `/health` funcionando.

## Risks / Trade-offs

- `pyenv install 3.12` pode falhar por faltar libs de build (libssl, libffi) → documentar pré-requisitos no README/`.env.example` e verificar `python --version` após o venv.
- Travar dependências sem pins pode quebrar builds futuros → usar versões com faixa compatível no `requirements.txt` e revisar ao congelar.
- OpenAI SDK instalado mas não usado nesta sessão → aceitável; evita reinstalar depois (dependência core do desafio).

## Migration Plan

Não aplicável — projeto novo, sem estado a migrar. Rollback = remover `app/`, `.python-version`, `requirements.txt` e o venv.
