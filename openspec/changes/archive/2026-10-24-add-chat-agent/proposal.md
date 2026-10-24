## Why

O PokéGarden precisa de uma camada de topo que exponha a API HTTP e orquestre o agente (OpenAI Agents SDK) que responde perguntas sobre Pokémon em português. O endpoint de health já existe e as changes de base (cliente PokéAPI, tools de domínio, catálogo de tools) entregam os blocos internos; falta o contrato HTTP e a orquestração `Agent + Runner` que amarram tudo com segurança, limites e proveniência verificável.

## What Changes

- Adicionar a API FastAPI em `app/main.py` com três rotas (além do `GET /health` já existente):
  - `GET /tools?query=...`: lista/pesquisa as tools habilitadas (resposta pode ser determinística, sem chamar o modelo).
  - `GET /tools/{name}`: retorna o contrato de uma tool, ou erro documentado se ausente/desabilitada.
  - `POST /chat`: recebe `{"message": "..."}`, executa o fluxo real do SDK (`Agent` + `Runner` com function tools) e responde um envelope estruturado.
- Definir a fronteira de arquitetura: `app/main.py` chama **uma** função `run_chat(message) -> Result` em `app/agent.py`. `app/main.py` NÃO importa o OpenAI SDK nem a PokéAPI diretamente.
- Envelope de resposta do `/chat`: `request_id`, `status` (`ok|partial|not_found|unsupported|error`, cada um com significado documentado), `answer` (em português, separando fatos / cálculos / limitações), `sources` (URLs, timestamps de coleta e indicação de cache), `tools_used`, `warnings`. Metadados vêm do runtime, nunca do modelo.
- Mapear `status` para códigos HTTP; falhas de validação e indisponibilidades NÃO retornam HTTP 200 com aparência de sucesso.
- Confiabilidade/limites: timeout por chamada HTTP, deadline total por requisição, caps configuráveis de turns do modelo / execuções de tools / requisições HTTP (incl. retries) aplicados à requisição inteira; limites de tamanho de entrada, de saída de tool e de concorrência. Comportamento ao esgotar orçamento é documentado (status `partial`).
- Segurança: nunca aceitar URLs arbitrárias do usuário/modelo; validar argumentos antes de executar; nenhuma tool expõe eval/shell/import arbitrário/leitura de arquivos/variáveis de ambiente; prompt injection (na mensagem do usuário E em texto externo simulado) não altera permissões nem instruções.
- Configuração: modelo via `OPENAI_MODEL`, chave via `OPENAI_API_KEY`; escolha de modelo e justificativa documentadas em `design.md`.

## Capabilities

### New Capabilities
- `chat-agent`: contrato da API HTTP (`/chat`, `/tools`, `/tools/{name}`) e orquestração `Agent + Runner`, incluindo envelope de resposta com proveniência de runtime, mapeamento status→HTTP, orçamentos/deadline por requisição, defesa contra prompt injection e observabilidade.

### Modified Capabilities
<!-- Nenhuma. service-health não muda; esta change não redefine GET /health. -->

## Impact

- **Código**: novo `app/main.py` (FastAPI, rotas e validação de entrada), novo `app/agent.py` (`run_chat` + montagem de `Agent`/`Runner`, aplicação de orçamentos e coleta de metadados de runtime).
- **APIs**: três rotas novas (`GET /tools`, `GET /tools/{name}`, `POST /chat`); `GET /health` permanece inalterado.
- **Dependências**: `openai-agents` (OpenAI Agents SDK), `fastapi`, `pydantic`/`pydantic-settings`; consome o cliente PokéAPI e o catálogo de tools das changes de base.
- **Configuração**: `.env` ganha `OPENAI_API_KEY`, `OPENAI_MODEL` e os limites (deadline total, timeout por chamada, max turns, max tool calls, max HTTP requests, tamanho máximo de mensagem/saída de tool).
- **Testes**: suíte com `TestClient`, SDK e PokéAPI simulados (sem rede/chave real), cobrindo status→HTTP, ausência de falso 200, E10 (prompt injection), E11 (pergunta ambígua) e E12 (orçamento esgotado + duas requisições paralelas sem estado compartilhado).
