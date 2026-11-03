"""Second half of sandbox_e2e.py: the refund, on the same database and log.

The restricted test key cannot create refunds (HTTP 403, no Refunds permission), so the refund
goes through the Stripe CLI's own test-mode login; the event still comes back through
`stripe listen` to the app's webhook, which is what is under test. Also refunds the payment an
earlier run left (HISTOR_E2E_REFUND_ALSO), whose rows that run's reset removed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sandbox_e2e import PORT, log, stripe_offset  # noqa: E402


def refund(intent: str) -> str:
    out = subprocess.run(["stripe", "refunds", "create", f"--payment-intent={intent}"], capture_output=True, text=True,
                         env={k: v for k, v in os.environ.items() if k != "STRIPE_API_KEY"}, timeout=60)
    try:
        return json.loads(out.stdout).get("status", "?")
    except ValueError:
        return f"cli exit {out.returncode}: {out.stderr.strip()[:120]}"


def main() -> int:
    sys.path.insert(0, str(Path.cwd()))
    import uvicorn

    os.environ.update({
        "HISTOR_PROFILE": "dev", "HISTOR_DATABASE_URL": os.environ["HISTOR_E2E_PG"], "HISTOR_DATA_DIR": str(HERE / "e2e-data"),
        "HISTOR_PUBLIC_BASE": f"http://127.0.0.1:{PORT}", "HISTOR_OPERATOR_TOKEN": "e" * 32,
        "HISTOR_CRAWL_INTERVAL_S": "0", "HISTOR_REMOTE_INTERVAL_S": "0", "HISTOR_ALLOW_PRIVATE_TARGETS": "1",
        "HISTOR_STRIPE_SECRET_KEY": Path("~/.aimarket-stripe-test-key").expanduser().read_text().strip(),
        "HISTOR_STRIPE_WEBHOOK_SECRET": Path("~/.aimarket-stripe-whsec").expanduser().read_text().strip(),
    })
    from histor import watch_paid
    from histor.app import create_app
    from histor.config import load_settings
    from histor.service import build

    offset = stripe_offset()
    watch_paid.time = types.SimpleNamespace(time=lambda: time.time() - offset, monotonic=time.monotonic)
    services = build(load_settings())
    threading.Thread(target=uvicorn.run, args=(create_app(services),),
                     kwargs={"host": "127.0.0.1", "port": PORT, "log_level": "warning"}, daemon=True).start()
    time.sleep(2)
    with services.store.db.read() as tx:
        payment = tx.one("SELECT * FROM watch_payments WHERE status='paid' ORDER BY paid_at DESC LIMIT 1")
        sub = tx.one("SELECT * FROM watch_subscriptions WHERE id=?", (payment["subscription_id"],))
    log(f"resume: {sub['id']} active until {sub['active_until']}, payment {payment['id']} paid")
    earlier = os.environ.get("HISTOR_E2E_REFUND_ALSO", "").strip()
    if earlier.startswith("pi_"):
        log(f"earlier run's payment refunded via CLI: {refund(earlier)}")
    log(f"refund via CLI: {refund(payment['payment_intent'])}")
    for _ in range(60):
        with services.store.db.read() as tx:
            status = tx.one("SELECT status FROM watch_payments WHERE id=?", (payment["id"],))["status"]
        if status == "refunded":
            break
        time.sleep(2)
    with services.store.db.read() as tx:
        after = tx.one("SELECT status, active_until, note FROM watch_subscriptions WHERE id=?", (sub["id"],))
    state = watch_paid._state(after, watch_paid._now())
    out = watch_paid.deliver_paid(services.store, services.settings)
    log(f"after refund: payment {status}, subscription {state} until {after['active_until']} ({after['note']}); "
        f"delivery pass {out}")
    ok = status == "refunded" and state == "lapsed" and out["subscriptions"] == 0
    log("PASS" if ok else "FAIL")
    if os.environ.get("HISTOR_E2E_HOLD"):
        time.sleep(int(os.environ["HISTOR_E2E_HOLD"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
