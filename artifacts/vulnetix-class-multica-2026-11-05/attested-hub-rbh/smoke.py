"""Inside the new image, no network: the module loads, the call carries routed_by_hub, buyer_identity behaves."""
import dataclasses
import hashlib
import sys
from types import SimpleNamespace

from aimarket_hub import provider_buyer_ref as p
from aimarket_hub.hub_routes import invoke

fields = {f.name: f.default for f in dataclasses.fields(invoke._Call)}
assert fields.get("routed_by_hub") is False, fields.get("routed_by_hub")
call = lambda **kw: SimpleNamespace(**{**dict(sandbox_mode=False, credit_account="", payer_wallet="", x_payment_channel=None), **kw})
local = lambda **kw: SimpleNamespace(**{**dict(x402_accepted=None, reserved=False, hold_rail=""), **kw})
ok = {"ok": True}
cases = [
    (call(credit_account="acct"), local(), "credits:acct"),
    (call(credit_account="acct", routed_by_hub=True), local(), ""),
    (call(x_payment_channel="ch", routed_by_hub=True), local(reserved=True, hold_rail="channel"), ""),
    (call(x_payment_channel="ch"), local(reserved=True, hold_rail="channel"), "channel:ch"),
    (call(payer_wallet="0xAB", routed_by_hub=True), local(x402_accepted=ok), "wallet:0xab"),
    (call(credit_account="acct"), local(), "credits:acct"),
]
for c, l, want in cases:
    got = p.buyer_identity(c, l)
    assert got == want, (c, l, got, want)
for path, expected in zip(sys.argv[1::2], sys.argv[2::2]):
    got = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert got == expected, (path, got, expected)
print("smoke ok: routed_by_hub field, 6 buyer_identity cases, files = build context")
