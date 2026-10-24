"""Catálogo e descoberta de tools (requisito 3.3), em memória e sem LLM.

- ``ToolCatalog`` guarda só contratos (``ToolManifest``) por nome: descoberta
  lexical determinística e habilitação em memória. Não guarda código.
- ``execute_tool`` liga o nome a um handler de ``HANDLERS`` (lista explícita) e
  aplica o gating em código: existe → habilitada → descoberta → args válidos.
- Perfis A/B definem o ``enabled`` inicial; o catálogo é criado uma vez por perfil.
  O estado por requisição (tools descobertas) vive no ``RequestContext`` do agente.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Callable
from functools import cache

import jsonschema

import tools
from config import settings
from models import ToolManifest


class ToolNotFound(Exception):
    """Tool inexistente no catálogo."""


class ToolDisabled(Exception):
    """Tool desabilitada, não descoberta ou sem handler autorizado."""


class ToolArgsInvalid(Exception):
    """Argumentos não satisfazem o input_schema da tool."""


class ToolAlreadyRegistered(Exception):
    """Já existe tool com esse nome (registro nunca sobrescreve)."""


def _normalize(text: str) -> str:
    """Minúsculas e sem acentos ("Evolução" → "evolucao")."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Tokens curtos ("de", "o", "um") casariam com quase tudo.
_MIN_TOKEN_LEN = 3


class ToolCatalog:
    """Manifestos de tools em memória, indexados por nome."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolManifest] = {}

    def register(self, manifest: ToolManifest) -> None:
        """Registra uma tool já validada pelo Pydantic; rejeita nome duplicado."""
        if manifest.name in self._tools:
            raise ToolAlreadyRegistered(manifest.name)
        self._tools[manifest.name] = manifest

    def get(self, name: str) -> ToolManifest:
        """Manifesto pelo nome, habilitado ou não (ToolNotFound se não existe)."""
        if name not in self._tools:
            raise ToolNotFound(name)
        return self._tools[name]

    def list_enabled(self) -> list[ToolManifest]:
        """Tools habilitadas, ordenadas por nome."""
        return [m for _, m in sorted(self._tools.items()) if m.enabled]

    def search_tools(self, query: str) -> list[ToolManifest]:
        """Busca lexical por tokens em nome, descrição e tags das habilitadas.

        Case/acento-insensitive; uma tool casa se algum token da consulta (com
        3+ caracteres) for substring do seu texto. Ordena por nº de tokens
        casados (desc) e depois por nome. Consulta sem tokens retorna todas.
        """
        tokens = [t for t in re.findall(r"\w+", _normalize(query or "")) if len(t) >= _MIN_TOKEN_LEN]
        enabled = self.list_enabled()
        if not tokens:
            return enabled
        scored = []
        for m in enabled:
            text = _normalize(f"{m.name} {m.description} {' '.join(m.tags)}")
            hits = sum(t in text for t in tokens)
            if hits:
                scored.append((-hits, m.name, m))
        return [m for *_, m in sorted(scored, key=lambda x: x[:2])]

    def get_tool_schema(self, name: str) -> ToolManifest:
        """Contrato de uma tool habilitada (ToolNotFound / ToolDisabled)."""
        manifest = self.get(name)
        if not manifest.enabled:
            raise ToolDisabled(name)
        return manifest

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Habilita/desabilita em memória; vale já na próxima consulta."""
        self.get(name).enabled = enabled


# --------------------------------------------------------------------------- #
# Tools de domínio: contratos, handlers autorizados e perfis
# --------------------------------------------------------------------------- #
def _list_of_strings(min_items: int, max_items: int) -> dict:
    return {
        "type": "array",
        "items": {"type": "string"},
        "minItems": min_items,
        "maxItems": max_items,
    }


def _input(field: str, spec: dict) -> dict:
    return {"type": "object", "properties": {field: spec}, "required": [field]}


_NAME_OR_ID = _input("name_or_id", {"type": ["string", "integer"]})
_STRINGS = {"type": "array", "items": {"type": "string"}}
_OBJECT = {"type": "object"}

# Erros que o executor do agente (``agent._run_tool``) devolve no lugar do resultado.
ERROR_CODES = [
    "ToolNotFound",
    "ToolDisabled",
    "ToolArgsInvalid",  # catálogo / gating
    "not_found",
    "invalid_argument",
    "invalid_response",
    "upstream_unavailable",  # PokéAPI
    "deadline_exceeded",
    "tool_call_budget_exceeded",
    "http_budget_exceeded",  # orçamento
    "tool_execution_failed",  # falha inesperada
]
ERROR_OUTPUT = {
    "type": "object",
    "properties": {"error": {"enum": ERROR_CODES}, "detail": {"type": "string"}},
    "required": ["error"],
}
_SOURCES = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "collected_at": {"type": "string"},
            "source": {"enum": ["live", "cache"]},
        },
        "required": ["url", "collected_at", "source"],
    },
}


def _output(**fields: dict) -> dict:
    """Contrato de saída: sucesso (campos + ``sources``/``warnings``) OU erro."""
    success = {
        "type": "object",
        "properties": {**fields, "sources": _SOURCES, "warnings": _STRINGS},
        "required": [*fields, "sources", "warnings"],
    }
    return {"oneOf": [success, ERROR_OUTPUT]}


MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        name="get_pokemon",
        description="Dados normalizados de um Pokémon por nome ou id, com proveniência.",
        tags=["pokemon", "stats", "lookup", "species", "dados", "informações", "tipos", "habilidades", "atributos"],
        input_schema=_NAME_OR_ID,
        output_schema=_output(
            id={"type": "integer"},
            name={"type": "string"},
            types=_STRINGS,
            abilities=_STRINGS,
            height={"type": "integer"},
            weight={"type": "integer"},  # decímetros / hectogramas
            height_m={"type": "number"},
            weight_kg={"type": "number"},
            stats={"type": "object", "additionalProperties": {"type": "integer"}},
            units=_OBJECT,
        ),
    ),
    ToolManifest(
        name="compare_pokemon",
        description="Compara de 2 a 6 Pokémon por tipos e base stats.",
        tags=["pokemon", "compare", "stats", "comparar", "comparação"],
        input_schema=_input("names", _list_of_strings(2, 6)),
        output_schema=_output(
            pokemon={"type": "array", "items": _OBJECT},
            stat_comparison=_OBJECT,
            totals=_OBJECT,
            total_leaders=_STRINGS,
            total_tie={"type": "boolean"},
            criterion={"type": "string"},
        ),
    ),
    ToolManifest(
        name="get_type_matchups",
        description="Relações defensivas (fraquezas, resistências, imunidades) de um ou dois tipos.",
        tags=["type", "matchup", "weakness", "resistance", "tipo", "fraqueza", "resistência", "imunidade", "vantagem"],
        input_schema=_input("types", _list_of_strings(1, 2)),
        output_schema=_output(
            defending_types=_STRINGS,
            weaknesses={"type": "object", "additionalProperties": {"type": "number"}},
            resistances={"type": "object", "additionalProperties": {"type": "number"}},
            immunities={"type": "object", "additionalProperties": {"type": "number"}},
        ),
    ),
    ToolManifest(
        name="get_evolution_chain",
        description="Árvore de evolução com ramos e condições para um Pokémon.",
        tags=["pokemon", "evolution", "chain", "evolve", "evolução", "evoluir"],
        input_schema=_NAME_OR_ID,
        output_schema=_output(chain=_OBJECT),
    ),
]

# Única lista de código executável. Lambdas resolvem ``tools.<fn>`` na chamada
# (mantém monkeypatch de testes funcionando).
HANDLERS: dict[str, Callable[..., dict]] = {
    "get_pokemon": lambda **kw: tools.get_pokemon(**kw),
    "compare_pokemon": lambda **kw: tools.compare_pokemon(**kw),
    "get_type_matchups": lambda **kw: tools.get_type_matchups(**kw),
    "get_evolution_chain": lambda **kw: tools.get_evolution_chain(**kw),
}

PROFILES: dict[str, set[str]] = {
    "A": {"get_pokemon", "compare_pokemon", "get_type_matchups"},
    "B": {"get_pokemon", "compare_pokemon", "get_type_matchups", "get_evolution_chain"},
}


def _resolve_profile(profile: str | None) -> str:
    """Parâmetro > env ``POKEGARDEN_TOOLS_PROFILE`` > ``.env`` > ``B``."""
    name = (profile or os.getenv("POKEGARDEN_TOOLS_PROFILE") or settings.pokegarden_tools_profile).strip().upper()
    if name not in PROFILES:
        raise ValueError(f"Perfil de tools desconhecido: {name!r}")
    return name


def build_catalog(profile: str | None = None) -> ToolCatalog:
    """Novo catálogo com as tools de domínio e ``enabled`` conforme o perfil."""
    enabled = PROFILES[_resolve_profile(profile)]
    catalog = ToolCatalog()
    for manifest in MANIFESTS:
        catalog.register(
            manifest.model_copy(deep=True, update={"enabled": manifest.name in enabled})
        )
    return catalog


@cache
def _catalog_for(profile_name: str) -> ToolCatalog:
    return build_catalog(profile_name)


def get_catalog(profile: str | None = None) -> ToolCatalog:
    """Catálogo da aplicação: um por perfil, criado uma única vez."""
    return _catalog_for(_resolve_profile(profile))


# --------------------------------------------------------------------------- #
# API usada por agent/main (retorna dicts)
# --------------------------------------------------------------------------- #
def list_enabled(profile: str | None = None) -> list[dict]:
    return [m.model_dump() for m in get_catalog(profile).list_enabled()]


def search_tools(query: str, profile: str | None = None) -> list[dict]:
    return [m.model_dump() for m in get_catalog(profile).search_tools(query)]


def get_tool_schema(name: str, profile: str | None = None) -> dict:
    return get_catalog(profile).get_tool_schema(name).model_dump()


def execute_tool(
    name: str,
    args: dict,
    discovered: set[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Executa uma tool só se existir, estiver habilitada, tiver sido descoberta
    nesta requisição (quando ``discovered`` é dado), tiver handler autorizado e
    receber args válidos pelo ``input_schema``."""
    manifest = get_catalog(profile).get(name)
    if not manifest.enabled or (discovered is not None and name not in discovered):
        raise ToolDisabled(name)
    handler = HANDLERS.get(name)
    if handler is None:
        raise ToolDisabled(f"{name}: sem handler autorizado")
    try:
        jsonschema.validate(args, manifest.input_schema)
    except jsonschema.ValidationError as exc:
        raise ToolArgsInvalid(exc.message) from None
    return handler(**args)
