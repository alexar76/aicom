import { describe, expect, it } from 'vitest';
import { adminReturnPath } from './adminReturnPath';

describe('admin login return path', () => {
  it.each(['/admin', '/admin?tab=new-product', '/admin?tab=pipeline#focus'])('preserves %s', path => {
    expect(adminReturnPath(path)).toBe(path);
  });
  it.each([null, '', 'https://example.com', '//example.com/admin', '/admin/login', '/administrator', '/admin/../checkout', '/admin?tab=x\n', '/admin?next=\\evil'])('rejects unsafe or unrelated destination %s', path => {
    expect(adminReturnPath(path)).toBe('/admin?tab=dashboard');
  });
});
