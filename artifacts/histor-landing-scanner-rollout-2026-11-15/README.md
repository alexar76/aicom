# HISTOR prod: landing cadence text + scanner line-split fix (2026-11-15)

Owner: «выкати новый образ HISTOR с исправленной главной».

## What runs now

`histor-histor:landing-scanner-20261115` = `sha256:f2660c5fcbb4c3fbdaa5fc0058f66a8c8910d17ae29b5473854bc5b1c19a5d51`,
live since 2026-11-15 17:46:39Z (server clock). Built FROM the previous live image `histor-histor:warden-0.27.0b-prod`
(`sha256:8dcade5371f4…`, WARDEN 0.27.0 build 403842d7). WARDEN is untouched. A hash list of every file in both
images differs in exactly these 7 files (plus the per-container `/etc/hostname`, `/etc/hosts`):

| File | Change | main |
|---|---|---|
| `/app/docs/landing/index.html`, `assets/i18n/{es,fr,ru,zh}.js` | the "What HISTOR does" card says "every six hours (every 30 minutes for a week once its tools have changed twice)", not "every day". Only those five lines; the rest of main's newer landing (desk.js, CSS, journey.js) is NOT shipped | bdad2a0ab |
| `/app/histor/scanner.py`, `/app/histor/digest_xcheck.py` | split JSON lines on `"\n"`, not `str.splitlines()`; a line that is not JSON is a `ScannerError` | 8f9e78965, 4f72b71e6 |

Each image file equalled main before the change, so the fixed files are main's.

## The scanner fault found during the rollout

From 08:27Z (first remote poll after the 06:34Z switch to WARDEN 0.27.0) the live log had `remote polling failed …
JSONDecodeError: Unterminated string`. WARDEN 0.27.0 quotes the matched clause; Node's `JSON.stringify` leaves
U+2028/U+2029 raw inside strings; Python's `str.splitlines()` breaks there. The `JSONDecodeError` was not a
`ScannerError`, so the crawler's job-by-job retry did not run and the whole poll failed before `_settle`:
observations were stored, labels and change records for that batch were not. Those servers are settled at their next
read (changes recorded with a later time).

Remote runs from the `runs` table (kind `remote`):

| Window (UTC) | Runs | With error | With scan labels |
|---|---|---|---|
| 06:35–08:27 | 456 | 0 | 456 |
| 08:27–17:39 (fault) | 1,406 | 241 | 1,201 |
| from 17:46:30 (final image), checked 17:53 | 27 | 0 | 26 |

No over-reading: in the fault window at most 18 reads per server in 9 h (= the 30-minute cadence).

## Checks

- Public `/` and the four i18n files serve the new text (checked 17:40Z); no SRI or CSP hashes reference them.
- `histor-histor-1` healthy, 0 restarts; 0 `remote polling failed` and 0 batch retries after 17:46:30Z.
- MOMUS (admin-vps): image copied with `docker save | docker load` (same ID), `skopos-warden-quality rebind
  sha256:f2660c5f…`; `live-image.json` names `f2660c5f…` with build 403842d7. `/.well-known/aicom-histor-runtime.json`
  names `f2660c5f…`.
- `warden/scripts/check-quality-gate.mjs` on the npm 0.27.0 package: "MOMUS release gate passed: 20261115T062632,
  403842d7…". (Run on the main checkout it says "not passed": that `dist/` is a stale local build, 40483094.)
- HISTOR suite on main 4f72b71e6: 1600 tests, 0 failures.

## Rollback

1. HISTOR host: `bash /root/histor-landing-scanner-20261115/switch.sh rollback` (restores the compose override to
   `warden-0.27.0b-prod` from `docker-compose.warden-image.yml.pre` and waits for healthy).
2. admin-vps: `/usr/local/sbin/skopos-warden-quality rebind sha256:8dcade5371f42e4c16b5bcf5b04a083e15505b7b4a6aca8b53b454bbf1a83dee`
   (the old binding is saved at `/root/histor-landing-scanner-20261115/live-image.json.pre`).

Rolling back brings the scanner fault back. The first build of this kit (`sha256:4bd2790a…`, without the
`ScannerError` change) ran 17:39–17:46Z and is tagged `landing-scanner-20261115-first` on the HISTOR host.
