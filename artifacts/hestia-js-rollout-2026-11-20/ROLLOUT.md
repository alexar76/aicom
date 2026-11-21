# HESTIA runs JavaScript agents — rollout 2026-11-20

Owner 20.11: «Запуск JavaScript. Тогда WARDEN становится вызываемой проверкой…», then «Да, скачивай» for the
engine: QuickJS-ng 0.17.0 `qjs-wasi.wasm` (MIT, 1 569 050 bytes, sha256
`42a732a676ec2d93488c19411e0fad283bf72658fdad746f089914b523c783b1`, the digest GitHub publishes; v0.18.0 of
2026-11-01 was passed over as under three weeks old). Code: aicom main 1a3472fa3 (platform + agent) and
b8819a764 (bundle rebuilt from WARDEN 0.34.0).

## Checks before

- hestia 834 passed (20 real-engine tests: escapes, limits, fetch protocol; 6 hearth tests), coverage 90 %;
  hestia-agents 919 passed, 1 failed (test_cli payment-redeem, fails the same on main without this change).
- warden.scan in QuickJS answers byte for byte what the same entry gives under Node 20 with the real
  node:crypto/Buffer/TextDecoder, on five cases (one with an instruction hidden in base64url).
- Open alerts first (skopos-vps): only `host_disk[attested]`, not this host.
- Candidate runner image offline (`candidate_smoke.py`, `--network none --read-only`, user 65532, from /app):
  languages python+javascript, a Python call 260 ms, a JS call 3 ms, a JS `import('qjs:std')` read of
  /data/provider.key → null and environment {}, warden.scan on the probe → block in 66 ms, ruleset 23.

## Kit (`kit/`, on the host at /root/hestia-js-rollout-20261120)

Overlay images FROM the images the containers ran, the way the 11-18 payment rollout did it: the whole
`hestia/hestia` package from main (`hestia-overlay.sha256`, 43 files, checked in the build) and, for the
runner, `qjs/` (fetched on the host by `fetch_qjs_wasi.py`, pin checked again in the build). `build.sh` refuses
unless the containers still run the images it was prepared against. The services import from /app (WORKDIR
/app, `python -m`), not the wheel in site-packages: test from /app.

| container | switched (UTC) | new image | previous (rollback) |
|---|---|---|---|
| hestia-hestia-runner-1 | 17:34:20–17:34:51 | `aicom-security:hestia-runner-js-20261120` = 2013a3fa719f | `hestia-hestia-runner-1-security-prev-1795196060649374524` (c238bb8a9483), snapshot `/root/security-rollbacks/hestia-hestia-runner-1-1795196060649374524` |
| hestia-hestia-1 (hearth) | 17:35:33 | `aicom-security:hestia-hearth-js-20261120` = 0ef2660285c2 | `hestia-hestia-1-security-prev-1795196133588581718` (176f205691d2), snapshot `/root/security-rollbacks/hestia-hestia-1-1795196133588581718` |

Runner first: the new runner takes an optional `language`, which the old hearth never sends. No migration.
Ledger dump before: `/root/hestia-backups/hestia-pg-pre-js-20261120T173404Z.sql.gz` (9 tables).

Rollback (hearth first, then the runner; JavaScript agents then fail their calls until removed):

    cd /root/hestia-js-rollout-20261120
    python3 rollout_container.py hestia-hestia-1 --rollback
    python3 rollout_container.py hestia-hestia-runner-1 --rollback

## After

- Runner healthy, no restarts, `/health` → `"languages": ["python", "javascript"]`. Existing Python agents
  through the new runner before the hearth switch: aid-proof 0.49 s, aid-record 1.2 s, base-gas 1.26 s.
- Hearth `/health` version 0.2.0; roster 17 running before warden-scan, 18 after.
- `warden.scan@v1` deployed (free, listed, `"language": "javascript"` on the roster). From skopos-vps the five
  cases gave the Node answers 5 of 5, each signed, 0.15–0.21 s end to end.
- Unpaid call to a priced agent (id-check) → 402, as before.
- Host tree `/root/claudecode/aicom/hestia` synced to main (`.env` untouched, `docker compose config` valid),
  so the next `deploy_hestia.sh` builds the image with the engine. aicom-hestia-guard copy refreshed.
- One `BrokenPipeError` traceback in the runner log at 17:35:31: `--probe` closed the socket after 64 bytes
  while the runner still wrote the health body. Harmless; `probe()` now reads the whole answer (main, next
  runner image).
