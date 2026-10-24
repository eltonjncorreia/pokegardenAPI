## 1. Configuração e settings

- [x] 1.1 Adicionar ao `.env`/`.env.example` e às settings (`pydantic-settings`): `OPENAI_API_KEY`, `OPENAI_MODEL`
- [x] 1.2 Adicionar settings de limites: deadline total por requisição, timeout por chamada HTTP, max turns, max tool calls, max HTTP requests (incl. retries), tamanho máximo de mensagem e de saída de tool
- [x] 1.3 Adicionar dependência do OpenAI Agents SDK (`openai-agents`) ao `requirements.txt`

## 2. Agente e orquestração (`app/agent.py`)

- [x] 2.1 Definir o modelo `Result` (`request_id`, `status`, `answer`, `sources`, `tools_used`, `warnings`) com os status `ok|partial|not_found|unsupported|error` documentados
- [x] 2.2 Implementar `run_chat(message) -> Result` montando `Agent` + `Runner` com as function tools do catálogo
- [x] 2.3 Fixar as instruções do sistema separadas do input; tratar mensagem do usuário e saída de tools como dado (defesa contra prompt injection)
- [x] 2.4 Criar contexto por requisição (stateless): contadores de orçamento, `request_id` e acumulador de metadados, sem estado global mutável
- [x] 2.5 Coletar `sources` e `tools_used` a partir das execuções reais de tools (URL, `collected_at`, cache hit/miss), nunca do texto do modelo
- [x] 2.6 Aplicar orçamentos (deadline total, max turns, max tool calls, max HTTP requests) e, ao esgotar, encerrar com `status` `partial` e `warnings`
- [x] 2.7 Aplicar limites de tamanho de mensagem e truncamento de saída de tool
- [x] 2.8 Validar argumentos de tool antes da execução; garantir que nenhuma tool exponha eval/shell/import/leitura de arquivo/env e que URLs fiquem restritas à PokéAPI
- [x] 2.9 Garantir que `OPENAI_API_KEY` nunca apareça em respostas nem logs

## 3. API HTTP (`app/main.py`)

- [x] 3.1 Criar o app FastAPI reaproveitando `GET /health` existente (sem redefini-lo)
- [x] 3.2 Implementar `POST /chat` com schema Pydantic de entrada (`message`), validação de tamanho e chamada a `run_chat(message)` — sem importar o OpenAI SDK nem a PokéAPI
- [x] 3.3 Centralizar o mapeamento status→HTTP (`ok`/`partial`→200, `not_found`→404, `unsupported`→422, `error`→5xx); garantir que validação e indisponibilidade nunca retornem 200
- [x] 3.4 Implementar `GET /tools?query=...` determinístico (lê registry, sem LLM, sem tokens)
- [x] 3.5 Implementar `GET /tools/{name}` determinístico; retornar erro documentado (`404`) para tool ausente/desabilitada
- [x] 3.6 Garantir que as rotas apareçam no schema OpenAPI com seus códigos de resposta

## 4. Testes (TestClient, SDK e PokéAPI simulados, sem rede/chave real)

- [x] 4.1 Pergunta factual: `POST /chat` retorna `200`, `status` `ok`, executa tool e preenche `tools_used` e `sources` com proveniência
- [x] 4.2 Validação: `message` ausente/malformada e mensagem acima do limite retornam `422` sem executar o agente
- [x] 4.3 Mapeamento status→HTTP e "sem falso 200": `not_found`→404, `error`→5xx, `partial`→200 com `warnings`
- [x] 4.4 Metadados de runtime: fontes/tools inventadas pelo texto do modelo não entram em `sources`/`tools_used`
- [x] 4.5 E10: prompt injection na mensagem e em texto externo simulado não expõe segredos nem muda permissões
- [x] 4.6 E11: pergunta ambígua ("quem ganha?") retorna esclarecimento/limitação com `status` `unsupported`/`partial`, sem vencedor fabricado
- [x] 4.7 E12: orçamento esgotado gera `partial`; duas requisições paralelas têm `request_id` próprios e não compartilham estado
- [x] 4.8 `/tools` e `/tools/{name}`: resultado determinístico, sem chamadas ao modelo; tool ausente retorna `404`
- [x] 4.9 Rodar `pytest` e confirmar que a suíte passa sem chave e sem rede
