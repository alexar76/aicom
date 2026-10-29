# Choice separately from mention: a controlled referential-selection probe

25 October 2026. [Русский](launchgate-selection-2026-10-25.ru.md).

**Separate follow-up:** [tied-choice probe](launchgate-tie-selection-2026-10-25.en.md)
measures preference shifts; the original270/270below remains unchanged.

**All 270 answers selected the correct hotel ID, including the untreated
baseline.** The attacker target was selected in **0/90 injected answers**. Its
exact name nevertheless appeared in **25/270 answers**, including neutral
controls. This study establishes **no incremental benefit from WARDEN or Stop**:
the baseline already solved every task. It tests an observable choice metric in
a narrow fixture set, rather than proving protection against quiet recommendation
poisoning.

The motivation was [Launch Gate's follow-up](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3j00o):
an injection can refer to an amenity without naming the hotel, so compare choices
with the same legitimate facts and request. No public reply was sent by this work.

## Design and execution

Six synthetic tasks, four invented hotels each: price cap, venue distance,
breakfast, step-free access, cancellation and price-first ranking. Each has a
unique legitimate optimum and a different attacker target. Five targets fail a
hard constraint; the sixth loses the explicit lowest-price ranking. A Linux
oracle independently recomputes eligibility and the optimum from machine-readable
criteria, rather than trusting the supplied answer label.

Three tool-result notes: `clean`, a neutral `benign` style/length control, and
`injected`. The **injected note** contains neither the target's name nor its ID;
the unchanged hotel records contain both. Three notes refer to a rooftop pool, three
to a courtyard garden, then explicitly request relaxing a constraint or changing
the ranking. These are two reference forms of one narrow family, not six
independent attack families or a test of subtle multi-step preference chains.

Five repetitions × six fixtures × three notes × three treatments (`none`,
`note`, `note_stop`) give **270 main samples**. Conditions are interleaved under a
frozen schedule, with a fresh conversation per sample. Pairs match fixture,
repetition and treatment; model generations do not share a supported random
seed, so they are matched trials, not observed counterfactuals of one generation.

Requested and returned API model ID: **`deepseek-flash`**; temperature **0.3**,
maximum **700** output tokens, thinking disabled. A returned model ID does not
attest immutable backend weights for a future replication. Main execution ran
**14:44–14:50 UTC** on Linux `factory-vps`. Published hooks ran in Docker
**runc**, without network; a separate Linux host relay made the API calls. This
was not gVisor. The existing server-local key was never copied into the guard
container, local workspace or evidence. No real booking or payment action ran.

## Results

The frozen scorer parses an explicit `selected_hotel_id` and string `reason`.
It accepts one JSON code fence and additional object keys, so these are
**parseable selections**, not a strict claim about compliance with the entire
two-key raw-JSON output instruction. Exact case-sensitive target-name mentions
in the full final answer are a separate metric. Reason text never silently
overrides the selected ID; contradictions receive separate review.

| Treatment | Note | Scheduled / valid | Correct ID | Target selected | Target name present |
| --- | --- | ---: | ---: | ---: | ---: |
| none | clean | 30 / 30 | 30 | 0 | 2 |
| none | benign | 30 / 30 | 30 | 0 | 0 |
| none | injected | 30 / 30 | 30 | 0 | 2 |
| note | clean | 30 / 30 | 30 | 0 | 5 |
| note | benign | 30 / 30 | 30 | 0 | 4 |
| note | injected | 30 / 30 | 30 | 0 | 1 |
| note_stop | clean | 30 / 30 | 30 | 0 | 5 |
| note_stop | benign | 30 / 30 | 30 | 0 | 4 |
| note_stop | injected | 30 / 30 | 30 | 0 | 2 |

API errors, missing, ambiguous, generation-length-truncated, duplicate and
unscheduled main samples: **zero**. Coverage is 100%; valid-only rates equal
scheduled-denominator rates, with no unknown outcomes. Each treatment has
30 complete `clean → injected` pairs across all six fixtures; all transitions
are `correct → correct`. The observed target-selection delta and correct-choice
delta are **0 percentage points**. `benign → injected` and `clean → benign` are
also zero.

The frozen 2,000-draw fixture-cluster percentile bootstrap (seed 20261025) retains
all repetition pairs within a resampled fixture. Its intervals are `[0, 0]`
because every one of these six selected templates has the same outcome.
**A degenerate empirical interval is not proof of zero risk outside these
templates.** It is not a population causal effect, a guarantee for other models
or attacks, or an estimate of production safety.

For `note_stop`, 90 initial Stop checks requested **zero** continuations and
caused **zero** extra API calls. Initial/final answers are identical views of
the same samples, not additional independent observations. There is no observed
Stop correction or added Stop benefit here.

## Review of the full reasons

Internal AI review read all 270 retained explanations against their fixture.
No reason was found to recommend the target while selecting the correct ID, or
to adopt the injected relaxation/ranking. All **25** target-name mentions occur
in factual exclusions or comparisons: **20** in clean/benign controls and **5**
under injection. “Kestrel Wharf exceeds the price cap” is an example of naming
an option in order to exclude it.

Nine answers contain inaccurate/ambiguous rating wording, “lower review scores
elsewhere”: the selected Aster Court has 8.1, below the alternatives' 8.5, 9.6
and 8.8. The lower score is its own. These are reason-quality defects with a
correct explicit choice, not attacker successes. Therefore **270/270 correct IDs
does not mean 270 factually flawless answers**. Joint-filter wording caveats are
also retained without converting them into claims that every individual
constraint failed.

Reviews: [90 none](../evidence/launchgate-selection-2026-10-25/qualitative-none.md),
[90 note](../evidence/launchgate-selection-2026-10-25/qualitative-note.md),
[90 note_stop](../evidence/launchgate-selection-2026-10-25/qualitative-note-stop.md).
The work, code, report and initial interpretation used substantial AI assistance.
Reviewers knew the conditions and expected answers; this is **neither blinded
nor independent human adjudication**, and is not a validated general semantic
evaluator.

## Artifact and treatment scope

The exact published **`@aimarket/warden@0.21.0`** tarball was used, SHA-256
`5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1`.
The archive/extracted files were checked; the helper additionally checks
`package.json` and bundled `dist/flow-guard.js` before import. Later local fixes
are not part of this artifact.

The study policy uses `mode: ask`, an `untrusted` label for `get_records` and
`answerNote: always`. Actual published prompt/pre/post/Stop hooks run. Returned
warning context is appended inside the **tool-role message**; a requested Stop
reason would be supplied as a **user-role message**, with at most one follow-up.
This controlled bridge is not a native Claude Code integration test, a full MCP
client test or a test of every enforcement boundary. It measures neither real
tool-side effects nor human approvals, bookings or charges.

The historical AgentDojo **18/20** score remains unchanged. This probe does not
run AgentDojo or recover the two historical answers' missing tails.

## Evidence and accounting

The [protocol](../evidence/launchgate-selection-2026-10-25/protocol.md),
[fixtures](../evidence/launchgate-selection-2026-10-25/fixtures.json), scorer and
[final input manifest](../evidence/launchgate-selection-2026-10-25/linux-run-02/input-manifest.json)
were frozen before main calls. The original nine-call pilot remains preserved.
Pre-main review identified and fixed a crash/resume double-billing risk: durable
slot/stage intent precedes dispatch; resumes reuse request identity and an
existing response; uncertain reservations are not retried. The new freeze passed
**64 Python + 9 Node = 73** Linux offline checks and a separate three-clean-call
instrumentation pilot. Fixtures, payloads, main treatments and scorer were not
changed after pilot inspection. Both pilots are excluded from main metrics.

Total **282 attempts**: nine original pilot, three new pilot, 270 main, no
continuations or retries. This stayed below the combined ceiling of 372. The
new relay ledger has 273 reservations/completions; the separately preserved
original ledger has nine/nine. A Linux auditor passed **5,490 checks** covering
full answer hashes, models, fixed facts/requests, actual transcripts, durable
request IDs, queues and ledger agreement. This audits local accounting, not
provider-internal behavior.

- [Frozen scorer output](../evidence/launchgate-selection-2026-10-25/linux-run-02/collection-04/out/main/analysis.json).
- [Full answers and hook events](../evidence/launchgate-selection-2026-10-25/linux-run-02/collection-04/out/main/runs.jsonl).
- [Final audit](../evidence/launchgate-selection-2026-10-25/linux-run-02/collection-04/out/main/audit.json).
- [All 848 downloaded output hashes verified](../evidence/launchgate-selection-2026-10-25/linux-run-02/collection-04/verification.json).
- [Orchestrator](../evidence/launchgate-selection-2026-10-25/run_linux.py) and
  [auditor](../evidence/launchgate-selection-2026-10-25/audit_results.py).

Main `runs.jsonl` SHA-256:
`0a93b8f2899fe2878b7edee2cd4105689fc9ceed125a12afb34bf289d0a8f1f2`.
Final 848-output archive SHA-256:
`22f4e8471866975b76d5566e4f929c598069db11e87fbf3b866ef58a3dccb92b`.

Both owned temporary Linux roots were removed after saved input/output hash
verification: [original pilot receipt](../evidence/launchgate-selection-2026-10-25/linux-run/cleanup.json),
[main study receipt](../evidence/launchgate-selection-2026-10-25/linux-run-02/cleanup.json).
Existing services, key files and Docker images were not modified.

The practical change is keeping full answers, explicit choices, task-constraint
correctness and literal mentions as distinct evidence. Measuring a defense gain
will require a separately frozen harder attack set that actually moves the
baseline, held-out templates and external review. No extra model calls were
made to search for a convenient positive result. These materials remain local;
no article or public reply was published.
