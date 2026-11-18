# WARDEN 0.30.0 — a gateway for OpenWebUI, and every launched package checked

```bash
npx -y @aimarket/warden@0.30.0 scan
npx -y @aimarket/warden@0.30.0 gateway --config gateway.json
```

Platforms such as OpenWebUI have no agent hooks for WARDEN to sit in: the model searches the web, reads documents and calls tools over HTTP in one chat. 0.30.0 adds `warden-mcp gateway`, which brings the flow guard and the tool-definition checks there, and closes a gap in 0.29.0's malware gate. The full list of changes is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.30.0/CHANGELOG.md).

- **`warden-mcp gateway`.** One process with one flow-guard state per chat:
  - `/mcp/<name>` and `/openapi/<name>/…` stand in front of MCP (Streamable HTTP) and OpenAPI tool servers (`mcpo` too). The gateway answers `tools/list` after the gates and pinning `wrap` uses, asks the flow guard before each call, and records and screens the result.
  - `/v1/prompt|source|pre|post|approve` decide for what never passes a proxy: the person's message, web search, documents, the platform's own tools.
  - In `ask`, a refused call carries a one-time code bound to the chat, the user, the tool and the exact arguments. Only the person's own message or the platform's confirmation dialog redeems it.
  - For OpenWebUI: a Filter function and `@warden_guard` for Python tools (`integrations/openwebui/`), and a Docker example with the tool servers on their own network.
  - Checked live on OpenWebUI v0.11.4 (native and "Default" function calling, OpenWebUI's own tools, the browser, the desktop app, Qwen and MiniMax through OpenRouter). Qwen 3.8 27B once followed an injected document; WARDEN refused the delete. An independent agent reviewed the gateway twice; what it found and what changed is in [docs/openwebui.md](https://github.com/alexar76/warden/blob/v0.30.0/docs/openwebui.md#independent-review). The two-week pilot in `audit` has not run yet, so there are no false-positive or latency figures.
- **Every package a launch line installs is checked.** The malware gate read one package per launch. It now also checks repeatable npm `--package` options, resolves `npm:` aliases to the package they install, checks extra packages named with Python launchers' `--with`, and reads `pipx run --spec`. An OpenSSF match blocks the launch even when its main package is clean. Found by an ecosystem audit on 2026-11-17.
- **Reading a key is not a key press.** After outside text, the flow guard refused `read_api_key`, `list_keys` or `rotate_key` as keyboard input. Credential and data keys (`api_key`, `ssh_keys`, `key_value`, `get_stripe_key`, `redis_get_key`, `key_get`) are now data; keyboard tools (`key`, `Key-Tool`, `vnc_key`, `key_toggle`, `press_keys`, `keyevent`) still count as keyboard input. Applies to the Claude Code plugin, Codex hooks, OpenCode and the gateway.
- **A verdict names its threshold.** `Warden.evaluate()`, `vet` and `vetLaunch` return `blockAtSeverity` beside `rulesets` (suggested in [#14](https://github.com/alexar76/warden/issues/14)).

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list unchanged from 0.29.0. Prepared first as 0.29.1 with the launch-package checks only; that version was never published.

Docs in five languages: [gateway](https://github.com/alexar76/warden/blob/v0.30.0/docs/gateway.md), [OpenWebUI](https://github.com/alexar76/warden/blob/v0.30.0/docs/openwebui.md).

Checks for this build:

| Check | Result |
|---|---|
| Tests | 2036 of 2036 |
| Red team, Claude Code profile | 0 of 28 attacks delivered; field regressions 0 of 4 |
| Red team, Codex / OpenCode | `all`: 0 of 28; `data`: 3 of 28, the same three as 0.26.0–0.29.0 |
| Doc version pins (`check-doc-versions --release`) | pass |
| MOMUS release gate | passed, run `20261118T041219`: development 8,244 attacks / 362 benign, holdout 24 / 24, candidates 25, behaviour 72 of 72; 0 missed, 0 false positives |
