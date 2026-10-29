# Live structured answer follow-up — 26 October 2026

The unchanged local WARDEN 0.22.0 SDK was exercised with **160 fresh deepseek-flash calls** on Linux factory-vps. No GitHub/npm writes or comment posting.

| Population | Observed result |
|---|---|
| 96 transitions from twelve saved prose contexts to the new catalog/schema | 96 valid first proposals; 0 natural repair opportunities |
| 32 deliberately seeded C price errors | 32 corrected on the first fresh repair |
| 32 deliberately seeded D distance errors | 32 corrected on the first fresh repair |
| All fresh proposals | 0 C/D admissions, duplicate/invalid JSON or extra prose fields |
| Final captured host frames | 160 checked results, 160 independent notices, 0 unverified candidates |

All 32 natural transitions from the four formerly contradicted contexts also passed first time. The controlled seeds are **synthetic starting errors**, not spontaneous new model failures; do not combine their repair rate with natural first-proposal accuracy. No trajectory needed the second correction or live withholding. Those paths retain their earlier deterministic/stdio verification; this run adds no live-model success estimate for them.

The output contract, normalized catalog and instruction changed together. There is no contemporaneous prose control or format-only causal ablation, no independent holdout, and no broad injection-prevention finding. The source's original untrusted instruction remained in the saved history. The model returned a restricted selected reference and complete eligible-reference list; no arbitrary explanation or price field is certified.

## Reproduction and custody

- `protocol.md`, `pricing.json`, `cases.json`, `slots.json`: frozen scope, tariff assumptions, twelve exact saved histories, randomized 160-slot schedule. Predictions >=80/96 natural first-valid and >=48/64 controlled final-valid both met.
- `study.mjs`, `worker.mjs`: actual `createAnswerGate` and a narrow model callback. Natural initial proposals are fresh; controlled initial candidates are deterministic and consume the SDK's initial proposal. At most two real repairs follow a controlled seed. Requests retain the original base history and only the latest failed structured candidate/feedback.
- `run-01/input-manifest.json` and `inputs.tar.gz`: exact 18-file/43-KB payload. The two compiled runtime modules were checked against the prior Linux build hashes. No key in payload/container/outputs.
- `run-01/out/frozen-before-api.json`: exact plan and manifest recorded before calls. `run-01/out/relay/req/` and `resp/`: complete model requests and provider outputs. `trajectories.jsonl`: every candidate, decision, structured catalog and host frame. `usage.jsonl`: fsynced reservation/settlement accounting.
- `run_linux.py`: safe collection. `outputs.tar.gz` and all **333 output hashes** verified before owned remote temporary root deletion. `--recover` never dispatches calls.
- `analyze.py`, `analysis.json`, `output-audit.json`, `artifact-audit.json`: request/response binding, full population accounting, and an independent calculation of eligible/optimal records and emitted fact values against the original fixture. The audit does not invoke the runtime validator. It is AI-assisted and unblinded, not independent human review.

Before paid calls: **9 Node harness tests + 28 relay/budget/collection tests**, and 480 request preflights passed in a keyless network-disabled Linux container. The host-local tested relay alone read the server credential and accessed the fixed official API endpoint. No transport retries, model fallbacks, discarded attempts or repeated study.

## Cost

160 successful requests, zero API errors; model phase 10:46:08–10:49:48 UTC (13:46–13:49 Moscow), entirely off-peak. From provider-reported usage and the [published tariff](https://api-docs.deepseek.com/quick_start/pricing/), cost is **USD 0.027169008** at that time-window rate. Persisted accounting conservatively used peak prices: **USD 0.054338016**, below the **USD 0.15** hard ceiling. A provider invoice/account-balance delta was not queried. Existing server capacity was used; no rental was purchased.

Product report: `warden/docs/flow-guard-structured-model-2026-10-26*.md` in EN/RU/ES/FR/ZH. Historical studies remain unchanged. No runtime code change was needed from these results; no general reliability claim follows from the complete score on this known set.
