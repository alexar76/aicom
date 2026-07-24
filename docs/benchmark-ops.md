# Benchmark Operations Guide

This guide explains how to run repeatable quality benchmarks on the factory using fresh product ideas.

## Goal

Measure whether the system consistently produces marketplace-ready products at scale (not just one-off successes).

Primary KPI:
- **Pass rate** = `completed / total` for a batch of fresh ideas

Supporting KPIs:
- failed count
- unresolved count (timed out / still processing)
- average pipeline time (optional future extension)

## Inputs

- Backend/admin API running (default expected at `http://127.0.0.1:8081`)
- Idea batch file (20-50 ideas), one idea per line
  - Example starter file: `scripts/benchmark_ideas.example.txt`
  - **Full_software-focused prompts** (dashboard/auth/API): `scripts/benchmark_full_software.txt`

## Run benchmark

Basic run (20 ideas, production mode):

```bash
python scripts/benchmark_pass_rate.py \
  --ideas-file scripts/benchmark_ideas.example.txt \
  --base-url http://127.0.0.1:8081 \
  --count 20 \
  --timeout-min 60 \
  --production-mode \
  --output benchmark_report.json
```

Larger run (50 ideas):

```bash
python scripts/benchmark_pass_rate.py \
  --ideas-file scripts/benchmark_ideas.example.txt \
  --base-url http://127.0.0.1:8081 \
  --count 50 \
  --timeout-min 120 \
  --production-mode \
  --output benchmark_report_50.json
```

## Output

The script prints and stores JSON report:

- `count`
- `completed`
- `failed`
- `unresolved`
- `pass_rate` (0.0-1.0)
- `products[]` with per-product state

## Suggested release thresholds

Use thresholds as policy gates before broad rollout:

- `pass_rate >= 0.80` for internal production readiness
- `pass_rate >= 0.90` for public scaling confidence
- `unresolved <= 0.10 * count`

If below threshold, inspect failures and tune:

- QA realism / acceptance traceability
- runtime backend E2E
- UX/a11y checks
- release score weight configuration

## Failure triage checklist

1. Sample failed products from `products[]` list
2. Inspect QA report:
   - `/app/data/bugs/<product_id>/qa_report.json`
3. Check gates:
   - demo quality
   - browser E2E
   - backend runtime E2E
   - acceptance traceability
   - maintainability review
4. Check architecture novelty and marketplace gate reasons
5. Adjust prompts/gates/env weights and re-run benchmark

## Notes

- Keep benchmark ideas stable between runs when comparing versions.
- Run with same env/gate config to compare apples-to-apples.
- Track pass-rate trend across commits to verify real progress.
