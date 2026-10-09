"""Structured JSON logs with the correlation ID. No invoice numbers, names or amounts."""

import logging
import sys
from contextvars import ContextVar

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.ids import new_id

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

CORRELATION_HEADER = "x-correlation-id"


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            lambda _, __, event: {**event, "correlation_id": correlation_id_var.get()},
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware:
    """Accepts X-Correlation-ID or generates one, and returns it on every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(CORRELATION_HEADER.encode())
        cid = incoming.decode()[:64] if incoming else str(new_id())
        token = correlation_id_var.set(cid)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((CORRELATION_HEADER.encode(), cid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)
