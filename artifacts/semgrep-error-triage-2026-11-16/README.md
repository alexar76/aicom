# Semgrep ERROR findings on main, triaged (2026-11-16)

Owner, 11-16: «Semgrep выдаёт ещё 537 предупреждений, 52 из них серьёзные… — разбери».

Run: Semgrep 1.185.0, the push gate's rule sets (p/python, p/javascript, p/typescript, p/owasp-top-ten) and excludes,
`--severity ERROR`, over `git archive` of aicom main 14af764e8. 52 findings (`semgrep-errors-14af764e8.json`), the same
count as the earlier backlog. Every finding was read in code; for Dockerfiles, the running containers on factory-vps,
attested, admin-vps, competing-lab and pingblip were listed with `docker inspect` (user), read-only. indep runs no Docker.

## Real (fix)

| # | Where | Rule | Why it is real | Severity | Fix |
|---|---|---|---|---|---|
| 1 | `argus/src/economy/keystore.ts` 230, 256, 383 | gcm-no-tag-length | `setAuthTag(file.tag)` takes the tag from the keystore file with no length check; Node accepts 4–16-byte GCM tags, so a rewritten file with a short tag weakens forgery resistance to 2^32. ARGUS is on npm and holds wallet keys | low | `createDecipheriv(..., { authTagLength: 16 })` |
| 2 | `domain-kit/src/store.js` 31 | gcm-no-tag-length | tag = `bytes.subarray(12, 28)`; a truncated row gives a short tag | low | same |
| 3 | `coach/.github/workflows/release.yml` 34, 65, 100, 135 | run-shell-injection | `${{ github.ref_name }}` is pasted into `run:` scripts; a tag name may hold `$(…)`. Only people who can push tags reach it | low | pass via `env:` and use `"$VERSION"` |
| 4 | `pingblip/world/Dockerfile`, `pingblip/memeforge/Dockerfile` | missing-user, missing-user-entrypoint | the public servers `pingblip-world-1` and `pingblip-forge-1` ran as root in prod (pingblip host). The first version of this record named world only; forge was in the root list too | medium (hardening) | non-root `USER node` + writable dirs chowned |

Side finding while reading (not a Semgrep rule): `web/backend/services/auto_publish.py` passes deploy tokens as
argv (`--token`, `--auth`), visible in the process list of the factory host. Low.

## Not real here (no change)

- **dangerous-subprocess-use-tainted-env-args (17):** list-form `subprocess` with values from the operator's own
  environment or config (binary paths, timeouts, tokens) in services and hand-run scripts: alien-monitor anvil start,
  DOLOS `forge`, factory-guard `rsync`, factory auto-publish and verify, relay-scout/seed/social-preview/courses/WARDEN
  research scripts. No outside input reaches them; no shell.
- **use-defused-xml-parse (4):** `ET.parse` of our own files (JUnit report, our sitemap.xml, our landing sitemap).
- **subprocess-shell-true (1):** `aimarket-playground/scripts/smoke_starters.py` runs commands from the playground's own
  starter catalogue in a temp dir.
- **missing-user / missing-user-entrypoint / last-user-is-root (21 of 22):** in prod these services run as a non-root
  user set by compose (oracles, WARDEN, aimarket-mcp, praxis, symmartys, gaia API …), or the image is not deployed
  (templates, `relay-scout-fix`, lottery contracts build). Root containers seen in prod are database and nginx images
  that drop privileges themselves, DinD/runner, and images not in this list.

Net: 52 → 4 real (5 files), all low except the PingBlip root containers.

## Fixed the same evening (owner: «Да, исправляй», and the argv tokens «тоже»)

1. ARGUS keystore: every AES-GCM cipher is created with `authTagLength: 16` (`GCM` constant). Two new tests (v1
   keystore, encrypted token) give a tag cut to 4 bytes: they fail on the old code (it decrypted) and pass now.
   ARGUS suite 593 passed, 10 skipped; typecheck clean. Not on npm until the next ARGUS release.
2. domain-kit store: same pin; a 4-byte tag is refused ("Invalid authentication tag length: 4"); suite 77/77.
   Not deployed (next domain-kit rollout).
3. coach release workflow: the tag name and env values reach the scripts as `$GITHUB_REF_NAME`, `$ARTIFACT_PREFIX`,
   `$APP_BUNDLE_NAME`, `$GITHUB_WORKSPACE` (pwsh: `$env:…`), never `${{ }}` inside `run:`. Semgrep: 4 → 0. Lands on
   GitHub with the next mirror sync (colleague).
4. PingBlip world + forge run as `node`. Dockerfiles changed in the repo. Prod: overlay images FROM the running ones
   (`aicom-seo:pingblip-world-5aa4bce94-nonroot-20261116` c5d4318a, `aicom-security:pingblip-forge-1-nonroot-20261116`
   edfd60d4), tested beside prod first (world: 6 pages same codes, route cache written as node; forge on a copy of its
   volume: migrate + seed + start, `/api/media/*.png` 200, previews and .next writable). Switched 2026-11-16
   20:08:09Z: volume `blip_forge-data` chowned to 1000:1000, compose image tags changed, `docker compose up -d --no-deps
   world forge`. After: both `user=node`, 0 restarts; world.pingblip.com, its og image, forge.pingblip.com, a forge
   preview PNG and pingblip.com answer 200; 0 permission errors in the logs. Kit and rollback on the pingblip host:
   `/root/pingblip-nonroot-20261116/switch.sh rollback` (compose backup `docker-compose.yml.pre`).
5. Factory auto-publish: Vercel and Netlify tokens go by env (`VERCEL_TOKEN`, `NETLIFY_AUTH_TOKEN`), not argv, in both
   the landing and the full-stack Vercel path. Checked on factory-vps that Vercel CLI 62.1.0 deploys with the env token
   alone (`vercel whoami` rc 0 with env only, rc 1 without). New test `test_deploy_tokens_go_by_env_not_argv` fails on
   the old code, passes now. Not deployed (next factory rollout).
