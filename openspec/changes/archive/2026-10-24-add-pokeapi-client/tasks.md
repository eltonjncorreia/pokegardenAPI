## 1. Configuração e modelos

- [x] 1.1 Adicionar settings via `.env` (`POKEAPI_BASE_URL`, `CACHE_DIR`, `CACHE_TTL_SECONDS`) com `pydantic-settings`
- [x] 1.2 Definir o modelo normalizado `Pokemon` (Pydantic) com `id`, `name`, `types`, `abilities`, `height`, `weight`, seis base stats e unidades documentadas
- [x] 1.3 Definir o modelo de proveniência (`url`, `collected_at`, `source`: live|cache) anexado ao resultado

## 2. Cache persistente

- [x] 2.1 Implementar cache em arquivos JSON sob `CACHE_DIR` com escrita atômica (temp + rename)
- [x] 2.2 Guardar `url`, `collected_at` e `payload`; aplicar TTL e preservar a data de coleta original em cache hit

## 3. Cliente HTTP

- [x] 3.1 Implementar fetch com `requests`, timeout por chamada e normalização de nome/ID (trim + minúsculas)
- [x] 3.2 Implementar retry com backoff apenas para 429 (respeitando `Retry-After`), 5xx e timeout; sem retry em 404/argumento inválido
- [x] 3.3 Definir erros distinguíveis (`NotFound`, `InvalidResponse`, `UpstreamUnavailable`, `InvalidArgument`)
- [x] 3.4 Validar origem: rejeitar URLs fora do host de `POKEAPI_BASE_URL` e bloquear redirects out-of-origin
- [x] 3.5 Integrar cache + fetch na função pública (ex.: `get_pokemon(name_or_id)`), retornando modelo + proveniência

## 4. Testes offline (determinísticos, sem rede)

- [x] 4.1 E01: busca por nome e por ID retornam a mesma entidade normalizada
- [x] 4.2 E02: cache hit dentro do TTL (sem rede) e persistência após reinício
- [x] 4.3 Erros: 404 (sem retry), timeout/5xx (com retry limitado), 429 com `Retry-After`, JSON inválido
- [x] 4.4 Segurança: URL arbitrária rejeitada antes da rede e redirect out-of-origin bloqueado
- [x] 4.5 Rodar `pytest` e confirmar que a suíte passa sem chave e sem rede
