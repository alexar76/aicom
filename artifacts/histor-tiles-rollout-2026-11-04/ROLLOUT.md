# HISTOR log as c2sp.org/tlog-tiles — rollout 2026-11-04

HISTOR's label log now also serves as a tiled transparency log (c2sp.org/tlog-tiles) under
`https://histor.modelmarket.dev/log/`. That address is `https://` plus the checkpoint origin
`histor.modelmarket.dev/log`. A witness or monitor that found the log in a witness-network list can
follow it with nothing but the C2SP specifications. Code: aicom histor 0.6.2 (commit a72667d74,
`histor/tiles.py`, routes in `histor/app.py`, spec §4.5 in `histor/docs/spec/transparency-log.md`).

| Path | Content |
|---|---|
| `/log/checkpoint` | the latest signed checkpoint, same body as `/checkpoint` (text/plain; charset=utf-8, no-cache) |
| `/log/tile/<L>/<N>[.p/<W>]` | Merkle tree tiles from the stored `log_nodes` (application/octet-stream, immutable) |
| `/log/tile/entries/<N>[.p/<W>]` | entry bundles: each label's JCS form with a uint16 length prefix, each hashed against its leaf before it is served |

`GET /api/v1/issuer` names the prefix: `checkpoint.tiles = {"format": "c2sp.org/tlog-tiles", "prefix": "https://histor.modelmarket.dev/log/"}`.

## Live

- Host: admin-vps, container `histor-histor-1`, compose `/opt/histor/docker-compose.postgres.yml`.
- Live since 2026-11-04 10:52:09Z on image `aicom-security:histor-histor-1-tiles-20261104`
  = `sha256:7dba8eba51a6daed4c176e00eba5f2452c3624628982544ce72fe74cdaa92d09`. The MOMUS binding was
  re-bound to that image, and the image was tagged `histor:warden-remediation-base`.
- Built FROM the running image `aicom-security:histor-histor-1-hreflang-20261104`
  (`sha256:a51f79b4cbaf895773fb9f2d0bc1a1469e06d29eac3376a0e25a57b57f8ba91c`). The overlay replaces
  `/app/histor/app.py` (base sha256 checked: `9c74333…d4ae3`) and adds `/app/histor/tiles.py`.
- The MOMUS release gate passed (`20261104T032752`). The candidate smoke ran on a disposable SQLite DB
  with `--network none` and checked: checkpoint, full/partial/level-1 tiles, entry bundle, root rebuilt
  from tiles, 404s, health and the issuer prefix.
- Backup: `/root/histor-backups/tiles-20261104.CldwEqvn` (compose file + previous `histor/app.py`).
- Kit on the host: `/root/histor-tiles-20261104/` (`rollout.sh`, `stage/`, both logs).

## First attempt (aborted before the switch, production untouched)

The candidate smoke got a 404 on `/log/checkpoint` (`rollout-attempt1.log`). The image carries the
older histor 0.5.1 wheel in site-packages. The overlay lives in `/app/histor`, and production imports
it from there because it starts `python -m histor serve` in `/app`. The smoke script was started as
`python /tmp/tiles_smoke.py`, which put `/tmp` first on `sys.path` and imported the old wheel instead.
Fix:

- the smoke now runs with `PYTHONPATH=/app`, as production imports;
- the smoke first asserts that `histor.__file__` is under `/app/histor/`.

The second run (`rollout.log`) went through.

## Verified live (2026-11-04 ~11:13Z, from outside, through nginx)

- `tilescheck/` is an independent Go checker built on golang.org/x/mod/sumdb/tlog and note, the Go
  checksum database's packages. It shares no code with HISTOR. Its output:

  ```
  $ tilescheck https://histor.modelmarket.dev/log/ histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU 1597824
  checkpoint histor.modelmarket.dev/log size 1598156, log signature verified by histor.modelmarket.dev/log
  root rebuilt from 3 tiles equals the signed root
  consistency proof 1597824 -> 1598156 verified (8 hashes)
  7 entries of the first bundle proven included in the signed tree
  ```

- `checkpoint-1598141.txt` is the head the witnesses co-signed in the 11:10 push. It was checked with
  `../histor-witness-listing-2026-11-04/verify_checkpoint.py`: the log signature and the Markovian,
  ring-any-bells and stagemole cosignatures are all valid (4 signatures). Heads signed between two
  10-minute pushes carry only the log signature. That was already the case before this change.
- Single responses:

  | Request | Status | Size |
  |---|---|---|
  | `/log/tile/0/000` | 200 | 8,192 bytes |
  | `/log/tile/2/000.p/24` | 200 | 768 bytes |
  | `/log/tile/entries/000` | 200 | 606,625 bytes |
  | `/log/tile/2/000` | 404 | full level-2 tile does not exist yet |
  | `/log/tile/0/00` | 404 | not canonical |

## Rollback

On admin-vps as root:

```
cd /opt/histor
cp -p /root/histor-backups/tiles-20261104.CldwEqvn/docker-compose.postgres.yml docker-compose.postgres.yml
cp -p /root/histor-backups/tiles-20261104.CldwEqvn/histor/app.py histor/app.py
rm -f histor/tiles.py
docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-deps --no-build histor
/usr/local/sbin/skopos-warden-quality rebind sha256:a51f79b4cbaf895773fb9f2d0bc1a1469e06d29eac3376a0e25a57b57f8ba91c
docker image tag aicom-security:histor-histor-1-hreflang-20261104 histor:warden-remediation-base
```

The witness push (`histor-witness-push.timer`) does not depend on the tiles and keeps working either way.
