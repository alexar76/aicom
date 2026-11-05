# WARDEN 0.23.0 release preparation

Prepared locally on 2026-11-04 with Node.js 22.22.1 on macOS, from branch `claude/multika-agent-ecosystem-2db731`
(Gitea PR #11). This directory records checks of the exact npm archive described in `artifact.json`.
**Not on npm yet.** MOMUS passed this build and production HISTOR runs it since 2026-11-04 15:21Z; the release
gate passes (`quality-after.log`). Left: the owner's `npm publish` and the mirror (section "Release steps").

## What 0.23.0 ships that npm 0.22.4 does not

- **Flow guard for OpenCode** — `@aimarket/warden/opencode` (`dist/opencode-plugin.js`), `docs/opencode.md`, loader
  `opencode-plugin/warden.js`. OpenCode plugin hooks drive the same per-session checks as the Claude Code plugin, for
  agents that run unattended. `block: "data"` (default) refuses every call that involves data or a sensitive payload
  and lets action-only calls run with a log line; `block: "all"` refuses everything the interactive hook would ask
  about. `shell.env` blanks listed keys for shell commands. Subagents share the root session's state. A failed
  record refuses the rest of the session tree.
- Core (also in the Claude Code plugin copies): `flowPre` reports reason and sensitivity through an optional fourth
  argument (hook output unchanged); Telegram bot tokens and AIMarket hub keys are secrets; OpenCode's `auth.json` and
  Multica's `config.json` are secret paths; OpenCode config and plugin folders are protected; a canonical UUID is a
  record id — no personal-data token, dropped from private-text fingerprints except on a line that names a
  credential.
- Ruleset unchanged: v17 `sha256-UOfK25xo6D8vrKEVfNFBTBVn5OspyaZut9vC9Z9Q5JE=`.
- Version pins move to 0.23.0 in the READMEs (five languages), scan, flow-guard and teams guides, the Claude plugin,
  `action.yml`'s default, `.pre-commit-hooks.yaml`, `server.json`, `CITATION.cff`, the landing page and the
  GitHub-org example. Test count 1,418 in the badge, READMEs and landing page. `examples/scan-demo` scanned with this
  build prints exactly the block in `README.md`.
- Live before release: the plugin runs on the Multica agents on attested since 2026-11-04 13:05Z
  (`artifacts/warden-opencode-2026-11-04/README.md`); checked by code against the Vulnetix classes
  (`artifacts/vulnetix-check-2026-11-04/REPORT.ru.md`).

## Checks (all passed except the release gate)

| Check | Result | File |
|---|---|---|
| TypeScript typecheck | clean | `typecheck.log` |
| Test suite | 1,418 tests in 59 files, 0 failures | `tests.log` |
| Red team (interactive hook) | 28 scenarios, 0 attacks delivered | `redteam.log` |
| Red team through the OpenCode adapter | `all` 0 of 28; `data` 3 of 28, all three action-only (listed in `docs/opencode.md`) | `redteam-opencode.log` |
| Ruleset | local v17 `sha256-UOfK25xo…`; 0.23.0 not on the registry yet | `ruleset.log` |
| `npm pack` | 351 files, 955,569 bytes, sha256 `833841f2…`, build digest `7f31b219…` (equal to `check-quality-gate.mjs` on the build and on the unpacked archive) | `pack.json`, `pack.log`, `artifact.json` |
| Archive vs npm 0.22.4 | +6 paths (`dist/opencode-plugin.*`, `docs/opencode.md`, `opencode-plugin/warden.js`), none removed; compiled JS differs only in `flow-guard`, `-fingerprints`, `-paths`, `-post`, `-pre`; source maps differ in `mappings` only (build environment); `package.json` differs in `version`, `exports`, `files`; no runtime dependencies | `package-diff.txt` |
| Clean consumer | offline install without scripts; `scan` exit 0; MCP `initialize` reports 0.23.0; `--help` exit 0; state dir untouched; `@aimarket/warden/opencode` resolves, its six hooks run, `shell.env` blanks a key, a call after outside text runs (`data`), the send after a credential read is refused; published 0.22.4 has no `./opencode` export (`ERR_PACKAGE_PATH_NOT_EXPORTED`) | `clean-consumer.json`, `clean-consumer.log` |
| MOMUS release gate | blocked at preparation: `This exact WARDEN build has not passed` | `quality.log` |

The control is `../warden-release-0.22.4-2026-11-01/aimarket-warden-0.22.4.tgz` (SHA-1 `73c82c1b…`, the registry's
`dist.shasum`). The native macOS sources are unchanged since 0.22.4, so the Swift suite was not rerun.
Reproduce the consumer check with `node docs/evidence/warden-release-0.23.0-2026-11-04/clean-consumer-check.mjs`.

## Release steps (owner: «Да, запускай» for the MOMUS run, 2026-11-04)

1. **Candidate — passed.** `quality/stage-candidate.py` built `aicom-security:histor-histor-1-wd-20261104`
   (`sha256:3fce01b3…`) on admin-vps from the running HISTOR image `tiles-20261104` (`sha256:7dba8eba…`, WARDEN
   0.22.4) with the vendored WARDEN replaced by this archive and `/opt/warden-source/src` by `git archive` of
   `2f0dd7dd2` (64 files, `quality/warden-src-2f0dd7dd2.tar`). Before anything ran it: the installed build digests to
   `7f31b219…`, `describe` reports 0.23.0 with the rules of 0.22.4 unchanged, the poisoned probe scans byte-identical
   to the base image (3 matches), HISTOR's code and migrations (21) untouched (`quality/artifact-manifest.json`,
   `quality/image-build.log`). `skopos-warden-quality candidate` ran 15:10–15:18Z, exit 0; the signed receipt
   (`quality/candidate-signed.json`): status passed, full; development 8,244 attacks and 362 benign, 0 missed, 0
   false positives; held-out 24 attacks and 24 benign, 0 missed, 0 false positives; 17 discovery candidates passed.
   `authorize` accepts the image.
2. **Production HISTOR — done (owner: «Да, переключай»).** `quality/histor_warden_0230_overlay.sh` ran
   15:20:53–15:21:04Z (`quality/rollout.log`): `authorize` accepted `3fce01b3…`, HISTOR recreated on
   `aicom-security:histor-histor-1-wd-20261104`, health ok, the sidecar reports WARDEN 0.23.0, `live` published run
   `20261104T151013` for build `7f31b219…` with source commit `2f0dd7dd2` (`quality/latest-signed.json`), and
   `histor:warden-remediation-base` now names the image. No crawl was running, so none was restarted.
   `npm run check:quality`: `MOMUS release gate passed: 20261104T151013, 7f31b219…` (`quality-after.log`).
   Rollback: the commands at the top of the overlay script (compose backup
   `/root/histor-backups/docker-compose.postgres.yml-pre-wd-20261104`, then `live` on `sha256:7dba8eba…`).
3. **npm publish** by the owner: `scripts/publish_warden.sh` (or `npm publish ./aimarket-warden-0.23.0.tgz` from this
   directory), then compare `npm view @aimarket/warden@0.23.0 dist.shasum` with `e9fe195e…`.
4. **Mirror** `alexar76/warden` synced by the colleague (GitHub is not written from here).
