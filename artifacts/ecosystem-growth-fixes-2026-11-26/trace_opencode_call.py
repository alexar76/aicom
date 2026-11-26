"""Measure one synthetic tool call with native MCP and Code Mode in OpenCode."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

FILE = Path(__file__).resolve()
ROOT = FILE.parents[2]
PREVIOUS_TRACE = ROOT / "artifacts/external-mentions-2026-11-25/implementation/trace_opencode.py"
spec = importlib.util.spec_from_file_location("first_request_trace", PREVIOUS_TRACE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
MARKER = "CATALOGUE_FIXTURE_B17"


def mcp():
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        method = message["method"]
        if method == "initialize":
            reply["result"] = {
                "protocolVersion": message["params"]["protocolVersion"],
                "serverInfo": {"name": "catalog-fixture", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            reply["result"] = {"tools": fixture.TOOLS}
        elif method == "tools/call" and message["params"]["name"] == "lookup_book":
            assert message["params"]["arguments"] == {"reference": "B-17"}
            reply["result"] = {"content": [{"type": "text", "text": MARKER + ": Synthetic book, 2001."}]}
        else:
            reply["error"] = {"code": -32601, "message": "Unknown fixture method"}
        print(json.dumps(reply), flush=True)


class Provider(fixture.MockProvider):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        functions = {tool["function"]["name"] for tool in request.get("tools", []) if tool["type"] == "function"}
        output = any(message["role"] == "tool" for message in request["messages"])
        if not output and "catalog_fixture_lookup_book" in functions:
            name, args = "catalog_fixture_lookup_book", {"reference": "B-17"}
        elif not output and "execute" in functions:
            name, args = "execute", {
                "description": "Look up the synthetic book",
                "code": 'return await tools.catalog_fixture.lookup_book({reference: "B-17"});',
            }
        else:
            name = None

        chunk = {"id": "measurement", "object": "chat.completion.chunk", "created": 1, "model": request["model"]}
        delta = {"role": "assistant", "content": "Measured."}
        if name:
            delta = {"role": "assistant", "tool_calls": [{
                "index": 0, "id": "call_fixture", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }]}
        events = [
            {**chunk, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if name else "stop"}]},
            {**chunk, "choices": [], "usage": fixture.MOCK_USAGE},
        ]
        body = ("".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def capture(binary, server, node, dest, code_mode):
    dest.mkdir()
    config = fixture.config(server.server_port, code_mode)
    config["mcp"]["servers"]["catalog_fixture"]["command"] = [sys.executable, str(FILE), "--mcp"]
    (dest / "opencode.json").write_text(json.dumps(config))
    scratch = dest / "tmp"
    scratch.mkdir()
    env = {
        "PATH": os.environ["PATH"], "TMPDIR": str(scratch), "TRACE_FIXTURE_KEY": "local-fixture",
        "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_TELEMETRY": "1",
        **{f"XDG_{key}_HOME": str(dest / key.lower()) for key in ("DATA", "CONFIG", "CACHE", "STATE")},
    }
    server.requests.clear()
    cli = subprocess.run(
        [str(binary), "--standalone", "run", "--format", "json", "--title", "Fixture tool call",
         "Look up the synthetic book B-17 and reply with Measured."],
        cwd=dest, env=env, capture_output=True, text=True, timeout=45,
    )
    requests = [request for request in server.requests if request.get("tools")]
    messages = [message for request in requests for message in request["messages"] if message["role"] == "tool"]
    returned = [message["content"] for message in messages if MARKER in json.dumps(message["content"])]
    if cli.returncode or len(requests) != 2 or len(returned) != 1:
        raise RuntimeError(f"code_mode={code_mode}: {cli.returncode}, {len(requests)} model requests\n"
                           f"{messages}\n{cli.stdout[-2500:]}\n{cli.stderr[-2500:]}")
    functions = [tool["function"] for tool in requests[0]["tools"] if tool["type"] == "function"]
    definitions = [{"name": f["name"], "description": f.get("description", ""), "inputSchema": f.get("parameters", {})}
                   for f in functions]
    catalogue = [tool for tool in definitions if tool["name"].startswith("catalog_fixture_")]
    content = returned[0]
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    token_counter = """
import { readFileSync } from 'node:fs';
import { encode } from 'gpt-tokenizer/encoding/o200k_base';
console.log(encode(readFileSync(0, 'utf8')).length);
"""
    return {
        "requests_with_tools": len(requests),
        "fixture_tool_result": text,
        "all_definition_tokens_at_first_request": fixture.count(node, dest, "all", definitions),
        "catalogue_definition_tokens_at_first_request": fixture.count(node, dest, "catalogue", catalogue) if catalogue else 0,
        "result_utf8_bytes": len(text.encode()),
        "result_tokens": int(subprocess.check_output([node, "--input-type=module", "-e", token_counter],
                              input=text, text=True, cwd=ROOT / "mcp-token-cost")),
    }


def main(binary):
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required")
    with tempfile.TemporaryDirectory(prefix="aicom-opencode-call-") as temp:
        dest = Path(temp)
        with fixture.ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server:
            server.requests = []
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                direct = capture(binary, server, node, dest / "direct", False)
                code_mode = capture(binary, server, node, dest / "code-mode", True)
            finally:
                server.shutdown()
        assert direct["catalogue_definition_tokens_at_first_request"] > 0
        assert code_mode["catalogue_definition_tokens_at_first_request"] == 0
        print(json.dumps({
            "client": "OpenCode 2.4.1", "tokenizer": "o200k_base",
            "full_catalogue_tokens": fixture.count(node, dest, "full", fixture.TOOLS),
            "scope": "One synthetic lookup. No model service was called; mock provider usage is excluded.",
            "direct": direct, "code_mode": code_mode,
        }, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["--mcp"]:
        mcp()
    elif len(sys.argv) == 2:
        main(Path(sys.argv[1]).resolve())
    else:
        sys.exit(f"Usage: python3 {FILE.name} /path/to/opencode")
