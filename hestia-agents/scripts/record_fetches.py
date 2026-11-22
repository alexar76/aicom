"""Run one agent's handler against the live network as the hearth would, and record every reply.

    python3 scripts/record_fetches.py <slug> '<json payload>' \\
        [--out tests/<slug>_vectors.json] [--key NAME]

The handler gets a `fetch` that makes the request for real (urllib, no redirects followed, the
response cut at 256 KiB, only the response headers the hearth passes on), refuses hosts outside the
agent's declared `egress_hosts` plus the caller-named ones, and allows six requests per call: the
hearth's own limits. Every reply is stored under the same key the sandbox uses, so a test can replay
the call with no network. `--key` names the case inside the vectors file; several runs add to one
file.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hestia_agents.manifests import AGENTS, handler_source  # noqa: E402

RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "date",
    "etag",
    "last-modified",
    "location",
    "retry-after",
    "cache-control",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "payment-required",
    "signature",
    "signature-input",
    "link",
}
MAX_ROUNDS = 6
MAX_BYTES = 256 * 1024


def request_key(method, url, headers, body):
    pairs = sorted((str(k).lower(), str(v)) for k, v in (headers or {}).items())
    return json.dumps(
        [str(method or "GET").upper(), url, pairs, body], ensure_ascii=False, separators=(",", ":")
    )


class Reply:
    def __init__(self, raw):
        self.status = int(raw.get("status") or 0)
        self.headers = dict(raw.get("headers") or {})
        self.text = str(raw.get("text") or "")
        self.error = raw.get("error")

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def caller_hosts(slug, payload):
    hosts = []
    for name in AGENTS[slug].get("egress_input_fields") or []:
        value = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(value, str) and value.strip():
            text = value.strip()
            hosts.append((urlsplit(text).hostname if "://" in text else text).lower().rstrip("."))
    return hosts


def live_fetch(slug, payload, recorded):
    allowed = set(AGENTS[slug].get("egress_hosts") or []) | set(caller_hosts(slug, payload))
    opener = urllib.request.build_opener(_NoRedirect)
    rounds = [0]

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        if json is not None:
            body = __import__("json").dumps(json, ensure_ascii=False, separators=(",", ":"))
            headers = dict(headers or {})
            headers.setdefault("content-type", "application/json")
        hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        key = request_key(method, url, hdrs, body)
        if key in recorded:
            return Reply(recorded[key])
        parts = urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "") not in allowed:
            raise RuntimeError("egress refused: " + str(parts.hostname) + " is not a declared host")
        rounds[0] += 1
        if rounds[0] > MAX_ROUNDS:
            raise RuntimeError("egress refused: more than six requests in one call")
        req = urllib.request.Request(  # noqa: S310 — https only, checked above
            url,
            method=str(method).upper(),
            data=body.encode() if isinstance(body, str) else body,
            headers={**hdrs, "user-agent": "hestia-agents-recorder/1"},
        )
        try:
            with opener.open(req, timeout=15) as r:  # noqa: S310 — https only, checked above
                status, raw_headers, data = r.status, r.headers, r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            status, raw_headers, data = e.code, e.headers, e.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raw = {"refused": "response is larger than " + str(MAX_BYTES) + " bytes"}
            recorded[key] = raw
            raise RuntimeError("egress refused: " + raw["refused"])
        raw = {
            "status": status,
            "headers": {
                k.lower(): v for k, v in raw_headers.items() if k.lower() in RESPONSE_HEADERS
            },
            "text": data.decode("utf-8", "replace"),
        }
        recorded[key] = raw
        return Reply(raw)

    return fetch


def run(slug, payload, recorded=None):
    recorded = {} if recorded is None else recorded
    namespace = {
        "__name__": "handler",
        "fetch": live_fetch(slug, payload, recorded),
        "Response": Reply,
    }
    exec(compile(handler_source(slug), "handler.py", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"](payload), recorded


def main(argv):
    slug, payload = argv[0], json.loads(argv[1])
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    name = argv[argv.index("--key") + 1] if "--key" in argv else None
    result, recorded = run(slug, payload)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    if out:
        path = Path(out)
        data = json.loads(path.read_text()) if path.exists() else {}
        data[name or str(len(data))] = {"payload": payload, "fetched": recorded}
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(
            "recorded",
            len(recorded),
            "replies into",
            out,
            "as",
            name or str(len(data) - 1),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main(sys.argv[1:])
