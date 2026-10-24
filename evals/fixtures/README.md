# Fixtures

Payloads no formato da PokéAPI usados **apenas** nas avaliações e testes
offline. Cada arquivo tem a chave `"_fixture"` para que nunca seja confundido
com uma consulta real, inclusive depois de passar pelo cache.

- Stats, tipos e relações de dano reproduzem os valores públicos da PokéAPI
  para que as checagens numéricas valham também no modo live.
- `pokemon/injectmon` é fictício: carrega uma instrução maliciosa no campo de
  habilidade (texto externo simulado do E10).
