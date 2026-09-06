# Competing lab host — notes for `hunt.modelmarket.dev`

> **Canonical runbook (EN/RU/ES/FR/ZH):**  
> [`docs/ecosystem/hub-vps-competing.md`](./ecosystem/hub-vps-competing.md)

This file is a short host-side checklist. Prefer the ecosystem runbook + scripts:

- `scripts/register_hub_upstream.sh`
- `scripts/register_federation_mesh.sh`
- `signal-hunt/scripts/register-upstream.sh`

## Quick facts (2026-08-11)

| Item | Value |
|------|--------|
| SSH | `ssh -i ~/.ssh/id_ed25519_factory -o IdentitiesOnly=yes root@hunt.modelmarket.dev` |
| Lab Hub peer | `http://hunt.modelmarket.dev:9083` (UNI, crypto off) |
| Hunt | `https://hunt.modelmarket.dev` (nginx TLS, compose `nginx-edge`) |
| Use | `use.modelmarket.dev` static under `/var/www/use.modelmarket.dev` |
| Alien Monitor galaxy | `COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)` on primary Monitor |
| SKOPOS fleet | `competing-lab` (`agent-push`) → [skopos.modelmarket.dev](https://skopos.modelmarket.dev) |

## Monorepo sync

```bash
rsync -az --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
  --exclude 'data' --exclude '.env' \
  ./ root@hunt.modelmarket.dev:/opt/aicom/
```
