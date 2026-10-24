## Context

O PokéGarden exige que o agente descubra capacidades em runtime, em vez de receber todas as tools pré-carregadas. O catálogo é a peça mais sensível à segurança: ele controla o que pode ser executado e prova que o sistema é extensível de forma declarativa (Config A -> Config B). Esta change entrega apenas o catálogo e o mecanismo de descoberta/execução (`app/catalog.py`), 100% testável offline. As 4 tools de domínio registram-se nele, mas são definidas em outra change.

## Goals / Non-Goals

**Goals**
- Registro declarativo de tools com schema de entrada/saída e flag `enabled`.
- Descoberta determinística e sem LLM (`search_tools`, `get_tool_schema`).
- Gating em código: só executa tool habilitada E descoberta na request.
- Estado de descoberta e limites por request, isolados entre requests paralelas.
- Extensão Config A/B puramente declarativa (sem tocar prompt, chat, orquestração ou roteamento especial).

**Non-Goals**
- Não implementar as tools de domínio nem o agente/orquestração (changes separadas).
- Sem Clean Architecture, sem banco, sem async; pacote flat `app/catalog.py`.
- Sem busca semântica/embeddings; a busca é lexical.

## Decisions

- **Estado de descoberta por request via objeto de sessão explícito, não global.** Cada request cria um `RequestContext` (ou dataclass equivalente) que guarda: perfil de tools habilitadas, conjunto de tools já descobertas e contador de chamadas do fluxo. O executor recebe esse contexto como argumento. _Alternativa:_ variável global/módulo-level — descartada porque vazaria estado entre requests paralelas e quebraria E12. `contextvars` seria aceitável, mas o objeto explícito é mais simples de testar.
- **Gating em duas condições, checadas em código antes de qualquer execução:** `enabled=true` no registry E `name` presente no conjunto de descobertas da request. O prompt nunca é a fonte de verdade. Mesmo que o modelo "alucine" uma chamada a tool desabilitada/não descoberta, o executor rejeita com erro de capacidade indisponível.
- **Descoberta determinística, sem LLM.** `search_tools(query)` faz match lexical (substring/token, case-insensitive) sobre `name`, `description` e `tags` das entradas habilitadas, com ordenação estável; `get_tool_schema(name)` é lookup direto. Nenhuma chamada ao modelo; mesma query + mesmo registry => mesmo resultado, 0 tokens. Isso mantém a camada de segurança barata, auditável e reproduzível em teste.
- **Registro declarativo por manifesto.** Cada tool expõe um manifesto (`ToolSpec`: name/version/description/tags/input_schema/output_schema/handler) e se registra chamando `register(spec)`. Habilitação vem de um perfil de configuração (ex.: lista de nomes habilitados por ambiente), separado do registro. Adicionar uma tool = novo módulo + manifesto + incluir o nome no perfil. Config A = `{get_pokemon, compare_pokemon, get_type_matchups}`; Config B = A + `get_evolution_chain`. Nenhum `if name == "evolution"` em lugar nenhum.
- **Schemas como JSON Schema / modelos Pydantic.** `input_schema` valida argumentos antes da execução; `output_schema` documenta o retorno. A validação de argumentos faz parte do gating (rejeita antes de chamar o handler).
- **Limites aplicados ao fluxo inteiro.** O `RequestContext` conta execuções; ao atingir o teto, o executor bloqueia novas chamadas naquela request, sem afetar outras.

## Risks / Trade-offs

- [Estado global acidental vaza entre requests] → proibir estado mutável em nível de módulo para habilitação/descoberta; tudo no `RequestContext`; teste E12 com duas requests paralelas cobre isso.
- [Modelo tenta burlar o gating pelo prompt] → o gating é em código e independe do prompt; teste E07 executa diretamente tool desabilitada/não descoberta e espera bloqueio.
- [Busca lexical perde sinônimos] → aceitável no escopo; tags cobrem termos alternativos; resultado vazio é tratado explicitamente (agente diz capacidade indisponível).
- [Acoplamento acidental com roteamento especial de "evolution"] → prova de extensão: adicionar `get_evolution_chain` só por registro; teste confirma que o fluxo descobre/executa sem mudança em prompt/chat/orquestração.

## Migration Plan

Rollout puramente aditivo: novo módulo `app/catalog.py` + testes. O perfil de habilitação começa em Config A. Config B é alcançada adicionando o nome da tool de evolução ao perfil. Rollback = remover o módulo (nada depende dele até a change do agente).

## Open Questions

- Formato exato do perfil de habilitação (lista em `.env`, constante por ambiente ou arquivo) — resolver na integração com o agente; não bloqueia esta change.
- Valor do limite de chamadas por fluxo — assumir um teto conservador e confirmar com os cenários de avaliação.
