import { describe, expect, it } from 'vitest';
import { computePipelineProductVitals } from './pipelineProductVitals';
import type { PipelineCatalogProduct } from '@/components/admin/pipeline/PipelineProductList';

const locale = 'en' as const;

describe('computePipelineProductVitals', () => {
  it('uses real LLM spend and stage progress (not fake 95% ETA)', () => {
    const product = {
      id: 'p1',
      state: 'CODE_COMMITTED',
      economics: {
        llm_cost_usd: 2.45,
        llm_call_count: 12,
        llm_total_tokens: 8000,
        pipeline_cost_cap_usd: 0,
      },
      pulse: {
        completed_stages: 7,
        total_stages: 11,
        eta_label: '~2h left',
        quality_pulse: 'amber',
        quality_hint: 'Build progressing',
      },
    } as PipelineCatalogProduct;

    const v = computePipelineProductVitals(product, locale);
    expect(v.costUsd).toBe(2.45);
    expect(v.costPct).toBeNull();
    expect(v.progressPct).toBe(64);
    expect(v.qualityPct).toBeNull();
  });

  it('does not use stage rings during DEV_FIXING (shows tasks or ETA only)', () => {
    const product = {
      id: 'p-repair',
      state: 'DEV_FIXING',
      task_counts: { total: 0, completed: 0 },
      pulse: {
        completed_stages: 10,
        total_stages: 11,
        eta_label: '~67 min left',
        quality_pulse: 'amber',
        quality_hint: 'Awaiting demo gate telemetry',
      },
    } as PipelineCatalogProduct;

    const v = computePipelineProductVitals(product, locale);
    expect(v.progressPct).toBeNull();
    expect(v.progressDetail).toContain('67');
    expect(v.qualityPct).toBeNull();
    expect(v.qualityDetail).toContain('Awaiting');
  });

  it('shows QA gate fail percent from catalog fields', () => {
    const product = {
      id: 'p-gates',
      state: 'DEV_FIXING',
      qa_gates_all_passed: false,
      pulse: {
        completed_stages: 10,
        total_stages: 11,
        quality_pulse: 'red',
        quality_hint: 'Demo gates failed',
      },
    } as PipelineCatalogProduct;

    const v = computePipelineProductVitals(product, locale);
    expect(v.qualityPct).toBe(0);
    expect(v.qualitySource).toBe('qa_gates');
  });

  it('maps human quality score 1-5 to percent', () => {
    const product = {
      id: 'p2',
      state: 'COMPLETED',
      economics: { llm_cost_usd: 0.5, quality_score: 4 },
      pulse: { completed_stages: 11, total_stages: 11, quality_pulse: 'unknown' },
    } as PipelineCatalogProduct;

    const v = computePipelineProductVitals(product, locale);
    expect(v.qualityPct).toBe(80);
    expect(v.qualitySource).toBe('human_score');
    expect(v.progressPct).toBe(100);
  });
});
