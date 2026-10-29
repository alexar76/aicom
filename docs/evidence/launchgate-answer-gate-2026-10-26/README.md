# Launch Gate: bounded correction and an owned output boundary

26 October 2026. Implementation and offline verification; no new model run or publication.

The current change adds an opt-in WARDEN host SDK. It does not rewrite the historical free-prose benchmark into a successful runtime result. See the five-language product contract in `warden/docs/flow-guard-answer-gate*.md`.

- `protocol.md`: scope, limits and regression requirements frozen before server verification.
- `run-01/`: retained failed verification; duplicate-key regression had a test syntax error. The other 23 suites passed.
- `run-02/`: retained failed verification; the analogous escaped-duplicate-key test also had an extra parenthesis. The other 23 suites passed.
- `run-03/`: corrected test sources; new suites run before compatibility suites. All attempts make zero model calls.
- `run_linux.py`, `run_server.py`: minimal hashed payload, own temporary root, nonroot Linux containers; network only for dev-dependency installation. Output archive and every member are verified locally before remote deletion. Failed collection retains remote evidence for `--recover`.
- `prepare_inputs.py`, `historical-inputs.json`, `replay.mjs`: project only explicitly reviewed eligible lists from all 384 retained historical answers into the new structured schema. This is post-hoc annotation encoding, not automated prose extraction. Unsupported prose must remain unknown, all 50 known false-set projections must deny. No historical model output is changed.
- `stubborn-transcript.json`: complete request/provider response for a representative stubborn-context answer, with original request and answer hashes. It retains both the false C eligibility/$129 sentence and the correct C exclusion/$190 sentence. Observable contradiction; hidden reasoning remains unknown. It is one inspected example, not proof that every unsuccessful case has this mechanism.
- `finish.py`: verify receipts/input hashes, synchronize only the validated Linux build, copy local product evidence and produce `results.json` / `build-sync.json`.

Mechanism tested: initial proposal → price contradiction → first correction → distance contradiction → bounded second correction → verified output or withholding. A mandatory host-owned notice accompanies the sole final frame. No intermediate candidate is sent to the final sink. Callback failure, timeout, cancellation and uncertain delivery do not trigger automatic retry. The callback must honor cancellation for its own outstanding work; gate ownership is per instance.

The structured SDK omits arbitrary model prose from deliverable output. It relies on correct host rules, normalized units, a conditional source snapshot and an application that buffers and displays the gate's output. Our actual child-process stdio integration is tested; third-party native GUI rendering and the new loop's live-model improvement are not measured here. No inference about model awareness, generalization or broader security follows.

Preparation, coding and semantic review used AI assistance. No independent blinded review is claimed.
