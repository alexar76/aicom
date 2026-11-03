"""Bounded newline-delimited JSON-RPC transport; shipped inside this standalone package."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

MAX_MESSAGE_BYTES = 4 * 1024 * 1024
log = logging.getLogger(__name__)


def error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


async def serve(dispatch, *, output, source=None) -> None:
    """Read one bounded message at a time; stdout is owned only by this writer.

    EOF ends the session. Notifications/client responses never generate a reply.
    Handler exceptions are logged to stderr without leaking exception text to clients.
    """
    source = source if source is not None else sys.stdin.buffer
    while True:
        line = await asyncio.to_thread(source.readline, MAX_MESSAGE_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_MESSAGE_BYTES:
            while line and not line.endswith(b"\n"):
                line = await asyncio.to_thread(source.readline, MAX_MESSAGE_BYTES + 1)
            reply = error(None, -32600, "Message too large")
        else:
            try:
                msg = json.loads(line.decode("utf-8"), parse_constant=_reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                reply = error(None, -32700, "Parse error")
            else:
                if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                    reply = error(None, -32600, "Invalid request")
                elif "method" not in msg and ("result" in msg or "error" in msg):
                    continue
                elif not isinstance(msg.get("method"), str):
                    reply = error(None, -32600, "Invalid request")
                elif "id" not in msg:
                    continue
                elif type(msg["id"]) not in (str, int):
                    reply = error(None, -32600, "Invalid request id")
                elif not isinstance(msg.get("params", {}), dict):
                    reply = error(msg["id"], -32602, "params must be an object")
                else:
                    try:
                        reply = await dispatch(msg)
                    except Exception:
                        log.exception("MCP request failed")
                        reply = error(msg["id"], -32603, "Internal error; see stderr")
        if reply is not None:
            output.write(json.dumps(reply, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
            output.flush()
