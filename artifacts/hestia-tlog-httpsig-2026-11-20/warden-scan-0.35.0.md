# warden.scan@v1 on WARDEN 0.35.0 — 2026-11-20

WARDEN 0.35.0 was released on npm by another session; its `dist-tags.latest` is 0.35.0. The agent was rebuilt the
same day, with two changes:

- **Bundle.** `scripts/build_warden_scan.sh`, esbuild 0.28.2, rebuilt from `warden/src` at main 2ffde06e9.
- **Hint check.** The agent now adds `hintContradictionFindings`, as `warden scan` in the package does (scan.ts
  line 524). It reports a `readOnlyHint: true` or `destructiveHint: false` that the tool's own description
  contradicts, as `TOOL_HINT_CONTRADICTS_DESCRIPTION`. The finding is advisory and never blocks.

## Checks

- Node, from the same entry bundled for node:
  - the five old cases answer exactly as before;
  - a new sixth case gives two findings: `update_issue_labels` "replaces the current labels" and `remove_file`
    "Deletes the file". The look-alike "List deleted files" is not marked.
- Live on the hearth, after `deploy --only warden-scan` at ~22:10Z: all six cases equal Node's answers byte for
  byte, report `warden: 0.35.0`, and come back signed.
- `tests/test_warden_scan.py` passes, including the bundle-reproducibility test with `ESBUILD` set. The QuickJS
  tests are skipped on the Mac; the live run above covers them.

**Rollback:** redeploy from the previous commit's `agents/warden-scan/handler.js` (0.34.0).
