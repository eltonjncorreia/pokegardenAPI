"""Tools de domínio: ponte determinística entre o pokeapi-client e o agente.

Cada tool é uma função que retorna um dict estruturado com:
  - os dados de domínio (chaves específicas de cada tool);
  - ``sources``: list[dict] de proveniência (url / collected_at / source);
  - ``warnings``: list[str] com limitações e fallbacks documentados.

Fatos e metadados vêm do runtime (pokegarden.pokeapi); as tools NÃO fabricam dados.
Cálculos (diferenças, totais, multiplicadores de tipo) são feitos em código.
Erros são repassados como exceções distinguíveis de pokegarden.pokeapi.
"""

import re

import pokeapi
from models import Pokemon, Provenance

# Ordem canônica das seis base stats da PokéAPI.
STAT_KEYS: list[str] = [
    "hp",
    "attack",
    "defense",
    "special-attack",
    "special-defense",
    "speed",
]

# Warning padrão: nomes/tipos ficam no inglês da PokéAPI (sem LLM nas tools).
_LANG_FALLBACK = (
    "Nomes e tipos permanecem no inglês da PokéAPI; nenhuma tradução é gerada "
    "pelas tools. Qualquer tradução deve ser rotulada como 'tradução gerada'."
)


def _provenance_dict(prov: Provenance) -> dict:
    """Serializa a proveniência vinda do runtime (sem fabricar metadados)."""
    return {
        "url": prov.url,
        "collected_at": prov.collected_at,
        "source": prov.source,
    }


def _normalize_identifier(name_or_id: "str | int") -> "str | int":
    """Normaliza um identificador (trim + minúsculas) ou valida o ID numérico.

    Levanta ``pokeapi.InvalidArgument`` para entradas vazias ou de tipo inválido,
    sem ir à rede.
    """
    if isinstance(name_or_id, bool):  # bool é subclasse de int: rejeitar.
        raise pokeapi.InvalidArgument("identificador inválido: booleano")
    if isinstance(name_or_id, int):
        if name_or_id <= 0:
            raise pokeapi.InvalidArgument("ID deve ser um inteiro positivo")
        return name_or_id
    if isinstance(name_or_id, str):
        normalized = name_or_id.strip().lower()
        if not normalized:
            raise pokeapi.InvalidArgument("identificador vazio")
        return normalized
    raise pokeapi.InvalidArgument(
        f"identificador de tipo inválido: {type(name_or_id).__name__}"
    )


def _pokemon_data(pokemon: Pokemon) -> dict:
    """Projeta o Pokémon normalizado nos campos de domínio expostos."""
    return {
        "id": pokemon.id,
        "name": pokemon.name,
        "types": pokemon.types,
        "abilities": pokemon.abilities,
        "height": pokemon.height,
        "weight": pokemon.weight,
        # Conversão em código: o modelo não converte unidades (dm → m, hg → kg).
        "height_m": pokemon.height / 10,
        "weight_kg": pokemon.weight / 10,
        "stats": pokemon.stats,
        "units": {"height": "decímetros", "weight": "hectogramas", "height_m": "metros", "weight_kg": "quilogramas"},
    }


def get_pokemon(name_or_id: "str | int") -> dict:
    """Dados normalizados de um Pokémon + proveniência.

    Aceita nome (case-insensitive, com trim) ou ID numérico positivo; busca por
    nome e por ID equivalentes retornam a mesma entidade (E01). Unidades: height
    em decímetros, weight em hectogramas; height_m/weight_kg já convertidos.
    """
    identifier = _normalize_identifier(name_or_id)
    pokemon = pokeapi.get_pokemon(identifier)
    data = _pokemon_data(pokemon)
    data["sources"] = [_provenance_dict(pokemon.provenance)]
    data["warnings"] = [_LANG_FALLBACK]
    return data


def compare_pokemon(names: list[str]) -> dict:
    """Compara de 2 a 6 Pokémon (tipos e base stats), com cálculo em código.

    Valida o tamanho da lista (2..6) antes de qualquer I/O. Calcula, por stat,
    o valor de cada Pokémon, o maior/menor, empates e totais por Pokémon. Totais
    NÃO são previsão de resultado de batalha.
    """
    if not isinstance(names, list):
        raise pokeapi.InvalidArgument("names deve ser uma lista")
    if not (2 <= len(names) <= 6):
        raise pokeapi.InvalidArgument(
            f"compare_pokemon exige de 2 a 6 Pokémon; recebeu {len(names)}"
        )

    identifiers = [_normalize_identifier(n) for n in names]
    pokemons = [pokeapi.get_pokemon(i) for i in identifiers]

    entries = []
    sources = []
    for pokemon in pokemons:
        entries.append(
            {
                "id": pokemon.id,
                "name": pokemon.name,
                "types": pokemon.types,
                "stats": pokemon.stats,
                "total": sum(pokemon.stats.get(k, 0) for k in STAT_KEYS),
            }
        )
        sources.append(_provenance_dict(pokemon.provenance))

    # Comparação por stat, calculada em código.
    stat_comparison = {}
    for key in STAT_KEYS:
        values = {e["name"]: e["stats"].get(key) for e in entries}
        present = {n: v for n, v in values.items() if v is not None}
        top = max(present.values(), default=None)
        bottom = min(present.values(), default=None)
        leaders = [n for n, v in present.items() if v == top]
        stat_comparison[key] = {
            "values": values,
            "missing": [n for n, v in values.items() if v is None],
            "max": top,
            "min": bottom,
            "diff": top - bottom if present else None,
            "leaders": leaders,
            "tie": bool(present) and (len(leaders) > 1 or top == bottom),
        }

    totals = {e["name"]: e["total"] for e in entries}
    best_total = max(totals.values())
    total_leaders = [n for n, v in totals.items() if v == best_total]

    return {
        "pokemon": entries,
        "stat_comparison": stat_comparison,
        "totals": totals,
        "total_leaders": total_leaders,
        "total_tie": len(total_leaders) > 1,
        "criterion": "soma das seis base stats (hp, attack, defense, "
        "special-attack, special-defense, speed)",
        "sources": sources,
        "warnings": [
            "Os totais de base stats NÃO são previsão de resultado de batalha.",
            _LANG_FALLBACK,
        ],
    }


# Multiplicador por relação de dano (aplicadas nesta ordem; a última vence).
_DAMAGE_FACTORS = {"double_damage_from": 2.0, "half_damage_from": 0.5, "no_damage_from": 0.0}


# Classificação de multiplicadores de dano em categorias defensivas.
def _classify(multiplier: float) -> str:
    if multiplier == 0:
        return "immunities"
    if multiplier < 1:
        return "resistances"
    if multiplier > 1:
        return "weaknesses"
    return "neutral"


def get_type_matchups(types: list[str]) -> dict:
    """Relações defensivas (fraquezas/resistências/imunidades) combinadas em código.

    Aceita 1 ou 2 tipos. Para cada tipo defensor, lê de get_resource('type/<nome>')
    as relações de dano e multiplica os vetores elemento a elemento (tipo duplo).
    Ignora habilidades, itens, clima, golpes e STAB.
    """
    if not isinstance(types, list):
        raise pokeapi.InvalidArgument("types deve ser uma lista")
    if not (1 <= len(types) <= 2):
        raise pokeapi.InvalidArgument(
            f"get_type_matchups exige 1 ou 2 tipos; recebeu {len(types)}"
        )

    defending = [_normalize_identifier(t) for t in types]

    # Multiplicador de cada tipo atacante contra a combinação defensora.
    multipliers: dict[str, float] = {}
    sources = []
    for defender in defending:
        payload, prov = pokeapi.get_resource(f"type/{defender}")
        sources.append(_provenance_dict(prov))
        relations = payload.get("damage_relations", {})
        contributions = {}
        for relation, factor in _DAMAGE_FACTORS.items():
            for entry in relations.get(relation, []):
                contributions[entry["name"]] = factor
        # Tipos atacantes não citados são neutros (x1) para este defensor.
        for attacker, factor in contributions.items():
            multipliers[attacker] = multipliers.get(attacker, 1.0) * factor

    buckets: dict[str, dict[str, float]] = {"weaknesses": {}, "resistances": {}, "immunities": {}, "neutral": {}}
    for attacker, multiplier in sorted(multipliers.items()):
        buckets[_classify(multiplier)][attacker] = multiplier

    return {
        "defending_types": defending,
        "weaknesses": buckets["weaknesses"],
        "resistances": buckets["resistances"],
        "immunities": buckets["immunities"],
        "sources": sources,
        "warnings": [
            "Cálculo defensivo apenas: ignora habilidades, itens, clima, golpes e STAB.",
            _LANG_FALLBACK,
        ],
    }


def _map_evolution_node(node: dict) -> dict:
    """Mapeia recursivamente um nó da cadeia preservando ramos e condições.

    Não lineariza ramos nem inventa níveis/condições; valores ausentes ficam None.
    """
    species = node.get("species") or {}
    children = []
    for child in node.get("evolves_to", []):
        mapped_child = _map_evolution_node(child)
        # Condições da aresta pai -> filho (uma ou mais entradas).
        mapped_child["conditions"] = [
            _map_condition(detail) for detail in child.get("evolution_details", [])
        ]
        children.append(mapped_child)
    return {
        "species": species.get("name"),
        "evolves_to": children,
    }


def _map_condition(detail: dict) -> dict:
    """Extrai condições de evolução preservando ausências como None."""
    trigger = detail.get("trigger") or {}
    item = detail.get("item") or {}
    return {
        "trigger": trigger.get("name"),
        "min_level": detail.get("min_level"),
        "item": item.get("name"),
        "min_happiness": detail.get("min_happiness"),
        "time_of_day": detail.get("time_of_day") or None,
    }


def get_evolution_chain(name_or_id: "str | int") -> dict:
    """Árvore de evolução com ramos e condições, preservando valores ausentes.

    ``evolution-chain/<id>`` só aceita o id da cadeia, então ele é resolvido
    antes via ``pokemon-species/<nome ou id>``. Ramos paralelos (ex.: Eevee)
    viram múltiplos filhos; condições ausentes ficam None, nunca inferidas.
    """
    identifier = _normalize_identifier(name_or_id)
    species, species_prov = pokeapi.get_resource(f"pokemon-species/{identifier}")
    chain_url = (species.get("evolution_chain") or {}).get("url") or ""
    match = re.search(r"/evolution-chain/(\d+)/?$", chain_url)
    if match is None:
        raise pokeapi.InvalidResponse("pokemon-species sem 'evolution_chain' válido")
    payload, prov = pokeapi.get_resource(f"evolution-chain/{match.group(1)}")
    chain = payload.get("chain")
    if chain is None:
        raise pokeapi.InvalidResponse("evolution-chain sem 'chain'")
    tree = _map_evolution_node(chain)
    # A raiz não tem condições de entrada.
    tree["conditions"] = []
    return {
        "chain": tree,
        "sources": [_provenance_dict(species_prov), _provenance_dict(prov)],
        "warnings": [
            "Ramos e condições preservados conforme a origem; ausências não são inferidas.",
            _LANG_FALLBACK,
        ],
    }
