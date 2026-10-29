# Completed Linux source-signal and Stop replay

See the [report](../../growth/launchgate-warning-diagnostics-2026-10-25.en.md)
and [reply draft](../../growth/launchgate-warning-reply-2026-10-25.en.md).

The user explicitly authorized this 164-file transfer to their admin-vps.
Build/typecheck and all 711 tests across 20 test files passed; the unchanged
28-case deterministic gate passed. There were zero model calls.

Published 0.21.0 exactly reproduced the original hook behavior on 288 rows.
The candidate produced specific warnings for 96/96 injected rows, versus zero
in the baseline, with zero in 192 clean/benign rows. Its Stop requested 12/48
counterfactual rechecks versus zero, with zero on 96 clean/benign Stop inputs.
Saved answers did not change. No new effectiveness claim follows.

`input-manifest.json` freezes source bytes. `execution.json` records commands,
image, timestamps and exit codes. `results/` retains baseline/candidate rows,
test report and deterministic gate. `output-manifest.json` covers all 266
collected artifacts; `outputs.tar.gz` preserves the same compiled artifacts.
`local-build-sync.json` records synchronization of Linux-generated code after
checking local frozen inputs. `cleanup.json` confirms removal of the owned root.

Only lockfile dependency preparation used network, with lifecycle scripts off.
All runtime checks used runc with network none, not gVisor. No real effect,
production mutation, package publication or public reply occurred.
