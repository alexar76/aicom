# HISTOR records in the Evidence Record Spec (AAIF O&T #37), 2026-11-21

Кратко по-русски: владелец 21.11 «делай валидатор для #37». Две вещи. (1) Независимая реализация лестницы E0–E4 по тексту
спецификации narko4u/evidence-record-spec, прогнанная по их корпусу: 14 из 14 совпали. (2) Настоящее наблюдение HISTOR,
проверенное в журнале со свидетелями и выраженное в их формате: их валидатор принимает обе записи, но ранг выходит E2 или
E4 в зависимости от того, как назвать песочницу. Три расхождения текста и кода — ниже, по-английски, для их репозитория.

Spec: https://github.com/narko4u/evidence-record-spec at `2bd96d6d9ea1020af95ce7ba5f7d49a5d0e7d952` (2026-11-14).
Published validator run with Python 3.14, jsonschema 4.25.1, rfc8785, from a fresh download.

## 1. An independent implementation of the grade floor

`grade_independent.py` is written from `VERIFIABILITY-OVERVIEW.md` (Axes A–C, "What makes a party independent", the
E0–E4 ladder table, the receipt claims) and the README, not from `evidence_grade_rules.py`. Standard library only.
It reaches the rungs differently: a boundary source starts at E2 and only an independent party with a reference to its
own record lifts it to E3, anchor markers to E4; the published code starts boundary sources at E4 and caps them down.

```text
$ python3 grade_independent.py <spec checkout>
OK  e0-declared … OK  e4-anchored              (8 grade-floor cases: rung and decision as expected)
OK  nr-01 … nr-09                               (6 record fixtures rejected; 3 appraisal fixtures not graded)
14/14 graded cases agree with the published expectation
```

## 2. A real HISTOR observation as an evidence record

`histor_evidence_record.py npm:@agentskit/mcp out/` uses public data only. Run on 2026-11-21:

| Check | Result |
|---|---|
| log note signature (Ed25519, vkey `histor.modelmarket.dev/log+ad3ca066`) | valid |
| witness cosignatures (c2sp.org/tlog-cosignature) verified under pinned keys | 5 of the 6 pinned witnesses |
| `tool-set-observation` label `urn:uuid:f1689b8f-…`, leaf 2525357 | RFC 9162 inclusion to the root of tree 3,082,424 |

The observation: HISTOR installed `@agentskit/mcp` 0.6.0 in a gVisor sandbox with no route out on 2026-11-16 21:50:15Z
and recorded the tool list it served. `out/anchor.json` holds the checkpoint note, the label and the proof, so anyone
can redo the three checks without HISTOR's help.

| Record | How the sandbox is named | Published validator | Published rung | Our rung |
|---|---|---|---|---|
| `out/record-as-published.json` | `source: sandbox`, engines `[sandbox]` | valid | **E2** (`no_independent_party`) | E2 |
| `out/record-operator-custody.json` | `source: external_authority`, engines `[external_authority, sandbox]`, provenance = the label | valid | **E4** | E4 |

## 3. Where the text and the code part ways

**(a) Custody by engine type vs by operator.** The overview decides independence by custody: a party is not
independent when "it is operated, owned or paid by the party whose claim is being graded", and the assignment rule asks
whether "a concrete artifact path exists that lets the named witness check it without relying on the enforcement
point's own account". The code fixes custody per engine name: `sandbox` is always SELF. For HISTOR the sandbox is not
the package publisher's: HISTOR runs it, the publisher cannot write to it, and the label is checkable by anyone against a
witnessed log. Under the engine table the same evidence is E2; naming the operator's role makes it E4. The format has no
field for who operates an engine or who produced the record, so a third-party observer has to pick the label. Question:
should custody attach to the operator (for example an `operator` or `witness_scope` per engine), so a sandbox run by an
outside party can be EXTERNAL without being renamed `external_authority`?

**(b) Source cap vs corroboration.** `probes/` holds the HISTOR record with the source changed to `framework` and to
`agent_self_report`, still corroborated by `external_authority` with a reference to that party's record and anchored.
Published code: E1 and E0, with **no gate reported** (the cap comes from the source base, so `grade_floor.py` explains
it as `grade_derived`). Our reading of the ladder table ("E3: an engine in Axis C custody at PEER or EXTERNAL, plus a
provenance reference to that party's own record"): E3 (not E4: the source cannot be anchored). Which is intended? If the
source caps, the explanation should name that cap.

**(c) Anchor markers are booleans.** E4 rests on `timestamped`, `chain_linked` and `verifiable_by`, which record
presence only. HISTOR can hand over the anchor itself: a checkpoint, an inclusion proof and witness cosignatures. Two
questions: is there room for an optional reference to a checkable anchor (as `anchor.json` here), and does a witness
cosignature, which carries the witness's own timestamp, count as "timestamped" (the field description names RFC 3161)?

Related: the spec's `removal-evidence/` vector shows the case only a witness catches (`resealed_pair`). HISTOR's log is a
production instance of that design: every checkpoint is co-signed by independent public witnesses, and a rewrite after a
co-signed head fails the RFC 9162 consistency check against what the witnesses hold.

## Files

- `grade_independent.py`: the independent grade floor; `--record` grades your own records.
- `histor_evidence_record.py`: fetch, verify and export one HISTOR observation (needs `cryptography`).
- `out/`: the anchor and the two records from the 2026-11-21 run. `probes/`: the two source probes of 3(b).
