import { describe, expect, it } from 'vitest';
import { productReviewState } from './productReviewState';
import type { Product } from './api';
const base: Product = { id: 'example', idea: 'Example', created_at: 0, state: 'COMPLETED' };
describe('public review evidence', () => {
  it('does not infer QA success from completion or a marketplace badge', () => {
    expect(productReviewState(base)).toBe('unknown');
    expect(productReviewState({ ...base, marketplace_verified: true })).toBe('unknown');
  });
  it('requires explicit passed QA for a completed build', () => {
    expect(productReviewState({ ...base, qa_gates_all_passed: true })).toBe('verified');
    expect(productReviewState({ ...base, marketplace_listing_fields: { telemetry_qa_gates_passed: true } })).toBe('verified');
  });
  it('a failed check or current review state overrides an old passing snapshot', () => {
    expect(productReviewState({ ...base, qa_gates_all_passed: true, telemetry_qa_gates_passed: false })).toBe('review');
    expect(productReviewState({ ...base, qa_gates_all_passed: true, state: 'HUMAN_REVIEW' })).toBe('review');
    expect(productReviewState({ ...base, qa_gates_all_passed: true, marketplace_quality: { eligible: false } })).toBe('review');
  });
});
