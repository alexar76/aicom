# Sample factory output (no Docker required)

Static artifacts so visitors can see **what AI-Factory produces** without
running the pipeline.

> **Honest tier:** These are **MVP storefront** examples (landing + basic SaaS shell) — not
> proof of complex long-lived software. External reviews fairly note shipped demos skew simple.
> See [`factory-pipeline-profiles.md`](../factory-pipeline-profiles.md) and
> [`ecosystem-maturity-review.en.md`](../ecosystem-maturity-review.en.md).

| File | Description |
|------|-------------|
| [`build-replay-spliteasy.json`](build-replay-spliteasy.json) | Public **build replay** for a fictional “SplitEasy” SaaS — same JSON shape as `GET /api/public/build/{id}`. No prompts, secrets, or raw agent output. |

Regenerate after changing `web/backend/services/build_replay.py`:

```bash
python scripts/export_sample_build_replay.py
```

Live demo (Docker): `./scripts/quickstart.sh` or `./demo.sh --landing`.
