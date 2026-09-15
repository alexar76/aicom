/**
 * Maps API / network failures to human copy plus concrete next steps (links into Admin).
 */

import { ApiRequestError } from './api';

export type ActionableLink = {
  label: string;
  href: string;
};

export type ResolvedFailure = {
  title: string;
  detail: string;
  actions: ActionableLink[];
};

function uniqActions(actions: ActionableLink[]): ActionableLink[] {
  const seen = new Set<string>();
  const out: ActionableLink[] = [];
  for (const a of actions) {
    const k = `${a.label}|${a.href}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(a);
  }
  return out;
}

/**
 * Turn any thrown value from `api.request` (or fetch) into title, body, and deep links.
 */
export function resolveActionableFailure(
  error: unknown,
  context?: { operation?: string },
): ResolvedFailure {
  const message = error instanceof Error ? error.message : String(error);
  const status = error instanceof ApiRequestError ? error.status : undefined;
  const op = (context?.operation || '').toLowerCase();
  const m = message.toLowerCase();
  const actions: ActionableLink[] = [];

  const providers = { label: 'Open LLM providers', href: '/admin?tab=providers' };
  const llmLogs = { label: 'Open LLM request logs', href: '/admin?tab=llm-logs' };
  const settings = { label: 'Open factory settings', href: '/admin?tab=settings' };
  const pipeline = { label: 'Open pipeline', href: '/admin?tab=pipeline' };
  const workshop = { label: 'Open Workshop', href: '/admin?tab=workshop' };
  const login = { label: 'Sign in again', href: '/admin/login' };

  if (status === 401) {
    return {
      title: 'Session expired or not signed in',
      detail: message,
      actions: [login],
    };
  }

  if (status === 403) {
    actions.push({ label: 'Read admin roles (docs)', href: '/admin?tab=settings' });
    return {
      title: 'Not allowed for your role',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (status === 429) {
    actions.push(settings);
    return {
      title: 'Too many requests',
      detail: message,
      actions: uniqActions([{ label: 'Open settings (rate limits)', href: '/admin?tab=settings' }, ...actions]),
    };
  }

  if (status === 404) {
    if (m.includes('architecture') || m.includes('specification')) {
      actions.push(pipeline, workshop);
      return {
        title: 'Artifact not found for this product',
        detail: message,
        actions: uniqActions(actions),
      };
    }
    actions.push(pipeline);
    return {
      title: 'Not found',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (status === 503 || status === 502) {
    actions.push(settings, providers);
    return {
      title: 'Service temporarily unavailable',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (
    status === 0 ||
    m.includes('network') ||
    m.includes('failed to fetch') ||
    m.includes('load failed') ||
    m.includes('aborted') ||
    m.includes('timeout')
  ) {
    actions.push(settings);
    if (op.includes('prefill') || op.includes('llm')) {
      actions.push(providers, llmLogs);
    }
    return {
      title: 'Could not reach the server',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (m.includes('consent must be true')) {
    return {
      title: 'AI call blocked',
      detail: 'Enable the consent checkbox before running an LLM-backed suggestion.',
      actions: [],
    };
  }

  if (
    m.includes('no available provider') ||
    m.includes('runtimeerror') ||
    m.includes('llm') ||
    m.includes('model') ||
    m.includes('openai') ||
    m.includes('anthropic') ||
    m.includes('ollama')
  ) {
    actions.push(providers, llmLogs);
    return {
      title: 'LLM routing or provider issue',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (m.includes('pywebpush') || m.includes('vapid')) {
    actions.push(settings);
    return {
      title: 'Web Push not fully configured',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  if (status && status >= 500) {
    actions.push(settings);
    return {
      title: 'Server error',
      detail: message,
      actions: uniqActions(actions),
    };
  }

  actions.push(settings);
  return {
    title: 'Something went wrong',
    detail: message,
    actions: uniqActions(actions),
  };
}
