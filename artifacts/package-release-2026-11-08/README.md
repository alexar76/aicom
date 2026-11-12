# Package releases prepared on 2026-11-08

**Nothing is uploaded.** Each file here was built in a clean export (`git archive`) of the same sources as this
commit, never from a working checkout. The wheels, sdists and tarballs are git-ignored (`.gitignore` here);
`SHA256SUMS` and the logs are tracked.
Upload these exact files rather than rebuilding: `scripts/publish_pypi.sh` builds whatever tree it is run in.

Why each one: the version on the registry was byte-compared with main `28d5206b4`
(`scripts/verify_published_dist_freshness.py` for PyPI; tarball against tree for npm). Each serves older code than
the tree under the same version string.

| Package | Registry now | Here | Status |
|---|---|---|---|
| aimarket-hub | 3.18.0 | 3.19.0 | ready |
| aimarket-histor | 0.6.2 | 0.7.0 | ready |
| helios-broadcast | 0.2.1 | 0.2.2 | ready |
| create-aimarket-agent (PyPI) | 0.1.1 | 0.1.2 | ready |
| create-aimarket-agent (npm) | 0.1.1 | 0.1.2 | optional: same files as 0.1.1, version kept equal to PyPI |
| @alexar76/argus3 | 0.3.4 | 0.3.5 | ready |
| aimarket-atlas | 0.3.5 | 0.4.0 | **hold**: `import atlas.main` fails from a pip install (see below) |
| aimarket-gaia-gateway | 0.2.2 | 0.3.0 | **hold**: `gaia.devices.om_mesh` and `sc_mesh` fail from a pip install (see below) |
| @aimarket/warden | 0.23.0 | 0.24.0 | **held, not in main**: branch `claude/warden-0.24.0-2026-11-08` (see below) |

The changelog entries say what changed: root `CHANGELOG.md` (hub 3.19.0), `histor/CHANGELOG.md`, `atlas/CHANGELOG.md`,
`gaia/CHANGELOG.md`, `helios/CHANGELOG.md`, `create-aimarket-agent/CHANGELOG.md`, `argus/CHANGELOG.md`. Not released: aimarket-bridges (a docstring changed) and aimarket-hestia (import order).

## Hold: ATLAS and GAIA read their city lists from the repository, not from the package

`gaia/devices/om_mesh.py` and `sc_mesh.py` read `config/om_mesh_cities.yaml` and `config/sc_mesh_cities.yaml` two
directories above the module, and ATLAS's copies read `atlas/config/…` one directory above. In the repository and in
the Docker images that path exists. In a wheel it points into `site-packages/` and the files are not shipped, so the
module fails on import with `FileNotFoundError`. That stops `atlas.main` and `atlas.aggregator` entirely. GAIA's app
imports, but its two mesh modules do not. **The published ATLAS 0.3.5 fails in exactly the same way** (checked in a
fresh venv on 2026-11-08), so this is old, not new in 0.4.0. Fix before uploading: ship the YAML files in the package
(hatch `force-include`), and read them from there when the repository copy is absent.

## WARDEN 0.24.0 is held on a branch

Branch `claude/warden-0.24.0-2026-11-08` carries the 0.24.0 bump: the Codex flow guard released, pins, docs in five
languages, and the landing page back on ruleset v17. Its evidence is in
`docs/evidence/warden-release-0.24.0-2026-11-08/`: 1443 tests, the red team, the archive, build digest `3adaab92…`.
The current WARDEN work is now committed in `9f923074378d701581eddcb21580eb6a0d48f468`:
`0.23.1-dev.20261108`, ruleset 19. Its 448-file source snapshot passed 1,574 full-suite cases per host in gVisor
on Attested and Blip, with separate current-source evidence under
`artifacts/warden-security-2026-11-07/current-source-20261108/`. The older branch's 1,443-case/ruleset-17 evidence
does not validate this newer source or replace its fixes. Keep that branch held; prepare the next release from the
current accepted source, reconciling any branch-only changes and rerunning the applicable release gates.
The MOMUS release gate still applies. A fresh direct npm registry check on 2026-11-08 still returns 0.23.0;
no new WARDEN npm release was published during the dual-host acceptance.

## Checks

| Check | Result |
|---|---|
| Wheels against the commit | every file of the six wheels equals the commit byte for byte. The hub's six `static/ui/` files equal their sources (`setup.py` copies them) (`logs/wheels-vs-commit.log`) |
| Wheels against the previous release | new files are exactly the expected ones: GAIA +24 sources, HISTOR `peers.py` and `digest_xcheck.py`, hub `provider_buyer_ref.py`; nothing removed |
| Secret gate (`scripts/verify_distribution_secrets.py`) | all six wheels and six sdists clean |
| Fresh venv, Python 3.12, dependencies from PyPI | all six install and import at the new version. App modules import (hub `api`, `mcp_gateway`, `crawler`; HISTOR `app`, `peers`, `tiles`; HELIOS `worker`), except the ATLAS/GAIA hold above |
| Package tests (worktree) | HISTOR passes; ATLAS 729 passed; HELIOS 91; create-aimarket-agent 58 (npm flavour 12); hub MCP and buyer-ref 98 |
| GAIA tests | 940 passed, 21 failed. All 21 are GAIA+hub end-to-end tests whose fake `safe_post` lacks the hub's `oracle_paid` argument. GAIA's code here is main's (only the version and changelog changed) |
| ARGUS 0.3.5 | typecheck, build, 405 passed, 13 skipped. Against npm 0.3.4 only the feature's `dist/` files and `package.json` differ; the 14,964 bundled `node_modules` files are unchanged. In a clean consumer, `--help` exits 0 and with no arguments over pipes it answers MCP `initialize` as 0.3.5 |
| `uv lock --check` | hub, HISTOR, GAIA, create-aimarket-agent: their own version updated in `uv.lock`, consistent |

## Upload (owner)

PyPI, these files only. Example for the hub:

```
uvx twine upload artifacts/package-release-2026-11-08/pypi/aimarket_hub-3.19.0*
```

npm:

```
npm publish ./artifacts/package-release-2026-11-08/npm/alexar76-argus3-0.3.5.tgz
npm view @alexar76/argus3@0.3.5 dist.shasum   # fd7f18622be2e460044049572ce02c065edabaa7
npm publish ./artifacts/package-release-2026-11-08/npm/create-aimarket-agent-0.1.2.tgz   # optional
npm view create-aimarket-agent@0.1.2 dist.shasum   # 796ca5c2b8f45116e59aa7183cc8401dce19e4ba
```

After each upload, run `scripts/verify_published_dist_freshness.py <tree>` again: the new version must read
`identical`. The MCP registry entries move with the packages (`argus/server.json` 0.3.5, `aimarket-hub/server.json`
3.19.0, `histor/server.json` 0.7.0), published separately.
