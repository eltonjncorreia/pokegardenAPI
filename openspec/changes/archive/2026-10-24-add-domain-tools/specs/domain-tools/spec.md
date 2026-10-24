## ADDED Requirements

### Requirement: Tool get_pokemon retorna dados normalizados com proveniência

A tool `get_pokemon` DEVE (SHALL) aceitar um Pokémon por nome ou por ID numérico, validar e normalizar a entrada no servidor (trim + minúsculas) e retornar uma saída estruturada com os dados normalizados do `pokeapi-client` (`id`, `name`, `types`, `abilities`, `height`, `weight`, as seis base stats) acompanhados da proveniência (URL de origem, `collected_at`, cache hit/miss). A tool DEVE (SHALL) aparar os campos ao que é necessário e documentar as unidades (`height` em decímetros, `weight` em hectogramas). A proveniência DEVE (SHALL) vir do runtime; a tool NÃO DEVE (MUST NOT) fabricar fatos ou metadados. A tool DEVE (SHALL) ter uma descrição útil e um schema de entrada explícito, e NÃO DEVE (MUST NOT) retornar traduções de nomes como se fossem dados oficiais da PokéAPI — qualquer tradução gerada pelo modelo DEVE (SHALL) ser rotulada como tradução gerada.

#### Scenario: Busca por nome equivale a busca por ID (E01)

- **WHEN** a tool recebe `pikachu` e, em outra chamada, o ID `25`
- **THEN** ambas retornam a mesma entidade normalizada (mesmo `id` e `name`)
- **AND** a saída inclui a proveniência (URL, `collected_at`, indicação de cache hit/miss) vinda do runtime

#### Scenario: Entrada inválida é rejeitada sem alucinação

- **WHEN** a tool recebe uma entrada vazia ou de tipo inválido
- **THEN** a tool retorna um erro de argumento inválido distinguível, sem inventar dados

### Requirement: Tool compare_pokemon compara de 2 a 6 Pokémon com cálculo em código

A tool `compare_pokemon` DEVE (SHALL) aceitar uma lista de 2 a 6 Pokémon (por nome ou ID), validando o tamanho da lista e cada item no servidor. A tool DEVE (SHALL) comparar tipos e as seis base stats e computar diferenças, totais por Pokémon e maiores/menores valores **em código**, nunca delegando o cálculo ao modelo. A saída estruturada DEVE (SHALL) declarar explicitamente empates e dados ausentes, e DEVE (SHALL) indicar que os totais de stats **NÃO** são (MUST NOT) uma previsão de resultado de batalha. A proveniência de cada Pokémon DEVE (SHALL) ser preservada na saída.

#### Scenario: Charizard vs Blastoise com matemática e critérios explícitos (E03)

- **WHEN** a tool compara `charizard` e `blastoise`
- **THEN** a saída traz, por stat, os valores de cada Pokémon e a diferença calculada em código
- **AND** traz os totais de base stats de cada um e o critério de comparação usado
- **AND** declara que os totais não representam previsão de vitória em batalha

#### Scenario: Empate e dado ausente são declarados

- **WHEN** dois Pokémon têm o mesmo valor em uma stat, ou uma stat está ausente para algum deles
- **THEN** a saída marca explicitamente o empate e identifica o dado ausente, sem preencher valores inventados

#### Scenario: Lista fora do intervalo permitido é rejeitada

- **WHEN** a tool recebe menos de 2 ou mais de 6 Pokémon
- **THEN** a tool retorna um erro de argumento inválido distinguível antes de consultar o cliente

### Requirement: Tool get_type_matchups calcula relações defensivas e declara o escopo

A tool `get_type_matchups` DEVE (SHALL) aceitar um ou dois tipos (ou derivá-los de um Pokémon) e retornar as relações defensivas — fraquezas, resistências e imunidades — combinando os multiplicadores de dano **em código** para tipos duplos. A saída DEVE (SHALL) declarar explicitamente que o cálculo ignora habilidades, itens, clima, golpes e STAB. A tool NÃO DEVE (MUST NOT) inventar relações de tipo ausentes e DEVE (SHALL) retornar tipo de erro distinguível para tipo inexistente.

#### Scenario: Matchup de tipo duplo com imunidade (E04)

- **WHEN** a tool recebe um Pokémon de tipo duplo cujo cruzamento resulta em imunidade a um tipo de ataque
- **THEN** a saída combina os multiplicadores dos dois tipos em código e lista a imunidade (multiplicador 0) separadamente de fraquezas e resistências
- **AND** declara que habilidades, itens, clima, golpes e STAB foram ignorados

#### Scenario: Tipo inexistente é rejeitado

- **WHEN** a tool recebe um nome de tipo inexistente
- **THEN** a tool retorna um erro distinguível, sem fabricar relações de dano

### Requirement: Tool get_evolution_chain preserva ramos e condições sem linearizar

A tool `get_evolution_chain` DEVE (SHALL) aceitar uma espécie (por nome ou ID) e retornar a árvore de evolução preservando a estrutura de ramificações e as condições de evolução (nível, item, troca, felicidade, etc.) conforme a origem. A tool NÃO DEVE (MUST NOT) linearizar ramos paralelos nem inventar níveis ou condições; valores ausentes DEVEM (SHALL) ser preservados como ausentes. A proveniência DEVE (SHALL) acompanhar a saída.

#### Scenario: Ramos de evolução do Eevee preservados (E05)

- **WHEN** a tool recebe `eevee`
- **THEN** a saída representa cada evolução ramificada como um filho distinto na árvore, sem achatar em uma lista linear
- **AND** cada aresta de evolução traz as condições disponíveis e preserva como ausentes as que a origem não fornece

#### Scenario: Condição ausente não é inventada

- **WHEN** uma evolução não possui nível ou condição informada na origem
- **THEN** a saída marca a condição como ausente em vez de inferir um valor

### Requirement: Tools expõem erros distinguíveis sem alucinação

Todas as tools de domínio DEVEM (SHALL) mapear falhas em tipos de erro distinguíveis (ex.: argumento inválido, não encontrado, resposta inválida, indisponibilidade) a partir dos erros do `pokeapi-client`, retornando uma saída estruturada de erro. As tools NÃO DEVEM (MUST NOT) fabricar dados nem responder sobre um Pokémon inexistente como se existisse. Quando uma pergunta for ambígua (ex.: "quem ganha?"), a tool/ a camada de resposta DEVE (SHALL) expor a limitação — os dados não predizem batalha — em vez de inventar um vencedor.

#### Scenario: Nome inexistente ou item inválido na lista (E06)

- **WHEN** uma tool recebe um nome inexistente, ou `compare_pokemon` recebe um item inválido na lista
- **THEN** a tool retorna um erro de não encontrado/argumento inválido distinguível, sem alucinar dados para o item

#### Scenario: Pergunta ambígua "quem ganha?" (E11)

- **WHEN** o usuário pergunta "quem ganha?" entre Pokémon sem critério claro de batalha
- **THEN** a resposta expõe a limitação (os totais de stats não predizem o resultado de batalha) e pede esclarecimento do critério, sem declarar um vencedor fabricado
