"""Exercise the actual CLI over live pipes, with no HTTP server or operator data."""

import asyncio
import io
import json
import os
import select
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from aimarket_hub import stdio

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "aimarket_hub"


@contextmanager
def session(tmp_path, **extra_env):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AIMARKET_", "AIFACTORY_", "HISTOR_"))
           and k not in ("DATABASE_URL", "PYTHONPATH")}
    env.update(PYTHONPATH=str(ROOT), AIMARKET_AUTO_CRAWL="0", AIMARKET_PQC="0",
               AIMARKET_SKIP_SEED="1", AIMARKET_UPDATE_CHECK="0",
               HISTOR_DATA_DIR=str(tmp_path / "data"), **extra_env)
    with (tmp_path / "stderr.log").open("wb") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", PACKAGE, "mcp"] + (["--init"] if PACKAGE == "aimarket_hub" else []),
            cwd=tmp_path, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, bufsize=0,
        )
        def send(message):
            proc.stdin.write((json.dumps(message) + "\n").encode())
            proc.stdin.flush()

        def read():
            ready, _, _ = select.select([proc.stdout], [], [], 20)
            assert ready, "MCP did not answer while stdin stayed open"
            raw = proc.stdout.readline()
            assert raw, (tmp_path / "stderr.log").read_text()
            return json.loads(raw)

        def call(req_id, method, **params):
            send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            reply = read()
            assert reply["id"] == req_id
            return reply

        try:
            initialized = call(0, "initialize", protocolVersion="2024-11-05", capabilities={},
                               clientInfo={"name": "stdio-test", "version": "1"})
            assert initialized["result"]["protocolVersion"] == "2024-11-05"
            assert "tools" in initialized["result"]["capabilities"]
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            yield call, send, read, proc
            proc.stdin.close()
            assert proc.wait(timeout=15) == 0, (tmp_path / "stderr.log").read_text()
            assert proc.stdout.read() == b"", "Extra stdout after EOF (or notification reply)"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            proc.stdout.close()
            if not proc.stdin.closed:
                proc.stdin.close()


def test_framing_errors_notifications_and_oversize_recovery(monkeypatch):
    monkeypatch.setattr(stdio, "MAX_MESSAGE_BYTES", 256)
    messages = [
        b"{broken", b"[]", b'{"jsonrpc":"1.0","id":1,"method":"ping"}',
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}',
        b'{"jsonrpc":"2.0","id":1,"result":{}}',
        b'{"jsonrpc":"2.0","id":true,"method":"ping"}',
        b'{"jsonrpc":"2.0","id":2,"method":"ping","params":[]}',
        b"x" * 600,
        b'{"jsonrpc":"2.0","id":"last","method":"ping"}',
    ]
    async def dispatch(msg):
        return {"jsonrpc": "2.0", "id": msg["id"], "result": {}}
    output = io.StringIO()
    asyncio.run(stdio.serve(dispatch, output=output, source=io.BytesIO(b"\n".join(messages) + b"\n")))
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r["error"]["code"] for r in replies[:-1]] == [-32700, -32600, -32600, -32600, -32602, -32600]
    assert replies[-1] == {"jsonrpc": "2.0", "id": "last", "result": {}}


def test_cli_protocol_and_tools(tmp_path):
    with session(tmp_path) as (call, send, read, proc):
        tools = call(1, "tools/list")["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert call(2, "ping")["result"] == {}
        assert call(3, "nonexistent")["error"]["code"] == -32601
        assert call(4, "tools/call", name="nonexistent")["error"]["code"] == -32602
        proc.stdin.write(b"not json\n")
        proc.stdin.flush()
        assert read()["error"]["code"] == -32700
        assert {"market_search", "market_invoke", "pipeline_prepare"} <= names
        search = call(5, "tools/call", name="market_search", arguments={"intent": "ping"})["result"]
        assert not search["isError"]
        invoked = call(6, "tools/call", name="market_invoke", arguments={
            "product_id": "hub-hello", "capability_id": "hub.ping@v1", "input": {},
            "include_full_receipt": True,
        })["result"]
        assert not invoked["isError"], invoked
        assert json.loads(invoked["content"][0]["text"])["success"] is True
        bad = call(7, "tools/call", name="market_invoke", arguments={})["result"]
        assert bad["isError"]


def test_stdio_account_uses_this_hub_without_a_listening_socket(tmp_path):
    with session(tmp_path, AIMARKET_MCP_API_KEY="aimk_invalid_test_key") as (call, *_):
        assert "account_status" in {t["name"] for t in call(1, "tools/list")["result"]["tools"]}
        result = call(2, "tools/call", name="account_status", arguments={})["result"]
        assert result["isError"]
        assert "invalid_api_key" in result["content"][0]["text"]
        assert "aimk_invalid_test_key" not in json.dumps(result)

