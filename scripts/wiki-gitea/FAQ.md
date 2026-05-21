# FAQ

> **Detailed FAQ:** [`docs/FAQ.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.md)  
> **Russian:** [[FAQ-RU]] · [`docs/FAQ.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.ru.md)  
> **Spanish:** [[FAQ-ES]] · [`docs/FAQ.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.es.md) · [`docs/USER_GUIDE.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.es.md)

## What is AI-Factory?

Self-hosted multi-agent pipeline: idea → spec → code → QA/E2E → security → deploy → optional storefront.

## Storefront vs Admin?

- **Storefront** — filtered marketplace-ready products  
- **Admin → Pipeline** — all products, all stages (source of truth)

## Default password?

**None** in repo. Bootstrap via TTY or `data/secrets/bootstrap_admin.txt`. Demo host `magic-ai-factory.com` uses `demo123` only there.

## How long does a run take?

| Type | Typical |
|------|---------|
| `marketing_landing` | ~20–25 min (DeepSeek, no long repair loops) |
| `full_software` | ~25–45 min simple brief; hours with gate iterations |

## LLM cost?

Roughly **$0.30–$2** landing first pass; **$3–15+** full_software with QA cycles. Bring your own keys.

## Why is my product stuck in repair?

Gate failure (demo/TZ, browser crawl, security, methodologist). State: `BUG_FOUND` → `DEV_FIXING`. Check **Pipeline** tab errors and **LLM Logs**.

## `AIFACTORY_GATE_FAILING_MODEL`?

Optional **model id override** on the **same** LLM provider during repair rounds (`quality_repair_round ≥ 1`). Does not switch providers. Example: DeepSeek-only fleet → set `deepseek-reasoner` for hard fixes.

## `AIFACTORY_MAX_QUALITY_LOOPS`?

Caps policy audit / remediation cycles before **FAILED** (default **8**).

## Discovery not creating products?

Check Director scheduler, `AIFACTORY_DISCOVERY_INTERVAL_HOURS`, source health at `data/discovery/source_health.json`, and admin `POST /api/admin/discovery/run`.

## Gallery images missing on GitHub README?

Gallery lives in repo `docs/gallery/*.webp`. Some mirrors omit binary paths — clone from Gitea or refresh with `scripts/capture_gallery_landings.py`.

## More

[[Pipeline]] · [[Security]] · [[Owner-Guide]] · [`docs/FAQ.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.md)
