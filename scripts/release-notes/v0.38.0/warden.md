# WARDEN 0.38.0 — a token sent back to its issuer is asked about, and the interceptor refuses tools next to result

```bash
npm install -g @aimarket/warden@0.38.0
```

A token of GitHub, GitLab, Slack or npm that goes back to its own issuer on one simple `curl`, `wget`,
`httpie` or `gh api` command is now asked about (`secret_issuer`), not denied: every destination must be an HTTPS
host of that issuer, and every copy of the token must sit in an authorisation header. Every other shape stays
denied; `deny` mode and unattended runs still refuse it. The terminal egress red team (`scripts/redteam/terminal-egress.mjs`)
records that only those four issuer requests changed (deny to ask); the seventeen attacks did not.

The interceptor also refuses a payload that puts `tools` next to `result`. Both validators used to read the
top-level `tools` first, so `{"tools":[clean],"result":{"tools":[poisoned]}}` looked clean and unchanged while a
lenient client (the MCP Python SDK drops the unknown member) reads `result.tools`. Both validators now refuse such
a payload, at the top or inside `result`, with `TSD-TOOL`, as mcp-tool-set-digest/1 section 3 (editors' draft of
2026-11-23) requires. The test copy of the specification's vectors follows its 92.

Scan verdicts, rulesets (23), the malware list and masking are unchanged from 0.37.3.

The full text is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.38.0/CHANGELOG.md).
