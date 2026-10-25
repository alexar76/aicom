# Kevin Hall: default-purchase fake-billing experiment

Completed 2026-10-25 on admin-vps, Linux amd64, Node 22.23.3, Python 3.11.2. Docker runtime **runc**, network none, read-only root, unprivileged uid, no real account or money. The own published WARDEN 0.21.0 tarball was checked against SHA-256 `5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1`. No third-party MCP code ran.

- [Execution and exact commands](execution.json).
- [Five input hashes](input-manifest.json): observer source, own synthetic MCP fixture, mock backend, experiment controller and the own public WARDEN artifact.
- [Results](results/result.json): **26 scenarios × 3 repeats = 78 expected outcomes passed**, plus three paired normalized-message controls. Pass means the experiment reproduced its specified outcome, including the unsafe/default cases; it is not a safety score.
- [Backend self-test](backend-self-test.log): 30 checks passed, including duplicate suppression/restart, invalid requests and concurrent duplicates.
- [Runtime log](linux.log), [475 output hashes](output-manifest.json), [remote verification and cleanup](cleanup.json).
- [Report](../../growth/kevin-fake-billing-2026-10-25.ru.md) and [clean reply](../../growth/kevin-reply-2026-10-25.en.md).

The original observer's `talk` and `canary_args` run unchanged; a recording Session subclass preserves the exchange. In this experiment the observer parameter `traced=True` only enables its tool-call loop. No gVisor trace was collected or claimed. The current observer source hash identifies this test; it is not presented as a frozen reproduction of every historical census input.

## Reproduced blind spot

The optional `mode` has enum `[preview, purchase]` and schema default `purchase`. The handler actually implements purchase when mode is absent. Current HISTOR canary chooses the first enum, `preview`, and records a successful call with no charge. The same server given `{}` performs one charge of **7 mock credits**. The backend ledger is independent of the MCP result: a backend thread in the Python controller owns the durable ledger, while a separate Node MCP process communicates with it over a local Unix socket. The fixture only records non-authoritative acknowledgements.

Compare the first repeat:

- [Current canary](results/cases/histor-current-canary/01/result.json) and its [MCP messages](results/cases/histor-current-canary/01/transcript.json).
- [Empty-argument call](results/cases/empty-default-purchase/01/result.json) and [authoritative charge](results/cases/empty-default-purchase/01/billing.jsonl).
- [Uncharged matched control](results/cases/uncharged-matched-control/01/result.json).

All complete MCP message objects in the matched billed/control runs are equal; direction is preserved and sequence/time metadata is excluded. The ledgers differ. No claim of identical raw socket bytes or latency is made.

Separate controls cover explicit preview/purchase, omitted arguments, invalid mode, hidden schema default, truly required mode, charge followed by error or timeout, readOnlyHint and idempotent retry. Published WARDEN default policy lets the ordinary-looking call through; configured sensitive names refuse it without a supported approval form, on decline, on unchecked accept or with `--ask refuse`. Scripted explicit accept allows one call, and the next scripted decline refuses the next call. A generic tool approval prompt is not a provider-attested price quote. Deliberately billing initialize/list shows that per-tool-call consent does not establish side-effect-free discovery.

These are synthetic counterexamples and controls, not a prevalence estimate for the 12,915-package census, an Apify test, real settlement verification or a study of human awareness. All consent replies were scripted. Production HISTOR/WARDEN behavior was not changed or deployed. AI agents assisted the fixture, controller, execution, analysis and report under the project owner's direction. Nothing was posted.

The scripts record a completed disposable remote run. Do not reuse their historical hardcoded temporary path as a new directory. A new experiment should get fresh evidence/output paths and preserve its own input hashes.
