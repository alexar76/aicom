# HISTOR handshake fallback, live on admin-vps — 2026-11-01 08:44–08:45Z

Owner: «Да, выкатывай». Code: aicom 2cf275902, one file, `histor/mcpclient.py` (sha256 0e42ea4e3d18…). It
replaces 46abbd51efe7…, which is what the running container and the host tree held: main before the fix. The why
is in `../scraperwatch-xcheck-2026-11-01/README.md`.

## How

`histor_handshake_overlay.sh`, run on admin-vps as root from `/root/histor-handshake-20261101/`:

1. **Guards.** The running image must be `aicom-security:histor-histor-1-hc-live-20261031` (86ebc0124063), and the
   running `mcpclient.py` must have the old sha. The script stops if an OS rollout is running.
2. **Overlay.** `FROM` the running image, `COPY mcpclient.py`. This keeps the security session's OS patches, the
   baked env and the WARDEN build. The new image is `aicom-security:histor-histor-1-hs-20261101` (503fc8da820c).
3. **Checks inside the image:**
   - the file sha;
   - the MOMUS release gate: passed, receipt 20261101T050101, build 3b6b074c…;
   - `smoke.py`: five legacy refusals fall back once on a mock transport, while a modern error and a 429 still
     stop;
   - four live endpoints read `ok`: kaiku 203 tools, quotewise 21, civai 6, marx.finance 12;
   - imports.
4. **Swap.** Back up the compose file and the host-tree file, rewrite the compose `image:` line, then
   `compose up -d --no-deps --no-build histor`. If `/health` does not come up, the script rolls back by itself.
5. **After the swap.** Install the file into `/opt/histor/histor/` and run
   `skopos-warden-quality rebind 503fc8da820c`, which also sets the `histor:warden-remediation-base` tag. Then
   restart the crawl that the redeploy interrupted.

Log: `rollout.log`. Dockerfile: `Dockerfile`. The file itself is `git show 2cf275902:histor/histor/mcpclient.py`.

## Verified (08:45–08:47Z)

- **Container.** `histor-histor-1` runs `aicom-security:histor-histor-1-hs-20261101` (503fc8da820c), started at
  08:44:57Z. The container and the host tree both hold mcpclient 0e42ea4e3d18. The compose line is rewritten.
  `/var/lib/momus-quality/live-image.json` points at 503fc8da820c.
- **Health.** `/health` returns ok with `crawl_running: true`, and the public `https://histor.modelmarket.dev/health`
  returns 200. The log has no traceback and no client error.
- **Remote reads, compared hour by hour:**

  | | Reads | `ok` | `protocol` | 401/403 |
  |---|---:|---:|---:|---:|
  | The hour before | 9,514 | 9,400 | 7 | 74 |
  | The first 90 s after | 172 | 171 | 0 | 1 |

  Of the 171 `ok` reads after the swap, 145 used a legacy protocol version. The hour before shows few errors
  because the failing targets were in backoff, not being read.

**Recovery of the lost servers.** 2,195 remote targets read `ok` on 10-28 and had no `ok` read from 10-30 until the
deploy. Their retry delays expire on the existing schedule:
- 12 by 12:00Z;
- 722 by 18:00Z;
- all of them by 2026-11-02 08:41Z.

A 401/403 waits at least a day, and other failures back off 6 h → 12 h → 24 h. None of them is nudged; the
schedule is untouched. To re-check, run `after2.sql` from the cross-check folder: the `ok_since_deploy` column
should approach 2,195.

## Rollback

```bash
cp /root/histor-backups/docker-compose.postgres.yml-pre-hs-20261101 /opt/histor/docker-compose.postgres.yml
install -m 0644 /root/histor-backups/mcpclient.py-pre-hs-20261101 /opt/histor/histor/mcpclient.py
cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
  up -d --no-deps --no-build histor
/usr/local/sbin/skopos-warden-quality rebind sha256:86ebc012406364d4a57d48259d34125436a843881ec4653aa294f577a9a4d670
docker image tag aicom-security:histor-histor-1-hc-live-20261031 histor:warden-remediation-base
```

No schema change, so no database step.
