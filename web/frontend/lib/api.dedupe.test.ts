/**
 * Identical GETs that overlap must reach the network once.
 *
 * The admin console loads the same endpoints from several independent places, so one
 * dashboard render measured 18 requests for 11 distinct endpoints. With the HTTP firewall
 * allowing 100 requests per minute per IP across every route, that made the console
 * rate-limit itself: about ten tab switches and everything answered 403, /admin/auth/me
 * included, which the UI reads as a lost session.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api from './api';

type FetchCall = { url: string; method: string };

let calls: FetchCall[] = [];
let resolvers: Array<(body: unknown) => void> = [];

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  calls = [];
  resolvers = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        url: String(input),
        method: String(init?.method || 'GET').toUpperCase(),
      });
      // Stay pending until the test releases it, so overlap is deterministic.
      return new Promise<Response>((resolve) => {
        resolvers.push((body) => resolve(jsonResponse(body)));
      });
    }),
  );
  vi.stubGlobal('document', { cookie: '' } as unknown as Document);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GET coalescing', () => {
  it('sends one request for two overlapping identical GETs', async () => {
    const a = api.getDashboardPipelineSummary();
    const b = api.getDashboardPipelineSummary();

    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(1);

    resolvers.forEach((r) => r({ total_products: 7 }));
    const [ra, rb] = await Promise.all([a, b]);
    expect(ra.total_products).toBe(7);
    expect(rb.total_products).toBe(7);
  });

  it('gives each caller its own object, so one cannot mutate the other', async () => {
    const a = api.getDashboardPipelineSummary();
    const b = api.getDashboardPipelineSummary();
    resolvers.forEach((r) => r({ total_products: 1 }));
    const [ra, rb] = await Promise.all([a, b]);

    (ra as { total_products: number }).total_products = 999;
    expect(rb.total_products).toBe(1);
  });

  it('does not coalesce across a settle — nothing is cached', async () => {
    const first = api.getDashboardPipelineSummary();
    resolvers.forEach((r) => r({ total_products: 1 }));
    await first;

    const second = api.getDashboardPipelineSummary();
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(2);
    resolvers.forEach((r) => r({ total_products: 2 }));
    await second;
  });

  it('never coalesces a mutation — two POSTs must both be sent', async () => {
    const a = api.recordTelemetryEvent({ event: 'audit' } as never);
    const b = api.recordTelemetryEvent({ event: 'audit' } as never);

    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2);

    resolvers.forEach((r) => r({ ok: true }));
    await Promise.all([a, b]);
  });
});
