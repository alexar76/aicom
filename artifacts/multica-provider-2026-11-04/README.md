# Multica provider (long jobs on the attested hub) — 2026-11-04

Owner: «а потом сразу все остальные пункты» (idea 2), then «если готово к использованию - выкатывай» (20:03Z).
Rolled 20:05–20:07Z; the first real order failed on two design problems, so the sale is **paused** since 20:11:48Z
(provider stopped, hub settings kept). Redesigned the same evening («Да, переделывай»), rolled 2026-11-05 03:58Z,
selling since the owner's GitHub token and two test orders (04:23–04:40Z). Times are server clocks (UTC).

## Done on attested

- Agent «дайджест на заказ» `0ac4ba96-4066-4c8d-bfb9-690ee0c98d3e` (deepseek/deepseek-flash, private, max 1 task);
  custom env: hub keys, `GH_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` empty, hub MCP off
  (`OPENCODE_CONFIG_CONTENT`); instructions = `multica/provider/agent-instructions.ru.md` (16:14Z).
- Autopilot `e06a96e6-c05f-4199-9baa-b01c8866f627` (create_issue), webhook trigger `85191ccb…`. The first webhook
  path was printed into a working log, so it was rotated before use; the current path is only in
  `/root/multica-provider-20261104/webhook.path` (0600). Test delivery 16:06Z → MY-61: the payload reaches the task as
  a JSON block in the description; the test agent read job_id, login, days.
- Image `multica-provider:20261104` (`sha256:dc14dc17abcb…`) built from `multica/provider/` in
  `/root/multica-provider-20261104/provider`; imports checked with no network.
- Multica skill `aimarket` `fd5d135e-4516-49cb-b656-ca2c887bb568` created from `multica/community/aimarket/SKILL.md`,
  not assigned to any agent.

## Rollout 2026-11-04 (owner's yes 20:03Z)

```bash
ssh attested 'cd /root/multica-provider-20261104 && python3 -I provider_secrets.py && python3 -I patch_compose.py && (cd /opt/multica && docker compose config -q) && (cd /opt/aicom/attested/attested-memory-hub && docker compose config -q)'
ssh attested 'cd /root/multica-provider-20261104 && python3 -I roll_hub.py'
ssh attested 'cd /opt/multica && docker compose up -d --no-deps provider'
```

1. `provider_secrets.py` (first named `secrets.py`: that name hid the standard `secrets` module, the first run
   stopped after copying the backup and changed nothing; renamed, run with `python3 -I`): publisher token appended to
   the hub's `.env` (backup `.env.bak-20261104-provider`), `/opt/multica/secrets/provider.env` 0600. Names only.
2. `patch_compose.py`: both compose files patched, backups `docker-compose.yml.bak-20261104-provider`; both stacks
   pass `docker compose config -q`.
3. Hub roll 20:05:26Z: DB backup `/root/hub-backups/attested-memory-hub-hub-1-pre-provider-20261104T200526Z.dump`
   (284K), then `rollout_container.py --set` for the three variables: healthy, image unchanged
   (`sha256:629feadf…` = `bref2-20261104`), `hub` alias kept on `attested-memory-hub_default`. Previous container
   `attested-memory-hub-hub-1-security-prev-1793822726993196303`, snapshot
   `/root/security-rollbacks/attested-memory-hub-hub-1-1793822726993196303/inspect.json`.
4. Provider up 20:06Z; both listings registered and `live` in the public manifest of hub.attestedmemory.net:
   `github.digest.order@v1` $0.05, `github.digest.result@v1` $0. Their `invoke_url` is the internal
   `http://multica-provider:8090/…`, like the hub's own gateway sellers (memory-market, truth-layer,
   provenance-ledger): buyers call through the hub.
5. Real order 20:07:28Z with вжик's key (`multica-vzhik`): `job_687b914aba1fd2ca1cf103d94c9f68e5` queued, $0.05
   charged (4.91 → 4.86), hub receipt `rcpt_f0ce832b829ab7c7dc0ec61b2c93623f` signed (Ed25519 + ML-DSA-65);
   `receipt_binding` input and output hashes match the input and the answer. The hub requires the seller's
   request-bound signature (`AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG=1`), so the 200 also means the provider's
   signature checked out. The webhook made task **MY-62** at the same second.

## What failed (MY-62, 20:07:28–20:07:54Z)

- **GitHub 403 on all three reads.** Not a block: the attested host's IP had used GitHub's 60 unauthenticated
  requests per hour (`/rate_limit`: core used 60, reset 20:29:49Z). Through the agents' egress proxy GitHub was hit
  only 5 times in two hours (3 by the agent, 2 by my check), so something else on the host spends the shared limit;
  no URL in container logs names it. Unauthenticated reads from attested are not dependable.
- **WARDEN refused the delivery** (block=data, `sensitive: true`, 20:07:45Z). The agent reads its task with
  `multica issue get`; shell output is private text to the guard, so the job token in `result_url` is private. After
  the GitHub reads (outside text) no call may carry private text, whatever the destination: in `data` mode the guard
  refuses every sensitive payload. That is the guard's contract for unattended agents (read outside text, then
  report), not a guard bug: the design asked the agent to send private data out after outside text.
- The agent answered honestly in MY-62 (403 on all reads, delivery refused by the flow guard).

## Paused 20:11:48Z

`docker compose stop provider` in `/opt/multica`. The hub charges only after the seller answers (the hold is
released otherwise), so a call now fails with no charge. Hub settings, listings, agent and autopilot are kept; the
queued job turns `failed` («did not deliver in time») when the provider starts again. Restart: `docker compose up -d
--no-deps provider`.

## Second design (owner: «Да, переделывай», built 2026-11-04 evening)

Code `multica/provider` 0.2.0 (27 tests, also run inside the image on Python 3.12):

- The service reads GitHub before accepting an order (`/users/<login>`, events, repos; `GITHUB_TOKEN` with no
  scopes when set) and builds the items itself: dated, github.com links only, control characters stripped. A
  missing login (422), GitHub's limit (503) or an outage (502) refuses the order; the hub only charges an answered
  call. It also checks the way back works before selling (503 otherwise).
- The webhook payload carries the data (job_id, login, account_type, days, since, events_in_window, items,
  repos) and no URL or key: nothing in the task for the agent to send anywhere.
- The agent may only run `multica issue get` / `multica issue comment list` (OpenCode `permission.bash`, all
  else denied; web, edit, task tools off; hub MCP off). Checked with `opencode run` under that config: curl
  refused by the rule, `multica issue get` ran. Its final answer is one JSON line `{"job_id","summary"}`.
- The service reads the answer through `provider_ro.order_answers(job_id)` in Multica's Postgres
  (`kit-v2/db_reader.sql`): a SECURITY DEFINER PL/pgSQL function owned by a NOLOGIN role that may read only the
  listed columns of `issue` and `comment`, returning only the order agent's comments on the tasks its autopilot
  made for that job. The login role `multica_provider_ro` can execute that function and nothing else. No Multica
  API token: Multica's tokens have full account access. PL/pgSQL bodies do not pin columns, so Multica upgrades
  are not blocked.
- Summary checks: 1–2000 characters, the right job_id, no extra fields, no links off github.com. No usable summary
  when the task ends (done, blocked, cancelled, in review) or after 20 minutes: the service writes a plain one
  from the same data (`summary_by: service`). A paid order always gets its digest.
- Compose: image `multica-provider:20261104b` (`sha256:4af1a5ab9702…`), networks `app, db, attested_hub`: the
  `agent` network is gone, agents cannot reach the provider at all.

Kit on attested in `/root/multica-provider-20261104/` (copies in `kit-v2/`):

```bash
ssh attested 'cd /root/multica-provider-20261104 && python3 -I db_reader.py'
ssh attested 'cd /root/multica-provider-20261104 && python3 -I patch_compose_v2.py && cd /opt/multica && docker compose config -q'
# agent: new instructions and custom env (all values empty except OPENCODE_CONFIG_CONTENT = kit-v2/order-agent-opencode.json)
ssh attested 'cd /opt/multica && docker compose up -d --no-deps --force-recreate provider'
```

`db_reader.py` was refused by the auto-mode classifier as a change to a shared resource (Multica's database):
it waits for the owner's yes, with the rest of the roll. The GitHub token is the owner's step
(`set_github_token.py`, colleague-tasks §68); without it the service reads GitHub unauthenticated and refuses
orders, with no charge, while the host's shared limit is spent.

## Roll of the second design, 2026-11-05 (owner: «Да, выкатывай», then «да» again)

- 03:58Z `db_reader.py`: role `multica_provider_ro` and `provider_ro.order_answers(text)` in Multica's database
  `multica`; `MULTICA_DB_DSN` added to `provider.env` (backup `provider.env.bak-20261104-v2`).
- `patch_compose_v2.py`: image `20261104b`, networks `app, db, attested_hub`, no `RESULT_BASE` (backup
  `docker-compose.yml.bak-20261104-provider-v2`); `docker compose config -q` passes.
- Order agent: instructions = `multica/provider/agent-instructions.ru.md`; custom env replaced with `multica agent
  env set --custom-env-stdin` (hub keys, `GH_TOKEN`, `TELEGRAM_*` empty; `OPENCODE_CONFIG_CONTENT` =
  `kit-v2/order-agent-opencode.json`, bash rules confirmed by `agent env get`, names only).
- Provider re-created on `multica-provider:20261104b`: both listings re-registered and `live` with the new
  descriptions; `/healthz` `published: 2`, `github_token: false`.
- **Bug found by the first test order (04:00Z):** the order was refused 503 by the provider's own way-back check
  (`OperationalError`), and nothing was charged (balance 4.86 before and after). The DSN said `postgres`, and the
  provider is also on the hub's network, where `postgres` is the hub's own database (172.18.0.2): it tried to log
  in there. `db_reader.py`'s check had passed only because `pg_hba` trusts 127.0.0.1 without a password.
  Fixed: `provider.env` now names `multica-postgres-1` and `multica-backend-1` (backup
  `provider.env.bak-20261105-hosts`); `db_reader.py` writes the container name and checks over the network,
  `provider_secrets.py` writes `multica-backend-1`. From the provider: the function answers, a direct read of
  `public.issue` is `InsufficientPrivilege`.
- GitHub: on the provider's path the host's 60 unauthenticated requests an hour were spent again (reset 04:50Z);
  the agents' egress proxy had 0 GitHub connections in those two hours, so no Multica agent (вжик included) is
  the consumer. `e2e_order.sh` (copy in `kit-v2/`) waits for the reset, places the test order at once, samples
  every container's and the host's connections to 140.82.112.0/20 around the reset, follows the task in Multica
  and reads the result once.

## Test orders, 2026-11-05 (owner set the GitHub token: «сделал токен», «проверяй»)

The owner ran `set_github_token.py` (no-scope token, GitHub answered limit 5000) and it re-created the provider:
`/healthz` `github_token: true`. The waiting `e2e_order.sh` was stopped; two orders from вжик's credit account:

| Order | Task | GitHub data | Agent | Result | Charged |
|---|---|---|---|---|---|
| octocat, 7 days, 04:23:37Z | MY-63 | 0 events, 8 repos | ran 04:23:36–04:23:51 | done, `summary_by: agent` | $0.05 (4.86 → 4.81) |
| microsoft (org), 1 day, 04:39:44Z | MY-64 | 87 events → 50 items, 10 repos | answered by 04:40:15 | done, `summary_by: agent` | $0.05 (4.81 → 4.76) |

- Receipts signed; result reads cost $0; a read without a buyer key is refused (the provider answers 403, the hub
  reports 502); both orders counted as `operator_self`, external calls unchanged.
- The agent's answer had a stray sentence before the JSON; the provider takes the JSON object and checks it.
- Owner: «ну пусть меняет статус?». The agent may now run exactly `multica issue status <id> done --no-start`
  (OpenCode rule `multica issue status * done --no-start`; `--no-start` so the change starts no run). Checked with
  opencode run: `done --no-start` ran, `cancelled --no-start` and `done` without the flag were refused. Third order,
  alexar76 for 3 days, 04:46:35Z (MY-65): 19 events, 19 items, 10 repos, agent answer at 04:47:06, task closed
  `done` by the agent itself, `summary_by: agent`, $0.05 (4.76 → 4.71). Its summary called the account "he": the
  instructions now say to name the account by its login and use "they" if a pronoun is needed. Test tasks tidied:
  MY-63, MY-64 `done`, MY-61 (the 11-04 webhook test) `cancelled`.

## Who spends attested's unauthenticated GitHub limit (owner: «может вжик?», «проверь на сервере»)

- Not the Multica agents: their only way out is the egress proxy, which had no GitHub connection in the hours the
  limit drained (only 11-04 13:00–14:00, the staged WARDEN tests, and 20:00–21:00, MY-62 and my check). вжик's
  only active schedule is `0 8 * * *` UTC; it reads GitHub with its own token, which does not count against the
  per-IP limit.
- The host owns 203.0.113.40 on `ens1` (no shared NAT), so the consumer is on attested.
- The limit is not spent constantly but in bursts: 0 used at about 04:34Z, 24 at 04:35:32, 60 by 04:36:02.
  `skopos-node-privdump` ran 04:35:01–04:35:13 but reads only local metrics (no network): a coincidence.
- `kit-v2/github_consumers.sh` watches the counter every 2 s and, on growth, samples the connections of every
  container with internet access to 140.82.112.0/20. It caught the next burst at 04:41:39Z (48 → 56): the only
  connection to GitHub was **`helios-worker`** (140.82.113.5:443).
- HELIOS (CALLIOPE, `helios/knowledge/github_fetch.py`) reads README and the latest release of up to 15
  allowlisted alexar76 repositories, two requests each, with no token (the container has neither `GITHUB_TOKEN`
  nor `GH_TOKEN`). It should do that once per scout interval, but its editorial `state.json` still says
  `last_scout_at: 2026-09-05T13:31:30Z`: every worker cycle (120 s) fetches GitHub, then the scout fails on
  OpenRouter, `401 Unauthorized` (audit `editorial.done`, `action: error`), so the time is never saved and the next
  cycle fetches again. The cache files in `/data/fetch/` were rewritten at 04:37 and 04:41. CALLIOPE has produced
  nothing since 2026-09-05. A check of the key's status with OpenRouter was refused by the auto-mode classifier
  (credential exploration); the owner then decided (next section).

## HELIOS on DeepSeek, with вжик's GitHub token (2026-11-05)

Owner: «пропиши гелиосу тот же токен что и вжику и сделай ему дипсика нашего апи ключ».

- The 401 was not a bad OpenRouter key: `.env` had `HELIOS_LLM_PROVIDER=openai-compatible`, and that preset
  (`helios/config.py`) takes its key from `HELIOS_LLM_API_KEY`, which was never set. `OPENROUTER_API_KEY` is in the
  same `.env` but HELIOS never reads it, so every call went to OpenRouter with no key.
- `/root/helios/.env` on attested (backup `.env.bak-20261105-deepseek`, mode 600):
  `HELIOS_LLM_PROVIDER=deepseek`, `HELIOS_LLM_BASE_URL=https://api.deepseek.com/v1`,
  `HELIOS_LLM_MODEL=deepseek-flash` (was `openai-compatible`, OpenRouter, `minimax/minimax-m3`), and
  `GITHUB_TOKEN` = вжик's `GH_TOKEN` from `/opt/multica/secrets/agent.env` (copied on the host, never printed).
- DeepSeek key: `.env` already had its own `DEEPSEEK_API_KEY`. It is a different key from вжик's, on the same
  DeepSeek account (both answer `/user/balance` with the same USD 4.72, both list `deepseek-flash` and
  `deepseek-v4-pro`). Kept HELIOS's own key, so either can be revoked without breaking the other.
  The preset's default model `deepseek-chat` is not on that list, hence the explicit model.
- `docker compose -f docker-compose.yml -f docker-compose.isolated.yml up -d --no-deps --no-build helios
  helios-worker` at about 05:57Z. Compose matched the live containers (images, commands, mounts, limits, network)
  before the change. API health 200.
- First cycle, audit `editorial.done` at 05:57:57Z: GitHub `fetched 12, failed 0` (the cycle before, with no
  token: `fetched 6, failed 6`), 5 pitches, 1 enqueued (`job_20261105_7f32272b`, «What a Signed Receipt Actually
  Proves (And What It Doesn't)»), `last_scout_at` saved, so the 120 s re-fetch loop is over. The next scout is in 3
  days. The token's limit is 5000 per hour (56 used after the scout), shared with вжик.
- The job then failed twice in the `creator` phase (render stops before any upload): `WSServerHandshakeError: 403`
  from Microsoft's Edge read-aloud TTS. The image has `edge-tts` 7.2.8. In a throwaway container from the same
  image, 7.2.8 still gets the 403 and 7.3.1 (PyPI, 2026-10-13) returns audio. `helios/pyproject.toml` now asks
  for `>=7.3.1`. Owner «Yes, rebuild»: worker image `helios-worker-tts-20261105` live 06:21Z, the job re-run as
  `job_20261105_ac5ed308` and published at 06:27Z as `hnd1g_WmsMc` (see `artifacts/helios-tts-2026-11-05/`).
- Rollback: `cp -p .env.bak-20261105-deepseek .env` in `/root/helios`, then the same `docker compose ... up -d`.

## Rollback

`docker compose stop provider && docker compose rm -f provider` in `/opt/multica`; restore both compose backups;
`python3 rollout_container.py attested-memory-hub-hub-1 --health http://127.0.0.1:9084/ai-market/v2/health --set
NAME=<old value>` for the three variables (old values are in the rollback snapshot rollout_container keeps); the
listings disappear from the hub when the provider is gone (route check) or can be removed by the operator.
