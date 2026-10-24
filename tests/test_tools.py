"""Testes offline das tools de domínio (sem rede/chave).

O cliente pokeapi é simulado via monkeypatch; dados vêm de fixtures inline.
Cobre E01, E03 (matemática), E04 (tipo duplo + imunidade), E05 (ramos do Eevee)
e E06 (inexistente / lista inválida).
"""

import pytest

import pokeapi, tools
from models import Pokemon, Provenance


def _prov(url: str, source: str = "cache") -> Provenance:
    return Provenance(url=url, collected_at="2026-01-01T00:00:00Z", source=source)


def _pokemon(id: int, name: str, types, stats, source="cache") -> Pokemon:
    return Pokemon(
        id=id,
        name=name,
        types=types,
        abilities=["ability-x"],
        height=10,
        weight=100,
        stats=stats,
        provenance=_prov(f"https://pokeapi.co/api/v2/pokemon/{id}", source),
    )


PIKACHU = _pokemon(
    25,
    "pikachu",
    ["electric"],
    {
        "hp": 35,
        "attack": 55,
        "defense": 40,
        "special-attack": 50,
        "special-defense": 50,
        "speed": 90,
    },
)

CHARIZARD = _pokemon(
    6,
    "charizard",
    ["fire", "flying"],
    {
        "hp": 78,
        "attack": 84,
        "defense": 78,
        "special-attack": 109,
        "special-defense": 85,
        "speed": 100,
    },
)

BLASTOISE = _pokemon(
    9,
    "blastoise",
    ["water"],
    {
        "hp": 79,
        "attack": 83,
        "defense": 100,
        "special-attack": 85,
        "special-defense": 105,
        "speed": 78,
    },
)


# --------------------------------------------------------------------------- #
# E01 - get_pokemon: nome == id
# --------------------------------------------------------------------------- #
def test_get_pokemon_name_equals_id(monkeypatch):
    calls = []

    def fake_get(identifier):
        calls.append(identifier)
        return PIKACHU

    monkeypatch.setattr(pokeapi, "get_pokemon", fake_get)

    by_name = tools.get_pokemon("  Pikachu ")
    by_id = tools.get_pokemon(25)

    assert by_name["id"] == by_id["id"] == 25
    assert by_name["name"] == by_id["name"] == "pikachu"
    # normalização: trim + minúsculas
    assert calls == ["pikachu", 25]
    # proveniência vinda do runtime
    assert by_name["sources"][0]["source"] == "cache"
    assert by_name["sources"][0]["url"].endswith("/pokemon/25")
    assert by_name["units"] == {
        "height": "decímetros",
        "weight": "hectogramas",
        "height_m": "metros",
        "weight_kg": "quilogramas",
    }
    # conversão feita em código (fixture): 10 dm → 1.0 m, 100 hg → 10.0 kg
    assert by_name["height_m"] == 1.0
    assert by_name["weight_kg"] == 10.0


def test_get_pokemon_invalid_input(monkeypatch):
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: PIKACHU)
    with pytest.raises(pokeapi.InvalidArgument):
        tools.get_pokemon("   ")
    with pytest.raises(pokeapi.InvalidArgument):
        tools.get_pokemon(0)
    with pytest.raises(pokeapi.InvalidArgument):
        tools.get_pokemon(None)


# --------------------------------------------------------------------------- #
# E03 - compare_pokemon: matemática e critério explícito
# --------------------------------------------------------------------------- #
def test_compare_charizard_vs_blastoise(monkeypatch):
    lookup = {"charizard": CHARIZARD, "blastoise": BLASTOISE}
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: lookup[i])

    result = tools.compare_pokemon(["Charizard", "blastoise"])

    # totais calculados em código
    assert result["totals"]["charizard"] == 534
    assert result["totals"]["blastoise"] == 530
    assert result["total_leaders"] == ["charizard"]
    assert result["total_tie"] is False

    # diferença por stat
    defense = result["stat_comparison"]["defense"]
    assert defense["values"] == {"charizard": 78, "blastoise": 100}
    assert defense["diff"] == 22
    assert defense["leaders"] == ["blastoise"]
    assert defense["tie"] is False

    # critério e disclaimer explícitos
    assert "base stats" in result["criterion"]
    assert any("batalha" in w for w in result["warnings"])
    assert len(result["sources"]) == 2


def test_compare_declares_tie_and_missing(monkeypatch):
    a = _pokemon(1, "a", ["normal"], {"hp": 50, "attack": 50})
    b = _pokemon(2, "b", ["normal"], {"hp": 50})  # attack ausente
    lookup = {"a": a, "b": b}
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: lookup[i])

    result = tools.compare_pokemon(["a", "b"])

    hp = result["stat_comparison"]["hp"]
    assert hp["tie"] is True
    assert sorted(hp["leaders"]) == ["a", "b"]

    attack = result["stat_comparison"]["attack"]
    assert attack["values"] == {"a": 50, "b": None}
    assert attack["missing"] == ["b"]
    # ausência não vira 0 na comparação: só "a" presente
    assert attack["max"] == 50 and attack["diff"] == 0


def test_compare_list_out_of_range(monkeypatch):
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: PIKACHU)
    with pytest.raises(pokeapi.InvalidArgument):
        tools.compare_pokemon(["pikachu"])
    with pytest.raises(pokeapi.InvalidArgument):
        tools.compare_pokemon(["a", "b", "c", "d", "e", "f", "g"])


# --------------------------------------------------------------------------- #
# E04 - get_type_matchups: tipo duplo + imunidade
# --------------------------------------------------------------------------- #
# Fixtures parciais das relações defensivas (apenas o necessário para o teste).
TYPE_RELATIONS = {
    "fire": {
        "damage_relations": {
            "double_damage_from": [{"name": "water"}, {"name": "rock"}, {"name": "ground"}],
            "half_damage_from": [{"name": "fire"}, {"name": "grass"}, {"name": "bug"}],
            "no_damage_from": [],
        }
    },
    "flying": {
        "damage_relations": {
            "double_damage_from": [{"name": "rock"}, {"name": "electric"}, {"name": "ice"}],
            "half_damage_from": [{"name": "grass"}, {"name": "bug"}, {"name": "fighting"}],
            "no_damage_from": [{"name": "ground"}],
        }
    },
}


def test_type_matchups_dual_with_immunity(monkeypatch):
    def fake_resource(path):
        type_name = path.split("/")[1]
        return TYPE_RELATIONS[type_name], _prov(f"https://pokeapi.co/api/v2/{path}")

    monkeypatch.setattr(pokeapi, "get_resource", fake_resource)

    result = tools.get_type_matchups(["Fire", "flying"])

    # ground: fire x2 * flying x0 = 0 -> imunidade (combinada em código)
    assert result["immunities"]["ground"] == 0.0
    # rock: x2 * x2 = 4 -> fraqueza dupla
    assert result["weaknesses"]["rock"] == 4.0
    # water: x2 * x1 = 2 -> fraqueza
    assert result["weaknesses"]["water"] == 2.0
    # grass: x0.5 * x0.5 = 0.25 -> resistência
    assert result["resistances"]["grass"] == 0.25
    # imunidade listada à parte de fraquezas/resistências
    assert "ground" not in result["weaknesses"]
    assert "ground" not in result["resistances"]
    assert any("STAB" in w for w in result["warnings"])
    assert len(result["sources"]) == 2


def test_type_matchups_invalid_count(monkeypatch):
    monkeypatch.setattr(pokeapi, "get_resource", lambda p: ({}, _prov("x")))
    with pytest.raises(pokeapi.InvalidArgument):
        tools.get_type_matchups([])
    with pytest.raises(pokeapi.InvalidArgument):
        tools.get_type_matchups(["fire", "water", "grass"])


def test_type_matchups_nonexistent_type(monkeypatch):
    def fake_resource(path):
        raise pokeapi.NotFound(path)

    monkeypatch.setattr(pokeapi, "get_resource", fake_resource)
    with pytest.raises(pokeapi.NotFound):
        tools.get_type_matchups(["notatype"])


# --------------------------------------------------------------------------- #
# E05 - get_evolution_chain: ramos do Eevee preservados
# --------------------------------------------------------------------------- #
EEVEE_CHAIN = {
    "chain": {
        "species": {"name": "eevee"},
        "evolution_details": [],
        "evolves_to": [
            {
                "species": {"name": "vaporeon"},
                "evolution_details": [
                    {
                        "trigger": {"name": "use-item"},
                        "item": {"name": "water-stone"},
                        "min_level": None,
                        "min_happiness": None,
                        "time_of_day": "",
                    }
                ],
                "evolves_to": [],
            },
            {
                "species": {"name": "espeon"},
                "evolution_details": [
                    {
                        "trigger": {"name": "level-up"},
                        "item": None,
                        "min_level": None,
                        "min_happiness": 160,
                        "time_of_day": "day",
                    }
                ],
                "evolves_to": [],
            },
        ],
    }
}


def _species(chain_id):
    """Payload mínimo de pokemon-species apontando para a cadeia ``chain_id``."""
    return {"evolution_chain": {"url": f"https://pokeapi.co/api/v2/evolution-chain/{chain_id}/"}}


def test_evolution_chain_branches_preserved(monkeypatch):
    calls = []

    def fake_resource(path):
        calls.append(path)
        payload = _species(67) if path.startswith("pokemon-species") else EEVEE_CHAIN
        return payload, _prov(f"https://pokeapi.co/api/v2/{path}")

    monkeypatch.setattr(pokeapi, "get_resource", fake_resource)

    result = tools.get_evolution_chain("Eevee")
    # evolution-chain só aceita id: o nome é resolvido via pokemon-species
    assert calls == ["pokemon-species/eevee", "evolution-chain/67"]
    root = result["chain"]

    assert root["species"] == "eevee"
    # ramos paralelos NÃO linearizados
    assert len(root["evolves_to"]) == 2
    names = [c["species"] for c in root["evolves_to"]]
    assert sorted(names) == ["espeon", "vaporeon"]

    vaporeon = next(c for c in root["evolves_to"] if c["species"] == "vaporeon")
    cond = vaporeon["conditions"][0]
    assert cond["trigger"] == "use-item"
    assert cond["item"] == "water-stone"
    # condições ausentes preservadas como None (não inventadas)
    assert cond["min_level"] is None
    assert cond["time_of_day"] is None

    espeon = next(c for c in root["evolves_to"] if c["species"] == "espeon")
    assert espeon["conditions"][0]["min_happiness"] == 160
    assert espeon["conditions"][0]["min_level"] is None
    assert len(result["sources"]) == 2


def test_evolution_chain_species_sem_cadeia(monkeypatch):
    monkeypatch.setattr(pokeapi, "get_resource", lambda p: ({}, _prov("x")))
    with pytest.raises(pokeapi.InvalidResponse):
        tools.get_evolution_chain("missingno")


def test_evolution_chain_linear(monkeypatch):
    linear = {
        "chain": {
            "species": {"name": "charmander"},
            "evolution_details": [],
            "evolves_to": [
                {
                    "species": {"name": "charmeleon"},
                    "evolution_details": [
                        {"trigger": {"name": "level-up"}, "min_level": 16}
                    ],
                    "evolves_to": [
                        {
                            "species": {"name": "charizard"},
                            "evolution_details": [
                                {"trigger": {"name": "level-up"}, "min_level": 36}
                            ],
                            "evolves_to": [],
                        }
                    ],
                }
            ],
        }
    }
    monkeypatch.setattr(
        pokeapi, "get_resource", lambda p: (_species(2) if p.startswith("pokemon-species") else linear, _prov("x"))
    )
    result = tools.get_evolution_chain("charmander")
    root = result["chain"]
    stage2 = root["evolves_to"][0]
    assert stage2["species"] == "charmeleon"
    assert stage2["conditions"][0]["min_level"] == 16
    assert stage2["evolves_to"][0]["species"] == "charizard"
    assert stage2["evolves_to"][0]["conditions"][0]["min_level"] == 36


# --------------------------------------------------------------------------- #
# E06 - erros distinguíveis: inexistente / lista inválida
# --------------------------------------------------------------------------- #
def test_get_pokemon_not_found(monkeypatch):
    def fake_get(identifier):
        raise pokeapi.NotFound(identifier)

    monkeypatch.setattr(pokeapi, "get_pokemon", fake_get)
    with pytest.raises(pokeapi.NotFound):
        tools.get_pokemon("missingno")


def test_compare_invalid_item_in_list(monkeypatch):
    def fake_get(identifier):
        if identifier == "charizard":
            return CHARIZARD
        raise pokeapi.NotFound(identifier)

    monkeypatch.setattr(pokeapi, "get_pokemon", fake_get)
    # item inválido na lista -> erro distinguível, sem fabricar dados
    with pytest.raises(pokeapi.NotFound):
        tools.compare_pokemon(["charizard", "notapokemon"])


def test_compare_not_a_list(monkeypatch):
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: CHARIZARD)
    with pytest.raises(pokeapi.InvalidArgument):
        tools.compare_pokemon("charizard")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Saídas reais das tools respeitam o output_schema publicado no catálogo
# --------------------------------------------------------------------------- #
def test_saidas_reais_respeitam_output_schema(monkeypatch):
    import jsonschema

    import catalog

    def fake_resource(path):
        if path.startswith("pokemon-species"):
            payload = _species(67)
        elif path.startswith("evolution-chain"):
            payload = EEVEE_CHAIN
        else:
            payload = TYPE_RELATIONS[path.split("/")[1]]
        return payload, _prov(f"https://pokeapi.co/api/v2/{path}")

    lookup = {"pikachu": PIKACHU, "charizard": CHARIZARD}
    monkeypatch.setattr(pokeapi, "get_pokemon", lambda i: lookup[i])
    monkeypatch.setattr(pokeapi, "get_resource", fake_resource)

    outputs = {
        "get_pokemon": tools.get_pokemon("pikachu"),
        "compare_pokemon": tools.compare_pokemon(["pikachu", "charizard"]),
        "get_type_matchups": tools.get_type_matchups(["fire", "flying"]),
        "get_evolution_chain": tools.get_evolution_chain("eevee"),
    }
    for name, output in outputs.items():
        schema = catalog.build_catalog("B").get_tool_schema(name).output_schema
        jsonschema.validate(output, schema)  # levanta se a saída fugir do contrato
