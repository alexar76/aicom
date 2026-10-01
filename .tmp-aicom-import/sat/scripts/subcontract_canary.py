#!/usr/bin/env python3
"""Buy weather.witness@v1 as its root buyer and check the subcontracting it sets off.

Subcontracting (aimarket-protocol/mandates.md §6) is proven only by a provider that really
buys from another provider while serving a call, paid out of a real root buyer's allowance.
There is no organic demand for that on the hub yet, so this script IS the demand: our own
buyer, calling our own composite (aimarket-hub/examples/subcontract-capability), which buys
two readings from our own GAIA. A self-driven research demonstration — its value is that
every step is the production code path, with real money on the credits rail, and that each
claim below is checked from outside.

Cost-plus (default): the root call reserves an allowance, and the canary asserts

* the composite delivered a witness;
* the bill of materials holds exactly two captured, allowance-funded children
  (gaia.weather.read@v1 and gaia.air.read@v1), and ``spent + released == allowance``;
* the node prices add up to what was spent, and the witness names the same nodes;
* ``GET /ai-market/v2/jobs/{job_id}`` returns the same tree, its allowance closed;
* the root's AWR/2 receipt lists the children's receipt digests in ``credentialSubject.parents``.

``--fixed-price`` sends no allowance: the composite pays the readings with its own key, and
the tree must still show both children, funded ``own``.

``--a2a`` makes the root call an A2A 1.0 ``SendMessage`` to ``POST /a2a`` instead of
``POST /ai-market/v2/invoke``, and additionally asserts that the answer is a COMPLETED Task
that ``GetTask`` reads back unchanged. Only the ROOT changes protocol: the composite still
buys its readings at ``/ai-market/v2/invoke``, the one place a job tree is joined (``/a2a``
refuses job headers rather than dropping them).

    SUBCONTRACT_CANARY_API_KEY=aimk_... scripts/subcontract_canary.py
    scripts/subcontract_canary.py --api-key-file /root/.subcontract-canary.key --fixed-price --json
    scripts/subcontract_canary.py --api-key-file /root/.subcontract-canary.key --a2a

The key is read from the environment or a file, never from the command line, where every
user on the host could read it from the process list. A cost-plus run costs the buyer the
composite's price plus what its two readings cost (about $0.004 on modelmarket.dev).

No third-party imports: this has to run from a bare cron on a host that has no venv.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_HUB = os.environ.get("AIMARKET_HUB_URL", "https://modelmarket.dev").rstrip("/")
USER_AGENT = "aimarket-subcontract-canary/1.0 (+https://modelmarket.dev)"
COMPOSITE = {"product_id": "weather-witness", "capability_id": "weather.witness@v1"}
CHILDREN = ("gaia.air.read@v1", "gaia.weather.read@v1")
# The credits ledger's unit is $0.00001; anything closer than half of it is the same amount.
EPS = 0.000005
A2A_HEADERS = {"A2A-Version": "1.0"}
A2A_COMPLETED = "TASK_STATE_COMPLETED"


class Check:
    """One assertion, with the evidence that decided it."""

    def __init__(self, name: str, ok: bool, detail: str, critical: bool = True):
        self.name, self.ok, self.detail, self.critical = name, ok, detail, critical

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "critical": self.critical}


class Http:
    """urllib, JSON in and out. Swappable, so the hub's suite runs this against its app."""

    def __init__(self, timeout: float = 45.0):
        self.timeout = timeout

    def _send(self, req: urllib.request.Request) -> tuple[int, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                return exc.code, None
        except Exception:  # noqa: BLE001 - unreachable, timeout, not JSON: no evidence
            return 0, None

    def get(self, url: str) -> tuple[int, Any]:
        return self._send(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}))

    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, Any]:
        return self._send(urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
        ))


# ── observation ──────────────────────────────────────────────────────────────


def _artifact_data(task: dict[str, Any], name: str) -> tuple[Any, dict[str, Any]]:
    for item in task.get("artifacts") or []:
        if isinstance(item, dict) and name in (item.get("name"), item.get("artifactId")):
            parts = item.get("parts") or [{}]
            part = parts[0] if isinstance(parts[0], dict) else {}
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            return part.get("data", part.get("text")), meta
    return None, {}


def task_as_invoke(task: Any) -> tuple[int, dict[str, Any] | None]:
    """An A2A Task, read back into the invoke answer the checks below expect: the result
    artifact, the bill from ``metadata.aimarket`` and the AWR/2 receipt artifact. A task that
    did not complete is reported with the hub's own refusal, never as a delivered call."""
    if not isinstance(task, dict):
        return 0, None
    aimarket = (task.get("metadata") or {}).get("aimarket") or {}
    if (task.get("status") or {}).get("state") != A2A_COMPLETED:
        refusal = ((((task.get("status") or {}).get("message") or {}).get("metadata") or {})
                   .get("aimarket") or {})
        return 502, {"success": False, "a2a_state": (task.get("status") or {}).get("state"),
                     "error": refusal.get("error"), "detail": refusal.get("detail")}
    result, _ = _artifact_data(task, "result")
    provenance, meta = _artifact_data(task, "provenance")
    body: dict[str, Any] = {"success": True, "result": result}
    for key in ("price_usd", "subcontracting", "remaining_balance"):
        if key in aimarket:
            body[key] = aimarket[key]
    if isinstance(provenance, dict):
        body["provenance_receipt"] = {**provenance, **meta}
    return 200, body


def _a2a_root(http: Http, hub: str, api_key: str, payload: dict[str, Any]) -> tuple[int, Any, dict[str, Any]]:
    headers = {"X-API-Key": api_key, **A2A_HEADERS}
    message = {"messageId": f"canary-{secrets.token_hex(8)}", "role": "ROLE_USER",
               "parts": [{"data": {"invoke": payload}, "mediaType": "application/json"}]}
    rpc_status, answer = http.post(f"{hub}/a2a", {"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                                                  "params": {"message": message}}, headers)
    task = ((answer or {}).get("result") or {}).get("task") if isinstance(answer, dict) else None
    a2a: dict[str, Any] = {"rpc_status": rpc_status, "task_id": None, "state": None,
                           "reread_state": None, "reread_same": False,
                           "rpc_error": (answer or {}).get("error") if isinstance(answer, dict) else None}
    if not isinstance(task, dict):
        return 0, None, a2a
    a2a["task_id"], a2a["state"] = task.get("id"), (task.get("status") or {}).get("state")
    # A Task is a record the client can come back to: read it again and compare.
    _, again = http.post(f"{hub}/a2a", {"jsonrpc": "2.0", "id": 2, "method": "GetTask",
                                        "params": {"id": task.get("id")}}, headers)
    reread = (again or {}).get("result") if isinstance(again, dict) else None
    if isinstance(reread, dict):
        a2a["reread_state"] = (reread.get("status") or {}).get("state")
        a2a["reread_same"] = (reread.get("id") == task.get("id")
                              and (reread.get("metadata") or {}).get("aimarket", {}).get("subcontracting")
                              == (task.get("metadata") or {}).get("aimarket", {}).get("subcontracting"))
    status, body = task_as_invoke(task)
    return status, body, a2a


def observe(hub: str, api_key: str, *, city: str, allowance_usd: float, fixed_price: bool,
            http: Http | None = None, a2a: bool = False) -> dict[str, Any]:
    http = http or Http()
    hub = hub.rstrip("/")
    payload: dict[str, Any] = {**COMPOSITE, "input": {"city": city}}
    if not fixed_price:
        payload["subcontract"] = {"allowance_usd": allowance_usd, "max_depth": 1}
    task: dict[str, Any] | None = None
    if a2a:
        status, body, task = _a2a_root(http, hub, api_key, payload)
    else:
        status, body = http.post(f"{hub}/ai-market/v2/invoke", payload, {"X-API-Key": api_key})
    seen: dict[str, Any] = {"status": status, "body": body if isinstance(body, dict) else None,
                            "tree_status": None, "tree": None, "receipt_status": None, "receipt": None,
                            "a2a": task}
    sub = (seen["body"] or {}).get("subcontracting") or {}
    job_id = sub.get("job_id")
    if isinstance(job_id, str) and job_id:
        seen["tree_status"], tree = http.get(f"{hub}/ai-market/v2/jobs/{job_id}")
        seen["tree"] = tree if isinstance(tree, dict) else None
    receipt = (seen["body"] or {}).get("provenance_receipt") or {}
    url = receipt.get("receipt_url") if isinstance(receipt, dict) else None
    if isinstance(url, str) and url:
        if url.startswith("/"):
            url = hub + url
        seen["receipt_status"], document = http.get(url)
        if isinstance(document, dict):
            seen["receipt"] = document.get("receipt", document)
    return seen


# ── evaluation: pure, so every verdict is testable without a network ─────────


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(seen: dict[str, Any], *, allowance_usd: float, fixed_price: bool) -> list[Check]:
    checks: list[Check] = []
    body = seen.get("body") or {}
    a2a = seen.get("a2a")
    if isinstance(a2a, dict):
        task_id = str(a2a.get("task_id") or "")
        checks.append(Check(
            "a2a_task_completed",
            task_id.startswith("a2at_") and a2a.get("state") == A2A_COMPLETED
            and a2a.get("reread_state") == A2A_COMPLETED and a2a.get("reread_same") is True,
            f"SendMessage (HTTP {a2a.get('rpc_status')}) → task {task_id or 'none'} {a2a.get('state')}; "
            f"GetTask → {a2a.get('reread_state')}, bill {'unchanged' if a2a.get('reread_same') else 'DIFFERENT'}"
            + (f"; error {json.dumps(a2a.get('rpc_error'))[:200]}" if a2a.get("rpc_error") else ""),
        ))
    delivered = seen.get("status") == 200 and body.get("success") is True
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    checks.append(Check(
        "root_delivered", delivered and result.get("witness") == "weather-witness/1",
        f"HTTP {seen.get('status')}: " + (
            f"witness for {result.get('place')}" if delivered
            else json.dumps({k: body.get(k) for k in ("error", "detail")})[:300]),
    ))
    if not delivered:
        return checks

    sub = body.get("subcontracting") or {}
    nodes = [n for n in sub.get("nodes") or [] if isinstance(n, dict)]
    funded = "own" if fixed_price else "allowance"
    good = [n for n in nodes if n.get("status") == "captured" and n.get("depth") == 1
            and n.get("funded_by") == funded]
    checks.append(Check(
        "two_children_captured",
        len(nodes) == 2 and len(good) == 2 and tuple(sorted(n.get("capability_id") for n in good)) == CHILDREN,
        f"{len(good)}/{len(nodes)} captured {funded}-funded depth-1 nodes: "
        + ", ".join(f"{n.get('capability_id')}={n.get('status')}/{n.get('funded_by')}" for n in nodes),
    ))

    spent = _num(sub.get("spent_usd"))
    if fixed_price:
        checks.append(Check(
            "no_allowance_reserved", "allowance_usd" not in sub,
            "no allowance in the bill" if "allowance_usd" not in sub
            else f"an allowance of {sub.get('allowance_usd')} appeared on a fixed-price call",
        ))
    else:
        allowance, released = _num(sub.get("allowance_usd")), _num(sub.get("released_usd"))
        balanced = (allowance is not None and spent is not None and released is not None
                    and abs(allowance - allowance_usd) < EPS and spent > 0
                    and abs(spent + released - allowance) < EPS)
        checks.append(Check(
            "allowance_accounted", balanced,
            f"allowance {allowance} = spent {spent} + released {released} (asked {allowance_usd})",
        ))
        priced = sum(_num(n.get("price_usd")) or 0.0 for n in nodes)
        checks.append(Check(
            "bill_adds_up", spent is not None and abs(priced - spent) < EPS,
            f"node prices sum to {round(priced, 6)}, spent_usd is {spent}",
        ))

    bill = {n.get("node"): n.get("receipt_digest") for n in nodes}
    named = {c.get("node"): c.get("receipt_digest")
             for c in result.get("children") or [] if isinstance(c, dict)}
    job = result.get("job") if isinstance(result.get("job"), dict) else {}
    checks.append(Check(
        "witness_matches_bill",
        bool(bill) and named == bill and job.get("job_id") == sub.get("job_id")
        and result.get("funding") == ("fixed-price" if fixed_price else "cost-plus"),
        f"witness names {sorted(map(str, named))} under {job.get('job_id')} ({result.get('funding')}); "
        f"bill has {sorted(map(str, bill))} under {sub.get('job_id')}",
    ))

    tree = seen.get("tree") or {}
    tree_nodes = {n.get("node") for n in tree.get("nodes") or [] if isinstance(n, dict)}
    tree_ok = seen.get("tree_status") == 200 and len(tree_nodes) == 3 and set(bill) <= tree_nodes
    if not fixed_price:
        tree_ok = tree_ok and tree.get("allowance_status") == "closed"
    checks.append(Check(
        "job_tree_readable", tree_ok,
        f"GET /jobs/{sub.get('job_id')} → HTTP {seen.get('tree_status')}, {len(tree_nodes)} nodes, "
        f"allowance {tree.get('allowance_status', 'n/a')}",
    ))

    receipt = seen.get("receipt") or {}
    subject = receipt.get("credentialSubject") if isinstance(receipt.get("credentialSubject"), dict) else {}
    parents = sorted(str(p.get("digestSRI")) for p in subject.get("parents") or [] if isinstance(p, dict))
    digests = sorted(str(d) for d in bill.values() if d)
    checks.append(Check(
        "receipt_commits_children", len(digests) == 2 and parents == digests,
        f"root receipt (HTTP {seen.get('receipt_status')}) parents {parents or 'none'}; "
        f"children's receipts {digests or 'none'}",
    ))

    agree = result.get("agreement") if isinstance(result.get("agreement"), dict) else {}
    # Not critical: two honest sensors can disagree, and saying so is the witness working.
    checks.append(Check(
        "readings_agree", agree.get("agree") is True,
        f"{agree.get('location_km')} km and {agree.get('time_apart_s')} s apart"
        + (f" — {'; '.join(agree.get('reasons') or [])}" if agree.get("reasons") else ""),
        critical=False,
    ))
    return checks


def render(checks: list[Check], hub: str, mode: str, when: str) -> str:
    lines = [f"subcontract canary — {hub} — {mode} — {when}", ""]
    for c in checks:
        mark = "PASS" if c.ok else ("FAIL" if c.critical else "warn")
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    failed = [c for c in checks if not c.ok and c.critical]
    lines += ["", "VERDICT: PASS" if not failed else f"VERDICT: FAIL ({len(failed)} critical check(s))"]
    return "\n".join(lines)


def _api_key(path: str) -> str:
    if path:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return os.environ.get("SUBCONTRACT_CANARY_API_KEY", "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--city", default="Berlin")   # a city GAIA relays (om-wx-01 / om-aq-01)
    parser.add_argument("--allowance", type=float, default=0.01, help="allowance_usd for cost-plus")
    parser.add_argument("--fixed-price", action="store_true",
                        help="send no allowance: the composite pays its readings itself")
    parser.add_argument("--a2a", action="store_true",
                        help="make the root call over A2A 1.0 (POST /a2a SendMessage) instead of /invoke")
    parser.add_argument("--api-key-file", default="",
                        help="file holding the buyer's X-API-Key (else $SUBCONTRACT_CANARY_API_KEY)")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    api_key = _api_key(args.api_key_file)
    if not api_key:
        print("no buyer key: set SUBCONTRACT_CANARY_API_KEY or pass --api-key-file", file=sys.stderr)
        return 2
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "fixed-price" if args.fixed_price else f"cost-plus (allowance ${args.allowance})"
    if args.a2a:
        mode += ", root over A2A"
    seen = observe(args.hub, api_key, city=args.city, allowance_usd=args.allowance,
                   fixed_price=args.fixed_price, http=Http(args.timeout), a2a=args.a2a)
    checks = evaluate(seen, allowance_usd=args.allowance, fixed_price=args.fixed_price)
    failed = [c for c in checks if not c.ok and c.critical]
    if args.json:
        body = seen.get("body") or {}
        print(json.dumps({"hub": args.hub, "mode": mode, "checked_at": when, "ok": not failed,
                          "checks": [c.as_dict() for c in checks],
                          "subcontracting": body.get("subcontracting"),
                          "price_usd": body.get("price_usd"),
                          "a2a_task_id": (seen.get("a2a") or {}).get("task_id")}, indent=2))
    else:
        print(render(checks, args.hub, mode, when))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
