# HISTOR subregistry onto production, second kit (2026-11-21)

The first kit (`../histor-subregistry-rollout-2026-11-20`) was built on `signed-fingerprints-20261119` and skipped:
production moved to WARDEN 0.32.0, 0.33.0, the cosigned checkpoint and WARDEN 0.35.0 first. This kit is built on the
image production runs since 2026-11-21 10:11:43Z.

| | |
|---|---|
| Base | `histor-histor:warden-0.35.0-prod` = `sha256:ef3e5cb4b31278cc91d1d88c72fa3f3ed1aac8cd533280b09f4d6129c8f68903` (WARDEN 0.35.0, MOMUS live) |
| Image | `histor-histor:subregistry-20261121` = `sha256:02011e75cf644c5164126f6ea03503d627787586203c6b3f1d87675b0e50fd65`, built on the HISTOR host 2026-11-21 |
| Files | `ctx/app.py`, `config.py`, `service.py`, `migrations.py`: the base image's own files with only the subregistry hunks of `933d203b9` applied (6, 17, 22, 23 changed lines, the same counts as that commit; the `app.py` mount hunk placed by hand before `@app.get("/api/v1/servers")`, its context had moved). `subregistry.py` as in main. `ctx.sha256` pins them |
| Migration | 026 (`registry_entries`), as in main; the base image has 025 as its last. Rollback SQL and its rehearsal on Postgres: first kit |
| Switch | `switch.sh`: image line → this image, `HISTOR_SUBREGISTRY: "1"` in the override, `docker compose config -q`, up, healthy. `switch.sh rollback` stops HISTOR, drops the table, restores the override, starts the base |
| MOMUS | WARDEN is the base image's, so after either direction: `skopos-warden-quality rebind <running image digest>` on admin-vps |

## Result (owner «Yes, switch now», 2026-11-21)

- 10:27:10Z the WARDEN 0.35.0 waiter wrote its 15-minute line (healthy, 0 tracebacks); no crawl open; schema at 25.
- 10:27:59Z `switch.sh`: `histor-histor-1` healthy on `sha256:02011e75…`, schema 26; the override names the image and
  `HISTOR_SUBREGISTRY: "1"` (`switch.log` on the host).
- MOMUS: the first `skopos-warden-quality rebind sha256:02011e75…` refused with `RuntimeError` — the tool reads the
  image on admin-vps, and it had been built only on the HISTOR host (`docker create` failed). Image copied
  (`docker save | docker load`, same ID); 10:29:43Z rebind accepted (exit 0). WARDEN build unchanged (`9106a6d8…`).
- From outside: `/`, `/health`, `/api/v1/stats`, `/api/v1/fingerprints?package=npm:@aimarket/warden`,
  `/api/v1/log/checkpoint/cosigned`, `/api/v1/subregistry`, `/v0.1/servers?limit=1` answer 200; `OPTIONS
  /v0.1/servers` gives `Access-Control-Allow-Origin: *`, `Allow-Methods: GET, OPTIONS`, `Allow-Headers:
  Authorization, Content-Type`. `/v0.1/servers/io.github.alexar76%2Fwarden/versions/latest` answers WARDEN 0.35.0 with
  `_meta["dev.modelmarket.histor/observed"]` (target `npm:@aimarket/warden`, 9 tools, last observed 2026-11-20 20:28Z).
- The first copy of the registry is slower than the local test (4 min 22 s): 5,300 entries at 10:29Z, 64,299 at
  10:44Z, 65,799 at 10:46Z.
- First copy finished 10:47:41Z (started 10:28:06Z, about 19.5 minutes): full walk, 695 pages, 69,484 read, 69,483
  stored, 1 skipped, 0 filtered, 0 gone; table `registry_entries` 84 MB; disk 84 %. Container healthy, 0 restarts, no
  traceback in the hour. Hourly `updated_since` syncs and a weekly full walk follow.
- 30 entries picked at random from the first 800 of the list: `server` and the official `_meta` equal to the
  official registry's `versions/latest` for all 30.
- Rollback: HISTOR host `/root/histor-subregistry-20261121/switch.sh rollback`, then admin-vps
  `skopos-warden-quality rebind sha256:ef3e5cb4b31278cc91d1d88c72fa3f3ed1aac8cd533280b09f4d6129c8f68903`.
- `histor/docker-compose.yml` in main passes the five `HISTOR_SUBREGISTRY*` settings (default off).
