# HISTOR GET /check: rollout 2026-11-09

What changed (aicom 16fcc741c):

- `GET /api/v1/check?endpoint=` (or `url=`, `package=`, `name=`, optional `toolSetDigest=`) returns the same
  signed answer as the POST.
  - It writes nothing: no contribution and no unlisted-host count.
  - It shares the POST's limits and is sent with `Cache-Control: no-store`.
- A browser that names no server is redirected (303) to the form at `/check`.
- A POST with `url` and no `endpoint` is read as the endpoint.
- The 400 for a missing server shows a POST and a GET example.
- The landing's "Use it" block adds the GET line.

Why: between 2026-10-27 and 11-08 every outside GET of `/api/v1/check` got 405.
- homouniversalis.ai's own bot (`HomoUniversalis-Keeper/1.5`) asked `?url=` about its endpoint. Its site shows the
  HISTOR badge.
- The author of api.awesomevideoeditor.com tried `?url=` and `?endpoint=`. Two POSTs then got 400 before three
  went through.
- People followed a link from PyPI to `/api/v1/check`.

## Live

- Host admin-vps, container `histor-histor-1`, compose `/opt/histor/docker-compose.postgres.yml`.
- Live since **2026-11-09 19:35:10Z** on `aicom-security:histor-histor-1-chk-20261109`
  = `sha256:aebc6a48bb1236df05e8c37cdb661857a39b49fd8ba9493c5c20a92daf25da73`.
  - MOMUS binding re-bound to it; the MOMUS release gate passed (`20261109T032941`).
  - Tagged `histor:warden-remediation-base`.
- Built FROM the running `aicom-security:histor-histor-1-wd-20261108` (`sha256:2bd30900…c3491a`).
- Overlay: `/app/histor/app.py`, `/app/histor/check.py`, `/app/docs/landing/index.html`.
  - Before the build, the live and host copies of all three equalled the commit's parent b546dee95, so the staged
    files are the commit's own; there was no merge.
- Unchanged: `MALLOC_ARENA_MAX=2` and the 1.5 GiB limit.
  - The previous container had run since 2026-11-08 10:36Z with 0 restarts, through the 11-08 crawl.
- The daily crawl was running and was restarted by the script.
- Candidate smoke (`stage/check_get_smoke.py`) ran on a disposable SQLite DB with `--network none` and checked:
  - GET with `url=` and `endpoint=`, a signed answer and `no-store`, with nothing written;
  - the 303 for a browser and the 400 with an example;
  - a POST with `url`, counted once;
  - the CORS preflight, `/health`, `/api/v1/stats`, and the `/check` page carrying the GET example.
- Production checks in the script, all passed:
  - GET for a listed server answers with that server;
  - a browser is redirected to the form;
  - `noDigest` in the servers API;
  - tile 0/000 is 8,192 bytes.
- Backup: `/root/histor-backups/chk-20261109.7ndQagRt` (compose file + the three previous host files).
- Kit on the host: `/root/histor-chk-20261109/`. Log: `rollout.log`.

## Verified live (from outside, through nginx, 19:36Z)

- `GET /api/v1/check?url=https://homouniversalis.ai/mcp`, the request their bot sent on 11-08: 200,
  `histor.check/v1`, signed, `target.page` …/s/4604b80f59f25096, `cache-control: no-store`, CORS `*`.
- `GET …?endpoint=https://api.awesomevideoeditor.com/mcp`: 200, target 2cbe93f509e7fb60.
- `GET /api/v1/check` with `Accept: text/html`: 303 to https://histor.modelmarket.dev/check.
- Without it: 400 `send endpoint, package or name, for example POST {…} or GET /api/v1/check?endpoint=…`.
- `POST {"url": …}`: 200, read as the endpoint.
- `/health` ok, 0.6.2, crawl running.

A GET without a digest answers `match: "no-digest"` ("you sent no digest"). That is the documented answer for a
lookup; `observed` and `target` carry what HISTOR holds.

## Rollback

On admin-vps as root:

```
cd /opt/histor
B=/root/histor-backups/chk-20261109.7ndQagRt
cp -p "$B/docker-compose.postgres.yml" docker-compose.postgres.yml
for f in histor/app.py histor/check.py docs/landing/index.html; do cp -p "$B/$f" "$f"; done
docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-deps --no-build histor
/usr/local/sbin/skopos-warden-quality rebind sha256:2bd3090011aa43b8cd65c8352c3712f349126f5b43e5d7c84328ecc32bc3491a
docker image tag aicom-security:histor-histor-1-wd-20261108 histor:warden-remediation-base
```

Nothing to undo in the database: GET writes nothing, and a POST with `url` stores what a POST with `endpoint`
stored before.
