# HESTIA: `handler_sha256` on the roster and the agent catalogue at `/agents/` — rollout 2026-11-22 (LIVE 07:29Z)

Owner 22.11: «Yes, publish it» (the full catalogue on the hearth, with `handler_sha256` on the roster), then
«Что ещё не сделано: - делай». Code: aicom main a0b44813a (HESTIA + hestia-agents), 5a47f524f (Alien Monitor),
5f2c92588 (hub strip link); records for the monitor and the hub are in `alien-hestia-catalogue-2026-11-22` and
`hub-hestia-catalogue-link-2026-11-22`.

## What changed on the hearth

- `/v1/hearth` gives `handler_sha256` for every sandbox agent: the SHA-256 of the handler file (Python or
  JavaScript) that every call hands the sandbox. Cached by the file's stat, dropped on every deploy, so a redeploy
  at the same size within the file system's timestamp resolution still shows the new digest (a test makes the
  stamps equal on purpose).
- `/agents/` serves `docs/agents/`, built by `hestia-agents/scripts/build_catalog.py`: five-language pages, each
  agent's purpose, reachable hosts, sandbox and egress limits (read from the HESTIA source), handler source and
  digest, tests and recorded replies, `catalog.json`, `SHA256SUMS`, `live.js`. Sources, tests and Markdown are
  `text/plain`; `/agents` → 308 `/agents/`; no directory listing; `live.js` writes roster values with
  `textContent` only (an owner's label is that owner's text).
- `live.js` compares every published digest with the roster when the page opens, and lists the agents whose code
  the catalogue does not publish (other owners', and the operator's `base-gas`).
- Published recordings: e-mail addresses (npm's publisher and maintainer fields, contacts in recorded agent cards) and local build
  paths (npm `_resolved`/`_from` of a package packed from a folder) are replaced by a marker, counted per file in
  `catalog.json` (`removed_from_recorded_data`: 38 addresses, 6 paths in three files). The tests run on the
  unedited files. Scanned before publishing: none of our server addresses, no hostnames of our hosts, no tokens
  or keys; the IPv4 literals left are public resolvers and third-party SPF/NS answers inside recorded DNS replies.
- Landing: "Agents" in both navigations and "Agent catalogue: code and digests" in the footer, five languages.

## Checks before

- hestia 836 passed (7 new); hestia-agents 1230 passed, 17 failed = the known environment failures
  (sandbox-lint tests without HESTIA's dependencies, the WARDEN bundle-version test); `test_catalog.py` 13 (the
  committed catalogue is byte-for-byte what the script builds; every handler published byte-for-byte with its
  digest; SHA256SUMS covers every source, test and document; every page links only to published files; the live
  check has its words in five languages; no address or local path left in published recordings).
- Before building: all 29 handlers stored on the hearth were byte-equal to the repository (sha256 of
  `/data/tenants/*/handler.*` against `handler_source()`).
- Open alerts: disk of pingblip (8 h) and of histor-vps (3 h); none on competing-lab or factory-vps.
- The live hearth's `/app/hestia` matched the unpaid-warning kit's manifest; only `app_routes/discovery.py` and
  `runtime/wasm.py` differ in this overlay. Prod Starlette 1.10.0 (local 1.6.0): the candidate check covers it.
- Candidate, offline (`--network none`, from `/app`, `PYTHONPATH=/app` — the wheel in site-packages is the old
  code): `/agents` 308, `/agents/` HTML with `live.js`, 29 agents served `text/plain` with matching digests,
  `live.js` as JavaScript, the landing links `/agents/`, an encoded `../` is 404, `/health` ok.

## Switch (overlay FROM the running image)

| container | switched (UTC) | new image | previous (rollback) |
|---|---|---|---|
| hestia-hestia-1 | 07:29:28–07:29:31 | `aicom-security:hestia-hearth-catalogue-20261122` = 0de5b8893bc2 | `hestia-hestia-1-security-prev-1795332568880248025` (49d5114aad9c) |

The runner is unchanged. Ledger dump `/root/hestia-backups/hestia-pg-pre-catalogue-20261122T072928Z.sql.gz`
(9 tables, like the previous dump). Kit on the host: `/root/hestia-catalogue-rollout-20261122` (`overlay/` there is
`git archive a0b44813a` of `hestia/hestia`, `hestia/docs/agents` and the landing page). Rollback:

    cd /root/hestia-catalogue-rollout-20261122 && python3 rollout_container.py hestia-hestia-1 --rollback

## After

- Healthy, 0 restarts, no traceback. Roster: 33 running, all 33 with `handler_sha256`; the 29 catalogued agents
  all equal to `catalog.json`. `x402-preflight` answers signed in 1.5 s; a priced agent (`json-canonical`) still
  answers 402 with its terms.
- From outside: `/agents/` and `index.zh.html` text/html, `live.js` text/javascript, `SHA256SUMS`, `src/*.py`,
  `tests/*.py` text/plain; `src/x402-preflight.py` hashes to the roster's digest (699cac9d…); the landing links it;
  an encoded `../` is refused (400 at nginx).
- Browser, `https://hestia.modelmarket.dev/agents/index.ru.html`: «Все 29 агентов выполняют ровно опубликованный
  код — сверено со списком агентов Гестии только что», 29 rows "тот же код", four other agents listed
  (attested-claim-weigh and attested-contradiction-scan of Attested Memory, base-gas of the operator,
  blackwell-storefront of an open-signup owner); no failed request. Phone width: no horizontal scroll (the facts
  grid and the live line were fixed for it before the build).
- Host tree `/root/claudecode/aicom/hestia` synced to main without deleting anything (11 files changed or added
  plus `docs/agents/`; a dry run showed no file the host has and main lacks); guard snapshot taken right after.
