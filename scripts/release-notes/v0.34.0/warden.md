# WARDEN 0.34.0 — which way a behaviour hint moved

```bash
npx -y @aimarket/warden@0.34.0 scan
```

When a reviewed tool changes, the re-approval text and the `scan --lock` report now name the behaviour hint that moved
and its direction. The full text is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.34.0/CHANGELOG.md).

A tool whose `readOnlyHint` goes from true to false now says it does more, so an approval given to it before does not
cover it (`widens`). A tool whose `readOnlyHint` goes from false to true now claims less, and a host that skips the
prompt for read-only tools stops asking about it (`narrows`). The same holds for `destructiveHint`, `idempotentHint`
and `openWorldHint`; an absent hint counts as the specification's default. The Markdown summary lists these moves
under "Read first" above the diff, and the JSON report carries them as `lock.changes[].hints`.

Nothing new is refused: any change to a reviewed tool already failed the lock and asked again in `wrap`. In HISTOR's
record from 23 October to 16 November 2026, `readOnlyHint` went from true to false on 524 tools and from false to true
on 321; for 176 and 262 of them the Vercel AI SDK's tool fingerprint did not change in that read.

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No scan verdict changes.
