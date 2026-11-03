# Figures for the Glama article (2026-11-02)

The figures behind PromoMaterials/outreach/glama-blog-2026-11-02/brief.md. They come from the public HISTOR snapshots
2026-11-02 and 2026-10-20 (https://histor.modelmarket.dev/datasets/). Each file was checked against the SHA-256 in
the snapshot's signed manifest.json before counting.

Two publishers are counted apart, because they would set any share on their own:
- `gateway.pipeworx.io`: 1,916 entries. Its router tool's description carries a live tool count, so every count
  change moves all entries at once: 14,573 changes, 27.4% of the 11-02 snapshot.
- `agent-observatory-sensor.nolimit-observatory.workers.dev`: 2,365 near-identical entries of 31 tools. All 2,317
  of its changes were on 2026-09-24.

```bash
# DIR holds servers.jsonl.gz, changes.jsonl.gz, extras_changes.jsonl.gz (11-02) and toolsets.jsonl.gz (1 GB)
python3 figures.py DIR figures-1102.json          # kinds, pins, versions, day-one remote cohort, with and without the two
python3 figures2.py DIR figures2-1102.json        # per-entry pin misses, schema-only edits, description edit sizes, annotations
python3 figures.py DIR_1020 figures-1020.json     # the 10-20 snapshot (no extras file there)
python3 cohort_by_host.py DIR                     # needs duckdb: the day-one remote cohort by entry and by host
python3 tokens.py DIR tokens-1102.json            # needs tiktoken; o200k tokens per tool set (not kept here: 3 MB)
python3 token_figures.py DIR tokens-1102.json token-figures-1102.json
```

For the share of remote servers that changed, leaving publishers out is not enough. A third publisher, with 1,108
entries in the 10-20 cohort, changed 6 of them. Dropping the sensor publisher alone gives 30.4%, which undercounts.
So the cohort is counted by host, each publisher's domain once (cohort-by-host-*.json):

| Snapshot | Entries changed | Hosts changed | Single-entry hosts changed |
|---|---:|---:|---:|
| 2026-10-20 (four weeks) | 4,926 / 10,929 (45.1%) | 2,489 / 6,822 (36.5%) | 2,420 / 6,674 (36.3%) |
| 2026-11-02 (39 days) | 5,920 / 11,836 (50.0%) | 2,976 / 7,213 (41.3%) | 2,896 / 7,056 (41.0%) |

The change-level shares in figures*.json (kinds, pins, versions, tokens) leave the two publishers out. The
1,108-entry publisher made 6 changes, too few to move them.

Definitions:
- A **schema pin** is a pin over tool names and input schemas. It fires when a tool is added or removed, or when
  any input-schema path moves. It misses a change when neither happens.
- An **escalation** is a tool that stops saying `readOnlyHint: true` or starts saying `destructiveHint: true`.
  It is checked against the before/after annotation values, not only against the snapshot's `escalations` list.
  420 of the listed tools were removed or had no annotation diff, and are not counted.
- The **steering-word** count is a heuristic regex (see figures2.py), not a classifier.

The scripts use the standard library except tokens.py; figures.py and figures2.py import histor/scripts/change_kinds.py.
