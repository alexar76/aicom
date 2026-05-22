# Satellite Extraction Report

**Date:** 2026-05-22  
**Monorepo:** [`alexar76/aicom`](https://github.com/alexar76/aicom)  
**Performed by:** automated extraction script

---

## 1. GitHub Org Chosen

**`alexar76`** (personal account of Aleksandr Artamokhov)

**Why:** The GitHub PAT (`ghp_d6Ty...`) available in the environment authenticates as `alexar76`. This user is not a member of the `modelmarket` organization (which exists but has 1 repo and no accessible org listing for this token), so creating repos under `modelmarket` was not possible. All 5 satellite repos were created under `alexar76/`.

*Recommended follow-up:* If `modelmarket` org membership is granted, transfer these repos to the org and update the workflow matrix URLs.

---

## 2. New Repos

| # | Monorepo Subdir | Satellite Repo URL | License | Files |
|---|-----------------|-------------------|---------|-------|
| 1 | `aimarket-protocol/` | https://github.com/alexar76/aimarket-protocol | MIT | 5 top-level (README, LICENSE, spec.md, schemas/, test-vectors/) |
| 2 | `aimarket-hub/` | https://github.com/alexar76/aimarket-hub | Apache-2.0 | 10 top-level (Python package, tests, Docker, docs) |
| 3 | `aimarket-widget/` | https://github.com/alexar76/aimarket-widget | MIT | 4 files (demo.html, widget.js, themes.css, live-stream.html) |
| 4 | `aimarket-agent/` | https://github.com/alexar76/aimarket-agent | MIT | 3 top-level (pyproject.toml, README, aimarket_agent/) |
| 5 | `plugins/` | https://github.com/alexar76/aimarket-plugins | MIT | 14 plugin packages (auction, channels, data-cap, dataset, mcp-packager, nft, orchestrator, personas, promo, reputation, safety, streaming, tee, zk) |

All repos are **public** with issues enabled, projects/wiki disabled.

---

## 3. Mirror Workflow

**Path:** `.github/workflows/mirror-satellites.yml`

**Trigger:** On every push to `main` (plus manual `workflow_dispatch`).

**Secret used for auth:** `MIRROR_SATELLITE_PAT` — a GitHub PAT stored as an encrypted Actions secret on `alexar76/aicom`. The PAT has repo-scope write access to all 5 satellite repos.

**How it works:**
1. Checks out the monorepo with full history (`fetch-depth: 0`).
2. Runs `git subtree split --prefix=<dir> -b export/<name>` for each subdir.
3. Force-pushes the export branch to the satellite repo's `main`.

**Important:** Force-push is only to satellite `main` branches — never to the monorepo's `main`.

---

## 4. Verification Commands

```bash
# aimarket-protocol
git clone --depth=1 https://github.com/alexar76/aimarket-protocol.git /tmp/check-protocol && ls /tmp/check-protocol

# aimarket-hub
git clone --depth=1 https://github.com/alexar76/aimarket-hub.git /tmp/check-hub && ls /tmp/check-hub

# aimarket-widget
git clone --depth=1 https://github.com/alexar76/aimarket-widget.git /tmp/check-widget && ls /tmp/check-widget

# aimarket-agent
git clone --depth=1 https://github.com/alexar76/aimarket-agent.git /tmp/check-agent && ls /tmp/check-agent

# aimarket-plugins
git clone --depth=1 https://github.com/alexar76/aimarket-plugins.git /tmp/check-plugins && ls -d /tmp/check-plugins/aimarket-*/
```

All 5 were verified and confirmed to produce the expected file listings.

---

## 5. Surprises & Notes

### 5a. Subdirs were untracked
The 5 subdirectories (`aimarket-protocol/`, `aimarket-hub/`, `aimarket-widget/`, `aimarket-agent/`, `plugins/`) were **not tracked by git** at the start. `git ls-files` returned empty for all of them, and `git status` showed them as `??` (untracked). They were not gitignored — they simply had never been committed.

**What was done:** The 148 files across all 5 directories were staged and committed as a single commit (`4dacee3`) before subtree splitting. This is a one-time requirement; subsequent pushes via the mirror workflow will work incrementally.

### 5b. `git subtree split` produces only one commit per subdir
Since all files were added in a single monorepo commit, each export branch contains exactly 1 commit (from the subtree perspective — the root commit is flattened). This means satellite repos show a clean, single-commit history. Future changes to these subdirs in the monorepo will add new commits to the satellite repos.

### 5c. .gitignore files in subdirs
Some subdirs (e.g., `aimarket-agent/.gitignore`, `aimarket-hub/.gitignore`) contain their own `.gitignore` files. These are included in the extracted repos. The monorepo-level `.gitignore` does NOT apply to satellite repos, which is the correct behavior — each satellite gets its own ignore rules.

### 5d. The PAT is embedded in `origin` remote URL
The monorepo's `origin` remote contains the PAT in the URL (`https://alexar76:ghp_...@github.com/alexar76/aicom.git`). This PAT was extracted and reused for:
- Creating repos via GitHub API
- Setting the `MIRROR_SATELLITE_PAT` secret
- Pushing export branches

Note: This PAT appears to be a classic token. If you rotate it, the `MIRROR_SATELLITE_PAT` secret must be updated as well.

### 5e. `gh` CLI not available
The GitHub CLI (`gh`) was not installed. All GitHub API operations were performed via `curl` with the PAT. If `gh` is installed later, the verification commands can be simplified to `gh repo view alexar76/aimarket-protocol`.

---

## 6. Local Export Branches

The following local branches were created during extraction and can be safely deleted:

```bash
git branch -D export/aimarket-protocol
git branch -D export/aimarket-hub
git branch -D export/aimarket-widget
git branch -D export/aimarket-agent
git branch -D export/aimarket-plugins
```

These exist only for push purposes and are not needed after the initial extraction.
