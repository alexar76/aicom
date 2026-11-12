#!/usr/bin/env python3
"""Host-side relay for model.py: the AgentDojo container has no network and never sees the API key.

model.py writes each chat request as a file into RELAY/req; this process forwards it to an
OpenAI-compatible endpoint and writes the reply into RELAY/resp. Only the conversation fields are
forwarded (messages, tools, temperature, max_tokens); the model, the endpoint and thinking-off are
fixed here. It keeps a spend estimate from the token counts and answers {"error": "budget"} once it
reaches --budget-usd, which stops the run. Spend survives restarts (RELAY/usage.jsonl).

usage: relay.py RELAY --env-file FILE --env-name NAME --model M --budget-usd X
       [--price-miss P --price-hit P --price-out P]   (USD per million tokens, for the estimate)
Stops when RELAY/stop exists. Never prints the key.
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FORWARDED = ("messages", "tools", "temperature", "max_tokens")
RETRY_CODES = {408, 409, 429, 500, 502, 503, 504}


def read_key(env_file: str, name: str) -> str:
    for line in Path(env_file).read_text(errors="ignore").splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)", line)
        if m and m.group(1).strip():
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit(f"{name} not found in {env_file}")


class Spend:
    def __init__(self, log: Path, limit: float, miss: float, hit: float, out: float) -> None:
        self.log, self.limit, self.prices = log, limit, (miss, hit, out)
        self.lock = threading.Lock()
        self.usd = 0.0
        if log.exists():
            for line in log.read_text().splitlines():
                self.usd += json.loads(line).get("usd", 0.0)

    def cost(self, usage: dict) -> float:
        miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
        hit = usage.get("prompt_cache_hit_tokens", 0)
        out = usage.get("completion_tokens", 0)
        return (miss * self.prices[0] + hit * self.prices[1] + out * self.prices[2]) / 1e6

    def over(self) -> bool:
        with self.lock:
            return self.usd >= self.limit

    def add(self, rid: str, usage: dict, seconds: float, status: str) -> None:
        usd = self.cost(usage) if usage else 0.0
        with self.lock:
            self.usd += usd
            with self.log.open("a") as f:
                f.write(json.dumps({"t": round(time.time(), 1), "id": rid, "status": status, "seconds": round(seconds, 2),
                                    "miss": usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0)) if usage else 0,
                                    "hit": usage.get("prompt_cache_hit_tokens", 0) if usage else 0,
                                    "out": usage.get("completion_tokens", 0) if usage else 0, "usd": usd}) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("relay")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--env-name", required=True)
    ap.add_argument("--url", default="https://api.deepseek.com/chat/completions")
    ap.add_argument("--model", required=True)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--price-miss", type=float, default=0.30)
    ap.add_argument("--price-hit", type=float, default=0.03)
    ap.add_argument("--price-out", type=float, default=1.20)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    root = Path(a.relay)
    req_dir, resp_dir = root / "req", root / "resp"
    key = read_key(a.env_file, a.env_name)
    spend = Spend(root / "usage.jsonl", a.budget_usd, a.price_miss, a.price_hit, a.price_out)

    def reply(rid: str, data: dict) -> None:
        tmp = resp_dir / f"{rid}.tmp"
        tmp.write_text(json.dumps(data))
        tmp.chmod(0o644)
        tmp.rename(resp_dir / f"{rid}.json")

    def handle(work: Path) -> None:
        rid = work.stem
        started = time.time()
        try:
            req = json.loads(work.read_text())
            body = {k: req[k] for k in FORWARDED if k in req}
            body["model"] = a.model
            body["max_tokens"] = min(int(body.get("max_tokens", 4096)), 8192)
            if "api.deepseek.com" in a.url:  # DeepSeek's own switch; other OpenAI-compatible APIs reject or ignore it
                body["thinking"] = {"type": "disabled"}
            if body.get("tools"):
                body["tool_choice"] = "auto"
            else:
                body.pop("tools", None)
        except (ValueError, TypeError, OSError) as e:
            reply(rid, {"error": f"bad request file: {type(e).__name__}"})
            work.unlink(missing_ok=True)
            return
        if spend.over():
            reply(rid, {"error": "budget"})
            work.unlink(missing_ok=True)
            return
        data, status = None, "ok"
        for attempt in range(6):
            request = urllib.request.Request(a.url, data=json.dumps(body).encode(),
                                             headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=300) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in RETRY_CODES and attempt < 5:
                    time.sleep(min(60, 2 ** attempt * 2))
                    continue
                data, status = {"error": f"http {e.code}: {e.read()[:300].decode(errors='ignore')}"}, f"http {e.code}"
                break
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                if attempt < 5:
                    time.sleep(min(60, 2 ** attempt * 2))
                    continue
                data, status = {"error": f"network: {type(e).__name__}"}, "network"
        spend.add(rid, (data or {}).get("usage") or {}, time.time() - started, status)
        reply(rid, data or {"error": "no reply"})
        work.unlink(missing_ok=True)

    def guarded(work: Path) -> None:
        try:
            handle(work)
        except Exception as e:  # a reply must always come back, or model.py waits until its timeout
            reply(work.stem, {"error": f"relay: {type(e).__name__}"})
            work.unlink(missing_ok=True)

    print(f"relay up: model {a.model}, budget ${a.budget_usd:.2f}, spent so far ${spend.usd:.4f}", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        while not (root / "stop").exists():
            for path in sorted(req_dir.glob("*.json")):
                work = path.with_suffix(".work")
                try:
                    path.rename(work)
                except FileNotFoundError:
                    continue
                pool.submit(guarded, work)
            time.sleep(0.1)
    print(f"relay stopped: spent ${spend.usd:.4f}", flush=True)


if __name__ == "__main__":
    main()
