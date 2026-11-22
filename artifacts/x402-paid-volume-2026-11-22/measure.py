"""Who actually pays x402 sellers: every USDC Transfer on Base to every payee the CDP Bazaar lists, over a window of days.

    python3 measure.py --catalog bazaar.json --out DIR [--days 7] [--rpc https://base-rpc.publicnode.com]

The catalogue is the CDP Bazaar discovery list (scripts/delivery-survey `catalog`). A payee is every distinct payTo of
an `exact` USDC offer on Base (eip155:8453, the token 0x8335…2913). Ours and our sibling ecosystems' payees and hosts are
left out (scripts/delivery-survey/lib.mjs). The window ends at a pinned block (the head minus 12 confirmations when
the run starts) and spans 432,000 blocks a day (Base: 0.2-second blocks; the first run of 2026-11-22 assumed
2-second blocks and covered 16.8 hours, so `--from-block/--to-block` read the missing part into another directory); each payee's logs are read in ranges of at most
50,000 blocks, a range that returns too many is halved. Output: transfers.jsonl (payee, payer, units, block, tx,
log index) and meta.json (window, counts, catalogue facts). Resumable: payees already in transfers.done are skipped.
Read-only: eth_blockNumber, eth_getBlockByNumber, eth_getLogs. Nothing is bought.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BLOCKS_PER_DAY = 432000  # Base blocks are 0.2 s apart (checked 2026-11-22: 3,024,000 blocks = 7 days)
RANGE = 50000
OWN_HOST_SUFFIXES = ("modelmarket.dev", "independentai.network", "attestedmemory.net", "pingblip.com")
OWN_WALLETS = {a.lower() for a in (
    "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a", "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
    "0x40409bE3bAf99f22aA86b2FBaAa99EF2188D5674", "0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef",
    "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec", "0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D",
    "0x12Db8FAC81E5999D2f2087B79e38951571562CF2", "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb")}
UA = "aimarket-x402-paid-volume/1 (+https://modelmarket.dev; reads public chain logs)"


def own_host(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in OWN_HOST_SUFFIXES)


def payees(catalog: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in catalog:
        host = (urlsplit(str(item.get("resource") or "")).hostname or "").lower()
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        for offer in item.get("accepts") or []:
            if not isinstance(offer, dict) or offer.get("scheme") != "exact":
                continue
            if offer.get("network") not in ("base", "eip155:8453") or str(offer.get("asset", "")).lower() != USDC:
                continue
            pay_to = str(offer.get("payTo") or "").lower()
            if len(pay_to) != 42 or int(pay_to, 16) == 0 or pay_to in OWN_WALLETS or own_host(host):
                continue
            row = out.setdefault(pay_to, {"hosts": set(), "listings": 0, "bazaar_calls_30d": 0,
                                           "bazaar_payers_30d_max": 0})
            row["hosts"].add(host)
            row["listings"] += 1
            row["bazaar_calls_30d"] += int(quality.get("l30DaysTotalCalls") or 0)
            row["bazaar_payers_30d_max"] = max(row["bazaar_payers_30d_max"], int(quality.get("l30DaysUniquePayers") or 0))
            break
    return out


class Rpc:
    def __init__(self, url: str, pause: float) -> None:
        self.url, self.pause, self.calls = url, pause, 0

    def batch(self, calls: list[tuple[str, list]]) -> list[dict]:
        body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)])
        for attempt in range(8):
            time.sleep(self.pause)
            req = urllib.request.Request(self.url, data=body.encode(), headers={
                "content-type": "application/json", "user-agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    answers = json.loads(r.read())
                self.calls += len(calls)
                if isinstance(answers, list):
                    by_id = {a.get("id"): a for a in answers}
                    return [by_id.get(i, {"error": {"message": "no answer"}}) for i in range(len(calls))]
                raise RuntimeError(str(answers)[:200])
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                wait = min(60, 2 ** attempt)
                print(f"  rpc retry in {wait}s: {str(exc)[:100]}", file=sys.stderr)
                time.sleep(wait)
        raise SystemExit("the RPC stopped answering; rerun to resume")


def logs_call(pay_to: str, a: int, b: int) -> tuple[str, list]:
    return ("eth_getLogs", [{"address": USDC, "fromBlock": hex(a), "toBlock": hex(b),
                             "topics": [TRANSFER, None, "0x" + pay_to[2:].zfill(64)]}])


def read_group(rpc: Rpc, group: list[str], ranges: list[tuple[int, int]], per_batch: int = 28) -> list[dict]:
    """Every transfer to each payee of the group; ranges of several payees go in one batch."""
    logs, todo = [], [(p, a, b) for p in group for a, b in ranges]
    while todo:
        chunk, todo = todo[:per_batch], todo[per_batch:]
        answers = rpc.batch([logs_call(p, a, b) for p, a, b in chunk])
        for (p, a, b), ans in zip(chunk, answers, strict=True):
            if isinstance(ans.get("result"), list):
                logs.extend((p, log) for log in ans["result"])
            elif b > a:  # too many results, or a refusal: halve the range and ask again
                mid = (a + b) // 2
                todo += [(p, a, mid), (p, mid + 1, b)]
            else:
                raise SystemExit(f"{p}: block {a} cannot be read: {ans.get('error')}")
    out = []
    for pay_to, log in logs:
        if log.get("removed"):
            continue
        out.append({"payee": pay_to, "payer": "0x" + log["topics"][1][-40:].lower(), "units": int(log["data"], 16),
                    "block": int(log["blockNumber"], 16), "tx": log["transactionHash"],
                    "log": int(log["logIndex"], 16)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--rpc", default="https://base-rpc.publicnode.com")
    ap.add_argument("--pause", type=float, default=0.25)
    ap.add_argument("--from-block", type=int, help="explicit window start (with --to-block)")
    ap.add_argument("--to-block", type=int, help="explicit window end")
    ap.add_argument("--shard", default="0/1", help="i/n: this process reads the payees whose index %% n == i")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text())
    sellers = payees(catalog)
    rpc = Rpc(args.rpc, args.pause)
    meta_path = args.out / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        head = args.to_block or int(rpc.batch([("eth_blockNumber", [])])[0]["result"], 16) - 12
        start = args.from_block or head - BLOCKS_PER_DAY * args.days + 1
        blocks = rpc.batch([("eth_getBlockByNumber", [hex(start), False]), ("eth_getBlockByNumber", [hex(head), False])])
        meta = {"catalog_listings": len(catalog), "payees": len(sellers), "days": args.days,
                "from_block": start, "to_block": head,
                "from_time": int(blocks[0]["result"]["timestamp"], 16), "to_time": int(blocks[1]["result"]["timestamp"], 16),
                "rpc": args.rpc, "token": USDC, "chain": "eip155:8453"}
        meta_path.write_text(json.dumps(meta, indent=1))
    ranges = [(a, min(a + RANGE - 1, meta["to_block"])) for a in range(meta["from_block"], meta["to_block"] + 1, RANGE)]
    shard, shards = (int(x) for x in args.shard.split("/"))
    suffix = "" if shards == 1 else f".{shard}"
    done_path, out_path = args.out / f"transfers{suffix}.done", args.out / f"transfers{suffix}.jsonl"
    done = set()
    for mark in args.out.glob("transfers*.done"):  # every shard's finished payees, and an earlier unsharded run's
        done |= set(mark.read_text().split())
    (args.out / "payees.json").write_text(json.dumps(
        {k: {**v, "hosts": sorted(v["hosts"])} for k, v in sorted(sellers.items())}, indent=0))
    started = time.time()
    todo = [p for i, p in enumerate(sorted(sellers)) if i % shards == shard and p not in done]
    with out_path.open("a") as out, done_path.open("a") as marks:
        for n in range(0, len(todo), 4):
            group = todo[n:n + 4]
            for row in read_group(rpc, group, ranges):
                out.write(json.dumps(row) + "\n")
            out.flush()
            marks.write("".join(p + "\n" for p in group))
            marks.flush()
            if n % 100 == 0:
                print(f"{len(done) + n}/{len(sellers)} payees, {rpc.calls} RPC calls, {time.time() - started:.0f}s",
                      file=sys.stderr)
    print(f"done: {len(sellers)} payees, window {meta['from_block']}..{meta['to_block']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
