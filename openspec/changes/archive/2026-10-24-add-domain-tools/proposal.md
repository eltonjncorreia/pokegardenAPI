## Why

O agente do PokéGarden responde em português sobre Pokémon, mas o modelo não pode inventar fatos: dados e cálculos precisam vir de código determinístico. A change `add-pokeapi-client` já entrega o cliente HTTP com dados normalizados e proveniência (URL de origem, `collected_at`, cache hit/miss). Falta expor essas informações ao agente como **tools de função** que fazem a consulta e a matemática no código, deixando ao modelo apenas a redação da resposta.

## What Changes

- Adicionar quatro tools de função (OpenAI Agents SDK) em um pacote plano `app/tools/*.py`, consumindo o `pokeapi-client`.
- `get_pokemon`: retorna dados normalizados + proveniência de um Pokémon por nome ou ID.
- `compare_pokemon`: compara de 2 a 6 Pokémon por tipos e base stats; diferenças e totais calculados **em código**; sinaliza empates e dados ausentes; os totais **não** são previsão de batalha.
- `get_type_matchups`: fraquezas/resistências/imunidades defensivas, combinadas para tipos duplos; ignora habilidades, itens, clima, golpes e STAB — e declara isso.
- `get_evolution_chain`: espécie + árvore de evolução com ramificações e condições, preservando valores ausentes; **não** lineariza ramos nem inventa níveis.
- Cada tool DEVE ter descrição útil, schema de entrada, validação no servidor, saída estruturada, tipos de erro distinguíveis, campos aparados e fallback de unidade/tradução documentado (traduções geradas pelo modelo rotuladas como tal).

## Capabilities

### New Capabilities
- `domain-tools`: quatro tools de função que consomem o `pokeapi-client` para expor dados e cálculos (consulta, comparação, matchups de tipo e cadeia de evolução) ao agente, sem fabricar fatos.

### Modified Capabilities
<!-- Nenhuma. pokeapi-client e service-health não mudam. -->

## Impact

- **Código**: novo pacote plano `app/tools/` (`get_pokemon.py`, `compare_pokemon.py`, `get_type_matchups.py`, `get_evolution_chain.py`); modelos Pydantic de saída (reutilizando/estendendo os do `pokeapi-client`).
- **Dependências**: depende conceitualmente da change `add-pokeapi-client` (cliente + proveniência); `openai-agents` para o decorator de function tool.
- **APIs**: nenhuma rota HTTP nova; as tools são registradas no agente (change futura).
- **Testes**: suíte offline determinística com o cliente simulado/fixtures; cobre cenários de avaliação E01, E03, E04, E05, E06 e E11.
