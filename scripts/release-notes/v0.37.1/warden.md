# WARDEN 0.37.1 — scan says what `--histor` could check

```bash
npm install -g @aimarket/warden@0.37.1
```

`warden-mcp scan` reads your MCP configs and vets the tool definitions on your machine. With `--histor` it also asks
the public [HISTOR](https://histor.modelmarket.dev) log one question per server: were you served the tools the log
records for everyone? That question is opt-in, and it stays opt-in.

What changes: a scan run without `--histor` now ends with one more line.

```text
2 of these servers are public (npm, PyPI or a public address). Add --histor to ask the HISTOR log whether you were served the tools it records for everyone. Nothing was sent to it in this run.
```

- The count is made on your machine from the configs: a stdio server started from the public npm or PyPI registry,
  or a remote server at a public address. A private registry, a local file or a non-public address is not counted.
- Nothing is sent to HISTOR without the flag. `--json` carries the count as `historAvailable`; the Markdown report
  has the same line.
- With `--histor` the line does not appear.

Nothing else changes: scan verdicts, rulesets (23), the malware list, masking and the flow guard rules are 0.37.0's.
