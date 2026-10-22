import { describe, expect, it } from 'vitest';
import { isProductId } from './productId';

describe('product id', () => {
  it.each(['prod-be897507f746', 'prod-demo-landing-studio', 'prod-demo-market-01'])('accepts %s', id => {
    expect(isProductId(id)).toBe(true);
  });
  it.each([undefined, null, '', 'undefined', 'null', 'prod-', 'product-1', 'prod-<script>', 'prod-a/../x'])('rejects %s', id => {
    expect(isProductId(id)).toBe(false);
  });
});
