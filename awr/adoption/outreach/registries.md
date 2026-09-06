DRAFT — NOT SENT. Requires the maintainer to review and send.

# Adoption asks, per target

Nothing here has been sent. No target below has adopted, endorsed, reviewed, or agreed to
anything. Naming a project in this table means "someone we intend to ask", nothing more.

**No sentence in the "objection we expect" column was said by any named party.** Those
objections are ours: internal red-teaming, written by us, in our own words, about arguments we
think a maintainer would reasonably make. Nobody at any named project has been contacted, quoted
or paraphrased, and none of that column may be repeated as if it were their position.

## Presence check — verified in this repo, 2026-07-31

Verified by reading files, not by querying any live service. Every "live" status below is a
claim made by a repo document; the live state is unverified from here.

| Directory | Verified evidence in repo | Presence |
|---|---|---|
| **glama.ai** | `aimarket-mcp/glama.json`, `argus/glama.json` (both `$schema: glama.ai/mcp/schemas/server.json`); score badges in both READMEs; `aimarket-mcp/docs/GLAMA.md` documents the admin build form; CI asserts `glama.json` shape (`aimarket-mcp/.github/workflows/ci.yml:25-41`) | **Present** for `aimarket-mcp`. `docs/growth/INDEX-AUDIT.md:19` marks `aimarket-oracle-gateway, aimarket-plugins, aimarket-mcp` live and does **not** list `argus` — argus listing is **TO VERIFY** |
| **Official MCP Registry** (`registry.modelcontextprotocol.io`) | `aimarket-mcp/server.json` (`io.github.alexar76/aimarket-mcp`, pypi `aimarket-mcp` 0.2.3), `argus/server.json` (`io.github.alexar76/argus3`, npm `@alexar76/argus3` 0.2.5), `docs/mcp-registries/official-registry-servers.json` (4 servers), `scripts/publish_mcp_registry.sh` | **Present** per `docs/growth/INDEX-AUDIT.md:25` ("active", resolved 2026-07-12). Re-confirm with `./scripts/publish_mcp_registry.sh --check-live` before sending |
| **PulseMCP** | No `pulsemcp` string anywhere in `aimarket-mcp/` or `argus/`. `docs/growth/seeding-playbook.md:86` row A5 is an unchecked box. `docs/mcp-registries/README.md:3` asserts PulseMCP ingests from the official registry | **Not submitted directly.** Any listing would be downstream ingest — **TO VERIFY**, do not assert presence |
| **mcp.so** | No `mcp.so` string in `aimarket-mcp/` or `argus/`. `docs/growth/INDEX-AUDIT.md:26` marks it not-done, reason "manual login"; `seeding-playbook.md:84` row A3 is an unchecked box | **Not present** |
| **Smithery** | No `smithery` string and no `smithery.yaml` in `aimarket-mcp/` or `argus/`. `INDEX-AUDIT.md:26` marks it not-done, reason "manual login"; `seeding-playbook.md:85` row A4 is an unchecked box | **Not present** |

Consequence for outreach: the MCP-registry message may honestly say "we maintain servers
listed on glama.ai and on the official MCP registry". It may **not** claim any mcp.so,
Smithery, or PulseMCP presence.

## Artefact inventory — what we can actually hand over

All counts below were measured on 2026-07-31 at 18:19 UTC. Both implementation trees are under
active development in this repository and the numbers move; re-measure before sending.

| Artefact | Path | State |
|---|---|---|
| Normative spec | `awr/SPEC.md` | Exists, v2.0.0 draft, 992 lines, 66 unique reason codes (counted by extracting every `AWR-XXXX-nnn` token from `SPEC.md`, deduplicating, and counting) |
| JSON Schemas (non-normative) | `awr/schemas/*.json` | Exists, 5 files, all parse |
| Python reference impl + §17 CLI | `awr/reference/python/` | Exists, **3839** lines (`wc -l awr/reference/python/awr/*.py`), exactly one third-party dependency (`cryptography>=41`), no networking import in any module; all five §17 subcommands present; `issue` → `verify --profile L0` green; tamper → `AWR-PROOF-006`; own suite 439 passed with 66/66 reason codes exercised |
| Second implementation (Rust) | `awr/rust/` | Exists, **6782** lines of `src/` (+1246 of `tests/`), implements the §17 CLI (plus a `keygen` extension). **Written from the specification prose without reading the Python source — an independent codebase, same author, same repository. No second party has implemented AWR.** Re-checked here on one document, both directions: identical `proofConfigHash`/`transformedDocumentHash`/`hashData`, identical document digest, each verifies the other's issued receipt as valid L0, both reject a one-field tamper with `AWR-PROOF-006`. **One document is not a conformance result, and the two codebases share an author** |
| Test vectors | `awr/vectors/` | **Now exists** (did not at 10:10 the same day): 124 files under `valid/`, `invalid/`, `canonicalization/`, `proof/`, plus `index.json` and `generate.py`. Re-check contents before sending |
| Conformance matrix | `awr/conformance/` | **Still does not exist** as of 18:19 UTC. Re-check before sending |

**Pre-send gate:** every draft in `drafts/` links to the conformance matrix. Do not send any
of them until `awr/conformance/` exists, is published at a stable URL, and that URL has
replaced the `<CONFORMANCE-MATRIX-URL>` token in the draft.

## The asks

The last column is **our own** anticipated objection, written by us. It is not a quotation, not a
paraphrase of anything anyone said, and not attributable to the named project.

| # | Target | The ask (one sentence) | What they get | Artefact we hand them | Objection we expect (our words, not theirs) |
|---|---|---|---|---|---|
| 1 | **glama.ai** | Add an optional `awrReceipt` field to your server manifest schema so a server can declare the `did:key` it signs receipts with. | A signal about a server that is checkable offline by anyone, unlike a self-reported description. | Spec §3.1/§5, the schemas, and the conformance matrix URL. | That their score rubric already covers tool quality, and a key nobody verifies adds a field nobody reads. Fair — the honest counter is that the ask is worthless until a client verifies, so ask for the field only after an emitter ships. |
| 2 | **Official MCP Registry** | Consider whether `server.json` should have a place for a signing identity, and tell us if the answer is no. | An answer recorded once instead of four directories inventing four conventions. | Spec §5 and §16 mapping table. | That it is out of scope for a registry, identity belonging to the transport/auth layer. Likely correct, and worth hearing early. |
| 3 | **mcp.so** | Nothing yet — submit `aimarket-mcp` and `argus3` through the normal form first; no AWR ask until we are a listed maintainer. | — | — | We are not present. Asking a directory for a schema change before being listed on it is the wrong order. |
| 4 | **PulseMCP** | Same as #3 — establish presence via the official-registry ingest path, verify the listing, then no further ask this quarter. | — | — | Same. |
| 5 | **Smithery** | Same as #3 — a `smithery.yaml` submission is a prerequisite, not an AWR conversation. | — | — | Same. |
| 6 | **OpenTelemetry GenAI semantic conventions (SIG)** | Register one optional span attribute for an AWR document id + digest, so a signed receipt can be correlated with an unsigned span. | The span stops being the end of the evidence chain; auditors get a pointer out of the telemetry store. | Spec §16 (`gen_ai.request.model` → `work.modelId`) plus a one-attribute concrete proposal. | That semconv does not reference non-OTel formats, and that this is a vendor format with no users. Both true today; the answer is to come back with emitters, not arguments. |
| 7 | **Open-source LLM observability (e.g. Langfuse, Arize Phoenix, Traceloop/OpenLLMetry)** | Accept an AWR document as an attachment on a trace and render `issuer.id` next to any verdict you display. | A judge score in your UI becomes attributable to a named key instead of anonymous. | Reference impl (measured 2026-07-31 18:19 UTC: the proof check is `proof.py`, 171 lines, over `jcs.py`, 284 lines; the full verifier reporting all 66 codes is `verify.py`, **1076** lines), the schemas, conformance matrix URL. | That their users want dashboards, not signatures, and nobody has asked for this. Probably true. The wedge is the compliance-adjacent user, not the median one. |
| 8 | **Commercial eval / judge vendors (e.g. Braintrust, LangSmith, Patronus)** | Sign your judge output as a `VerificationVerdict` with your own key, so a customer can show an auditor which key produced the score. | A differentiator a competitor cannot claim by writing a blog post: verdicts a customer can show to their own auditor, attributable to the key that signed them. | Spec §3.4 + §10.2, reference impl `issue` path, conformance matrix URL. | That signing makes their judgements quotable against them in a dispute. That is precisely the point, and it is the strongest reason to refuse. Do not soften it. |
| 9 | **Open-source eval libraries (e.g. Ragas, DeepEval, Inspect)** | Add an optional exporter that writes a `VerificationVerdict` next to the JSON you already emit. | Eval runs become comparable across libraries because `method.id` is explicit and signed. | The verdict schema and one exporter example. | That it is one more output format to maintain for a spec at version 2.0.0 with no adopters. Correct; keep the exporter small enough to be deleted. |
| 10 | **Agent frameworks (e.g. LangGraph, LlamaIndex, CrewAI, AutoGen)** | Emit a `WorkReceipt` per node when a flag is set, with `parents` digest-linking the upstream node. | A DAG whose edges are content-addressed, which is what makes `BlameAttestation` possible at all. | Spec §3.3, §8, `parents` rules, reference impl. | That their users cannot manage a keypair, and that per-node signing is latency they will be blamed for. Real. Measure the Ed25519 cost and bring the number, not a reassurance. |
| 11 | **MCP specification itself** | Ask whether tool-result metadata is the right place for a provenance pointer, before any registry invents its own. | One convention instead of several. | Spec §15 (media type) + §16. | That it is premature and we should bring an implementation. Accept and stop. |

## Sequencing note

Targets 1, 6, 8, 9, 10 and 11 all have the same true objection: **there is no AWR/2 emitter in
production yet.** Sending to them before an emitter exists spends the introduction on the
weakest version of the case. The defensible order is: ship one emitter, complete the conformance
matrix, then send.

Two things that order cannot fix, and they should be said in the message rather than discovered:

- The conformance matrix will cover **two codebases with one author**, not two parties. It
  demonstrates that the prose is implementable twice without the source; it does not
  demonstrate that anyone outside this repository agrees with our reading of it.
- Nothing in the pack currently answers the largest cost to a consumer. For the MTL profile,
  the one non-optional check (`mcp-trust-label/PROFILE.md` §4.6, subject-digest recomputation)
  requires the consumer to retrieve the tool set itself, which for a `stdio` server means
  executing the package it is listing. That is an infrastructure programme, not a five-minute
  integration, and a maintainer will find it whether or not we mention it first.
