/**
 * Retries + persistent outbound queue for the storefront Support widget when the API is flaky.
 */

export type SupportUiContext = {
  current_page?: string;
  active_tab?: string;
  selected_product_id?: string;
};

export type QueuedSupportMessage = {
  id: string;
  text: string;
  /** JSON-serialized SupportUiContext */
  uiContextJson: string;
  addedAt: number;
};

const QUEUE_KEY = 'aif_support_out_q_v1';
const MAX_QUEUE = 30;

function safeParseContext(json: string): SupportUiContext | undefined {
  try {
    const o = JSON.parse(json) as SupportUiContext;
    return typeof o === 'object' && o ? o : undefined;
  } catch {
    return undefined;
  }
}

export function loadOutboundQueue(): QueuedSupportMessage[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    const j = JSON.parse(raw) as unknown;
    if (!Array.isArray(j)) return [];
    return j
      .filter(
        (x): x is QueuedSupportMessage =>
          typeof x === 'object' &&
          x !== null &&
          typeof (x as QueuedSupportMessage).id === 'string' &&
          typeof (x as QueuedSupportMessage).text === 'string'
      )
      .slice(-MAX_QUEUE);
  } catch {
    return [];
  }
}

export function saveOutboundQueue(items: QueuedSupportMessage[]): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-MAX_QUEUE)));
  } catch {
    /* quota / private mode */
  }
}

export function enqueueOutboundMessage(
  prev: QueuedSupportMessage[],
  text: string,
  ctx: SupportUiContext | undefined
): QueuedSupportMessage[] {
  const id = `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const uiContextJson = JSON.stringify(ctx ?? {});
  const next = [
    ...prev,
    { id, text: text.slice(0, 4000), uiContextJson, addedAt: Date.now() },
  ].slice(-MAX_QUEUE);
  saveOutboundQueue(next);
  return next;
}

export function removeOutboundById(prev: QueuedSupportMessage[], id: string): QueuedSupportMessage[] {
  const next = prev.filter((x) => x.id !== id);
  saveOutboundQueue(next);
  return next;
}

export function parseQueuedContext(row: QueuedSupportMessage): SupportUiContext | undefined {
  return safeParseContext(row.uiContextJson);
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Retry when network fails or server is overloaded — not for auth/validation errors. */
export function shouldRetrySupportSend(e: unknown): boolean {
  if (e instanceof TypeError) return true;
  const m = e instanceof Error ? e.message : String(e);
  if (/HTTP\s+5\d\d/.test(m)) return true;
  if (/HTTP\s+429/.test(m)) return true;
  if (/failed to fetch|network|Load failed|ECONNRESET|ETIMEDOUT|timeout/i.test(m)) return true;
  return false;
}

export function isSupportAuthError(e: unknown): boolean {
  const m = e instanceof Error ? e.message : String(e);
  return /401|403|410|invalid|expired/i.test(m);
}

/**
 * Runs fn up to `attempts` times with delays between failures (transient errors only).
 */
export async function withRetries<T>(
  fn: () => Promise<T>,
  options?: { attempts?: number; delaysMs?: readonly number[] }
): Promise<T> {
  const attempts = Math.max(1, options?.attempts ?? 4);
  const delays = options?.delaysMs ?? [0, 900, 2200, 5000];
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    if (i > 0) await sleep(delays[Math.min(i - 1, delays.length - 1)] ?? 1000 * i);
    try {
      return await fn();
    } catch (e) {
      last = e;
      const retry = shouldRetrySupportSend(e);
      if (!retry || i === attempts - 1) throw e;
    }
  }
  throw last;
}
