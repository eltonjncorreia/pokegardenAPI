"""Logs estruturados (JSON por linha) correlacionados por ``request_id``.

Cada evento é uma linha JSON em stderr e, se ``settings.log_file`` estiver
definido, também nesse arquivo. O ``request_id`` vem de uma ContextVar setada
por requisição, então eventos do cliente HTTP e das tools herdam a correlação
sem receber o id por parâmetro. Nunca logue segredos nem payloads completos.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from config import settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("pokegarden")


def _configure() -> None:
    """Handlers de stderr (e arquivo opcional) emitindo a mensagem crua (já JSON)."""
    if logger.handlers:
        return
    logger.setLevel(settings.log_level.upper())
    logger.propagate = False
    formatter = logging.Formatter("%(message)s")
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if settings.log_file:
        path = Path(settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


_configure()


@contextmanager
def request_scope(request_id: str) -> Generator[None]:
    """Associa os eventos emitidos dentro do bloco ao ``request_id``."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


def log_event(event: str, level: int = logging.INFO, **fields: object) -> None:
    """Emite um evento estruturado: ``ts``, ``event``, ``request_id`` + campos."""
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "request_id": _request_id.get(),
        **fields,
    }
    logger.log(level, json.dumps(record, ensure_ascii=False, default=str))
