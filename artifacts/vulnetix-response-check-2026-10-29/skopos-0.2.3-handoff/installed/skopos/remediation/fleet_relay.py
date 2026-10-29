"""The fleet's remediation front door — so a hand on another machine needs no hole.

The self-healing loop is single-host by construction: MOMUS, the conductor, the Factory's fixer
and Gitea all live on one machine and the last two are bound to loopback deliberately. A deploy
hand on a different server therefore has nothing to talk to. The obvious fix — publish the
conductor and Gitea — opens the two most sensitive services in the loop to the network.

This is the other way round. Both sides speak OUTBOUND to a host that is already public and
already the fleet agents' front door:

    conductor host  ──push order + source bundle──▶  relay  ◀──poll order, fetch source──  hand host

Nothing new listens on the conductor's host or on the hand's. The relay holds two things:

* **orders**, handed out ONCE per host — a replayed poll cannot re-run a deploy — and results
  posted back for the forwarder to drain;
* **source**, as a bare git repository the relay updates from uploaded bundles. A bundle rather
  than a push because a push needs an account and a shell; a bare repo rather than the bundle
  itself because the hand fetches with stock git and must stay unchanged — the code that decides
  whether a commit may be built is the last place to introduce a special case.

What the relay is NOT trusted with: anything. It never signs, never decides and never holds a
key. An order is signed by the conductor and carries a MOMUS verdict; the hand verifies both
against keys it was given out of band. A relay that tampered with an order, or served a
different commit, produces a signature check that fails on the hand — which is exactly what a
courier should be able to do at worst.
"""
from __future__ import annotations

import base64
import calendar
import hmac
import json
import mimetypes
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

#: A source bundle. Steady state is a few kilobytes — the courier asks the relay what it already
#: has and sends only the difference — but the FIRST bundle for a fresh relay carries the whole
#: history, which for this monorepo is 586 MB. Configurable so that one-off does not need a code
#: change, and bounded so an unauthenticated flood still cannot fill the disk (the token is
#: checked before the body is read).
MAX_BODY_BYTES = int(os.environ.get("SKOPOS_RELAY_MAX_BODY_MB", "1024")) * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
ORDER_TTL_S = 3600.0                    # an order nobody claimed in an hour is stale, not pending
RESULT_TTL_S = 86400.0


def _token() -> str:
    return os.environ.get("SKOPOS_RELAY_TOKEN", "").strip()


def _repo_dir() -> str:
    return os.environ.get("SKOPOS_RELAY_REPO", "/srv/skopos-relay/aicom.git")


#: How old a conductor-signed order may be and still be carried. The signature never
#: expires on its own, so without this a captured order is replayable for ever. Generous
#: enough that a slow courier or a clock skew is not an outage.
ORDER_MAX_AGE_S = int(os.environ.get("SKOPOS_RELAY_ORDER_MAX_AGE_S", "3600"))


def _order_is_fresh(order: dict[str, Any] | None) -> bool:
    """Is the order's own signed ``created_at`` inside the freshness window?

    An order with no ``created_at`` is carried: build orders in the existing flow do not
    always set one, and refusing them would take the repair loop down rather than harden it.
    An UNPARSEABLE timestamp is refused — that is a malformed document, not an old one.
    """
    stamp = str((order or {}).get("created_at") or "").strip()
    if not stamp:
        return True
    try:
        parsed = time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return False
    age = time.time() - calendar.timegm(parsed)
    # A future stamp is clock skew, not staleness; only the past is bounded.
    return age <= ORDER_MAX_AGE_S


class RelayStore:
    """Orders per host, results by order id. In memory plus a journal, because losing an order is
    safe (the conductor re-publishes) and losing a RESULT is not — it is the only record that a
    deploy happened at all."""

    def __init__(self, journal_path: str = ""):
        self._lock = threading.Lock()
        self._orders: dict[str, list[dict[str, Any]]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._journal = journal_path
        #: order_ids this relay has ever accepted. `claim` POPS, so de-duplicating against
        #: the live queue alone made "handed out once" true only until the queue drained —
        #: after that the same order_id could be pushed back and served again. The relay's
        #: token is fleet-wide (every deploy hand holds it), so anyone who claimed an order
        #: held a genuine conductor-signed document with a valid MOMUS verdict inside it.
        self._spent: set[str] = set()
        #: The host each order_id was accepted for, so a spent id cannot be re-aimed.
        self._claimed_for: dict[str, str] = {}

    def put_order(self, host: str, order_id: str, order: dict[str, Any]) -> None:
        """Accept one order for one host, once, and only while it is fresh.

        Three refusals, all cheap, none of which needs the relay to verify a signature (it
        holds no keys and must not start): a spent order_id, a host that disagrees with the
        host named INSIDE the order, and an order older than the freshness window.
        """
        signed_host = str((order or {}).get("host") or "").strip()
        if signed_host and signed_host != host:
            # The target host is inside the conductor's signature. Honouring it here is what
            # stops a captured order being pointed at a different machine.
            return
        if not _order_is_fresh(order):
            return
        with self._lock:
            if order_id in self._spent:
                return
            queue = self._orders.setdefault(host, [])
            if any(o["order_id"] == order_id for o in queue):
                return                     # idempotent: the forwarder may retry
            self._claimed_for[order_id] = host
            queue.append({"order_id": order_id, "order": order, "at": time.time()})

    def claim(self, host: str) -> dict[str, Any] | None:
        """Once, and once for ever — not merely once per queue lifetime.

        The id goes into `_spent` on the way out, so a re-injection of the same order after
        it drained is refused by `put_order` rather than served again.
        """
        now = time.time()
        with self._lock:
            queue = self._orders.get(host) or []
            while queue:
                entry = queue.pop(0)
                self._spent.add(entry["order_id"])
                if now - entry["at"] <= ORDER_TTL_S:
                    return entry
            return None

    def put_result(self, order_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._results[order_id] = {"order_id": order_id, "result": result, "at": time.time()}
        if self._journal:
            try:
                with open(self._journal, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"order_id": order_id, "result": result,
                                         "at": time.time()}, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def drain_results(self) -> list[dict[str, Any]]:
        with self._lock:
            out = list(self._results.values())
            self._results.clear()
            return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"pending_orders": {h: len(q) for h, q in self._orders.items() if q},
                    "undrained_results": len(self._results)}


#: The only branches this relay will carry. Same prefix the hand enforces; stated twice on
#: purpose, because the two checks protect different things — the hand protects the host it
#: deploys to, the relay protects what it is willing to store and serve at all.
BRANCH_PREFIX = "momus/fix-"
_BRANCH_OK = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./"
)


def base_branch() -> str:
    """The trunk, carried once so every fix branch after it is incremental.

    Without it the FIRST remediation pays for the whole history — 586 MB for this monorepo —
    and it pays during an incident, which is the worst possible moment. It is the only branch
    outside the machine-authored prefix the relay will hold, and it is still never built: the
    hand builds the commit an order names, and an order names a `momus/fix-` branch.
    """
    return os.environ.get("SKOPOS_RELAY_BASE_BRANCH", "main").strip()


def _branch_is_acceptable(branch: str) -> bool:
    name = str(branch or "")
    if len(name) > 200:
        return False
    if not (name.startswith(BRANCH_PREFIX) or (base_branch() and name == base_branch())):
        return False
    if ".." in name or name.endswith("/") or "//" in name:
        return False
    return all(ch in _BRANCH_OK for ch in name)


def apply_bundle(bundle_path: str, branch: str, repo_dir: str = "") -> tuple[bool, str]:
    """Fold an uploaded bundle into the bare repo the hands fetch from.

    `git bundle` verifies its own contents, and the fetch names one branch, so a bundle cannot
    introduce a ref the forwarder did not send. `update-server-info` is what makes the result
    readable over dumb HTTP — without it a fetch sees a repository frozen at the last time
    somebody remembered to run it.
    """
    repo = repo_dir or _repo_dir()
    if not _branch_is_acceptable(branch):
        # The relay carries machine-authored source and nothing else. A branch name outside the
        # prefix — or one carrying a path separator games could hide in — is refused here as well
        # as on the hand, because a courier that will carry anything is a courier worth attacking.
        return False, f"refusing an unexpected branch name: {branch!r}"
    if not os.path.isdir(os.path.join(repo, "objects")):
        os.makedirs(repo, exist_ok=True)
        rc = subprocess.run(["git", "init", "--bare", repo], capture_output=True, text=True)
        if rc.returncode != 0:
            return False, f"could not create the relay repo: {rc.stderr.strip()[:200]}"
    # `-C repo`: `git bundle verify` needs to be inside a repository to know which of the
    # bundle's prerequisites it already has. Run from anywhere else it fails with
    # "need a repository to verify a bundle" — which reads like a bad bundle, not a bad cwd.
    verify = subprocess.run(["git", "-C", repo, "bundle", "verify", bundle_path],
                            capture_output=True, text=True, timeout=300)
    if verify.returncode != 0:
        return False, f"bundle failed verification: {verify.stderr.strip()[:200]}"
    fetch = subprocess.run(
        ["git", "-C", repo, "fetch", "--force", bundle_path,
         f"refs/heads/{branch}:refs/heads/{branch}"],
        capture_output=True, text=True, timeout=300)
    if fetch.returncode != 0:
        return False, f"could not fetch the bundle: {fetch.stderr.strip()[:200]}"
    info = subprocess.run(["git", "-C", repo, "update-server-info"],
                          capture_output=True, text=True, timeout=60)
    if info.returncode != 0:
        return False, f"update-server-info failed: {info.stderr.strip()[:200]}"
    return True, branch


def _relay_refs() -> dict[str, str]:
    """What the relay repo already has, as {ref: sha}. Empty on a fresh relay."""
    repo = _repo_dir()
    if not os.path.isdir(os.path.join(repo, "objects")):
        return {}
    proc = subprocess.run(["git", "-C", repo, "show-ref"], capture_output=True, text=True,
                          timeout=60)
    if proc.returncode != 0:
        return {}
    out = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1]] = parts[0]
    return out


def make_handler(store: RelayStore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "SkoposFleetRelay/1.0"

        def _supplied_token(self) -> str:
            """The token, however the caller could send it.

            `git` cannot be told to set a custom header, but it will send HTTP Basic from a URL
            — so the hand fetches with `https://hand:<token>@host/git/...`. One secret, two
            spellings, rather than a second credential for the same trust."""
            # `x-agent-token` too, because a hand reaching the relay is the SAME program that
            # reaches the conductor and sends that header. Teaching it a second header would be a
            # second code path through the only place a deploy happens; teaching the courier to
            # accept both costs nothing and keeps the hand identical on every host.
            for name in ("x-relay-token", "x-agent-token"):
                header = (self.headers.get(name) or "").strip()
                if header:
                    return header
            auth = (self.headers.get("authorization") or "").strip()
            if auth.lower().startswith("basic "):
                try:
                    decoded = base64.b64decode(auth[6:]).decode("utf-8", "replace")
                except (ValueError, UnicodeDecodeError):
                    return ""
                return decoded.split(":", 1)[1] if ":" in decoded else ""
            return ""

        def _authorised(self, *, git: bool = False) -> bool:
            expected = _token()
            if not expected:
                # Fail closed. A relay with no token would hand any caller the fleet's orders.
                if git:
                    self.send_response(503)
                    self.end_headers()
                else:
                    self._send(503, {"error": "SKOPOS_RELAY_TOKEN is unset — relay refuses to serve"})
                return False
            if not hmac.compare_digest(self._supplied_token(), expected):
                if git:
                    # `git` retries with credentials only when it is asked to.
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="skopos-relay"')
                    self.send_header("content-length", "0")
                    self.end_headers()
                else:
                    self._send(403, {"error": "relay token required"})
                return False
            return True

        def _send(self, code: int, body: Any) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _body(self, limit: int) -> bytes | None:
            """Read the body without believing the headers. ``None`` means "already answered".

            ``int(Content-Length)`` accepts ``-1`` and ``rfile.read(-1)`` then reads to EOF,
            so the cap was not enforced at all; a non-numeric value raised ValueError out of
            the handler. api_server._read_body already documents this trap — this is the
            second door that did not inherit the first one's guard.

            Returning ``None`` rather than ``b""`` matters: the JSON caller treated an empty
            body as "no fields" and sent a SECOND complete response after the 413, which
            desynchronises a keep-alive connection (HTTP/1.1 is declared here).
            """
            raw = (self.headers.get("content-length") or "").strip()
            if not raw.isdigit():
                self._send(400, {"error": "Content-Length must be a non-negative integer"})
                return None
            declared = int(raw)
            if declared > limit:
                self._send(413, {"error": "payload too large"})
                return None
            chunks: list[bytes] = []
            remaining = declared
            read = 0
            while remaining > 0:
                block = self.rfile.read(min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                read += len(block)
                remaining -= len(block)
                if read > limit:
                    self._send(413, {"error": "payload too large"})
                    return None
            return b"".join(chunks)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/fleet/v1/health":
                self._send(200, {"status": "ok", **store.stats()})
                return
            if parsed.path.startswith("/git/"):
                self._serve_git(parsed.path[len("/git/"):])
                return
            if not self._authorised():
                return
            if path == "/fleet/v1/refs":
                # So the courier can send only what is missing. A bundle of the whole history is
                # hundreds of megabytes and has to be carried exactly once; every fix branch after
                # that is two commits deep. Without this the relay is handed the entire repository
                # on every remediation, and the first one does not even fit through nginx.
                self._send(200, {"refs": _relay_refs()})
                return
            if path == "/fleet/v1/orders":
                host = (parse_qs(parsed.query).get("host") or [""])[0].strip()
                if not host:
                    self._send(400, {"error": "host is required"})
                    return
                entry = store.claim(host)
                self._send(200, {"order": (entry or {}).get("order"), "host": host,
                                 "order_id": (entry or {}).get("order_id")})
            elif path == "/fleet/v1/results":
                self._send(200, {"results": store.drain_results()})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if not self._authorised():
                return
            if path == "/fleet/v1/source":
                raw = self._body(MAX_BODY_BYTES)
                if raw is None:
                    return                    # already answered (400/413)
                if not raw:
                    # Answer explicitly: returning silently left the caller hanging.
                    self._send(400, {"error": "empty bundle"})
                    return
                branch = (self.headers.get("x-branch") or "").strip()
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bundle")
                try:
                    tmp.write(raw)
                    tmp.close()
                    ok, note = apply_bundle(tmp.name, branch)
                finally:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                self._send(200 if ok else 400, {"applied": ok, "detail": note})
                return

            raw = self._body(MAX_JSON_BYTES)
            if raw is None:
                return                        # already answered; do not send a second response
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                self._send(400, {"error": "invalid json"})
                return
            if not isinstance(body, dict):
                self._send(400, {"error": "invalid json"})
                return
            if path == "/fleet/v1/orders":
                host = str(body.get("host") or "").strip()
                order = body.get("order")
                order_id = str(body.get("order_id") or "").strip()
                if not host or not order_id or not isinstance(order, dict):
                    self._send(400, {"error": "host, order_id and order are required"})
                    return
                store.put_order(host, order_id, order)
                self._send(200, {"queued": True, "host": host, "order_id": order_id})
            elif path == "/fleet/v1/result":
                order_id = str(body.get("order_id") or "").strip()
                if not order_id:
                    self._send(400, {"error": "order_id is required"})
                    return
                store.put_result(order_id, body.get("result") or {})
                self._send(200, {"recorded": True, "order_id": order_id})
            else:
                self._send(404, {"error": "not found"})

        def _serve_git(self, rel: str) -> None:
            """Read-only dumb-HTTP git.

            Serving the repository from this process rather than from nginx keeps the deployment
            to one moving part — and, more to the point, means the hand fetches with stock git
            against a plain repository. The code that decides whether a commit may be built is
            the last place to introduce a special case.
            """
            if not self._authorised(git=True):
                return
            root = os.path.realpath(_repo_dir())
            # The repo name is part of the URL so the path is `<repo>.git/objects/...`; strip the
            # leading component and resolve inside the root. Traversal is refused by comparing
            # the resolved path, never by inspecting the string.
            tail = rel.split("/", 1)[1] if "/" in rel else ""
            target = os.path.realpath(os.path.join(root, tail))
            if not tail or (target != root and not target.startswith(root + os.sep)):
                self.send_response(404)
                self.send_header("content-length", "0")
                self.end_headers()
                return
            try:
                with open(target, "rb") as fh:
                    payload = fh.read()
            except (OSError, IsADirectoryError):
                self.send_response(404)
                self.send_header("content-length", "0")
                self.end_headers()
                return
            ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(payload)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: Any) -> None:
            import sys
            sys.stderr.write("relay %s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def main() -> None:  # pragma: no cover - process entrypoint
    host = os.environ.get("SKOPOS_RELAY_HOST", "127.0.0.1")
    port = int(os.environ.get("SKOPOS_RELAY_PORT", "9403"))
    journal = os.environ.get("SKOPOS_RELAY_JOURNAL", "/var/lib/skopos-relay/results.jsonl")
    os.makedirs(os.path.dirname(journal), exist_ok=True)
    store = RelayStore(journal)
    if not _token():
        print("WARNING: SKOPOS_RELAY_TOKEN is unset — every request will be refused", flush=True)
    print(f"fleet relay on {host}:{port}, repo {_repo_dir()}", flush=True)
    ThreadingHTTPServer((host, port), make_handler(store)).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
