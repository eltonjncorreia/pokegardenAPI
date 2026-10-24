## Why

O desafio exige que o agente **não** receba todas as tools de domínio pré-carregadas: ele deve descobrir capacidades em tempo de execução a partir de um catálogo, buscar o contrato de cada tool, checar disponibilidade e só então executar por um mecanismo controlado. Isso é a parte mais distintiva e sensível à segurança do PokéGarden (prova de extensão Config A/B) e precisa existir antes do agente para que a adição de uma nova tool seja puramente declarativa, sem mexer no prompt principal, no endpoint de chat nem na orquestração.

## What Changes

- Adicionar um catálogo de tools (`app/catalog.py`): um registro de entradas com `name`, `version`, `description`, `tags`, `input_schema`, `output_schema` e flag `enabled`.
- Expor **apenas** tools de descoberta no início de cada request: `search_tools(query)` (busca lexical, resultado vazio tratado) e `get_tool_schema(name)`. Schemas completos das tools de domínio **NÃO** são pré-carregados.
- Adicionar um executor controlado que é o **único** caminho para rodar uma tool de domínio, aplicando o gating em código.
- Bloquear EM CÓDIGO (não só por prompt) qualquer execução de tool desabilitada (`enabled=false`) ou não descoberta na request corrente.
- Manter estado de descoberta e limites por request, isolados entre requests paralelas (sem estado compartilhado de tools habilitadas).
- Registrar tools de forma declarativa (módulo/manifesto), de modo que a extensão Config A -> Config B (adicionar `get_evolution_chain`) não exija mudança no prompt principal, no endpoint de chat, no loop de orquestração nem roteamento especial para "evolution".

## Capabilities

### New Capabilities
- `tool-catalog`: registro de tools com schemas e flag de habilitação, descoberta em runtime (`search_tools`, `get_tool_schema`), execução controlada com gating em código, isolamento de estado por request e extensão declarativa (Config A/B).

### Modified Capabilities
<!-- Nenhuma. service-health e pokeapi-client não mudam. -->

## Impact

- **Código**: novo módulo `app/catalog.py` (registro + descoberta + executor controlado + estado por request). Pacote flat, sem Clean Architecture. As 4 tools de domínio (`get_pokemon`, `compare_pokemon`, `get_type_matchups`, `get_evolution_chain`) registram-se declarativamente; esta change define apenas o catálogo e o mecanismo, não as tools em si.
- **APIs**: nenhuma rota HTTP nova nesta change (consumido internamente pelo agente/orquestração em change futura).
- **Dependências**: `pydantic` para modelar entradas do registro; nada além do já previsto.
- **Config**: perfil de habilitação por ambiente (Config A = só as 3 primeiras tools; Config B = adiciona `get_evolution_chain`), declarativo.
- **Testes**: suíte offline determinística cobrindo E05 (Eevee em A e B), E07 (capacidade ausente + execução bloqueada de tool desabilitada/não descoberta) e E12 (duas requests paralelas independentes, sem estado compartilhado).
