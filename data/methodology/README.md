# Methodology knowledge (versioned baseline)

This directory mirrors the on-disk layout used at runtime under `{AIFACTORY_DATA_ROOT}/methodology/` (default `/app/data/methodology/` in Docker).

**Why it lives in git:** methodology memory (cases, optional lessons) is part of **quality discipline** — sample structure, regression examples, and team-owned lessons should be reviewable like code.

## Layout

| Path | Purpose |
|------|---------|
| `cases/<product_id>.json` | Per-product review history (post-spec / post-implementation), findings, scores. |
| `lessons.jsonl` | Optional operator or auto-promoted rules (JSONL). Create when first lesson is added. |
| `feedback.jsonl` | Optional operator feedback on past cases (JSONL). |

The `MethodologyKnowledgeStore` implementation is in `web/backend/services/methodology_knowledge.py`.

## Note on `cases/`

Filenames use real `prod-…` ids when copied from a dev environment for documentation or regression. Strip or anonymize before publishing if you treat case payloads as sensitive.
