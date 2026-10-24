## ADDED Requirements

### Requirement: Coleta normalizada de Pokémon

O cliente DEVE (SHALL) aceitar um Pokémon por nome ou por ID numérico e retornar um modelo normalizado contendo `id`, `name`, `types`, `abilities`, `height`, `weight` e as seis base stats (`hp`, `attack`, `defense`, `special-attack`, `special-defense`, `speed`). As unidades de `height` (decímetros) e `weight` (hectogramas), conforme a PokéAPI, DEVEM (SHALL) ser documentadas. O cliente NÃO DEVE (MUST NOT) depender de nenhum código do agente ou do OpenAI SDK.

#### Scenario: Busca por nome e por ID são equivalentes

- **WHEN** o cliente busca `pikachu` e depois busca o ID `25`
- **THEN** ambas as chamadas retornam a mesma entidade normalizada (mesmo `id` e `name`)

#### Scenario: Entrada é normalizada

- **WHEN** o cliente recebe `"  Pikachu "` com espaços e maiúsculas
- **THEN** a entrada é normalizada (trim + minúsculas) antes da consulta

### Requirement: Proveniência em todo dado retornado

Todo dado retornado DEVE (SHALL) incluir proveniência: a URL de origem na PokéAPI, o timestamp da coleta e a indicação de origem (cache hit ou busca ao vivo). Esses metadados DEVEM (SHALL) vir do runtime, nunca de texto gerado por modelo.

#### Scenario: Resposta ao vivo carrega proveniência

- **WHEN** o cliente busca um Pokémon pela rede
- **THEN** o resultado inclui a URL de origem, o timestamp da coleta e indicação de cache miss

### Requirement: Cache local persistente com expiração

O cliente DEVE (SHALL) persistir respostas em cache local (arquivos ou SQLite) com timestamp, URL original e uma política de expiração (TTL) documentada. Um cache hit dentro do TTL DEVE (SHALL) preservar a data de coleta original e evitar nova chamada de rede.

#### Scenario: Cache hit dentro do TTL

- **WHEN** um Pokémon já coletado é solicitado novamente dentro do TTL
- **THEN** o cliente responde a partir do cache sem chamada de rede
- **AND** a data de coleta original é preservada e a origem é indicada como cache hit

#### Scenario: Cache persiste após reinício

- **WHEN** o processo é reiniciado e um Pokémon previamente coletado é solicitado dentro do TTL
- **THEN** o cliente ainda responde a partir do cache persistido

### Requirement: Tratamento de erros sem fabricação de dados

O cliente DEVE (SHALL) tratar not-found (404), timeout, falha de conexão, resposta inválida (JSON malformado ou contrato inesperado) e indisponibilidade, retornando tipos de erro distinguíveis. O cliente NÃO DEVE (MUST NOT) inventar ou completar dados ausentes.

#### Scenario: Pokémon inexistente

- **WHEN** o cliente busca um nome inexistente e a PokéAPI responde 404
- **THEN** o cliente retorna um erro de not-found distinguível, sem dados fabricados

#### Scenario: Resposta inválida

- **WHEN** a PokéAPI retorna JSON malformado ou fora do contrato esperado
- **THEN** o cliente retorna um erro de resposta inválida, sem dados parciais inventados

### Requirement: Timeouts e retries limitados

O cliente DEVE (SHALL) aplicar timeout por chamada HTTP e repetir com backoff apenas falhas transitórias (timeout, 5xx e 429 respeitando `Retry-After`). O cliente NÃO DEVE (MUST NOT) repetir 404 nem erros de argumento inválido, e o número de tentativas DEVE (SHALL) ser limitado.

#### Scenario: Retry em falha transitória

- **WHEN** a PokéAPI responde 429 com `Retry-After` ou 5xx
- **THEN** o cliente aguarda conforme o backoff e repete até o limite configurado

#### Scenario: Sem retry em 404

- **WHEN** a PokéAPI responde 404
- **THEN** o cliente não repete a chamada e retorna not-found imediatamente

### Requirement: Coleta restrita à PokéAPI

O cliente DEVE (SHALL) restringir toda coleta à PokéAPI configurada em `POKEAPI_BASE_URL`. O cliente NÃO DEVE (MUST NOT) aceitar URLs arbitrárias vindas do usuário ou do modelo, e DEVE (SHALL) validar URLs de recursos e redirecionamentos, rejeitando qualquer destino fora da origem permitida.

#### Scenario: URL arbitrária rejeitada

- **WHEN** uma URL fora do domínio da PokéAPI é fornecida como alvo de coleta
- **THEN** o cliente rejeita a requisição antes de qualquer acesso à rede

#### Scenario: Redirecionamento para fora da origem é bloqueado

- **WHEN** uma resposta tenta redirecionar para um domínio fora da PokéAPI
- **THEN** o cliente bloqueia o redirecionamento e não segue o destino externo
