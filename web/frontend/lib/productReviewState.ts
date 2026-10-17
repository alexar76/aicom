import type { Product } from './api';

// A completed pipeline alone is not evidence of passing QA. Explicit failure wins.
export function productReviewState(product: Product): 'verified' | 'review' | 'unknown' {
  const gates = [product.qa_gates_all_passed, product.telemetry_qa_gates_passed, product.marketplace_listing_fields?.telemetry_qa_gates_passed];
  if (gates.includes(false) || product.marketplace_quality?.eligible === false || product.state !== 'COMPLETED') return 'review';
  return gates.includes(true) ? 'verified' : 'unknown';
}
