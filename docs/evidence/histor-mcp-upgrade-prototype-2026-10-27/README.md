# HISTOR modern MCP and local upgrade brief verification

Date: 2026-10-27. All implementation changes remain local. No publication, deployment, production
database, real payment or GitHub write was used.

## Result

- Remote HTTP observations, sandbox stdio observations, the `tool-cost` stdio client and
  `histor mcp` support the implemented modern MCP revision `2026-07-28` while preserving legacy
  initialization. Malformed negotiation, recognized modern errors, interactive results and
  invalid pagination cannot silently become a successful legacy or empty observation.
- API history and package dataset observations retain `protocolVersion`; equal definitions
  under different protocols do not collapse into one timeline row.
- Sandbox observer 5 and defaults are coordinated across Python settings, example env and
  Compose. Completed successes from observers 3 and 4 remain valid; failed captures can retry.
- `histor upgrade-brief` compares a user's local before/after observations and selected tools,
  maps changes to explicit workflows and produces a human checklist and JSON evidence. It runs
  offline. The separate `capture` subcommand makes explicit read-only HTTP observations into
  new files. Local captures are unsigned.

## Verification

The complete non-integration HISTOR suite passed **828 tests**, with **216 skips** and
**12 integration tests deselected**. The skips include unset PostgreSQL fixtures and optional
dependencies. One existing Starlette/httpx deprecation warning remains. See [pytest.log](pytest.log)
and [JUnit](pytest.xml). The first sandboxed attempt could not bind five local TLS/trap fixtures;
the successful run was repeated with permission for temporary loopback sockets.

After final report rendering and capture refinements, **61 focused tests passed**, including
the two added transport-to-report acceptance cases. These overlap the full suite and their
counts must not be added together. See [focused log](end-to-end.log) and [JUnit](end-to-end.xml).

The two end-to-end cases exercise:

1. An actual temporary loopback HTTP server that accepts only modern requests. Two captures
   record a changed required field; the personal report identifies the affected weekly workflow
   and requests a retest. The request trace contains only `server/discover` and `tools/list`.
2. The real `tool-cost` client connected over process pipes to the real `histor mcp` process,
   using a temporary local data directory. Modern discovery succeeds without `initialize` and
   all three HISTOR tools are listed.

Ruff passes across `histor`, `tests` and `sandbox`; `git diff --check` passes. Tests do not
execute third-party packages or reach public endpoints. Public interoperability at arbitrary
auth scopes and production rollout remain separate work.

## Local prototype

The [input bundle](https://github.com/alexar76/histor/blob/main/examples/upgrade-brief/README.md) is fully synthetic. Its
generated [report](demo-report.md) and [JSON](demo-report.json) demonstrate changed definitions,
changed protocol context and failed-observation uncertainty. They are not customer or live
server observations.

From the `histor/` directory:

```bash
.venv/bin/python -m histor upgrade-brief \
  --watchlist examples/upgrade-brief/watchlist.json \
  --out-dir ../output/histor-upgrade-brief-demo

.venv/bin/python -m pytest -m 'not integration' -o addopts='' -q
.venv/bin/python -m pytest tests/test_upgrade_end_to_end.py -o addopts='' -q
.venv/bin/python -m ruff check histor tests sandbox
```

The socket-based checks require an environment that permits temporary local listeners.
[Prototype guide](https://github.com/alexar76/histor/blob/main/docs/upgrade-brief.ru.md) ·
[compatibility details](https://github.com/alexar76/histor/blob/main/docs/mcp-compatibility.md).
