"""A client that disconnects mid-request must not be reported as a server error.

Starlette's ``BaseHTTPMiddleware`` raises ``RuntimeError("No response returned.")`` when the
inner app yields no response, which is what a disconnect looks like from inside the chain.
The factory stacks four such middlewares, so the error travelled all the way out and the
request finished as a 500. The previous production backend logged 30 of them, and the
user-visible result was a black sandbox preview frame in the admin panel.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from web.backend.middleware.client_disconnect import (
    CLIENT_CLOSED_REQUEST,
    client_disconnect_middleware,
)


def _app_that_raises(message: str) -> FastAPI:
    """An app whose inner middleware raises like starlette does on a disconnect."""
    app = FastAPI()

    @app.get("/slow")
    async def slow():  # pragma: no cover - never reached
        return {"ok": True}

    async def inner(request: Request, call_next):
        raise RuntimeError(message)

    # Registration order matters: `app.middleware` prepends, so the guard must be added LAST
    # to sit outside the raiser — the same relationship it has with the real stack.
    app.middleware("http")(inner)
    app.middleware("http")(client_disconnect_middleware)
    return app


def test_disconnect_becomes_499_not_500():
    client = TestClient(_app_that_raises("No response returned."))
    r = client.get("/slow")
    assert r.status_code == CLIENT_CLOSED_REQUEST, (
        "a disconnected client must not be logged and reported as a server fault"
    )


def test_disconnect_is_logged_as_a_warning(caplog):
    client = TestClient(_app_that_raises("No response returned."))
    with caplog.at_level(logging.WARNING):
        client.get("/slow")
    assert any(
        "client closed the request" in rec.getMessage() for rec in caplog.records
    ), "the disconnect must still be visible to an operator"


def test_unrelated_runtime_errors_still_propagate():
    """The guard matches one message on purpose — it must not swallow real failures."""
    client = TestClient(_app_that_raises("database is on fire"), raise_server_exceptions=True)
    with pytest.raises(RuntimeError, match="database is on fire"):
        client.get("/slow")


def test_the_guard_is_the_outermost_middleware_on_the_real_app():
    """Only the outermost layer can stop the error; registration order is the whole fix."""
    import web.backend.main as main

    stack = [m.cls.__name__ if hasattr(m, "cls") else str(m) for m in main.app.user_middleware]
    # Starlette wraps @app.middleware("http") functions in BaseHTTPMiddleware and prepends
    # them, so the LAST registered is first in this list and outermost at runtime.
    dispatchers = [
        (m.kwargs or {}).get("dispatch") for m in main.app.user_middleware
    ]
    names = [getattr(d, "__name__", None) for d in dispatchers]
    assert names[0] == "client_disconnect_middleware", (
        f"client_disconnect_middleware must be outermost; middleware order is {names} ({stack})"
    )
