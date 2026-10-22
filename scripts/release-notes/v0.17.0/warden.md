# WARDEN 0.17.0 — a flow guard for agents, measured on AgentDojo

```bash
npx -y @aimarket/warden@0.17.0 scan
```

Checks every MCP server your clients start. No account, no API key, no model.

## What is new

- **Flow guard at tool-call boundaries.** After the agent reads outside text (a web page, an MCP result, a foreign file), a call that sends data out to a destination you did not name asks first, and a secret leaving is denied in any encoding. Runs as Claude Code plugin hooks, or for any MCP client through `warden-mcp wrap --flow NAME`.
- **Measured, not claimed.** On AgentDojo with a model that obeys every injection: 593 of 609 attack actions succeed without the guard, 0 of 584 with it. With a real model (DeepSeek V4.1 Flash, 21,654 runs), told the injection is the user's own: 42 attack actions without the guard, 0 with it. The cost: 51 of 97 clean tasks finish with the guard, 90 without. Method and numbers: [docs/flow-guard.md](https://github.com/alexar76/warden/blob/main/docs/flow-guard.md).
- **Rulesets v13 and v14.** A new rule reads argument descriptions for key material asked for by value. Writing it found a hole every ruleset had since v4: "Send me your private key." passed because of its final period. MCPTox held-out with v13: 171 of 218, unchanged. v14 only narrows when a key counts as kept locally and was not re-measured.
- **Security audit follow-up.** URL authority parsing, symlinked policy paths, contact resolution only through explicit contact tools, and opaque shell code gated even for allowed destinations.

Full list: [CHANGELOG.md](https://github.com/alexar76/warden/blob/main/CHANGELOG.md#0170--unreleased).

Try it in the browser, no install: [modelmarket.dev/tools/warden-scan](https://modelmarket.dev/tools/warden-scan?utm_source=github&utm_medium=release&utm_campaign=warden-0.17.0)
