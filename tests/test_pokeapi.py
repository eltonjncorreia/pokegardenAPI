"""Testes offline do cliente da PokéAPI (sem rede, sem chave OpenAI)."""

from __future__ import annotations

import importlib
import json

import pytest
import requests

import pokeapi
from config import settings


# --------------------------------------------------------------------------- #
# Fakes / fixtures
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, raise_json=False):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("JSON inválido")
        return self._json_data


def _pokemon_payload(poke_id=25, name="pikachu"):
    return {
        "id": poke_id,
        "name": name,
        "height": 4,
        "weight": 60,
        "types": [{"type": {"name": "electric"}}],
        "abilities": [{"ability": {"name": "static"}}],
        "stats": [
            {"stat": {"name": "hp"}, "base_stat": 35},
            {"stat": {"name": "attack"}, "base_stat": 55},
            {"stat": {"name": "defense"}, "base_stat": 40},
            {"stat": {"name": "special-attack"}, "base_stat": 50},
            {"stat": {"name": "special-defense"}, "base_stat": 50},
            {"stat": {"name": "speed"}, "base_stat": 90},
        ],
    }


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """Cache em tmp_path, base fixa e sem espera real de backoff."""
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(settings, "pokeapi_base_url", "https://pokeapi.co/api/v2")
    monkeypatch.setattr(settings, "cache_ttl_seconds", 86400)
    monkeypatch.setattr(pokeapi.time, "sleep", lambda *_a, **_k: None)


class Recorder:
    """Registra chamadas e devolve respostas programadas."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, timeout=None, allow_redirects=None):
        self.calls.append(url)
        item = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def _patch_get(monkeypatch, responses):
    rec = Recorder(responses)
    monkeypatch.setattr(pokeapi.requests, "get", rec)
    return rec


# --------------------------------------------------------------------------- #
# E01 — nome == id
# --------------------------------------------------------------------------- #
def test_name_and_id_equivalent(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])

    by_name = pokeapi.get_pokemon("  Pikachu ")
    by_id = pokeapi.get_pokemon(25)

    assert by_name.id == by_id.id == 25
    assert by_name.name == by_id.name == "pikachu"
    assert by_name.stats["speed"] == 90
    # Entrada normalizada: nome com espaços/maiúsculas vira "pokemon/pikachu".
    assert rec.calls[0].endswith("/pokemon/pikachu")
    # Por ID reaproveita o cache gravado pelo nome: um único GET, mesma coleta.
    assert len(rec.calls) == 1
    assert by_id.provenance.source == "cache"
    assert by_id.provenance.collected_at == by_name.provenance.collected_at


def test_logs_mostram_miss_write_e_hit(monkeypatch):
    _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])
    events = []
    monkeypatch.setattr(pokeapi, "log_event", lambda event, *_a, **f: events.append((event, f)))

    pokeapi.get_pokemon("pikachu")
    pokeapi.get_pokemon("pikachu")

    names = [e for e, _ in events]
    assert names == ["cache.miss", "http.request", "cache.write", "cache.write", "cache.hit"]
    assert events[0][1]["reason"] == "absent"
    assert events[1][1]["status"] == 200
    assert {events[2][1]["key"], events[3][1]["key"]} == {"pokemon/pikachu", "pokemon/25"}
    assert events[4][1]["key"] == "pokemon/pikachu"


def test_log_cache_expirado(monkeypatch):
    _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])
    pokeapi.get_pokemon("pikachu")
    monkeypatch.setattr(settings, "cache_ttl_seconds", -1)
    events = []
    monkeypatch.setattr(pokeapi, "log_event", lambda event, *_a, **f: events.append((event, f)))

    assert pokeapi.get_pokemon("pikachu").provenance.source == "live"
    assert events[0][0] == "cache.miss" and events[0][1]["reason"] == "expired"


# --------------------------------------------------------------------------- #
# E02 — cache hit dentro do TTL + persistência após reinício
# --------------------------------------------------------------------------- #
def test_cache_hit_no_network_and_persists(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])

    first = pokeapi.get_pokemon("pikachu")
    assert first.provenance.source == "live"
    assert len(rec.calls) == 1

    # Segunda chamada: cache hit, sem rede, preserva collected_at.
    def _boom(*_a, **_k):
        raise AssertionError("não deveria ir à rede em cache hit")

    monkeypatch.setattr(pokeapi.requests, "get", _boom)
    second = pokeapi.get_pokemon("pikachu")
    assert second.provenance.source == "cache"
    assert second.provenance.collected_at == first.provenance.collected_at

    # "Reinício": recria o módulo; o cache em disco deve persistir.
    reloaded = importlib.reload(pokeapi)
    monkeypatch.setattr(reloaded.requests, "get", _boom)
    monkeypatch.setattr(reloaded.time, "sleep", lambda *_a, **_k: None)
    third = reloaded.get_pokemon("pikachu")
    assert third.provenance.source == "cache"
    assert third.provenance.collected_at == first.provenance.collected_at


# --------------------------------------------------------------------------- #
# Erros
# --------------------------------------------------------------------------- #
def test_404_no_retry(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(404)])
    with pytest.raises(pokeapi.NotFound):
        pokeapi.get_pokemon("missingno")
    assert len(rec.calls) == 1  # sem retry


def test_5xx_retries_limited(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(503) for _ in range(5)])
    with pytest.raises(pokeapi.UpstreamUnavailable):
        pokeapi.get_pokemon("pikachu")
    assert len(rec.calls) == pokeapi.MAX_ATTEMPTS


def test_429_retry_after_then_success(monkeypatch):
    rec = _patch_get(
        monkeypatch,
        [
            FakeResponse(429, headers={"Retry-After": "1"}),
            FakeResponse(200, _pokemon_payload()),
        ],
    )
    result = pokeapi.get_pokemon("pikachu")
    assert result.id == 25
    assert len(rec.calls) == 2


def test_timeout_retries(monkeypatch):
    rec = _patch_get(monkeypatch, [requests.exceptions.Timeout()])
    with pytest.raises(pokeapi.UpstreamUnavailable):
        pokeapi.get_pokemon("pikachu")
    assert len(rec.calls) == pokeapi.MAX_ATTEMPTS


def test_invalid_json(monkeypatch):
    _patch_get(monkeypatch, [FakeResponse(200, raise_json=True)])
    with pytest.raises(pokeapi.InvalidResponse):
        pokeapi.get_pokemon("pikachu")


def test_unexpected_contract(monkeypatch):
    _patch_get(monkeypatch, [FakeResponse(200, {"id": 1})])  # faltam campos
    with pytest.raises(pokeapi.InvalidResponse):
        pokeapi.get_pokemon("pikachu")


# --------------------------------------------------------------------------- #
# Segurança — origem restrita
# --------------------------------------------------------------------------- #
def test_arbitrary_url_rejected_before_network(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])
    with pytest.raises(pokeapi.InvalidArgument):
        pokeapi.get_resource("https://evil.example.com/steal")
    assert rec.calls == []  # nenhuma rede


def test_redirect_out_of_origin_blocked(monkeypatch):
    _patch_get(
        monkeypatch,
        [FakeResponse(302, headers={"Location": "https://evil.example.com/x"})],
    )
    with pytest.raises(pokeapi.InvalidArgument):
        pokeapi.get_resource("type/electric")


def test_resource_cache_and_provenance(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(200, {"name": "electric"})])
    payload, prov = pokeapi.get_resource("type/electric")
    assert payload["name"] == "electric"
    assert prov.source == "live"
    assert prov.url.endswith("/type/electric")

    payload2, prov2 = pokeapi.get_resource("type/electric")
    assert prov2.source == "cache"
    assert len(rec.calls) == 1
    assert prov2.collected_at == prov.collected_at


# --------------------------------------------------------------------------- #
# Orçamento de requisições HTTP por requisição (inclui retries)
# --------------------------------------------------------------------------- #
def test_http_budget_conta_retries(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(503), FakeResponse(503), FakeResponse(200, _pokemon_payload())])
    with pokeapi.http_budget(2), pytest.raises(pokeapi.HttpBudgetExceeded):
        pokeapi.get_pokemon("pikachu")
    assert len(rec.calls) == 2  # a 3ª tentativa não foi à rede


def test_http_budget_cache_hit_nao_conta(monkeypatch):
    _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])
    pokeapi.get_pokemon("pikachu")  # popula o cache, fora do orçamento
    with pokeapi.http_budget(0):
        assert pokeapi.get_pokemon("pikachu").provenance.source == "cache"


def test_http_budget_sem_limite_fora_do_bloco(monkeypatch):
    rec = _patch_get(monkeypatch, [FakeResponse(200, _pokemon_payload())])
    with pokeapi.http_budget(1):
        pass
    pokeapi.get_pokemon("pikachu")
    assert len(rec.calls) == 1
