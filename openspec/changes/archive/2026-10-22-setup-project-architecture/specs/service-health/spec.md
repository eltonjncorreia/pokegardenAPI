# Spec Delta

## Purpose

Expõe o estado operacional do serviço PokéGarden por um endpoint HTTP de health check, usado para verificações de readiness/liveness e como sinal de que a aplicação subiu corretamente.

## ADDED Requirements

### Requirement: Endpoint de health check

O serviço SHALL expor um endpoint `GET /health` que responde ao estado operacional da aplicação sem exigir autenticação.

#### Scenario: Serviço no ar

- **WHEN** um cliente envia `GET /health`
- **THEN** o serviço responde com status HTTP `200`
- **AND** o corpo é um JSON contendo um campo de estado igual a `"ok"`

#### Scenario: Resposta em formato legível por máquina

- **WHEN** um cliente envia `GET /health`
- **THEN** a resposta tem `Content-Type: application/json`
- **AND** o corpo pode ser desserializado como objeto JSON
