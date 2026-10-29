# Exact Oracle Gateway wheel startup replay

Fresh local replay on 27 October 2026 confirms the startup failure in the unmodified official
`aimarket-oracle-gateway` 0.3.1 wheel and successful MCP startup in the unmodified 0.3.2 wheel.
The original HISTOR evidence was not changed.

| Exact wheel | Process exit | Initialize | Complete tools list |
|---|---|---|---|
| 0.3.1 | `1` | No response; module import fails | Unavailable, retained as `null` |
| 0.3.2 | `0` after normal input closure | Protocol `2025-06-18`, server version `0.3.2` | 36 unique tools |

Both executions used the same existing CPython 3.12.13 environment, MCP SDK 1.30.0, HTTPX and
Pydantic versions recorded in [runtime.json](runtime.json). The environment was not modified.
SHA-256 values of both wheels were checked against the prior verified artifact index before
unpacking; extracted package `Name` and `Version` metadata were checked independently.

## Failure and successful startup

The old [stderr](0.3.1-stderr.log) shows `NameError: name 'ValuesList' is not defined` while
FastMCP evaluates the string annotations of `aggregate_values`. The alias is local to its
registrar, while postponed annotations are evaluated against the function's module globals.
FastMCP turns that error into `InvalidSignature`, so the process exits before answering the
first `initialize` request. No old tool list is fabricated.

The new [wire transcript](0.3.2-wire.json) contains a real initialize response and the complete
paginated `tools/list` result. Checks cover `aggregate_values`, `list_oracle_capabilities`
and representative Sortes, Gauss, Aestus, Betti, Kantor and Fourier tools. `aggregate_values`
still declares a nonempty numeric array: its `values` schema has `type: array` and `minItems: 1`.
All 36 tool definitions retain object input schemas. This verifies startup and declarations;
it does not invoke any oracle operation.

## Files

- [Verification and hashes](verification.json).
- [0.3.1 execution receipt](0.3.1-result.json), [wire](0.3.1-wire.json),
  [stdout](0.3.1-stdout.log), [stderr](0.3.1-stderr.log).
- [0.3.2 execution receipt](0.3.2-result.json), [wire](0.3.2-wire.json),
  [stdout](0.3.2-stdout.log), [stderr](0.3.2-stderr.log).
- [Replay implementation](reproduce.py) and [guarded launcher](guarded_launch.py).

Each receipt records the actual argv, package source hashes, exact wheel hash, runtime profile,
timestamps and process status. `verification.json` hashes the scripts and saved results. The
scripts were finalized before these captures; all recorded sources remain unchanged.

## Reproduction scope

The reader sends only `initialize`, `notifications/initialized` and `tools/list`. Child
processes receive a PATH-only environment with no credentials, Python `-I -B`, an explicit
verified package overlay and a separate working directory. Python audit hooks deny DNS,
socket connections and child-process execution inside the server. This is an audit guard,
not an OS sandbox.

No network, package installation, `tools/call`, payment, deployment or GitHub publication
occurred. The reader is bounded by a 20-second observation deadline, size/page caps and
process cleanup. Graceful input closure let 0.3.2 exit normally.

The replay script deliberately refuses to replace existing receipts. To collect a fresh run,
copy `reproduce.py` and `guarded_launch.py` into a new sibling directory under this evidence
folder and invoke the copied script with the existing HISTOR Python environment. It reuses
the cached verified wheel files and release runtime; it does not download or install anything.
