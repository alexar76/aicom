import { getStoredReferral } from './referral';
import { csrfHeaders } from './csrf';

type Meta = Record<string, unknown>;

function postEvent(body: {
  event: string;
  path?: string;
  product_id?: string;
  referral?: string;
  meta?: Meta;
}) {
  if (typeof window === 'undefined') return;
  const payload = JSON.stringify(body);
  void fetch('/api/marketing/analytics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

export function trackEvent(event: string, meta?: Meta, productId?: string) {
  const referral = getStoredReferral();
  postEvent({
    event,
    path: typeof window !== 'undefined' ? window.location.pathname : undefined,
    product_id: productId,
    referral: referral ?? undefined,
    meta: meta ?? {},
  });
}

export async function submitLead(input: {
  email: string;
  idea: string;
  name?: string;
  company?: string;
  source?: string;
}): Promise<{
  ok: boolean;
  message?: string;
  status_token?: string;
  status_url?: string;
  product_id?: string;
  pipeline_started?: boolean;
}> {
  const res = await fetch('/api/marketing/lead', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify({
      email: input.email,
      idea: input.idea,
      name: input.name,
      company: input.company,
      source: input.source ?? 'lead_page',
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { detail?: string }).detail || 'Failed to submit');
  }
  return data;
}

export function buildProductShareUrl(productId: string): string {
  const origin =
    typeof window !== 'undefined' ? window.location.origin : '';
  const u = new URL(`${origin}/product/${encodeURIComponent(productId)}`);
  u.searchParams.set('utm_source', 'share');
  u.searchParams.set('utm_medium', 'link');
  u.searchParams.set('utm_campaign', 'product');
  return u.toString();
}
