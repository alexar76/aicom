# Local WARDEN server_info validation fix

Date: 2026-10-27. Unknown own JSON keys in `server_info` are rejected by the shared status and
approval validator with `McpToolError("server_info may contain only name and version")`.
The message does not copy attacker-controlled field names or values.

The previous handling of omitted/undefined metadata, `null`, `{}`, partial `name`/`version`,
empty strings and the 200-character boundary is preserved. Existing type and length checks,
reviewed hashes, revision compare-and-swap and operator opt-in remain in force.

## Regression coverage

[The new test file](https://github.com/alexar76/warden/blob/main/test/server-info-validation.test.ts) adds 22 cases over the
actual compiled stdio server with isolated temporary pin directories and sanitized child env.
It covers unknown `extra`, JSON own `__proto__` and `constructor`, compatible old inputs,
existing invalid types/lengths and explicitly enabled approvals.

Invalid approval metadata is checked with otherwise valid current review hashes and revision:
it neither creates a first pin nor changes an existing pin's bytes or revision. Positive
controls verify that old calls without metadata and approvals with valid partial metadata work.
No real operator pins are used.

## Verification

- New regression suite: **22 passed**, included in the full-suite count.
- Full WARDEN suite: **1382 passed in 57 files**, zero failures.
- `npm run build` and `npm run typecheck`: passed.
- `git diff --check`: passed.
- The serialized nine advertised MCP definitions have the same SHA-256 before and after;
  this corrects runtime enforcement of the existing schema.

Logs: [build](build.log), [typecheck](typecheck.log), [regressions](regression.log),
[full tests](tests.log), [Vitest JSON](vitest.json).
[Before](before.json), [after](after.json) and [verification with source hashes](verification.json).

Commands from `warden/`:

```bash
npm run build
npm run typecheck
npm test -- test/server-info-validation.test.ts
npm test
```

Some existing full-suite fixtures open temporary loopback HTTP listeners and need a test
environment that permits local sockets. No live service calls, payments, package installation,
publication, GitHub writes or deployment were performed. Package version remains 0.22.1; the
local `dist` build was refreshed. Earlier HISTOR evidence remains unchanged as a pre-fix record.
