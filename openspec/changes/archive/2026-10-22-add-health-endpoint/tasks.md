## 1. Implementação

- [x] 1.1 Criar o app FastAPI em `app/main.py` (padrão mais simples: instanciar `FastAPI()` diretamente)
- [x] 1.2 Adicionar a rota `GET /health` que retorna `{"status": "ok"}` com status `200`, sem depender de serviços externos

## 2. Testes

- [x] 2.1 Adicionar teste de integração (`httpx`/`TestClient`) que verifica `GET /health` retornando `200` e corpo `{"status": "ok"}`
- [x] 2.2 Rodar `pytest` e confirmar que os testes passam
