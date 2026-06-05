# Trust sprint — profile + ecosystem landing (≤1 h)

Goal: fix the two trust leaks before awesome-list PRs or outbound posts.

| # | Task | Owner | Est. |
| --- | --- | --- | --- |
| 1 | Publish profile README | alexar76 | 15 min |
| 2 | Push landing fix → GitHub Pages | alexar76 | 10 min |
| 3 | Run link verifier | anyone | 2 min |
| 4 | Smoke live demos | anyone | 10 min |
| 5 | (Next day) awesome-sdks PR | alexar76 | 30 min |

---

## 1. Profile README

**Source:** [`scripts/profile-readme/README.md`](README.md)  
**Steps:** [`PUBLISH.md`](PUBLISH.md)

**Done when:**

- [ ] https://github.com/alexar76/alexar76 exists and is public
- [ ] Profile shows **Start here** table (factory, monitor, hub, pip, YouTube)
- [ ] `orchestration-course` listed under 3D visualization, learning & sample apps

---

## 2. Ecosystem landing on GitHub Pages

**Monorepo commit:** `fix(ecosystem-landing): point GitHub links at satellite repos` (includes `ecosystem-landing/index.html`).

From a clone with **write access** to `github.com/alexar76/aicom`:

```bash
git push git@github.com:alexar76/aicom.git main
# or: git push https://github.com/alexar76/aicom.git main
```

**Pages:** repo **Settings → Pages → Source: GitHub Actions** (workflow `.github/workflows/pages-ecosystem.yml`).

Wait for workflow **Deploy ecosystem landing to GitHub Pages** (green).

**Done when:**

- [ ] https://alexar76.github.io/aicom/ project cards use `github.com/alexar76/<repo>` (not `aicom/tree/main/...`)
- [ ] Flow text says **invokable** (not invocable)
- [ ] Academy line has no `<code>` break around `aimarket-agent`

---

## 3. Verify GitHub links (automated)

From monorepo root:

```bash
./scripts/verify_ecosystem_landing_links.sh
./scripts/verify_ecosystem_landing_links.sh --live https://alexar76.github.io/aicom/
```

Expect: all satellite URLs **200** (or 301→200); `contracts` may stay under `aicom/tree/main/contracts`.

---

## 4. Smoke live demos

| URL | Expect |
| --- | --- |
| https://magic-ai-factory.com | Homepage loads, hero video |
| https://magic-ai-factory.com/admin/login | Login form |
| https://magic-ai-factory.com/monitor/ | Alien Monitor UI |
| https://magic-ai-factory.com/pulse/ | Pulse Terminal |
| https://modelmarket.dev | Hub / well-known |
| https://alexar76.github.io/aicom/ | Ecosystem landing |

---

## 5. Next day — distribution (optional)

Patches ready in `docs/awesome-submissions/`:

1. **e2b-dev/awesome-sdks-for-ai-agents** — `aimarket-agent` + `aimarket-sdks` (`e2b-awesome-sdks.patch.md`)
2. **slavakurilyak/awesome-ai-agents** — `aicom` factory (`slavakurilyak-awesome-ai-agents.patch.md`)
3. **punkpeye/awesome-mcp-servers** — MCP packager via `aimarket-plugins`

Run only **after** steps 1–3 pass — reviewers click GitHub links.

Full playbook: [`docs/awesome-list-submissions.md`](../../docs/awesome-list-submissions.md).

---

## Hygiene backlog (not blocking sprint)

- [ ] Replace `github.com/ai-factory/*` → `alexar76/*` in hub badge + plugin `homepage` fields
- [ ] Fix `alexar76/aimarket` → `aimarket-protocol` in `capability-composer/README.md`
- [ ] PyPI `aimarket-agent` description: shorten mirror banner for public readers (optional)
