# Supplier reviewer: letters use only letter_points (attested, 2026-11-06)

Owner: «Да, выкатывай». Code: aicom `4945e0f4e` (main and Gitea).

## Why

The 2026-11-04 welcome draft to textokit asked the author to reword "instead of", "API key" and "secrets".
All three were WARDEN advisory word matches (`TOOL_DEF_IMPERATIVE`, `TOOL_DEF_CREDENTIAL_PARAM`). One of them was
"remove secrets and personal data before submitting", a privacy note the description should keep. The report did
not tell advisory matches from findings, so the model used them although its instructions forbade it.

## What changed on attested (container `multica-daemon`, Multica 0.8.0)

| Item | Before | After |
|---|---|---|
| `/home/node/tools/supplier-review/review.mjs` | sha256 `e6b574be1dfd2962…` (1ec9bd988) | sha256 `875d4ba8ffafa3b6…` (4945e0f4e), root:root 0644, the agent cannot write it |
| Agent «ревьюер поставщиков» `c232c399-cf59-4982-a1dc-3608daaf40c5`, instructions | `instructions.before.txt` (= repo before the fix) | `instructions.after.txt` (= repo `multica/supplier-review/instructions.ru.md` at 4945e0f4e), updated 2026-11-06T20:58:38Z |

`run.sh` is unchanged (sha256 `251dae7e768b379f…`). The agent's state `~/.local/state/supplier-review/state.json` was
not touched (last written by the 10:00 UTC run).

## Checks

- In the container, as the agent's user, the new `review.mjs` ran on a temporary copy of the hub's manifest, peers
  and observed sellers (downloaded 2026-11-06), with a fresh state in `/tmp/sr-smoke`, then removed. Findings
  high 69, medium 3, low 35, info 35 with `@aimarket/warden@0.23.0` ruleset v17. That is the same as the local run
  on the same files, which gives letter points: textokit 0, agent-exec 4 (the storage tool's string input schema,
  untyped properties in rpc and watch).
- `multica agent get` returns the new instructions; they differ from the repository file only by the final newline.
- The first real run is the autopilot at 10:00 UTC on 2026-11-07.

## Second step, 21:09–21:10 UTC: no letters to addresses nobody can write to

Owner: «Да, исключи». The agent's next run would have seen 88 new pending peers announced between 12:13 and
15:55 UTC, all of them probes of the hub's address checks: 69 not on https (DNS-rebinding names, `127.0.0.1@host`,
internal ports, redirects to `169.254.169.254`) and 19 on https that the hub never managed to read (webhook.site,
httpbin and tinyurl redirects, example.com, one with `<img onerror>` as its name). Each would have got a welcome
draft.

- Sources and items now carry `welcome` and `no_welcome_reason` (`not_https`, `no_public_name`,
  `credentials_in_address`, or `not_reached` for a peer with no `last_crawl`). The facts block counts them on one
  line, and the instructions say: no letter, one line in «Позиции», named in the Telegram summary only when
  `welcome=true`.
- `review.mjs` sha256 `b949baa5d36ca3ce…` (backup of the first step's file: `/root/sr-20261106/v2/review.before-v2.mjs`,
  sha256 `875d4ba8ffafa3b6…`); instructions updated 2026-11-06T21:10:17Z, `instructions.after.txt` here.
- Simulated next run in the container, from a copy of the agent's state and the hub's documents fetched at
  ~22:05 local time: 1 changed outside listing (agent-exec `execute`, output schema), 88 peers counted on one
  line (not https 69, never read 19), letters possible only for agent-exec. The agent's state was not touched.

To return to the first step: copy `/root/sr-20261106/v2/review.before-v2.mjs` in place of `review.mjs` as below,
and set the instructions from the repository at 4945e0f4e.

## Rollback

Backups on attested in `/root/sr-20261106/backup/` (`review.mjs`, `instructions.before.txt`):

```bash
ssh attested 'docker cp /root/sr-20261106/backup/review.mjs multica-daemon:/home/node/tools/supplier-review/review.mjs && docker exec -u 0 multica-daemon chmod 644 /home/node/tools/supplier-review/review.mjs'
```

```bash
ssh attested 'docker cp /root/sr-20261106/backup/instructions.before.txt multica-daemon:/tmp/sr-instr.txt && docker exec multica-daemon sh -c "multica agent update c232c399-cf59-4982-a1dc-3608daaf40c5 --instructions \"\$(cat /tmp/sr-instr.txt)\" --output json >/dev/null" && docker exec -u 0 multica-daemon rm -f /tmp/sr-instr.txt'
```

## Traps

- The daemon container drops all capabilities: `docker exec -u 0 … chown` fails. Files copied with `docker cp` are
  root-owned; the agent's user can read them but not change them. Remove a root-owned file in `/tmp` with `-u 0`.
- Do not run `run.sh` by hand to test: it advances the agent's state, and the next daily run then sees an empty
  difference.
