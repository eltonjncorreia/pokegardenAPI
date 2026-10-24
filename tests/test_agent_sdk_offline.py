"""Fluxo offline completo pelo Runner REAL do Agents SDK (modelo roteirizado).

Diferente de ``test_api.py`` (que substitui o ``Runner``), aqui o SDK executa as
tools de verdade: descoberta → contrato → validação → execução, com a PokéAPI
servida por fixtures (``evals/fixtures``). Sem rede e sem chave da OpenAI.
"""

import pytest

import agent, pokeapi
from config import settings
from evals.fake_pokeapi import FakePokeApi
from evals.scripted_model import ScriptedModel, call, final


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(settings, "pokeapi_base_url", "https://pokeapi.co/api/v2")
    monkeypatch.setenv("POKEGARDEN_TOOLS_PROFILE", "B")
    server = FakePokeApi()
    monkeypatch.setattr(pokeapi.requests, "get", server)
    return server


def test_sdk_descobre_valida_e_executa(api):
    model = ScriptedModel([
        call("search_tools", query="evolução"),
        call("get_tool_schema", name="get_evolution_chain"),
        call("run_tool", name="get_evolution_chain", args={"name_or_id": "eevee"}),
        final("ok", "Eevee tem 8 ramos."),
    ])
    result = agent.run_chat("Como o Eevee evolui?", model=model)

    assert result.status == "ok"
    assert result.tools_used == ["search_tools", "get_tool_schema", "get_evolution_chain"]
    assert [s["url"] for s in result.sources] == [
        "https://pokeapi.co/api/v2/pokemon-species/eevee",
        "https://pokeapi.co/api/v2/evolution-chain/67",
    ]
    # O SDK devolveu ao modelo as saídas reais das 3 tools.
    assert len(model.observed) == 3
    assert '"vaporeon"' in model.observed[-1]["output"]


def test_sdk_bloqueia_tool_nao_descoberta(api):
    model = ScriptedModel([
        call("run_tool", name="get_evolution_chain", args={"name_or_id": "eevee"}),
        final("unsupported", "Indisponível."),
    ])
    result = agent.run_chat("Evolução do Eevee", model=model)

    assert result.sources == [] and api.gets == []
    assert "ToolDisabled" in model.observed[0]["output"]


def test_sdk_args_invalidos_nao_chegam_ao_handler(api):
    model = ScriptedModel([
        call("search_tools", query="tipo fraqueza"),
        call("run_tool", name="get_type_matchups", args={"types": "fire"}),
        final("unsupported", "Argumentos inválidos."),
    ])
    result = agent.run_chat("Fraquezas do fire", model=model)

    assert api.gets == [] and result.sources == []
    assert "ToolArgsInvalid" in model.observed[-1]["output"]
