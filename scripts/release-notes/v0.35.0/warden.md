# WARDEN 0.35.0 — a hint its own description contradicts

```bash
npx -y @aimarket/warden@0.35.0 scan
```

A lock or a fingerprint keeps a wrong behaviour hint as stable as a right one: it tells you the server changed its
story, not whether the story was true. One part of that is visible in the definition itself. `scan` now reports
`TOOL_HINT_CONTRADICTS_DESCRIPTION` when a tool says `readOnlyHint: true` while its description says it deletes,
sends a message, writes files or creates an account, or says `destructiveHint: false` while its description says it
removes, overwrites, "replaces the current …" or "cannot be undone". Example: GitHub's MCP server
`update_issue_labels` says `destructiveHint: false`, and its description says "This replaces the current labels with
the provided list". The full text is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.35.0/CHANGELOG.md).

The finding is advisory: it is shown in the text output, the Markdown summary and `--json` (not SARIF), and it never
blocks or changes the exit code. A host that skips approval for read-only or non-destructive tools would not ask
before such a call, so label the tool yourself. The check reads English descriptions, sentence by sentence, where the
tool is the subject of the verb; a hint that only the code contradicts is not seen.

On HISTOR's 2026-11-16 snapshot (468,359 tools with an explicit hint on 26,808 servers) it marks 307 tools on 204
servers that say `readOnlyHint: true` and 960 tools on 593 servers that say `destructiveHint: false`. In
hand-labelled samples of 50, 40 and 45 were real contradictions. Recall was not measured.

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No scan verdict changes.
