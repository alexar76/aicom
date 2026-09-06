# Charter contracts — telling the factory what it must not get wrong

Every quality gate in the pipeline is **structural**. `api_contract_check` asks whether the routes
match the spec, `frontend_build_check` whether the bundle builds, `product_demo_journey` whether a
real account can log in and read every list endpoint, `duplicate_module_check` whether the modules
resolve, `foreign_subsystem` whether a subsystem was ordered at all.

Not one of them can see that a function is **wrong while being well-formed**.

That is fine for most products. It is not fine for a product whose value *is* a claim about its own
output — a verifier, a sampler, a signer, a meter, a settlement split. For those, correctness is not
a quality attribute layered on top of the feature; it is the feature, and a plausible-looking wrong
answer is worse than a crash, because a crash gets fixed.

This is not a hypothetical class of defect in this ecosystem. It has shipped three times, and all
three are one bug wearing different clothes:

| What shipped | Where |
|---|---|
| A randomness output not derived from the committed entropy, signed with the real key — so the proof verified anything you handed it. Shipped in **both** copies of platon. | `oracles/oracles/platon/backend/tests/test_randomness.py:117` |
| A prover emitting `alpha` as bare hex and a verifier decoding it as UTF-8 — so **every honest proof the oracle issued verified as false**, in a paid verification capability. | `oracles/oracles/sortes/tests/test_vrf.py` |
| A signed bill of materials carrying no algorithm and no key, whose read route appends a field *after* signing — so a buyer's verifier cannot succeed. | `web/backend/services/ai_market_protocol/pipelines.py` |

None crashed. All returned plausible JSON. Each was found by a person staring at the composition of
two functions, which is not something a pipeline can be relied on to do — and each was found *after*
shipping.

So a charter can now carry two blocks the pipeline **enforces** rather than interprets. They are
parsed by [`core/charter_contracts.py`](../core/charter_contracts.py) and enforced in the QA stage by
[`pinned_dependency_gate`](../web/backend/services/pinned_dependency_gate.py) and
[`property_contract_gate`](../web/backend/services/property_contract_gate.py). Both follow the
convention `charter_fidelity` established: a marked section, checked deterministically, with no model
call in the loop.

---

## `pinned dependency` — import this, do not rewrite it

The factory's instinct under repair pressure is to write a new module rather than call the existing
one. `duplicate_module_check` exists because a developer agent answered "cannot import
`get_password_hash`" by writing a fifth seeding module. This block covers the case one level up: the
tree is clean, the roles are distinct, and the single module the product's correctness rests on was
written from scratch instead of imported.

The reason prose cannot prevent this is that the reimplementation *works*. Right signature, right
shape, passes any test written against it — including tests the agents write themselves. What it does
not have is the property the original was verified for. Sortes' ECVRF is byte-exact against the RFC
9381 Appendix B.3 vectors in both directions; a fresh implementation that is merely self-consistent
passes everything you would think to test and is interoperable with nobody.

```
====== pinned dependency ======
module: sortes.vrf
symbols: prove, verify, proof_to_hash
requires: aimarket-oracle-core
why: RFC 9381 ECVRF-EDWARDS25519-SHA512-TAI, byte-exact against the Appendix B.3 vectors
     in both directions. A reimplementation produces proofs that verify anything.
```

| Key | Required | Meaning |
|---|---|---|
| `module` | yes | Import path. Matched by dotted suffix, so `sortes.vrf` also matches `oracles.oracles.sortes.sortes.vrf` — the operator does not have to guess which path the agents will write. |
| `symbols` | yes | The pinned surface. Comma- or space-separated. |
| `requires` | no | Distribution name that must appear in the product's requirements manifest. |
| `why` | no | Quoted verbatim in the finding, so the developer agent reads the reason and not just the rule. |

Findings:

- **`pinned_dependency_unused`** (blocking) — nothing in the tree imports the pinned module. The
  clearest signal, and it suppresses the per-symbol findings, because one instruction beats five
  restatements of it.
- **`pinned_dependency_reimplemented`** (blocking) — a pinned symbol is defined locally and imported
  nowhere. The reflex this gate exists for.
- **`pinned_dependency_undeclared`** (blocking) — imported, but `requires` is absent from the
  manifest. Resolves in the build environment and not in the deployed one, which is the same defect
  discovered at the worst moment; this ecosystem has had that incident twice.
- **`pinned_dependency_shadowed`** (non-blocking) — defined locally *and* genuinely imported. A
  same-named wrapper is a legitimate pattern, and per `charter_fidelity`'s rule, a gate that cries
  wolf gets switched off.

Test files and `frontend/` are never accused: a test stub named like a pinned symbol is noise.

---

## `executable property` — a statement the pipeline checks by running it

Not a test the agents write (agents write tests that pass) but a property the operator states and the
gate enforces from outside, against the built tree.

```
====== executable property ======
name: the selection depends on the randomness
kind: sensitive
target: app.sampling:select
vary: alpha
args: {"roster_digest": "a3f1", "alpha": "seed", "k": 5, "population": 500}
```

Five kinds, each chosen because it maps onto a defect above rather than onto a textbook:

| `kind` | Holds when | Catches |
|---|---|---|
| `deterministic` | `trials` identical calls return identical results | an unseeded `random`, a clock read, iteration order leaking into a result |
| `sensitive` | varying `vary` produces more than one distinct output | **the vacuous-proof shape** — the output not depending on what it claims to depend on |
| `roundtrip` | `inverse(target(x)) == x` | prover and verifier disagreeing on a wire format, invisible until composed |
| `distinct` | no duplicate elements in the output | a k-of-n draw without replacement that repeats an element |
| `uniform` | the output distribution passes a chi-square goodness-of-fit test **and the run had the power to detect the canonical bias** | modulo bias, which is indistinguishable from fairness on any single call |

Keys beyond `name`/`kind`/`target`/`args`: `vary` (required for `sensitive` and `uniform`),
`inverse` (required for `roundtrip`), `buckets`/`trials`/`alpha`/`detect` (for `uniform`), `trials`
(optional elsewhere, default 32).

A malformed block is reported as `executable_property_malformed` and **blocks**, because an
unexecutable property reads as a checked guarantee and is not one. A gate that could not run is
reported as `executable_property_not_run` and also blocks: that is the same epistemic position as an
unrun test suite, and this pipeline has twice mistaken one for the other.

Product code is agent-written, so it runs **out of process with a scrubbed environment** — the
ecosystem audit already found generated code inheriting `os.environ`, and a gate that hands the
factory's secrets to the code under test would be a worse defect than the one it is looking for.

### Why `uniform` refuses to pass an underpowered run

This was measured while building the gate, on a fixture sampler doing `byte % 12` — textbook modulo
bias, the exact bug the check is for:

```
chi2 = 19.17   critical value (alpha=0.001, df=11) = 31.43   n = 24000   ->  PASSED
```

The bias was real. The test simply lacked the power to see it, and the first version of this gate
reported it as uniform. **A fairness gate that answers "probably fine" when it means "I could not
tell" is worse than no gate**, because the product it approves ships a fairness claim on its
authority — the same defect as a survey quoting a number nobody can reproduce.

So failing to reject only counts as uniform when the run demonstrably had the power to reject the
canonical bias for that bucket count. `modulo_bias_w(buckets)` computes Cohen's *w* for
`byte % buckets` exactly — for 12 buckets, `256 = 21*12 + 4`, so four buckets get 22/256 and eight
get 21/256, giving `w = 0.0221`. Required sample size follows from the non-central chi-square at
`UNIFORM_POWER`:

```
w = 0.0221   lambda_req = 43.4   n_req = 88 979 observations
```

At that n the same fixture separates cleanly — the fair sampler gives `chi2 = 15.84` and the biased
one `chi2 = 40.81`. `UNIFORM_POWER` is **0.95, not the textbook 0.80**: at 0.80 the biased sampler
came in at `chi2 = 32.01` against a critical value of `31.43`, a coin-flip from approval, and the
extra power costs about 40% more trials (89k vs 63k — both a few seconds).

If `buckets` divides 256 exactly there is no canonical bias, and the gate says so rather than
inventing an effect size; declare `detect: <w>` to gate on a specific one. Below `df = 8`
(`buckets < 9`) the Wilson–Hilferty critical-value approximation is not trustworthy, and the gate
declines to judge instead of judging badly.

---

## What this does not do

- **It does not verify cryptography.** `sensitive` establishes that an output depends on an input,
  not that a proof is sound. Soundness comes from pinning an implementation that was verified
  against a standard — which is what the other block is for. The two blocks are complements: pin the
  primitive, then assert the properties of the code you wrote around it.
- **It does not replace the operator's judgement about what to state.** An unstated property is an
  unchecked one, and the gate cannot know what you meant to guarantee.
- **`uniform` tests the distribution of what the target returns**, not the fairness of the whole
  product. A sampler that is perfectly uniform over the wrong population is uniform.
