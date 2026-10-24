"""Cliente HTTP da PokéAPI + cache local em SQLite.

Projeto deliberadamente simples: funções puras + modelos Pydantic. Sem classes
grandes. Toda coleta é restrita ao host de ``settings.pokeapi_base_url``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Generator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from config import settings
from models import Pokemon, Provenance
from obs import log_event

# Política de retry para falhas transitórias (timeout, 5xx, 429).
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5
MAX_BACKOFF_S = 8.0
# Limite de redirects inspecionados (todos validados contra a origem).
MAX_REDIRECTS = 5

_RETRY_STATUS = {429, 500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}


class PokeApiError(Exception):
    """Erro base do cliente."""


class NotFound(PokeApiError):
    """Recurso inexistente (404)."""


class InvalidResponse(PokeApiError):
    """Resposta malformada ou fora do contrato."""


class UpstreamUnavailable(PokeApiError):
    """Falha transitória/indisponibilidade após retries."""


class InvalidArgument(PokeApiError):
    """Argumento inválido (não vai à rede)."""


class HttpBudgetExceeded(PokeApiError):
    """Orçamento de requisições HTTP (incluindo retries) da requisição esgotado."""


# Requisições HTTP restantes na requisição atual (None = sem limite). Lista para
# que threads do Runner (que copiam o contexto) compartilhem o mesmo contador.
_http_budget: ContextVar[list[int] | None] = ContextVar("http_budget", default=None)


@contextmanager
def http_budget(limit: int) -> Generator[None]:
    """Limita as requisições HTTP feitas dentro do bloco (cache hit não conta)."""
    token = _http_budget.set([limit])
    try:
        yield
    finally:
        _http_budget.reset(token)


def http_requests_left() -> int | None:
    """Requisições HTTP restantes no orçamento atual (``None`` = sem limite)."""
    remaining = _http_budget.get()
    return None if remaining is None else remaining[0]


def _ms_since(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _spend_http() -> None:
    remaining = _http_budget.get()
    if remaining is None:
        return
    if remaining[0] <= 0:
        raise HttpBudgetExceeded("orçamento de requisições HTTP esgotado")
    remaining[0] -= 1


class _Retry(Exception):
    """Sinaliza, internamente, que a tentativa deve ser repetida.

    ``retry_after`` (segundos) vem do header em 429; ``None`` usa backoff.
    """

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after


# --------------------------------------------------------------------------- #
# Origem / URLs
# --------------------------------------------------------------------------- #
def _base() -> str:
    """URL base normalizada com barra final (para ``urljoin``)."""
    base = settings.pokeapi_base_url.strip()
    return base if base.endswith("/") else base + "/"


def _allowed_host() -> str:
    """Host permitido, derivado de ``settings.pokeapi_base_url``."""
    return urlparse(_base()).netloc


def _resolve_url(resource_path: str) -> str:
    """Resolve ``resource_path`` contra a base e valida a origem (antes da rede).

    Aceita caminho relativo (ex.: ``'type/electric'``) ou URL absoluta no host
    permitido; levanta :class:`InvalidArgument` para qualquer outra origem.
    """
    candidate = (resource_path or "").strip()
    if not candidate:
        raise InvalidArgument("resource_path vazio")
    parsed = urlparse(candidate)
    if parsed.netloc and (parsed.scheme not in ("http", "https") or parsed.netloc != _allowed_host()):
        raise InvalidArgument(f"URL fora da origem permitida: {candidate}")
    url = urljoin(_base(), candidate.lstrip("/"))
    # Revalida após a junção (defende contra barras/esquemas inesperados).
    if urlparse(url).netloc != _allowed_host():
        raise InvalidArgument(f"URL fora da origem permitida: {url}")
    return url


# --------------------------------------------------------------------------- #
# Cache em SQLite
# --------------------------------------------------------------------------- #
def _connect() -> sqlite3.Connection:
    """Abre a conexão e garante a tabela de cache (chave -> registro)."""
    path = Path(settings.cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path / "pokeapi_cache.sqlite3")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "  key TEXT PRIMARY KEY,"
        "  url TEXT NOT NULL,"
        "  collected_at TEXT NOT NULL,"
        "  payload TEXT NOT NULL)"
    )
    return conn


def _cache_key(resource_path: str) -> str:
    """Chave de cache estável a partir do caminho normalizado do recurso."""
    return resource_path.strip().strip("/").lower() or "root"


def _cache_read(resource_path: str) -> dict | None:
    """Lê um registro de cache válido dentro do TTL, ou ``None``.

    Loga ``cache.hit`` (com idade) ou ``cache.miss`` com o motivo: ``absent``,
    ``expired`` ou ``corrupt``.
    """
    key = _cache_key(resource_path)
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT url, collected_at, payload FROM cache WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        log_event("cache.miss", key=key, reason="absent")
        return None
    url, collected_at, payload = row
    try:
        collected_dt = datetime.fromisoformat(collected_at)
    except ValueError:
        log_event("cache.miss", key=key, reason="corrupt")
        return None
    age = (datetime.now(UTC) - collected_dt).total_seconds()
    if age > settings.cache_ttl_seconds:
        log_event("cache.miss", key=key, reason="expired", age_s=round(age), ttl_s=settings.cache_ttl_seconds)
        return None
    log_event("cache.hit", key=key, url=url, collected_at=collected_at, age_s=round(age))
    return {"url": url, "collected_at": collected_at, "payload": json.loads(payload)}


def _alias_paths(resource_path: str, payload: dict) -> list[str]:
    """Chaves equivalentes (``<recurso>/<id>`` e ``<recurso>/<name>``) do payload."""
    parts = _cache_key(resource_path).split("/")
    if len(parts) != 2:
        return []
    keys = {
        f"{parts[0]}/{str(payload[field]).lower()}"
        for field in ("id", "name")
        if isinstance(payload.get(field), (int, str)) and not isinstance(payload.get(field), bool)
    }
    return sorted(keys - {_cache_key(resource_path)})


def _cache_write(resource_path: str, url: str, collected_at: str, payload: dict) -> None:
    """Grava/atualiza o registro de cache (commit via context manager)."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, url, collected_at, payload) VALUES (?, ?, ?, ?)",
            (
                _cache_key(resource_path),
                url,
                collected_at,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    log_event("cache.write", key=_cache_key(resource_path), url=url, collected_at=collected_at)


# --------------------------------------------------------------------------- #
# HTTP (fetch com retry e validação de redirect)
# --------------------------------------------------------------------------- #
def _retry_after_seconds(response: requests.Response) -> float | None:
    """Lê ``Retry-After`` (segundos) do header 429, ou ``None`` se ausente."""
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return min(float(header), MAX_BACKOFF_S)
    except ValueError:
        return None


def _redirect_target(current: str, response: requests.Response) -> str:
    """Resolve o próximo hop e exige que ele permaneça na origem permitida."""
    target = urljoin(current, response.headers.get("Location", ""))
    if urlparse(target).netloc != _allowed_host():
        raise InvalidArgument(f"redirect fora da origem bloqueado: {target}")
    return target


def _request_once(url: str, attempt: int = 1) -> dict:
    """Uma tentativa: segue redirects validados e devolve o JSON final.

    Levanta :class:`_Retry` para condições transitórias (rede, 429, 5xx) e os
    erros terminais (:class:`NotFound`, :class:`InvalidResponse`) diretamente.
    Cada GET real gera um evento ``http.request``.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _spend_http()
        started = time.monotonic()
        try:
            response = requests.get(
                current,
                timeout=settings.http_timeout_s,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as exc:
            log_event(
                "http.request", logging.WARNING, url=current, attempt=attempt, status=None,
                error=type(exc).__name__, duration_ms=_ms_since(started),
            )
            raise _Retry() from exc

        status = response.status_code
        log_event("http.request", url=current, attempt=attempt, status=status, duration_ms=_ms_since(started))
        if status in _REDIRECT_STATUS:
            current = _redirect_target(current, response)
            continue
        if status == 404:
            raise NotFound(f"recurso não encontrado: {url}")
        if status in _RETRY_STATUS:
            raise _Retry(_retry_after_seconds(response))
        if status >= 400:
            raise InvalidResponse(f"status inesperado: {status}")

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidResponse(f"JSON inválido: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidResponse("payload não é um objeto JSON")
        return data

    raise InvalidResponse("excesso de redirecionamentos")


def _fetch_json(url: str) -> dict:
    """GET ``url`` com timeout e retries transitórios.

    Pressupõe que ``url`` já foi validada contra a origem permitida.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            return _request_once(url, attempt + 1)
        except _Retry as retry:
            if attempt == MAX_ATTEMPTS - 1:
                log_event("http.unavailable", logging.ERROR, url=url, attempts=MAX_ATTEMPTS)
                raise UpstreamUnavailable(
                    "indisponível após retries"
                ) from (retry.__cause__ or retry)
            wait = retry.retry_after
            if wait is None:
                wait = min(BACKOFF_BASE_S * (2 ** attempt), MAX_BACKOFF_S)
            log_event("http.retry", logging.WARNING, url=url, attempt=attempt + 1, wait_s=wait)
            time.sleep(wait)
    raise UpstreamUnavailable("indisponível após retries")  # defensivo


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_resource(resource_path: str) -> tuple[dict, Provenance]:
    """GET genérico e cacheado para recursos da PokéAPI.

    ``resource_path`` é relativo à base (ex.: ``'type/electric'`` ou
    ``'evolution-chain/67'``); a origem é validada antes de qualquer rede.
    Retorna o payload bruto e a proveniência (``live`` ou ``cache``).
    """
    url = _resolve_url(resource_path)  # valida origem antes da rede

    cached = _cache_read(resource_path)
    if cached is not None:
        provenance = Provenance(
            url=cached["url"],
            collected_at=cached["collected_at"],  # preserva coleta original
            source="cache",
        )
        return cached["payload"], provenance

    payload = _fetch_json(url)
    collected_at = _now_iso()
    _cache_write(resource_path, url, collected_at, payload)
    # Mesmo recurso por id e por nome: grava o outro identificador também, com a
    # mesma origem e data de coleta, para "pokemon/25" reaproveitar "pokemon/pikachu".
    for alias in _alias_paths(resource_path, payload):
        _cache_write(alias, url, collected_at, payload)
    provenance = Provenance(url=url, collected_at=collected_at, source="live")
    return payload, provenance


def _normalize_name_or_id(name_or_id: str | int) -> str:
    """Normaliza a entrada: trim + minúsculas (nome e ID ficam equivalentes)."""
    normalized = str(name_or_id).strip().lower()
    if not normalized:
        raise InvalidArgument("name_or_id vazio")
    return normalized


def _to_pokemon(payload: dict, provenance: Provenance) -> Pokemon:
    """Normaliza o payload da PokéAPI no modelo ``Pokemon``.

    Falhas de contrato viram :class:`InvalidResponse` (sem fabricar dados).
    """
    try:
        stats = {
            entry["stat"]["name"]: entry["base_stat"]
            for entry in payload["stats"]
        }
        return Pokemon(
            id=payload["id"],
            name=payload["name"],
            types=[t["type"]["name"] for t in payload["types"]],
            abilities=[a["ability"]["name"] for a in payload["abilities"]],
            height=payload["height"],
            weight=payload["weight"],
            stats=stats,
            provenance=provenance,
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise InvalidResponse(f"contrato inesperado da PokéAPI: {exc}") from exc


def get_pokemon(name_or_id: str | int) -> Pokemon:
    """Retorna um Pokémon normalizado com proveniência (via cache ou rede)."""
    normalized = _normalize_name_or_id(name_or_id)
    payload, provenance = get_resource(f"pokemon/{normalized}")
    return _to_pokemon(payload, provenance)
