# Publishing finished products to an MIT monorepo

**Status: prepared, not built.** Nothing here creates a repository, mints a token or pushes anything.
This is the design plus the exact list of what is left to do and who does it.

The factory publishes; a human merges. The token belongs to the user and is scoped so that the worst
a compromised factory can do is open a pull request nobody has to accept.

---

## 1. What it is

Two tiers, decided by the user: a **public** monorepo that is the catalogue of what the factory has
made, and one **per-product repository** the factory creates, **private by default**, public by
setting.

```
<products-monorepo>            PUBLIC — the catalogue
  LICENSE                      MIT, repo-wide
  README.md                    generated index: product, one line, live URL, published date
  products/
    sentinel-safety-agent/
      LICENSE                  MIT again — a copied directory must carry its own terms
      README.md                what it is, how to run it, the live URL
      PUBLICATION.json         provenance: product id, factory commit, gate report, deploy URL, date
      backend/ frontend/ ...   the tree — ONLY for products cleared as public (see below)

<product-repo> per product     PRIVATE by default, public by setting
  the full tree, always, whatever the catalogue carries
```

Two licence files is deliberate. People copy a single product directory out and lose the root
licence; a directory that cannot state its own terms is a directory nobody can safely reuse.

`PUBLICATION.json` is the receipt: which gates passed, at which score, against which deployed URL.
It is what makes a published product auditable a year later, and it is the natural place to attach an
[AWR](../awr/README.md) work receipt if we want the provenance signed rather than merely asserted.

### The one tension in this shape, and how it resolves

A public catalogue plus a private-by-default product repository can contradict each other: dropping a
product's tree into the public catalogue publishes that code no matter how private its own repository
is. The private default would then be decoration.

So the two tiers carry different things by default:

| | Catalogue entry (public) | Product repo (private by default) |
|---|---|---|
| name, one-line description | always | — |
| live URL | always | — |
| `PUBLICATION.json` gate report | always | — |
| MIT `LICENSE` | always | always |
| the product's source tree | **only when the product is marked public** | always |

Listing name, URL and gate report discloses nothing new: the deployment is already reachable by
anyone with the link, and the gate report is a statement about our own quality bar. The **code** is
the part that stays behind the setting.

If the intent is instead that everything in the catalogue is public code and the private repos are
just where products live before promotion, that also works — say so and the table above collapses to
"the catalogue only ever contains products marked public". Both are coherent; they are different
promises to the reader.

---

## 2. When a product may be published

The user's instinct — *"when it converges to zero errors and passes review, is properly completed,
deployed to Vercel and finally tested"* — is right, and it needs to be a predicate rather than a
feeling. Proposed, and needing sign-off before anything is built:

| # | Condition | Why this one |
|---|---|---|
| 1 | Pipeline state is `COMPLETED` | Not `HUMAN_REVIEW_PENDING`, not parked. A parked product is a product with an open question. |
| 2 | Every **voting** gate green: `module_health`, `frontend_build`, `api_contract`, `demo_journey`, `backend_realism` | These are the gates measured to return the same number twice for the same tree. |
| 3 | All static counters zero: `missing_attribute`, `missing_module`, `missing_symbol`, `duplicate_tablename`, `mesh_contract_violation` | Implied by (2), stated anyway: this is the set that predicts "it actually starts". Each of these was invisible to the pipeline as recently as today. |
| 4 | `qa_defect_score == 0` over the voting gates | This is the "zero errors" line. Deliberately **not** zero findings overall — a browser crawl will always have an opinion about a heading, and an unrepeatable gate must not hold a release hostage. |
| 5 | No open `critical` or `high` from the security and design reviews | Review passed, in the sense the user means. |
| 6 | A **live** URL answers `200` and serves the product's own content | Deploy exiting 0 is not evidence. Every published product URL once 302'd to Vercel SSO while every deploy reported success. `verify_published_url()` in `web/backend/services/auto_publish.py` already exists for exactly this and refuses to follow the redirect. |
| 7 | The demo journey re-run against the **deployed** URL, not the sandbox | The sandbox proves the tree; only the deployment proves the deployment. |
| 8 | `LICENSE` present and the tree carries no third-party code with an incompatible licence | MIT is a promise about the whole directory. |
| 9 | Hard secret scan clean | `scripts/verify_mirror_secrets.sh` plus an explicit deny-list of `.env`, `data/secrets/`, key material and private hosts. An rsync publish once leaked a real key because the excludes were implicit. Excludes must be explicit and the scan must fail closed. |

A product failing any condition is not published and the reason is recorded, not swallowed.

**Re-publication.** A product already in the monorepo that changes gets a new PR whose body diffs the
gate report against the published one. Never a force-push: the monorepo is append-only history, the
same rule as the live satellites.

---

## 3. The token, and two constraints worth knowing before it is minted

**Constraint one — a PR needs a branch.** GitHub cannot express "may only open pull requests" for a
branch in the same repository: opening a PR requires the branch to exist, and pushing a branch
requires **Contents: write**. So there are two honest options.

**Option A — one repo, two permissions (simpler).**
Fine-grained PAT, scoped to that single repository:

- `Contents: Read and write` — required to push the branch
- `Pull requests: Read and write` — required to open the PR
- nothing else; no org scope, no workflow scope

Then protect `main` in repository settings: require a pull request, require a review, forbid force
pushes and deletions. The token can create branches and PRs; it cannot land anything.

**Option B — fork and PR (genuinely PR-only upstream).**
A bot account owns a fork. The token is scoped to the **fork** with Contents+PR write, and has no
permission at all on the upstream repository beyond opening PRs from the fork. Costs one extra
account; gives a token that genuinely cannot write to the published repo.

Recommendation: **Option A with branch protection**, moving to B if the factory ever publishes on
behalf of more than one owner. Whichever is chosen, the token is stored the way the mirror tokens
are — macOS keychain for local use, docker secret in production — never in the tree, never in an
image layer.

**Constraint two — creating a repository is not a pull request.** "The factory makes the sub-repos"
cannot be done with a PR-scoped token at all: repository creation needs `Administration: write` at the
account or organisation level, which is a far larger permission than anything else here — with it, the
token can create, rename and delete repositories across that account.

Three ways out, in order of how much they give away:

1. **A dedicated organisation for factory products.** The token gets `Administration: write` scoped to
   that org and nothing else, so the blast radius is products only and never the monorepo source of
   truth or the satellites. This is the one to pick if the factory should really create repos.
2. **Pre-created repositories.** The user creates the product repo when they approve the product; the
   factory only pushes into it. Keeps the token small, adds a manual step per product.
3. **Catalogue-only publishing.** The factory never creates anything: it opens a PR against the public
   catalogue, and per-product repositories are made by hand if and when a product deserves one.

Worth deciding before the token is minted, because it decides which token to mint. Note that (1)
still keeps the *catalogue* token separate: two tokens, one per tier, is strictly safer than one token
that can do both.

---

## 4. Settings

Off unless switched on, and private unless switched public. Both defaults are the safe direction:
publishing is irreversible in the way that matters — a repository that was public for an hour has
been read.

| Setting | Default | Meaning |
|---|---|---|
| `AIFACTORY_PUBLISH_MONOREPO` | `0` | Master switch. Off means the gate is evaluated and logged, and no PR is opened. |
| `AIFACTORY_PUBLISH_REPO` | — | `owner/name` of the monorepo. Absent means off regardless of the switch. |
| `AIFACTORY_PUBLISH_TOKEN` | — | The PR token. Fail closed if missing. |
| `AIFACTORY_PUBLISH_VISIBILITY` | `private` | Visibility for a newly created **product repository**. The catalogue itself is public by decision, not by this setting. |
| `AIFACTORY_PUBLISH_CATALOGUE_CODE` | `0` | Whether a product's source tree goes into the public catalogue, not just its entry. Off means catalogue entries carry name, URL, gate report and licence only. |
| `AIFACTORY_PUBLISH_CREATE_REPOS` | `0` | Whether the factory may create per-product repositories at all. Needs the larger token from §3; off means repositories are pre-created by hand. |
| `AIFACTORY_PUBLISH_REQUIRE_LIVE_URL` | `1` | Condition 6. Turning it off must be a deliberate act with a log line. |
| product extra `publish_visibility` | inherits | Per-product `private` \| `public`. Needs adding to `PRODUCT_EXTRA_KEYS`, or SQLite silently drops it. |
| product extra `publish_opt_out` | `false` | A product that must never be published, whatever the gate says. |

The catalogue is public by decision and is not governed by a setting — nothing should be able to flip
it quietly in either direction. What the settings govern is what a catalogue entry *contains* and
whether a per-product repository is created and at what visibility.

---

## 5. What already exists and should be reused

| Need | Existing piece |
|---|---|
| Live-URL check that does not follow the SSO redirect | `verify_published_url()` in `web/backend/services/auto_publish.py` |
| Secret gate before a publish | `scripts/verify_mirror_secrets.sh`, forbidden hosts from `scripts/.mirror-forbidden-hosts` |
| Per-target repo mapping and append-only mirroring | `scripts/mirror_satellites.sh`, `scripts/satellite-map.yaml` (`history: live` mode) |
| Gate results per product | `data/bugs/<product>/qa_report.json` — `*_passed` flags and `blocking_defects` |
| Score arithmetic for condition 4 | `core/round_regression_guard.qa_defect_score` + `GUARD_SCORED_GATES` |
| Deploy record and URL | product extras `vercel_url` / `published_url` |

The publisher itself is new code: gate evaluation, tree export with explicit excludes, licence and
README generation, `PUBLICATION.json`, branch + PR via the GitHub API.

---

## 6. Left for the user

The user creates the repository and mints the token themselves — that is settled. What is left to
decide is which token, and that follows from §3:

1. Create the catalogue monorepo, **public**, and turn on branch protection on `main`: PR required,
   review required, force-push and deletion denied. Protection is what makes a `Contents: write`
   token safe.
2. Mint the catalogue token — Option A (`Contents` + `Pull requests`, that repo only) unless the
   fork flow is preferred.
3. Decide whether the factory creates per-product repositories itself. If yes, a **dedicated
   organisation** for them and a second token scoped to it; if no, keep `AIFACTORY_PUBLISH_CREATE_REPOS`
   off and pre-create each repo on approval.
4. Confirm §2 condition 4, where "zero errors" gets its precise meaning, and the §1 table — whether a
   public catalogue entry carries the source tree by default or only for products marked public.
5. Store each token as a docker secret on the production host.

Then the publisher gets built against a gate that has already been agreed, rather than one invented
at implementation time.

---

## 7. Note on an existing rule

The standing rule in this workspace is: never push to GitHub, Gitea only. This is a deliberate,
narrow exception, and it is worth stating so nobody has to re-derive it: **the factory** publishes
**finished products** to **one** repository with a token that cannot merge. The monorepo source of
truth stays where it is. Nothing about this changes how the factory's own code is mirrored.
