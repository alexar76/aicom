# Prospective fixture holdout after product freeze

26 October 2026. One completed model run, unchanged frozen WARDEN 0.22.0 build. Same AI-assisted author wrote generator/implementation; **not independently authored or blinded**. No GitHub/npm publication or comment posting.

Product source/compiled hashes, commit, protocol and generator were recorded in `freeze.json` at 12:31:23 UTC before drawing the seed or creating fixtures. Exactly one saved random seed generated 24 fixtures under six synthetic domain labels. All use the existing finite numeric/boolean contract: maximum, minimum, numeric equality, boolean equality, plus min/max ranking. Six fixtures have an optimal tie. Record and rule order are shuffled; every ordinary catalog retains two eligible records and four distinct attractive single-rule traps. These are new parameter combinations, not new constraint-language support or a real-world domain corpus.

## Separate results

| Population | First proposal / repair | Final task outcome |
|---|---|---|
| Natural clean, 48 | 47 valid; 1 ranking error corrected after one repair | 48 delivered, 0 withheld |
| Natural injected, 48 | 42 valid; 6 ranking errors: 3 fixed after one repair, 1 after two, 2 unresolved | 46 delivered, 2 withheld |
| Seeded ineligible alternative, 24 | 24 fixed after one repair | 24 delivered |
| Seeded omitted eligible record, 12 | 11 fixed after one repair; 1 developed persistent ranking error | 11 delivered, 1 withheld |
| Seeded suboptimal selection, 12 | 9 fixed after one repair, 1 after two, 2 unresolved | 10 delivered, 2 withheld |
| Deterministic valid seeds, 4 | No model call | 4 delivered |
| Deterministic missing facts, 4 | No model call | 4 withheld as incomplete |
| Deterministic no eligible records, 4 | No model call | 4 withheld |

Natural first validity **89/96**, final **94/96**. All seven first errors were ranking errors, not malformed JSON or admitted ineligible records. Five were corrected, two withheld. Controlled repair **45/48** with three withheld; seeded errors are not spontaneous failures. Second repair was triggered in seven live trajectories: two then passed, five were withheld. These are observed transitions, without a no-review control to identify net causal benefit. No new hard-constraint trap substitution; one omitted-set error changed into a ranking error.

Independent arithmetic audit of all final frames finds **zero invalid deliveries**. There are **143 delivered frames, 13 withholding frames**, all 156 with the appropriate host notice. Eight refusals are deterministic controls and five follow live model failure. Withholding is not scored as a solved task. Every ordinary catalog (144/144) retains all six records, four rules and all four trap types. Full scores from the prior known set are not generalized here.

All frozen predictions met: >=84/96 natural first validity (89), >=46/48 clean final delivery (48), >=40/48 controlled final delivery (45). No API errors, transport retries, dropped attempts, re-draw or repeated study.

## Cost, custody and collection recovery

158 fresh calls, 12:35:28–12:38:59 UTC (15:35–15:38 Moscow), off-peak. Usage: 182,656 input tokens, including 62,461 cached, and 17,863 output. Published-tariff usage calculation **USD .028934433**; conservative peak ledger **USD .057868866**, below the USD .15 ceiling. No invoice/account-balance delta queried; existing server capacity.

Before API: 11 Node harness tests, 28 relay/budget/collection tests and 180 request preflights passed in a keyless networkless Linux container. Only the tested host relay reached the fixed official endpoint. All requests and outputs are retained.

The first collection command had a syntax error from a misplaced string replacement in the packager. The model run had finished successfully and the sole remote copy was retained. `collection-amendment.json` records the collection-only repair before recovery; `--recover` dispatched **zero** calls and collected all **329 verified output hashes** before remote cleanup. The original payload remains in `run-01/inputs.tar.gz`; current collector additionally syntax-checks its embedded program. No model evidence was lost or regenerated.

`analyze.py` checks frozen product bytes from the immutable payload/commit, binds requests/responses, independently recalculates truth from original records and verifies emitted values without invoking the runtime validator. Every candidate, including errors, is in `run-01/out/trajectories.jsonl` and the verified archive. `analysis.json`, `output-audit.json` and `artifact-audit.json` contain the results/receipts.

## Separate post-hoc code improvement

The five unresolved live trajectories all ended in `not-optimal`. The old feedback named this code but supplied no selected-versus-best numeric witness. A separate local change adds bounded ranking facts and missing-eligible-reference evidence; see `../launchgate-ranking-feedback-2026-10-26/`. It is outside the frozen run and its model efficacy is unmeasured. Original outcomes are not replaced by replay. No new model experiment is authorized by the replay itself.

Limits: synthetic fixtures within the supported grammar, same author, unblinded, two repeated observations per case/condition, no independent deployment sample, no source-truth/unsupported-unit/arbitrary-prose guarantee. Source-instruction notices use known synthetic arm labels, not a validated detector. Captured frames do not prove native GUI display. Preparation and audit used AI assistance.
