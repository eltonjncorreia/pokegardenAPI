# Avaliação (evals)

Casos E01–E12 da seção 8 do desafio, versionados como código em
[`cases.py`](cases.py), e o runner que gera um relatório por caso.

## Como rodar

```bash
make test        # suíte pytest offline (inclui o fluxo pelo SDK com modelo roteirizado)
make eval        # avaliação offline: pytest + agente via SDK com modelo roteirizado
make eval-live   # modelo real (OPENAI_MODEL) + PokéAPI real; requer OPENAI_API_KEY

# direto, com filtro de casos (prefixo: E12 casa E12a..E12d)
.venv/bin/python -m evals.run --mode offline --cases E05,E12
.venv/bin/python -m evals.run --mode all
```

O comando sai com código 1 se algum caso falhar. O relatório vai para
[`../evidence/evals/`](../evidence/evals/): `report-<modo>.md` e
`report-<modo>.json`, mais os logs JSON de cada caso em `<modo>/<caso>.jsonl`.
Cada caso traz `pass`/`fail`/`not_run`, o modo, o motivo, a duração e as
evidências (logs e testes pytest). Falhas nunca são omitidas.

## Modos

| Modo | Modelo | PokéAPI | Prova |
|---|---|---|---|
| `offline-pytest` | — | fakes/monkeypatch | cliente HTTP, cache, schemas, cálculos, catálogo, limites, falhas |
| `offline-sdk-roteirizado` | `ScriptedModel` (replay) | [fixtures](fixtures/pokeapi/) | integração com o `Runner` real: descoberta, gating, validação, orçamento, metadados de runtime |
| `live` | OpenAI real | real (cache temporário) | qualidade das decisões do modelo nos casos marcados `live=True` |

O modo offline **não prova a qualidade das decisões de um modelo real**: o
roteiro é fixo. Ele prova que o runtime trata corretamente as decisões
roteirizadas, inclusive as maliciosas (E07 e E10 simulam um modelo que tenta
executar o que não deve).

Sem `OPENAI_API_KEY`, o modo live marca os casos como `not_run` com o motivo.
Casos sem execução live (E02, E07–E09, E12) aparecem como `not_run` no relatório
live, com o motivo "coberto no modo offline".

## Como um caso é verificado

Nenhuma checagem compara o texto gerado literalmente. Para cada requisição:

- **Invariantes gerais**: toda fonte em `sources` corresponde a uma execução real
  de handler; todo GET vai para `pokeapi.co`; o valor da `OPENAI_API_KEY` (ou um
  canário no modo offline) nunca aparece na resposta; `tools_used` só cita tools
  executadas.
- **Esperadas do caso** (`Expect`): status permitido, tools obrigatórias e
  proibidas (o handler é envolvido por um spy, então "proibida" significa "nunca
  executada"), mínimo/máximo de fontes, regex obrigatórias/proibidas na
  resposta, warnings, erros esperados nos logs `tool.call`, número máximo de GETs.
- **Checagens específicas**: números calculados (totais, multiplicadores),
  ordem descoberta → contrato → execução nos logs, reuso de cache entre
  requisições, sobreposição temporal e isolamento entre requisições paralelas.

## Cobertura

| Caso | Agente (offline) | Live | pytest |
|---|---|---|---|
| E01 nome × ID | ✔ | ✔ | ✔ |
| E02 cache/reinício | ✔ (repetição) | — | ✔ (reload do módulo) |
| E03 comparação | ✔ | ✔ | ✔ |
| E04 tipo duplo | ✔ | ✔ | ✔ |
| E05 evolução A/B | ✔ | ✔ (A e B separados) | ✔ |
| E06 inexistente/lista | ✔ | ✔ | ✔ |
| E07 tool ausente/bloqueada | ✔ | — | ✔ |
| E08 timeout/429/5xx/JSON | ✔ (falhas injetadas) | — | ✔ |
| E09 URL/args/redirect | ✔ | — | ✔ |
| E10 prompt injection | ✔ (pedido + texto externo) | ✔ (pedido) | ✔ |
| E11 "quem ganha?" | ✔ | ✔ | ✔ |
| E12 orçamento/paralelo | ✔ (E12a–d) | — | ✔ |

## Arquivos

- [`cases.py`](cases.py): casos, roteiros e checagens.
- [`harness.py`](harness.py): isolamento por caso (cache temporário, perfil,
  settings), spies dos handlers, captura de logs e invariantes.
- [`scripted_model.py`](scripted_model.py): `Model` do Agents SDK que responde
  com um roteiro.
- [`fake_pokeapi.py`](fake_pokeapi.py): `requests.get` falso servido pelas
  fixtures, com falhas injetáveis (status, 429 + Retry-After, timeout, JSON
  inválido, redirect).
- [`fixtures/pokeapi/`](fixtures/pokeapi/): payloads no formato da PokéAPI,
  marcados com `"_fixture"`. **Não são consultas reais.**
- [`run.py`](run.py): CLI e relatório.
