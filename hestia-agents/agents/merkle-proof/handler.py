"""Merkle roots and proofs: build them, and check one you were handed.

Two families, because the world uses two:

  rfc6962       Certificate Transparency / RFC 9162 (HISTOR, Sigstore Rekor, Trillian).
                leaf = SHA-256(0x00 || data), node = SHA-256(0x01 || left || right), the tree
                split at the largest power of two. Inclusion AND consistency proofs: the
                second one is how you know a log was only appended to, never rewritten.
  openzeppelin  Solidity's MerkleProof.verify: leaf = keccak256(keccak256(abi.encode(values)))
                (StandardMerkleTree) or a bytes32 you hashed yourself (SimpleMerkleTree),
                node = keccak256 of the SORTED pair. Airdrops, allowlists, claim sets.

A proof you were handed is checked by recomputing the root from it, never by trusting a
`valid` flag that came with it. Everything is a pure function of the payload.
"""

import hashlib

MAX_RFC6962_LEAVES = 20000
MAX_OZ_LEAVES = 1024  # keccak256 is pure Python here: ~3 hashes per leaf
MAX_PROOF = 64

# ------------------------------------------------------------------ keccak256
# Ethereum's Keccak-256 (0x01 padding, not SHA3-256's 0x06): hashlib has no keccak.

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
# (source lane, destination lane, rotation): rho and pi in one pass, lanes indexed x + 5y.
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


# ------------------------------------------------------------------ input helpers


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


def _index(payload, name):
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("'" + name + "' must be a non-negative integer")
    return value


def _hash_list(values, where):
    if not isinstance(values, list):
        raise ValueError(where + " must be a list of 32-byte hex hashes")
    if len(values) > MAX_PROOF:
        raise ValueError(where + " is longer than " + str(MAX_PROOF) + " hashes")
    return [_hex_bytes(v, where + "[" + str(i) + "]", 32) for i, v in enumerate(values)]


# ------------------------------------------------------------------ JCS (for leaf_format json)

_SHORT_ESCAPES = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r",
                  0x22: '\\"', 0x5C: "\\\\"}
_MAX_SAFE_INTEGER = 9007199254740991


def _jcs_string(text):
    out = ['"']
    for char in text:
        point = ord(char)
        short = _SHORT_ESCAPES.get(point)
        if short is not None:
            out.append(short)
        elif point < 0x20:
            out.append("\\u" + format(point, "04x"))
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _jcs(value, where):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if value > _MAX_SAFE_INTEGER or value < -_MAX_SAFE_INTEGER:
            raise ValueError("integer at " + where + " is past 2^53-1; send it as a string")
        return str(value)
    if isinstance(value, float):
        raise ValueError("number at " + where + " is not an integer; JCS floats do not "
                         "reproduce across languages")
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, list):
        items = [_jcs(v, where + "[" + str(i) + "]") for i, v in enumerate(value)]
        return "[" + ",".join(items) + "]"
    if isinstance(value, dict):
        for name in value:
            if not isinstance(name, str):
                raise ValueError("object key at " + where + " must be a string")
        names = sorted(value, key=lambda n: n.encode("utf-16-be"))
        return "{" + ",".join(_jcs_string(n) + ":" + _jcs(value[n], where + "." + n)
                              for n in names) + "}"
    raise ValueError("unsupported value at " + where)


# ------------------------------------------------------------------ RFC 6962 / 9162


def _leaf_data(value, fmt, where):
    if fmt == "hex":
        return _hex_bytes(value, where)
    if fmt == "utf8":
        if not isinstance(value, str):
            raise ValueError(where + " must be a string for leaf_format utf8")
        return value.encode("utf-8")
    if fmt == "json":
        return _jcs(value, where).encode("utf-8")
    raise ValueError("leaf_format must be hex, utf8 or json")


def _ct_leaf(data):
    return hashlib.sha256(b"\x00" + data).digest()


def _ct_node(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n):
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def _mth(hashes, start, end):
    n = end - start
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashes[start]
    k = _split(n)
    return _ct_node(_mth(hashes, start, start + k), _mth(hashes, start + k, end))


def _ct_path(hashes, m, start, end):
    n = end - start
    if n == 1:
        return []
    k = _split(n)
    if m < k:
        return _ct_path(hashes, m, start, start + k) + [_mth(hashes, start + k, end)]
    return _ct_path(hashes, m - k, start + k, end) + [_mth(hashes, start, start + k)]


def _ct_subproof(hashes, m, start, end, whole):
    n = end - start
    if m == n:
        return [] if whole else [_mth(hashes, start, end)]
    k = _split(n)
    if m <= k:
        return _ct_subproof(hashes, m, start, start + k, whole) + [_mth(hashes, start + k, end)]
    return _ct_subproof(hashes, m - k, start + k, end, False) + [_mth(hashes, start, start + k)]


def _ct_root_from_path(leaf, index, size, proof):
    """RFC 9162 2.1.3.2. Returns the root the path implies, or None if its shape is wrong."""
    fn, sn = index, size - 1
    r = leaf
    for p in proof:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = _ct_node(p, r)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            r = _ct_node(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


def _ct_consistent(first, second, proof, first_root, second_root):
    """RFC 9162 2.1.4.2."""
    if first == second:
        if proof:
            return False, "equal sizes take an empty proof"
        if first_root != second_root:
            return False, "equal sizes but different roots: the log was rewritten"
        return True, "same tree"
    if not proof:
        return False, "empty proof for different sizes"
    path = list(proof)
    if first & (first - 1) == 0:
        path.insert(0, first_root)
    fn, sn = first - 1, second - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = path[0]
    for c in path[1:]:
        if sn == 0:
            return False, "proof is longer than these sizes allow"
        if fn & 1 or fn == sn:
            fr = _ct_node(c, fr)
            sr = _ct_node(c, sr)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            sr = _ct_node(sr, c)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        return False, "proof is shorter than these sizes need"
    if fr != first_root:
        return False, "proof does not lead to the old root"
    if sr != second_root:
        return False, "proof does not lead to the new root: the old tree is not a prefix"
    return True, "the new tree extends the old one"


def _rfc6962(op, payload):
    fmt = payload.get("leaf_format", "hex")
    if op in ("root", "prove", "consistency"):
        leaves = payload.get("leaves")
        if not isinstance(leaves, list):
            raise ValueError("'leaves' must be a list")
        if len(leaves) > MAX_RFC6962_LEAVES:
            raise ValueError("at most " + str(MAX_RFC6962_LEAVES) + " leaves")
        hashes = [_ct_leaf(_leaf_data(v, fmt, "leaves[" + str(i) + "]"))
                  for i, v in enumerate(leaves)]
        size = len(hashes)
        if op == "root":
            return {"scheme": "rfc6962", "tree_size": size, "root": _mth(hashes, 0, size).hex()}
        if op == "prove":
            index = _index(payload, "index")
            if index >= size:
                raise ValueError("index " + str(index) + " is outside a tree of " + str(size))
            return {"scheme": "rfc6962", "tree_size": size, "index": index,
                    "leaf_hash": hashes[index].hex(), "root": _mth(hashes, 0, size).hex(),
                    "proof": [h.hex() for h in _ct_path(hashes, index, 0, size)]}
        old_size = _index(payload, "old_size")
        if not 0 < old_size <= size:
            raise ValueError("need 0 < old_size <= the number of leaves")
        return {"scheme": "rfc6962", "old_size": old_size, "new_size": size,
                "old_root": _mth(hashes, 0, old_size).hex(),
                "new_root": _mth(hashes, 0, size).hex(),
                "proof": [h.hex() for h in _ct_subproof(hashes, old_size, 0, size, True)]}
    if op == "verify":
        size = _index(payload, "tree_size")
        index = _index(payload, "index")
        root = _hex_bytes(payload.get("root"), "root", 32)
        proof = _hash_list(payload.get("proof"), "proof")
        if "leaf_hash" in payload:
            leaf = _hex_bytes(payload.get("leaf_hash"), "leaf_hash", 32)
        elif "leaf" in payload:
            leaf = _ct_leaf(_leaf_data(payload.get("leaf"), fmt, "leaf"))
        else:
            raise ValueError("send 'leaf' (the entry) or 'leaf_hash'")
        out = {"scheme": "rfc6962", "leaf_hash": leaf.hex(), "index": index, "tree_size": size}
        if index >= size:
            return dict(out, valid=False, computed_root=None, reason="index is outside the tree")
        computed = _ct_root_from_path(leaf, index, size, proof)
        if computed is None:
            return dict(out, valid=False, computed_root=None,
                        reason="proof has the wrong length for this index and tree size")
        valid = computed == root
        return dict(out, valid=valid, computed_root=computed.hex(),
                    reason="leaf is in the tree" if valid else "proof leads to a different root")
    if op == "verify_consistency":
        first = _index(payload, "old_size")
        second = _index(payload, "new_size")
        if not 0 < first <= second:
            raise ValueError("need 0 < old_size <= new_size")
        valid, reason = _ct_consistent(first, second, _hash_list(payload.get("proof"), "proof"),
                                       _hex_bytes(payload.get("old_root"), "old_root", 32),
                                       _hex_bytes(payload.get("new_root"), "new_root", 32))
        return {"scheme": "rfc6962", "old_size": first, "new_size": second, "valid": valid,
                "reason": reason}
    raise ValueError("op must be root, prove, verify, consistency or verify_consistency")


# ------------------------------------------------------------------ ABI encoding (OZ leaves)


def _checked_address(value, where):
    raw = _hex_bytes(value, where, 20)
    body = value[2:] if value[:2] in ("0x", "0X") else value
    if body != body.lower() and body != body.upper():
        digest = keccak256(body.lower().encode("ascii")).hex()
        for i, char in enumerate(body):
            if char.isalpha() and (char.isupper() != (int(digest[i], 16) >= 8)):
                raise ValueError(where + " has a wrong EIP-55 checksum (mixed case that "
                                 "does not match): a mistyped address")
    return raw


def _integer(value, where):
    if isinstance(value, bool):
        raise ValueError(where + " must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            if text[:2] in ("0x", "0X") or text[:3] in ("-0x", "-0X"):
                return int(text, 16)
            return int(text, 10)
        except ValueError:
            raise ValueError(where + " is not an integer") from None
    raise ValueError(where + " must be an integer or a decimal/hex string")


def _abi_word(kind, value, where):
    """One static ABI value as its 32-byte head."""
    if kind == "address":
        return b"\x00" * 12 + _checked_address(value, where)
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(where + " must be true or false")
        return (1 if value else 0).to_bytes(32, "big")
    if kind.startswith("uint"):
        bits = int(kind[4:] or "256")
        number = _integer(value, where)
        if number < 0 or number >> bits:
            raise ValueError(where + " does not fit " + kind)
        return number.to_bytes(32, "big")
    if kind.startswith("int"):
        bits = int(kind[3:] or "256")
        number = _integer(value, where)
        if not -(1 << (bits - 1)) <= number < (1 << (bits - 1)):
            raise ValueError(where + " does not fit " + kind)
        return (number % (1 << 256)).to_bytes(32, "big")
    if kind.startswith("bytes") and kind != "bytes":
        size = int(kind[5:])
        return _hex_bytes(value, where, size) + b"\x00" * (32 - size)
    raise ValueError("unsupported type " + kind)


def _abi_type(kind):
    if kind in ("address", "bool", "string", "bytes"):
        return kind
    for prefix, low, high, step in (("uint", 8, 256, 8), ("int", 8, 256, 8), ("bytes", 1, 32, 1)):
        if kind.startswith(prefix) and kind[len(prefix):].isdigit():
            size = int(kind[len(prefix):])
            if low <= size <= high and size % step == 0:
                return kind
    if kind in ("uint", "int"):
        return kind + "256"
    raise ValueError("unsupported ABI type '" + str(kind) + "' (static types, string and bytes)")


def _abi_encode(types, values, where):
    if not isinstance(values, list) or len(values) != len(types):
        raise ValueError(where + " must be a list of " + str(len(types)) + " values")
    heads, tails = [], []
    offset = 32 * len(types)
    for i, kind in enumerate(types):
        here = where + "[" + str(i) + "]"
        if kind in ("string", "bytes"):
            if kind == "string":
                if not isinstance(values[i], str):
                    raise ValueError(here + " must be a string")
                raw = values[i].encode("utf-8")
            else:
                raw = _hex_bytes(values[i], here)
            padded = raw + b"\x00" * ((32 - len(raw) % 32) % 32)
            heads.append(offset.to_bytes(32, "big"))
            tail = len(raw).to_bytes(32, "big") + padded
            tails.append(tail)
            offset += len(tail)
        else:
            heads.append(_abi_word(kind, values[i], here))
    return b"".join(heads) + b"".join(tails)


# ------------------------------------------------------------------ OpenZeppelin


def _oz_pair(a, b):
    return keccak256(a + b) if a <= b else keccak256(b + a)


def _oz_leaves(payload, single):
    """Leaf hashes, from `types` + values (StandardMerkleTree) or bytes32 hashes (Simple)."""
    types = payload.get("types")
    if types is not None:
        if not isinstance(types, list) or not types:
            raise ValueError("'types' must be a non-empty list of ABI types")
        types = [_abi_type(t) for t in types]
        values = [payload.get("value")] if single else payload.get("values")
        if not isinstance(values, list):
            raise ValueError("send 'values' (a list of value lists) with 'types'")
        if len(values) > MAX_OZ_LEAVES:
            raise ValueError("at most " + str(MAX_OZ_LEAVES) + " leaves")
        names = ["value"] if single else ["values[" + str(i) + "]" for i in range(len(values))]
        return [keccak256(keccak256(_abi_encode(types, v, names[i]))) for i, v in enumerate(values)]
    if single:
        if "leaf" not in payload:
            raise ValueError("send 'leaf' (a bytes32 hash) or 'types' with 'value'")
        return [_hex_bytes(payload.get("leaf"), "leaf", 32)]
    leaves = payload.get("leaves")
    if not isinstance(leaves, list):
        raise ValueError("send 'leaves' (bytes32 hashes) or 'types' with 'values'")
    if len(leaves) > MAX_OZ_LEAVES:
        raise ValueError("at most " + str(MAX_OZ_LEAVES) + " leaves")
    return [_hex_bytes(v, "leaves[" + str(i) + "]", 32) for i, v in enumerate(leaves)]


def _oz_standard(hashes, sort_leaves):
    """@openzeppelin/merkle-tree: leaves at the end of one array, parent of i at (i-1)//2."""
    order = list(range(len(hashes)))
    if sort_leaves:
        order.sort(key=lambda i: hashes[i])
    tree = [b""] * (2 * len(hashes) - 1)
    position = {}
    for leaf_index, value_index in enumerate(order):
        tree[len(tree) - 1 - leaf_index] = hashes[value_index]
        position[value_index] = len(tree) - 1 - leaf_index
    for i in range(len(tree) - 1 - len(hashes), -1, -1):
        tree[i] = _oz_pair(tree[2 * i + 1], tree[2 * i + 2])
    return tree, position


def _oz_standard_proof(tree, node):
    proof = []
    while node > 0:
        proof.append(tree[node + 1] if node % 2 else tree[node - 1])
        node = (node - 1) // 2
    return proof


def _oz_layers_root_and_proof(hashes, index):
    """Pairs left to right, an odd node promoted (merkletreejs sortPairs, ACEX distributor)."""
    proof, layer, idx = [], list(hashes), index
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                if idx is not None and idx in (i, i + 1):
                    proof.append(layer[i + 1] if idx == i else layer[i])
                nxt.append(_oz_pair(layer[i], layer[i + 1]))
            else:
                nxt.append(layer[i])
        if idx is not None:
            idx //= 2
        layer = nxt
    return layer[0], proof


def _openzeppelin(op, payload):
    layout = payload.get("layout", "standard")
    if layout not in ("standard", "layers"):
        raise ValueError("layout must be standard (@openzeppelin/merkle-tree) or layers")
    if op == "verify":
        leaf = _oz_leaves(payload, True)[0]
        root = _hex_bytes(payload.get("root"), "root", 32)
        computed = leaf
        for p in _hash_list(payload.get("proof"), "proof"):
            computed = _oz_pair(computed, p)
        valid = computed == root
        return {"scheme": "openzeppelin", "leaf_hash": "0x" + leaf.hex(), "valid": valid,
                "computed_root": "0x" + computed.hex(),
                "reason": "leaf is in the tree" if valid else "proof leads to a different root"}
    if op not in ("root", "prove"):
        raise ValueError("openzeppelin supports root, prove and verify (no consistency proofs)")
    hashes = _oz_leaves(payload, False)
    if not hashes:
        raise ValueError("a tree needs at least one leaf")
    index = None
    if op == "prove":
        index = _index(payload, "index")
        if index >= len(hashes):
            raise ValueError("index " + str(index) + " is outside " + str(len(hashes)) + " leaves")
    if layout == "standard":
        sort_leaves = payload.get("sort_leaves", True)
        if not isinstance(sort_leaves, bool):
            raise ValueError("'sort_leaves' must be true or false")
        tree, position = _oz_standard(hashes, sort_leaves)
        root = tree[0]
        proof = _oz_standard_proof(tree, position[index]) if op == "prove" else []
    else:
        root, proof = _oz_layers_root_and_proof(hashes, index)
    out = {"scheme": "openzeppelin", "layout": layout, "leaf_count": len(hashes),
           "root": "0x" + root.hex()}
    if op == "prove":
        out.update({"index": index, "leaf_hash": "0x" + hashes[index].hex(),
                    "proof": ["0x" + p.hex() for p in proof]})
    return out


def handle(payload):
    op = payload.get("op")
    scheme = payload.get("scheme", "rfc6962")
    if scheme == "rfc6962":
        return _rfc6962(op, payload)
    if scheme == "openzeppelin":
        return _openzeppelin(op, payload)
    raise ValueError("scheme must be rfc6962 or openzeppelin")
