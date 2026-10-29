# Final matched comparison of ranking feedback

26 October 2026. User requested completion of the remaining live validation and a reply. This is the last model experiment in this series. No added fixtures, adaptive extension or further model rerun. New API ceiling USD .08, added to the prior holdout's conservative USD .057868866 = USD .137868866, below the stated combined USD .15 limit. Max 120 dispatched calls; no retries/fallbacks or budget refill.

## Fixed population and scope

Select **all five** live trajectories withheld in the completed prospective fixture experiment: two naturally generated and three controlled-start trajectories. No successful or unsuccessful case is selected based on the new feedback's outcomes. Preserve their exact final invalid answers and the exact recorded request histories that produced them. All five ended in `not-optimal`; they span four distinct parameter fixtures. This is a selected known-failure cohort, not a new holdout or deployment sample.

For each context, generate eight matched blocks with two arms: the prior SDK's verdict-only feedback, and the changed SDK's explicit selected-versus-best witness. **40 failure opportunities per arm**, 80 calls total. Both use the same retained history and invalid answer; only the final review message differs. Record values were already available in the catalog in both arms. The treatment makes the comparison and record binding explicit; it does not establish an information deficit or isolate the effect of each phrase.

Create one explicitly synthetic valid control answer per retained context using its known complete eligible set and an admissible optimum. Four blocks per context, two nominal arms: **20 valid-control opportunities per arm**, 40 calls total. Both SDKs produce exactly the same verified feedback for these controls. They measure preservation under continued sampling, not a treatment contrast. Do not present synthetic valid controls as spontaneous model successes.

## Single fresh continuation

Append the fixed invalid (or controlled valid) assistant answer and the arm's feedback to the complete original final-request body. Freeze both compiled SDK versions, source history hashes, input answers, messages and schedule before API calls. Use the current gate only to evaluate/buffer one new continuation (`maxCorrections: 0`) and emit checked data or withholding. This is a separate research continuation from a previously held answer, **not** a third production repair; production retains its two-correction ceiling.

Deepseek-flash, temperature .3, thinking disabled, JSON object mode, max_tokens 700, no tools/actions. Accept reported model deepseek-flash or deepseek-v4.1-flash-1017; stop on another model, budget refusal or three consecutive API errors. Every request/response, error, decision and final frame is retained. Withholding is not a corrected task answer. No silently edited output.

## Predictions and analysis frozen before calls

Primary predictions: witness corrects >=32/40 failure continuations and improves over the old arm by >=8/40. Control prediction: >=19/20 remain valid in each nominal arm. Report failed predictions and all contexts. Record paired outcomes and per-context rates; five known contexts/four fixtures cannot justify a general statistical or security claim. Keep two natural-origin and three controlled-origin failure subgroups visible. Do not pool these 80 failure calls with the prior holdout or the 40 positive-control calls.

Independently audit final eligible/optimal values against original source records without invoking the runtime validator. Require zero invalid deliveries and the proper host notice on all emitted frames. After this run, close the series with the measured result whether positive or negative; any remaining failure is documented, without inventing an internal-cause explanation or promising another model test.

## Execution and custody

Linux factory-vps. The Node runner has neither network nor key; only the tested host relay reaches the fixed official DeepSeek endpoint. It persists reservations before paid dispatch, holds unknown transport costs and uses conservative peak prices (.30/.006/1.20 USD per million input-miss/input-hit/output tokens, checked 26 October at https://api-docs.deepseek.com/quick_start/pricing/). Actual time-window usage calculation is separate from an unqueried invoice/balance delta. Existing server, no new rental.

Linux-only offline tests/preflights must pass before calls. Verify archive/member hashes locally before deleting server data; recovery collects without API calls. No GitHub/npm write, release or comment posting. Product code remains unchanged. Preparation and audit use AI, unblinded and same-author; no independent human review is claimed. Later documentation supersedes the earlier statement that live efficacy was unmeasured, only for this fixed cohort/comparison.
