## Context

O cliente da PokéAPI é a fundação de dados do PokéGarden. O desafio exige coleta separada da lógica do agente, cache persistente com proveniência e tratamento robusto de falhas, sem fabricar dados. Esta change entrega só o cliente e seu cache, de forma 100% testável offline (sem chave OpenAI, sem rede). As tools de domínio (change futura) consumirão este cliente.

## Goals / Non-Goals

**Goals**
- Cliente HTTP isolado, síncrono, reutilizável por qualquer tool.
- Modelo normalizado estável com unidades documentadas.
- Cache persistente com TTL e proveniência (URL + timestamp + cache hit/miss).
- Erros distinguíveis e retries limitados apenas para falhas transitórias.
- Restrição de origem (somente PokéAPI) com validação de URL e redirecionamentos.

**Non-Goals**
- Nenhuma tool de domínio, agente, catálogo ou rota HTTP (changes separadas).
- Sem cache distribuído, sem async, sem camada de ORM.

## Decisions

- **Cache em arquivos JSON sob `CACHE_DIR`, não SQLite.** Mais simples de inspecionar, versionar mentalmente e testar; chave = caminho do recurso normalizado. Cada registro guarda `url`, `collected_at`, `payload`. _Alternativa:_ SQLite — descartada por adicionar schema e migração sem ganho neste volume. Trocar depois é local ao módulo de cache.
- **`requests` síncrono com uma função de fetch + wrapper de cache.** O challenge pede coleta sob demanda em lotes limitados, não alta concorrência. _Alternativa:_ `httpx` async — descartada para manter o cliente simples; `httpx` fica só nos testes (TestClient).
- **Retry manual com backoff exponencial, apenas para 429/5xx/timeout.** `Retry-After` do 429 é respeitado quando presente. 404 e argumento inválido retornam de imediato. _Alternativa:_ `urllib3 Retry` — descartada por dificultar distinguir transitório de permanente e testar o `Retry-After`.
- **Erros como tipos/exceções distinguíveis** (`NotFound`, `InvalidResponse`, `UpstreamUnavailable`, `InvalidArgument`) em vez de retornar `None`. Deixa a camada de tool mapear para status (`not_found`, `error`, ...).
- **Allowlist de origem por comparação de host com `POKEAPI_BASE_URL`.** Toda URL (inclusive de recursos aninhados e redirects) é validada contra o host permitido antes do acesso; redirecionamentos são inspecionados (não seguidos automaticamente para fora da origem).
- **Modelo normalizado em Pydantic** com `extra="ignore"`, aparando campos da PokéAPI para só o necessário; unidades (`height` em decímetros, `weight` em hectogramas) documentadas no modelo.

## Risks / Trade-offs

- [Cache em arquivos pode corromper em escrita concorrente] → escrita atômica (arquivo temporário + rename); concorrência real fica fora de escopo nesta change.
- [PokéAPI muda formato/campos] → modelo tolerante (`extra="ignore"`) e erro `InvalidResponse` explícito em vez de quebra silenciosa.
- [Backoff pode estourar o deadline por requisição] → limite de tentativas e teto de espera configuráveis; o deadline total por request é responsabilidade da change do agente.
- [Validação de redirect incompleta vaza SSRF] → desabilitar follow automático e checar cada hop contra a allowlist; coberto por teste de redirect out-of-origin.

## Migration Plan

Não há dados legados. O código anterior foi descartado a pedido. Rollout é puramente aditivo: novo módulo + testes. Rollback = remover o módulo (nada depende dele até a próxima change).

## Open Questions

- Formato exato da chave de cache para recursos além de `pokemon` (ex.: `type`, `evolution-chain`) — resolver quando as tools correspondentes forem propostas.
- TTL padrão: assumido `CACHE_TTL_SECONDS=86400` (24h) do `.env.example`; confirmar se o desafio espera outro valor.
