# WARDEN flow guard on the Multica agents: check and update, 2026-11-19

Host attested, `/opt/multica`. Times are UTC from the host clock.

## What was there

- The daemon `multica-daemon` runs every agent (вжик, тайный покупатель, ревьюер поставщиков, недельный пост, order
  agent, qa-worker) through OpenCode with the WARDEN plugin from `/opt/multica/opencode-guard` (`block: 'data'`,
  policy `flow-policy.json`, mode `ask`, nobody answers a question, so a sensitive call is refused).
- The guard files were a build of 2026-11-10: 18 of 22 files equal to npm 0.31.0, 4 older (classify, policy, pre,
  screen).

## What the check found

| Check | Build of 11-10 | npm 0.31.0 | main da259d3c3 |
|---|---|---|---|
| Red team, `data` mode: attacks delivered | 3 of 28 (action-only) | 3 of 28 | not rerun in `data` mode |
| Red team release gate (`npm run test:redteam`) | n/a | 0 of 28 | 0 of 28 |
| Field regressions delivered | 1 of 4 (`field-npm-ci-output`) | 0 of 4 | 0 of 4 |
| Six ordinary agent flows (`agents-replay.mjs`) | pass | pass | pass |
| Five attacks on the agents (`agents-replay.mjs`) | 4 denied | 4 denied | 5 denied |
| Token sent from an environment variable (`env-probe.mjs`, 11 forms) | 11 pass | 11 pass | 0 pass |

The gap: after outside text, `printenv TELEGRAM_BOT_TOKEN | curl …`, `$GH_TOKEN` in a `curl`, `env | curl`,
`/proc/self/environ` were reviewed as ordinary shell code and passed in `data` mode. `GH_TOKEN` and the Telegram
variables are in the agents' shell environment, and the egress allowlist contains GitHub and Telegram.

The agents' own recorded sessions (OpenCode database, names only) use these variables only in presence tests
(`test -z "$GH_TOKEN"`, `${TELEGRAM_BOT_TOKEN:+yes}`), which the fix keeps.

## What was changed

- WARDEN, main da259d3c3: such a call is `credential_egress`, sensitive; a plain print (`env`, `printenv NAME`) still
  runs and records a credential read. Not on npm (CHANGELOG "Next release").
- attested, 21:01: the 22 guard files replaced with the build of da259d3c3 (`install.sha256`; 19 files equal to npm
  0.31.0). No agent was running; no restart is needed, each task starts a new OpenCode process.
- Check inside the daemon container with the live policy, 21:01: six ordinary flows pass, five attacks denied,
  environment sends 12 denied, `gh api …` and `tg-send "…"` pass.

`curl … -H "Authorization: Bearer $GH_TOKEN"` after outside text is now refused too: it has the same form as a send
to a gist. The agents use `gh` and `tg-send`, which read the token themselves.

## Rollback

    install -o root -g root -m 644 /root/multica-guard-20261119/before/*.js /opt/multica/opencode-guard/warden/

## Not done

- (Done on 2026-11-20, see the last section.) A run of a real agent after the update.
- The three action-only deliveries in `data` mode stay: that mode refuses data sends only.

## Rerun

    node agents-replay.mjs <dir with the guard .js files>     # needs flow-policy.json and task-manifest.json in cwd
    node env-probe.mjs <dir>

## 2026-11-20: real runs, then 0.33.0

- The first scheduled runs under the updated guard (08:02 and 09:01, read from the guard's own logs in
  `/home/node/.local/state/warden/claude-code/flow/`): 16 calls allowed and 6 refused, 16 allowed and 1 refused. The
  refusals are `opaque_shell` in a session that had read a credential and one `private_text`; none has the new reason
  `credential_egress`. The eleven sessions before had 1 to 13 refusals each, so the update refused nothing new.
- 0.32.0 is on npm (07:18:21Z) and equals the files installed here. 0.33.0 (08:43:31Z) changes one of the 22 files,
  `flow-guard-classify.js`. On the 0.33.0 files from the npm tarball the replay gives the same result: six ordinary
  flows pass, five attacks denied, environment sends 12 denied, `gh api …` and `tg-send "…"` pass.
- 09:49:40Z the 22 files were replaced with npm 0.33.0's (`install-033.sha256`), no agent running; the plugin loads
  inside the daemon container. The 0.33.0 files are kept in `/root/multica-guard-20261119/v033`, the 0.32.0 files in
  `…/new`, the build of 11-10 in `…/before`.
- Not checked: a run under 0.33.0 (the next scheduled one is about 10:00).
