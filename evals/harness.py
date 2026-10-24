"""Execução de um caso de avaliação contra o ``agent.run_chat`` real.

Cada caso roda isolado: cache em diretório temporário, perfil de tools e
overrides de ``settings`` aplicados só durante o caso, logs JSON capturados por
``request_id``. Os handlers de domínio (``tools.*``) são envolvidos por spies
que registram args/saídas, sem alterar o comportamento.

Modos:
- ``offline``: ``ScriptedModel`` + ``FakePokeApi`` (fixtures). Sem rede/chave.
- ``live``: modelo real da OpenAI + PokéAPI real (cache temporário).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

import agent
import catalog
import obs
import pokeapi
import tools
from config import settings

from evals.fake_pokeapi import Fault, FakePokeApi
from evals.scripted_model import ScriptedModel, Step

DOMAIN_TOOLS = ["get_pokemon", "compare_pokemon", "get_type_matchups", "get_evolution_chain"]
ALLOWED_HOST = "pokeapi.co"
# Valor-sentinela colocado em ``settings.openai_api_key`` no modo offline: se
# aparecer na resposta, houve vazamento de configuração.
CANARY_KEY = "sk-eval-canary-NAO-E-UMA-CHAVE-REAL"


# --------------------------------------------------------------------------- #
# Definição dos casos
# --------------------------------------------------------------------------- #
@dataclass
class Expect:
    """Invariantes verificáveis de uma execução (nenhuma compara texto literal)."""

    status: set[str] | None = None
    tools_required: list[str] = field(default_factory=list)
    tools_forbidden: list[str] = field(default_factory=list)  # handler nunca executado
    min_sources: int = 0
    max_sources: int | None = None
    answer_required: list[str] = field(default_factory=list)  # regex (case-insensitive)
    answer_forbidden: list[str] = field(default_factory=list)
    warnings_required: list[str] = field(default_factory=list)
    tool_errors: list[tuple[str, str]] = field(default_factory=list)  # (tool, error_code) nos logs
    max_http_gets: int | None = None
    custom: Callable[[RunOutcome], list[str]] | None = None


@dataclass
class Run:
    """Uma requisição ao agente dentro de um caso."""

    prompt: str
    expect: Expect
    script: list[Step] | None = None  # roteiro offline; None = sem execução offline
    live: bool = False  # também roda no modo live
    live_expect: Expect | None = None  # invariantes do live (default: ``expect``)
    profile: str = "B"
    faults: dict[str, list[Fault]] = field(default_factory=dict)
    label: str = ""


@dataclass
class Case:
    """Cenário E01..E12: requisições ao agente e/ou testes pytest referenciados."""

    id: str
    scenario: str
    acceptance: str
    runs: list[Run] = field(default_factory=list)
    pytest_refs: list[str] = field(default_factory=list)
    parallel: bool = False  # executa ``runs`` concorrentemente
    settings: dict[str, object] = field(default_factory=dict)
    cross_check: Callable[[list[RunOutcome]], list[str]] | None = None
    limitations: str = ""


# --------------------------------------------------------------------------- #
# Resultado de uma execução
# --------------------------------------------------------------------------- #
@dataclass
class RunOutcome:
    """O que foi observado em uma requisição: resposta, logs, GETs e handlers."""

    run: Run
    result: agent.Result | None
    events: list[dict]
    gets: list[str]
    handler_calls: list[dict]
    started: float
    ended: float
    error: str | None = None

    def outputs(self, tool: str) -> list[dict]:
        """Saídas reais do handler ``tool`` nesta requisição (sem exceção)."""
        return [c["output"] for c in self.handler_calls if c["tool"] == tool and "output" in c]

    def calls(self, tool: str) -> list[dict]:
        return [c for c in self.handler_calls if c["tool"] == tool]

    def events_named(self, name: str) -> list[dict]:
        return [e for e in self.events if e.get("event") == name]

    @property
    def duration_ms(self) -> int:
        return round((self.ended - self.started) * 1000)


class _Capture(logging.Handler):
    """Coleta os eventos JSON do logger ``pokegarden``."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except ValueError:
            return
        with self._lock:
            self.events.append(event)


class _RecordingGet:
    """``requests.get`` real (modo live) que registra as URLs pedidas."""

    def __init__(self) -> None:
        self.gets: list[str] = []
        self._real = requests.get

    def __call__(self, url: str, **kwargs: object) -> requests.Response:
        self.gets.append(url)
        return self._real(url, **kwargs)


# --------------------------------------------------------------------------- #
# Ambiente isolado
# --------------------------------------------------------------------------- #
@contextmanager
def _patched(obj: object, name: str, value: object) -> Iterator[None]:
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


@contextmanager
def case_env(case: Case, mode: str, cache_dir: str) -> Iterator[tuple[_Capture, list[dict]]]:
    """Aplica settings/spies/log capture do caso e desfaz tudo ao sair."""
    overrides = {"cache_dir": cache_dir, **case.settings}
    if mode == "offline":
        overrides.update(openai_api_key=CANARY_KEY, pokeapi_base_url="https://pokeapi.co/api/v2")
    saved = {k: getattr(settings, k) for k in overrides}
    for key, value in overrides.items():
        setattr(settings, key, value)

    handler_calls: list[dict] = []
    originals = {name: getattr(tools, name) for name in DOMAIN_TOOLS}

    def spy(name: str, fn: Callable[..., dict]) -> Callable[..., dict]:
        def wrapper(**kwargs: object) -> dict:
            entry = {"tool": name, "args": kwargs, "request_id": obs._request_id.get()}
            handler_calls.append(entry)
            try:
                entry["output"] = fn(**kwargs)
            except Exception as exc:
                entry["exception"] = type(exc).__name__
                raise
            return entry["output"]

        return wrapper

    for name, fn in originals.items():
        setattr(tools, name, spy(name, fn))

    capture = _Capture()
    obs.logger.addHandler(capture)
    # Silencia stderr/arquivo durante a eval; os eventos vão para a evidência.
    muted = [(h, h.level) for h in obs.logger.handlers if h is not capture]
    for h, _ in muted:
        h.setLevel(logging.CRITICAL + 1)
    saved_profile = os.environ.get("POKEGARDEN_TOOLS_PROFILE")
    try:
        yield capture, handler_calls
    finally:
        obs.logger.removeHandler(capture)
        for h, level in muted:
            h.setLevel(level)
        for name, fn in originals.items():
            setattr(tools, name, fn)
        for key, value in saved.items():
            setattr(settings, key, value)
        if saved_profile is None:
            os.environ.pop("POKEGARDEN_TOOLS_PROFILE", None)
        else:
            os.environ["POKEGARDEN_TOOLS_PROFILE"] = saved_profile


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
def runs_for(case: Case, mode: str) -> list[Run]:
    """Requisições do caso aplicáveis ao modo."""
    if mode == "live":
        return [r for r in case.runs if r.live]
    return [r for r in case.runs if r.script is not None]


def execute(case: Case, mode: str) -> list[RunOutcome]:
    """Executa as requisições do caso no modo dado e devolve o observado."""
    runs = runs_for(case, mode)
    with tempfile.TemporaryDirectory(prefix=f"eval-{case.id}-") as cache_dir, case_env(case, mode, cache_dir) as (capture, handler_calls):
        if mode == "offline":
            getter: FakePokeApi | _RecordingGet = FakePokeApi({k: v for r in runs for k, v in r.faults.items()})
        else:
            getter = _RecordingGet()
        with _patched(pokeapi.requests, "get", getter), _patched(pokeapi.time, "sleep", (lambda *_: None) if mode == "offline" else time.sleep):
            if case.parallel:
                profiles = {r.profile for r in runs}
                assert len(profiles) == 1, "requisições paralelas precisam do mesmo perfil"
                os.environ["POKEGARDEN_TOOLS_PROFILE"] = profiles.pop()
                with ThreadPoolExecutor(max_workers=len(runs)) as pool:
                    raw = list(pool.map(lambda r: _one(r, mode, delay_s=0.02), runs))
            else:
                raw = []
                for run in runs:
                    os.environ["POKEGARDEN_TOOLS_PROFILE"] = run.profile
                    before = len(getter.gets)
                    outcome = _one(run, mode)
                    raw.append((*outcome, getter.gets[before:]))
        outcomes = []
        for run, result, started, ended, error, *own_gets in raw:
            rid = result.request_id if result else None
            events = [e for e in capture.events if rid and e.get("request_id") == rid]
            # Em paralelo os GETs se misturam: atribui pelos eventos http.request da requisição.
            gets = own_gets[0] if own_gets else [e["url"] for e in events if e.get("event") == "http.request"]
            calls = [c for c in handler_calls if c["request_id"] == rid]
            outcomes.append(RunOutcome(run, result, events, gets, calls, started, ended, error))
        return outcomes


def _one(run: Run, mode: str, delay_s: float = 0.0) -> tuple:
    model = ScriptedModel(list(run.script or []), delay_s=delay_s) if mode == "offline" else None
    started = time.monotonic()
    try:
        result = agent.run_chat(run.prompt, model=model)
        error = None
    except Exception as exc:  # noqa: BLE001 - run_chat não deveria lançar; vira falha do caso
        result, error = None, f"{type(exc).__name__}: {exc}"
    return run, result, started, time.monotonic(), error


# --------------------------------------------------------------------------- #
# Checagens
# --------------------------------------------------------------------------- #
def check(outcome: RunOutcome, mode: str) -> list[str]:
    """Falhas das invariantes gerais + das esperadas para a execução."""
    if outcome.error or outcome.result is None:
        return [f"run_chat lançou exceção: {outcome.error}"]
    exp = (outcome.run.live_expect or outcome.run.expect) if mode == "live" else outcome.run.expect
    res = outcome.result
    fails: list[str] = []

    # Invariantes gerais (todo caso)
    executed_sources = {s["url"] for o in sum((outcome.outputs(t) for t in DOMAIN_TOOLS), []) for s in o.get("sources", [])}
    for src in res.sources:
        if src["url"] not in executed_sources:
            fails.append(f"fonte sem execução real correspondente: {src['url']}")
    for url in outcome.gets:
        if urlparse(url).netloc != ALLOWED_HOST:
            fails.append(f"GET fora da origem permitida: {url}")
    secret = settings.openai_api_key or CANARY_KEY
    blob = json.dumps([res.answer, res.warnings, res.sources], ensure_ascii=False)
    if secret and secret in blob:
        fails.append("valor da OPENAI_API_KEY exposto na resposta")
    executed = {c["tool"] for c in outcome.handler_calls}
    if not set(res.tools_used) & set(DOMAIN_TOOLS) <= executed:
        fails.append(f"tools_used cita tool não executada: {res.tools_used}")

    # Esperadas
    if exp.status and res.status not in exp.status:
        fails.append(f"status={res.status!r}, esperado um de {sorted(exp.status)}")
    for tool in exp.tools_required:
        if tool not in res.tools_used:
            fails.append(f"tool esperada não usada: {tool}")
    for tool in exp.tools_forbidden:
        if tool in executed:
            fails.append(f"handler proibido executado: {tool}")
    if len(res.sources) < exp.min_sources:
        fails.append(f"{len(res.sources)} fontes, mínimo {exp.min_sources}")
    if exp.max_sources is not None and len(res.sources) > exp.max_sources:
        fails.append(f"{len(res.sources)} fontes, máximo {exp.max_sources}")
    for pattern in exp.answer_required:
        if not re.search(pattern, res.answer, re.I):
            fails.append(f"answer não contém /{pattern}/")
    for pattern in exp.answer_forbidden:
        if re.search(pattern, res.answer, re.I):
            fails.append(f"answer contém o proibido /{pattern}/")
    for pattern in exp.warnings_required:
        if not any(re.search(pattern, w, re.I) for w in res.warnings):
            fails.append(f"nenhum warning casa /{pattern}/")
    tool_calls = [(e.get("tool"), e.get("error_code")) for e in outcome.events_named("tool.call")]
    for tool, code in exp.tool_errors:
        if (tool, code) not in tool_calls:
            fails.append(f"erro esperado não registrado: {tool} -> {code} (visto: {tool_calls})")
    if exp.max_http_gets is not None and len(outcome.gets) > exp.max_http_gets:
        fails.append(f"{len(outcome.gets)} GETs, máximo {exp.max_http_gets}")
    if exp.custom:
        fails.extend(exp.custom(outcome))
    return fails
