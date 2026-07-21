# Publish runbook — monorepo → Gitea (canon) + GitHub mirrors

How to get local changes into the canonical monorepo (Gitea) and out to the public
GitHub mirrors, without crossing the two up. **All pushes are run by a human** —
these scripts never auto-push from an agent.

## Mental model — three publish paths (mutually guarded)

| Script | Publishes | Target | Guard |
|--------|-----------|--------|-------|
| [`push_gitea_monorepo.sh`](../scripts/push_gitea_monorepo.sh) | **full** monorepo (history + satellites) | **Gitea** (both servers) | refuses any `github.com` target |
| [`mirror_satellites.sh`](../scripts/mirror_satellites.sh) | one folder per satellite | **GitHub** | refuses any non-GitHub target |
| [`publish_aicom_factory.sh`](../scripts/publish_aicom_factory.sh) | trimmed single-commit `aicom` snapshot | **GitHub** `<org>/aicom` | refuses anything that isn't `github.com/<org>/aicom` |

The guards make it impossible to accidentally force-push the full monorepo to GitHub
(leak) or overwrite the Gitea canon with a trimmed snapshot (data loss).

Order for any release: **commit → push to Gitea → publish to GitHub.**

---

## 1. Commit (stage only your files)

Do **not** `git add -A` — leave unrelated untracked paths (e.g. `argus/.argus-warden-scan-memory/`)
and the `lottery/alien-monitor` submodule alone. Review first:

```bash
git diff -- scripts/ docs/ README.md start.sh
```

Then commit the specific files (one or several logical commits — your call).

## 2. Push to Gitea (canonical, both servers)

```bash
./scripts/push_gitea_monorepo.sh --dry-run   # preview: remotes + pending commits
./scripts/push_gitea_monorepo.sh             # push to Gitea#1 + Gitea#2
```

Unchanged from before. The guard only *rejects* an accidental GitHub target; the normal
Gitea path is transparent. Races are handled (fetch/merge/retry).

## 3. Publish the `aicom` snapshot to GitHub (public showcase)

Always pass the GitHub target explicitly and a token:

```bash
GH_PAT=<token> \
AICOM_FACTORY_REMOTE=https://github.com/alexar76/aicom.git \
./scripts/publish_aicom_factory.sh --dry-run   # confirm: "Cloning …github.com/alexar76/aicom"
```

Run without `--dry-run` only once the output shows **github.com/alexar76/aicom**.
If `AICOM_FACTORY_REMOTE` is omitted the script now **aborts** (the guard) instead of
falling back to the Gitea `origin` — so it can no longer overwrite the canon.

**Contributor credit:** external human contributors are listed in
[`scripts/aicom-coauthors.txt`](../scripts/aicom-coauthors.txt) and appended as
`Co-authored-by:` trailers to the snapshot commit, so they appear in the GitHub
contributor graph. The publish output prints `Crediting co-authors …`.

## 4. (Optional) Publish a satellite to GitHub

```bash
GH_PAT=<token> ./scripts/mirror_satellites.sh --satellite <id> --dry-run
GH_PAT=<token> ./scripts/mirror_satellites.sh --satellite <id>
```

Per-satellite mode comes from `history:` in [`scripts/satellite-map.yaml`](../scripts/satellite-map.yaml):

- **`mirror`** (default): squashed orphan snapshot, force-pushed (read-only; PRs overwritten).
- **`live`** (e.g. `metis`): append-only real history, normal push (no `--force`); **PRs accepted**.
  Before each live sync, import any merged PRs back into the monorepo first:
  ```bash
  ./scripts/import_satellite_pr.sh <id>      # emits a reviewable patch
  # review → git apply --directory=<path> → commit → re-sync:
  ALLOW_DIVERGENCE=1 ./scripts/mirror_satellites.sh --satellite <id>
  ```
  A divergence guard aborts the sync if an un-imported PR sits on the satellite tip.

---

## Current pending batch (2026-07-19)

Concrete commits for the changes currently in the working tree:

```bash
# A — satellites accept PRs (live history + reverse-import) + GitHub/Gitea target guards
git add scripts/satellite-map.yaml scripts/mirror_satellites.sh \
        scripts/import_satellite_pr.sh scripts/push_gitea_monorepo.sh \
        docs/repository-canonical-policy.md
git commit -m "feat(mirror): satellites accept PRs (live history + reverse-import) + GitHub/Gitea target guards"

# B — keep human Co-authored-by; credit aicom snapshot (Benjamin Ayivoh); guard GitHub target
git add scripts/sanitize_git_commit_meta.py scripts/aicom-coauthors.txt \
        scripts/publish_aicom_factory.sh
git commit -m "feat(mirror): keep human Co-authored-by; credit aicom snapshot (Benjamin Ayivoh); guard GitHub target"

# C — docs
git add docs/running.md docs/publish-runbook.md README.md start.sh
git commit -m "docs: running + publish runbooks; start.sh bootstrap-pw parse fix"
```

Then §2 (Gitea) → §3 (publish `aicom`, which credits Benjamin) → optionally §4 for `metis`.

## See also
- [running.md](running.md) — how to *run* the stack (core / full / dev container).
- [repository-canonical-policy.md](repository-canonical-policy.md) — monorepo-is-canon + live/mirror policy.
- [deploy-ecosystem.md](deploy-ecosystem.md) — full fleet redeploy reference.
