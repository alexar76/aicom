# AI-Factory — Wiki

**Self-hosted MIT factory:** plain-language idea → multi-agent pipeline → shippable web product (landing or full stack).

| | |
|---|---|
| **Live demo** | [magic-ai-factory.com](https://magic-ai-factory.com) |
| **Demo admin** | [admin/login](https://magic-ai-factory.com/admin/login) — `admin` / `demo123` *(demo host only)* |
| **Demo disclaimer** | Shared site — [`AIFACTORY_DEMO_READONLY=1`](Public-Demo) locks password, settings, backup/restore |
| **Source repo** | [Superowner/aicom](http://5.129.212.122/Superowner/aicom) |
| **Full docs in tree** | [`docs/`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/README.md) (50+ guides) |
| **YouTube** | [Idea → agents → shippable product](https://youtu.be/Gg9a52-ZbNA) |

---

## What it is

**AI-Factory** is a multi-agent pipeline you run on your own server: analyst, PM, architect, developer, QA/E2E, security, DevOps, marketing, and more. State and artifacts live on disk (`data/`), you bring your own LLM keys, and there is no per-seat cloud pricing.

**Typical wall-clock** (DeepSeek, without long repair loops): **marketing_landing ~20–25 min**; **full_software ~25–45 min** for a simple brief, up to **hours** when gates iterate.

---

## Quick start (self-hosted)

```bash
git clone http://5.129.212.122/Superowner/aicom.git
cd aicom && cp -n .env.example .env
docker compose up -d --build
# UI → http://localhost:9080/admin/login
```

There is **no** default admin password in the repo — see [[Security]] and [`docs/security.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/security.md).

More detail: [[Quick-Start]] · [[Deployment]]

---

## Wiki map

| Topic | Page |
|-------|------|
| Install and first product | [[Quick-Start]] |
| Platform owner | [[Owner-Guide]] |
| Pipeline, discovery, remediation | [[Pipeline]] |
| Admin UI and roles | [[Admin-Panel]] |
| Docker / production | [[Deployment]] |
| Passwords, CSRF, sandbox | [[Security]] |
| REST API | [[API-Integration]] |
| AI Market (AI-to-AI) | [[AI-Market-Protocol]] |
| Agents and gates | [[Agents]] |
| FAQ | [[FAQ]] |
| Architecture (Mermaid) | [[Architecture]] |
| Index of all `docs/` | [[Documentation-Index]] |
| Languages (EN / RU / ES policy) | [[Languages]] |
| Public demo mode | [[Public-Demo]] |

**Other languages (optional):** [[FAQ-RU]] · [`docs/USER_GUIDE.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.ru.md) · [[FAQ-ES]] · [`docs/USER_GUIDE.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.es.md)

---

## Positioning

Hosted builders (Bolt, Lovable, v0, Devin) offer a managed UI and integrations. **AI-Factory** is a transparent **self-hosted** pipeline: you own keys, gates, storefront policy, and the fork. Want zero ops → use them. Want agents, artifacts, and gates under your control → use this.

---

## Ship-then-keep-improving

1. **Ship** — product reaches **COMPLETED** / **DEPLOYED** when gates pass *at that moment*.
2. **Repair before ship** — `BUG_FOUND` → `DEV_FIXING` on demo/TZ, crawl, security, or methodologist failures.
3. **After ship** — policy audit and storefront remediation reopen products when rules tighten.
4. **Budget** — `AIFACTORY_MAX_QUALITY_LOOPS` (default **8**).
5. **Hard repairs** — optional `AIFACTORY_GATE_FAILING_MODEL` (model id on the **same** provider only).

Public counters: `GET /api/public/pipeline-status`.

---

## Pipeline (one line)

`Idea → Discovery → Analyst → PM → Architect → Developer → QA+E2E → Security → DevOps → Marketing → Sales → Evolution`

Canonical sequence: [`config/pipeline_flow.json`](http://5.129.212.122/Superowner/aicom/src/branch/main/config/pipeline_flow.json). Agent modules: [`agents/`](http://5.129.212.122/Superowner/aicom/src/branch/main/agents/).

Diagrams: [[Architecture]] · [`docs/architecture-diagrams.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/architecture-diagrams.md)

---

## Support

- Operators: [[Owner-Guide]] · [`docs/USER_GUIDE.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.md)
- Russian: [[FAQ-RU]] · [`docs/USER_GUIDE.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.ru.md)
- Spanish: [[FAQ-ES]] · [`docs/USER_GUIDE.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.es.md) · UI locale `es` — [[Languages]]
- Issues: Gitea tracker on the repository
