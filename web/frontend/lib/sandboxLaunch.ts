import api from '@/lib/api';
import {
  normalizeSandboxLaunchLocale,
  sandboxLaunchLabel,
  type SandboxLaunchLocale,
} from '@/lib/sandboxLaunchI18n';

export type SandboxLaunchProgress = {
  percent: number;
  label: string;
};

export type SandboxLaunchOptions = {
  fromStorefront?: boolean;
  locale?: SandboxLaunchLocale | string | null;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Start sandbox and poll until preview HTML is reachable; reports progress for UI overlay.
 */
export async function launchSandboxWithProgress(
  productId: string,
  options: SandboxLaunchOptions | undefined,
  onProgress: (p: SandboxLaunchProgress) => void,
): Promise<{ sandbox_id: string; url: string }> {
  const locale = normalizeSandboxLaunchLocale(options?.locale);
  const L = (key: Parameters<typeof sandboxLaunchLabel>[1]) => sandboxLaunchLabel(locale, key);

  onProgress({ percent: 8, label: L('startingSandbox') });
  const result = await api.startSandbox(productId, options);
  const sandboxId = result.sandbox_id;
  const viewUrl = result.url?.startsWith('http')
    ? result.url
    : `${typeof window !== 'undefined' ? window.location.origin : ''}${result.url || `/api/sandbox/view/${sandboxId}`}`;

  const startupWarning =
    typeof (result as { startup_warning?: string }).startup_warning === 'string'
      ? (result as { startup_warning: string }).startup_warning
      : null;
  const previewTier = (result as { preview_tier?: string }).preview_tier;
  const isDegraded = previewTier === 'degraded' || Boolean((result as { degraded_badge?: boolean }).degraded_badge);

  if (startupWarning) {
    onProgress({ percent: 18, label: L('heavyStackWarning') });
    await sleep(800);
  }
  if (isDegraded) {
    onProgress({ percent: 40, label: L('degradedPreview') });
  } else {
    onProgress({ percent: 35, label: L('preparingCode') });
  }

  const maxAttempts = isDegraded ? 24 : 48;
  let ready = false;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const pct = Math.min(35 + attempt * (isDegraded ? 2 : 1), 92);
    onProgress({
      percent: pct,
      label:
        attempt < 2 && !isDegraded
          ? L('bootstrapping')
          : attempt < 6
            ? L('buildingPreview')
            : L('loadingLanding'),
    });
    try {
      const status = await api.sandboxReady(sandboxId);
      const phase = (status as { startup_phase?: string }).startup_phase;
      if (phase === 'failed') {
        throw new Error('Sandbox bootstrap failed on server');
      }
      if (status.ready) {
        ready = true;
        break;
      }
      const previewPath =
        typeof status.preview_path === 'string' && status.preview_path
          ? status.preview_path
          : 'index.html';
      const probe = await fetch(
        `/api/sandbox/file/${encodeURIComponent(sandboxId)}/${previewPath.split('/').map(encodeURIComponent).join('/')}`,
        { method: 'GET', cache: 'no-store' },
      );
      if (probe.ok && (await probe.text()).length > 400) {
        ready = true;
        break;
      }
    } catch {
      /* retry */
    }
    await sleep(attempt < 3 ? 500 : isDegraded ? 700 : 1200);
  }

  onProgress({ percent: ready ? 100 : 96, label: ready ? L('done') : L('openingPreview') });
  await sleep(ready ? 120 : 0);
  return { sandbox_id: sandboxId, url: viewUrl };
}
