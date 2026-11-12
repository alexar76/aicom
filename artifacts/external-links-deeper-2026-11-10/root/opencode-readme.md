# opencode-integrity

[![CI](https://github.com/Hamza-Abili/opencode-integrity/actions/workflows/ci.yml/badge.svg)](https://github.com/Hamza-Abili/opencode-integrity/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/%40hamzaabili%2Fopencode-integrity)](https://www.npmjs.com/package/@hamzaabili/opencode-integrity)
[![npm downloads](https://img.shields.io/npm/dt/%40hamzaabili%2Fopencode-integrity)](https://www.npmjs.com/package/@hamzaabili/opencode-integrity)
[![GitHub stars](https://img.shields.io/github/stars/Hamza-Abili/opencode-integrity?style=social)](https://github.com/Hamza-Abili/opencode-integrity/stargazers)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**The tool you approved is not the tool you are running.**

`opencode-integrity` locks what OpenCode can load — plugin content, MCP tool
descriptions and schemas, and skill files — and detects when any of them
change. No proxy, no config rewrite, no cloud. Local, zero runtime
dependencies, OpenCode V1 and V2.

```text
audit  → see plugins, MCP tools and skills with capabilities and hashes
lock   → write opencode.lock.json (commit it)
check  → fail CI when anything drifts
runtime→ warn or deny changed MCP tools and skills during a session
```

## Why

An MCP tool description is not inert data: it is instructions the model reads.
A server can serve one toolset today and a different one tomorrow. Skills are
Markdown files that can be edited after review. Plugins are npm/Git code that
runs in the OpenCode server with the agent's privileges. OpenCode policies
(`plugin.use`, `mcp.use`, `skill.use`) only match names; they do not verify
content.

Existing MCP scanners are on-demand CLIs, and the strongest pinning tool
(`mcp-pin`) is a stdio proxy for other clients. This is the OpenCode-native
layer: it sees what OpenCode actually loaded, including remote MCP servers and
Code Mode, and covers plugins and skills too.

## Install (OpenCode V2)

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": [
    {
      "package": "@hamzaabili/opencode-integrity",
      "options": { "mode": "warn" }
    }
  ]
}
```

## Install (OpenCode V1)

```jsonc
{
  "plugin": [
    ["@hamzaabili/opencode-integrity", { "mode": "warn" }]
  ]
}
```

V1 can hash project plugins, MCP configuration and skills, and in `enforce`
mode it blocks changed MCP configuration and skills. The V1 API does not expose
live MCP tool descriptors, so tool-level drift is V2-only.

## Quick start

```sh
# 1. See what is loaded, without a lockfile
npx @hamzaabili/opencode-integrity audit

# 2. Inside OpenCode, capture the live MCP tool definitions
/integrity lock

# 3. Commit the lockfile
git add opencode.lock.json

# 4. In CI
npx @hamzaabili/opencode-integrity check --format sarif
```

`/integrity lock` is important: only the running OpenCode instance can see the
tool descriptions and schemas returned by MCP servers (local and remote, with
or without Code Mode). The CLI locks project plugins, MCP configuration and
skills; it preserves runtime tool hashes when the server configuration did not
change.

## What is hashed

| Asset | Fields |
| --- | --- |
| Plugin | package.json, every package file (capped at 5000 files / 50 MiB), version, source, detected capabilities |
| MCP server | transport, command, URL, cwd, environment/header **names** and redacted values, codemode |
| MCP tool | name, description, input/output schema, annotations, suspicious-instruction scan |
| Skill | full `SKILL.md` content, size, suspicious-instruction scan |

Secret-looking environment values and headers (`TOKEN`, `KEY`, `SECRET`,
`PASSWORD`, `AUTHORIZATION`, `COOKIE`, `CREDENTIAL`) are replaced with
`[redacted]` before hashing, so rotating a token does not create drift. Their
names still change the hash.

## Runtime modes

| Mode | Behavior |
| --- | --- |
| `warn` (default) | Inject a drift report into the session and log it; nothing is blocked. |
| `enforce` | Disable MCP servers whose configuration changed, remove changed skills, and deny changed MCP tools and skills before execution. |

`enforce` is fail-closed for **asset drift**, not a sandbox. A plugin that is
already loaded cannot be unloaded by a plugin hook; review plugin changes with
the lock diff and restart OpenCode. MCP and skill transforms are applied at
startup, so after `/integrity lock` in an existing session, reload to re-enable
previously quarantined assets.

## CLI

```sh
npx @hamzaabili/opencode-integrity audit [--json] [--strict]
npx @hamzaabili/opencode-integrity lock
npx @hamzaabili/opencode-integrity check [--format text|json|sarif]
npx @hamzaabili/opencode-integrity diff
npx @hamzaabili/opencode-integrity policy [--deny-unlisted] [--include plugins,mcp,skills]
```

- `check` exits `1` on drift or when no lockfile exists.
- CLI `check` verifies project files/configuration; live MCP tool descriptors are
  only verifiable by the running V2 adapter. Use `/integrity check` or the
  `integrity_status` tool inside OpenCode for the full check.
- `audit --strict` exits `1` on drift or an unlocked project.
- `policy` emits native OpenCode `mcp.use`, `skill.use` and `plugin.use`
  statements from the lockfile. Policies default to allow, so allow statements
  alone restrict nothing. `--deny-unlisted` prepends `deny *` for each included
  class, producing a real allowlist; review it because it also blocks global or
  newly added assets. A `plugin.use` deny keeps
  `@hamzaabili/opencode-integrity` allowed by package name so the runtime plugin
  is not blocked by its own policy; an absolute-path install needs an explicit
  allow. Local `./`/`../` plugin targets are resolved against the
  config file directory, like OpenCode does. OpenCode's built-in `opencode` and
  `report` skills are not in the lock, so `skill.use deny *` also hides them;
  add explicit allows if you need them. `--include` applies to `policy` only.
  It is not a hash check; pair it with `check`/runtime enforcement.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `lockfile` | `<project>/opencode.lock.json` | Lockfile path. |
| `mode` | `"warn"` | `warn` or `enforce`. |
| `include` | `["plugins","mcp","skills"]` | Asset classes to inspect. |
| `ignore` | `[]` | Asset ids or globs to ignore, e.g. `mcp:local-dev`, `skill:experimental-*`. |
| `includeGlobal` | `false` | Include global MCP config and, at runtime, global plugins/skills. Project-scoped assets are the default so a committed lock stays portable. |
| `trace` | unset | Reserved for redacted diagnostics. |

## Capabilities and suspicious content

`audit` reports heuristic capabilities found in plugin entry code (`network`,
`filesystem`, `process`, `environment`, `dynamic-code`) and flags zero-width
characters, bidi controls, HTML comments, “ignore previous instructions”,
“do not tell”, and exfiltration language in tool descriptions and skills.

These are **signals**, not proof. They are deliberately deterministic and
offline; a clean scan does not make a plugin safe.

## Differences from other tools

| | opencode-integrity | mcp-pin | mcp-scan / Cisco | Socket/npm audit |
| --- | --- | --- | --- | --- |
| OpenCode-native runtime | yes | no (proxy) | no (on-demand) | no |
| MCP tool descriptor pinning | yes | yes (stdio only) | scan only | no |
| Remote MCP | yes | no | yes | no |
| Plugins and skills | yes | no | no | packages only |
| Runtime deny/quarantine | yes | proxy block | no | no |
| Policy/SARIF output | yes | no | partial | no |
| Zero runtime deps | yes | yes | varies | varies |

## Security model

The lockfile is a review artifact, not a signature. It catches changes between
the version you reviewed and the version that runs; it does not prove that the
reviewed version was safe. Use it with code review, OpenCode permissions,
`opencode-sandbox`, and least-privilege MCP servers.

Read [SECURITY.md](SECURITY.md) before enabling `enforce` on a shared machine.

## Support

- Bugs: [open an issue](https://github.com/Hamza-Abili/opencode-integrity/issues/new/choose)
  with `audit --json` and the relevant lock diff (redact secrets).
- Questions: [Discussions](https://github.com/Hamza-Abili/opencode-integrity/discussions).
- Security: [private advisory](https://github.com/Hamza-Abili/opencode-integrity/security/advisories/new),
  never a public issue.

## Development

```sh
bun install
bun run ci        # biome + tsc + tests + build + smoke
```

MIT. Zero runtime dependencies.
