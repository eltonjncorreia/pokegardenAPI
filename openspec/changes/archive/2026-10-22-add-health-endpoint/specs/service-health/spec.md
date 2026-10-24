## ADDED Requirements

### Requirement: Endpoint de health (liveness)

O serviço DEVE (SHALL) expor um endpoint `GET /health` que informa se o processo está em execução e apto a responder requisições. O endpoint NÃO DEVE (MUST NOT) depender de nenhum serviço externo (banco de dados, cache ou API de terceiros), para permanecer um sinal de liveness barato e autocontido.

#### Scenario: Serviço em execução

- **WHEN** um cliente envia `GET /health`
- **THEN** o serviço responde com status HTTP `200`
- **AND** o corpo da resposta é um JSON contendo `{"status": "ok"}`

#### Scenario: Endpoint documentado

- **WHEN** um cliente consulta o schema OpenAPI gerado
- **THEN** a rota `GET /health` aparece listada com sua resposta `200` em JSON
