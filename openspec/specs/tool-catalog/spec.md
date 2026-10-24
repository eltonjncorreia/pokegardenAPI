# tool-catalog Specification

## Purpose
TBD - created by archiving change add-tool-catalog. Update Purpose after archive.
## Requirements
### Requirement: Registro de tools com schema e habilitação

O catálogo DEVE (SHALL) manter um registro de tools no qual cada entrada contém `name`, `version`, `description`, `tags`, `input_schema`, `output_schema` e uma flag `enabled`. O registro DEVE (SHALL) permitir registro declarativo (por módulo/manifesto), e uma entrada com `enabled=false` DEVE (SHALL) permanecer descrita no registro porém indisponível para execução.

#### Scenario: Entrada de registro completa

- **WHEN** uma tool é registrada no catálogo
- **THEN** sua entrada expõe `name`, `version`, `description`, `tags`, `input_schema`, `output_schema` e `enabled`

#### Scenario: Tool desabilitada permanece descrita

- **WHEN** uma tool é registrada com `enabled=false`
- **THEN** seus metadados continuam consultáveis no registro
- **AND** a tool é marcada como indisponível para execução

### Requirement: Descoberta em runtime sem pré-carregar schemas

No início de uma request o agente DEVE (SHALL) receber apenas as tools de descoberta (`search_tools`, `get_tool_schema`) e, quando necessário, um executor controlado. Os schemas completos das tools de domínio NÃO DEVEM (MUST NOT) ser pré-carregados no contexto do agente; eles DEVEM (SHALL) ser obtidos sob demanda via `get_tool_schema(name)`.

#### Scenario: Busca lexical retorna correspondências

- **WHEN** o agente chama `search_tools("evolution")`
- **THEN** o catálogo retorna as tools habilitadas cujo nome, descrição ou tags correspondem ao termo

#### Scenario: Busca sem correspondência

- **WHEN** o agente chama `search_tools` com um termo sem correspondência
- **THEN** o catálogo retorna uma lista vazia, sem erro

#### Scenario: Contrato obtido sob demanda

- **WHEN** o agente chama `get_tool_schema("get_pokemon")` para uma tool habilitada
- **THEN** o catálogo retorna o `input_schema` e o `output_schema` daquela tool
- **AND** nenhum schema de domínio foi injetado no contexto antes dessa chamada

### Requirement: Descoberta determinística sem LLM

A listagem/busca de tools habilitadas e seus metadados DEVE (SHALL) ser determinística e puramente lexical sobre o registry. `search_tools(query)` e `get_tool_schema(name)` NÃO DEVEM (MUST NOT) chamar o modelo de linguagem nem consumir tokens: são busca textual pura sobre `name`, `description` e `tags`, sem raciocínio do LLM. Para uma mesma query e um mesmo estado do registry, o resultado DEVE (SHALL) ser sempre idêntico.

#### Scenario: Mesma query retorna sempre o mesmo resultado

- **WHEN** `search_tools("evolution")` é chamado duas vezes com o registry inalterado
- **THEN** ambas as chamadas retornam exatamente o mesmo conjunto de tools, na mesma ordem

#### Scenario: Descoberta não consome tokens nem chama o LLM

- **WHEN** `search_tools(query)` ou `get_tool_schema(name)` é executado
- **THEN** a operação resolve apenas por busca lexical no registry em código
- **AND** nenhuma chamada ao modelo de linguagem é feita e nenhum token é consumido

### Requirement: Execução controlada com gating em código

Toda execução de tool de domínio DEVE (SHALL) passar por um executor controlado que valida, EM CÓDIGO, que a tool está habilitada (`enabled=true`) e foi descoberta na request corrente antes de validar os argumentos contra o `input_schema` e executar. O executor NÃO DEVE (MUST NOT) executar tool desabilitada ou não descoberta, independentemente do que o prompt ou o modelo solicitem.

#### Scenario: Execução de tool desabilitada é bloqueada

- **WHEN** o agente tenta executar uma tool com `enabled=false`
- **THEN** o executor rejeita a execução em código, sem chamar a tool
- **AND** retorna um erro de capacidade indisponível

#### Scenario: Execução de tool não descoberta é bloqueada

- **WHEN** o agente tenta executar uma tool que não foi descoberta via `search_tools`/`get_tool_schema` na request corrente
- **THEN** o executor rejeita a execução em código, sem chamar a tool

#### Scenario: Argumentos inválidos são rejeitados

- **WHEN** o agente executa uma tool habilitada e descoberta com argumentos que violam o `input_schema`
- **THEN** o executor rejeita a execução antes de chamar a tool
- **AND** retorna um erro de validação distinguível

### Requirement: Estado de descoberta e limites por request

O catálogo DEVE (SHALL) manter o estado de descoberta (quais tools foram descobertas e habilitadas) e os limites do fluxo no escopo de uma única request. Requests paralelas NÃO DEVEM (MUST NOT) compartilhar estado de tools habilitadas nem estado de descoberta; o estado de uma request NÃO DEVE (MUST NOT) vazar para outra.

#### Scenario: Descoberta não vaza entre requests paralelas

- **WHEN** duas requests independentes executam em paralelo e a request A descobre uma tool
- **THEN** a request B não enxerga essa descoberta e precisa descobrir por conta própria

#### Scenario: Perfis de habilitação distintos por request

- **WHEN** uma request roda sob um perfil que habilita uma tool e outra request roda sob um perfil que a desabilita
- **THEN** cada request aplica apenas seu próprio conjunto de tools habilitadas

#### Scenario: Limites aplicados ao fluxo inteiro

- **WHEN** uma request atinge o limite configurado de chamadas de tool do fluxo
- **THEN** o executor bloqueia novas execuções naquela request sem afetar outras requests

### Requirement: Extensão declarativa de tools (Config A/B)

Adicionar uma nova tool DEVE (SHALL) exigir apenas seu módulo/manifesto, seus testes e seu registro declarativo no catálogo. NÃO DEVE (MUST NOT) ser necessário alterar o prompt principal, o endpoint de chat, o loop de orquestração nem adicionar roteamento especial para uma tool específica (por exemplo, "evolution"). Quando uma capacidade solicitada não existe ou está desabilitada, o agente DEVE (SHALL) informar que a capacidade está indisponível, sem improvisar a resposta.

#### Scenario: Config A informa capacidade indisponível (E05/E07)

- **WHEN** apenas as três primeiras tools estão habilitadas (Config A) e o usuário pede a cadeia de evolução do Eevee
- **THEN** `search_tools` não retorna a tool de evolução
- **AND** o agente responde que a capacidade está indisponível, sem improvisar dados de evolução

#### Scenario: Config B descobre a nova tool antes de executar (E05)

- **WHEN** a tool `get_evolution_chain` é adicionada e habilitada (Config B) apenas por registro declarativo e o usuário pede a evolução do Eevee
- **THEN** o agente descobre a tool via `search_tools`, obtém o contrato via `get_tool_schema` e a executa pelo executor controlado
- **AND** nenhuma alteração foi feita no prompt principal, no endpoint de chat ou no loop de orquestração

