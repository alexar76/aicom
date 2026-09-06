"""A browser that walks away must not turn into a 500.

Starlette's ``BaseHTTPMiddleware`` raises ``RuntimeError("No response returned.")`` when the
inner app produces no response — which is exactly what happens when the client disconnects
mid-request. The factory stacks four of these (CSRF, HTTP firewall, sandbox opaque CORS,
security headers), so the error propagates the whole way out and the request ends as a 500.

That is not theoretical. The previous backend process logged **30** of them, and the visible
symptom was the admin sandbox preview: the iframe requested ``/api/sandbox/view/…``, the
connection was interrupted, the middleware chain raised, and the panel was left with a black
frame or a bare "NetworkError" instead of a preview. Long-running sandbox requests made it
easy to hit; ``_start_sandbox_for_product`` no longer blocks for the whole bootstrap, which
removes the easiest trigger, but any slow request over a flaky link can still get there.

So the outermost layer translates that one specific condition into 499 (nginx's code for
"client closed the request"), logged at warning. Nothing is sent — the socket is already
gone — but the exception stops here instead of being reported as a server fault, and the
access log stops claiming the server failed when it did not.

A genuine "middleware returned no response" bug still shows up: same warning, and the client
that is still connected gets 499 rather than a 500 with no explanation. That is a trade worth
making — the alternative is drowning real disconnects in false 500s.
"""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Starlette raises this exact message from BaseHTTPMiddleware.call_next. Matching on the text
# is deliberate: a bare `except RuntimeError` here would swallow unrelated failures from every
# route in the application.
_NO_RESPONSE = "No response returned."

# 499 is not in the HTTP standard; it is nginx's convention for a client-closed request, and
# the access logs in front of this service already use it. Keeping the same number means the
# two logs agree about what happened.
CLIENT_CLOSED_REQUEST = 499


async def client_disconnect_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except RuntimeError as exc:
        if _NO_RESPONSE not in str(exc):
            raise
        logger.warning(
            "client closed the request before a response was produced: %s %s",
            request.method,
            request.url.path,
        )
        return Response(status_code=CLIENT_CLOSED_REQUEST)
