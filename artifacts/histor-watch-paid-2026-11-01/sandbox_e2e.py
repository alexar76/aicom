"""HISTOR Watch for teams against the real Stripe sandbox, end to end, on Postgres.

Run from histor/ (it reuses the test suite's fake MCP servers so no real crawl is needed):

    HISTOR_E2E_PG=postgresql://... uv run python ../artifacts/histor-watch-paid-2026-11-01/sandbox_e2e.py

The Stripe test key and webhook secret are read from ~/.aimarket-stripe-test-key and
~/.aimarket-stripe-whsec (never printed); `stripe listen --forward-to
http://127.0.0.1:9497/api/v1/watch/stripe` must run beside it. The script opens a subscription,
writes the checkout URL to the log, waits for the payment (paid by hand in the browser with
the test card), then makes a server change, delivers it to a public HTTPS endpoint, sends a test
event, refunds the payment through the Stripe API and waits for the refund webhook.

This Mac's clock runs about an hour ahead (the servers are NTP-synced): the harness corrects
histor.watch_paid's clock (time.time, which it reads for periods, delivery and the signature
window) by the offset to Stripe's Date header; nothing else in the code under test is touched.
"""

from __future__ import annotations

import email.utils
import json
import os
import shutil
import sys
import threading
import time
import types
import urllib.request
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "sandbox_e2e.log"
PORT = 9497
HOOK = os.environ.get("HISTOR_E2E_HOOK", "https://httpbin.org/post")


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")


def stripe_offset() -> float:
    r = urllib.request.urlopen("https://api.stripe.com/healthcheck", timeout=15)
    return time.time() - email.utils.parsedate_to_datetime(r.headers["Date"]).timestamp()


def main() -> int:
    sys.path.insert(0, str(Path.cwd()))
    import psycopg
    import uvicorn

    pg = os.environ["HISTOR_E2E_PG"]
    with psycopg.connect(pg, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    data = HERE / "e2e-data"
    # A fresh log each run: the database was just reset, and HISTOR refuses a key that signed a longer history.
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir()
    os.environ.update({
        "HISTOR_PROFILE": "dev", "HISTOR_DATABASE_URL": pg, "HISTOR_DATA_DIR": str(data),
        "HISTOR_PUBLIC_BASE": f"http://127.0.0.1:{PORT}", "HISTOR_OPERATOR_TOKEN": "e" * 32,
        "HISTOR_CRAWL_INTERVAL_S": "0", "HISTOR_REMOTE_INTERVAL_S": "0", "HISTOR_ALLOW_PRIVATE_TARGETS": "1",
        "HISTOR_STRIPE_SECRET_KEY": Path("~/.aimarket-stripe-test-key").expanduser().read_text().strip(),
        "HISTOR_STRIPE_WEBHOOK_SECRET": Path("~/.aimarket-stripe-whsec").expanduser().read_text().strip(),
    })
    from histor import watch_paid
    from histor.app import create_app
    from histor.config import load_settings
    from histor.mcpclient import McpReader
    from histor.service import build
    from tests.conftest import Clock, FakeMcp, FakeScanner, make_target, tool

    offset = stripe_offset()
    log(f"mac clock minus Stripe: {offset:.0f} s (corrected in histor.watch_paid only)")
    watch_paid.time = types.SimpleNamespace(time=lambda: time.time() - offset, monotonic=time.monotonic)

    mcp, clock, targets = FakeMcp(), Clock(), []
    settings = load_settings()
    services = build(replace(settings, crawl_workers=2), crawler_kwargs={
        "reader": McpReader(timeout=5, allow_private=True, transport=mcp.transport()),
        "harvest_fn": lambda _url: list(targets), "clock": clock})
    services.scanner = services.crawler.scanner = services.checker.scanner = FakeScanner()
    mcp.tools["/a"] = [tool("get_weather", "Return the weather.")]
    targets.append(make_target("io.example/weather", "/a"))
    services.crawler.run()
    server = services.store.all_targets()[0]["id"]
    app = create_app(services)
    threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "127.0.0.1", "port": PORT, "log_level": "warning"},
                     daemon=True).start()
    time.sleep(2)

    def page(path):
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=30) as r:
            return r.status, r.read().decode()

    def call(method, path, body=None, token=None):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    status, plan = call("GET", "/api/v1/watch/plan")
    log(f"plan: {status} price {plan['priceUsd']} days {plan['days']} card {plan['card']}")
    status, sub = call("POST", "/api/v1/watch/subscriptions", {"watch": [server], "url": HOOK})
    log(f"open: {status} id {sub.get('id')} checkout host {sub.get('checkoutUrl', '')[:40]}")
    (HERE / "checkout_url.txt").write_text(sub["checkoutUrl"] + "\n")
    token = sub["manageToken"]
    (HERE / "manage.txt").write_text(f"http://127.0.0.1:{PORT}/watch#{sub['id']}.{token}\n")
    log("waiting for the test-card payment (checkout_url.txt) …")
    for _ in range(600):
        status, view = call("GET", f"/api/v1/watch/subscriptions/{sub['id']}", token=token)
        if view.get("state") == "active":
            break
        time.sleep(2)
    with services.store.db.read() as tx:
        payment = tx.one("SELECT * FROM watch_payments WHERE subscription_id=?", (sub["id"],))
    log(f"after payment: state {view.get('state')} until {view.get('activeUntil')} payment {payment['status']} "
        f"livemode {payment['livemode']} intent {str(payment['payment_intent'])[:8]}…")
    if view.get("state") != "active":
        log("FAIL: not active")
        return 1

    clock.advance(days=1)
    mcp.tools["/a"] = [tool("get_weather", "Return the weather. Changed for the e2e run.")]
    services.crawler.run()
    out = watch_paid.deliver_paid(services.store, services.settings)
    with services.store.db.read() as tx:
        newest = tx.one("SELECT MAX(id) AS n FROM changes")["n"]
        cur = tx.one("SELECT cursor, attempts FROM webhook_cursors WHERE id=?", (f"watch-{sub['id']}",))
    # The app's own worker may have sent it first (every 20 s); the cursor says either way.
    log(f"delivery to {HOOK}: {out}; cursor {cur['cursor']} of newest change {newest}, failed attempts {cur['attempts']}")
    status, test = call("POST", f"/api/v1/watch/subscriptions/{sub['id']}/test", token=token)
    log(f"test event: {status} {test}")
    status, html = page("/watch")
    log(f"/watch page: {status}, {len(html)} bytes, desk markup {'id=\"view\"' in html}")

    # The restricted test key has no Refunds permission (403); the Stripe CLI's test-mode login
    # refunds, and the event still returns through `stripe listen` to the webhook under test.
    import subprocess
    cli = subprocess.run(["stripe", "refunds", "create", f"--payment-intent={payment['payment_intent']}"], capture_output=True,
                         text=True, env={k: v for k, v in os.environ.items() if k not in ("STRIPE_API_KEY",) and not k.startswith("HISTOR_STRIPE")},
                         timeout=60)
    refund = json.loads(cli.stdout or "{}")
    log(f"refund via Stripe CLI: {refund.get('status')} {refund.get('amount')} {refund.get('currency')}")
    for _ in range(60):
        with services.store.db.read() as tx:
            p = tx.one("SELECT status FROM watch_payments WHERE id=?", (payment["id"],))
        if p["status"] == "refunded":
            break
        time.sleep(2)
    status, view = call("GET", f"/api/v1/watch/subscriptions/{sub['id']}", token=token)
    log(f"after refund: payment {p['status']} state {view.get('state')} until {view.get('activeUntil')} note {view.get('note')}")
    out = watch_paid.deliver_paid(services.store, services.settings)
    log(f"delivery after refund: {out}")
    ok = p["status"] == "refunded" and view.get("state") == "lapsed" and out["subscriptions"] == 0
    log("PASS" if ok else "FAIL")
    if os.environ.get("HISTOR_E2E_HOLD"):
        log("holding the server for the browser check …")
        time.sleep(int(os.environ["HISTOR_E2E_HOLD"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
