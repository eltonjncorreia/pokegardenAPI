"""PokéAPI falsa servida a partir de ``evals/fixtures/pokeapi`` (offline).

Substitui só o ``requests.get`` usado por ``pokeapi``: cache, validação de
origem, retries, orçamento HTTP e normalização continuam os reais. Cada GET é
registrado para as checagens (ex.: "sem novo GET no cache hit").

Falhas são injetadas por caminho, consumidas em ordem antes da resposta normal:
``503`` (status), ``(429, "2")`` (status + Retry-After), ``"timeout"``,
``"badjson"`` ou ``("redirect", url)``.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pokeapi"
API_PREFIX = "/api/v2/"

Fault = int | str | tuple[int, str] | tuple[str, str]


class FakeResponse:
    """Resposta mínima com a interface que ``pokeapi`` usa."""

    def __init__(self, status_code: int, data: object = None, headers: dict | None = None, bad_json: bool = False) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._data = data
        self._bad_json = bad_json

    def json(self) -> object:
        if self._bad_json:
            raise ValueError("JSON inválido (falha injetada)")
        return self._data


def _load_index(root: Path) -> dict[str, dict]:
    """Indexa as fixtures por ``<recurso>/<name>`` e ``<recurso>/<id>``."""
    index: dict[str, dict] = {}
    for path in root.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        resource = path.parent.name
        index[f"{resource}/{path.stem}"] = data
        if "id" in data:
            index[f"{resource}/{data['id']}"] = data
    return index


class FakePokeApi:
    """``requests.get`` falso: fixtures + falhas injetadas + registro de GETs."""

    def __init__(self, faults: dict[str, list[Fault]] | None = None, root: Path = FIXTURES_DIR) -> None:
        self._index = _load_index(root)
        self._faults = {k: list(v) for k, v in (faults or {}).items()}
        self._lock = threading.Lock()
        self.gets: list[str] = []

    def __call__(self, url: str, timeout: float | None = None, allow_redirects: bool = True, **_: object) -> FakeResponse:
        with self._lock:
            self.gets.append(url)
            parsed = urlparse(url)
            if parsed.netloc != "pokeapi.co":
                # Nunca deveria acontecer: a origem é validada antes da rede.
                return FakeResponse(599, {"error": "host fora da fixture"})
            path = parsed.path.removeprefix(API_PREFIX).strip("/").lower()
            pending = self._faults.get(path)
            fault = pending.pop(0) if pending else None
        if fault is not None:
            return self._fault(fault)
        data = self._index.get(path)
        return FakeResponse(200, data) if data is not None else FakeResponse(404, {"detail": "Not found."})

    def gets_for(self, path: str) -> list[str]:
        """GETs feitos para um caminho (``pokemon/pikachu``)."""
        return [u for u in self.gets if urlparse(u).path.removeprefix(API_PREFIX).strip("/").lower() == path]

    @staticmethod
    def _fault(fault: Fault) -> FakeResponse:
        if fault == "timeout":
            raise requests.exceptions.Timeout("timeout injetado")
        if fault == "badjson":
            return FakeResponse(200, bad_json=True)
        if isinstance(fault, tuple) and fault[0] == "redirect":
            return FakeResponse(302, headers={"Location": fault[1]})
        if isinstance(fault, tuple):
            return FakeResponse(fault[0], {}, headers={"Retry-After": fault[1]})
        return FakeResponse(int(fault), {})
