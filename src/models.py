"""Modelos de dados compartilhados (stub de contrato — implementado por add-pokeapi-client)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Um JSON Schema é um documento JSON aninhado de forma arbitrária (properties,
# items, required, ...). Modelá-lo campo a campo não agrega valor e engessaria o
# contrato, então o alias usa ``Any`` de forma deliberada e localizada — a única
# ocorrência no projeto — e não como atalho para evitar tipagem.
JsonSchema = dict[str, Any]


class Provenance(BaseModel):
    """Proveniência de um dado coletado."""

    url: str
    collected_at: str  # ISO-8601
    source: Literal["live", "cache"]


class Pokemon(BaseModel):
    """Pokémon normalizado. Unidades: height em decímetros, weight em hectogramas."""

    id: int
    name: str
    types: list[str]
    abilities: list[str]
    height: int
    weight: int
    stats: dict[str, int]  # hp, attack, defense, special-attack, special-defense, speed
    provenance: Provenance


class ToolManifest(BaseModel):
    """Contrato declarativo de uma tool, exposto pela descoberta (requisito 3.3).

    Guarda apenas METADADOS/contrato — nunca o código executável da tool (a
    implementação real vive em ``tools`` e é ligada pelo executor). ``enabled``
    define se a tool pode ser descoberta e executada; ``input_schema`` e
    ``output_schema`` são JSON Schema (incl. o contrato de erros no output).
    """

    name: str = Field(min_length=1)
    version: str = "1.0"
    description: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    input_schema: JsonSchema = Field(default_factory=lambda: {"type": "object"})
    output_schema: JsonSchema = Field(default_factory=lambda: {"type": "object"})
    enabled: bool = True
