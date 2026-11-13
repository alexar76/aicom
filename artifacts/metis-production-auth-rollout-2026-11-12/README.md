# Metis production authentication rollout

Deployed the three runtime modules from `f1c579ab4` on 2026-11-12. Both targets run derived local images built from their previous production images. The package and API version remain `0.2.6`. The image IDs and in-container module SHA-256 hashes identify this deployment.

| Target | Local image tag | `/health` | `/v1/models` valid / missing / invalid Bearer | Knowledge entries |
| --- | --- | --- | --- | --- |
| [Metis](https://metis.modelmarket.dev/health) | `metis:0.2.6-local-f1c579ab4` | 200 | 200 / 401 / 401 | 143 |
| [Metis Appeal](https://attestedmemory.net/metis-appeal/health) | `metis-appeal:0.2.6-local-f1c579ab4` | 200 | 200 / 401 / 401 | 0 |

Each canary ran against a private copy of the corresponding data. Its offline HTTP checks reproduced local development access and verified that runtime production config and environment flags override development relay opt-ins. Production checks passed for both containers, including Docker health, dependency consistency, CLI commands and the public status codes above. Docker config, environment, mounts, network membership, custom network IPs and port bindings matched their prior values.

- Metis [canary](metis-prepare.jsonl), [promotion](metis-promote.jsonl) and [runtime state](metis-runtime.txt).
- Metis Appeal [canary](metis-appeal-prepare.jsonl), [promotion](metis-appeal-promote.jsonl) and [runtime state](metis-appeal-runtime.txt).
- [Independent public smoke checks](public-smoke.json).

Use the recorded immutable image ID and existing runtime configuration for any later recreate. Each host retains its stopped `*-rollback-f1c579ab4` container and a private stopped-state data snapshot under `/root/metis-rollouts/20261112-f1c579ab4/`. Follow the existing [rollback procedure](../oracle-metis-rollout-2026-10-28/prod-metis/receipt.md) using these container names, image IDs and snapshots.
