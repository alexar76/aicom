/** Trigger a file download in the browser without revoking the blob URL too early. */

export function parseContentDispositionFilename(
  contentDisposition: string | null,
  fallback: string
): string {
  if (!contentDisposition) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
  const quoted = /filename="([^"]+)"/i.exec(contentDisposition);
  const plain = /filename=([^;\s]+)/i.exec(contentDisposition);
  const raw = star?.[1] ?? quoted?.[1] ?? plain?.[1];
  if (!raw) return fallback;
  try {
    return decodeURIComponent(raw.replace(/^"+|"+$/g, ''));
  } catch {
    return raw.replace(/^"+|"+$/g, '');
  }
}

function triggerAnchorDownload(blob: Blob, filename: string): void {
  if (typeof window === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke too early (in finally right after click) prevents the download from starting.
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
}

/**
 * Save a blob as a download. When supported, opens the native save dialog first (keeps
 * user activation for large async fetches), then writes after the blob is ready.
 */
export async function saveBlobAsDownload(
  blob: Blob,
  filename: string,
  options?: { offerSavePicker?: boolean }
): Promise<void> {
  if (!blob.size) {
    throw new Error('Download is empty (0 bytes). The server may have timed out while building the archive.');
  }

  const picker =
    options?.offerSavePicker !== false &&
    typeof window !== 'undefined' &&
    typeof (window as Window & { showSaveFilePicker?: unknown }).showSaveFilePicker === 'function';

  if (picker) {
    try {
      const w = window as unknown as {
        showSaveFilePicker: (opts: {
          suggestedName: string;
          types: { description: string; accept: Record<string, string[]> }[];
        }) => Promise<{ createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }> }>;
      };
      const handle = await w.showSaveFilePicker({
        suggestedName: filename,
        types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        throw new Error('Download cancelled');
      }
      /* fall through to anchor download */
    }
  }

  triggerAnchorDownload(blob, filename);
}
