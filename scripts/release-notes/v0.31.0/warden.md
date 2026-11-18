# WARDEN 0.31.0 — OpenWebUI in one command

```bash
npx -y @aimarket/warden@0.31.0 openwebui setup --url http://localhost:3000 --email admin@example.com
npx -y @aimarket/warden@0.31.0 openwebui check
```

0.30.0 brought the flow guard to OpenWebUI through `warden-mcp gateway`, but setting it up took five manual steps:
tokens, a gateway config, every tool connection re-entered by hand, the Filter imported and wired, and no way to see
that it worked. 0.31.0 does that for an OpenWebUI that already runs. The full list of changes is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.31.0/CHANGELOG.md).

- **`warden-mcp openwebui setup`.** It finds the OpenWebUI container and its Docker network, moves each tool server
  connection's key into the gateway's `.env`, starts the gateway next to OpenWebUI, and has OpenWebUI itself verify
  every server through the gateway. Then it installs the WARDEN Filter (active, global, valves set) and switches the
  connections over, with the chat and user headers OpenWebUI fills per call (`{{CHAT_ID}}`, `{{USER_ID}}`): no
  OpenWebUI restart, no new environment variable. Connections it cannot carry (per-user OAuth or session auth, header
  templates, forwarded cookies, `localhost` inside the container) stay direct and are named. The policy starts in
  `audit`. Without Docker, `--local` runs the gateway as a process.
- **`warden-mcp openwebui check`** proves the result: gateway health, the Filter, each connection reached through the
  gateway, two real decisions of the running gateway (a page from a web search that asks to send the chat out would be
  refused; the person's own request is allowed), and Python tools without `@warden_guard`.
- **`warden-mcp openwebui undo`** puts the original connections back, switches the Filter off and stops the gateway.
- **Audit answers name the refusal.** In `audit` the gateway's `/v1/pre` and its log line carry `wouldRefuse` with the
  reason `deny` would give, so a pilot can count what `deny` would stop before switching it on.
- **One start page for OpenWebUI**, in five languages: how the protection works (diagrams of a chat's states and of an
  injected page being stopped), setup in one command, the manual setup with a complete `gateway.json`, and the results
  of the live checks: [docs/openwebui.md](https://github.com/alexar76/warden/blob/v0.31.0/docs/openwebui.md).

Checked live: `scripts/openwebui-turnkey-check.sh` starts a fresh OpenWebUI v0.11.4 whose MCP and OpenAPI tool servers
are connected directly, runs `setup` and `check`, then the attack scenarios (native 10 of 10, legacy 4 of 4, OpenAPI
7 of 7) and `undo`. The two-week pilot in `audit` on a real project has not run yet, so there are no false-positive or
latency figures.

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No verdict changes.

Checks for this build:

| Check | Result |
|---|---|
| Tests | 2045 of 2045 |
| Red team, Claude Code profile | 0 of 28 attacks delivered; field regressions 0 of 4 |
| Red team, Codex / OpenCode | `all`: 0 of 28; `data`: 3 of 28, the same three as 0.26.0–0.30.0 |
| Doc version pins (`check-doc-versions --release`) | pass |
| MOMUS release gate | passed, run `20261118T145827`: development 8,244 attacks / 362 benign, holdout 24 / 24, candidates 23, behaviour 72 of 72; 0 missed, 0 false positives |
