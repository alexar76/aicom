# Multica agent «недельный пост» on attested — 2026-11-04

Owner: «а потом сразу все остальные пункты» (idea 8). Times are server clocks (UTC).

- Files in `multica-daemon`: `/home/node/tools/weekly-post/{collect.mjs,run.sh}` (collect.mjs sha256/12
  `3e7fc20f332a`), uid 501, not writable by the agent.
- Agent `0e18e127-e95d-486b-828a-15bebbee195f` «недельный пост», deepseek/deepseek-flash, private, max 1 task;
  same custom env as the reviewer (hub MCP off, hub keys and GH_TOKEN empty); instructions =
  `multica/weekly-post/instructions.ru.md` (test-task rule added 16:03Z after MY-60).
- Autopilot `e8da8232-bcf0-4c8a-af29-6c6f8c2c1912`, trigger `d083bc54…` cron `0 11 * * 1` UTC, next 2026-11-09T11:00:00Z.
- Dry run with a throw-away state 16:01Z ok; first run MY-60 (manual trigger) wrote the first snapshot
  (`/home/node/.local/state/weekly-post/snapshots.json`) and a draft (one factual slip, see the use-case doc).

Rollback: delete the autopilot and the agent with the `multica` CLI; remove `/home/node/tools/weekly-post` through
the host volume path.
