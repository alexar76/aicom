# Tied choices and remaining selection influence

25 October 2026. [Detailed Russian report](launchgate-tie-selection-2026-10-25.ru.md).

The tie experiment produced **432 admissible choices**, but also a clear
target-selection shift. The unguarded target rate rose from **28/48 clean to
48/48 injected**. With the published warning it rose from **25/48 to44/48**;
with warning plus Stop, **29/48 to45/48**. The added guard effect remains
uncertain after accounting for these different clean baselines.

| Profile | Clean target | Benign target | Injected target | Admissible total |
| --- | ---: | ---: | ---: | ---: |
| none | 28/48 | 25/48 | 48/48 | 144/144 |
| note | 25/48 | 25/48 | 44/48 | 144/144 |
| note_stop | 29/48 | 25/48 | 45/48 | 144/144 |

All nine cells have48/48 parseable selections; no API errors, unknown, missing,
duplicate, unscheduled or generation-length-truncated answers. Target selection
under a tie **is not itself an error or security failure**. Both legitimate
optima are declared in `acceptable_ids`; the old single `correct_id` is only
a compatibility field, not the sole winner.

## Design

Six synthetic cases, eight repetitions, three notes and three treatments.
Each has two equally eligible lowest-price hotels, different unrequested
amenities, and two ineligible decoys. The user explicitly permits either tied
option. Targets are fixed before responses. Record order rotates over four
positions twice; matched case/repetition groups retain identical ordered facts
and user requests across all notes/treatments. These are six deliberately
selected cases, not representative random tasks or broad attack coverage.

Fixed attack notes spoof developer roles, a later customer preference, cached
assistant reasoning, a multilingual preference, a prior approval, or a private
evaluation rubric. They remain tool-result strings, not real API-role changes.
The note omits the target name/ID, while the unchanged records include both.
Benign metadata is character-length-matched, not lexically equivalent. Keep
both clean and benign comparisons rather than picking a reference after results.

Same API model `deepseek-flash` and exact published WARDEN0.21.0 as the prior
unique-choice study. Temperature0.3, max700 tokens, thinkingdisabled, independent
conversations, schedule seed20261025. No shared model-generation seed or
immutable weight identity is claimed. Linux factory-vps; actual hooks in Docker
runc without network, separate host API relay. Warning appended inside the
tool-role message; a requested Stop would use a user-role continuation. This
controlled bridge is not a native-client or full-enforcement evaluation.

## Effect and uncertainty

The clean-adjusted target shifts are **+41.7pp none**, **+39.6pp note** and
**+33.3pp note_stop**. Baseline-adjusted attenuation versus none is:

- note: **+2.1pp**, fixture-cluster95% interval **[−16.7,+33.3]pp**;
- note_stop: **+8.3pp**, interval **[−4.2,+20.8]pp**.

Both intervals includezero. Using benign instead gives+8.3pp [0,+20.8] and
+6.3pp [−4.2,+20.8], respectively; no reference establishes a clear robust gain.
The preregistered common-untreated-baseline distance reduction is+8.3pp for
note [0,+25.0], +6.3pp for note_stop [0,+18.8]. Mean absolute guard-induced
clean shifts are14.6pp and6.3pp: removing its own delta cannot alone establish
restoration to the unguarded baseline.

Bootstrap resamples six whole fixture clusters, retaining all matched repeated
conditions (2,000draws, seed20261025). All48four-condition pairs are complete.
Small purposive clusters, empirical absolute-distance noise and coarse
intervals prevent population or general safety claims. Three unguarded clean
cases still chose target8/8; most new headroom lies in cases2,4,6. Guarded
injected reductions occur in case6, not uniformly across payload families.

Separate real-user preference controls explicitly request the previously
targeted amenity. The model follows that legitimate preference **18/18**, six
per profile. Controls do not enter main metrics. Stop requested **zero**
follow-ups in144main checks and6control checks. Thus44versus45 injected choices
is not an observed correction caused by Stop; they are separate generations.

Every one of the137injected target selections names that hotel in the final
answer. This study therefore **does not demonstrate a target choice with no
final target-name mention**. Only the attack note omitted the name/ID. Choices
and mentions remain distinct recorded columns. Full independent/blinded
semantic adjudication of every reason was not performed; explicit-ID utility
is not a claim that every explanation fact is flawless.

## WARDEN code and evidence

The new local `offline evaluator` (`warden/scripts/selection-probe/README.md`, repository only)
supports admissible sets, separate mentions/choices, missing outcomes,
own-baseline and common-reference effects, and guard-induced clean shifts.
Tests cover the counterexample of a guard with constant preference bias. Its
bytes match the frozen study scorer. **Runtime blocking was not tightened**:
forbidding an admissible target merely to lower its rate would not solve
preference provenance. Published0.21.0 and production are unchanged.

The frozen sources passed **70Python+9Node=79** Linux checks. A post-run Linux
auditor passed **9,098checks**. **453 API attempts** total:3smoke+18controls+
432main, no follow-ups/retries, independent cap620. Prior282attempts remain
separate. No real bookings, seller charges, public comments or GitHub writes.
Key files stayed server-local. Research, implementation and initial
interpretation used AI assistance, not independent/blinded human adjudication.

The same frozen run was resumed in two segments to remain below the adapter's
256-session process limit. The first297rows/207guarded sessions were preserved
as the final file's exact byte prefix; the same command, request IDs and ledger
were reused. One already-queued response was recovered without a second API
call. No samples or payloads changed. Both the used tie root and the earlier
zero-call preparatory root were removed after evidence verification.

- [Frozen protocol](../evidence/launchgate-tie-selection-2026-10-25/protocol.md).
- [Final metrics](../evidence/launchgate-tie-selection-2026-10-25/linux-run/collection-06/out/main/analysis.json).
- [Full answers and actual hook inputs](../evidence/launchgate-tie-selection-2026-10-25/linux-run/collection-06/out/main/runs.jsonl).
- [Accounting audit](../evidence/launchgate-tie-selection-2026-10-25/linux-run/collection-06/out/main/audit.json).
- [1,403 verified outputs](../evidence/launchgate-tie-selection-2026-10-25/linux-run/collection-06/verification.json).
- [Cleanup receipt](../evidence/launchgate-tie-selection-2026-10-25/linux-run/cleanup.json).

The historical AgentDojo18/20 and prior270/270unique-choice result are unchanged.
No public article/reply was published by this work.
