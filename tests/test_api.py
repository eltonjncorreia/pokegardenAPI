"""Testes offline da camada HTTP e do wiring do agente.

Sem rede e sem chave real: o agente e o catálogo são simulados via monkeypatch.
O objetivo é cobrir o mapeamento status->HTTP, o envelope de resposta, a
validação de tamanho, o determinismo de ``/tools`` (sem LLM) e o fluxo de
proveniência de runtime do agente.
"""

import agent as agent_module
import main as main_module
import agent as agent_pkg
from agent import Result
from fastapi.testclient import TestClient

client = TestClient(main_module.app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /chat — mapeamento status -> HTTP e envelope
# ---------------------------------------------------------------------------
def _patch_run_chat(monkeypatch, result: Result):
    monkeypatch.setattr(main_module.agent, "run_chat", lambda message: result)


def test_chat_ok_200_full_envelope(monkeypatch):
    result = Result(
        request_id="req-1",
        status="ok",
        answer="Pikachu é do tipo Elétrico.",
        sources=[{"tool": "get_pokemon", "url": "https://pokeapi.co/api/v2/pokemon/pikachu",
                  "collected_at": "2026-01-01T00:00:00Z", "cached": False}],
        tools_used=["get_pokemon"],
        warnings=[],
    )
    _patch_run_chat(monkeypatch, result)
    resp = client.post("/chat", json={"message": "Quais os tipos do Pikachu?"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"request_id", "status", "answer", "sources", "tools_used", "warnings"}
    assert body["status"] == "ok"
    assert body["tools_used"] == ["get_pokemon"]
    assert body["sources"][0]["url"].startswith("https://pokeapi.co")


def test_chat_not_found_404(monkeypatch):
    _patch_run_chat(monkeypatch, Result("r", "not_found", "Não existe esse Pokémon."))
    resp = client.post("/chat", json={"message": "tipos do Pokemon xyz"})
    assert resp.status_code == 404
    assert resp.json()["status"] == "not_found"


def test_chat_unsupported_422(monkeypatch):
    _patch_run_chat(monkeypatch, Result("r", "unsupported", "Preciso das regras de batalha."))
    resp = client.post("/chat", json={"message": "quem ganha, Charizard ou Blastoise?"})
    assert resp.status_code == 422
    assert resp.json()["status"] == "unsupported"


def test_chat_error_never_false_200(monkeypatch):
    _patch_run_chat(monkeypatch, Result("r", "error", "Falha interna."))
    resp = client.post("/chat", json={"message": "oi"})
    assert resp.status_code == 500
    assert resp.json()["status"] == "error"


def test_chat_partial_200_with_warnings(monkeypatch):
    _patch_run_chat(
        monkeypatch,
        Result("r", "partial", "Resposta incompleta.", warnings=["Deadline esgotado."]),
    )
    resp = client.post("/chat", json={"message": "algo demorado"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert body["warnings"] == ["Deadline esgotado."]


# ---------------------------------------------------------------------------
# POST /chat — validação (nunca executa o agente)
# ---------------------------------------------------------------------------
def test_chat_missing_message_422(monkeypatch):
    called = {"v": False}
    monkeypatch.setattr(main_module.agent, "run_chat", lambda m: called.__setitem__("v", True))
    resp = client.post("/chat", json={})
    assert resp.status_code == 422
    assert called["v"] is False


def test_chat_message_too_long_422(monkeypatch):
    called = {"v": False}
    monkeypatch.setattr(main_module.agent, "run_chat", lambda m: called.__setitem__("v", True))
    big = "x" * (main_module.settings.max_message_chars + 1)
    resp = client.post("/chat", json={"message": big})
    assert resp.status_code == 422
    assert called["v"] is False


# ---------------------------------------------------------------------------
# /tools — determinístico, sem LLM, sem tokens
# ---------------------------------------------------------------------------
def test_tools_list_deterministic_no_llm(monkeypatch):
    calls = {"list": 0, "search": 0}

    def fake_list():
        calls["list"] += 1
        return [{"name": "get_pokemon", "description": "Dados de um Pokémon"}]

    monkeypatch.setattr(main_module.catalog, "list_enabled", fake_list)
    # Garante que o fluxo do agente/LLM nunca é tocado por /tools.
    monkeypatch.setattr(main_module.agent, "run_chat", lambda m: (_ for _ in ()).throw(AssertionError("LLM!")))

    r1 = client.get("/tools")
    r2 = client.get("/tools")
    assert r1.status_code == 200
    assert r1.json() == r2.json()  # determinístico
    assert calls["list"] == 2
    assert r1.headers["cache-control"] == f"public, max-age={main_module.settings.tools_cache_max_age_seconds}"


def test_tools_search_query(monkeypatch):
    monkeypatch.setattr(
        main_module.catalog, "search_tools",
        lambda q: [{"name": "get_pokemon", "description": q}],
    )
    resp = client.get("/tools", params={"query": "pokemon"})
    assert resp.status_code == 200
    assert "max-age=" in resp.headers["cache-control"]
    assert resp.json()[0]["name"] == "get_pokemon"


def test_tool_schema_found(monkeypatch):
    monkeypatch.setattr(
        main_module.catalog, "get_tool_schema",
        lambda name: {"name": name, "parameters": {"name": "str"}},
    )
    resp = client.get("/tools/get_pokemon")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get_pokemon"
    assert "max-age=" in resp.headers["cache-control"]


def test_tool_schema_missing_404(monkeypatch):
    def raise_missing(name):
        raise main_module.catalog.ToolNotFound(name)

    monkeypatch.setattr(main_module.catalog, "get_tool_schema", raise_missing)
    resp = client.get("/tools/nope")
    assert resp.status_code == 404
    assert "cache-control" not in resp.headers


def test_health_not_cached():
    assert "cache-control" not in client.get("/health").headers


# ---------------------------------------------------------------------------
# Fluxo offline do agente: descoberta -> validação -> execução com proveniência
# de RUNTIME (sem chamar a OpenAI). Simula o Runner, mas os metadados vêm das
# execuções reais de tools via o contexto da requisição.
# ---------------------------------------------------------------------------
def test_run_chat_runtime_metadata(monkeypatch):
    executed = {}

    def fake_execute(name, args, discovered):
        executed["name"] = name
        executed["args"] = args
        return {
            "url": "https://pokeapi.co/api/v2/pokemon/pikachu",
            "collected_at": "2026-01-01T00:00:00Z",
            "cached": True,
            "types": ["electric"],
        }

    monkeypatch.setattr(agent_pkg.catalog, "execute_tool", fake_execute)

    class FakeRun:
        final_output = agent_module.AgentOutput(status="ok", answer="Pikachu é Elétrico.")

    def fake_run_sync(agent, message, *, context, max_turns, run_config=None):
        # Simula o modelo: descobre e executa a tool de domínio via runtime.
        context.discovered.add("get_pokemon")
        output = agent_pkg.catalog.execute_tool("get_pokemon", {"name": "pikachu"}, context.discovered)
        agent_pkg._record_provenance(context, "get_pokemon", output)
        # Mesmo que o modelo "mencione" uma URL inventada, ela não entra em sources.
        return FakeRun()

    monkeypatch.setattr(agent_module.Runner, "run_sync", staticmethod(fake_run_sync))

    result = agent_module.run_chat("Quais os tipos do Pikachu?")
    assert result.status == "ok"
    assert result.tools_used == ["get_pokemon"]
    assert result.sources[0]["url"] == "https://pokeapi.co/api/v2/pokemon/pikachu"
    assert result.sources[0]["cached"] is True
    assert executed["args"] == {"name": "pikachu"}
    assert result.request_id  # request_id próprio por requisição


def test_run_chat_error_on_runtime_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("SDK indisponível")

    monkeypatch.setattr(agent_module.Runner, "run_sync", staticmethod(boom))
    result = agent_module.run_chat("oi")
    assert result.status == "error"
    assert result.request_id


def test_warnings_das_tools_vao_para_a_resposta():
    ctx = agent_module.RequestContext(request_id="r", deadline_at=float("inf"))
    output = {"sources": [{"url": "u", "collected_at": "t", "source": "live"}], "warnings": ["aviso A", "aviso A"]}
    agent_pkg._record_provenance(ctx, "get_pokemon", output)
    agent_pkg._record_provenance(ctx, "get_pokemon", output)
    assert ctx.warnings == ["aviso A"]  # sem duplicar
    assert ctx.tools_used == ["get_pokemon"]
