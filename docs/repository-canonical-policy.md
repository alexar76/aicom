# Repository canonical policy

**Decision date:** 2026-05-24
**Status:** ACCEPTED
**Owner:** AI-Factory maintainers

## Question

The AICOM monorepo physically contains the source for two components that
also exist as standalone GitHub repositories under `alexar76/`:

| Component | Monorepo path | External mirror |
|-----------|---------------|-----------------|
| ACEX (capital / pricing) | [`acex/`](../acex/) | `alexar76/acex` |
| AI Service Mesh | [`ai-service-mesh/`](../ai-service-mesh/) | `alexar76/ai-service-mesh` |

Without an explicit canonical-source rule, any feature work risks landing
on the side that the next `scripts/mirror_satellites.sh` run will overwrite.

## Decision

**The monorepo (this repo) is canonical for both components.**

1. All feature work, bug fixes, and security patches MUST land in
   `acex/` and `ai-service-mesh/` here first.
2. The standalone repos at `alexar76/acex` and `alexar76/ai-service-mesh`
   are **read-only mirrors**, regenerated from the monorepo by
   `scripts/mirror_satellites.sh`. Pull requests opened against them
   should be redirected to this repo and closed.
3. The mirror script must run with `--force-with-lease` so a manual edit on
   the GitHub side does NOT silently propagate back to the monorepo.
4. The mirrors' READMEs must carry a banner stating "Mirror — open PRs at
   `Superowner/aicom`".

## Rationale

- The monorepo already runs the full CI matrix (forge, anchor, pytest,
  vitest, dart test). Splitting CI ownership doubles maintenance.
- Federation contracts (`AIMarketEscrow.sol`, payment channels, hub
  bond) cross the ACEX / Mesh / Hub / Factory boundary; cross-cutting
  changes must be atomic.
- Existing imports (`from acex.integrations.pricing import ...` in
  `aimarket_hub.capital_pricing`) already assume the monorepo layout.
- Operators install the whole stack from `docker-compose.yml` — there is no
  consumer that needs Mesh or ACEX as a standalone package.

## Non-goals

- We are NOT removing `alexar76/acex` and `alexar76/ai-service-mesh` from
  GitHub. Visibility for evaluators and prospective contributors is still
  useful; they just don't accept commits.
- We are NOT migrating to git submodules. The mirror script is simpler than
  submodule discipline and keeps `git clone` of the monorepo self-contained.

## Open follow-ups

- [ ] `scripts/mirror_satellites.sh`: ensure `--force-with-lease` is set
      and add a banner injection step that prepends the read-only notice
      to each mirror's `README.md`.
- [ ] CI: add a guard that fails the build if `acex/` or `ai-service-mesh/`
      contain a stray `.gitmodules` entry pointing back at the mirrors.
- [ ] Each mirror's `CONTRIBUTING.md`: link back to this policy file.
