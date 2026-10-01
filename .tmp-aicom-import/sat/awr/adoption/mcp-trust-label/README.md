# MCP Trust Label — an AWR/2 adoption profile

> **Everything in this directory is a draft on disk.** Nothing has been sent, posted,
> submitted, published or registered anywhere, and no outbound request was made while writing
> it. Distribution is the repository owner's decision.

MCP registry listings we are aware of surface popularity signals — stars, downloads, install
counts. That is **TO VERIFY** against each target's live UI before this document is shown to
anyone: no registry was queried while writing it, and no outbound request was made. MTL turns a
small set of MCP-server security signals into signed AWR `VerificationVerdict` documents whose
*arithmetic* anyone can re-check offline. What is reproducible is the digest comparison, not the
observation it is computed over (see §1.2 of `PROFILE.md`).

**What the label records, as its issuer's signed assertion:** the exact tool definitions the
issuer says a server advertised at a stated time, committed by digest; whether they changed since
a previous label; whether the advertised text matched a published pattern set; whether the
server's name and coordinates matched a published threat record set. The signature makes those
statements attributable to one Ed25519 key and tamper-evident. It does not establish that the
retrieval happened, or when.

**What it does not record at all:** that any code was read, any package inspected, or any tool
invoked. Nothing in this ecosystem audits an MCP server's source, and the profile provides no
vocabulary for claiming otherwise.

| File | Read it if |
|---|---|
| [`PROFILE.md`](PROFILE.md) | you are implementing an issuer or judging whether the claims are sound. Normative, BCP 14. Start with the Abstract, then §12 (non-goals) |
| [`registry-integration.md`](registry-integration.md) | you run a registry and want to consume labels. Five minutes to check a signature — but read §3.2 first: the one check that matters is not five minutes (see below) |
| [`examples/`](examples/) | you want real signed bytes. Four labels signed by the AWR/2 reference implementation; re-verified 2026-08-24, each `valid=true profile=null` (SPEC §10.4 — a verdict is not a receipt), 0 reasons, 0 warnings, exit 0 |
| [`tools/mtl_subject.py`](tools/mtl_subject.py) | you need to compute a subject digest — issuer side or registry side |

## The cost we are not going to bury

Checking a label's signature takes five minutes. The check that makes a label *mean* anything —
§4.6, recomputing the subject digest — is **REQUIRED**, and it requires the consumer to retrieve
the tool set itself. For a `stdio` server, which is the transport of both shipped examples and of
most MCP servers, retrieving a tool set means installing the package and **executing it** to
answer `tools/list`. In sandbox terms that is an untrusted-code execution fleet, not an
integration.

If you will not do that, §4.6's fallback has you compare `mcpTrustLabel.server` against your own
record and render the label as **unconfirmed subject**. Read §13.1 before deciding that is
enough: in that mode a valid signature can certify a claim about a different server, and §13.1
calls subject substitution the primary attack on the format. We do not have a third option to
offer, and a registry whose whole economics rest on *not* executing what it lists should weigh
this before anything else in the profile.

## Three decisions worth knowing before you read further

1. **Three of the four methods can never return `fail`.** `fail` in AWR means the verifier
   judged the work wrong, and a regex match over advertised prose cannot establish that. The
   shipping pattern set flags an ordinary tool that accepts an `api_key`, so `inconclusive` is
   the only honest non-`pass` outcome (`PROFILE.md` §7.3).
2. **Labels carry no score.** The available composite is a product including a constant from a
   gate that never executes; a flawless server's ceiling is 0.540. Publishing that as a `[0,1]`
   safety score would be the most misleading thing the profile could do (§6.4, §8).
3. **AWR profiles L0/L1/L2 do not apply.** There is no `WorkReceipt` for a server, so L1's
   "the judge is not the judged" guarantee is structurally unavailable. Corroboration —
   distinct issuer DIDs agreeing on the same subject digest — is the substitute (§3.2, §9.4),
   and it is a weak one: distinct DIDs are distinct **keys**, keys are free, and a count over
   DIDs the consumer has not allow-listed as separately operated is a count of keypairs, not of
   parties (§13.3).

## Open items before this could be sent anywhere

- The profile namespace URI `https://verify.modelmarket.dev/ns/awr/mtl/v1` is an identifier
  and is **not currently served**. Verifiers must not dereference it, but a reviewer will look.
  `urn:awr:` is not an IANA-registered URN namespace either.
- Whether the AWR reference implementation is installable from a package registry is **not
  asserted** — **TO VERIFY**; `registry-integration.md` §2 says install from source and flags it.
- **There is no MTL issuer.** Nothing in this repository connects to an MCP server and issues a
  label. `examples/generate.py` builds labels over two invented servers from hardcoded tool
  arrays, and the pattern matches inside them are Python literals transcribed from a gate the
  generator never executes (Appendix A of `PROFILE.md` says so; `examples/test_examples.py`
  checks the transcription against the source, which is not the same as producing it). AWR/2 has
  zero production emitters.
- The registry-facing **MUST**s in this profile bind a consumer that chooses to claim MTL/1
  conformance, and nothing else. MTL has no authority over anyone and asks for none (§1.3
  principle 5, §9).
- The claim about what registry listings display is **TO VERIFY** against each target's live UI.
  No registry UI was queried.
- No registry has been contacted, and no adoption, endorsement or interest is claimed anywhere
  in these documents.
