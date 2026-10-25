import { describe, expect, it } from 'vitest';
import { cn, formatCurrency, truncate } from './utils';

describe('Tailwind 4 class conflict resolution', () => {
  it('replaces migrated shadow and blur scales instead of retaining both', () => {
    expect(cn('shadow-xs', 'shadow-sm')).toBe('shadow-sm');
    expect(cn('backdrop-blur-xs', 'backdrop-blur-md')).toBe('backdrop-blur-md');
  });

  it('preserves independent layout, color and radius classes', () => {
    expect(cn('p-4 rounded-sm bg-indigo-500', 'p-6'))
      .toBe('rounded-sm bg-indigo-500 p-6');
  });
});

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
