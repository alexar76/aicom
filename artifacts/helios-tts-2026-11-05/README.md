# HELIOS worker with edge-tts 7.3.1 — 2026-11-05

Owner: «Yes, rebuild» (rebuild the worker image with edge-tts 7.3.1 and rerun the job). Times are attested's clock (UTC).

## Why

After HELIOS moved to DeepSeek (see `artifacts/multica-provider-2026-11-04/README.md`, «HELIOS on DeepSeek»), the
first CALLIOPE job `job_20261105_7f32272b` failed twice before upload: Microsoft's Edge read-aloud service answers
`WSServerHandshakeError: 403` to `edge-tts` 7.2.8, the version in `aicom-security:helios-worker-hc-live-20261031`.
In a throwaway container from that image, 7.3.1 (PyPI, 2026-10-13) returned audio.

## Files (= `/root/helios-tts-20261105/` on attested)

- `Dockerfile`: `FROM aicom-security:helios-worker-hc-live-20261031`, `pip install edge-tts==7.3.1` as root,
  back to `USER helios`; the build prints the `pip freeze` diff. Diff: only `edge-tts 7.2.8 → 7.3.1`.
- `smoke.py`: inside the new image, edge-tts is 7.3.1, a short synthesis returns audio (18,000 bytes), `helios
  --help` works. Passed.
- `build.sh`: builds `aicom-security:helios-worker-tts-20261105` (sha256:9e9624b99486…) and runs the smoke.

## Rollout

- `/root/helios/docker-compose.isolated.yml` (backup `docker-compose.isolated.yml.bak-20261105-tts`): the
  `helios-worker` image line now names `helios-worker-tts-20261105`. `docker compose -f docker-compose.yml -f
  docker-compose.isolated.yml up -d --no-deps --no-build helios-worker` at 06:21:27Z. The API container `helios`
  is unchanged (`helios-hc-live-20261031`; it does not render).
- The failed job was put back through HELIOS's own `QueueStore.enqueue` with the same template, vars, YouTube
  metadata, script and idempotency key (a failed job does not block its key): `job_20261105_ac5ed308`, audit
  `job.enqueued` with `rerun_of`.
- 06:23:32Z first render: `NoAudioReceived` from edge-tts (one empty answer); the worker's normal retry at
  06:26:16Z rendered (`render.done` 06:27:11Z, 60 s, 6.2 MB, with subtitles), uploaded private 06:27:18Z as
  `hnd1g_WmsMc`, and auto-approve (`HELIOS_AUTO_APPROVE=1`) made it public 06:27:19Z.
- Public check: YouTube oEmbed 200, «What a Signed Receipt Actually Proves (And What It Doesn't) | AIMarket Hub
  #Shorts», channel `@My-AI-Factory`.

## Rollback

```bash
ssh attested 'cd /root/helios && cp -p docker-compose.isolated.yml.bak-20261105-tts docker-compose.isolated.yml && docker compose -f docker-compose.yml -f docker-compose.isolated.yml up -d --no-deps --no-build helios-worker'
```

The old image brings the 403 back. To hide the video: `docker exec helios-worker helios unpublish job_20261105_ac5ed308`.

## Still open

The next image built from the repository gets 7.3.1 through `helios/pyproject.toml` (`edge-tts>=7.3.1`). Once
renders work, CALLIOPE publishes with no manual check: at most one video per scout, a scout every 3 days, a quota of
4 per week, `max_uploads_per_day: 9`.
