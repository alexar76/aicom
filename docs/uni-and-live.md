# UNI and LIVE — two realms

> **English** · **Русский:** [uni-and-live.ru.md](./uni-and-live.ru.md) · **Español:** [uni-and-live.es.md](./uni-and-live.es.md) · **Français:** [uni-and-live.fr.md](./uni-and-live.fr.md) · **中文:** [uni-and-live.zh.md](./uni-and-live.zh.md)

Two processes, two hubs, two catalogues. Mixing them is how bubble dollars get read as
revenue.

This page is **UNI vs LIVE**. TEST is a third overlay on the same monitor process — not a
third economy. On-chain switch: [crypto-switch.md](./crypto-switch.md). UNI seal:
[uni-realm.md](./uni-realm.md).

## At a glance

| | **LIVE** | **UNI** |
|---|---|---|
| Hub | [modelmarket.dev](https://modelmarket.dev) | [uni.modelmarket.dev](https://uni.modelmarket.dev) |
| Alien Monitor | [`monitor.modelmarket.dev`](https://monitor.modelmarket.dev/) · `:9101` · `ALIEN_MODE=real` | [`monitor-uni.modelmarket.dev`](https://monitor-uni.modelmarket.dev/) · `:9100` · `ALIEN_MODE=universe` |
| Money | Base, when crypto is **ON** | private Anvil, chain id `31337` — simulated |
| Catalogue | live federation (Platon, ATLAS, GAIA, oracles, …) | six bubble labs below |
| Those six labs | **not** LIVE federation peers | KHRONOS · STOICHEION · HORIZON · PSEPHOS · KYMA · DIKTYON |
| Deploy hub | `./scripts/deploy_hub.sh` | `bash deploy/uni-hub.sh …` |
| Deploy capabilities | live satellite hosts | `bash deploy/uni-satellites.sh` |
| Deploy monitor | `ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh --live` | `./scripts/deploy_alien_monitor.sh` (universe) |

A LIVE badge on the universe map is not live money. The buttons **navigate** between maps;
they do not repaint one process.

## LIVE

What you deploy: the real economy.

- **Hub** answers on `https://modelmarket.dev`. Zero local capabilities; the catalogue is
  federated from live satellites.
- **Monitor** is a second container (`alien-monitor-live`). Card CTA and stats poll that hub.
  The LIVE button stays. The UNI button goes to `ALIEN_UNIVERSE_MAP_URL` (on this fleet: `https://monitor-uni.modelmarket.dev/`).
- **Balls:** live satellites and strangers. Never the six UNI labs as catalogue peers.
- **Crypto** is a separate switch. LIVE with crypto **OFF** still talks to the live hub; it
  does not light the chain nodes. See [crypto-switch.md](./crypto-switch.md).

## UNI

What you deploy: a sealed parallel economy. From the inside the APIs look like LIVE. The
name is the seal: a separate subdomain, never a path under the live host.

- **Hub** answers on `https://uni.modelmarket.dev` (loopback `:9183` behind nginx).
- **Monitor** is the default universe process. Card CTA and stats poll
  `ALIEN_UNI_HUB_URL` / `https://uni.modelmarket.dev` — **not** the live hub. The UNI
  button stays. The LIVE button goes to `/monitor-live/`.
- **Catalogue peers** are six bubble-only labs, one process (`uni/satellite.py`) × six
  catalogues, stood up by `deploy/uni-satellites.sh`. Paths under the UNI hub name so the
  crawler's SSRF guard accepts them. Keys in `/var/lib/uni-satellites` must survive: the
  hub pins a peer key on first contact.

| satellite | product | caps | sells |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | statistics, smoothing, decomposition, forecast |
| STOICHEION Data Hygiene | `stoicheion` | 17 | schemas, diffs, profiles, text, units |
| HORIZON Geo & Telemetry | `horizon` | 17 | geodesy, spatial queries, sensor transforms |
| PSEPHOS Draws & Ballots | `psephos` | 13 | committed draws, discrete probability, ballots |
| KYMA Signal Lab | `kyma` | 12 | spectra, filters, waveforms |
| DIKTYON Graph Metrics | `diktyon` | 12 | centrality, connectivity, ordering |

Every capability is a pure function of its input, computed with the standard library. Only
the money is simulated. Detail: [uni/README.md](../uni/README.md).

**Observation deck.** Platon, ATLAS and the other live satellites may still appear on the
UNI map as status overlays of **live** services. They are not UNI catalogue peers. The
catalogue peers are the six labs.

## Do not mix

| Leak | What happens |
|---|---|
| UNI monitor polls the live hub | both maps show the same invokes / dollars |
| UNI card CTA is `modelmarket.dev` | an operator inside the bubble is handed a door out |
| LIVE seed list in the UNI hub | the bubble publishes real satellite addresses and can route real money |
| Painting `mode=real` on the UNI process | the numbers on screen are still the bubble's |

The hub seal (`aimarket_hub/realm.py`) refuses a live seed inside UNI and a private seed
inside LIVE. The monitor (`session_tick_mode`) refuses to tick the other realm's numbers on
this process.

## Related

- [uni-realm.md](./uni-realm.md) — chain seal, Anvil, why the bubble runs production mode
- [crypto-switch.md](./crypto-switch.md) — on-chain economy on/off (not the same as UNI)
- [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) — Factory clusters on both maps
- [quickstart-ecosystem-deploy.md](./quickstart-ecosystem-deploy.md) — live fleet
