"""evm.signature.verify@v1: did this address sign this message, be it a key or a smart wallet?

Give `signer` (an address), `signature` (hex) and what was signed: `message` (an EIP-191 personal
message, text or 0x hex bytes), `typed_data` (EIP-712: types, primaryType, domain, message) or
`hash` (a 32-byte digest). `network` is "base" (default), "base-sepolia" or "ethereum".

  - A 65-byte signature (r, s, v) or a 64-byte EIP-2098 one is first recovered here, with no
    network: when the recovered address is `signer`, the key holder signed it (method "ecrecover").
  - Otherwise the agent asks the chain: one eth_call, with no target contract, of the ERC-6492
    universal signature validator (the bytecode viem 2.57.11 uses,
    erc6492SignatureValidatorByteCode, sha256 d46b6085…). It calls the signer's isValidSignature
    (ERC-1271) when the signer is a deployed smart wallet, and for a signature wrapped by ERC-6492
    (ending in the 0x6492… suffix) it first runs the wallet's factory call, so a wallet that is not
    deployed yet verifies too. The call is pinned to one block (`block`, or the latest when the call
    starts) and does not change chain state. Method "erc1271" or "erc6492", and whether the signer
    had code at that block.

Answers valid or invalid with the digest that was checked. A smart wallet decides itself what it
accepts; "valid" means the wallet's own code said so at that block, and it can say otherwise later.
"""

import json

NETWORKS = {
    "base": (8453, "https://mainnet.base.org"),
    "base-sepolia": (84532, "https://sepolia.base.org"),
    "ethereum": (1, "https://ethereum-rpc.publicnode.com"),
}
ERC6492_SUFFIX = bytes.fromhex("6492" * 16)
MAX_TYPED = 64 * 1024


_RC = [
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
]
_MASK64 = (1 << 64) - 1
_RHO = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_STEPS = [
    (x + 5 * y, y + 5 * ((2 * x + 3 * y) % 5), _RHO[x][y]) for x in range(5) for y in range(5)
]


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
            state[i] ^= int.from_bytes(padded[off + 8 * i : off + 8 * i + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


# ------------------------------------------------------------------ secp256k1 recovery

_P = 2**256 - 2**32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
    1,
)
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
    return "0x" + "".join(
        c.upper() if c.isalpha() and int(digest[i], 16) >= 8 else c for i, c in enumerate(lower)
    )


def _address(value, where):
    raw = _hex_bytes(value, where, 20)
    body = value[2:] if value[:2] in ("0x", "0X") else value
    if body != body.lower() and body != body.upper() and "0x" + body != checksum(raw):
        raise ValueError(where + " has a wrong EIP-55 checksum: a mistyped address")
    return raw


VALIDATOR_BYTECODE = (
    "608060405234801561001057600080fd5b5060405161069438038061069483398101604081905261002f9161051e565b"
    "600061003c848484610048565b9050806000526001601ff35b60007f6492649264926492649264926492649264926492"
    "6492649264926492649264926100748361040c565b036101e75760006060808480602001905181019061009291906105"
    "77565b60405192955090935091506000906001600160a01b038516906100b69085906105dd565b600060405180830381"
    "6000865af19150503d80600081146100f3576040519150601f19603f3d011682016040523d82523d6000602084013e61"
    "00f8565b606091505b50509050876001600160a01b03163b60000361016057806101605760405162461bcd60e51b8152"
    "60206004820152601e60248201527f5369676e617475726556616c696461746f723a206465706c6f796d656e74000060"
    "448201526064015b60405180910390fd5b604051630b135d3f60e11b808252906001600160a01b038a1690631626ba7e"
    "90610190908b9087906004016105f9565b602060405180830381865afa1580156101ad573d6000803e3d6000fd5b5050"
    "50506040513d601f19601f820116820180604052508101906101d19190610633565b6001600160e01b03191614945050"
    "505050610405565b6001600160a01b0384163b1561027a57604051630b135d3f60e11b808252906001600160a01b0386"
    "1690631626ba7e9061022790879087906004016105f9565b602060405180830381865afa158015610244573d6000803e"
    "3d6000fd5b505050506040513d601f19601f820116820180604052508101906102689190610633565b6001600160e01b"
    "031916149050610405565b81516041146102df5760405162461bcd60e51b815260206004820152603a60248201526000"
    "8051602061067483398151915260448201527f3a20696e76616c6964207369676e6174757265206c656e677468000000"
    "0000006064820152608401610157565b6102e7610425565b506020820151604080840151845185939260009185919081"
    "1061030c5761030c61065d565b016020015160f81c9050601b811480159061032b57508060ff16601c14155b1561038c"
    "5760405162461bcd60e51b815260206004820152603b602482015260008051602061067483398151915260448201527f"
    "3a20696e76616c6964207369676e617475726520762076616c756500000000006064820152608401610157565b604080"
    "51600081526020810180835289905260ff83169181019190915260608101849052608081018390526001600160a01b03"
    "89169060019060a0016020604051602081039080840390855afa1580156103ea573d6000803e3d6000fd5b5050506020"
    "60405103516001600160a01b0316149450505050505b9392505050565b600060208251101561041d57600080fd5b5080"
    "51015190565b60405180606001604052806003906020820280368337509192915050565b6001600160a01b0381168114"
    "61045857600080fd5b50565b634e487b7160e01b600052604160045260246000fd5b60005b8381101561048c57818101"
    "5183820152602001610474565b50506000910152565b600082601f8301126104a657600080fd5b81516001600160401b"
    "038111156104bf576104bf61045b565b604051601f8201601f19908116603f011681016001600160401b038111828210"
    "17156104ed576104ed61045b565b60405281815283820160200185101561050557600080fd5b61051682602083016020"
    "8701610471565b949350505050565b60008060006060848603121561053357600080fd5b835161053e81610443565b60"
    "20850151604086015191945092506001600160401b0381111561056157600080fd5b61056d86828701610495565b9150"
    "509250925092565b60008060006060848603121561058c57600080fd5b835161059781610443565b6020850151909350"
    "6001600160401b038111156105b357600080fd5b6105bf86828701610495565b60408601519093509050600160016040"
    "1b0381111561056157600080fd5b600082516105ef818460208701610471565b9190910192915050565b828152604060"
    "208201526000825180604084015261061e816060850160208701610471565b601f01601f191691909101606001939250"
    "5050565b60006020828403121561064557600080fd5b81516001600160e01b03198116811461040557600080fd5b634e"
    "487b7160e01b600052603260045260246000fdfe5369676e617475726556616c696461746f72237265636f7665725369"
    "676e6572"
)


# ------------------------------------------------------------------ EIP-191 and EIP-712


def personal_digest(data):
    return keccak256(b"\x19Ethereum Signed Message:\n" + str(len(data)).encode() + data)


DOMAIN_FIELDS = (
    ("name", "string"),
    ("version", "string"),
    ("chainId", "uint256"),
    ("verifyingContract", "address"),
    ("salt", "bytes32"),
)


def _base(kind):
    return kind[: kind.index("[")] if "[" in kind else kind


def _deps(types, primary, found):
    if primary in found or primary not in types:
        return found
    found.append(primary)
    for field in types[primary]:
        _deps(types, _base(field["type"]), found)
    return found


def encode_type(types, primary):
    deps = _deps(types, primary, [])
    deps.remove(primary)
    return "".join(
        name + "(" + ",".join(f["type"] + " " + f["name"] for f in types[name]) + ")"
        for name in [primary] + sorted(deps)
    )


def _int_word(value, bits, signed, where):
    if isinstance(value, bool):
        raise ValueError(where + " must be a number, not a boolean")
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        raise ValueError(where + " is not an integer") from None
    if isinstance(value, float) and value != number:
        raise ValueError(where + " is not an integer")
    low, high = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
    if not low <= number <= high:
        raise ValueError(where + " does not fit " + ("int" if signed else "uint") + str(bits))
    return (number % (1 << 256)).to_bytes(32, "big")


def encode_value(types, kind, value, where):
    if kind.endswith("]"):
        inner, size = kind[: kind.rindex("[")], kind[kind.rindex("[") + 1 : -1]
        if not isinstance(value, list) or (size and len(value) != int(size)):
            raise ValueError(where + " must be a list" + (" of " + size if size else ""))
        return keccak256(
            b"".join(
                encode_value(types, inner, v, where + "[" + str(i) + "]")
                for i, v in enumerate(value)
            )
        )
    if kind in types:
        if not isinstance(value, dict):
            raise ValueError(where + " must be an object (" + kind + ")")
        return hash_struct(types, kind, value, where)
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError(where + " must be a string")
        return keccak256(value.encode("utf-8"))
    if kind == "bytes":
        return keccak256(_hex_bytes(value, where))
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(where + " must be true or false")
        return (1 if value else 0).to_bytes(32, "big")
    if kind == "address":
        return b"\x00" * 12 + _address(value, where)
    if kind.startswith("uint") or kind.startswith("int"):
        signed = kind.startswith("int")
        bits = int(kind[3 if signed else 4 :] or 256)
        if bits % 8 or not 8 <= bits <= 256:
            raise ValueError(where + ": " + kind + " is not a Solidity integer type")
        return _int_word(value, bits, signed, where)
    if kind.startswith("bytes") and kind[5:].isdigit() and 1 <= int(kind[5:]) <= 32:
        raw = _hex_bytes(value, where, int(kind[5:]))
        return raw + b"\x00" * (32 - len(raw))
    raise ValueError(where + ": unknown type " + kind)


def hash_struct(types, primary, data, where):
    type_hash = keccak256(encode_type(types, primary).encode())
    return keccak256(
        type_hash
        + b"".join(
            encode_value(types, f["type"], data.get(f["name"]), where + "." + f["name"])
            for f in types[primary]
        )
    )


def typed_digest(typed):
    if not isinstance(typed, dict):
        raise ValueError("typed_data must be an object: types, primaryType, domain, message")
    types = typed.get("types")
    primary = typed.get("primaryType")
    domain = typed.get("domain") or {}
    if not isinstance(types, dict) or not isinstance(primary, str) or not isinstance(domain, dict):
        raise ValueError(
            "typed_data needs types (object), primaryType (string) and domain (object)"
        )
    for name, fields in types.items():
        if not isinstance(fields, list) or not all(
            isinstance(f, dict)
            and isinstance(f.get("name"), str)
            and isinstance(f.get("type"), str)
            for f in fields
        ):
            raise ValueError("types." + str(name) + " must be a list of {name, type}")
    types = dict(types)
    if "EIP712Domain" not in types:
        types["EIP712Domain"] = [{"name": n, "type": t} for n, t in DOMAIN_FIELDS if n in domain]
    if primary not in types or primary == "EIP712Domain":
        raise ValueError("primaryType " + primary + " is not one of the types")
    separator = hash_struct(types, "EIP712Domain", domain, "domain")
    body = hash_struct(types, primary, typed.get("message") or {}, "message")
    return keccak256(b"\x19\x01" + separator + body), separator.hex(), body.hex()


# ------------------------------------------------------------------ signatures and ABI


def split_signature(raw):
    """(r, s, recid) of a 65-byte or EIP-2098 64-byte signature, or None."""
    if len(raw) == 65:
        v = raw[64]
        recid = v - 27 if v in (27, 28) else v if v in (0, 1) else None
        if recid is None:
            return None
        return int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:64], "big"), recid
    if len(raw) == 64:
        vs = int.from_bytes(raw[32:], "big")
        return int.from_bytes(raw[:32], "big"), vs & ((1 << 255) - 1), vs >> 255
    return None


def recover_address(digest, raw):
    parts = split_signature(raw)
    if parts is None:
        return None
    point = _recover(digest, parts[2], parts[0], parts[1])
    if point is None:
        return None
    return keccak256(point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big"))[12:]


def _word(n):
    return n.to_bytes(32, "big")


def abi_address_bytes32_bytes(address, digest, data):
    """abi.encode(address, bytes32, bytes)."""
    padded = data + b"\x00" * (-len(data) % 32)
    return b"\x00" * 12 + address + digest + _word(96) + _word(len(data)) + padded


def unwrap_6492(raw):
    """(factory, factory calldata, inner signature) of an ERC-6492 wrapped signature, or None."""
    if len(raw) < 32 + 96 or raw[-32:] != ERC6492_SUFFIX:
        return None
    body = raw[:-32]
    try:
        factory = body[12:32]
        offsets = int.from_bytes(body[32:64], "big"), int.from_bytes(body[64:96], "big")
        parts = []
        for off in offsets:
            size = int.from_bytes(body[off : off + 32], "big")
            if off + 32 + size > len(body):
                return None
            parts.append(body[off + 32 : off + 32 + size])
    except (ValueError, IndexError):
        return None
    return factory, parts[0], parts[1]


# The hearth's pool of free Base RPCs (hestia.rpc_pool) is tried first for Base mainnet. A hearth
# without it refuses that name, and the agent then reads the public RPC for the rest of the call.
POOL = "https://base-rpc.hestia.modelmarket.dev"
_POOL_FOR = {"https://mainnet.base.org"}
_no_pool = []


def _post(url, body):
    if url in _POOL_FOR and not _no_pool:
        try:
            reply = fetch(POOL, method="POST", json=body)  # noqa: F821 — the sandbox provides fetch()
        except Exception:  # noqa: BLE001 — the hearth refused the name: no pool on this hearth
            reply = None
        if reply is not None and reply.status not in (0, 429) and reply.status < 500:
            return reply
        _no_pool.append(True)
    return fetch(url, method="POST", json=body)  # noqa: F821


def _rpc_batch(url, calls):
    reply = _post(
        url,
        [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)],
    )
    if not reply.ok:
        raise RuntimeError("the RPC answered HTTP " + str(reply.status))
    body = reply.json()
    if isinstance(body, dict):
        raise RuntimeError("the RPC refused the batch: " + str(body.get("error"))[:160])
    by_id = {item.get("id"): item for item in body if isinstance(item, dict)}
    return [by_id.get(i) or {"error": {"message": "no answer"}} for i in range(len(calls))]


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: signer, signature, and message, typed_data or hash")
    signer = _address(payload.get("signer"), "signer")
    signature = _hex_bytes(payload.get("signature"), "signature")
    if not 64 <= len(signature) <= 16 * 1024:
        raise ValueError("signature must be 64 to 16384 bytes")
    given = [k for k in ("message", "typed_data", "hash") if payload.get(k) is not None]
    if len(given) != 1:
        raise ValueError("give exactly one of message, typed_data or hash")
    out = {"signer": checksum(signer)}
    if given[0] == "hash":
        digest = _hex_bytes(payload["hash"], "hash", 32)
        out["signed"] = "hash"
    elif given[0] == "message":
        text = payload["message"]
        if not isinstance(text, str):
            raise ValueError("message must be text, or 0x-prefixed hex for raw bytes")
        data = _hex_bytes(text, "message") if text[:2] in ("0x", "0X") else text.encode("utf-8")
        digest = personal_digest(data)
        out["signed"] = "EIP-191 personal message (" + str(len(data)) + " bytes)"
    else:
        if len(json.dumps(payload["typed_data"])) > MAX_TYPED:
            raise ValueError("typed_data is larger than 64 KiB")
        digest, separator, struct = typed_digest(payload["typed_data"])
        out["signed"] = "EIP-712 " + str(payload["typed_data"].get("primaryType"))
        out["domain_separator"] = "0x" + separator
        out["struct_hash"] = "0x" + struct
    out["digest"] = "0x" + digest.hex()
    network = str(payload.get("network") or "base").strip().lower()
    if network not in NETWORKS:
        raise ValueError("network must be " + ", ".join(NETWORKS))
    block = payload.get("block")
    if block is not None and (isinstance(block, bool) or not str(block).isdigit()):
        raise ValueError("block must be a block number")

    wrapped = unwrap_6492(signature)
    inner = wrapped[2] if wrapped else signature
    recovered = recover_address(digest, inner)
    if recovered is not None:
        out["recovered"] = checksum(recovered)
    if recovered == signer and not wrapped:
        out.update(
            valid=True,
            verdict="valid",
            method="ecrecover",
            detail="the signature recovers to signer: the key holder signed this digest",
        )
        return out
    if wrapped:
        out["erc6492"] = {
            "factory": checksum(wrapped[0]),
            "factory_calldata_bytes": len(wrapped[1]),
        }

    chain_id, url = NETWORKS[network]
    out["network"] = network
    if block is None:
        head = _rpc_batch(url, [("eth_chainId", []), ("eth_blockNumber", [])])
        if any("error" in item for item in head):
            raise RuntimeError("the RPC did not give the chain head: " + str(head)[:160])
        if int(head[0]["result"], 16) != chain_id:
            raise RuntimeError(
                "the RPC serves chain " + str(int(head[0]["result"], 16)) + ", not " + network
            )
        block = int(head[1]["result"], 16)
    block = int(block)
    tag = hex(block)
    data = (
        "0x"
        + "".join(VALIDATOR_BYTECODE)
        + abi_address_bytes32_bytes(signer, digest, signature).hex()
    )
    answers = _rpc_batch(
        url,
        [
            ("eth_chainId", []),
            ("eth_getCode", ["0x" + signer.hex(), tag]),
            ("eth_call", [{"data": data}, tag]),
        ],
    )
    if "error" in answers[0] or int(answers[0]["result"], 16) != chain_id:
        raise RuntimeError("the RPC does not serve " + network)
    if "error" in answers[1]:
        raise RuntimeError("eth_getCode failed: " + str(answers[1]["error"])[:160])
    code = str(answers[1]["result"] or "0x")
    out["block"] = block
    out["signer_has_code"] = code not in ("0x", "0x0")
    if out["signer_has_code"] and code.lower().startswith("0xef0100") and len(code) == 48:
        out["eip7702_delegate"] = checksum(bytes.fromhex(code[8:]))
    call = answers[2]
    result = str(call.get("result") or "")
    valid = "error" not in call and result.lower() in ("0x01", "0x" + "0" * 63 + "1")
    out["valid"] = valid
    out["verdict"] = "valid" if valid else "invalid"
    if wrapped and not out["signer_has_code"]:
        out["method"] = "erc6492"
    elif out["signer_has_code"]:
        out["method"] = "erc1271"
    else:
        out["method"] = "ecrecover"
    if valid:
        out["detail"] = {
            "erc6492": "the wallet's factory call deploys it (in the call only), and its "
            "isValidSignature accepts the signature",
            "erc1271": "the wallet's isValidSignature accepts the signature at block " + str(block),
            "ecrecover": "the validator recovers signer from the signature",
        }[out["method"]]
    else:
        why = (
            call.get("error", {}).get("message")
            if "error" in call
            else "the validator returned " + result[:20]
        )
        out["detail"] = (
            "signer has no code and the signature does not recover to it"
            if out["method"] == "ecrecover"
            else "the wallet does not accept the signature: " + str(why)[:200]
        )
    return out
