"""``histor tool-cost``: what your server's tool list costs a model, and whether a release made it worse.

    histor tool-cost snapshot --stdio "node dist/index.js" -o tool-cost.json
    histor tool-cost check --baseline tool-cost.json --stdio "node dist/index.js" --max-increase 10%
    histor tool-cost diff before.json after.json

A source is one of ``--tools FILE`` (a tools/list result, a JSON-RPC response carrying one, a bare
array, or ``-`` for stdin), ``--stdio COMMAND`` (started here, probed with ``server/discover``
or initialized for legacy MCP, asked ``tools/list``, then stopped) or ``--url URL`` (a streamable HTTP endpoint, local addresses
allowed: this runs on your machine, not on HISTOR's). ``diff`` also takes snapshots.

``check`` exits 1 when a gated total grew more than ``--max-increase`` or the list is over
``--budget``, 2 when it could not count, 0 otherwise. Its Markdown goes to stdout and, in a GitHub
or Gitea Actions job, to the job summary. ``--update`` writes the new snapshot over the baseline
whatever the outcome, for the commit that accepts a growth.

Counted as HISTOR counts (histor/toolcost.py). Needs the ``cost`` extra:
``pip install 'aimarket-histor[cost]'``.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from histor import __version__, toolcost
from histor.mcpclient import MAX_PAGES, MAX_TOOLS, PROTOCOL_VERSION

MAX_LINE_BYTES = 8 * 1024 * 1024
MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)
MODERN_ERRORS = {-32020, -32021, -32022}
DISCOVER_TIMEOUT_S = 10.0


class SourceError(RuntimeError):
    pass


class _ReplyTimeout(SourceError):
    pass


class _RpcError(SourceError):
    def __init__(self, method: str, error: Any) -> None:
        self.error = error
        super().__init__(f"{method} failed: {json.dumps(error)[:300]}")


def tools_from_json(data: Any) -> list[Any]:
    """The tools of a tools/list result in any of the shapes people save it in."""
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data["result"]
    if isinstance(data, dict) and data.get("resultType", "complete") != "complete":
        raise SourceError(f"{data['resultType']}; tool list incomplete (no client interaction)")
    if isinstance(data, dict) and isinstance(data.get("tools"), list):
        return data["tools"]
    if isinstance(data, list):
        return data
    raise SourceError("no tool list here: expected {\"tools\": [...]}, a JSON-RPC result carrying one, or an array")


def _read_json(path: str) -> Any:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, ValueError) as exc:
        raise SourceError(f"{path}: {exc}") from exc


class _Stdio:
    """Read a complete tool list over modern or legacy MCP without client interactions."""

    def __init__(self, argv: list[str], deadline: float) -> None:
        self.deadline = deadline
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None)
        except OSError as exc:
            raise SourceError(f"could not start {argv[0]!r}: {exc}") from exc
        self.inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.next_id = 0
        self.modern = True  # discover is sent before any era-ambiguous request
        self.protocol_version: str | None = None
        self.server_info: dict[str, Any] | None = None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in iter(lambda: self.proc.stdout.readline(MAX_LINE_BYTES), b""):
            try:
                msg = json.loads(line)
            except ValueError:
                continue    # a server that logs to stdout: not ours to judge here
            if isinstance(msg, dict):
                self.inbox.put(msg)
        self.inbox.put(None)

    def send(self, msg: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(json.dumps(msg).encode() + b"\n")
            self.proc.stdin.flush()
        except OSError as exc:
            raise SourceError(f"the server closed its input ({exc})") from exc

    def request(self, method: str, params: dict[str, Any], wait_s: float | None = None) -> dict[str, Any]:
        self.next_id += 1
        want = self.next_id
        until = self.deadline if wait_s is None else min(self.deadline, time.monotonic() + wait_s)
        self.send({"jsonrpc": "2.0", "id": want, "method": method, "params": params})
        while True:
            left = until - time.monotonic()
            if left <= 0:
                raise _ReplyTimeout(f"no answer to {method} in time")
            try:
                msg = self.inbox.get(timeout=left)
            except queue.Empty:
                raise _ReplyTimeout(f"no answer to {method} in time") from None
            if msg is None:
                raise SourceError(f"the server exited before answering {method} (exit code {self.proc.poll()})")
            if "method" in msg and "id" in msg:
                if self.modern:
                    raise SourceError("modern server sent a server-to-client request; no client interaction supported")
                # A request from the server (roots, sampling, elicitation): refused, so it does not wait.
                self.send({"jsonrpc": "2.0", "id": msg["id"],
                           "error": {"code": -32601, "message": "not supported by histor tool-cost"}})
                continue
            error = msg.get("error")
            if self.modern and ("result" in msg or "error" in msg):
                if msg.get("jsonrpc") != "2.0" or ("result" in msg) == ("error" in msg):
                    raise SourceError("invalid modern JSON-RPC response envelope; no downgrade")
                if "error" in msg and (not isinstance(error, dict) or type(error.get("code")) is not int):
                    raise SourceError("invalid modern JSON-RPC error code; no downgrade")
                if msg.get("id") is None and "error" in msg:
                    raise _RpcError(method, error)  # protocol errors may omit the id
                if type(msg.get("id")) is not int or msg["id"] != want:
                    raise SourceError("modern response did not match the request id; no downgrade")
            if type(msg.get("id")) is not int or msg["id"] != want:
                continue
            if "error" in msg:
                raise _RpcError(method, msg["error"])
            result = msg.get("result")
            if not isinstance(result, dict):
                raise SourceError(f"{method} returned a malformed result")
            if result.get("resultType", "complete") != "complete":
                raise SourceError(f"{method}: {result['resultType']}; observation incomplete (no client interaction)")
            return result

    @staticmethod
    def metadata(params: dict[str, Any] | None = None, version: str = MODERN_PROTOCOL_VERSIONS[0]) -> dict[str, Any]:
        return {**(params or {}), "_meta": {
            "io.modelcontextprotocol/protocolVersion": version,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "histor-tool-cost", "version": __version__},
        }}

    def negotiate(self) -> None:
        # Leave most of the caller's total deadline for legacy initialization/listing if the
        # old server silently ignores discovery. Both attempts use the same process and budget.
        probe_wait = min(DISCOVER_TIMEOUT_S, max(0.001, (self.deadline - time.monotonic()) / 4))
        preferred = MODERN_PROTOCOL_VERSIONS[0]
        try:
            info = self.request("server/discover", self.metadata(version=preferred), probe_wait)
        except _ReplyTimeout:
            info = None
        except _RpcError as exc:
            error = exc.error
            if not isinstance(error, dict) or error.get("code") not in MODERN_ERRORS:
                info = None
            elif error.get("code") != -32022:
                raise
            else:
                data = error.get("data")
                supported = data.get("supported") if isinstance(data, dict) else None
                mutual = [v for v in MODERN_PROTOCOL_VERSIONS if isinstance(supported, list) and v in supported]
                if not mutual:
                    raise SourceError("server/discover: no mutually supported modern protocol version") from exc
                # A second failure propagates. Never repeatedly negotiate or downgrade a
                # positively identified modern server to initialize.
                info = self.request("server/discover", self.metadata(version=mutual[0]), probe_wait)
        if info is not None:
            versions = info.get("supportedVersions")
            if not isinstance(versions, list) or not all(isinstance(v, str) for v in versions):
                raise SourceError("server/discover: malformed supportedVersions")
            mutual = [v for v in MODERN_PROTOCOL_VERSIONS if v in versions]
            if not mutual:
                raise SourceError("server/discover: no mutually supported modern protocol version")
            self.protocol_version = mutual[0]
            meta = info.get("_meta") if isinstance(info.get("_meta"), dict) else {}
            reported = meta.get("io.modelcontextprotocol/serverInfo")
        else:
            self.modern = False
            info = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                               "clientInfo": {"name": "histor-tool-cost", "version": __version__}})
            self.protocol_version = info.get("protocolVersion")
            reported = info.get("serverInfo")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.server_info = reported if isinstance(reported, dict) else None

    def tools(self) -> list[Any]:
        self.negotiate()
        tools: list[Any] = []
        cursor = None
        for _ in range(MAX_PAGES):
            params = {"cursor": cursor} if cursor else {}
            result = self.request("tools/list", self.metadata(params, self.protocol_version) if self.modern else params)
            page = result.get("tools")
            if not isinstance(page, list):
                raise SourceError("tools/list returned no tools array")
            tools += page
            if len(tools) > MAX_TOOLS:
                raise SourceError(f"more than {MAX_TOOLS} tools")
            cursor = result.get("nextCursor")
            if cursor is None:
                return tools
            if not isinstance(cursor, str) or not cursor:
                raise SourceError("tools/list returned an invalid pagination cursor; observation incomplete")
        raise SourceError(f"tools/list still had pages after {MAX_PAGES}")

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def tools_from_stdio(command: str, timeout: float) -> list[Any]:
    argv = shlex.split(command)
    if not argv:
        raise SourceError("--stdio needs a command")
    client = _Stdio(argv, time.monotonic() + timeout)
    try:
        return client.tools()
    finally:
        client.close()


def tools_from_url(url: str, timeout: float) -> list[Any]:
    from histor.mcpclient import McpReader

    obs = McpReader(timeout=min(timeout, 30.0), deadline=timeout, allow_private=True).list_tools(url)
    if obs.status != "ok" or obs.tools is None:
        raise SourceError(f"{url}: {obs.status}{': ' + obs.detail if obs.detail else ''}")
    return obs.tools


def load(args: argparse.Namespace) -> dict[str, Any]:
    if args.tools:
        tools = tools_from_json(_read_json(args.tools))
    elif args.stdio:
        tools = tools_from_stdio(args.stdio, args.timeout)
    elif args.url:
        tools = tools_from_url(args.url, args.timeout)
    else:
        raise SourceError("say where the tools come from: --tools FILE, --stdio COMMAND or --url URL")
    return toolcost.cost(tools)


def load_file(path: str) -> dict[str, Any]:
    """A snapshot as written by ``snapshot``, or a tool list to count."""
    data = _read_json(path)
    if isinstance(data, dict) and data.get("format") == toolcost.FORMAT:
        return data
    return toolcost.cost(tools_from_json(data))


def _source_args(p: argparse.ArgumentParser) -> None:
    src = p.add_mutually_exclusive_group()
    src.add_argument("--tools", metavar="FILE", help="a saved tools/list result, or - for stdin")
    src.add_argument("--stdio", metavar="COMMAND", help='start the server, e.g. "node dist/index.js"')
    src.add_argument("--url", metavar="URL", help="a streamable HTTP MCP endpoint")
    p.add_argument("--timeout", type=float, default=60.0, help="seconds for the whole listing (default 60)")


def _write(path: str | None, doc: dict[str, Any]) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if path and path != "-":
        Path(path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="histor tool-cost", description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="count a tool list and write the snapshot")
    _source_args(snap)
    snap.add_argument("-o", "--output", metavar="FILE", help="where to write it (default stdout)")
    dif = sub.add_parser("diff", help="compare two snapshots or tool lists")
    dif.add_argument("before")
    dif.add_argument("after")
    dif.add_argument("--json", action="store_true", help="print the diff as JSON instead of Markdown")
    chk = sub.add_parser("check", help="compare with a baseline and fail on a regression")
    chk.add_argument("--baseline", required=True, metavar="FILE", help="the committed snapshot (or a tool list)")
    _source_args(chk)
    chk.add_argument("--max-increase", default="10%", metavar="LIMIT",
                     help="how much the total, the descriptions or the input schemas may grow: 10%% or 500 tokens "
                          "(default 10%%); none to only report")
    chk.add_argument("--budget", type=int, metavar="TOKENS", help="fail when the whole list is over this")
    chk.add_argument("--noise", type=int, default=50, metavar="TOKENS",
                     help="a growth under this many tokens never fails (default 50)")
    chk.add_argument("--update", action="store_true", help="write the new snapshot over the baseline")
    chk.add_argument("--json", action="store_true", help="print the diff and the verdict as JSON")
    args = parser.parse_args(argv)

    try:
        if args.command == "snapshot":
            _write(args.output, load(args))
            return 0
        if args.command == "diff":
            d = toolcost.diff(load_file(args.before), load_file(args.after))
            text = json.dumps(d, ensure_ascii=False, indent=1) if args.json else toolcost.markdown(d)
            print(text)
            if not args.json:
                _summary(text)
            return 0
        limit = None if args.max_increase.strip().lower() == "none" else args.max_increase
        if limit is not None:
            toolcost.parse_limit(limit)
        baseline = load_file(args.baseline)
        current = load(args)
        d = toolcost.diff(baseline, current)
        problems = toolcost.regressions(d, max_increase=limit, budget=args.budget, noise=args.noise)
        if args.json:
            print(json.dumps({"ok": not problems, "problems": problems, "diff": d}, ensure_ascii=False, indent=1))
        else:
            text = toolcost.markdown(d, problems)
            print(text)
            _summary(text)
        if args.update:
            _write(args.baseline, current)
        return 1 if problems else 0
    except (SourceError, toolcost.CostUnavailable, ValueError) as exc:
        print(f"histor tool-cost: {exc}", file=sys.stderr)
        return 2
