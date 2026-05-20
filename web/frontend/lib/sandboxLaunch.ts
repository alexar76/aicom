import api from '@/lib/api';

export type SandboxLaunchProgress = {
  percent: number;
  label: string;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Start sandbox and poll until preview HTML is reachable; reports progress for UI overlay.
 */
export async function launchSandboxWithProgress(
  productId: string,
  options: { fromStorefront?: boolean } | undefined,
  onProgress: (p: SandboxLaunchProgress) => void,
): Promise<{ sandbox_id: string; url: string }> {
  onProgress({ percent: 8, label: 'Запуск песочницы…' });
  const result = await api.startSandbox(productId, options);
  const sandboxId = result.sandbox_id;
  const viewUrl = result.url?.startsWith('http')
    ? result.url
    : `${typeof window !== 'undefined' ? window.location.origin : ''}${result.url || `/api/sandbox/view/${sandboxId}`}`;

  onProgress({ percent: 35, label: 'Подготовка кода продукта…' });
  let ready = false;
  for (let attempt = 0; attempt < 24; attempt++) {
    const pct = Math.min(35 + attempt * 2, 92);
    onProgress({
      percent: pct,
      label: attempt < 4 ? 'Сборка превью…' : 'Загрузка лендинга…',
    });
    try {
      const status = await api.sandboxReady(sandboxId);
      if (status.ready) {
        ready = true;
        break;
      }
    } catch {
      /* retry */
    }
    try {
      const probe = await fetch(
        `/api/sandbox/file/${encodeURIComponent(sandboxId)}/index.html`,
        { method: 'GET', cache: 'no-store' },
      );
      if (probe.ok && (await probe.text()).length > 400) {
        ready = true;
        break;
      }
    } catch {
      /* retry */
    }
    await sleep(attempt < 3 ? 400 : 700);
  }

  onProgress({ percent: ready ? 100 : 96, label: ready ? 'Готово' : 'Открываем превью…' });
  await sleep(ready ? 120 : 0);
  return { sandbox_id: sandboxId, url: viewUrl };
}
