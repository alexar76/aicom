"""tlog.checkpoint.verify@v1: is this transparency-log checkpoint signed by the log, cosigned by
enough witnesses, and does it hold what you were shown?

A checkpoint (c2sp.org/tlog-checkpoint) is a signed note (c2sp.org/signed-note): the log's origin
line, the tree size, the root hash in base64, optional extension lines, a blank line, then one
"— <name> <base64>" line per signature. Logs that use it: the Go checksum database
(sum.golang.org), Sigstore's Rekor v2, Trillian-Tessera logs, HISTOR.

Give `checkpoint` (the note text) and `log_key`, the log's verifier key
(`<name>+<hash>+<base64>`, Ed25519). Optionally `witness_keys` (cosignature/v1 verifier keys,
c2sp.org/tlog-cosignature, or plain Ed25519 note keys) and `witness_quorum` (how many must have
cosigned; default all of them). Optionally:
  - `inclusion`: {"leaf_index", "proof": [hashes], and one of "leaf_hash", "leaf" (UTF-8 text),
    "leaf_base64"}: is that entry in this tree (RFC 9162 2.1.3, leaf hash SHA-256(0x00 || leaf));
  - `consistency`: {"proof": [hashes], and "old_checkpoint" (verified with the same log key) or
    "old_size" with "old_root"}: does this tree extend the older one (RFC 9162 2.1.4) — the log
    did not rewrite history between the two;
  - `now` (Unix seconds) to judge cosignature times (a cosignature from the future is refused).
Hashes are hex or base64. The verdict is `valid` only when the log's signature verifies, the
quorum of witnesses is met and every proof given holds. No network: everything is in the request.
"""

import base64
import hashlib
import struct

MAX_PROOF = 64
MAX_NOTE = 64 * 1024
MAX_KEYS = 32
COSIGNATURE_SKEW = 60

# ------------------------------------------------------------------ Ed25519 (RFC 8032, pure Python)

_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)
_IDENTITY = (0, 1, 1, 0)


def _recover_x(y, sign):
    if y >= _Q:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q) % _Q
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_Q + 3) // 8, _Q)
    if (x * x - x2) % _Q:
        x = x * _I % _Q
    if (x * x - x2) % _Q:
        return None
    if x & 1 != sign:
        x = _Q - x
    return x


def _decode(raw):
    y = int.from_bytes(raw, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _Q)


_BY = 4 * pow(5, _Q - 2, _Q) % _Q
_B = (_recover_x(_BY, 0), _BY, 1, _recover_x(_BY, 0) * _BY % _Q)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _Q
    b = (p[1] + p[0]) * (q[1] + q[0]) % _Q
    c = 2 * p[3] * q[3] * _D % _Q
    d = 2 * p[2] * q[2] % _Q
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _double(p):
    a = p[0] * p[0] % _Q
    b = p[1] * p[1] % _Q
    c = 2 * p[2] * p[2] % _Q
    h = a + b
    e = h - (p[0] + p[1]) * (p[0] + p[1])
    g = a - b
    f = c + g
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _same(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % _Q == 0 and (p[1] * q[2] - q[1] * p[2]) % _Q == 0


def _two_mul(k1, p1, k2, p2):
    both = _add(p1, p2)
    acc = _IDENTITY
    for i in range(max(k1.bit_length(), k2.bit_length()) - 1, -1, -1):
        acc = _double(acc)
        b1, b2 = (k1 >> i) & 1, (k2 >> i) & 1
        if b1 and b2:
            acc = _add(acc, both)
        elif b1:
            acc = _add(acc, p1)
        elif b2:
            acc = _add(acc, p2)
    return acc


def ed25519_verify(public, message, signature):
    """RFC 8032 5.1.7, cofactorless; small-order keys and unreduced S refused."""
    if len(signature) != 64 or len(public) != 32:
        return False
    a = _decode(public)
    if a is None:
        return False
    small = a
    for _ in range(3):
        small = _double(small)
    if _same(small, _IDENTITY):
        return False
    r = _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if r is None or s >= _L:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    neg_a = ((-a[0]) % _Q, a[1], a[2], (-a[3]) % _Q)
    return _same(_two_mul(s, _B, k, neg_a), r)


# ------------------------------------------------------------------ signed notes and keys


def _b64(text, where):
    if not isinstance(text, str) or not text or len(text) % 4:
        raise ValueError(where + " is not padded standard base64")
    try:
        return base64.b64decode(text, validate=True)
    except ValueError:
        raise ValueError(where + " is not standard base64") from None


def parse_vkey(vkey, where):
    """(name, key type, 4-byte key hash, 32-byte key) of a note verifier key."""
    if not isinstance(vkey, str) or vkey.count("+") < 2:
        raise ValueError(where + " must be a verifier key <name>+<hash>+<base64>")
    name, khash, b64 = vkey.split("+", 2)
    if not name or any(c in name for c in " +\n") or len(khash) != 8:
        raise ValueError(where + ": bad name or key hash")
    raw = _b64(b64, where)
    if len(raw) != 33 or raw[0] not in (0x01, 0x04):
        raise ValueError(where + ": only Ed25519 (type 0x01) and cosignature/v1 (type 0x04) "
                         "keys of 32 bytes are supported")
    if hashlib.sha256(name.encode() + b"\n" + raw).digest()[:4].hex() != khash.lower():
        raise ValueError(where + ": the key hash does not match the name and key")
    return name, raw[0], bytes.fromhex(khash), raw[1:]


def parse_note(text):
    """(body including its final newline, [(name, signature bytes)], warnings)."""
    if not isinstance(text, str) or not text:
        raise ValueError("checkpoint must be the signed note text")
    if len(text) > MAX_NOTE:
        raise ValueError("checkpoint is longer than " + str(MAX_NOTE) + " characters")
    warnings = []
    if not text.endswith("\n"):
        text += "\n"
        warnings.append("the note did not end with a newline; one was added (the format "
                        "requires it)")
    if "\r" in text:
        raise ValueError("the note has carriage returns: a signed note uses \\n line ends only")
    if "\n\n" not in text:
        raise ValueError("not a signed note: no blank line between the text and the signatures")
    body, sigs = text.split("\n\n", 1)
    out = []
    for line in sigs.split("\n"):
        if not line:
            continue
        if not line.startswith("— "):
            raise ValueError("a signature line must start with an em dash and a space: "
                             + line[:40])
        name, sep, b64 = line[2:].rpartition(" ")
        if not sep or not name:
            raise ValueError("a signature line needs a name and a base64 signature")
        sig = _b64(b64, "the signature of " + name)
        if len(sig) < 5:
            raise ValueError("the signature of " + name + " is too short")
        out.append((name, sig))
    if not out:
        raise ValueError("the note carries no signature")
    return body + "\n", out, warnings


def parse_checkpoint(body):
    lines = body[:-1].split("\n")
    if len(lines) < 3:
        raise ValueError("a checkpoint body has at least three lines: origin, size, root hash")
    origin, size_text, root_text = lines[:3]
    if not origin:
        raise ValueError("the origin line is empty")
    if not (size_text.isdigit() and size_text.isascii()) or (len(size_text) > 1
                                                              and size_text[0] == "0"):
        raise ValueError("the size line must be a decimal number without leading zeros")
    root = _b64(root_text, "the root hash line")
    if len(root) != 32:
        raise ValueError("the root hash is " + str(len(root)) + " bytes, not 32")
    extensions = lines[3:]
    if any(not line for line in extensions):
        raise ValueError("an extension line is empty")
    return origin, int(size_text), root, extensions


def _hash(value, where):
    if not isinstance(value, str):
        raise ValueError(where + " must be a hex or base64 string")
    text = value.strip()
    if text.lower().startswith("0x"):
        text = text[2:]
    if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
        return bytes.fromhex(text)
    raw = _b64(text, where)
    if len(raw) != 32:
        raise ValueError(where + " is " + str(len(raw)) + " bytes, not 32")
    return raw


def _proof(value, where):
    if not isinstance(value, list) or len(value) > MAX_PROOF:
        raise ValueError(where + " must be a list of at most " + str(MAX_PROOF) + " hashes")
    return [_hash(item, where + "[" + str(i) + "]") for i, item in enumerate(value)]


def _count(value, where):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(where + " must be a non-negative integer")
    return value


# ------------------------------------------------------------------ RFC 9162 proofs


def _node(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def inclusion_root(leaf_hash, index, size, path):
    """RFC 9162 2.1.3.2: the root the path leads to, or None when its shape is wrong."""
    if index >= size:
        return None
    fn, sn, r = index, size - 1, leaf_hash
    for p in path:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = _node(p, r)
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


def consistent(first, second, proof, first_root, second_root):
    """RFC 9162 2.1.4.2: (ok, reason)."""
    if first > second:
        return False, "the old tree is larger than this one"
    if first == 0:
        return (not proof), "an empty tree is consistent with every tree; the proof must be empty"
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
            return False, "the proof is longer than these sizes allow"
        if fn & 1 or fn == sn:
            fr = _node(c, fr)
            sr = _node(c, sr)
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            sr = _node(sr, c)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        return False, "the proof is shorter than these sizes need"
    if fr != first_root:
        return False, "the proof does not lead to the old root"
    if sr != second_root:
        return False, "the proof does not lead to this root: the old tree is not a prefix"
    return True, "this tree extends the old one"


# ------------------------------------------------------------------ the check


def _log_signature(body, sigs, log):
    name, kind, khash, key = log
    if kind != 0x01:
        raise ValueError("log_key must be an Ed25519 note key (type 0x01), not a cosigner key")
    mine = [sig for signer, sig in sigs if signer == name and sig[:4] == khash]
    if not mine:
        return False, "no signature by " + name + " with this key"
    if any(len(sig) == 68 and ed25519_verify(key, body.encode(), sig[4:]) for sig in mine):
        return True, "the log's Ed25519 signature verifies"
    return False, "the log's signature does not verify with this key"


def _witnesses(body, sigs, keys, now):
    found, refused = [], []
    for _vkey, (name, kind, khash, key) in keys:
        entry = {"name": name, "key_hash": khash.hex()}
        ok = False
        for signer, sig in sigs:
            if signer != name or sig[:4] != khash:
                continue
            if kind == 0x04:
                if len(sig) != 76:
                    continue
                (ts,) = struct.unpack(">Q", sig[4:12])
                message = ("cosignature/v1\ntime " + str(ts) + "\n").encode() + body.encode()
                if ed25519_verify(key, message, sig[12:]):
                    entry["cosigned_at"] = ts
                    if now is not None and ts > now + COSIGNATURE_SKEW:
                        entry["problem"] = "cosigned in the future (" + str(ts - now) + " s)"
                    else:
                        ok = True
                        if now is not None:
                            entry["age_seconds"] = now - ts
            elif len(sig) == 68 and ed25519_verify(key, body.encode(), sig[4:]):
                entry["kind"] = "ed25519 note signature (no timestamp)"
                ok = True
        if ok:
            found.append(entry)
        else:
            entry.setdefault("problem", "no valid signature by this witness key")
            refused.append(entry)
    return found, refused


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: checkpoint and log_key")
    body, sigs, warnings = parse_note(payload.get("checkpoint"))
    origin, size, root, extensions = parse_checkpoint(body)
    log = parse_vkey(payload.get("log_key"), "log_key")
    if log[0] != origin:
        warnings.append("the log key's name (" + log[0] + ") differs from the checkpoint "
                        "origin (" + origin + "): normally they are the same")
    raw_keys = payload.get("witness_keys") or []
    if not isinstance(raw_keys, list) or len(raw_keys) > MAX_KEYS:
        raise ValueError("witness_keys must be a list of at most " + str(MAX_KEYS) + " keys")
    keys = [(k, parse_vkey(k, "witness_keys[" + str(i) + "]")) for i, k in enumerate(raw_keys)]
    if len({(k[1][0], k[1][2]) for k in keys}) != len(keys):
        raise ValueError("witness_keys lists one key twice")
    quorum = payload.get("witness_quorum")
    quorum = len(keys) if quorum is None else _count(quorum, "witness_quorum")
    if quorum > len(keys):
        raise ValueError("witness_quorum is larger than the number of witness keys")
    now = payload.get("now")
    if now is not None:
        now = _count(now, "now")

    log_ok, log_detail = _log_signature(body, sigs, log)
    found, refused = _witnesses(body, sigs, keys, now)
    known = {(log[0], log[2])} | {(k[1][0], k[1][2]) for k in keys}
    other = sorted({signer for signer, sig in sigs if (signer, sig[:4]) not in known})
    out = {
        "origin": origin,
        "size": size,
        "root_hash": base64.b64encode(root).decode(),
        "root_hash_hex": root.hex(),
        "extensions": extensions,
        "log_signature": {"ok": log_ok, "detail": log_detail},
        "witnesses": {"quorum": quorum, "cosigned": len(found), "met": len(found) >= quorum,
                      "valid": found, "missing_or_invalid": refused},
        "other_signers": other,
    }
    problems = []
    if not log_ok:
        problems.append(log_detail)
    if len(found) < quorum:
        problems.append(str(len(found)) + " of the required " + str(quorum)
                        + " witnesses cosigned")

    inclusion = payload.get("inclusion")
    if inclusion is not None:
        if not isinstance(inclusion, dict):
            raise ValueError("inclusion must be an object")
        index = _count(inclusion.get("leaf_index"), "inclusion.leaf_index")
        given = [k for k in ("leaf_hash", "leaf", "leaf_base64") if inclusion.get(k) is not None]
        if len(given) != 1:
            raise ValueError("inclusion needs exactly one of leaf_hash, leaf, leaf_base64")
        if given[0] == "leaf_hash":
            leaf_hash = _hash(inclusion["leaf_hash"], "inclusion.leaf_hash")
        elif given[0] == "leaf":
            if not isinstance(inclusion["leaf"], str):
                raise ValueError("inclusion.leaf must be text")
            leaf_hash = hashlib.sha256(b"\x00" + inclusion["leaf"].encode()).digest()
        else:
            leaf_hash = hashlib.sha256(b"\x00" + _b64(inclusion["leaf_base64"],
                                                      "inclusion.leaf_base64")).digest()
        path = _proof(inclusion.get("proof"), "inclusion.proof")
        reached = inclusion_root(leaf_hash, index, size, path)
        ok = reached == root
        out["inclusion"] = {
            "ok": ok, "leaf_index": index, "leaf_hash": leaf_hash.hex(),
            "detail": "the entry is in this tree" if ok else (
                "the proof's shape does not fit this index and size" if reached is None
                else "the proof leads to another root: the entry is not in this tree"),
        }
        if not ok:
            problems.append("inclusion: " + out["inclusion"]["detail"])

    cons = payload.get("consistency")
    if cons is not None:
        if not isinstance(cons, dict):
            raise ValueError("consistency must be an object")
        result = {}
        if cons.get("old_checkpoint") is not None:
            old_body, old_sigs, _ = parse_note(cons["old_checkpoint"])
            old_origin, old_size, old_root, _ = parse_checkpoint(old_body)
            old_ok, old_detail = _log_signature(old_body, old_sigs, log)
            result["old_log_signature"] = {"ok": old_ok, "detail": old_detail}
            if old_origin != origin:
                raise ValueError("the old checkpoint is for another log: " + old_origin)
            if not old_ok:
                problems.append("consistency: the old checkpoint's " + old_detail)
        else:
            old_size = _count(cons.get("old_size"), "consistency.old_size")
            old_root = _hash(cons.get("old_root"), "consistency.old_root")
        ok, detail = consistent(old_size, size, _proof(cons.get("proof"), "consistency.proof"),
                                old_root, root)
        result.update(ok=ok, old_size=old_size, old_root_hash=base64.b64encode(old_root).decode(),
                      detail=detail)
        out["consistency"] = result
        if not ok:
            problems.append("consistency: " + detail)

    out["verdict"] = "valid" if not problems else "invalid"
    out["problems"] = problems
    if warnings:
        out["warnings"] = warnings
    return out
