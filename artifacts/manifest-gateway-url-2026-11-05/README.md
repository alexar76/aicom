# Public manifest: no private address for gateway sellers — 2026-11-05

Owner, about the supplier reviewer's only high finding (MY-58, 2026-11-04): «исправляй».

## The finding

modelmarket.dev's public manifest listed `aicom-diagnostics` (`aicom.diagnose@v1`, $0.10) with
`invoke_url: http://aicom-diagnostics:8124/diagnose`: the container name on factory-vps's private network
`aicom_aicom_net`, plain http. It is an operator gateway provider (`AIMARKET_INVOKE_HOST_GATEWAY` of
`modelmarket-hub` = `host.docker.internal,aicom-diagnostics`): only the hub can reach it, buyers go through
`https://modelmarket.dev/ai-market/v2/invoke`. The address told every reader an internal hostname and offered a
URL nobody outside can call. The same pattern is on hub.attestedmemory.net (memory-market, truth-layer,
provenance-ledger, multica-provider). Search, `/ai-market/v2/catalog`, `/.well-known/agent-marketplace` and
the ARD documents did not show it; only the manifest did (`hub_routes/catalog.py`).

## The fix (aimarket-hub)

`published_invoke_url()` in `aimarket_hub/hub_routes/catalog.py`: a local row whose stored address is a gateway
host, `localhost`, a name without a dot, or a loopback / private / link-local IP is shown as this hub's invoke
endpoint; public sellers and federated rows are unchanged; the stored address and routing are untouched.
Tests: `tests/test_manifest_invoke_url.py` (13, Python 3.12). The 24 test files that touch the manifest: 565
passed; the 11 failures (`test_ard.py`: the venv's `awr` has no `jcs`; one `test_pipeline_provider.py` case) fail
the same way with the unchanged `catalog.py`.

## Overlay for modelmarket.dev (LIVE 2026-11-05 06:03Z, owner: «да»)

`modelmarket-hub/` here = `/root/mgw-20261105/` on factory-vps: Dockerfile FROM the running image
(`modelmarket-hub:cf-20261104`), the patched `catalog.py`, `live.sha` (live `catalog.py` 3b4497e410f0 = the
repo's before the change), `smoke.py`, `build.sh`.

- `build.sh modelmarket-hub modelmarket-hub:mgw-20261105`: base is the running image, live file unchanged,
  smoke inside the image with no network passed («gateway seller shown as the hub, public seller unchanged, stored
  address kept, health 200»), file in the image = context (1e57c510c286).
- Roll (first refused by the auto-mode classifier as a production deploy; run after the owner's «да»):

```bash
ssh factory-vps 'cd /root/hub-3160-main-20261021 && bash roll.sh modelmarket-hub modelmarket-hub:cf-20261104 modelmarket-hub:mgw-20261105 http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health'
```

  `roll.sh` backs up the sqlite DB, refuses if the hub no longer runs `cf-20261104`, and `rollout_container.py`
  re-creates THEMIS inside the new container and rolls back on a failed health check of the hub or THEMIS.
- After: the public manifest must not contain `aicom-diagnostics:8124`, the listing's `invoke_url` must be
  `https://modelmarket.dev/ai-market/v2/invoke`, `route_status` still `live`.
- Done 2026-11-05: alerter had nothing open (12 h); the hub ran `cf-20261104`; `roll.sh` backed up the DB
  (`/app/data/hub-backup-pre-3160-20261105T060310Z.db`), started `mgw-20261105` at 06:03:13Z, healthy; previous
  container kept as `modelmarket-hub-security-prev-1793858590954250685`. In the container `catalog.py` =
  1e57c510c286; hub and THEMIS health 200. Public `https://modelmarket.dev/ai-market/v2/manifest`: 285 listings,
  no `aicom-diagnostics:8124`, `aicom.diagnose@v1` shows `https://modelmarket.dev/ai-market/v2/invoke` with
  `route_status: live`, and no listing has a non-https or dotless address left.
- Rollback: `python3 rollout_container.py modelmarket-hub --image modelmarket-hub:cf-20261104 --health
  http://127.0.0.1:9083/ai-market/v2/health --health http://127.0.0.1:9460/health` in the same folder.

The attested hub runs a different `catalog.py` (differs from the repo): it gets the change with its next
rollout from main, or with a ported overlay.
