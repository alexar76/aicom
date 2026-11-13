# Hub SHAKE backend rollout, 2026-11-12

All six production Hubs retained `aimarket-hub` 3.21.0. Each had been using `dilithium-py`'s
shared SHAKE fallback. The rollout added `xoflib==0.4.0` to the exact live image or venv on each
node. The Linux CPython 3.12 wheel from [PyPI](https://pypi.org/project/xoflib/0.4.0/#files)
matched the lockfile SHA-256 `e6eff28d29b495ec9b8caaec9ca515520a0f10f035d2e065f996e59c52dd57f5`.
The Docker build installed it offline without resolving other dependencies.

The candidate and the live runtime on each node passed the SHAKE-128 and SHAKE-256 interleaving
check against Python's `hashlib` and eight concurrent ML-DSA-65 round trips, including rejection of
altered messages. [Runtime check](verify.py)

| Hub | DB backup (UTC) | Previous → current Docker image | Outside checks |
| --- | --- | --- | ---: |
| hub.modelmarket.dev (canary) | 17:31:56 | `6c3f31b30f20` → `bead7dce1a8c` | 92 |
| hunt.modelmarket.dev | 17:33:27 | `ba2341bd5372` → `4b429f58d752` | 100 |
| uni.modelmarket.dev | 17:33:49 | `1e26a196e516` → `6b02053cd5c0` | 100 |
| hub.attestedmemory.net | 17:34:22 | `f6374b4917a7` → `edfcf5d2699d` | 268 |
| independentai.network/hub | 17:35:13 | systemd venv `hub-3.21.0-20261112` → `hub-3.21.0-xoflib-20261112` | 132 |
| modelmarket.dev | 17:36:23 | `76298ef1e089` → `0d2aeefc891ce` | 124 |

The [outside verifier](../hub-3.21.0-rollout-2026-11-12/logs/verify_live.py) verified ML-DSA-65 catalogue
signatures and Ed25519 Trust Manifests on the five signing Hubs. Independent uses unsigned catalogues
under `/hub`. Its full check used the production address with the TLS hostname and certificate
validated after the workstation resolver missed that domain. At the apex, the rollout helper
reattached THEMIS to the new Hub network namespace and both loopback health checks passed.
The final process check found all five Hub containers and THEMIS healthy with restart count zero.
Independent was active with `NRestarts=0` and the intended Python executable.

Database backups and previous containers were retained by the existing rollout helper. Its local
health checks trigger rollback on failure. Independent retains its previous venv and drop-in.
`bash deploy.sh indep-rollback` on that host removes the new drop-in and confirms the old venv is
serving. [Rollout script](deploy.sh) · [Container rollout helper](../hub-3.21.0-rollout-2026-11-12/kit/rollout_container.py)
