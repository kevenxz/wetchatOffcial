"""Request correlation for logs.

Why this exists
---------------
``structlog.contextvars.merge_contextvars`` was already in the processor chain, but nothing
ever called ``bind_contextvars``, so no log line carried a correlation id. Without one you
cannot take a ``task_id`` from a UI error and find the matching HTTP request, or follow a
single request through the router, the service layer and the workflow.

Two identifiers are bound:

* ``request_id`` — per HTTP request, echoed back in the ``X-Request-ID`` response header so
  a user can quote it in a bug report.
* ``task_id`` — per workflow run, bound by the workflow entrypoint, so every line a task
  emits is greppable by task.

Both are cleared when their scope ends, so ids never leak between requests or tasks.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger(__name__)


def new_request_id() -> str:
    """Short, unique, and safe to paste into a log search."""
    return uuid.uuid4().hex[:16]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id (and the caller's own, if supplied) for the request's lifetime."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Honour an upstream id (proxy/load balancer) so a trace can span services, but
        # cap the length so a client cannot stuff the log with an enormous header.
        incoming = (request.headers.get(REQUEST_ID_HEADER) or "").strip()[:64]
        request_id = incoming or new_request_id()

        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            # Logging with the id already bound means the failure is traceable even
            # though the client never receives a response.
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
            )
            raise
        finally:
            # Only request-scoped keys are cleared; a task_id bound by a background
            # workflow lives in that task's own context and is unaffected.
            structlog.contextvars.unbind_contextvars("request_id")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
