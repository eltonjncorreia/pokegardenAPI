## Why

O agente e as tools de domínio precisam de dados reais da PokéAPI, mas o desafio exige que a coleta seja feita por um cliente HTTP reutilizável, **separado da lógica do agente**, com cache local persistente e proveniência (URL de origem + data de coleta). Construir essa base primeiro permite testar tudo offline (sem chave OpenAI e sem rede) antes de montar o agente.

## What Changes

- Adicionar um cliente HTTP da PokéAPI (`app/pokeapi.py`) isolado, sem dependência do OpenAI SDK.
- Normalizar entrada por nome ou ID e retornar um modelo estável: `id`, `name`, `types`, `abilities`, `height`, `weight` e as seis base stats, com unidades documentadas.
- Anexar proveniência a todo dado retornado: URL de origem, timestamp da coleta e indicação de cache hit/miss.
- Cache local persistente (arquivos JSON ou SQLite) com timestamp, política de expiração (TTL) documentada e a URL original; cache hit preserva a data de coleta original.
- Tratar sem fabricar dados: not-found (404), timeout, falha de conexão, resposta inválida e indisponibilidade.
- Timeout por chamada; retry com backoff apenas para falhas transitórias (timeout, 5xx, 429 com `Retry-After`); **não** repetir 404 nem argumento inválido.
- Restringir a coleta à PokéAPI: nunca aceitar URL arbitrária de usuário ou modelo; validar URLs de recursos e redirecionamentos.

## Capabilities

### New Capabilities
- `pokeapi-client`: cliente HTTP para a PokéAPI com normalização, cache persistente, proveniência, tratamento de erros e limites.

### Modified Capabilities
<!-- Nenhuma. service-health não muda. -->

## Impact

- **Código**: novo módulo `app/pokeapi.py` (cliente + cache); modelos Pydantic de dados normalizados (ex.: `app/schemas.py` ou inline); configuração via `.env` (`POKEAPI_BASE_URL`, `CACHE_DIR`, `CACHE_TTL_SECONDS`).
- **APIs**: nenhuma rota HTTP nova nesta change (consumido internamente pelas tools).
- **Dependências**: `requests` (já em `requirements.txt`); cache em arquivos ou `sqlite3` (stdlib).
- **Testes**: suíte offline determinística com fixtures e respostas simuladas; sem rede real.
