# aimarket-oracle-gateway 0.3.1 — verifiable oracles as MCP tools

- **Payment input is checked, not trusted.** The gateway verifies the money-moving fields it is handed instead of passing them on (2026-10-08 review).
- **`__version__` and `server.json` agree with the package** (the module reported 0.1.0).
- **CI hardened:** every action pinned to a commit, read-only default tokens.

```bash
uvx aimarket-oracle-gateway
```
