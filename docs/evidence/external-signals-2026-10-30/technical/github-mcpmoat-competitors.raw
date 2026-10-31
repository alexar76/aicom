# Competitors

This page compares mcpmoat with five tools that overlap with it. It helps us pick ideas to adopt and
ideas to avoid. It answers issue #32 and the risk "Strong competitors" in
[PRD section 13](PRD.md).

Checked on 2026-10-23. Tools change fast. Check the linked source before you rely on a row.

How to read this page:

- Every fact has a link to its source. A fact without a link was removed.
- "Unknown" means we found no source. We did not guess.
- The licence is the one that GitHub and the repository `LICENSE` file report. We state it as a fact
  and do not judge it.
- We read the READMEs and docs of each project. We did not install or run any of these tools. Test
  results in this page are claims by the project, not by us.

## Comparison table

| Tool | Scope | Offline? | Licence | Detection approach | Rule format | Pins / rug pull | Source |
|---|---|---|---|---|---|---|---|
| Snyk Agent Scan | Scans agents, MCP servers and skills on the machine ([README](https://github.com/snyk/agent-scan#readme)) | No. `scan` needs a `SNYK_TOKEN` and sends tool names, descriptions and server signatures to the Snyk API ([CLI reference](https://github.com/snyk/agent-scan/blob/main/docs/cli-reference.md), [README](https://github.com/snyk/agent-scan#analysis-and-validation)) | Apache-2.0 ([LICENSE](https://github.com/snyk/agent-scan/blob/main/LICENSE)) | Local checks plus remote analysis. Reports scored risks such as `prompt_injection_tool_desc` ([risks](https://github.com/snyk/agent-scan/blob/main/docs/risks.md)) | Not public. The analysis runs in the Snyk API ([README](https://github.com/snyk/agent-scan#analysis-and-validation)) | Not described in the current README or docs we read. The 2025 MCP-Scan post describes tool pinning with hashes ([post](https://invariantlabs.ai/blog/introducing-mcp-scan)) | [repo](https://github.com/snyk/agent-scan) |
| mcpproxy-go | Proxy that federates MCP servers and holds new servers in quarantine ([README](https://github.com/smart-mcp-proxy/mcpproxy-go#why-mcpproxy)) | Yes for the core binary and the offline scan ([README](https://github.com/smart-mcp-proxy/mcpproxy-go#why-mcpproxy)) | MIT ([LICENSE](https://github.com/smart-mcp-proxy/mcpproxy-go/blob/main/LICENSE)) | Offline detect engine with seven checks, for example `unicode.hidden` and `phrase.injection`. Optional Docker-based scanners ([quarantine docs](https://docs.mcpproxy.app/features/security-quarantine/), [scanner plugins](https://docs.mcpproxy.app/features/security-scanner-plugins/)) | No schema in the pages we read. The docs name a signature file, `scanner-bundle.json` ([quarantine docs](https://docs.mcpproxy.app/features/security-quarantine/)) | Yes. Hashes each tool and holds a changed tool for review ([quarantine docs](https://docs.mcpproxy.app/features/security-quarantine/)) | [repo](https://github.com/smart-mcp-proxy/mcpproxy-go) |
| Docker MCP tooling (we studied the Docker MCP Gateway, `docker/mcp-gateway`, and the MCP Toolkit) | Runs MCP servers in containers behind one gateway ([README](https://github.com/docker/mcp-gateway#readme)) | Not stated as offline. Catalogs and images come from OCI registries ([README](https://github.com/docker/mcp-gateway#catalog-management)) | MIT ([README](https://github.com/docker/mcp-gateway#license)) | Isolation and policy, not tool-description analysis: signature checks on `mcp/` images, secret-pattern blocking, name collision checks ([security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md)) | Unknown. No detection rules found. Catalog entries use a server spec ([docs](https://github.com/docker/mcp-gateway/blob/main/docs/server-entry-spec.md)) | Not described for tool definitions in the pages we read ([Toolkit docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/), [security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md)) | [repo](https://github.com/docker/mcp-gateway), [Toolkit docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/) |
| `alexar76/warden` | Scans MCP configs of several clients and can wrap a stdio server as a firewall ([README](https://github.com/alexar76/warden#readme)) | Mostly. The README says the only network traffic is to the servers in your config. Opt-in features (`--histor`, a signed feed, a classifier) use the network ([README](https://github.com/alexar76/warden#scan-every-server-your-clients-start)) | MIT ([README](https://github.com/alexar76/warden#readme)) | 36 static regex rules, a threat feed, an origin gate and a pinning gate ([gates](https://github.com/alexar76/warden/blob/main/docs/gates.md)) | Regex table. `staticScanRuleset()` returns each rule with its regex source and flags ([gates](https://github.com/alexar76/warden/blob/main/docs/gates.md)) | Yes. A sha256 hash of the tool definitions is compared with the approved pin. A change raises `TOOL_DEF_DRIFT` ([gates](https://github.com/alexar76/warden/blob/main/docs/gates.md)) | [repo](https://github.com/alexar76/warden) |
| `mcp-lock` (we studied `dragoscv/mcp-lock`; the name is ambiguous, see below) | Lockfile for MCP tools, with a CI check and a runtime proxy ([README](https://github.com/dragoscv/mcp-lock#readme)) | Not stated. It connects to the servers in your config ([README](https://github.com/dragoscv/mcp-lock#config)) | MIT ([package.json](https://github.com/dragoscv/mcp-lock/blob/main/package.json)) | The README describes only hash comparison, no content analysis ([README](https://github.com/dragoscv/mcp-lock#what-is-hashed)) | None. It writes `mcp-lock.json` ([README](https://github.com/dragoscv/mcp-lock#readme)) | Yes. This is its main feature: it hashes description, schema and annotations apart ([README](https://github.com/dragoscv/mcp-lock#what-is-hashed)) | [repo](https://github.com/dragoscv/mcp-lock) |

## Tool notes

### Snyk Agent Scan

- The repository `invariantlabs-ai/mcp-scan` now redirects to `snyk/agent-scan`
  ([GitHub API](https://api.github.com/repos/invariantlabs-ai/mcp-scan)). It is Python. The
  [README](https://github.com/snyk/agent-scan#readme) lists `uvx` and a standalone binary as install
  methods. The repository was active on 2026-10-23.
- It finds Claude Code, Cursor, Codex and other clients, and also scans agent skills
  ([README](https://github.com/snyk/agent-scan#supported-agents-and-capabilities)).
- It starts stdio servers and connects to remote ones to read tool descriptions. It asks for consent
  for each server in interactive runs ([README](https://github.com/snyk/agent-scan#interactive-consent-for-mcp-servers)).
- `inspect` shows components without the analysis step
  ([README](https://github.com/snyk/agent-scan#cli-parameters)).
- The README says the CLI output is experimental and can change without notice
  ([README](https://github.com/snyk/agent-scan#readme)).
- It does not accept outside contributions
  ([README](https://github.com/snyk/agent-scan#agent-scan-is-closed-to-contributions)).
- The Invariant Labs tool poisoning post is the base of this work
  ([post](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)).

### mcpproxy-go

- Repository: [smart-mcp-proxy/mcpproxy-go](https://github.com/smart-mcp-proxy/mcpproxy-go). It is
  written in Go and was active on 2026-10-23.
- New servers are quarantined. The user reviews and approves them
  ([README](https://github.com/smart-mcp-proxy/mcpproxy-go#3-add-your-first-server-and-approve-it)).
- Trust modes are `manual` (default), `scan` and `auto`. The docs say `auto` carries "rug-pull risk"
  ([quarantine docs](https://docs.mcpproxy.app/features/security-quarantine/)).
- The README lists exceptions to the review hold, for example input-schema-only edits outside `scan`
  mode ([README](https://github.com/smart-mcp-proxy/mcpproxy-go#why-mcpproxy)).
- The README says a clean scan does not prove a server is safe
  ([README](https://github.com/smart-mcp-proxy/mcpproxy-go#3-add-your-first-server-and-approve-it)).
- Note: the README and the docs page word the `manual` mode a little differently (the README lists
  exceptions, the docs page says every change is held). We cite both and do not decide between them.

### Docker MCP tooling

"Docker MCP tooling" is not one product. We studied two parts that fit the issue best:

- The [Docker MCP Gateway](https://github.com/docker/mcp-gateway) (the `docker-mcp` CLI plugin). It
  is Go, MIT, and was active on 2026-10-23.
- The [MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/) in Docker Desktop,
  which uses the gateway and the Docker MCP Catalog.

We did not study the [Docker MCP Catalog](https://hub.docker.com/mcp) build and review process. Docker
says it is separate from the gateway repository
([security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md)).

Facts from the [security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md):

- Signature verification is on by default for images in the `mcp/` namespace.
- Server containers get no host environment by default. They run with `no-new-privileges` and CPU and
  memory limits.
- `--block-secrets` scans tool-call arguments and text responses for secret-like values.
- The gateway rejects tool names that collide with another enabled server.
- Remote URLs must be public HTTPS by default. Loopback, private and cloud-metadata addresses are
  refused.

The gateway also has OpenTelemetry instrumentation
([telemetry docs](https://github.com/docker/mcp-gateway/blob/main/docs/telemetry/README.md)). We did
not check where, or if, it sends data by default.

### alexar76/warden

- Repository: [alexar76/warden](https://github.com/alexar76/warden). It is TypeScript with no npm
  runtime dependencies, MIT, created on 2026-08-24, and was active on 2026-10-23
  ([README](https://github.com/alexar76/warden#readme)). The README names the npm package
  `@aimarket/warden`.
- `warden scan` reads the MCP configs of Claude Code, Claude Desktop, Cursor, VS Code and Windsurf,
  connects to the servers, and prints a table, JSON, SARIF or Markdown
  ([README](https://github.com/alexar76/warden#scan-every-server-your-clients-start)).
- A `warden.lock.json` file turns a change in tool definitions into a reviewable diff
  ([README](https://github.com/alexar76/warden#scan-every-server-your-clients-start)).
- `wrap` puts Warden in front of one stdio server. First contact creates a pin. A later change needs
  a human to run `pins approve` in a terminal
  ([README](https://github.com/alexar76/warden#protect-claude-desktop-or-cursor-with-one-wrapper)).
- Each verdict records the rule set version and a digest of the rules
  ([README](https://github.com/alexar76/warden#the-verdict-is-meant-to-be-recorded)).
- The README states what it does not do: it is not a sandbox, not a model, and the regex scan misses
  paraphrases no rule covers ([README](https://github.com/alexar76/warden#what-this-is-not)).
- The README publishes benchmark numbers and a method
  ([scanner comparison](https://github.com/alexar76/warden/blob/main/docs/scanner-comparison.md)).
  These numbers come from the project. We did not reproduce them.
- Warden is the closest tool to mcpmoat in this list.

### mcp-lock

The name `mcp-lock` points to several projects. No source ties the issue text to one of them. We
searched GitHub repository search, the npm registry, PyPI and crates.io on 2026-10-23.

| Candidate | What it is | Source |
|---|---|---|
| `dragoscv/mcp-lock` (studied) | Pins tool descriptions and schemas in `mcp-lock.json`. Has `lock`, `check` and a stdio `proxy`. npm name `@codai/mcp-lock`. MIT. Version 0.2, API may change before 1.0. | [README](https://github.com/dragoscv/mcp-lock#readme), [package.json](https://github.com/dragoscv/mcp-lock/blob/main/package.json) |
| `blestlabs/mcp-lock` | "package-lock.json for your MCP servers": `pin`, `diff`, `scan`, `ci`. Apache-2.0. Last push 2026-02-10. | [README](https://github.com/blestlabs/mcp-lock#readme) |
| `mcpguards/mcp-lock` | Records the version and tarball hash of each MCP server package. It pins packages, not tool definitions. MIT. | [README](https://github.com/mcpguards/mcp-lock#readme) |
| `StevieHeyes/MCP-Lock` | A local control plane that starts and stops servers and gates write access. Not a scanner. Apache-2.0. | [README](https://github.com/StevieHeyes/MCP-Lock#readme) |
| npm package `mcp-lock` | An unrelated placeholder (version 0.0.1, "part of HLOS ecosystem"). | [npm registry](https://registry.npmjs.org/mcp-lock) |
| PyPI and crates.io `mcp-lock` | No package found. | [PyPI](https://pypi.org/pypi/mcp-lock/json), [crates.io](https://crates.io/api/v1/crates/mcp-lock) |

We picked `dragoscv/mcp-lock` because its name is exact and its purpose (pin tool definitions, detect
drift) matches the issue. This is our choice, not a fact from a source. If the issue author meant
another project, the row must change. We read only the README and `package.json` of each repository.
Several other lockfile-style tools exist under other names. We did not study them.

## Ideas to adopt

Each idea names the tool that gave it to us.

1. Hash description, schema and annotations as separate parts. A review then shows what kind of
   change happened. Hash canonical JSON with sorted keys, so a key reorder is not a false alarm.
   Credit: [mcp-lock](https://github.com/dragoscv/mcp-lock#what-is-hashed). mcpproxy-go also
   re-baselines key-order-only changes without a hold
   ([docs](https://docs.mcpproxy.app/features/security-quarantine/)).
2. Record the rule set version and a digest of the rules in every report. Without them, a changed
   result cannot be told from a changed server. Credit:
   [Warden](https://github.com/alexar76/warden#the-verdict-is-meant-to-be-recorded).
3. Show a pin change field by field, with words added and removed in the description. Credit:
   [Warden](https://github.com/alexar76/warden#protect-claude-desktop-or-cursor-with-one-wrapper).
4. Keep severity and blocking as two separate axes. An advisory finding is reported and never
   blocks. Credit: [Warden](https://github.com/alexar76/warden#the-gate-chain).
5. Split checks into hard checks (fail) and soft checks (ask a human to review). Credit:
   [mcpproxy-go](https://docs.mcpproxy.app/features/security-quarantine/).
6. Ask for consent before mcpmoat starts each server. Show the command or URL, with env values and
   headers redacted. Credit:
   [Snyk Agent Scan](https://github.com/snyk/agent-scan#interactive-consent-for-mcp-servers).
7. Refuse remote destinations in link-local and cloud-metadata ranges, and do not follow redirects.
   Credit: [Snyk Agent Scan](https://github.com/snyk/agent-scan#security-warning) and the
   [Docker MCP Gateway](https://github.com/docker/mcp-gateway/blob/main/docs/security.md).
8. Flag a tool name that collides with a tool from another server. This helps with shadowing (T3).
   Credit: [Docker MCP Gateway](https://github.com/docker/mcp-gateway/blob/main/docs/security.md).
9. Write down the limits in plain words: what the tool does not cover. Credit:
   [mcpproxy-go](https://github.com/smart-mcp-proxy/mcpproxy-go#why-mcpproxy) and
   [Warden](https://github.com/alexar76/warden#what-this-is-not).
10. Publish the method behind any detection numbers, with a held-out test set. Credit:
    [Warden](https://github.com/alexar76/warden/blob/main/docs/scanner-comparison.md).
11. For later phases: verify image signatures and run servers with a small environment and limits.
    Credit: [Docker MCP Gateway](https://github.com/docker/mcp-gateway/blob/main/docs/security.md).

## Ideas to avoid

1. Do not need an account or send tool text to a remote service for the default scan. Snyk Agent
   Scan does this ([README](https://github.com/snyk/agent-scan#analysis-and-validation)). It breaks
   the offline goal (G7 in the PRD).
2. Do not change the output format without a version. Snyk Agent Scan states its output is
   experimental ([README](https://github.com/snyk/agent-scan#readme)). mcpmoat promises versioned
   JSON.
3. Do not offer a mode that trusts tool changes without a hold. mcpproxy-go has `auto` mode, which
   its docs link to rug-pull risk ([docs](https://docs.mcpproxy.app/features/security-quarantine/)).
4. Do not add a runtime proxy in phase 1. mcpproxy-go, Warden `wrap` and `mcp-lock proxy` sit in the
   message path ([mcp-lock](https://github.com/dragoscv/mcp-lock#runtime-proxy),
   [Warden](https://github.com/alexar76/warden#protect-claude-desktop-or-cursor-with-one-wrapper)).
   That is the firewall scope of a later phase.
5. Do not add optional network features to the scanner in phase 1. Warden has `--histor`, a signed
   feed and a classifier that use the network
   ([README](https://github.com/alexar76/warden#scan-every-server-your-clients-start)). The only
   opt-in network call in mcpmoat is the `--llm` flag.
6. Do not add telemetry. The Docker MCP Gateway has OpenTelemetry instrumentation
   ([docs](https://github.com/docker/mcp-gateway/blob/main/docs/telemetry/README.md)). mcpmoat has
   none.
7. Do not rely on a hash-only check. `mcp-lock` as described in its
   [README](https://github.com/dragoscv/mcp-lock#what-is-hashed) finds changes, not bad content, so a
   tool that is already bad when you first pin it stays pinned. mcpmoat pins and also applies rules
   (T1, T3).

## How mcpmoat differs

These points come from the [PRD](PRD.md) and the facts above.

- **Offline by design.** mcpmoat has no account and no telemetry. It makes no network call except to
  the MCP servers you configured and, only with `--llm`, to the LLM provider you choose (PRD
  section 1.1 and NFR-01).
- **One person, one machine.** The target user is an individual developer on macOS or Linux. The PRD
  lists SSO, RBAC and a central dashboard as non-goals (section 2.2).
- **Rules plus pins in one scan.** mcpmoat applies YAML rules and native heuristics to detect T1 to
  T5. It pins a hash of every tool to detect rug pulls (T2). Each built-in rule is one YAML file
  with positive and negative tests (NFR-05).
- **Open rule files.** Rules are YAML files in the repository (`rules/`), embedded in the binary.
  Snyk Agent Scan keeps its rules in a remote service
  ([README](https://github.com/snyk/agent-scan#analysis-and-validation)). Warden keeps rules as a
  regex table ([gates](https://github.com/alexar76/warden/blob/main/docs/gates.md)).
- **Go, one static binary.** mcpmoat ships as a single binary through GitHub Releases, Homebrew and
  `go install`. Warden needs Node 20 or newer
  ([README](https://github.com/alexar76/warden#readme)). `mcp-lock` is a Node package
  ([package.json](https://github.com/dragoscv/mcp-lock/blob/main/package.json)).
- **Scanner first, no proxy in phase 1.** mcpmoat reads and reports. It does not sit in the message
  path in phase 1.
- **Closest overlap.** Warden also scans local configs, connects to servers, and pins tool
  definitions. The difference is the language, the YAML rule model with required tests, and the
  choice to keep optional network features out of phase 1.

## Sources

Research for this page:

- Snyk Agent Scan: [repo](https://github.com/snyk/agent-scan),
  [README](https://github.com/snyk/agent-scan#readme),
  [CLI reference](https://github.com/snyk/agent-scan/blob/main/docs/cli-reference.md),
  [scanning](https://github.com/snyk/agent-scan/blob/main/docs/scanning.md),
  [risks](https://github.com/snyk/agent-scan/blob/main/docs/risks.md),
  [LICENSE](https://github.com/snyk/agent-scan/blob/main/LICENSE),
  [Introducing MCP-Scan](https://invariantlabs.ai/blog/introducing-mcp-scan)
- mcpproxy-go: [repo](https://github.com/smart-mcp-proxy/mcpproxy-go),
  [LICENSE](https://github.com/smart-mcp-proxy/mcpproxy-go/blob/main/LICENSE),
  [security quarantine](https://docs.mcpproxy.app/features/security-quarantine/),
  [security scanner plugins](https://docs.mcpproxy.app/features/security-scanner-plugins/)
- Docker: [docker/mcp-gateway](https://github.com/docker/mcp-gateway),
  [security model](https://github.com/docker/mcp-gateway/blob/main/docs/security.md),
  [telemetry](https://github.com/docker/mcp-gateway/blob/main/docs/telemetry/README.md),
  [server entry spec](https://github.com/docker/mcp-gateway/blob/main/docs/server-entry-spec.md),
  [MCP Toolkit docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)
- Warden: [repo](https://github.com/alexar76/warden),
  [gates](https://github.com/alexar76/warden/blob/main/docs/gates.md),
  [scanner comparison](https://github.com/alexar76/warden/blob/main/docs/scanner-comparison.md)
- mcp-lock: [dragoscv/mcp-lock](https://github.com/dragoscv/mcp-lock),
  [blestlabs/mcp-lock](https://github.com/blestlabs/mcp-lock),
  [mcpguards/mcp-lock](https://github.com/mcpguards/mcp-lock),
  [StevieHeyes/MCP-Lock](https://github.com/StevieHeyes/MCP-Lock),
  [npm registry](https://registry.npmjs.org/mcp-lock),
  [PyPI](https://pypi.org/pypi/mcp-lock/json),
  [crates.io](https://crates.io/api/v1/crates/mcp-lock)
- Repository metadata (licence, last push, redirect) came from the GitHub API on 2026-10-23, for
  example [snyk/agent-scan](https://api.github.com/repos/snyk/agent-scan).

Threat model references:

- Invariant Labs, [MCP security notification: tool poisoning attacks](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/)
