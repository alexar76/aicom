# Repository canonical policy

**Decision date:** 2026-05-24
**Status:** ACCEPTED
**Owner:** AI-Factory maintainers

## Question

The AICOM monorepo physically contains the source for two components that
also exist as standalone GitHub repositories under `alexar76/`:

| Component | Monorepo path | External mirror |
|-----------|---------------|-----------------|
| ACEX (capital / pricing) | [`acex/`](https://github.com/alexar76/acex/tree/main/) | `alexar76/acex` |
| AI Service Mesh | [`ai-service-mesh/`](https://github.com/alexar76/ai-service-mesh/tree/main/) | `alexar76/ai-service-mesh` |

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
   `alexar76/aicom` (Gitea#2)".

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

## Amendment 2026-07-19 — `live` history mode (PRs accepted)

The monorepo stays canonical. But a satellite may now opt into **accepting pull
requests** via a per-satellite `history:` field in
[`scripts/satellite-map.yaml`](../scripts/satellite-map.yaml). Two modes:

| `history:` | Publish | PRs | Use for |
|------------|---------|-----|---------|
| `mirror` (default, or omitted) | squashed **orphan** commit, **`--force`** push | **overwritten** on next sync → not accepted | read-only showcases; the historical default above |
| `live` | normal commit **on top**, normal push (**never** `--force`/orphan) | **accepted** — history is append-only so merged PRs survive | community-facing satellites (first: `metis`) |

**Two-way flow for `live` satellites:**

1. **Out (you):** work lands in the monorepo → `mirror_satellites.sh` appends one
   `chore(satellite): sync …` commit to the satellite and pushes (no force).
2. **In (contributor):** a PR is merged on GitHub → it lives on the satellite's `main`.
3. **Reverse-import (you, before the next out-sync):**
   [`scripts/import_satellite_pr.sh <id>`](../scripts/import_satellite_pr.sh) emits a
   reviewable patch of the merged PR(s); you apply + commit it into the monorepo so
   the contribution becomes canonical.

**Guard rails baked into the script (live mode only):**

- **Divergence guard** — if the satellite tip is *not* a monorepo-sync commit (i.e. an
  un-imported PR is sitting on top), the sync **aborts** instead of overwriting it.
  Override only after reverse-importing, with `ALLOW_DIVERGENCE=1`.
- **Hard secret gate** — `scripts/verify_mirror_secrets.sh` must pass or the push is
  refused (live history is permanent — a leaked secret can't be scrubbed without a
  force-push, which live mode forbids).
- **README banner** flips to "PRs welcome; merged PRs are imported back into the monorepo."

`mirror`-mode satellites are unchanged by this amendment.

## Amendment 2026-09-15 — factory GitHub is `live` too

[`scripts/publish_aicom_factory.sh`](../scripts/publish_aicom_factory.sh) now uses the
same **append-only** path as a `history: live` satellite (first: `metis`):

- **Out:** trimmed factory tree is committed **on top** of `alexar76/aicom` `main` and
  pushed **without** `--force` / orphan (`chore(factory): sync …`).
- **In:** pull requests on `alexar76/aicom` are **accepted**.
- **Reverse-import:** [`scripts/import_factory_pr.sh`](../scripts/import_factory_pr.sh)
  before the next outbound factory publish, or the divergence guard aborts.

The GitHub factory tree stays **trimmed** (satellites excluded). Canonical source is
still this monorepo on Gitea. The old single-commit snapshot + `--force` path is gone
so contributor forks keep a common ancestor and GitHub will open PRs.

## Amendment 2026-10-15 — every repository is `live`

`live` is now the **default** `history:` mode. Every satellite in
[`scripts/satellite-map.yaml`](../scripts/satellite-map.yaml) publishes append-only
history and accepts pull requests, the same door as `metis` and the factory repo
`alexar76/aicom`. `mirror` stays available as an explicit opt-out
(`history: mirror`); no satellite uses it.

**Where to send a change:** to the repository you found the code in. A pull request
on `alexar76/aimarket-hub` goes to `alexar76/aimarket-hub`; one on the factory goes
to `alexar76/aicom`. Nobody outside the team needs the monorepo.

**Bringing a merged PR home:**
[`scripts/import_satellite_pr.sh <id>`](../scripts/import_satellite_pr.sh) writes a patch
whose paths are **monorepo** paths, so it applies at the monorepo root
(`git apply --3way`). [`scripts/satellite_import_paths.py`](../scripts/satellite_import_paths.py)
maps satellites that fold several folders together: the desktop repo's `apps/<sku>`
and `packages/`, the plugins repo's `plugins/aimarket-provenance`, attested-memory's
`apps/`, and a vendored `vendor/oracle-core`. Files the mirror writes on every sync
(LICENSE, SECURITY.md, CONTRIBUTING.md, `.github/`, badges) are listed as left out
instead of being dropped silently. For the factory repo use
[`scripts/import_factory_pr.sh`](../scripts/import_factory_pr.sh).

**Also changed:** the Glama tag `glama-build` follows the tip in live mode too, and a
live wiki's `main` fast-forwards to `master` instead of being force-pushed.

