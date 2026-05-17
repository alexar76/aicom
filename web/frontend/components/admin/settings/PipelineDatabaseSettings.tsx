'use client';

import { useCallback, useState } from 'react';
import { Database, RefreshCw, Server } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';
import { type AdminLocale, t, tVars } from '@/lib/adminI18n';

type PipelineDbStatus = {
  configured_backend?: string;
  effective_backend?: string;
  sqlite_path?: string;
  sqlite_exists?: boolean;
  sqlite_products?: number;
  sqlite_tasks?: number;
  postgres_products?: number;
  postgres_tasks?: number;
  database_url_masked?: string;
  postgres_error?: string;
  sqlite_error?: string;
};

type Props = {
  locale: AdminLocale;
  backend: 'sqlite' | 'postgres' | 'json';
  databaseUrl: string;
  status: PipelineDbStatus | null;
  onBackendChange: (v: 'sqlite' | 'postgres' | 'json') => void;
  onDatabaseUrlChange: (v: string) => void;
  disabled?: boolean;
};

export function PipelineDatabaseSettings({
  locale,
  backend,
  databaseUrl,
  status,
  onBackendChange,
  onDatabaseUrlChange,
  disabled,
}: Props) {
  const [testBusy, setTestBusy] = useState(false);
  const [migrateBusy, setMigrateBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const runTest = useCallback(async () => {
    setTestBusy(true);
    setMessage(null);
    try {
      const res = await api.testPipelineDatabaseConnection(databaseUrl.trim() || undefined);
      setMessage(res.ok ? `✅ ${res.detail}` : `❌ ${res.detail}`);
    } catch (e: unknown) {
      setMessage(`❌ ${e instanceof Error ? e.message : t(locale, 'settings.pipelineDb.testFailed')}`);
    } finally {
      setTestBusy(false);
    }
  }, [databaseUrl, locale]);

  const runMigrate = useCallback(async () => {
    if (!window.confirm(t(locale, 'settings.pipelineDb.migrateConfirm'))) {
      return;
    }
    setMigrateBusy(true);
    setMessage(null);
    try {
      const res = await api.migratePipelineSqliteToPostgres({
        database_url: databaseUrl.trim() || undefined,
        clear_target: false,
      });
      setMessage(
        tVars(locale, 'settings.pipelineDb.migrateOk', {
          products: res.products_migrated,
          tasks: res.tasks_migrated,
          dest: res.destination,
        }),
      );
    } catch (e: unknown) {
      setMessage(`❌ ${e instanceof Error ? e.message : t(locale, 'settings.pipelineDb.migrateFailed')}`);
    } finally {
      setMigrateBusy(false);
    }
  }, [databaseUrl, locale]);

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-2 flex items-center gap-2">
        <Database className="w-5 h-5 text-sky-400" aria-hidden />
        {t(locale, 'settings.pipelineDb.title')}
      </h3>
      <p className="text-sm text-gray-400 mb-4">{t(locale, 'settings.pipelineDb.intro')}</p>

      <div className="space-y-4">
        <div>
          <label className="text-sm text-gray-300 block mb-1">{t(locale, 'settings.pipelineDb.backend')}</label>
          <select
            value={backend}
            disabled={disabled}
            onChange={(e) => onBackendChange(e.target.value as 'sqlite' | 'postgres' | 'json')}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
          >
            <option value="sqlite">{t(locale, 'settings.pipelineDb.sqlite')}</option>
            <option value="postgres">{t(locale, 'settings.pipelineDb.postgres')}</option>
            <option value="json">{t(locale, 'settings.pipelineDb.jsonLegacy')}</option>
          </select>
        </div>

        {(backend === 'postgres' || databaseUrl) && (
          <div>
            <label className="text-sm text-gray-300 block mb-1">{t(locale, 'settings.pipelineDb.pgUrl')}</label>
            <input
              type="password"
              autoComplete="off"
              disabled={disabled}
              value={databaseUrl}
              onChange={(e) => onDatabaseUrlChange(e.target.value)}
              placeholder="postgresql://user:pass@host:5432/aicom"
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white font-mono"
            />
            {status?.database_url_masked ? (
              <p className="text-[11px] text-gray-500 mt-1">
                {t(locale, 'settings.pipelineDb.saved')}{' '}
                <span className="font-mono">{status.database_url_masked}</span>
              </p>
            ) : null}
          </div>
        )}

        {status ? (
          <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-gray-300 space-y-1">
            <div className="flex items-center gap-1 text-gray-400">
              <Server className="w-3.5 h-3.5" aria-hidden />
              {t(locale, 'settings.pipelineDb.effective')}{' '}
              <span className="text-white">{status.effective_backend}</span>
              {status.configured_backend && status.configured_backend !== status.effective_backend ? (
                <span className="text-amber-400">
                  {tVars(locale, 'settings.pipelineDb.configured', { backend: status.configured_backend })}
                </span>
              ) : null}
            </div>
            {status.sqlite_exists ? (
              <p>
                {tVars(locale, 'settings.pipelineDb.sqliteStats', {
                  products: status.sqlite_products ?? '?',
                  tasks: status.sqlite_tasks ?? '?',
                })}
                <span className="text-gray-500"> ({status.sqlite_path})</span>
              </p>
            ) : null}
            {status.postgres_products != null ? (
              <p>
                {tVars(locale, 'settings.pipelineDb.pgStats', {
                  products: status.postgres_products,
                  tasks: status.postgres_tasks ?? '?',
                })}
              </p>
            ) : null}
            {status.postgres_error ? (
              <p className="text-red-400">
                {tVars(locale, 'settings.pipelineDb.postgresError', { error: status.postgres_error })}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={disabled || testBusy || backend !== 'postgres'}
            onClick={() => void runTest()}
          >
            {testBusy ? t(locale, 'settings.pipelineDb.testing') : t(locale, 'settings.pipelineDb.test')}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={disabled || migrateBusy || backend !== 'postgres'}
            onClick={() => void runMigrate()}
          >
            {migrateBusy ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1" aria-hidden />
                {t(locale, 'settings.pipelineDb.migrating')}
              </>
            ) : (
              t(locale, 'settings.pipelineDb.migrate')
            )}
          </Button>
        </div>

        {message ? (
          <p className="text-xs whitespace-pre-wrap text-gray-300" role="status">
            {message}
          </p>
        ) : null}

        <p className="text-[11px] text-gray-500 leading-relaxed">{t(locale, 'settings.pipelineDb.workflow')}</p>
      </div>
    </GlassCard>
  );
}
