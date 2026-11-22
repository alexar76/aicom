# Factory: no API key preview in the router's debug log — production, 2026-11-22

Host factory-vps, container `aicom-app-1`. Times are UTC from the host clock. Owner: «убери строку с ключом из лога тоже».

## What changed

The running `llm/router.py` (older than main) wrote the first 8 characters of each enabled provider's `api_key` in a
`logger.debug` line at config load. Main has logged only whether a key is configured since `febbc9fe2`. The image now
carries the running file with that one hunk (`keylog.patch`):

    logger.debug(f"Provider '{name}': api_key_configured={bool(api_key_val)}, api_key_env={has_env!r}")

The line was debug level and the factory logs at INFO: `docker logs aicom-app-1` held 0 lines with `api_key=` before
the change. Nothing in the repository changes (main already has this form).

router.py sha256: before `b4a861a9…` (the router-select fix of 06:57Z), after `87649c77…`.

## Image

`aicom-security:aicom-app-1-router-keylog-20261122` = `sha256:80160e8ec22c43cdd90db0b6830db6cd31ffb1333775f89e62e136fe1558dd89`,
`FROM aicom-security:aicom-app-1-owner-routing-v1` (`sha256:0824b7d4…`) + `llm/router.py` (`Dockerfile`).

`owner-routing-v1` is another session's image (07:10Z, admin sign-in / users / OIDC, 13 files listed in
`/root/aicom-owner-routing-v1.biqQn9/candidate.sha256`), itself `FROM` the router-select image. That session activated
it at 07:15Z by copying its files into the running container and pinned it in compose at 07:16Z, without recreating
the container.

## What went wrong on the way, and how it was put right

- 12:03:10Z first switch, to an image built `FROM` router-select. Recreating the container dropped the files the
  owner-routing activation had copied into it: from 12:03 to 12:09:54Z the factory ran the image versions of those 13
  files (for example `web/backend/api/admin/auth.py` `a027c2a3…` instead of `c625b60c…`). The compose pin had changed
  to `owner-routing-v1` after the 06:57Z rollout; I found it only when writing the pin.
- 12:09:36–12:09:54Z second switch, to the image above (`FROM owner-routing-v1`). Re-tagging had left the first
  image's ID unresolvable (containerd snapshotter), so `rollout_container.py` (copy in the host folder) reads the old
  image's config from `ROLLOUT_OLD_IMAGE_CONFIG`, a rebuild of the same Dockerfile with the same Env / Entrypoint /
  Cmd / ports. The switch and health checks passed; the last step (re-creating the previous container without its
  Compose labels) failed on the same lookup, so the previous container — the 12:03 one, created by this session, in
  the reverted state — was removed with `docker rm`. Its inspect snapshot stays in
  `/root/security-rollbacks/aicom-app-1-1795349376614220196/`.

## Checks (after 12:10Z)

- In the image, no network: the 13 owner-routing files match `candidate.sha256` (13/13); `check.py` from the
  router-select record: architecture_design → deepseek_api, auto / unloaded / no rule → openrouter_api.
- Running: healthy, 0 restarts; `/api/health` 200, frontend `/` 200, `/admin/login` 200; `pipeline_worker`,
  `director.worker` and uvicorn on the new image; `llm/router.py` `87649c77…`, `routes_providers.py` `12148be5…`
  (the routing-save fix) as before. New log errors: none (a Reddit 403 in discovery, a frontend ECONNREFUSED while the
  backend started).
- No Factory build was running: the director was in discovery analysis only.
- `docker-compose.host-docker.yml` names the new image and `/root/claudecode/aicom/llm/router.py` is the new file,
  both written in place (the folder keeps its immutable flag). `aicom-factory-guard-repair`: "factory tree whole;
  every container bound to it".

## Rollback

On factory-vps, from `/root/factory-router-keylog-20261122`:

    ROLLOUT_OLD_IMAGE_CONFIG=aicom-security:aicom-app-1-owner-routing-v1 python3 rollout_container.py aicom-app-1 --image aicom-security:aicom-app-1-owner-routing-v1 --health http://127.0.0.1:9081/api/health

then write `docker-compose.host-docker.yml.pre` back over `/root/claudecode/aicom/docker-compose.host-docker.yml` and
`router.py.before` over `/root/claudecode/aicom/llm/router.py`, in place. Rolling back to `owner-routing-v1` keeps the
owner-routing files and the router-select fix; only the key-preview line returns.
