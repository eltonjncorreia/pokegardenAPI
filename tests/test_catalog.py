"""Testes offline do catálogo de tools (sem rede, sem chave, sem LLM).

Os handlers de domínio são monkeypatchados para não depender da implementação
real nem da PokéAPI.
"""

import json
import re

import jsonschema
import pytest
from pydantic import ValidationError

import agent, catalog, pokeapi, tools
from models import ToolManifest


@pytest.fixture(autouse=True)
def fake_handlers(monkeypatch):
    """Substitui as tools de domínio por stubs deterministas."""
    monkeypatch.setattr(tools, "get_pokemon", lambda name_or_id: {"ok": "get_pokemon", "arg": name_or_id})
    monkeypatch.setattr(tools, "compare_pokemon", lambda names: {"ok": "compare_pokemon", "arg": names})
    monkeypatch.setattr(tools, "get_type_matchups", lambda types: {"ok": "get_type_matchups", "arg": types})
    monkeypatch.setattr(tools, "get_evolution_chain", lambda name_or_id: {"ok": "get_evolution_chain", "arg": name_or_id})


# --------------------------------------------------------------------------- #
# E05 — Config A não lista evolution; Config B lista
# --------------------------------------------------------------------------- #
def test_e05_config_a_nao_lista_evolution():
    names = {t["name"] for t in catalog.list_enabled(profile="A")}
    assert "get_evolution_chain" not in names
    assert {"get_pokemon", "compare_pokemon", "get_type_matchups"} <= names


def test_e05_config_b_lista_evolution():
    names = {t["name"] for t in catalog.list_enabled(profile="B")}
    assert "get_evolution_chain" in names
    assert len(names) == 4


def test_e05_config_b_descobre_e_executa_evolution():
    found = catalog.search_tools("evolution", profile="B")
    assert [t["name"] for t in found] == ["get_evolution_chain"]
    schema = catalog.get_tool_schema("get_evolution_chain", profile="B")
    assert "input_schema" in schema and "output_schema" in schema
    discovered = {"get_evolution_chain"}
    out = catalog.execute_tool(
        "get_evolution_chain", {"name_or_id": "eevee"}, discovered=discovered, profile="B"
    )
    assert out == {"ok": "get_evolution_chain", "arg": "eevee"}


# --------------------------------------------------------------------------- #
# E07 — capacidade ausente em Config A + gating de não-descoberta
# --------------------------------------------------------------------------- #
def test_e07_evolution_ausente_na_descoberta_config_a():
    assert catalog.search_tools("evolution", profile="A") == []
    assert all(t["name"] != "get_evolution_chain" for t in catalog.list_enabled(profile="A"))


def test_e07_get_tool_schema_bloqueia_desabilitada():
    with pytest.raises(catalog.ToolDisabled):
        catalog.get_tool_schema("get_evolution_chain", profile="A")


def test_e07_execute_bloqueia_tool_desabilitada():
    with pytest.raises(catalog.ToolDisabled):
        catalog.execute_tool(
            "get_evolution_chain",
            {"name_or_id": "eevee"},
            discovered={"get_evolution_chain"},
            profile="A",
        )


def test_e07_execute_bloqueia_tool_habilitada_mas_nao_descoberta():
    # Habilitada em B, porém ausente do set `discovered` desta request.
    with pytest.raises(catalog.ToolDisabled):
        catalog.execute_tool(
            "get_evolution_chain",
            {"name_or_id": "eevee"},
            discovered=set(),
            profile="B",
        )


def test_execute_tool_inexistente():
    with pytest.raises(catalog.ToolNotFound):
        catalog.execute_tool("nao_existe", {}, discovered={"nao_existe"}, profile="B")


# --------------------------------------------------------------------------- #
# E12 — isolamento entre requests paralelas (sets `discovered` independentes)
# --------------------------------------------------------------------------- #
def test_e12_descoberta_nao_vaza_entre_requests():
    req_a: set[str] = set()
    req_b: set[str] = set()

    # Request A descobre get_pokemon.
    catalog.get_tool_schema("get_pokemon", profile="B")
    req_a.add("get_pokemon")

    # B não enxerga a descoberta de A.
    assert "get_pokemon" not in req_b
    with pytest.raises(catalog.ToolDisabled):
        catalog.execute_tool("get_pokemon", {"name_or_id": 1}, discovered=req_b, profile="B")

    # A executa normalmente com seu próprio estado.
    out = catalog.execute_tool("get_pokemon", {"name_or_id": 1}, discovered=req_a, profile="B")
    assert out["ok"] == "get_pokemon"


# --------------------------------------------------------------------------- #
# Determinismo da busca (sem LLM, 0 tokens)
# --------------------------------------------------------------------------- #
def test_search_determinista():
    r1 = catalog.search_tools("pokemon", profile="B")
    r2 = catalog.search_tools("pokemon", profile="B")
    assert r1 == r2
    names = [t["name"] for t in r1]
    assert names == sorted(names)  # ordenação estável


def test_search_vazio_sem_erro():
    assert catalog.search_tools("xyznaoexiste", profile="B") == []


def test_search_por_tag():
    names = {t["name"] for t in catalog.search_tools("weakness", profile="B")}
    assert names == {"get_type_matchups"}


# --------------------------------------------------------------------------- #
# Validação de argumentos antes do handler
# --------------------------------------------------------------------------- #
def test_args_invalidos_rejeitados_antes_do_handler():
    with pytest.raises(catalog.ToolArgsInvalid):
        catalog.execute_tool(
            "compare_pokemon",
            {"names": ["pikachu"]},  # minItems=2
            discovered={"compare_pokemon"},
            profile="B",
        )


def test_args_campo_obrigatorio_ausente():
    with pytest.raises(catalog.ToolArgsInvalid):
        catalog.execute_tool(
            "get_pokemon", {}, discovered={"get_pokemon"}, profile="B"
        )


def test_args_tipo_invalido():
    with pytest.raises(catalog.ToolArgsInvalid):
        catalog.execute_tool(
            "get_type_matchups",
            {"types": "fire"},  # deve ser array
            discovered={"get_type_matchups"},
            profile="B",
        )


# --------------------------------------------------------------------------- #
# Perfil via variável de ambiente (default B)
# --------------------------------------------------------------------------- #
def test_profile_default_b(monkeypatch):
    # O default vem do Settings sem .env; o .env local (ex.: perfil A) não pode vazar.
    monkeypatch.delenv("POKEGARDEN_TOOLS_PROFILE", raising=False)
    default = type(catalog.settings).model_fields["pokegarden_tools_profile"].default
    assert default == "B"
    monkeypatch.setattr(catalog.settings, "pokegarden_tools_profile", default)
    names = {t["name"] for t in catalog.list_enabled()}
    assert "get_evolution_chain" in names


def test_profile_env_a(monkeypatch):
    monkeypatch.setenv("POKEGARDEN_TOOLS_PROFILE", "A")
    names = {t["name"] for t in catalog.list_enabled()}
    assert "get_evolution_chain" not in names


# --------------------------------------------------------------------------- #
# ToolCatalog (unitário, instância isolada)
# --------------------------------------------------------------------------- #
def _manifest(name="echo", **kw):
    return ToolManifest(name=name, description=kw.pop("description", "Ecoa o texto."), **kw)


def test_register_e_get_tool_schema():
    cat = catalog.ToolCatalog()
    cat.register(_manifest(tags=["util"]))
    assert cat.get_tool_schema("echo").tags == ["util"]


def test_register_rejeita_duplicado():
    cat = catalog.ToolCatalog()
    cat.register(_manifest())
    with pytest.raises(catalog.ToolAlreadyRegistered):
        cat.register(_manifest(description="outra"))
    assert cat.get("echo").description == "Ecoa o texto."  # não sobrescreveu


def test_manifesto_invalido_rejeitado():
    with pytest.raises(ValidationError):
        ToolManifest(name="", description="x")


def test_busca_por_nome_descricao_e_tag():
    cat = catalog.ToolCatalog()
    cat.register(_manifest("alpha", description="Primeira tool.", tags=["red"]))
    cat.register(_manifest("beta", description="Segunda TOOL.", tags=["blue"]))
    assert [m.name for m in cat.search_tools("ALPHA")] == ["alpha"]
    assert [m.name for m in cat.search_tools("segunda")] == ["beta"]
    assert [m.name for m in cat.search_tools("blue")] == ["beta"]
    assert [m.name for m in cat.search_tools("   ")] == ["alpha", "beta"]  # vazio = todas


def test_set_enabled_afeta_busca_e_schema():
    cat = catalog.ToolCatalog()
    cat.register(_manifest())
    cat.set_enabled("echo", False)
    assert cat.search_tools("echo") == []
    with pytest.raises(catalog.ToolDisabled):
        cat.get_tool_schema("echo")
    cat.set_enabled("echo", True)
    assert [m.name for m in cat.search_tools("echo")] == ["echo"]


def test_tool_inexistente():
    cat = catalog.ToolCatalog()
    with pytest.raises(catalog.ToolNotFound):
        cat.get_tool_schema("nope")
    with pytest.raises(catalog.ToolNotFound):
        cat.set_enabled("nope", True)


def test_build_catalog_nao_compartilha_estado():
    a, b = catalog.build_catalog("B"), catalog.build_catalog("B")
    a.set_enabled("get_pokemon", False)
    assert b.get_tool_schema("get_pokemon").enabled is True


# --------------------------------------------------------------------------- #
# Executor: desabilitada em runtime, handler autorizado, sem handler
# --------------------------------------------------------------------------- #
def test_execute_bloqueia_tool_desabilitada_em_runtime(monkeypatch):
    cat = catalog.build_catalog("B")
    cat.set_enabled("get_pokemon", False)
    monkeypatch.setattr(catalog, "get_catalog", lambda profile=None: cat)
    with pytest.raises(catalog.ToolDisabled):
        catalog.execute_tool("get_pokemon", {"name_or_id": 1}, discovered={"get_pokemon"})


def test_execute_handler_autorizado():
    out = catalog.execute_tool(
        "compare_pokemon", {"names": ["a", "b"]}, discovered={"compare_pokemon"}, profile="B"
    )
    assert out == {"ok": "compare_pokemon", "arg": ["a", "b"]}


def test_execute_sem_handler_autorizado(monkeypatch):
    cat = catalog.ToolCatalog()
    cat.register(_manifest())  # no catálogo, mas sem handler em HANDLERS
    monkeypatch.setattr(catalog, "get_catalog", lambda profile=None: cat)
    with pytest.raises(catalog.ToolDisabled):
        catalog.execute_tool("echo", {}, discovered={"echo"})


def test_args_bool_nao_e_integer():
    with pytest.raises(catalog.ToolArgsInvalid):
        catalog.execute_tool("get_pokemon", {"name_or_id": True}, discovered={"get_pokemon"}, profile="B")


# --------------------------------------------------------------------------- #
# Agente: tool necessária indisponível não gera resultado inventado
# --------------------------------------------------------------------------- #
def test_agente_tool_indisponivel_retorna_erro_sem_fonte(monkeypatch):
    monkeypatch.setenv("POKEGARDEN_TOOLS_PROFILE", "A")
    ctx = agent.RequestContext(request_id="r", deadline_at=float("inf"))
    ctx.discovered.add("get_evolution_chain")  # mesmo "descoberta" à força

    out = json.loads(agent._run_tool(ctx, "get_evolution_chain", {"name_or_id": "eevee"}))

    assert out == {"error": "ToolDisabled"}
    assert ctx.sources == [] and ctx.tools_used == []
    assert any("indisponível" in w for w in ctx.warnings)


def test_agente_args_invalidos_devolve_motivo():
    ctx = agent.RequestContext(request_id="r", deadline_at=float("inf"))
    ctx.discovered.add("compare_pokemon")
    out = json.loads(agent._run_tool(ctx, "compare_pokemon", {"names": ["só-um"]}))
    assert out["error"] == "ToolArgsInvalid" and out["detail"]
    assert ctx.sources == []


def test_agente_orcamento_http_esgotado_vira_partial(monkeypatch):
    def boom(name_or_id):
        raise pokeapi.HttpBudgetExceeded("esgotado")

    monkeypatch.setattr(tools, "get_pokemon", boom)
    ctx = agent.RequestContext(request_id="r", deadline_at=float("inf"))
    ctx.discovered.add("get_pokemon")

    out = json.loads(agent._run_tool(ctx, "get_pokemon", {"name_or_id": "pikachu"}))

    assert out == {"error": "http_budget_exceeded"}
    assert ctx.budget_exhausted and ctx.sources == []


def test_agente_404_da_pokeapi_vira_not_found(monkeypatch):
    def missing(name_or_id):
        raise pokeapi.NotFound("pokemon/xyz")

    monkeypatch.setattr(tools, "get_pokemon", missing)
    ctx = agent.RequestContext(request_id="r", deadline_at=float("inf"))
    ctx.discovered.add("get_pokemon")

    out = json.loads(agent._run_tool(ctx, "get_pokemon", {"name_or_id": "xyz"}))

    assert out["error"] == "not_found"
    jsonschema.validate(out, catalog.ERROR_OUTPUT)  # erro segue o contrato publicado


def test_todo_codigo_de_erro_do_agente_esta_no_contrato():
    import inspect

    source = inspect.getsource(agent)
    emitted = set(agent._POKEAPI_ERRORS.values()) | set(re.findall(r'"error": "(\w+)"', source))
    emitted |= {"ToolNotFound", "ToolDisabled"}  # via type(exc).__name__
    assert emitted <= set(catalog.ERROR_CODES)


def test_profile_lido_do_env_file(monkeypatch):
    # Sem variável exportada, vale o valor do .env (carregado no Settings).
    monkeypatch.delenv("POKEGARDEN_TOOLS_PROFILE", raising=False)
    monkeypatch.setattr(catalog.settings, "pokegarden_tools_profile", "A")
    names = {t["name"] for t in catalog.list_enabled()}
    assert "get_evolution_chain" not in names


def test_busca_por_tokens_ignora_acento_e_palavras_curtas():
    assert [t["name"] for t in catalog.search_tools("informações sobre Pikachu", profile="B")] == ["get_pokemon"]
    assert [t["name"] for t in catalog.search_tools("Evolução do Eevee", profile="B")] == ["get_evolution_chain"]
    assert catalog.search_tools("Evolução do Eevee", profile="A") == []
    # ordena por nº de tokens casados; empate por nome
    assert catalog.search_tools("fraqueza tipo", profile="B")[0]["name"] == "get_type_matchups"
