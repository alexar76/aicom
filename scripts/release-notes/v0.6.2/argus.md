# ARGUS 0.6.2 — WARDEN 0.35.0

Since 0.6.1 (2026-11-20): the WARDEN dependency moves from 0.33.0 to 0.35.0. Nothing else in ARGUS changes, and nothing ARGUS shows or decides changes.

- WARDEN 0.34.0 names a behaviour hint that moved and its direction in `warden wrap`'s re-approval text and the `scan --lock` report; 0.35.0 adds the advisory `scan` finding `TOOL_HINT_CONTRADICTS_DESCRIPTION`. Both live in WARDEN's own commands. ARGUS calls the gate, whose verdicts and messages are the same as under 0.33.0.
- Rulesets (23), the known-malicious package list and the flow guard are as in 0.33.0. Pins stored by WARDEN 0.33.0 verify under 0.35.0, so servers approved before the update stay approved.

```bash
npm install -g @alexar76/argus3@0.6.2
```
