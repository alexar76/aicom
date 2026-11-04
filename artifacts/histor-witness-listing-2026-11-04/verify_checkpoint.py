"""verify_checkpoint.py CHECKPOINT_FILE — check a C2SP tlog checkpoint's log signature and witness cosignatures.

Independent of HISTOR's code: c2sp.org/signed-note (Ed25519, key type 0x01) for the log, c2sp.org/tlog-cosignature
(cosignature/v1, key type 0x04) for witnesses. Key hash = SHA-256(name || "\\n" || type || public key)[:4].
"""
import base64
import hashlib
import struct
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VKEYS = [
    "histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU",
    "witness.stagemole.eu+67f7aea0+BEqSG3yu9YrmcM3BHvQYTxwFj3uSWakQepafafpUqklv",
    "markovianprotocol.com/witness+41b8827f+BJKLl8rBYM0oUxSaWh9rjTldTprEpYj/SWVIGgacA9XC",
    "witness.gdbsecurity.com+a1398f73+BAbIijGonVIk3ikDac+KKlSm1ELHOzcddhjjB6zB4BNf",
    "staging.witness.transparency.goog/ring-any-bells+2e1a8dc9+BG5JTpLc3FJtwzgh1Uv+Qelz9qeOH2bfWjS1s0s+y4rL",
]


def parse_vkey(vkey):
    name, hexhash, rest = vkey.split("+", 2)  # base64 may contain '+': split on the first two only
    raw = base64.b64decode(rest)
    kind, pub = raw[0], raw[1:]
    computed = hashlib.sha256(name.encode() + b"\n" + raw).digest()[:4]
    assert computed.hex() == hexhash, f"key hash mismatch for {name}"
    return name, kind, computed, Ed25519PublicKey.from_public_bytes(pub)


keys = {}
for v in VKEYS:
    name, kind, khash, pub = parse_vkey(v)
    keys[(name, khash)] = (kind, pub)

text = open(sys.argv[1], encoding="utf-8").read()
body, sigs = text.split("\n\n", 1)
note = body + "\n"
print("origin", body.split("\n")[0], "size", body.split("\n")[1])
ok = 0
for line in sigs.strip().split("\n"):
    assert line.startswith("— "), line
    name, b64 = line[2:].rsplit(" ", 1)
    raw = base64.b64decode(b64)
    khash = raw[:4]
    if (name, khash) not in keys:
        print("unknown key", name)
        continue
    kind, pub = keys[(name, khash)]
    if kind == 0x01:
        pub.verify(raw[4:], note.encode())
        print(f"ok  log signature        {name}")
    elif kind == 0x04:
        (ts,) = struct.unpack(">Q", raw[4:12])
        msg = f"cosignature/v1\ntime {ts}\n".encode() + note.encode()
        pub.verify(raw[12:], msg)
        print(f"ok  witness cosignature  {name}  time {ts}")
    else:
        print("unexpected key type", kind, name)
        continue
    ok += 1
print(f"{ok} signature(s) verified")
