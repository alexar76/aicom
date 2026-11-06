# Multica 0.5.3 → 0.8.0 on attested — 2026-11-05

Owner: «Yes, upgrade». Times are attested's clock (UTC).

## What 0.8.0 changes for us (release notes 0.5.4–0.8.0 and source)

- 63 database migrations (547 → 610).
- Statuses follow workflows ("Default" included). The keys our rules use did not change (`done`, `cancelled`,
  `blocked`, `in_review`).
- **OpenCode over ACP.** For OpenCode 1.15 and later, the daemon drives `opencode acp` instead of
  `opencode run --format json --dangerously-skip-permissions`, unless `MULTICA_OPENCODE_TRANSPORT=run`
  (`server/pkg/agent/opencode_acp.go`). WARDEN and the agents' permission rules were tested on the run transport, so we
  keep it. ACP can be tested separately later.
- Task tokens addressed to another workspace are refused (MUL-8138).
- Checked along the way: `--dangerously-skip-permissions` in OpenCode 1.18.32 only answers "allow once" to rules that
  would ask (`cli/cmd/run.ts`). Explicit `deny` rules never ask, so they hold in Multica's runs. This was true on 0.5.3
  too.

## Rehearsal on a copy (15:29–15:31Z)

- Backup: `pg_dump -Fc` → `/root/multica-upgrade-20261105/multica-pre080.dump` (11.9 MB, 121 tables with data, 69
  tasks), mode 600.
- Stand on an `--internal` network: a postgres from the same image, restored with `--no-owner --no-privileges`, and
  `ghcr.io/multica-ai/multica-backend:v0.8.0` with the live backend's settings and its own database. The settings file
  was root-only and shredded afterwards. The migrations ran (547 → 610) and the server started.
- On the migrated copy:
  - `provider_ro.order_answers` columns are all present, and MY-66's answer reads back;
  - status values are unchanged;
  - with CLI 0.8.0 (release binary, checksum OK), `issue get` keeps `assignee_type` and `assignee_id`;
  - `order-task`: its own task is read, another agent's task is refused (exit 3), and its own task is closed
    (`in_review → done`);
  - every CLI command the kit uses exists;
  - the autopilot webhook created a task assigned to the order agent, from the order autopilot, with the JSON payload
    in the description, and the function found it by `job_id`.
- The stand was removed afterwards (containers, network, settings file).

## Production (15:33–15:36Z)

- No active tasks; the alerter had nothing open.
- Backups: `docker-compose.yml.bak-20261105-v080` and `.env.bak-20261105-v080`.
- New images:
  - backend: `ghcr.io/multica-ai/multica-backend:v0.8.0`;
  - web: `ghcr.io/multica-ai/multica-web:v0.8.0`;
  - daemon: `multica-daemon:080-20261105` = `aicom-security:multica-daemon-hc-live-20261031` with only
    `/usr/local/bin/multica` replaced by the 0.8.0 binary (`daemon-Dockerfile`). OpenCode 1.18.32, WARDEN, tools,
    entrypoint, user and healthcheck are unchanged.

  The daemon environment gains `MULTICA_OPENCODE_TRANSPORT: run`. `.env`: `MULTICA_IMAGE_TAG=v0.8.0`,
  `MULTICA_CLI_VERSION=0.8.0`. Postgres and the nginx gateway are unchanged.
- Order: daemon stopped → backend (migrations 547 → 610, server started) → web → daemon.
- Checks:
  - the daemon is online; all five agents are on the same runtime, now displayed as "Opencode (attested)";
  - `MULTICA_OPENCODE_TRANSPORT=run`, and the guard loads from `/opt/opencode-guard`;
  - the UI through the gateway answers 200;
  - the provider's function works on the live database.
- **Test order MY-70** (octocat, 1 day, $0.05): the agent's answer came 31 s after the order, `summary_by: agent`.
  The only tool calls were `order-task get <uuid>` and `order-task done <uuid>`, and the task is `done`. WARDEN wrote
  its state for the session.

## Rollback

0.8.0's migrations only go forward. To roll back:
1. Stop backend, web and daemon.
2. Restore `multica-pre080.dump` into a fresh database (`pg_restore --clean --if-exists`, or drop and recreate
   `multica` first).
3. Restore the two backups and run `docker compose up -d --no-deps --no-build backend frontend daemon`.

Tasks and comments written after 15:33Z would be lost.

## Not covered yet

- The scheduled runs (вжик 08:00, shopper 09:00, reviewer 10:00 UTC; weekly post on Mondays 11:00) first run on 0.8.0
  on 2026-11-06.
- The new images are upstream builds, not the security session's OS-hardened rebuilds of 2026-10-31.
