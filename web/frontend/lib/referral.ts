const STORAGE_KEY = 'af_ref';

const SAFE_REF = /^[a-zA-Z0-9._-]{1,64}$/;

/**
 * On first visit, persist `?ref=` for checkout / analytics (must match backend regex).
 */
export function captureReferralFromUrl(): void {
  if (typeof window === 'undefined') return;
  const ref = new URLSearchParams(window.location.search).get('ref');
  if (ref && SAFE_REF.test(ref)) {
    try {
      localStorage.setItem(STORAGE_KEY, ref);
    } catch {
      // ignore quota / private mode
    }
  }
}

export function getStoredReferral(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && SAFE_REF.test(v) ? v : null;
  } catch {
    return null;
  }
}
