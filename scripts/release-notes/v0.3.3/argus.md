# ARGUS 0.3.3 — the personal agent behind the WARDEN firewall

Since 0.2.5 (July):

- **MCP servers run contained.** Each stdio MCP server ARGUS starts runs under bubblewrap, sandbox-exec or its own container, and ARGUS keeps its own secrets out of their environment.
- **WARDEN is its own package.** ARGUS pins `@aimarket/warden` from npm; its launch, pin and threat-feed gates fail closed.
- **Owner mandates.** ARGUS can pay with its owner's mandate instead of a wallet, and a config cannot drop the spend approvals.
- **A2A client for the hub:** `argus a2a search / invoke / task`.
- **Stricter config reading.** `include_schemas: "false"` means false; legacy pins are re-approved instead of trusted.

```bash
npm install -g @alexar76/argus3
```
