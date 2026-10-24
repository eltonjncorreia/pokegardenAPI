# Tasks

## 1. Interpretador e ambiente

- [x] 1.1 Instalar Python 3.12 com pyenv (`pyenv install 3.12`) e fixar na raiz com `.python-version`; verificar que `pyenv version` aponta para 3.12.x
- [x] 1.2 Criar o venv do projeto com o interpretador 3.12 e verificar que `python --version` dentro do venv imprime 3.12.x
- [x] 1.3 Criar `requirements.txt` com fastapi, uvicorn, openai, requests, pydantic, pydantic-settings; instalar e verificar que `pip install -r requirements.txt` conclui sem erro

## 2. Estrutura Clean Architecture

- [x] 2.1 Criar pacotes `app/domain`, `app/application`, `app/adapters`, `app/infrastructure` (com `__init__.py`) e `tests/unit`, `tests/integration`; verificar que `python -c "import app"` funciona
- [x] 2.2 Adicionar `tests/conftest.py` vazio/base e verificar que `pytest` coleta 0 testes sem erro de import

## 3. Aplicação FastAPI e /health

- [x] 3.1 Criar `app/main.py` com instância FastAPI e a rota `GET /health` retornando JSON `{"status": "ok"}` com HTTP 200
- [x] 3.2 Escrever teste de integração em `tests/integration/test_health.py` usando `TestClient`, cobrindo os dois cenários da spec (status 200 + campo `"ok"`; `Content-Type: application/json`); verificar que o teste passa
- [x] 3.3 Subir o servidor com `uvicorn app.main:app` e verificar manualmente que `curl localhost:8000/health` retorna `{"status":"ok"}`

## 4. Configuração centralizada

- [x] 4.1 Criar `app/infrastructure/config.py` com `Settings` (pydantic-settings) lendo `OPENAI_API_KEY`, `POKEAPI_BASE_URL`, `CACHE_DIR` de `.env`; verificar com um teste unitário que carrega valores de um `.env` de teste
- [x] 4.2 Criar `.env.example` documentando as variáveis e adicionar `.env` ao `.gitignore`; verificar que `.env.example` lista todas as chaves lidas por `Settings`

## 5. Logger e tratamento de exceção

- [x] 5.1 Criar `app/infrastructure/logger.py` com logger configurado (nível via `LOG_LEVEL`/Settings); verificar com teste unitário que o logger emite no nível configurado
- [x] 5.2 Criar exceções base/helpers de exception handling em `app/infrastructure/`; verificar com teste unitário que as exceções customizadas carregam mensagem/contexto esperados

## 6. Verificação de integração da Sessão 1

- [x] 6.1 Rodar `pytest` e confirmar que toda a suíte passa; confirmar que o esqueleto respeita a direção de dependências (domain não importa de adapters/infrastructure)
