import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it('an expired-session API response preserves the intended creation tab through login', async () => {
  const location = { origin: 'https://factory.example', pathname: '/admin', search: '?tab=new-product', hash: '', href: 'https://factory.example/admin?tab=new-product' };
  const storage = { getItem: () => null, removeItem: vi.fn() };
  vi.stubGlobal('window', { location, localStorage: storage });
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401, headers: { 'Content-Type': 'application/json' } })));
  const { default: api } = await import('./api');
  await expect(api.getMe()).rejects.toThrow();
  expect(location.href).toBe('/admin/login?next=%2Fadmin%3Ftab%3Dnew-product');
});
