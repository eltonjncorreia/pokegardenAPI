## Context

As tools de domínio são a ponte entre o `pokeapi-client` (dados + proveniência) e o agente OpenAI. O desafio exige que fatos e cálculos venham de código determinístico, nunca do modelo, e que metadados (fontes, timestamps) venham do runtime. Esta change define quatro function tools num pacote plano `app/tools/`, sem Clean Architecture, proporcional ao tamanho do problema. Cada tool consome o cliente já existente e devolve saída estruturada em Pydantic que o agente apenas redige em português.

## Goals / Non-Goals

**Goals:**
- Quatro function tools (`get_pokemon`, `compare_pokemon`, `get_type_matchups`, `get_evolution_chain`) com descrição útil, schema de entrada, validação no servidor e saída estruturada.
- Cálculos (diferenças, totais, multiplicadores de tipo) feitos em código, com empates e dados ausentes explícitos.
- Erros distinguíveis mapeados a partir dos erros do cliente.
- Proveniência propagada em toda saída; fallback de unidade/tradução documentado e rotulado.

**Non-Goals:**
- Montar o agente, registrar as tools no runner ou criar rotas HTTP (change futura).
- Reimplementar HTTP, cache ou proveniência (vem de `pokeapi-client`).
- Previsão de batalha, cálculo de dano com STAB/habilidades/itens/clima, catálogo ou busca fuzzy de nomes.

## Decisions

- **Pacote plano `app/tools/`, uma tool por arquivo.** Mais simples que camadas; o usuário pediu explicitamente para evitar Clean Architecture. _Alternativa:_ pacote em camadas use-case/adapter — descartada por excesso de cerimônia para quatro funções puras.
- **Validação no servidor com Pydantic antes de chamar o cliente.** Tamanho de lista (2–6 em `compare_pokemon`), tipo/valor dos identificadores e nomes de tipo são validados e normalizados (trim + minúsculas) antes de qualquer I/O, retornando `InvalidArgument` cedo. _Alternativa:_ confiar no schema do SDK — descartada porque a validação de regra de negócio (intervalo da lista, tipo existente) não cabe só no JSON schema.
- **Cálculo de comparação em código.** `compare_pokemon` lê as base stats normalizadas, computa diferença por stat, total por Pokémon e maior/menor, marcando empates (valores iguais) e ausências (`None`). A saída carrega um campo explícito dizendo que totais não são previsão de batalha. _Alternativa:_ deixar o modelo somar — descartada: viola "sem fabricação" e é não determinístico.
- **Algoritmo de matchup defensivo em código.** Parte de uma tabela de eficácia de tipos (18x18, multiplicadores 0/0.5/1/2). Para tipo duplo, multiplica os dois vetores defensivos elemento a elemento; o produto classifica cada tipo atacante em imunidade (0), resistência (<1), neutro (1) ou fraqueza (>1), inclusive duplas (0.25 / 4). A tabela pode vir do próprio `pokeapi-client` (endpoint `type`) para não ser hardcode divergente; combinação é sempre em código. Escopo declarado na saída: ignora habilidades, itens, clima, golpes e STAB. _Alternativa:_ pedir matchup combinado ao modelo — descartada por risco de alucinação e erro em imunidades.
- **Árvore de evolução preservada, não linearizada.** `get_evolution_chain` mapeia a estrutura recursiva (`chain` -> `evolves_to[]`) da PokéAPI para uma árvore com filhos e condições por aresta; ramos paralelos (ex.: Eevee) viram múltiplos filhos. Condições ausentes ficam `None`, nunca inferidas. _Alternativa:_ achatar para lista ordenada — descartada: perde ramos e força invenção de ordem.
- **Erros distinguíveis mapeados do cliente.** `NotFound`, `InvalidResponse`, `UpstreamUnavailable`, `InvalidArgument` do `pokeapi-client` são repassados como tipo de erro estruturado na saída da tool, para a camada de resposta decidir o texto (`not_found`, `error`, esclarecimento).
- **Fallback de unidade/tradução documentado e rotulado.** Unidades seguem a PokéAPI (decímetros, hectogramas), documentadas na saída; conversões, se oferecidas, são calculadas em código. Nomes/tipos em português não existem como fato oficial — qualquer tradução gerada pelo modelo é rotulada como "tradução gerada", nunca apresentada como dado da fonte.

## Risks / Trade-offs

- [Tabela de eficácia de tipos divergir da PokéAPI] → preferir derivar os multiplicadores do endpoint `type` do cliente; se houver tabela estática, cobri-la por teste contra fixtures.
- [Cadeia de evolução profunda/ramificada mal mapeada] → teste determinístico com fixture do Eevee (multi-ramo) e de cadeia linear simples.
- [Pergunta ambígua "quem ganha?" levar o modelo a prever batalha] → saída de comparação carrega disclaimer explícito; camada de resposta pede esclarecimento (E11).
- [Campos ausentes tratados como zero] → distinguir `None` (ausente) de `0` em stats e condições, propagando ausência na saída.

## Migration Plan

Change puramente aditiva: novos arquivos em `app/tools/` + testes offline com o cliente simulado. Depende conceitualmente de `add-pokeapi-client`. Rollback = remover o pacote `app/tools/` (nada depende dele até a change do agente).

## Open Questions

- Origem definitiva da tabela de eficácia de tipos: endpoint `type` do cliente (dinâmico) vs. tabela estática versionada — resolver na implementação conforme cobertura de cache.
- Formato exato do envelope de erro estruturado compartilhado entre as quatro tools — alinhar com o contrato que o agente consumirá.
