## 1. Estrutura e modelos

- [x] 1.1 Criar o pacote plano `app/tools/` (um arquivo por tool) e `__init__.py`
- [x] 1.2 Definir modelos Pydantic de saída estruturada e envelope de erro distinguível (argumento inválido, não encontrado, resposta inválida, indisponibilidade)
- [x] 1.3 Criar helper de normalização/validação de entrada (trim + minúsculas, nome ou ID) reutilizado pelas tools

## 2. Tool get_pokemon

- [x] 2.1 Implementar `get_pokemon` consumindo o `pokeapi-client`, com descrição útil e schema de entrada
- [x] 2.2 Montar saída com dados normalizados aparados + proveniência (URL, `collected_at`, cache hit/miss) e unidades documentadas
- [x] 2.3 Rotular qualquer tradução gerada pelo modelo como "tradução gerada"; cobrir E01 (nome == ID) e entrada inválida em teste

## 3. Tool compare_pokemon

- [x] 3.1 Validar lista de 2 a 6 itens e cada identificador no servidor
- [x] 3.2 Calcular em código diferenças por stat, totais por Pokémon e maior/menor; marcar empates e dados ausentes (`None` != `0`)
- [x] 3.3 Incluir disclaimer de que totais não são previsão de batalha; cobrir E03 (Charizard vs Blastoise) e E06 (item inválido) em teste

## 4. Tool get_type_matchups

- [x] 4.1 Obter a tabela de eficácia de tipos (preferir endpoint `type` do cliente) e combinar multiplicadores em código para tipo duplo
- [x] 4.2 Classificar atacantes em imunidade (0), resistência, neutro e fraqueza; declarar que ignora habilidades, itens, clima, golpes e STAB
- [x] 4.3 Tratar tipo inexistente com erro distinguível; cobrir E04 (tipo duplo + imunidade) em teste

## 5. Tool get_evolution_chain

- [x] 5.1 Mapear a estrutura recursiva da cadeia para árvore com filhos e condições por aresta, sem linearizar ramos
- [x] 5.2 Preservar condições/níveis ausentes como ausentes (nunca inferir) e anexar proveniência
- [x] 5.3 Cobrir E05 (ramos do Eevee) e cadeia linear simples em teste

## 6. Erros e ambiguidade

- [x] 6.1 Mapear erros do `pokeapi-client` para os tipos de erro distinguíveis em todas as tools
- [x] 6.2 Garantir que a camada de resposta exponha limitação em pergunta ambígua "quem ganha?" sem fabricar vencedor; cobrir E11 em teste

## 7. Testes e validação

- [x] 7.1 Suíte offline determinística com o cliente simulado/fixtures para todas as tools
- [x] 7.2 Rodar `openspec validate add-domain-tools` e garantir "is valid"
