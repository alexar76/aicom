# Agent Capital Exchange, never the acronym, in the hubs' public API — 2026-11-27

**Why.** The links sweep of 27 November (PromoMaterials/outreach/ecosystem-links-2026-11-27) found APIs.io listing
"ModelMarket Acex Capital API" (https://apis.io/providers/modelmarket-dev). The source was our own public OpenAPI
(`/openapi.json` on every hub):
- the tag `acex-capital` on the ten `/api/v2/capital/*` routes;
- "Capability revenue indices for Pulse Terminal (ACEX Phase 2)";
- "Float a product as an ACEX CapShares listing (Agent IPO)".

Owner rule of 2026-11-15: public texts say "Agent Capital Exchange", never the acronym; ids stay. The 11-15 clean-up
missed the API. Owner: «делай».

## Change (hub 3.22.5)

- `hub_routes/capital.py`:
  - tag `capital`;
  - the pricing route's description;
  - the 503 body "the Agent Capital Exchange {ledger} ledger is not available on this hub".
- `api_models.py`: `IpoRequest` description.
- `capital_pricing.py`: the 503 body when the `acex` package is absent. That is the answer on pip-installed hubs
  (Attested, Independent).
- Docstrings and section comments in these files and `auto_listing.py`.
- Unchanged: URL paths, operationIds, `acex_*` modules, the `acex` package, `ACEX_*` env names, log lines.
- Version 3.22.5 (pyproject, `__init__`, server.json); 3.22.4 is on PyPI. Not released to PyPI.
- Test `tests/test_public_text_capital.py`: no "acex" in any case anywhere in /openapi.json; the routes still exist
  under the tag `capital`. It fails on main before the change, which finds "ACEX Phase 2" and the tag.
- Full suite: 4429 passed. The 2 failures are the known ones, present since 3.22.0:
  - `test_mandates_hardening::TestJobTree::test_each_receipt_commits_to_its_own_children_by_their_receipt_ids`;
  - `test_pipeline_provider::test_free_graph_needs_no_wallet_and_returns_one_sub1_tree`.

## Kit (`kit/`, on each host `/root/hub-capitaltext-20261127`)

The six hubs run six different images: Tutu, HALOWERK, capsfix and mcp0728 overlays. So the kit does not copy files.
`patch_text.py` makes the eight replacements in the running image's own code and refuses unless each one matches
exactly once. `probe.sh` ran it with `--check` in all five containers and the Independent venv: all matched.

`build.sh` builds `<running image>-capitaltext-20261127` FROM the running image (Dockerfile: `USER root`, patch,
`compileall`, back to the image's user). It then checks the image in a throw-away container: `--network none`, as
root, PATH/PYTHONPATH only (the image's own settings belong to the live hub). The check builds the app on a temporary
SQLite file and asserts that /openapi.json has 0 "acex" and the tag `capital`. Two retries were needed:
- the image settings (empty `AIMARKET_ROUTING_FEE_BPS`, data paths) broke the first check;
- the apex image carries an old root-owned `/app/data/channels.db` from 8 November.

`roll.sh` = database backup + `rollout_container.py` (restores the previous container if health fails).
`apex_roll.sh` waits for a publisher payout run to finish, checks that only `themis` shares the hub's network
namespace, then rolls. `indep.sh` = copy of the running mcp0728 venv, patched, drop-in 99l.

## Per hub (server UTC)

| hub | switched | previous container (rollback) | database backup |
|---|---|---|---|
| hub.modelmarket.dev (canary), competing-lab `modelmarket-hub` | 14:04:30Z | `modelmarket-hub-security-prev-1795788270667209694` | `/root/hub-backups/modelmarket-hub-pre-capitaltext-20261127T140430Z.db` |
| hunt.modelmarket.dev, competing-lab `signal-hunt-hub-1` | 14:04:55Z | `signal-hunt-hub-1-security-prev-1795788296222860427` | `/root/hub-backups/signal-hunt-hub-1-pre-capitaltext-20261127T140455Z.dump` |
| uni.modelmarket.dev, factory-vps `modelmarket-hub-uni` | 14:04:55Z | `modelmarket-hub-uni-security-prev-1795788297782471760` | `/root/hub-backups/modelmarket-hub-uni-pre-capitaltext-20261127T140455Z.db` |
| hub.attestedmemory.net, attested `attested-memory-hub-hub-1` | 14:04:56Z | `attested-memory-hub-hub-1-security-prev-1795788297511249597` | `/root/hub-backups/attested-memory-hub-hub-1-pre-capitaltext-20261127T140456Z.dump` |
| modelmarket.dev, factory-vps `modelmarket-hub` (+ THEMIS); after a payout run, borrowers = themis | 14:05:51Z | `modelmarket-hub-security-prev-1795788352255356486` (themis: `themis-security-prev-1795788352255356486`) | `/root/hub-backups/modelmarket-hub-pre-capitaltext-20261127T140551Z.db` |
| independentai.network/hub, indep `independentai-hub.service` | 14:07:23Z | `./indep.sh rollback` (drop-in 99l → back to mcp0728 via 99k) | `/var/backups/independentai/hub-pre-capitaltext-20261127T140723Z.dump` |

Container rollback: `cd /root/hub-capitaltext-20261127 && python3 rollout_container.py <container> --rollback`. For
modelmarket-hub, roll back only right after a payout run, as `apex_roll.sh` does. No migration, so the old images run
on the same database.

## Checks after (from outside, 14:07Z)

- All six: health 200, /openapi.json with 0 "acex" in any case, tag `capital`, the IPO routes present, `IpoRequest`
  described as an Agent Capital Exchange listing.
- `/api/v2/capital/pricing`:
  - modelmarket.dev, hub.modelmarket.dev, uni: 200;
  - Attested, Independent: 503 "Agent Capital Exchange pricing is unavailable…", as designed for pip-installed hubs.
- hunt.modelmarket.dev/openapi.json is the Signal Hunt app's own (14 paths, 0 "acex"). That hub's API on the host
  (127.0.0.1:9084) has 177 paths, 0 "acex" and the tag `capital`.
- The payout job's next run after the apex roll: 14:06:53Z, success. modelmarket-hub and themis: 0 restarts, healthy.

APIs.io re-reads the OpenAPI on its own schedule; its page still says "Acex Capital API" until then.
