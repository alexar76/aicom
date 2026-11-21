"""histor.witnessed@v1: is this MCP tool set in HISTOR's log, and did independent witnesses sign it?

Give the server (`endpoint`, `name` or `package`) and either `tool_set_digest` (the MTL/1 digest,
sha256-…) or `tools` (the tools/list array; HISTOR computes the digest). The agent asks HISTOR what
it observed (/api/v1/check), takes the label HISTOR issued for that tool set, downloads it and
proves it is in the log: RFC 9162 inclusion of SHA-256(0x00 || JCS(label)) under the newest head
the witnesses co-signed. The head is checked here, not taken on trust: the log's Ed25519 signature
under its pinned key, and each witness's cosignature/v1 under the witness keys pinned below.

What it proves: HISTOR's log holds, and cannot later remove without the witnesses seeing a split,
a label saying HISTOR observed this exact tool set at this server. What it does not: that the
tools are safe, that HISTOR saw every change between observations, or anything about behaviour.
Only histor.modelmarket.dev is reached (the agent's one egress host).
"""
# ruff: noqa: E501 — pinned witness keys and answer texts are kept whole

import base64
import hashlib
import json
import struct
from urllib.parse import quote

HISTOR = "https://histor.modelmarket.dev"
LOG_VKEY = "histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU"
# The witnesses that co-sign HISTOR's checkpoints (histor/docs/cross-check.md, 2026-11-19).
WITNESS_VKEYS = {
    "Mullvad (stagemole)": "witness.stagemole.eu+67f7aea0+BEqSG3yu9YrmcM3BHvQYTxwFj3uSWakQepafafpUqklv",
    "Markovian Protocol": "markovianprotocol.com/witness+41b8827f+BJKLl8rBYM0oUxSaWh9rjTldTprEpYj/SWVIGgacA9XC",
    "TrustFabric": "staging.witness.transparency.goog/ring-any-bells+2e1a8dc9+BG5JTpLc3FJtwzgh1Uv+Qelz9qeOH2bfWjS1s0s+y4rL",
    "CrawlCheck": "crawlcheck.io/witness+f6b056e2+BCYE6WcaJVekqxEETT9IF/pKvxP7yZM6dLW65YDWpQpE",
    "GDB Security": "witness.gdbsecurity.com+a1398f73+BAbIijGonVIk3ikDac+KKlSm1ELHOzcddhjjB6zB4BNf",
    "Geomys (Navigli)": "witness.navigli.sunlight.geomys.org+a3e00fe2+BNy/co4C1Hn1p+INwJrfUlgz7W55dSZReusH/GhUhJ/G",
    "IPng (krabbel)": "krabbel.ct.ipng.ch+4b10dbd8+BO4sLOtnhktlqMCejDx9C5LDd+/xZxbmBb6BP9ZD2Def",
}
LABEL_METHODS = (
    "urn:awr:mtl:1:method:tool-set-observation",
    "urn:awr:mtl:1:method:tool-set-continuity",
)

# ------------------------------------------------------------------ Ed25519

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
    """(ok, reason) per RFC 8032 5.1.7, cofactorless; small-order keys refused."""
    if len(signature) != 64:
        return False, "the signature is " + str(len(signature)) + " bytes, Ed25519 needs 64"
    a = _decode(public)
    if a is None:
        return False, "k is not a valid curve point"
    small = a
    for _ in range(3):
        small = _double(small)
    if _same(small, _IDENTITY):
        return False, "k has small order: it verifies forged signatures"
    r = _decode(signature[:32])
    if r is None:
        return False, "signature R is not a valid curve point"
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False, "signature S is not reduced (S >= L)"
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    neg_a = ((-a[0]) % _Q, a[1], a[2], (-a[3]) % _Q)
    if _same(_two_mul(s, _B, k, neg_a), r):
        return True, "Ed25519 verifies over the signature base"
    return False, "Ed25519 does not verify for this key over the signature base"


# ------------------------------------------------------------------ signed notes (c2sp.org/signed-note)


def parse_vkey(vkey):
    """(name, key type, key hash, 32-byte Ed25519 key) of a note verifier key."""
    name, khash, b64 = vkey.split("+", 2)
    raw = base64.b64decode(b64)
    if hashlib.sha256(name.encode() + b"\n" + raw).digest()[:4].hex() != khash:
        raise ValueError("key hash mismatch for " + name)
    return name, raw[0], bytes.fromhex(khash), raw[1:]


def parse_note(text):
    """(body with its final newline, [(name, signature bytes)])."""
    if "\n\n" not in text:
        raise ValueError("not a signed note")
    body, sigs = text.split("\n\n", 1)
    lines = []
    for line in sigs.split("\n"):
        if not line:
            continue
        if not line.startswith("— "):
            raise ValueError("a signature line must start with an em dash")
        name, b64 = line[2:].rsplit(" ", 1)
        lines.append((name, base64.b64decode(b64)))
    return body + "\n", lines


def check_note(text):
    """The checkpoint's (size, root) and who signed it: the log, and each pinned witness."""
    body, lines = parse_note(text)
    origin, size, root_b64 = body.split("\n")[:3]
    log_name, _, log_hash, log_key = parse_vkey(LOG_VKEY)
    if origin != log_name:
        raise ValueError("the checkpoint is for another log: " + origin)
    log_ok, witnesses = False, []
    known = {}
    for label, vkey in WITNESS_VKEYS.items():
        name, kind, khash, key = parse_vkey(vkey)
        known[(name, khash)] = (label, key)
    for name, sig in lines:
        if name == log_name and sig[:4] == log_hash:
            log_ok = ed25519_verify(log_key, body.encode(), sig[4:])[0]
        elif (name, sig[:4]) in known and len(sig) == 76:
            label, key = known[(name, sig[:4])]
            (ts,) = struct.unpack(">Q", sig[4:12])
            message = ("cosignature/v1\ntime " + str(ts) + "\n").encode() + body.encode()
            if ed25519_verify(key, message, sig[12:])[0]:
                witnesses.append({"witness": label, "name": name, "cosigned_at": ts})
    return int(size), base64.b64decode(root_b64), log_ok, witnesses


# ------------------------------------------------------------------ the log (RFC 9162, RFC 8785)


def _jcs_string(text):
    return json.dumps(text, ensure_ascii=False)


def jcs(value):
    """RFC 8785 for the values a label holds: strings, integers, booleans, null, lists, objects."""
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, list):
        return "[" + ",".join(jcs(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(_jcs_string(k) + ":" + jcs(value[k]) for k in keys) + "}"
    raise ValueError("a label holds a value JCS here cannot write: " + type(value).__name__)


def _node(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def inclusion_root(leaf_hash, index, size, path):
    """RFC 9162 section 2.1.3.2: the root the path leads to, or None when it cannot."""
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


# ------------------------------------------------------------------ HISTOR


def _get(path):
    reply = fetch(HISTOR + path, headers={"accept": "application/json"})  # noqa: F821 — the sandbox provides fetch()
    if reply.status == 404:
        return None
    if not reply.ok:
        raise RuntimeError("HISTOR answered " + str(reply.status) + " for " + path.split("?")[0])
    return reply.json()


def selector(payload):
    for key in ("endpoint", "package", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            if len(value) > 500:
                raise ValueError(key + " is too long")
            return key, value.strip()
    raise ValueError(
        "name the server: endpoint (a URL), package (npm:… or pypi:…) or name (registry name)"
    )


def ask_histor(payload):
    """HISTOR's signed /check answer for the server and the set the caller holds."""
    key, value = selector(payload)
    digest, tools = payload.get("tool_set_digest"), payload.get("tools")
    if isinstance(tools, list) and tools:
        body = {key: value, "tools": tools}
        reply = fetch(HISTOR + "/api/v1/check", method="POST", json=body)  # noqa: F821
        if not reply.ok:
            raise RuntimeError("HISTOR's check answered " + str(reply.status))
        return reply.json()
    if not isinstance(digest, str) or not digest.startswith("sha256-") or len(digest) > 60:
        raise ValueError(
            "send tool_set_digest (the MTL/1 digest, sha256-…) or tools (the tools/list array)"
        )
    return _get(
        "/api/v1/check?"
        + key
        + "="
        + quote(value, safe="")
        + "&toolSetDigest="
        + quote(digest, safe="")
    )


def label_for(detail, digest, below):
    """The newest HISTOR label that names this tool set and sits under the co-signed head."""
    subjects = {
        row.get("subjectDigest")
        for row in detail.get("timeline") or []
        if row.get("toolSetDigest") == digest and row.get("subjectDigest")
    }
    candidates = []
    for label in detail.get("labels") or []:
        if label.get("subject") in subjects and label.get("method") in LABEL_METHODS:
            candidates.append((int(label.get("leaf_index", -1)), label["id"]))
    for change in detail.get("changes") or []:
        if change.get("to_toolset") == digest and change.get("label_id"):
            candidates.append((-1, change["label_id"]))  # leaf unknown until fetched
    known = sorted((c for c in candidates if 0 <= c[0] < below), reverse=True)
    if known:
        return known[0][1]
    return next((label_id for leaf, label_id in candidates if leaf < 0), None)


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: endpoint, package or name, and tool_set_digest or tools")
    check = ask_histor(payload)
    if not check:
        raise RuntimeError("HISTOR gave no answer for that server")
    digest = (check.get("query") or {}).get("toolSetDigest") or payload.get("tool_set_digest")
    target = check.get("target") or {}
    out = {
        "match": check.get("match"),
        "histor_note": check.get("note"),
        "tool_set_digest": digest,
        "server": {k: target.get(k) for k in ("id", "name", "endpoint", "page")},
        "observed": check.get("observed"),
        "seen_before": check.get("seenBefore"),
    }
    if check.get("match") not in ("same", "previously-observed") or not target.get("id"):
        out.update(
            witnessed=False,
            verdict="not_recorded",
            detail="HISTOR holds no observation of this tool set at this server, so there is "
            "no log entry to prove",
        )
        return out
    # The compact change feed first: a set the server moved to carries the label of that observation.
    # The full server record (labels of every daily read) only when no change leads to the set; it
    # can be larger than the 256 KiB one fetch may bring back for a server with hundreds of tools.
    feed = _get("/api/v1/changes?watch=" + target["id"] + "&limit=50") or {}
    detail = {"changes": feed.get("changes") or []}
    if not any(c.get("to_toolset") == digest for c in detail["changes"]):
        detail = _get("/api/v1/servers/" + target["id"]) or {}
    note = fetch(HISTOR + "/api/v1/log/checkpoint/cosigned")  # noqa: F821
    witnessed_head = note.ok
    if not witnessed_head:
        # A HISTOR without the route (before 2026-11-21) or with no co-signed head: prove against the
        # newest head, signed by the log alone, and say so — "logged", never "witnessed".
        note = fetch(HISTOR + "/checkpoint")  # noqa: F821
        if not note.ok:
            raise RuntimeError("HISTOR served no checkpoint (" + str(note.status) + ")")
    size, root, log_ok, witnesses = check_note(note.text)
    label_id = label_for(detail, digest, size)
    if not label_id:
        out.update(
            witnessed=False,
            verdict="no_label_under_witnessed_head",
            checkpoint={"tree_size": size},
            detail="HISTOR's labels for this set are newer than the last head the witnesses "
            "co-signed (it pushes every 10 minutes): ask again shortly",
        )
        return out
    label = _get("/api/v1/labels/" + quote(label_id, safe=""))
    proof = _get("/api/v1/labels/" + quote(label_id, safe="") + "/proof?tree_size=" + str(size))
    if not label or not proof:
        raise RuntimeError("HISTOR did not serve label " + label_id + " or its proof")
    mtl = (label.get("credentialSubject") or {}).get("mcpTrustLabel") or {}
    named = (mtl.get("toolSet") or {}).get("digestSRI")
    leaf = hashlib.sha256(b"\x00" + jcs(label).encode("utf-8")).digest()
    index = int(proof.get("leafIndex", -1))
    path = [bytes.fromhex(h) for h in proof.get("inclusionProof") or []]
    computed = inclusion_root(leaf, index, size, path)
    checks = [
        {
            "check": "label_names_this_set",
            "ok": named == digest,
            "detail": "the label's toolSet.digestSRI is " + str(named),
        },
        {
            "check": "label_names_this_server",
            "ok": (mtl.get("server") or {}).get("name") == target.get("name"),
            "detail": "label server " + str((mtl.get("server") or {}).get("name")),
        },
        {
            "check": "inclusion",
            "ok": computed == root,
            "detail": "leaf "
            + str(index)
            + " of "
            + str(size)
            + ": "
            + (
                "the path leads to the checkpoint's root"
                if computed == root
                else "the path does not lead to the root"
            ),
        },
        {
            "check": "log_signature",
            "ok": log_ok,
            "detail": "Ed25519 under " + LOG_VKEY.split("+")[0],
        },
        {
            "check": "witnesses",
            "ok": bool(witnesses) or not witnessed_head,
            "detail": str(len(witnesses))
            + " of "
            + str(len(WITNESS_VKEYS))
            + " pinned witnesses co-signed this head",
        },
    ]
    proven = all(c["ok"] for c in checks)
    if not witnessed_head:
        checks[-1]["detail"] = (
            "HISTOR named no co-signed head; proved against its newest head, "
            "signed by the log alone"
        )
    out.update(
        witnessed=proven and witnessed_head and bool(witnesses),
        verdict=("witnessed" if witnessed_head else "logged") if proven else "proof_failed",
        checks=checks,
        label={
            "id": label_id,
            "method": (label.get("credentialSubject") or {}).get("method", {}).get("id"),
            "observed_at": mtl.get("observedAt"),
            "unchanged_since": mtl.get("unchangedSince"),
            "leaf_index": index,
            "leaf_hash": leaf.hex(),
        },
        checkpoint={"tree_size": size, "root": root.hex(), "log_signature": log_ok},
        witnesses=witnesses,
        scope="HISTOR observed this tool set at this server; its label is in the log under a head the "
        "listed witnesses co-signed. Nothing here says the tools are safe or describes behaviour.",
    )
    return out
