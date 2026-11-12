"""Read-only reachability probe for one hub process. Prints JSON.

Usage (inside the hub's runtime): python3 - [PID]   (default PID 1)
Prints values ONLY for whitelisted non-secret flags (short alnum); every other name -> set/unset.
"""
import json
import os
import re
import sys

pid = sys.argv[1] if len(sys.argv) > 1 else "1"
env = {}
try:
    raw = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
    for item in raw:
        if b"=" in item:
            k, v = item.split(b"=", 1)
            env[k.decode()] = v.decode(errors="replace")
except Exception as exc:  # noqa: BLE001
    env = dict(os.environ)
    env["_environ_error"] = type(exc).__name__
try:
    cwd = os.readlink(f"/proc/{pid}/cwd")
except Exception:  # noqa: BLE001
    cwd = os.getcwd()
cmd = ""
try:
    cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()[:160]
except Exception:  # noqa: BLE001
    pass

VALUE = [
    "AIMARKET_CREDITS_ENABLED", "AIMARKET_TOPUP_ENABLED", "AIMARKET_DEPOSIT_WATCH", "AIMARKET_DEPOSIT_WATCH_INTERVAL_S",
    "AIFACTORY_CRYPTO_ENABLED", "AIMARKET_ESCROW_BRIDGE_ENABLED", "AIMARKET_ESCROW_REQUIRED",
    "AIMARKET_ESCROW_SUBMIT_STRATEGY", "AIMARKET_ESCROW_COLLECT_INTERVAL_S", "AIMARKET_ESCROW_MAX_USD_PER_PASS",
    "AIMARKET_ESCROW_MAX_USD_PER_DAY", "AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "AIMARKET_VERIFY_ENABLED",
    "AIMARKET_VERIFY_MAX_WAIT_S", "AIMARKET_APPEAL_WINDOW_S", "AIMARKET_VERIFY_MIN_PRICE_USD",
    "AIMARKET_X402_ENABLED", "AIMARKET_X402_ACCEPT", "AIMARKET_MARKET_FEE_BPS", "AIMARKET_X402_BRIDGE",
    "AIMARKET_X402_BRIDGE_SELLER_DAY_USD", "AIMARKET_X402_BRIDGE_DAY_USD", "AIMARKET_X402_BRIDGE_MAX_CALL_USD",
    "AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD", "AIMARKET_PUBLISHER_SHARE_BPS", "AIMARKET_SUPPLY_SECURITY_ENABLED",
    "AIMARKET_INVOKE_RATE_PER_MIN", "AIMARKET_REALM", "AIMARKET_PRODUCTION",
]
PRESENCE = [
    "AIMARKET_TOPUP_PAY_TO", "AIMARKET_VERIFY_METIS_URL", "AIMARKET_VERIFY_ROUTES", "AIMARKET_MARKET_SPLITTER",
    "AIMARKET_MARKET_FEE_TO", "AIMARKET_X402_BRIDGE_KEY_FILE", "AIMARKET_X402_BRIDGE_GRANTED_ACCOUNTS",
    "AIMARKET_SELLS_FOR", "AIMARKET_PEER_API_KEYS", "AIMARKET_PEER_PAYMENT_CHANNEL", "AIMARKET_SETTLE_RPC_URL",
    "AIMARKET_ESCROW_SIGNER_URL", "AIMARKET_ESCROW_PRIVATE_KEY", "STRIPE_SECRET_KEY", "AIMARKET_CARD_TOPUP_ENABLED",
]
SAFE = re.compile(r"^[0-9A-Za-z._:-]{0,16}$")
flags = {}
for name in VALUE:
    v = env.get(name)
    if v is None:
        flags[name] = None
    elif SAFE.fullmatch(v):
        flags[name] = v
    else:
        flags[name] = "set(non-simple)"
for name in PRESENCE:
    flags[name] = "set" if (env.get(name) or "").strip() else None

pkg = os.path.join(cwd, "aimarket_hub")
if not os.path.isdir(pkg):
    pkg = ""
    for base in ("/app", "/opt/app"):
        if os.path.isdir(os.path.join(base, "aimarket_hub")):
            pkg = os.path.join(base, "aimarket_hub")
            break
    if not pkg:
        try:
            import aimarket_hub  # noqa: F401
            pkg = os.path.dirname(aimarket_hub.__file__)
        except Exception:  # noqa: BLE001
            pkg = ""

MARKERS = {
    "credits-1 topup dust": "amount_units=1, amount_usd=q.amount_usd",
    "invoke-local-1 pop on non-dict": 'or result.pop("_provenance_receipt", None)',
    "escrow-1/channels-1 receipt lower()": "str(live.receipt_id).lower() == str(auth.receipt_id).lower()",
    "escrow-2 withdraw early return": "if row is None or row.status not in (store.PENDING, store.PLANNED):",
    "federation-1 fed auth w/o credit check": "if fed.escrow_binding and fed_authorized_total > 0:",
    "federation-1 pre-split variant": "fed_escrow_binding and fed_authorized_total > 0",
    "pov-1 intent+output only": '_compose_input(row["intent"], row["output_json"]',
    "pov-2 capture then acex only": "self._accrue_acex(row)",
    "x402-bridge-1 buyer_spent statuses": "status IN ('reserved', 'signed', 'delivered')",
    "L-1 guard0 before deadline": "cannot read the contract's replay flag",
    "escrow-6 per-pass cap": "AIMARKET_ESCROW_MAX_USD_PER_PASS",
    "deposits-x402-2 rpc->payment_invalid": "payment_invalid",
    "pov-5 verify max wait": "AIMARKET_VERIFY_MAX_WAIT_S",
}
hits = {k: [] for k in MARKERS}
version = ""
if pkg:
    for root, _dirs, files in os.walk(pkg):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except Exception:  # noqa: BLE001
                continue
            rel = os.path.relpath(p, pkg)
            for k, m in MARKERS.items():
                if m in text:
                    hits[k].append(rel)
            if rel == "__init__.py":
                mm = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text)
                version = mm.group(1) if mm else ""
prov = False
try:
    import importlib.util
    prov = importlib.util.find_spec("aimarket_provenance") is not None
except Exception:  # noqa: BLE001
    pass
print(json.dumps({"cwd": cwd, "cmd": cmd, "pkg": pkg, "version": version, "provenance_plugin": prov,
                  "flags": flags, "markers": {k: v[:3] for k, v in hits.items()},
                  "env_error": env.get("_environ_error")}, indent=0))
