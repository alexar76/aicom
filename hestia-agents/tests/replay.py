"""Replay what an agent's hosts answered, recorded by scripts/record_fetches.py, with no network.

`load(slug, fetched, tamper=None)` executes the agent's handler with a `fetch` that answers from
`fetched` (the replies keyed exactly as the sandbox keys them) and fails the test on any request
that was not recorded. `tamper(url, raw)` may return a changed copy of one reply. `asked` lists the
URLs in the order the handler asked for them, so a test can hold the handler to the hearth's six
requests.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from record_fetches import Reply, request_key  # noqa: E402

from hestia_agents.manifests import handler_source  # noqa: E402

MAX_ROUNDS = 6


class Unrecorded(AssertionError):
    pass


def load(slug, fetched, tamper=None, extra=None):
    asked = []
    answers = dict(fetched)
    answers.update(extra or {})

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        if json is not None:
            body = __import__("json").dumps(json, ensure_ascii=False, separators=(",", ":"))
            headers = dict(headers or {})
            headers.setdefault("content-type", "application/json")
        hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        key = request_key(method, url, hdrs, body)
        asked.append(url)
        if len(asked) > MAX_ROUNDS:
            raise AssertionError("more than six requests in one call: " + url)
        if key not in answers:
            raise Unrecorded("not recorded: " + key)
        raw = copy.deepcopy(answers[key])
        if tamper:
            raw = tamper(url, raw)
        if raw.get("refused"):
            raise RuntimeError("egress refused: " + str(raw["refused"]))
        return Reply(raw)

    namespace = {"__name__": "handler", "fetch": fetch}
    exec(compile(handler_source(slug), slug, "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked, namespace


def key_for(url, accept):
    return request_key("GET", url, {"accept": accept}, None)


def text_of(raw):
    return json.loads(raw["text"])


def with_json(raw, doc):
    out = dict(raw)
    out["text"] = json.dumps(doc)
    return out
