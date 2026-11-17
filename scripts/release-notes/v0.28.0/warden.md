# WARDEN 0.28.0 — rulesets 21–23

```bash
npx -y @aimarket/warden@0.28.0 scan
```

No new commands or options; the minor version marks that static-scan verdicts change. Static-scan verdicts change only in the cases below. The full list is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.28.0/CHANGELOG.md).

- **Ruleset 21: two notes from the [#14](https://github.com/alexar76/warden/issues/14) re-run.**
  - "Returns the seed phrase checksum for a BIP39 wordlist entry" no longer blocks. The new guard `seedPhraseProperty` clears it only when all of these hold:
    - an output verb comes before the match;
    - a public property (checksum, word count, length, wordlist, language) follows it;
    - the clause has no possessive, request verb, requirement or wallet word.

    "Returns the seed phrase" and "Returns your seed phrase checksum" still block.
  - The advisory `TOOL_DEF_CREDENTIAL_PARAM` rules skip a credential the tool says it does not need: "No API key", "works without an API key", "API key not required". The negation has to sit next to the noun. No block-tier rule has this guard.
- **Rulesets 22 and 23: a negation about something else no longer excuses a credential request.**
  - Through ruleset 21, any refusal word in the same clause cleared a match. So "No signup needed: provide your private key", "Don't sign up, just paste your private key" and "Enter your seed phrase, we never store it" passed.
  - The `polarity` guard now takes the last refusal cue before the match. That cue no longer counts once a colon, dash, opening parenthesis or comma closes it, and the text after the break asks for the secret.
  - A promise after a requested secret ("…, we never store it", "(never stored)") does not withdraw the request.
  - Refusals that govern the request still clear it: "Never, under any circumstances, share your private key", "Under no circumstances, share your private key", "Send your private key to no one", "Never share your seed phrase, or paste your private key anywhere".
  - The cases are in `test/ruleset-v22.test.ts` and `test/ruleset-v23.test.ts`.
- **Field corpus.** We compared rulesets on the committed 2026-10-01 corpus (1,027 servers, 16,231 tools):
  - ruleset 20 against 21: no block lost and none added; 369 advisory matches go away;
  - 21 against 22 and 22 against 23: every blocking and advisory verdict is identical.
- **Markdown report.** The footer of `--markdown` output, the GitHub step summary and the PR comment links to the source repository.

Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`.

Checks for this build:

| Check | Result |
|---|---|
| Tests | 1891 of 1891 |
| Red team, Claude Code profile | 0 of 28 attacks delivered; field regressions 0 of 4 |
| Red team, Codex and OpenCode, `all` | 0 of 28 |
| Red team, Codex and OpenCode, `data` | 3 of 28 (the same three action-only attacks as in 0.26.0 and 0.27.0) |
| Clean install of the tarball | pass |
| MOMUS release gate | the evidence folder in the monorepo records the run |
