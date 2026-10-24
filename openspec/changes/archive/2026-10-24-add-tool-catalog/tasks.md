## 1. Registro e modelo de tool

- [x] 1.1 Definir `ToolSpec` (Pydantic) com `name`, `version`, `description`, `tags`, `input_schema`, `output_schema`, `handler` e flag `enabled`
- [x] 1.2 Implementar o registry em `app/catalog.py` com `register(spec)` declarativo; entrada com `enabled=false` permanece descrita mas indisponível
- [x] 1.3 Definir o perfil de habilitação separado do registro (Config A = `get_pokemon`, `compare_pokemon`, `get_type_matchups`)

## 2. Descoberta determinística (sem LLM)

- [x] 2.1 Implementar `search_tools(query)` como busca lexical case-insensitive sobre `name`/`description`/`tags` das tools habilitadas, com ordenação estável
- [x] 2.2 Tratar resultado vazio sem erro
- [x] 2.3 Implementar `get_tool_schema(name)` como lookup direto retornando `input_schema` e `output_schema`
- [x] 2.4 Garantir determinismo: mesma query + mesmo registry => mesmo resultado; nenhuma chamada ao LLM e nenhum token consumido

## 3. Estado por request e isolamento

- [x] 3.1 Implementar `RequestContext` com perfil habilitado, conjunto de tools descobertas e contador de chamadas do fluxo
- [x] 3.2 Garantir que nenhum estado de habilitação/descoberta viva em nível de módulo (sem global mutável)
- [x] 3.3 Aplicar limite de chamadas ao fluxo inteiro da request

## 4. Executor controlado (gating em código)

- [x] 4.1 Implementar executor que recebe o `RequestContext` e só executa se a tool estiver `enabled=true` E descoberta na request
- [x] 4.2 Bloquear em código execução de tool desabilitada ou não descoberta, retornando erro de capacidade indisponível
- [x] 4.3 Validar argumentos contra o `input_schema` antes de chamar o handler; rejeitar inválidos com erro distinguível

## 5. Extensão declarativa Config A/B

- [x] 5.1 Documentar/estruturar a adição de `get_evolution_chain` apenas por módulo/manifesto + registro + inclusão no perfil (Config B)
- [x] 5.2 Garantir que não há roteamento especial para "evolution" nem dependência do prompt/chat/orquestração

## 6. Testes offline (determinísticos, sem rede, sem LLM)

- [x] 6.1 E05 (Config A): pedido de evolução do Eevee -> `search_tools` não retorna a tool; agente informa capacidade indisponível sem improvisar
- [x] 6.2 E05 (Config B): tool de evolução adicionada por registro; descoberta via `search_tools` + `get_tool_schema` e executada pelo executor
- [x] 6.3 E07: execução direta de tool desabilitada e de tool não descoberta é bloqueada em código
- [x] 6.4 E12: duas requests paralelas independentes não compartilham estado de habilitação/descoberta
- [x] 6.5 Determinismo: `search_tools` idempotente (mesmo resultado/ordem) e sem chamada ao LLM
- [x] 6.6 Validação de argumentos: args fora do `input_schema` rejeitados antes do handler
- [x] 6.7 Rodar `pytest` e confirmar que a suíte passa sem chave OpenAI e sem rede
