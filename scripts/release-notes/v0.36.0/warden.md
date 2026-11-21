# WARDEN 0.36.0 — the evidence of a contradicted hint as fields

```bash
npx -y @aimarket/warden@0.36.0 scan --json
```

0.35.0 added `TOOL_HINT_CONTRADICTS_DESCRIPTION`: a tool that says `readOnlyHint: true` or `destructiveHint: false`
while its own description says otherwise. The finding named the matched words and quoted the sentence, but only inside
its message. In `--json` it now also carries them as fields, next to the message, which is unchanged:

```json
"evidence": {
  "claim": "destructiveHint=false",
  "matchedPhrase": "replaces the current",
  "quotedSentence": "This replaces the current labels with the provided list."
}
```

`matchedPhrase` is lower case, so findings group cleanly by trigger word; `quotedSentence` is the whole sentence
(control characters escaped), while the message still quotes its first 160 characters. Two runs can be diffed without
parsing the message:

```bash
npx -y @aimarket/warden@0.36.0 scan --json | jq -r '.servers[].findings[] | select(.code == "TOOL_HINT_CONTRADICTS_DESCRIPTION") | [.evidence.matchedPhrase, .tool, .evidence.quotedSentence] | @tsv'
```

In the library, `hintContradictions` adds `phrase` and `sentence` to each result and `hintContradictionFindings`
sets `evidence`. Asked for by a reader on DEV under the readOnlyHint article. The full text is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.36.0/CHANGELOG.md).

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No scan verdict or exit code changes.
