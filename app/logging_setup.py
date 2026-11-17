"""Structured JSON logging. Only request id, user id and event type are bound
as context; no PII or document content is ever added. Requirement 17.8."""
from __future__ import annotations

import logging
import re
import sys
import uuid
from typing import Optional

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_ALLOWED_KEYS = {"request_id", "user_id", "event_type", "event", "level", "timestamp", "logger"}


def resolve_request_id(incoming: Optional[str]) -> str:
    if incoming and _REQUEST_ID_RE.match(incoming):
        return incoming
    return str(uuid.uuid4())


def current_request_id() -> Optional[str]:
    return get_contextvars().get("request_id")


def bind_user(user_id: Optional[str]) -> None:
    bind_contextvars(user_id=user_id)


def _restrict_keys(_logger, _method, event_dict):
    """Drop everything except the allow-listed fields (defence against PII)."""
    return {k: v for k, v in event_dict.items() if k in _ALLOWED_KEYS}


def configure_logging(level: int = logging.INFO, stream=None) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _restrict_keys,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "claims"):
    return structlog.get_logger(name)


class RequestContextMiddleware:
    """Pure ASGI middleware: sets request_id (and echoes it in the response)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = None
        for k, v in scope.get("headers", []):
            if k.lower() == b"x-request-id":
                incoming = v.decode("latin-1")
                break
        rid = resolve_request_id(incoming)
        clear_contextvars()
        bind_contextvars(request_id=rid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_contextvars()
