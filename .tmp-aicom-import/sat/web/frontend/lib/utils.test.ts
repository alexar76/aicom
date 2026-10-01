import { describe, expect, it } from 'vitest';
import { formatCurrency, truncate } from './utils';

describe('formatCurrency', () => {
  it('formats USDT amounts with two decimals', () => {
    expect(formatCurrency(12.3)).toMatchInlineSnapshot(`"12.30 USDT"`);
    expect(formatCurrency(0, 'USDC')).toMatchInlineSnapshot(`"0.00 USDC"`);
  });
});

describe('truncate', () => {
  it('leaves short strings unchanged', () => {
    expect(truncate('hello', 10)).toBe('hello');
  });

  it('adds ellipsis when over limit', () => {
    expect(truncate('abcdefghij', 5)).toBe('abcde...');
  });
});
