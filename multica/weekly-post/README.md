# Weekly build-in-public post (Multica agent)

The deterministic half of the Multica agent «недельный пост» on attested (Mondays 11:00 UTC): public hub counters
(`/ai-market/v2/stats/live` of modelmarket.dev and hub.attestedmemory.net) compared with last week's snapshot, and
our Multica agents' tasks of the last 7 days with each agent's last answer (read with the `multica` CLI). The model
writes an owner summary, a DEV.to draft and a short X post from `week.json` and pastes `facts.md` unchanged.
Nothing is published by the agent. Description: `docs/multica-use-cases.ru.md`, section 6.

- `collect.mjs` — the collector (Node 22, no dependencies); `run.sh` downloads the counters and runs it; state in
  `~/.local/state/weekly-post/snapshots.json`.
- `instructions.ru.md` — the agent's instructions as set in Multica.
- `collect.test.mjs` — `node --test multica/weekly-post/collect.test.mjs`.
