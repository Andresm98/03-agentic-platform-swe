"""Logging JSON de una línea por evento con `task_id` en cada línea.

El `task_id` viaja en una ContextVar (`bind_task`). Las claves sensibles se redactan.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("task_id", default=None)
_REDACT = {"authorization", "api_key", "openai_api_key", "x-demo-token", "demo_token", "password"}
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}


@contextlib.contextmanager
def bind_task(task_id: str | None) -> Iterator[None]:
    token = _task_id.set(task_id)
    try:
        yield
    finally:
        _task_id.reset(token)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "msg": record.getMessage(),
            "task_id": getattr(record, "task_id", None) or _task_id.get(),
        }
        for key, value in record.__dict__.items():
            if key in _STD or key.startswith("_") or key == "task_id":
                continue
            payload[key] = "[REDACTED]" if key.lower() in _REDACT else value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "httpx2", "grpc"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
