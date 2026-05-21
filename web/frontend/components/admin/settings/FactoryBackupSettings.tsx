'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Download, Loader2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import api, { type FactoryRestorePreview } from '@/lib/api';
import type { AdminLocale } from '@/lib/adminI18n';
import { t } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

export function FactoryBackupSettings({ locale }: { locale: AdminLocale }) {
  const [busy, setBusy] = useState(false);
  const [includeSandboxes, setIncludeSandboxes] = useState(false);
  const [publicDemo, setPublicDemo] = useState(false);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<FactoryRestorePreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [cReplace, setCReplace] = useState(false);
  const [cTrusted, setCTrusted] = useState(false);
  const [cSaved, setCSaved] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void api
      .getMe()
      .then((me) => setPublicDemo(Boolean(me.public_demo || me.public_demo_readonly)))
      .catch(() => setPublicDemo(false));
  }, []);

  const onDownload = async () => {
    setBusy(true);
    try {
      await api.downloadFactoryBackupZip(includeSandboxes);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t(locale, 'settings.factoryBackup.failed');
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const onPreview = async () => {
    if (!zipFile) return;
    setPreviewBusy(true);
    setPreview(null);
    try {
      const p = await api.previewFactoryRestore(zipFile);
      setPreview(p);
      setCReplace(false);
      setCTrusted(false);
      setCSaved(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.factoryBackup.previewFailed'));
    } finally {
      setPreviewBusy(false);
    }
  };

  const onRestore = async () => {
    if (!preview?.restore_token) return;
    setRestoreBusy(true);
    try {
      const res = await api.executeFactoryRestore(preview.restore_token, {
        confirm_replace_all: cReplace,
        confirm_trusted_backup: cTrusted,
        confirm_saved_current_backup: cSaved,
      });
      toast.success(res.message || t(locale, 'settings.factoryBackup.restoreDone'));
      setPreview(null);
      setZipFile(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.factoryBackup.restoreFailed'));
    } finally {
      setRestoreBusy(false);
    }
  };

  const formatBytes = useCallback((n: number) => {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }, []);

  if (publicDemo) {
    return (
      <section className="rounded-lg border border-sky-500/40 bg-sky-950/25 p-4 space-y-2">
        <h3 className="text-sm font-semibold text-sky-100">{t(locale, 'settings.factoryBackup.title')}</h3>
        <p className="text-sm text-gray-300">{t(locale, 'settings.factoryBackup.demoBlocked')}</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-4 space-y-4">
      <h3 className="text-sm font-semibold text-amber-100">{t(locale, 'settings.factoryBackup.title')}</h3>
      <p className="text-sm text-gray-300">{t(locale, 'settings.factoryBackup.body')}</p>
      <p className="text-xs text-gray-500">{t(locale, 'settings.factoryBackup.roleHint')}</p>
      <p className="text-xs text-gray-500">{t(locale, 'settings.factoryBackup.productZipHint')}</p>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={includeSandboxes}
            onChange={(e) => setIncludeSandboxes(e.target.checked)}
            className="rounded border-gray-600"
          />
          {t(locale, 'settings.factoryBackup.includeSandboxes')}
        </label>
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={() => void onDownload()}
          className="inline-flex items-center gap-2"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {t(locale, 'settings.factoryBackup.download')}
        </Button>
      </div>

      <hr className="border-amber-500/20" />

      <h4 className="text-sm font-medium text-amber-100/90">{t(locale, 'settings.factoryBackup.restoreTitle')}</h4>
      <p className="text-xs text-gray-400">{t(locale, 'settings.factoryBackup.restoreHint')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip,application/zip"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setZipFile(f);
            setPreview(null);
          }}
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="inline-flex items-center gap-2"
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="h-4 w-4" />
          {zipFile?.name ?? t(locale, 'settings.factoryBackup.chooseZip')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={!zipFile || previewBusy}
          onClick={() => void onPreview()}
        >
          {previewBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t(locale, 'settings.factoryBackup.preview')}
        </Button>
      </div>

      {preview && (
        <div className="rounded-md border border-red-500/30 bg-red-950/20 p-3 space-y-3 text-sm">
          <div className="grid gap-1 text-gray-300">
            <div>
              {t(locale, 'settings.factoryBackup.currentProducts')}:{' '}
              <strong>{preview.current.products_total}</strong>
              {Object.keys(preview.current.products_by_state || {}).length > 0 && (
                <span className="text-gray-500 text-xs ml-2">
                  {JSON.stringify(preview.current.products_by_state)}
                </span>
              )}
            </div>
            <div>
              {t(locale, 'settings.factoryBackup.backupFrom')}:{' '}
              <span className="text-gray-400">
                {String(preview.backup.backup_manifest.exported_at_utc ?? '—')}
              </span>
              {' · '}
              {preview.backup.archive_files} files · {formatBytes(preview.backup.archive_bytes_uncompressed)}
            </div>
            <div className="text-xs text-amber-200/80">Mode: {preview.restore_mode}</div>
          </div>
          {preview.warnings.length > 0 && (
            <div>
              <div className="flex items-center gap-2 text-amber-200 font-medium mb-1">
                <AlertTriangle className="h-4 w-4" />
                {t(locale, 'settings.factoryBackup.warnings')}
              </div>
              <ul className="list-disc pl-5 space-y-1 text-gray-300">
                {preview.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="space-y-2">
            <label className="flex items-start gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={cReplace}
                onChange={(e) => setCReplace(e.target.checked)}
                className="mt-1 rounded border-gray-600"
              />
              {t(locale, 'settings.factoryBackup.confirmReplace')}
            </label>
            <label className="flex items-start gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={cTrusted}
                onChange={(e) => setCTrusted(e.target.checked)}
                className="mt-1 rounded border-gray-600"
              />
              {t(locale, 'settings.factoryBackup.confirmTrusted')}
            </label>
            <label className="flex items-start gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={cSaved}
                onChange={(e) => setCSaved(e.target.checked)}
                className="mt-1 rounded border-gray-600"
              />
              {t(locale, 'settings.factoryBackup.confirmSaved')}
            </label>
          </div>
          <Button
            type="button"
            variant="accent"
            disabled={restoreBusy || !cReplace || !cTrusted || !cSaved}
            className="bg-red-900/80 hover:bg-red-800 text-white"
            onClick={() => void onRestore()}
          >
            {restoreBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            {t(locale, 'settings.factoryBackup.runRestore')}
          </Button>
        </div>
      )}
    </section>
  );
}
