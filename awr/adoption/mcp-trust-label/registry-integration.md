# Consuming an MCP Trust Label — registry integration

> **Draft on disk.** Nothing in this directory has been sent, published or submitted anywhere.
> This is a proposal for review, not an announcement.

Five-minute version. Normative detail is in `PROFILE.md`; section references below point there.

**What you get:** a document in which the holder of one Ed25519 key states that it retrieved an
MCP server's tool definitions at a stated time, commits to their exact bytes by digest, and
reports whether those bytes changed since last time and whether they matched a published pattern
list. The signature makes that statement attributable to the key and tamper-evident. **It does
not establish that the retrieval happened, or when** — the issuer is a pseudonymous `did:key`
with no verified identity behind it (AWR SPEC §3.1 gives `issuer.name` no trust weight, and
`PROFILE.md` §9.1 forbids displaying it as one), `observedAt` is an issuer claim with no
timestamping authority behind it (`PROFILE.md` §13.5), and an issuer can fabricate a tool set
outright.

**What you do not get:** a code audit, a safety verdict, or a score. Nobody read the server's
source. `PROFILE.md` §12 is the full list of what the label does not prove, and it is worth the
two minutes.

**The cost, before you read further.** §3.2 below is not optional, and it is not five minutes:
it requires you to retrieve the tool set yourself, which for a `stdio` server means executing the
package you are listing, in a sandbox you operate. If you will not do that, the fallback renders
the label as `unconfirmed subject` — a mode in which a valid signature can certify a claim about
a different server (`PROFILE.md` §13.1). Decide that before building anything.

---

## 1. The one file to fetch

A label is a single JSON document — a W3C Verifiable Credential, media type `application/vc`,
no authentication required. Store one URL per server in your listing record.

Recommended layout for an issuer, so you can cache correctly:

| Path | Content | Caching |
|---|---|---|
| `<base>/mtl/v1/<subject-sha256-hex>.awrb.json` | every label for one exact tool set, as an AWR bundle | immutable — content-addressed |
| `<base>/mtl/v1/by-server/<urlencoded-registry>/<urlencoded-name>/latest.awrb.json` | the current bundle for a server name | revalidate |
| `<base>/mtl/v1/subject/<subject-sha256-hex>.json` | the MCP Server Descriptor (§4) | immutable |
| `<base>/mtl/v1/patternset/<id>.json` | the pattern list a scan ran under (§7.3) | immutable |

Poll `latest` on your own schedule. A bundle is just `{"awrBundle":"2.0","documents":[…]}` and
carries no claims of its own (AWR SPEC §9) — every document inside is verified separately.

**Fetch and verify are separate phases.** Verification must not touch the network (AWR SPEC
§13.5). Download first, then verify the bytes you have.

## 2. Install a verifier

The AWR/2 reference implementation is pure Python plus `cryptography` for Ed25519, and **no
module in the package imports a networking library** — verified by auditing every `import`
statement in `awr/reference/python/awr/*.py`, which resolve to the standard library plus
`cryptography`. There is no runtime egress assertion, so treat that as a property of the source
rather than an enforced guarantee; if you need the guarantee, run the verifier in a sandbox with
no network.

```bash
pip install ./awr/reference/python      # provides the `awr` CLI
```

A **second implementation** exists in `awr/rust/`, written from the specification prose without
reading the Python source. It is an independent codebase, **same author, same repository — no
second party has implemented AWR**, so it is evidence that the prose is implementable twice, not
evidence that anyone outside this project agrees with our reading of it. Any conformant W3C VC
library with `eddsa-jcs-2022` support should be able to verify a label too — the label is an
ordinary VC and nothing issuer-specific is required — but **TO VERIFY**: no third-party VC
library has been tested against an AWR document.

*(Registry availability of the reference implementation is not asserted here — install from
source. **TO VERIFY** before publishing this document: whether `awr` is published on PyPI.)*

## 3. Verify offline — four checks

### 3.1 Signature and structure

```bash
awr verify label.awr.json
```

Exit `0` and `"valid": true` means: this issuer signed these claims and the bytes are intact.
Exit `1` means don't display it. Output for the included example, **abridged** — the real
document has nine top-level keys (`valid`, `awrVersion`, `documentType`, `profile`, `reasons`,
`warnings`, `chain`, `documentDigestSRI`, `profilesEvaluated`) and `profilesEvaluated` carries
`AWR-PROFILE-001` for L1 and L2, which for a label is expected and not a defect (§3.2):

```json
{
  "valid": true,
  "documentType": "VerificationVerdict",
  "profile": "L0",
  "reasons": [],
  "warnings": []
}
```

Verify each document individually. Do **not** rely on bundle subject resolution: a bundle
containing no `WorkReceipt` is reported as `AWR-BUNDLE-003` (subject ambiguous) unless you name
a subject explicitly (`PROFILE.md` §6.2).

Ignore `"profile": "L0"`. AWR's L0/L1/L2 assurance profiles are defined over a `WorkReceipt`
and do not apply to a label. **Do not display an AWR profile level** (`PROFILE.md` §3.2).

### 3.2 Is the label about *this* server?

**This is the check that matters most, and a signature check does not cover it.** A valid label
is a portable document about *some* subject; whoever controls your listing pipeline can attach a
clean server's label to a different server and every signature will still pass.

Rebuild the descriptor yourself from your own record of the server's name and your own retrieval
of its tool list, then compare digests.

**Say the quiet part first: "your own retrieval" means you run the server.** For a `stdio`
server — the transport of both shipped examples, and of most MCP servers — answering `tools/list`
means installing the package and **executing it**. There is no way to obtain a tool set from a
`stdio` server without running its code, and MTL/1 offers no signed installable-artifact digest
that would let you skip it (`PROFILE.md` §8.5: nothing in this ecosystem produces one). So the
honest shape of the requirement is: an untrusted-code execution sandbox per listed server, on
your infrastructure. If that is not something you will operate, use the fallback at the end of
this section and read `PROFILE.md` §13.1 about what it costs you.

```bash
awr digest my-descriptor.json
# sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s=
```

That must equal `credentialSubject.verifiedWork.digestSRI`. Mismatch → `MTL-SUBJ-004`, do not
display the label as being about that server.

`tools/mtl_subject.py` builds the descriptor for you:

```bash
python tools/mtl_subject.py tools-list.json \
  --server-name com.example/weather \
  --registry urn:awr:mtl:1:registry:example \
  --server-version 1.4.2 --transport stdio
```

If you can't retrieve tool lists yourself, compare `mcpTrustLabel.server` against your record
instead and render the label as **unconfirmed subject** — not as a label about that server.

### 3.3 Do you accept this issuer?

Anyone can generate a `did:key` in a millisecond and issue a perfectly valid `pass` label about
their own malicious server. MTL provides accountability, not authority.

Keep an explicit allow-list of `issuer.id` DIDs whose labels you render as trust signals.
Everything else: store it, don't badge it. Ignore `issuer.name` inside the document as an
identity — it is issuer-supplied and carries no trust weight; bind display names to DIDs in
your own table.

There is no revocation in AWR (SPEC §13.6). Removing a DID from your allow-list is the only way
to retire a compromised issuer.

### 3.4 Do you know the method?

Read `credentialSubject.method.id`. Four are defined. Every "says" below is the **issuer's
assertion**, not an established fact:

| `method.id` | The issuer says | `pass` | `fail` |
|---|---|---|---|
| `…:method:tool-set-observation` | it retrieved these exact tool definitions at this time | retrieved and digested | never |
| `…:method:tool-def-pattern-scan` | it matched the advertised text against a published pattern list | zero matches | never |
| `…:method:tool-set-continuity` | the definitions are/aren't identical to a prior label's | unchanged | **changed** |
| `…:method:name-threat-match` | the name and coordinates aren't on a published list | no match | never |

Unknown method id → don't render it (`MTL-METH-001`). A `verdict` the method can't produce →
reject it (`MTL-METH-002`).

Anything typed `MCPTrustOpinion` instead of `MCPTrustLabel` is a **model's judgement**, not
reproducible. Never put it in a badge, a filter, or an aggregate; if you show it, name the model
(`PROFILE.md` §7.6).

### 3.5 Minimal consumer, end to end

Every check MTL/1 makes a **MUST** is here, including the two that are easy to skip: the
verdict-permitted-for-method check (`MTL-METH-002`, `PROFILE.md` §7.1) and the opinion quarantine
(`MTL-OPIN-001`, §7.6). Note the `returncode` handling — on exit `2` (usage or I/O error, e.g.
`awr` not on PATH) stdout is empty, and a consumer that goes straight to `json.loads` raises
`JSONDecodeError` instead of refusing the label.

```python
import json, subprocess
from mtl_subject import build_descriptor, descriptor_digest   # tools/mtl_subject.py

ALLOWED_ISSUERS = {"did:key:z6Mk..."}                          # your allow-list, §3.3
NEVER_FAIL = {                                                 # §7.1: fail is not permitted
    "urn:awr:mtl:1:method:tool-set-observation",
    "urn:awr:mtl:1:method:tool-def-pattern-scan",
    "urn:awr:mtl:1:method:name-threat-match",
}
KNOWN_METHODS = NEVER_FAIL | {"urn:awr:mtl:1:method:tool-set-continuity"}
VERDICTS = {"pass", "fail", "inconclusive"}

def accept(label_path, server_name, registry, tools):
    proc = subprocess.run(
        ["awr", "verify", label_path], capture_output=True, text=True)
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        return None, ["VERIFIER-UNAVAILABLE"]     # exit 2: no result was produced — refuse
    result = json.loads(proc.stdout)
    if not result["valid"]:
        return None, [r["code"] for r in result["reasons"]]        # 3.1

    label = json.loads(open(label_path, "rb").read())
    subject = label["credentialSubject"]
    block = subject.get("mcpTrustLabel", {})

    if "MCPTrustOpinion" in label["type"]:
        return None, ["MTL-OPIN-001"]              # §7.6: never a label slot, badge or filter
    if "MCPTrustLabel" not in label["type"]:
        return None, ["MTL-DOC-001"]
    if block.get("reproducibility") == "model-dependent":
        return None, ["MTL-OPIN-001"]              # §7.6: typed as a label but is an opinion
    if "score" in subject or "threshold" in subject.get("policy", {}):
        return None, ["MTL-DOC-003"]                               # §6.4: labels carry no score
    if label["issuer"]["id"] not in ALLOWED_ISSUERS:
        return None, ["MTL-ISS-001"]                               # 3.3
    method = subject["method"]["id"]
    if method not in KNOWN_METHODS:
        return None, ["MTL-METH-001"]                              # 3.4
    verdict = subject["verdict"]
    if verdict not in VERDICTS or (verdict == "fail" and method in NEVER_FAIL):
        return None, ["MTL-METH-002"]              # §7.1: verdict not permitted for this method

    descriptor, _, _ = build_descriptor(
        server_name=server_name, registry=registry, tools=tools)
    if descriptor_digest(descriptor) != subject["verifiedWork"]["digestSRI"]:
        return None, ["MTL-SUBJ-004"]                              # 3.2 — the important one

    return verdict, []
```

`tools` in that signature is **your own** retrieval of the server's tool list (§3.2). If you do
not have one, this function cannot be called, and there is no version of it that reaches the last
check without you executing the server.

## 4. What to display

Show four things, always together: the **outcome**, the **issuer**, `mcpTrustLabel.observedAt`,
and **what was checked**. A bare check mark without the issuer and date misrepresents the format
(AWR SPEC §13.7).

**Never use these words** for any MTL outcome: *safe, secure, audited, certified, approved,
trusted*, or an unqualified *verified*. No method supports them.

| Outcome | Say | Don't say |
|---|---|---|
| `pass` observation | "Tool definitions pinned 30 Jul by *issuer*" | "Verified", "Audited" |
| `pass` pattern scan | "No known injection or secret-request patterns in the advertised definitions" | "Safe", "No vulnerabilities" |
| `pass` continuity | "Definitions unchanged since 24 Jul" | "Stable and secure" |
| `pass` name-threat | "Name not on threat list *id*" | "Not malicious" |
| `inconclusive` | "3 patterns matched — see details" + the codes | "Failed", "Dangerous", red |
| `fail` continuity | "Tool definitions changed 30 Jul — re-approval recommended" | "Compromised", "Rug-pull" |
| no label | "No label" | "Failed" |

Three rules that decide whether this ecosystem stays honest:

1. **`inconclusive` is neutral, not failure.** Don't colour it red, don't count it as a failure,
   and don't rank a server holding one below an unlabelled server. Penalising `inconclusive`
   teaches issuers to launder it into `pass`, and then the label is worth nothing.
2. **Don't sort by match `severity`.** Those values come from the pattern list and MTL attaches
   no risk meaning to them (`PROFILE.md` §7.3).
3. **A missing label means nobody ran a scanner.** It is not a negative signal.

If you need one glyph, derive it — and publish your rule, and don't attribute it to the issuer.
A rule that stays within what the labels support: **Pinned** / **Pinned, unchanged N days** /
**Changed** / **Flagged for review** / **Unlabelled**.

**Corroboration, and what it is worth:** a single label is one key's claim. You can count
**distinct issuer DIDs** carrying valid labels with the same `verifiedWork.digestSRI` and the
same `method.id`, and that count is checkable. What it is *evidence of* depends entirely on you:
two DIDs are two **keys**, and generating a `did:key` costs nothing. The count is evidence that
two **parties** retrieved and canonicalized identically only if your allow-list (§3.3) records
those two keys as separately operated — otherwise it is one party with two keys, or a copier who
never retrieved anything and lifted the digest out of the first label, where it is published in
the clear. A corroboration count over DIDs you have not allow-listed as separate operators is a
count of keypairs; do not display it as agreement between parties (`PROFILE.md` §13.3).

Two issuers *disagreeing* on the digest for the same server at nearby times suggests a server
serving different definitions to different clients; surface it rather than picking a winner
(`PROFILE.md` §9.4) — and note that this detector needs two genuinely separate operators, so it
inherits the same caveat.

## 5. Failure modes

| What you see | Means | Do |
|---|---|---|
| `AWR-PROOF-006` | signature failed — bytes altered in transit or storage, or re-serialized | Don't display. Re-fetch. Most self-inflicted cases are a JSON round-trip through a lossy store: never re-serialize a label, store the **original bytes** (AWR SPEC §4.2) |
| `AWR-CANON-004` | duplicate JSON key | Reject; your parser's choice would decide which bytes were signed |
| `AWR-DOC-009` | `awrVersion` major you don't implement | Reject, don't guess |
| `AWR-BUNDLE-003` | you verified a bundle instead of its documents | Verify each document individually (§3.1) |
| `AWR-TIME-001/002` | timestamps outside your clock window | **Warning only.** Age is policy, never validity (AWR SPEC §11.3) |
| `MTL-SUBJ-004` | your recomputed subject digest ≠ the label's | The label is not about this server, or the server changed since it was issued. Never display it against this listing |
| `MTL-NUM-001` | a tool schema contains a non-integer number, so the tool set isn't digestible | Expect `inconclusive` and no `toolSet.digestSRI`. **Never** show drift as `fail` for this subject — there's no digest to compare |
| `MTL-ISS-001` | issuer not on your allow-list | Store, don't badge |
| `MTL-METH-001` | unknown method | Store, don't badge |
| `MTL-DOC-003` | the label carries a `score` | Reject the label: MTL/1 forbids scores, so the issuer is non-conformant |
| Only `inconclusive` labels for a popular server | normal | An `api_key` property alone does it: executed here against `warden/dist/static-scan.js` (2026-08-24, ruleset v3), a single tool with a neutral description and an `api_key` property produces one `advise`-tier `TOOL_DEF_CREDENTIAL_PARAM` match at severity `low`, leaving the gate score at 1.0 — the scanner itself does not treat it as a defect. Not a red flag |
| Two issuers, different subject digests, same server | the server varies its advertised definitions, **or** one issuer canonicalizes wrongly | Investigate. Compare against your own recomputation (§3.2) to see who's right |
| Continuity `pass` for months on a remote server | weak signal | Definitions are served by the same party that serves behaviour. Show `transport` next to the claim (`PROFILE.md` §13.4) |

## 6. What this asks of you, in total

1. One URL field per server record.
2. A periodic fetch.
3. `awr verify` per document.
4. **Your own retrieval of each server's tool set, and one digest recomputation over it** — the
   step that binds the label to your listing (§3.2). For a `stdio` server this is an
   untrusted-code execution sandbox. This is the item that dominates the cost, by a wide margin.
5. An issuer allow-list you maintain, with a record of which DIDs you treat as separately
   operated (§3.3, and the corroboration caveat in §4).
6. Display strings that don't say "safe".
7. A local cache of the artefacts a label points at — see the next paragraph.

No accounts, no API keys, no calls back to any issuer, no chain, no dependency on the ecosystem
that produced the label.

**If the issuer disappears tomorrow, every label it ever signed still verifies — but not
everything still *means* anything.** The signature check is self-contained; the label's content
is not. A pattern-scan label is comparable only through `patternSet.digestSRI` (`PROFILE.md`
§7.3: "without the digest the label is unfalsifiable"), a continuity label needs the prior label
it references (`MTL-CONT-001`), and `PROFILE.md` §10 leaves publication of those artefacts as a
**SHOULD** on the issuer. Issuer vanishes → the digests dangle → a valid signature over "no known
patterns matched (pattern set `<unknown>`)". So cache the pattern sets, the record sets, the MSDs
and the prior labels yourself, keyed by digest, as you receive them. That is the difference
between durable evidence and a signature over an unresolvable reference.
