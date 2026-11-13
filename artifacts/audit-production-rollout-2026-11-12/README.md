# Production rollout of f1c579ab4

The Factory app and the `/tools/` gateway were updated on 2026-11-12. Each candidate was built from the exact running image. The Factory layer adds the pinned CPython 3.12 Linux wheel for `xoflib==0.4.0`; the gateway layer replaces the five locale files after matching the running files against the parent commit.

| Target | Production image | Verification |
| --- | --- | --- |
| Factory app | `aicom-security:aicom-app-1-audit-f1c579ab4` | Public home and `/api/health` returned 200. The running app used xoflib for SHAKE-128 and SHAKE-256 and passed eight concurrent ML-DSA-65 key generation, signing and verification cases. The existing Compose service now pins this image. |
| Tools gateway | `aicom-security:okx-a2mcp-audit-f1c579ab4` | All five public language routes returned 200 with the expected footer. The free WARDEN scan returned 200 and allowed the benign fixture. |
| WARDEN landing | Static files from `f1c579ab4` | The public page returned 200 with `WARDEN by AIMarket — MCP tool firewall (@aimarket/warden)` in `title` and `og:title`. |

The wheel SHA-256 was `e6eff28d29b495ec9b8caaec9ca515520a0f10f035d2e065f996e59c52dd57f5`. The first gateway candidate failed the offline Node check because its locale files were unreadable by the service user. The rebuilt image passed that check before switching production traffic. The [existing container rollout helper](../hub-3.21.0-rollout-2026-11-12/kit/rollout_container.py) kept the original settings and saved rollback snapshots. Both previous containers remain available.

See the separate receipts for [Metis](../metis-production-auth-rollout-2026-11-12/README.md) and [Hub](../hub-xoflib-rollout-2026-11-12/README.md).
