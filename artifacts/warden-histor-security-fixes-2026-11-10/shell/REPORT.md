# Research retry helper fixes — 2026-11-10

Changed only `warden/scripts/scanner-comparison/hosts/retry_set.sh` and
`retry_cross.sh`. Both historical host scripts remain self-contained and still
accept `SET CPUS`. Their existing Python dependency now performs argument
handling and launches subprocesses with argument lists.

The old helpers joined local SET and retry-JSON scanner keys into a command
string passed to `sh -c`. A bounded fake-Docker regression reproduced actual
marker-file execution in **both original scripts** using a malicious top-level
JSON scanner key. The original files are retained as `.before.sh` evidence.
No real Docker command or remote host was used.

The fixed helpers run one container with the same gVisor/network/resource
controls. They deliver a fixed Python dispatcher on stdin (`docker run -i ...
python3 -`) and pass scanner argument arrays as JSON data. No generated shell
source or `sh -c` remains. Scanner order and per-tool worker values are retained;
all scanners still run even if an earlier one fails, and the final scanner's
status becomes the Docker status.

Before moving first-pass evidence or launching a container, both helpers check:

- SET is one bounded path component containing letters, digits, `.`, `_` or `-`;
  names such as `mcptox-decorated.v2_1` and the historical `packages-a` remain valid.
- Retry JSON is an object whose scanner keys are exactly from `mcp-audit`,
  `mcp-shield`, `truecopy`, `mcpsentry`; server-list values are lists of single
  file names, with no path separators, NUL, empty name, `.` or `..`. Duplicate JSON
  object keys are rejected.
- CPUS/cpus.cap are positive decimal values; cpu.shares is within Docker's
  supported integer range. These are separate arguments, never split options.

The cross-host helper parses the four known numeric `workers.conf` assignments
as data instead of sourcing shell code. Its configuration subset is fully
validated before creating output, starting the watchdog or calling Docker.

The local helper still moves originals to `raw-firstpass/SET/<scanner>/`. The
cross helper still keeps the other host's originals and writes only selected
server configs into `raw/SET-retry/`. A behavior improvement is intentional:
helpers now return Docker/final-scanner failure instead of masking it with the
final successful `echo`. The done log records that status.

## Validation

Run from the workspace root:

```sh
.venv-quality/bin/python artifacts/warden-histor-security-fixes-2026-11-10/shell/check_retry_helpers.py
```

**29 passed bounded cases** (`results.json`, `regressions.log`): two original
marker-execution reproductions; shell syntax, command substitution and traversal
in SET; malicious/unknown retry scanner keys; malformed server lists and path
traversal; CPU/CPU-share injection; executable/invalid worker config; normal
four-scanner dispatch with historical worker overrides and evidence retention;
nonzero final-scanner status propagation; and operator cap/share/worker changes
during readiness waiting. The queued-config regression initially failed on the
first implementation (retained in `queued-initial.log`); the corrected helper
reads those operator controls after readiness, preserving the original timing. The fake Docker executes the
actual fixed dispatcher while recording scanner calls rather than launching
those scanners. Only the fixed production workspace path is substituted in a
temporary copy of each helper.

`sh -n` passed for both scripts; their embedded Python compiled, and scoped
`git diff --check` passed. A local targeted Vulnetix 4.24.6 `VNX-BASH-001` recheck returned **exit 0,
no findings** on the two changed helpers. It is recorded separately in
`vulnetix-shell-run.json` and `vulnetix-shell.log`; it does not claim all-rule
SAST coverage or alter the original broad scan evidence.

No production research jobs were started, no remote files were changed and
nothing was uploaded or published. Adjacent historical `run_set.sh` still uses
its original trusted-operator command-string dispatch; it was outside this
focused change and is not claimed fixed here.
