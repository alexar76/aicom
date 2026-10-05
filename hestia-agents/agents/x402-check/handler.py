"""x402 payment authorization check: who signed it, for what, and will USDC accept it.

x402's `exact` scheme on EVM pays with USDC's EIP-3009 `transferWithAuthorization`: the
buyer signs EIP-712 typed data off chain and anyone may submit it. This recomputes the
EIP-712 digest, recovers the signer with secp256k1, and runs the checks the token contract
itself will run (signer, v, low s, the validity window) plus the ones the seller cares about
(payee, amount, asset, network, the nonce a 402 bound). The domains of seven USDC
deployments were read from the contracts themselves; a wrong `name` (Base mainnet says
"USD Coin", Base Sepolia says "USDC") is the commonest reason a signature fails on chain.

It never touches a chain. Whether the nonce is still unused and the balance covers the
value are named in `not_checked`, not guessed. Pure Python: hashlib has no keccak and the
hearth has no crypto library, so keccak256 and secp256k1 recovery are written out here.
"""

import json

# ------------------------------------------------------------------ keccak256

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_MASK64 = (1 << 64) - 1
_RHO = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14]]
_STEPS = [(x + 5 * y, y + 5 * ((2 * x + 3 * y) % 5), _RHO[x][y])
          for x in range(5) for y in range(5)]


def _keccak_f(a):
    m = _MASK64
    for rc in _RC:
        c0 = a[0] ^ a[5] ^ a[10] ^ a[15] ^ a[20]
        c1 = a[1] ^ a[6] ^ a[11] ^ a[16] ^ a[21]
        c2 = a[2] ^ a[7] ^ a[12] ^ a[17] ^ a[22]
        c3 = a[3] ^ a[8] ^ a[13] ^ a[18] ^ a[23]
        c4 = a[4] ^ a[9] ^ a[14] ^ a[19] ^ a[24]
        d = (
            c4 ^ (((c1 << 1) | (c1 >> 63)) & m),
            c0 ^ (((c2 << 1) | (c2 >> 63)) & m),
            c1 ^ (((c3 << 1) | (c3 >> 63)) & m),
            c2 ^ (((c4 << 1) | (c4 >> 63)) & m),
            c3 ^ (((c0 << 1) | (c0 >> 63)) & m),
        )
        b = [0] * 25
        for src, dst, r in _STEPS:
            v = a[src] ^ d[src % 5]
            b[dst] = (((v << r) | (v >> (64 - r))) & m) if r else v
        for y in (0, 5, 10, 15, 20):
            b0, b1, b2, b3, b4 = b[y], b[y + 1], b[y + 2], b[y + 3], b[y + 4]
            a[y] = b0 ^ (~b1 & b2)
            a[y + 1] = b1 ^ (~b2 & b3)
            a[y + 2] = b2 ^ (~b3 & b4)
            a[y + 3] = b3 ^ (~b4 & b0)
            a[y + 4] = b4 ^ (~b0 & b1)
        a[0] ^= rc


def keccak256(data):
    rate = 136
    state = [0] * 25
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate:
        padded.append(0)
    padded[-1] ^= 0x80
    for off in range(0, len(padded), rate):
        for i in range(17):
            state[i] ^= int.from_bytes(padded[off + 8 * i:off + 8 * i + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


# ------------------------------------------------------------------ secp256k1 recovery

_P = 2 ** 256 - 2 ** 32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8, 1)
_INFINITY = (0, 1, 0)  # Jacobian, z == 0


def _double(pt):
    x, y, z = pt
    if z == 0 or y == 0:
        return _INFINITY
    p = _P
    ysq = y * y % p
    s = 4 * x * ysq % p
    m = 3 * x * x % p
    nx = (m * m - 2 * s) % p
    return (nx, (m * (s - nx) - 8 * ysq * ysq) % p, 2 * y * z % p)


def _add(a, b):
    if a[2] == 0:
        return b
    if b[2] == 0:
        return a
    p = _P
    x1, y1, z1 = a
    x2, y2, z2 = b
    z1z1 = z1 * z1 % p
    z2z2 = z2 * z2 % p
    u1 = x1 * z2z2 % p
    u2 = x2 * z1z1 % p
    s1 = y1 * z2 * z2z2 % p
    s2 = y2 * z1 * z1z1 % p
    if u1 == u2:
        return _double(a) if s1 == s2 else _INFINITY
    h = (u2 - u1) % p
    r = (s2 - s1) % p
    h2 = h * h % p
    h3 = h * h2 % p
    u1h2 = u1 * h2 % p
    nx = (r * r - h3 - 2 * u1h2) % p
    return (nx, (r * (u1h2 - nx) - s1 * h3) % p, h * z1 * z2 % p)


def _two_mul(k1, a, k2, b):
    """k1*a + k2*b in one pass (Shamir's trick)."""
    both = _add(a, b)
    acc = _INFINITY
    for i in range(max(k1.bit_length(), k2.bit_length()) - 1, -1, -1):
        acc = _double(acc)
        bit1 = (k1 >> i) & 1
        bit2 = (k2 >> i) & 1
        if bit1 and bit2:
            acc = _add(acc, both)
        elif bit1:
            acc = _add(acc, a)
        elif bit2:
            acc = _add(acc, b)
    return acc


def _recover(digest, recid, r, s):
    """The public key (x, y) whose signature over `digest` is (r, s, recid), or None."""
    if not (0 < r < _N and 0 < s < _N) or recid not in (0, 1):
        return None
    alpha = (r * r * r + 7) % _P
    beta = pow(alpha, (_P + 1) // 4, _P)
    if beta * beta % _P != alpha:
        return None
    y = beta if beta % 2 == recid else _P - beta
    r_inv = pow(r, -1, _N)
    e = int.from_bytes(digest, "big")
    q = _two_mul((-e * r_inv) % _N, _G, (s * r_inv) % _N, (r, y, 1))
    if q[2] == 0:
        return None
    z_inv = pow(q[2], -1, _P)
    return (q[0] * z_inv * z_inv % _P, q[1] * z_inv * z_inv * z_inv % _P)


# ------------------------------------------------------------------ addresses and hex


def _hex_bytes(value, where, length=None):
    if not isinstance(value, str):
        raise ValueError(where + " must be a hex string")
    text = value[2:] if value[:2] in ("0x", "0X") else value
    if len(text) % 2:
        raise ValueError(where + " has an odd number of hex digits")
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        raise ValueError(where + " is not hex") from None
    if length is not None and len(raw) != length:
        raise ValueError(where + " must be " + str(length) + " bytes, got " + str(len(raw)))
    return raw


def checksum(raw):
    """EIP-55 mixed-case form of a 20-byte address."""
    lower = raw.hex()
    digest = keccak256(lower.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(digest[i], 16) >= 8 else c
                          for i, c in enumerate(lower))


def _address(value, where):
    raw = _hex_bytes(value, where, 20)
    body = value[2:] if value[:2] in ("0x", "0X") else value
    if body != body.lower() and body != body.upper() and "0x" + body != checksum(raw):
        raise ValueError(where + " has a wrong EIP-55 checksum: a mistyped address")
    return raw


def _uint(value, where):
    if isinstance(value, bool):
        raise ValueError(where + " must be an integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            number = int(text, 16) if text[:2] in ("0x", "0X") else int(text, 10)
        except ValueError:
            raise ValueError(where + " is not an integer") from None
    else:
        raise ValueError(where + " must be an integer or a decimal string")
    if number < 0 or number >> 256:
        raise ValueError(where + " does not fit uint256")
    return number


# ------------------------------------------------------------------ USDC and networks

# Read from each contract (name(), version(), decimals(), DOMAIN_SEPARATOR()) on 2026-10-04.
KNOWN_TOKENS = {
    1: ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "USD Coin", "USDC on Ethereum"),
    10: ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", "USD Coin", "USDC on OP Mainnet"),
    137: ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", "USD Coin", "USDC on Polygon PoS"),
    8453: ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "USD Coin", "USDC on Base"),
    42161: ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", "USD Coin", "USDC on Arbitrum One"),
    43114: ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", "USD Coin", "USDC on Avalanche"),
    84532: ("0x036cbd53842c5426634e7929541ec2318f3dcf7e", "USDC", "USDC on Base Sepolia"),
}
NETWORKS = {
    "ethereum": 1, "mainnet": 1, "optimism": 10, "polygon": 137, "base": 8453,
    "arbitrum": 42161, "arbitrum-one": 42161, "avalanche": 43114, "base-sepolia": 84532,
    "avalanche-fuji": 43113, "sepolia": 11155111, "polygon-amoy": 80002,
}


def _chain_id(network, where):
    if isinstance(network, int) and not isinstance(network, bool):
        return network
    if isinstance(network, str):
        text = network.strip().lower()
        if text.startswith("eip155:") and text[7:].isdigit():
            return int(text[7:])
        if text in NETWORKS:
            return NETWORKS[text]
    raise ValueError(where + " is not a known EVM network (a name like base, or eip155:<id>)")


def _decimal(units, places):
    whole, frac = divmod(units, 10 ** places)
    text = str(frac).rjust(places, "0").rstrip("0")
    return str(whole) + ("." + text if text else "")


# ------------------------------------------------------------------ EIP-712

_DOMAIN_TYPEHASH = keccak256(
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
_TYPEHASH = {
    kind: keccak256((kind + "(address from,address to,uint256 value,uint256 validAfter,"
                     "uint256 validBefore,bytes32 nonce)").encode("ascii"))
    for kind in ("TransferWithAuthorization", "ReceiveWithAuthorization")
}


def domain_separator(name, version, chain_id, contract):
    return keccak256(_DOMAIN_TYPEHASH + keccak256(name.encode("utf-8"))
                     + keccak256(version.encode("utf-8")) + chain_id.to_bytes(32, "big")
                     + b"\x00" * 12 + contract)


# ------------------------------------------------------------------ input shapes

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _b64decode(text):
    text = text.strip().replace("-", "+").replace("_", "/").rstrip("=")
    if len(text) % 4 == 1:
        raise ValueError("x_payment is not base64")
    out, bits, count = bytearray(), 0, 0
    for char in text:
        value = _B64.find(char)
        if value < 0:
            raise ValueError("x_payment is not base64")
        bits = (bits << 6) | value
        count += 6
        if count >= 8:
            count -= 8
            out.append((bits >> count) & 0xFF)
            bits &= (1 << count) - 1
    return bytes(out)


def _signature(payload, inner):
    sig = inner.get("signature") if "signature" in inner else payload.get("signature")
    if sig is not None:
        raw = _hex_bytes(sig, "signature")
        if len(raw) == 64:
            raise ValueError("signature is 64 bytes (EIP-2098 compact); USDC takes 65: r, s, v")
        if len(raw) != 65:
            raise ValueError("signature must be 65 bytes (r, s, v), got " + str(len(raw)))
        return int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:64], "big"), raw[64]
    if all(k in payload for k in ("v", "r", "s")):
        v = _uint(payload.get("v"), "v")
        return (int.from_bytes(_hex_bytes(payload.get("r"), "r", 32), "big"),
                int.from_bytes(_hex_bytes(payload.get("s"), "s", 32), "big"), v)
    raise ValueError("send 'signature' (65-byte hex), or v, r and s")


def _unpack(payload):
    """(authorization, signature, network, kind) from any of the shapes buyers send."""
    payment = payload.get("payment")
    if "x_payment" in payload:
        if not isinstance(payload.get("x_payment"), str):
            raise ValueError("x_payment must be the X-PAYMENT header value (base64)")
        try:
            payment = json.loads(_b64decode(payload.get("x_payment")).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("x_payment does not decode to a JSON payment payload") from None
    if payment is not None:
        if not isinstance(payment, dict) or not isinstance(payment.get("payload"), dict):
            raise ValueError("payment must be an x402 payment payload with a 'payload' object")
        inner = payment.get("payload")
        accepted = payment.get("accepted") if isinstance(payment.get("accepted"), dict) else {}
        network = payment.get("network") or accepted.get("network")
        auth = inner.get("authorization")
        sig = _signature({}, inner)
    else:
        auth = payload.get("authorization")
        network = payload.get("network")
        sig = _signature(payload, {})
    if not isinstance(auth, dict):
        raise ValueError("send 'authorization' {from, to, value, validAfter, validBefore, nonce}")
    kind = payload.get("primary_type", "TransferWithAuthorization")
    if kind not in _TYPEHASH:
        raise ValueError("primary_type must be TransferWithAuthorization or "
                         "ReceiveWithAuthorization")
    return auth, sig, network, kind


def _check(checks, name, ok, detail):
    checks.append({"check": name, "ok": ok, "detail": detail})


# A signature that does not recover to `from` was usually made for a slightly different domain.
# The usual slips, tried in order, at most eight recoveries: the other USDC name, version "1",
# the other authorization type, the mainnet/testnet twin of the chain.
_TWINS = {8453: 84532, 84532: 8453}


def _signer_of(kind, name, version, chain_id, contract, fields, recid, r, s):
    separator = domain_separator(name, version, chain_id, contract)
    struct = keccak256(_TYPEHASH[kind] + fields)
    point = _recover(keccak256(b"\x19\x01" + separator + struct), recid, r, s)
    if point is None:
        return None
    return keccak256(point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big"))[12:]


def _diagnose(sender, kind, name, version, chain_id, contract, fields, recid, r, s):
    """What the signature was really made for, when one of the usual slips explains it."""
    other_name = "USDC" if name == "USD Coin" else "USD Coin"
    other_kind = ("ReceiveWithAuthorization" if kind == "TransferWithAuthorization"
                  else "TransferWithAuthorization")
    tries = [(kind, other_name, version, chain_id, contract, "the domain name '" + other_name + "'"),
             (kind, name, "1", chain_id, contract, "version '1'"),
             (kind, other_name, "1", chain_id, contract,
              "the domain name '" + other_name + "' and version '1'"),
             (other_kind, name, version, chain_id, contract, other_kind)]
    twin = _TWINS.get(chain_id)
    if twin in KNOWN_TOKENS:
        twin_contract, twin_name, twin_label = KNOWN_TOKENS[twin]
        for twin_token in (contract, bytes.fromhex(twin_contract[2:])):
            tries.append((kind, twin_name, "2", twin, twin_token, twin_label + "'s domain (chain "
                          + str(twin) + ", name '" + twin_name + "')"))
    for try_kind, try_name, try_version, try_chain, try_contract, label in tries[:8]:
        if (try_kind, try_name, try_version, try_chain, try_contract) == (
                kind, name, version, chain_id, contract):
            continue
        signer = _signer_of(try_kind, try_name, try_version, try_chain, try_contract, fields,
                            recid, r, s)
        if signer == sender:
            return {"signed_for": {"primary_type": try_kind, "name": try_name,
                                   "version": try_version, "chainId": try_chain,
                                   "verifyingContract": checksum(try_contract)},
                    "explains": "from signed this with " + label + "; the token checks it "
                    "against name '" + name + "', version '" + version + "', chain "
                    + str(chain_id) + " — re-sign with those"}
    return None


def handle(payload):
    auth, (r, s, v), network, kind = _unpack(payload)
    requirements = payload.get("requirements")
    if requirements is not None and not isinstance(requirements, dict):
        raise ValueError("requirements must be the 402's accepts entry (an object)")
    requirements = requirements or {}
    extra = requirements.get("extra") if isinstance(requirements.get("extra"), dict) else {}
    domain = payload.get("domain") if isinstance(payload.get("domain"), dict) else {}

    sender = _address(auth.get("from"), "authorization.from")
    receiver = _address(auth.get("to"), "authorization.to")
    value = _uint(auth.get("value"), "authorization.value")
    valid_after = _uint(auth.get("validAfter", 0), "authorization.validAfter")
    valid_before = _uint(auth.get("validBefore"), "authorization.validBefore")
    nonce = _hex_bytes(auth.get("nonce"), "authorization.nonce", 32)

    if "chainId" in domain:
        chain_id = _uint(domain.get("chainId"), "domain.chainId")
    elif network is not None or "network" in requirements:
        chain_id = _chain_id(network if network is not None else requirements.get("network"),
                             "network")
    else:
        raise ValueError("send the network (or domain.chainId): the signature binds the chain")
    known = KNOWN_TOKENS.get(chain_id)
    contract_hex = domain.get("verifyingContract") or requirements.get("asset") or (
        known[0] if known else None)
    if contract_hex is None:
        raise ValueError("send domain.verifyingContract (the token) for chain " + str(chain_id))
    contract = _address(contract_hex, "domain.verifyingContract")
    is_known = bool(known) and contract.hex() == known[0][2:]
    name = domain.get("name") or extra.get("name") or (known[1] if is_known else None)
    version = domain.get("version") or extra.get("version") or ("2" if is_known else None)
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError("send domain.name and domain.version: this token is not one of the "
                         "known USDC deployments, so they cannot be filled in")

    separator = domain_separator(name, version, chain_id, contract)
    fields = (b"\x00" * 12 + sender + b"\x00" * 12 + receiver + value.to_bytes(32, "big")
              + valid_after.to_bytes(32, "big") + valid_before.to_bytes(32, "big") + nonce)
    struct = keccak256(_TYPEHASH[kind] + fields)
    digest = keccak256(b"\x19\x01" + separator + struct)

    checks = []
    recid = v - 27 if v in (27, 28) else v
    _check(checks, "v", v in (27, 28), "v = " + str(v) if v in (27, 28) else
           "v = " + str(v) + "; USDC reverts unless v is 27 or 28")
    _check(checks, "low_s", s <= _N // 2,
           "s is in the lower half" if s <= _N // 2 else
           "s is in the upper half: USDC reverts (EIP-2); use n - s and flip v")
    point = _recover(digest, recid, r, s)
    signer = None
    diagnosis = None
    if point is None:
        _check(checks, "signer", False, "no public key recovers from this signature")
    else:
        signer_raw = keccak256(point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big"))[12:]
        signer = checksum(signer_raw)
        if signer_raw != sender and recid in (0, 1) and s <= _N // 2:
            diagnosis = _diagnose(sender, kind, name, version, chain_id, contract, fields,
                                  recid, r, s)
        _check(checks, "signer", signer_raw == sender,
               "signed by from" if signer_raw == sender else
               ("not valid for this token: " + diagnosis["explains"]) if diagnosis else
               "signed by " + signer + ", not by from — a wrong key, a wrong domain or an "
               "altered field (a contract wallet signing ERC-1271 cannot be checked offline)")
    if is_known:
        problems = []
        if name != known[1]:
            problems.append("name is '" + name + "', the contract's is '" + known[1] + "'")
        if version != "2":
            problems.append("version is '" + version + "', the contract's is '2'")
        _check(checks, "domain", not problems,
               "matches " + known[2] if not problems else "; ".join(problems))
    elif known:
        _check(checks, "domain", None, "verifyingContract is not USDC on chain " + str(chain_id)
               + " (" + known[0] + "); the domain cannot be checked here")
    if valid_before <= valid_after:
        _check(checks, "window", False, "validBefore is not after validAfter: never valid")
    elif "now" in payload:
        now = _uint(payload.get("now"), "now")
        is_open = valid_after < now < valid_before
        _check(checks, "window", is_open,
               "open now" if is_open else ("not valid yet" if now <= valid_after else "expired"))
    else:
        _check(checks, "window", None, "send 'now' (unix seconds) to check the window: valid "
               "after " + str(valid_after) + " and before " + str(valid_before))
    if requirements:
        if "payTo" in requirements:
            pay_to = _address(requirements.get("payTo"), "requirements.payTo")
            _check(checks, "pay_to", pay_to == receiver,
                   "pays the seller" if pay_to == receiver else
                   "to is not the payTo the seller named")
        amount_key = "maxAmountRequired" if "maxAmountRequired" in requirements else "amount"
        if amount_key in requirements:
            amount = _uint(requirements.get(amount_key), "requirements." + amount_key)
            _check(checks, "amount", value >= amount,
                   ("value covers the price" + (" (pays " + str(value - amount)
                                                  + " units more)" if value > amount else ""))
                   if value >= amount else "value is below the price")
        if "asset" in requirements:
            asset = _address(requirements.get("asset"), "requirements.asset")
            _check(checks, "asset", asset == contract,
                   "the asked token" if asset == contract else "signed for another token")
        if "network" in requirements:
            asked = _chain_id(requirements.get("network"), "requirements.network")
            _check(checks, "network", asked == chain_id,
                   "the asked chain" if asked == chain_id else
                   "signed for chain " + str(chain_id) + ", asked " + str(asked))
        bound = extra.get("nonce")
        if bound is not None:
            same = _hex_bytes(bound, "requirements.extra.nonce", 32) == nonce
            _check(checks, "nonce_binding", same,
                   "the nonce the 402 bound" if same else
                   "not the nonce this 402 bound: the seller will refuse it")
    failed = [c["check"] for c in checks if c["ok"] is False]
    out = {
        "verdict": "invalid" if failed else "valid",
        "failed": failed,
        "checks": checks,
        "signer": signer,
        "primary_type": kind,
        "authorization": {
            "from": checksum(sender), "to": checksum(receiver), "value": str(value),
            "validAfter": valid_after, "validBefore": valid_before, "nonce": "0x" + nonce.hex(),
        },
        "domain": {"name": name, "version": version, "chainId": chain_id,
                   "verifyingContract": checksum(contract)},
        "domain_separator": "0x" + separator.hex(),
        "digest": "0x" + digest.hex(),
        "not_checked": ["the nonce is unused on chain (authorizationState)",
                        "the balance of from covers the value",
                        "submission happens before validBefore"],
    }
    if diagnosis:
        out["diagnosis"] = diagnosis
    if is_known:
        out["token"] = known[2]
        out["value_usdc"] = _decimal(value, 6)
    return out
