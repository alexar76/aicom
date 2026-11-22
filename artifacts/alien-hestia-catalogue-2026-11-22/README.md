# Alien Monitor: HESTIA card links the agent catalogue — rollout 2026-11-22 (LIVE 07:36Z / 07:37Z)

Part of «Что ещё не сделано: - делай» (owner 22.11) after the hearth started publishing `handler_sha256` and
`/agents/` (record: `hestia-catalogue-rollout-2026-11-22`). Code: aicom main 5a47f524f.

## What the card shows now

- A button "Open the agent catalogue: code and digests" → `https://hestia.modelmarket.dev/agents/`.
- A line "N of M catalogued agents run exactly the published code".
- On each running agent's row, "code = catalogue" (or "code ≠ catalogue") linked to its entry in the catalogue,
  with the digest in the tooltip. Other owners' agents carry no mark: the catalogue does not publish them.
- Backend (`hestia_status.py`): reads `/agents/catalog.json` every ten minutes (own TTL,
  `ALIEN_HESTIA_CATALOGUE_TTL_S`), carries only well-formed lowercase SHA-256 values from the roster, and says
  nothing about published code when the catalogue was not read. Five languages.

## Build

Both monitors run thin images. The live UI had been built with the main checkout's packages (vite 6.4.4), not a
clean `npm ci` of the current lock (vite 8.3.5): built from main's parent (a0b44813a) with those packages, every
JS chunk is byte-identical to the live dist (only `.map` files differ, by build paths). The new UI is built the
same way from 5a47f524f; against that parent only the entry chunk, its CSS and `index.html` change. The clean
toolchain was used for the checks: `tsc -b`, `vite build` and 292 frontend tests pass; backend 26 tests.

Kit `kit/` (on factory-vps `/root/alien-hestia-catalogue-20261122`): `ctx/Dockerfile` (`FROM ${BASE}`, dist and
`hestia_status.py` copied as root:root like the files they replace), `SHA256SUMS` of the copied files (`ctx/dist`
itself is not committed: rebuild as above), and main's `scripts/redeploy_alien_monitor_live.sh`. The host mirror's
copy of that script is older and would mount LIVE's `/app/data/provider-events` read-only, so the kit's copy ran.

## Switch

| container | switched (UTC) | new image | previous image (rollback) |
|---|---|---|---|
| alien-monitor-live (monitor.modelmarket.dev, :9101) | 07:36:34–07:36:39 | `alien-monitor:hestia-catalogue-live-20261122` = a104d7c3a57d | `aicom-security:alien-monitor-provider-events-20261113` |
| alien-monitor (monitor-uni.modelmarket.dev, :9100) | 07:37:18–07:37:25 | `alien-monitor:hestia-catalogue-uni-20261122` = a9626f83fee7 | `alien-monitor:uni-lottery-feed-20261114` |

Environment carried whole (values never printed; 40 names on LIVE); mounts as before (LIVE provider-events rw,
UNI universe rw, the rest ro). The UNI monitor's UI had been older than LIVE's (it lacked the frontend part of
2f55e9176, provider events, live on LIVE since 11-13); it now has main's UI like LIVE. Rollback, per container:

    cd /root/alien-hestia-catalogue-20261122
    ./scripts/redeploy_alien_monitor_live.sh alien-monitor-live --image "$(cat alien-monitor-live.previous-image)"
    ./scripts/redeploy_alien_monitor_live.sh alien-monitor --image "$(cat alien-monitor.previous-image)"

## After

- Both healthy, 0 restarts, no traceback. LIVE `/api/topology`: HESTIA node with `links.catalogue`,
  `published` 29 / `published_matching` 29, 33 roster rows, 29 marked `published`, 0 `differs`. UNI: 73 nodes,
  `blockchain_ready`, "Core contracts already on chain", HESTIA node with the catalogue link.
- Browser, `https://monitor.modelmarket.dev/?node=hestia&lang=ru`: the card reads «29 из 29 агентов каталога
  выполняют ровно опубликованный код», 29 «код = каталог» links (e.g. `…/agents/#agent-card`) and the button
  «Открыть каталог агентов: код и хеши ↗».
- The attested monitor (monitor.attestedmemory.net) was not changed.
