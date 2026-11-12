# WARDEN 0.24.0 — the flow guard for Codex and OpenCode

```bash
npx -y @aimarket/warden@0.24.0 scan
```

The last GitHub release was v0.21.0 (2026-10-25). npm has every version since; 0.24.0 was published on 2026-11-08. What changed, from the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.24.0/CHANGELOG.md):

- **0.24.0: flow guard for OpenAI Codex** (`@aimarket/warden/codex`, `docs/codex.md` in five languages). It covers the CLI, `codex exec`, the desktop app and Multica runtimes through Codex's command hooks. Codex has no "ask", so a question becomes `deny`, or a logged pass when you set `WARDEN_CODEX_BLOCK`. Unreadable input, an unknown event or a missing guard file deny the call.
  - Red-team replay in Codex's tool vocabulary: 0 of 28 attacks with `block=all`, 3 of 28 with `block=data`.
  - Live check on 2026-11-07 (Codex CLI 0.167.0-alpha.3): the `curl` sending `.env` was denied, and the listener received nothing.
- **0.23.0: flow guard for OpenCode** (`@aimarket/warden/opencode`, `docs/opencode.md`). Subagents share the guard's state.
  - New secret formats: Telegram bot tokens and AIMarket hub keys.
  - A UUID is treated as a record id, not as personal data.
- **0.22.4: ruleset v17.** `TOOL_DEF_CROSS_TOOL` catches a tool that adds a fixed address to another server's tool, and `TOOL_DEF_EXFIL` reads "put records@… in BCC" as well as "bcc records@…".
- **0.22.3:** the `--histor` tool-set digest follows MTL/1.1, where numbers are written as RFC 8785 doubles. A check that runs in CI says so in its User-Agent, and `warden-mcp --help` lists the commands.
- **0.22.1–0.22.2:** an opt-in structured-answer gate for ranking tasks, and stricter `server_info` input for status and approval calls.

What the flow guard does not do is listed in the docs: an injection that only changes the answer, an address the user pastes, and short pieces dressed as ordinary sentences.

Full list: [CHANGELOG.md](https://github.com/alexar76/warden/blob/v0.24.0/CHANGELOG.md).
