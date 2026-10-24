## Context

Esta change é a camada de topo do PokéGarden: a API HTTP e a orquestração do agente que amarram o cliente PokéAPI e as tools de domínio (changes de base) a um endpoint conversacional em português. O `GET /health` já foi entregue (`openspec/specs/service-health`). O desafio exige um agente real (OpenAI Agents SDK com `Agent` + `Runner` e function tools), proveniência verificável, segurança contra prompt injection e limites explícitos por requisição. A restrição de arquitetura foi decidida com o usuário: manter pacote flat (sem Clean Architecture), com `app/main.py` (HTTP) chamando uma única função `run_chat(message) -> Result` em `app/agent.py`.

## Goals / Non-Goals

**Goals:**
- Contrato HTTP estável: `POST /chat`, `GET /tools`, `GET /tools/{name}` (health já existe).
- Fronteira nítida: HTTP não conhece o SDK nem a PokéAPI; toda orquestração vive em `app/agent.py`.
- Envelope de resposta com proveniência de runtime e separação fatos/cálculos/limitações.
- Mapeamento status→HTTP sem falso 200; orçamentos/deadline por requisição; isolamento stateless.
- Defesa contra prompt injection e execução segura de tools.

**Non-Goals:**
- Implementar o cliente PokéAPI, as tools de domínio ou o catálogo (changes separadas).
- Redefinir `GET /health`.
- Persistência de histórico/sessão, autenticação de usuários, streaming, concorrência distribuída.
- Clean Architecture ou múltiplas camadas: o pacote é flat e proporcional ao escopo.

## Decisions

- **Fronteira `main.py` → `run_chat()`.** `app/main.py` só faz HTTP (validação de corpo, mapeamento status→código, serialização) e chama `run_chat(message)`. O OpenAI SDK e a PokéAPI ficam contidos em `app/agent.py` e nas tools. _Alternativa:_ injetar o `Runner` no controller — descartada por vazar o SDK para a camada HTTP e dificultar testes do contrato.
- **`Result` como objeto de runtime, não texto do modelo.** `run_chat` retorna um dataclass/Pydantic com `request_id`, `status`, `answer`, `sources`, `tools_used`, `warnings`. `sources` e `tools_used` são montados a partir de hooks/callbacks das execuções reais de tools (a proveniência vem do cliente PokéAPI: URL, `collected_at`, cache hit/miss), nunca extraídos do texto do modelo. _Alternativa:_ pedir ao modelo para listar fontes — descartada por ser falsificável e violar o requisito de metadados de runtime.
- **Mapeamento status→HTTP.** `ok`/`partial` → `200`; `not_found` → `404`; `unsupported` → `422`; `error` → `5xx`. Validação de corpo (FastAPI/Pydantic) → `422` antes de executar o agente. Regra de ouro: validação e indisponibilidade nunca retornam `200` com aparência de sucesso. _Alternativa:_ sempre `200` com status no corpo — descartada por mascarar falhas a clientes e monitores.
- **`/tools` e `/tools/{name}` determinísticos, sem LLM.** Leem o registry/catálogo de tools habilitadas e seus metadados; não chamam o modelo, não rodam `Runner`, não consomem tokens. Apenas `POST /chat` executa o fluxo `Agent`/`Runner`. _Alternativa:_ gerar descrições via modelo — descartada por custo, não-determinismo e risco de alucinação de contrato.
- **Orçamentos aplicados à requisição inteira.** Timeout por chamada HTTP (herdado do cliente PokéAPI) + deadline total por requisição + caps de turns do modelo, execuções de tools e requisições HTTP (incluindo retries). Ao esgotar qualquer orçamento, encerra com `status` `partial` e registra em `warnings`. Padrões propostos (ajustáveis via `.env`): deadline total 20s, timeout por chamada 5s, max turns 6, max tool calls 8, max HTTP requests 12, mensagem máxima 2000 chars, saída máxima de tool 8 KB. _Alternativa:_ só timeout global — descartada por não conter loops de tool-calling nem explosão de custo.
- **Isolamento stateless.** Cada requisição cria seu próprio contexto (contadores de orçamento, `request_id`, acumulador de metadados); nada mutável é global. Garante que E12 (duas requisições paralelas) não compartilhe estado.
- **Defesa contra prompt injection.** Instruções do sistema fixas e separadas do input; texto do usuário e saídas de tools entram como dado. As permissões/tools habilitadas vêm do registry, não do conteúdo. Nenhuma tool expõe eval/shell/import/leitura de arquivo/env; URLs são restritas ao host da PokéAPI (validação já no cliente). Argumentos de tool validados por schema antes da execução.
- **Escolha de modelo.** Padrão proposto `OPENAI_MODEL=gpt-4o-mini`: boa capacidade de tool-calling a baixo custo/latência, adequado a um assistente local com orçamento limitado de tokens e turns. Configurável via `.env`; a chave vem de `OPENAI_API_KEY` e nunca é exposta em logs/respostas/tools. _Alternativa:_ modelo maior (`gpt-4o`) — disponível por configuração quando se quer mais qualidade, ao custo de latência/tokens.

## Risks / Trade-offs

- [Loop de tool-calling consome tokens/estoura deadline] → caps de turns e de execuções de tools + deadline total; encerra como `partial` com `warnings`.
- [Prompt injection via texto externo simulado] → instruções fixas, conteúdo tratado como dado, permissões vindas do registry; coberto por testes E10.
- [Modelo tenta inventar fontes/tools] → `sources`/`tools_used` montados só do runtime; texto do modelo nunca alimenta metadados.
- [Falso 200 mascarando falha] → mapeamento status→HTTP centralizado e testado, incluindo validação (`422`) e indisponibilidade (`5xx`).
- [Estado compartilhado entre requisições paralelas] → contexto por requisição, sem globais mutáveis; coberto por teste E12.
- [Modelo padrão indisponível/custo] → modelo e limites configuráveis via `.env`; defaults documentados.

## Migration Plan

Rollout puramente aditivo: novos módulos `app/main.py` e `app/agent.py`, novas variáveis em `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL`, limites). Depende das changes de base (cliente PokéAPI, tools de domínio, catálogo) estarem disponíveis para importação pelo agente. `GET /health` permanece inalterado. Rollback = remover as rotas novas e os dois módulos; nada depende desta camada.

## Open Questions

- Valores finais dos caps (deadline, turns, tool calls) — defaults propostos acima, a confirmar com o desafio.
- Formato exato do `request_id` (UUID v4 assumido) e se deve ser ecoado em header HTTP além do corpo.
- Semântica fina de `partial` vs `unsupported` para perguntas ambíguas (E11) — ambos previstos na spec; decidir caso a caso na implementação.
