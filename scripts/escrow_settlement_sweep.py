#!/usr/bin/env python3
"""Turn signed debit authorizations into on-chain transactions, on a schedule.

Until this existed, every payment needed an operator: a buyer's EIP-712 authorization sat
in the hub's store until somebody remembered to run `escrow_bridge.cli submit --yes`. The
earning side of the ecosystem was automatic and the collecting side was a human habit —
which means revenue quietly accrued as a promise instead of money, and nothing would ever
have said so out loud.

Why a sweep is safe to automate, in the order the guards apply:

* the hub holds **no key** (`private_key_set=false`); signing happens in HORKOS on another
  host, behind its own policy — rules, caps, cooldowns, a monotone clock;
* HORKOS signs **only** `debitChannel`, so a bug here cannot move funds any other way;
* replays are impossible twice over — HORKOS is idempotent on
  `(chain_id, escrow, receipt_id)`, and the escrow's own `usedReceipts` mapping refuses a
  receipt it has already seen;
* the amount is fixed by the buyer's signature. This script chooses *when*, never *what*.

It publishes its result to the same public directory as the payment canary, so the alerter
on the other host can see it over HTTPS — a collector that stops collecting has to be
visible, or automating it has just moved the silence somewhere new.

    scripts/escrow_settlement_sweep.py --dry-run     # `plan`: decide, send nothing
    scripts/escrow_settlement_sweep.py               # `submit --yes`: broadcast
    scripts/escrow_settlement_sweep.py --publish /var/www/verify.modelmarket.dev/settlement.json

Stdlib only, and it talks to the hub through `docker exec` rather than importing it: the
running image is not this checkout (see docs/operations-traps.md T-6).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import time
from typing import Any

CONTAINER = os.environ.get("AIMARKET_HUB_CONTAINER", "modelmarket-hub")
CLI = ["python", "-m", "aimarket_hub.escrow_bridge.cli"]

# A sweep that hangs is worse than one that fails: the timer would pile up instances.
TIMEOUT_S = 240.0


def _extract_json(text: str) -> Any:
    """The CLI prints warnings before its JSON. Take the first complete object.

    A naive `json.loads(stdout)` fails the moment the hub logs a deprecation notice, and
    the failure looks exactly like "the bridge is broken" — so this tolerates noise
    around the payload but never guesses at its content.
    """
    start = text.find("{")
    if start < 0:
        raise ValueError(f"no JSON object in output: {text[:200]!r}")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def run_cli(*args: str, timeout: float = TIMEOUT_S) -> tuple[int, Any, str]:
    """(exit code, parsed JSON or None, stderr/parse error)."""
    cmd = ["docker", "exec", CONTAINER, *CLI, *args, "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, None, f"timed out after {timeout:.0f}s: {' '.join(args)}"
    except FileNotFoundError:
        return 127, None, "docker not found on PATH"
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    try:
        return proc.returncode, _extract_json(combined), proc.stderr[-400:]
    except ValueError as exc:
        hint = ""
        if proc.returncode == 137:
            hint = " (exit 137 — process likely OOM-killed; retry or raise hub container memory)"
        return proc.returncode, None, f"{exc}{hint}; stderr={proc.stderr[-300:]}"


def pending_units(status: Any) -> int:
    """Unsubmitted value the hub is still owed, in token units.

    The number lives under `store`, not at the top level — `status --json` returns
    `{config, signer, store: {by_status, unsubmitted_units, ...}, queue}`. Reading it from
    the root returned 0 for every input, so the sweep would have found an empty queue
    forever and never submitted anything, while reporting success. Written against the
    real payload, not the shape it seemed like it should have.

    Reads the published field rather than re-deriving it from `by_status`: those two
    disagreed once, when an abandoned row's units stayed in the total.
    """
    if not isinstance(status, dict):
        return 0
    for scope in (status.get("store"), status):
        if not isinstance(scope, dict):
            continue
        for key in ("unsubmitted_units", "pending_units"):
            if key in scope:
                try:
                    return int(scope.get(key) or 0)
                except (TypeError, ValueError):
                    return 0
    return 0


def broadcast_blocked(status: Any) -> str:
    """"" when the bridge may broadcast, else why it may not.

    Without this the sweep would run every fifteen minutes against a bridge whose
    `may_broadcast` is false — planning politely, collecting nothing, and reporting an
    empty queue as success.
    """
    config = status.get("config") if isinstance(status, dict) else None
    if not isinstance(config, dict):
        return ""
    if not config.get("enabled"):
        return "bridge disabled (AIMARKET_ESCROW_BRIDGE_ENABLED)"
    reason = str(config.get("blocked_reason") or "").strip()
    if reason:
        return f"blocked: {reason}"
    if not config.get("may_broadcast"):
        return (f"may_broadcast=false (strategy={config.get('strategy')!r}) — "
                "the confirm phrase or the strategy is missing")
    return ""


# ── uncollected money: channels the chain still holds ────────────────────────────────────

# `getChannel(bytes32)`. Hardcoded because this runs on a bare host with no eth libraries;
# tests/test_escrow_settlement_sweep.py re-derives it from the signature with eth_utils and
# fails if it ever drifts.
GET_CHANNEL_SELECTOR = "0x831c2b82"
BASE_RPCS = ("https://base-rpc.publicnode.com", "https://mainnet.base.org",
             "https://base.drpc.org")


def _rpc(method: str, params: list, timeout: float = 20.0) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    last = ""
    for url in BASE_RPCS:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json",
                         "User-Agent": "aicom-settlement-sweep/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read(200_000).decode("utf-8", "replace"))
            if "result" in body:
                return body["result"]
            last = str(body.get("error"))
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"every Base endpoint failed: {last[:160]}")


def decode_channel(raw: str) -> dict[str, Any]:
    """The escrow's Channel struct, as `getChannel` returns it."""
    words = [raw[2 + i * 64: 2 + (i + 1) * 64] for i in range(9)]
    return {
        "depositor": "0x" + words[0][24:],
        "hub": "0x" + words[1][24:],
        "balance_units": int(words[4], 16),
        "used_units": int(words[5], 16),
        "expires_at": int(words[6], 16),
        "status": int(words[8], 16),   # 0 Open, 1 Settled, 2 Refunded, 3 Expired
    }


def collectable(channels: list[dict[str, Any]], *, now: float) -> dict[str, Any]:
    """Money the contract holds for us that only needs someone to pay gas.

    A channel keeps its `usedAmount` until somebody calls `settleChannel` (depositor or
    hub) or, past expiry, `expireChannel` — which anyone may call and which pays the hub
    the same amount. So nothing here is at risk of being lost; it is revenue sitting in
    escrow because no transaction has asked for it yet. Reporting it is what turns that
    from invisible into a decision.
    """
    open_channels = [c for c in channels if c["status"] == 0 and c["used_units"] > 0]
    expired = [c for c in open_channels if c["expires_at"] and now > c["expires_at"]]
    return {
        "open_with_earnings": len(open_channels),
        "expired_uncollected": len(expired),
        "collectable_units": sum(c["used_units"] for c in open_channels),
        "collectable_usd": round(sum(c["used_units"] for c in open_channels) / 1_000_000, 6),
        "expired_usd": round(sum(c["used_units"] for c in expired) / 1_000_000, 6),
    }


def read_escrow_channels(escrow: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Every escrow channel the hub knows about, read from the chain."""
    errors: list[str] = []
    code, out, err = run_cli_raw(
        "python3", "-c",
        "import sqlite3,json;c=sqlite3.connect('data/channels.db');"
        "print(json.dumps([r[0] for r in c.execute("
        "\"SELECT DISTINCT escrow_channel FROM channels WHERE COALESCE(escrow_channel,'')<>''\")]))")
    if out is None:
        return [], [f"could not list escrow channels (exit {code}): {err}"]
    channels = []
    for cid in out if isinstance(out, list) else []:
        if not (isinstance(cid, str) and cid.startswith("0x") and len(cid) == 66):
            continue
        try:
            raw = _rpc("eth_call", [{"to": escrow,
                                     "data": GET_CHANNEL_SELECTOR + cid[2:]}, "latest"])
            channel = decode_channel(raw)
            channel["channel_id"] = cid
            channels.append(channel)
        except Exception as exc:
            errors.append(f"{cid[:12]}…: {type(exc).__name__}")
    return channels, errors


def run_cli_raw(*cmd: str, timeout: float = 60.0) -> tuple[int, Any, str]:
    """Run an arbitrary command in the hub container and parse its JSON output."""
    full = ["docker", "exec", CONTAINER, *cmd]
    try:
        proc = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, None, "timed out"
    except FileNotFoundError:
        return 127, None, "docker not found on PATH"
    try:
        start = proc.stdout.find("[")
        if start < 0:
            raise ValueError("no JSON array in output")
        return proc.returncode, json.JSONDecoder().raw_decode(proc.stdout[start:])[0], ""
    except ValueError as exc:
        return proc.returncode, None, f"{exc}; stderr={proc.stderr[-200:]}"


# ── collecting: ask the signer to expire what is already ours ────────────────────────────

EXPIRE_SELECTOR = "0x42161b74"   # expireChannel(bytes32); tests re-derive it from the
                                 # signature and fail if it drifts.


def signer_endpoint() -> tuple[str, str]:
    """(url, token) for the policy signer, read from the hub's own environment.

    The token stays on this host: it is already in the hub container that runs here, and
    the alternative — a second copy in a file next to this script — is one more place for
    it to leak from.
    """
    out = {}
    for name in ("AIMARKET_ESCROW_SIGNER_URL", "AIMARKET_ESCROW_SIGNER_TOKEN"):
        proc = subprocess.run(["docker", "exec", CONTAINER, "printenv", name],
                              capture_output=True, text=True, timeout=30)
        out[name] = proc.stdout.strip()
    return out["AIMARKET_ESCROW_SIGNER_URL"], out["AIMARKET_ESCROW_SIGNER_TOKEN"]


def ask_signer_to_expire(url: str, token: str, escrow: str, channel_id: str,
                         timeout: float = 60.0) -> tuple[bool, str]:
    """(collected, detail). The signer's policy is the authority on whether to sign.

    This function deliberately does not second-guess it: it sends the call and reports the
    answer. Every reason the signer can refuse for — not ours, not expired, nothing owed,
    already in flight, daily gas limit — is a decision that belongs next to the key, not
    in a sweep script that could be edited without review.
    """
    body = json.dumps({"transaction": {
        "to": escrow,
        "data": EXPIRE_SELECTOR + channel_id[2:],
        "chainId": 8453,
        "gas": 120_000,
        "value": 0,
    }}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                 "User-Agent": "aicom-settlement-sweep/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            answer = json.loads(resp.read(20_000).decode("utf-8", "replace"))
        return True, str(answer.get("tx_hash", ""))
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read(4_000).decode("utf-8", "replace")).get("error", "")
        except Exception:
            reason = f"HTTP {exc.code}"
        return False, f"{channel_id[:12]}…: {reason}"
    except Exception as exc:
        return False, f"{channel_id[:12]}…: {type(exc).__name__}"


def collect_expired(channels: list, *, escrow: str, now: float) -> dict:
    """Ask for every expired channel that owes us something. Never raises."""
    due = [c for c in channels
           if c["status"] == 0 and c["used_units"] > 0
           and c["expires_at"] and now > c["expires_at"]]
    if not due:
        return {"attempted": 0, "collected": 0, "tx_hashes": [], "refusals": []}
    try:
        url, token = signer_endpoint()
    except Exception as exc:
        return {"attempted": 0, "collected": 0, "tx_hashes": [],
                "refusals": [f"signer endpoint unreadable: {type(exc).__name__}"]}
    if not url or not token:
        return {"attempted": 0, "collected": 0, "tx_hashes": [],
                "refusals": ["no signer url/token in the hub environment"]}
    hashes, refusals = [], []
    for channel in due:
        ok, detail = ask_signer_to_expire(url, token, escrow, channel["channel_id"])
        (hashes if ok else refusals).append(detail)
    return {"attempted": len(due), "collected": len(hashes), "tx_hashes": hashes,
            "refusals": refusals}


def summarize(before: Any, result: Any, after: Any, *, dry_run: bool,
              errors: list[str], now: float | None = None,
              uncollected: dict[str, Any] | None = None) -> dict[str, Any]:
    """The published record. Pure, so its verdict is testable without docker."""
    now = time.time() if now is None else now
    outcomes = {}
    if isinstance(result, dict) and isinstance(result.get("outcomes"), dict):
        outcomes = {str(k): int(v) for k, v in result["outcomes"].items()}
    scanned = int(result.get("scanned") or 0) if isinstance(result, dict) else 0

    pending_before = pending_units(before)
    pending_after = pending_units(after)
    submitted = outcomes.get("submitted", 0) + outcomes.get("confirmed", 0)
    failed = sum(v for k, v in outcomes.items()
                 if k not in ("submitted", "confirmed", "skipped", "planned"))

    # "Nothing to do" and "tried and left money on the table" must not look alike. A sweep
    # is only ok when the queue is empty afterwards — or when it never intended to send.
    ok = not errors and (dry_run or pending_after == 0)

    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "mode": "plan" if dry_run else "submit",
        "ok": ok,
        "scanned": scanned,
        "submitted": submitted,
        "failed": failed,
        "outcomes": outcomes,
        "pending_units_before": pending_before,
        "pending_units_after": pending_after,
        "pending_usd_after": round(pending_after / 1_000_000, 6),
        "by_status": ((before or {}).get("store") or {}).get("by_status")
                     if isinstance(before, dict) else None,
        # Money the chain already holds for us, waiting only for somebody to pay gas.
        # Separate from `pending_*`, which is about authorizations not yet broadcast: this
        # is about debits that ARE on chain and have not been swept out of escrow.
        "uncollected": uncollected or {},
        "errors": errors,
    }


def sweep(*, dry_run: bool, collect: bool = False) -> dict[str, Any]:
    errors: list[str] = []

    code, before, err = run_cli("status")
    if before is None:
        errors.append(f"status failed (exit {code}): {err}")
        return summarize(None, None, None, dry_run=dry_run, errors=errors)

    # A bridge that cannot broadcast is not an empty queue, and must not read as one.
    blocked = broadcast_blocked(before)
    if blocked and not dry_run:
        errors.append(blocked)
        return summarize(before, None, before, dry_run=dry_run, errors=errors)

    result: Any = None
    confirm_result: Any = None
    if not dry_run:
        # Submitted-but-unconfirmed rows count as unsubmitted; clear them before broadcast.
        c_code, confirm_result, c_err = run_cli("confirm", "--limit", "20")
        if confirm_result is None and c_code not in (0, 124, 127):
            errors.append(f"confirm failed (exit {c_code}): {c_err}")
        code, before, err = run_cli("status")
        if before is None:
            errors.append(f"post-confirm status failed (exit {code}): {err}")

    pending = pending_units(before)
    if pending > 0 or dry_run:
        # `plan` is the CLI's own dry run; `submit --yes` is the only broadcasting call,
        # and the four opt-in gates (enabled / strategy / confirm phrase / --yes) all have
        # to be in place already — this script sets none of them.
        # Small `--limit` per tick avoids OOM on heavy hub cold paths (exit 137).
        submit_args = ["plan"] if dry_run else ["submit", "--yes", "--limit", "5"]
        code, result, err = run_cli(*submit_args)
        if result is None:
            errors.append(f"{submit_args[0]} failed (exit {code}): {err}")
        if not dry_run and pending > 0 and result is not None:
            c_code, confirm_result, c_err = run_cli("confirm", "--limit", "20")
            if confirm_result is None and c_code not in (0, 124, 127):
                errors.append(f"post-submit confirm failed (exit {c_code}): {c_err}")

    code, after, err = run_cli("status")
    if after is None:
        errors.append(f"post-status failed (exit {code}): {err}")

    # Read the chain last, and never let it fail the sweep: submission is the job, and a
    # flaky public RPC must not turn a successful collection into a red run.
    uncollected: dict[str, Any] = {}
    escrow = ((before or {}).get("config") or {}).get("contract") or ""
    if escrow:
        channels, read_errors = read_escrow_channels(escrow)
        uncollected = collectable(channels, now=time.time())
        uncollected["channels_read"] = len(channels)
        if read_errors:
            uncollected["read_errors"] = read_errors[:4]
        # Ask the signer to sweep what is past expiry. Its policy decides; this only
        # asks, and a refusal is information rather than a failure of the sweep.
        if collect and not dry_run and uncollected.get("expired_uncollected"):
            uncollected["collect"] = collect_expired(channels, escrow=escrow,
                                                     now=time.time())
            after, _ = read_escrow_channels(escrow)
            uncollected.update({k: v for k, v in collectable(after, now=time.time()).items()
                                if k in ("expired_uncollected", "expired_usd",
                                         "collectable_usd", "collectable_units",
                                         "open_with_earnings")})

    return summarize(before, result, after, dry_run=dry_run, errors=errors,
                     uncollected=uncollected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--dry-run", action="store_true",
                        help="run the CLI's `plan` instead of `submit --yes`")
    parser.add_argument("--publish", metavar="PATH", default="",
                        help="write the report here for the alerter to read over HTTPS")
    parser.add_argument("--collect", action="store_true",
                        help="also ask the signer to expireChannel anything past its "
                             "expiry that still owes us — the signer's policy decides")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = sweep(dry_run=args.dry_run, collect=args.collect)

    if args.json:
        print(json.dumps(report, indent=1))
    else:
        unc = report.get("uncollected") or {}
        print(f"{report['mode']}: scanned {report['scanned']}, submitted "
              f"{report['submitted']}, failed {report['failed']}, "
              f"pending ${report['pending_usd_after']:.6f}, "
              f"uncollected ${unc.get('collectable_usd', 0):.6f} "
              f"({unc.get('expired_uncollected', 0)} expired)"
              + (f" | errors: {'; '.join(report['errors'])}" if report["errors"] else ""))

    if args.publish:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.publish)), exist_ok=True)
            tmp = f"{args.publish}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=1)
                fh.write("\n")
            os.replace(tmp, args.publish)
        except OSError as exc:
            # A publish failure must not read like a settlement failure: the sweep may
            # have done its job perfectly. Say which one broke.
            print(f"warning: could not publish to {args.publish}: {exc}", file=sys.stderr)
            return 2

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
