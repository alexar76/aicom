DRAFT — NOT SENT. Requires the maintainer to review and send.

# AWR/2 — the ten hardest questions

Answers written for someone who intends to say no. Where the honest answer is "you are right",
it says so. No third party has adopted, endorsed, reviewed, or agreed to anything in AWR.

---

## 1. Why not C2PA? It already does provenance.

C2PA binds provenance to a media asset and is anchored in file formats — pixels, audio, video
frames, and the container that holds them. AWR describes an *invocation*: which model ran over
which input digest producing which output digest, and whether some other key signed a judgement
of the result. Those are different objects. A C2PA manifest cannot express "hop 3 of a 5-node
agent chain returned malformed output, and here is a named key's signed opinion about it", and
it does not try to.

They compose. §16 states that a C2PA assertion **may** carry an AWR document's `id` and
`digestSRI`. AWR deliberately defines no C2PA assertion label of its own, because inventing one
unilaterally would be exactly the land-grab this question suspects.

If your output *is* an image or a video, use C2PA for the asset. Use AWR if you also need the
judge to be nameable.

## 2. Why not just OpenTelemetry? I already have traces.

Because a span is unsigned and operator-owned. Anyone with write access to your collector can
author a span, and nobody outside your organisation can check one. That is fine — telemetry is
for debugging your own system, and OTel is good at it.

The moment the claim has to travel outside the organisation that produced it, "our observability
stack says so" stops being evidence. AWR is for that hop. §16 maps `gen_ai.request.model` to
`work.modelId` and expects a span to carry a receipt `id` as an attribute. AWR is not a place to
put your latency histograms and should not become one.

If your claims never leave your own stack, you do not need AWR. Say so and keep OTel.

## 3. Why a new format instead of a JSON convention everyone agrees on?

Because a convention cannot answer "which bytes were signed". Concretely, here is what AWR/1 —
our own predecessor, a convention over JSON — got wrong, all recorded in Appendix D:

- `id`, `type` and `issuer` were **outside** the signature, so an intermediary could rename a
  valid receipt and re-point a chain at it without breaking any signature.
- Its canonicalization was "JCS-like": NFC normalization, code-point key sort, and 10-decimal
  float truncation. The issuer was written in a language that distinguishes integers from floats
  and the verifier in one that does not, so the two produced **different bytes for the same
  document** and signatures made by one failed under the other. §12 has to accept both dialects
  forever.
- `did:key:` was followed by the first 32 characters of a base64 public key. That is not a valid
  DID, and it named a different key than the document embedded.

None of those are exotic. They are what a convention degrades into when there is no normative
byte-level statement and no negative test vectors. The new format is the same JSON with the
ambiguity removed: RFC 8785 exactly, integers only in signed documents, decimals as strings,
whole-document signing, real `did:key` derivation.

## 4. What stops a verifier from lying?

Nothing. AWR does not make claims true — §1.3 says so, and §13.7 says a valid document means
only "this issuer signed these claims and the bytes are intact".

What AWR removes is *deniability*. A false verdict is signed by a stable `did:key` and is bound
by digest to the exact work it judged, so **a consumer who recomputes that digest** can tell
when the verdict has been reattached to different work, and the signature makes it undisownable
by the key that made it. That converts a lie from anonymous noise into an attributable record
that anyone holding a copy can show was signed by that key — which is what reputation, contracts
and disputes can act on. Two limits stated plainly: without the consumer's digest recomputation
the reattachment is undetectable, and the record is not *permanent* — AWR has no anchoring, no
timestamping authority, no revocation, no publication requirement and no registry. A document is
a file. Delete every copy and there is nothing left. The format supplies the evidence; it does
not supply the consequence, and it does not supply the durability either — whoever needs the
record to survive has to keep it.

Three structural guards, none of which is a truth guarantee:

- L1 requires the verdict's issuer DID to differ from the receipt's issuer DID
  (`AWR-PROFILE-002`), so self-issuance under one key is detectable rather than invisible.
- L2 requires two verdicts from **distinct issuer DIDs**. That excludes a single-key rubber
  stamp. It does **not** exclude one operator running two keys: SPEC §10.3 requires two distinct
  `issuer.id` values and nothing else, AWR has no mechanism that distinguishes two operators
  from two keypairs, and a `did:key` costs nothing to generate. A consumer who needs two parties
  must decide out of band which DIDs are separately operated and allow-list them as such. Do not
  read L2 as sybil resistance.
- `inconclusive` is a first-class verdict that MUST NOT be reported as failure, so a verifier
  that cannot judge has an honest option available and no excuse for guessing.

If you need a verifier to be *punished* for lying, that is a settlement layer and AWR is
explicitly not it (§10.3 references bindings; it defines no scheme semantics).

## 5. What happens when the `@context` URI does not resolve?

Nothing happens, because a conformant verifier never fetches it. §3.1: "A verifier **MUST NOT**
dereference any context URI." §13.5 generalises it to parent documents, evidence bytes,
policies and schemas.

The URI is an identifier, not a location. It is inside the signed bytes, so it names the
vocabulary the issuer committed to; if our domain lapses tomorrow, every existing document keeps
verifying with the same result forever.

This is also a security property, not just resilience: a verifier that fetches lets the
*document author* choose which bytes the verifier reads at verification time.

The trade-off is real and worth stating: AWR gives up JSON-LD expansion and canonical RDF
semantics. `eddsa-jcs-2022` signs the JSON as it is written, so AWR is a VC that uses the VC
envelope without buying into the linked-data processing model.

## 6. Why should I trust your test vectors?

You should not. Test vectors from the format's author are a self-consistency check, and a wrong
vector produced by the reference implementation would be reproduced by anything that trusts it.

What the vectors are actually for: localising a disagreement. `awr/vectors/proof/` records
`proofConfigHash`, `transformedDocumentHash` and `hashData` separately, so when your
implementation disagrees you learn *which of the three steps* differs instead of "signature
failed". The single most common Data Integrity bug is the concatenation order at §6.2 step 6,
and the vectors exist to catch precisely that in one comparison.

The load-bearing check is not our vectors — it is a second implementation written against the
prose. And here is where the honest answer costs us the argument, so read it carefully.

There **is** a second implementation, in Rust. It was written from the specification prose
without reading the Python source, which is a real property: a spec sentence that two codebases
read differently shows up as different bytes, and that is what caught the errors Appendix D
records. But it is an independent *codebase*, not an independent *party*. Same author, same
repository, same work session. **No second party has implemented AWR.** The thing you are
actually screening for — did someone with no stake in this being right implement the spec and
still agree — has not happened, and nothing in this pack should be read as claiming it has.

What was measured, re-run for this document:

- The Python reference passes its own suite: `pytest awr/reference/python/tests -q` → **439
  passed**, and the suite prints its own coverage footer: 66 registry reason codes, **66 of 66**
  exercised by at least one assertion. `pytest .../tests/test_jcs.py --collect-only -q` → **44**
  canonicalization tests.
- On `awr/vectors/valid/receipt-minimal-l0.json`, the Rust and Python CLIs produce byte-identical
  `proofConfigHash`, `transformedDocumentHash` and concatenated `hashData`, and identical
  document digests. Each verifies as valid L0 a receipt the other issued, and both reject the
  same one-field tamper with `AWR-PROOF-006` at exit 1.

That is one document, not a conformance result, and the agreement is between two codebases with
one author. It is the difference we want you to hold us to. When you find a vector that is wrong,
that is the most useful thing anyone can send us — and if you implement the spec yourself, you
would be the first party other than us to have done it.

## 7. What does this format cost me if AWR dies?

An Ed25519 keypair you already know how to make, and a JSON document.

Precisely what you are *not* buying: no dependency on our servers (verification is offline by
specification), no account, no registry entry, no chain, no revocation list, no schema fetch, no
DID resolution, no payment. §10.1 makes L0 free of third parties on purpose.

Measured here, on the smallest L0 receipt in the shipped vector set:

```bash
PYTHONPATH=awr/reference/python python -c \
  "import json; from awr import jcs; \
   print(len(jcs.canonicalize(json.load(open('awr/vectors/valid/receipt-minimal-l0.json')))))"
# 980
```

**980 canonical bytes.** The reference verifier has exactly one third-party dependency
(`cryptography>=41`, for Ed25519), and no module in the package imports a networking library —
established by auditing every `import` statement in the package, which resolve to the standard
library plus `cryptography`. There is no runtime egress assertion, so that is a fact about the
source, not a sandbox guarantee.

If AWR dies, the documents you already emitted remain verifiable, because the proof is
`eddsa-jcs-2022` over RFC 8785 — both published standards we profile rather than invent. The
spec's Abstract makes two claims — that any conformant W3C VC library can check an AWR document,
and that a 100-line implementation can too. Treat **both halves as TO VERIFY**, and treat the
second half as probably wrong as stated: nobody has written a 100-line AWR verifier, and in our
own reference the canonicalizer plus the proof check alone are **455 lines** before `didkey.py`,
`multibase.py` or `digest.py` are counted (`wc -l awr/reference/python/awr/jcs.py
awr/reference/python/awr/proof.py` → 284 + 171). No third-party VC library has been tested
against an AWR document either. What you lose if AWR dies is *our* spec; the residue is a signed
JSON blob whose signature still checks.

## 8. Who is using this in production?

Nobody. AWR/2 has zero production emitters as of this document.

Its predecessor AWR/1 runs in one system (the AIMarket hub's provenance plugin, which issues
`Ed25519Signature2018` receipts), and that deployment is the source of every mistake catalogued
in Appendix D. We are describing our own migration, not a track record.

If your policy is to adopt only formats with third-party production users, AWR fails that policy
today and you should say no. The counter-question is narrower: is any part of §3.4 —
the verdict document — wrong?

## 9. Why not JWS, COSE, or a plain detached signature? Verifiable Credentials are heavy.

Fair. VC 2.0 brings a `@context` you may not want and an ecosystem whose linked-data half AWR
deliberately does not use (see Q5).

The reason it wins anyway: a VC gives issuer identity, a proof purpose, and a validity window in
one envelope that off-the-shelf libraries already parse, and `did:key` resolves offline, so
there is no key-distribution problem to solve separately. A JWS over a bespoke payload would
have obliged us to invent all of that, and §1.2 principle 6 says to profile a standard rather
than build a parallel mechanism.

The overhead is bounded and measurable: **980 canonical bytes** for the smallest shipped L0
receipt, of which 510 (52%) come from the envelope — `@context`, `type` and the `proof` block —
and 369 from the `proof` block alone. Measured by canonicalizing the document with and without
those keys; the command is in Q7. If that is too much for your per-call volume, AWR is the wrong
tool and sampling is a better answer than a smaller format.

## 10. Your spec says a valid document proves almost nothing. Why would I display it?

Correct, and §13.7 is blunt about it: a valid AWR document means this issuer signed these claims
and the bytes are intact. It does not mean the model ran, the digests correspond to real
payloads, the price was paid, or the output is correct.

So do not render it as a green check. §13.7 says that interfaces which show validity without the
issuer identity **misrepresent the format**, and §13.3 says a verifier exposing a single boolean
should surface whether the verdict was self-issued — because "verified by itself" is worse than
no claim at all.

What you display is a name and a judgement: *this* verifier, using *this* method, said pass/fail/
inconclusive about *this* work. Everything AWR provides is attribution. If your product needs to
tell users an output is true, no signature format will do that for you.
