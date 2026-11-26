# Federated entries expire 48 hours after the last verified read — six hubs, 2026-11-26

**Why.** Roberto Pioli on dawn@ietf.org (thread on draft-king-dawn-requirements-02, 2026-11-26) proposed REQ-PROP-6:
Discovery Information held from another source must not be returned as valid beyond its validity. He cited our
96-entries case and noted, correctly, that our index kept a peer's entries with no limit when a read failed
(`crawler.py` `_prune_unlisted` replaces them only after a verified read). Owner: «Да, сначала хаб», «делай все в
лучшем виде потом пишем ответ».

**Live case found before the change.** Four of the six hubs (hub.modelmarket.dev, hunt, modelmarket.dev,
independentai.network) still served 4 entries of `https://x402-gateway-production-1f21.up.railway.app`, whose catalogue
they last verified on 2026-10-31 (17:24–18:01Z). That host answers 404 on `/.well-known/ai-market.json`,
`/ai-market/v2/manifest` and `/.well-known/agent-marketplace`; every crawl since then failed and kept the rows. The peer
itself stays in the peer list and on the map (external nodes rule); only its entries stop being served, and they come
back with its next verifiable catalogue.

## Change (main 91b373a10, hub 3.22.2)

- `config.py`: `federated_max_unverified_s` / `AIMARKET_FEDERATED_MAX_UNVERIFIED_S`, default 172800 (48 h), 0 = off.
- `database.py`: every read of `capabilities` (get, find, list, diverse browse, search, counts) serves a peer row only
  while `updated_at` (set on each upsert, i.e. each verified read) is within the bound: `_SERVABLE`. Local rows are
  never bounded. `include_unverified=True` for housekeeping. `expire_unverified_federated()` deletes the rest. The
  cutoff is a UTC `YYYY-MM-DD HH:MM:SS` string formatted by hand (`datetime.strftime` goes through `time.strftime`,
  which a test patches); it compares correctly with SQLite `datetime('now')` and with PostgreSQL's TEXT `NOW()` values
  (`2026-11-26 16:42:18.964979+00`, server time zone UTC, checked on hunt).
- `crawler.py`: `_prune_unlisted` also sees rows past the bound; the end of every crawl deletes expired rows
  (`stats["expired_unverified"]`).
- `realm.py`: UNI's eviction of outside peers also deletes rows past the bound.
- Tests: `tests/test_crawler.py::TestUnverifiedPeerRowsExpire` (5; all fail on the previous code). Docs:
  `docs/ecosystem-autodiscovery.md`. Federation draft -02 (unsubmitted): Privacy bounds the kept entries.

## Kit (`kit/`, on each host `/root/hub-fedvalid-20261126`)

All six hubs ran the same four files before (hashes: config `e2f0eec359c0`, crawler `51757ad16355`, database
`cf228b3f01a9`, realm `6ff2fc43d197`). Three equal main; `config.py` is main's except the federation judge's default
model (`minimax/minimax-m3` live, `qwen/qwen4-max` in main; the hubs set it through env). So the kit's `config.py` is
the LIVE file plus this change only, and the other three are main's. `build.sh` refuses a container whose four files
differ from those hashes and builds `<image>-fedvalid-20261126` FROM the running image. `roll.sh` = database backup +
`rollout_container.py` (restores the previous container when a health URL fails). `indep.sh` for Independent (copy of
the running venv with the four files, drop-in `99i-hub-fedvalid-20261126.conf`). `postcheck.py`: what the bound serves
and hides, read-only.

Read-only smoke before the switch, new code against the live databases: hunt (PostgreSQL), hub.modelmarket.dev
(SQLite) and Independent (PostgreSQL, as the service user) each hide exactly the railway peer's 4 entries.

## Per hub (2026-11-26, server UTC)

| hub | host, unit | switched | image (rollback = previous container) | database backup | after |
|---|---|---|---|---|---|
| hub.modelmarket.dev (canary) | competing-lab `modelmarket-hub` | 17:05:32Z | `modelmarket-hub:tutu-find-20261124-fedvalid-20261126`; prev `modelmarket-hub-security-prev-1795712733373331377` | `/root/hub-backups/modelmarket-hub-pre-fedvalid-20261126T170532Z.db` | healthy; first crawl deleted the 4 railway rows (336 stored, 0 railway) |
| hunt.modelmarket.dev | competing-lab `signal-hunt-hub-1` | 17:06:42Z | `signal-hunt-hub:3.22.0-capsfix-20261122-fedvalid-20261126`; prev `signal-hunt-hub-1-security-prev-1795712803330653500` | `/root/hub-backups/signal-hunt-hub-1-pre-fedvalid-20261126T170642Z.dump` | healthy; railway 4 hidden |
| uni.modelmarket.dev | factory-vps `modelmarket-hub-uni` | 17:07:26Z | `modelmarket-hub-uni:3.22.0-20261121-fedvalid-20261126`; prev `modelmarket-hub-uni-security-prev-1795712848269388248` | `/root/hub-backups/modelmarket-hub-uni-pre-fedvalid-20261126T170726Z.db` | healthy; nothing hidden |
| modelmarket.dev | factory-vps `modelmarket-hub` (+ THEMIS) | 17:08:11Z, right after a payout run, borrowers = themis only | `modelmarket-hub:tutu-federated-probems-20261125-fedvalid-20261126`; prev `modelmarket-hub-security-prev-1795712892029825536` | `/root/hub-backups/modelmarket-hub-pre-fedvalid-20261126T170811Z.db` | hub + THEMIS healthy (9083, 9460); railway 4 hidden |
| hub.attestedmemory.net | attested `attested-memory-hub-hub-1` | 17:09:17Z | `attested-memory-hub:3.22.0-capsfix-20261122-fedvalid-20261126`; prev `attested-memory-hub-hub-1-security-prev-1795712958864397892` | `/root/hub-backups/attested-memory-hub-hub-1-pre-fedvalid-20261126T170917Z.dump` | healthy; nothing hidden |
| independentai.network/hub | indep `independentai-hub.service` | 17:09:42Z | venv `hub-3.22.0-fedvalid-20261126` via drop-in `99i-hub-fedvalid-20261126.conf`; rollback `./indep.sh rollback` | `/var/backups/independentai/hub-pre-fedvalid-20261126T170942Z.dump` | active; railway 4 hidden |

Every roll: `rollout_container.py --dry-run` first (no env names dropped; borrowers only `themis` on the apex). No
schema change, so a rollback needs nothing in the databases. Rollback of a container hub:
`cd /root/hub-fedvalid-20261126 && python3 rollout_container.py <container> --rollback`.

From outside, 17:10–17:12Z: `/ai-market/v2/search?intent=&limit=0` on all six returns 0 railway rows (319, 288, 92, 319,
292 and 318 rows). The railway peer stays in the apex peer list (`active`, last_crawl 2026-10-31T17:24:24Z). Hubs
whose crawl has not run yet still store the rows (not served); their next crawl deletes them.
