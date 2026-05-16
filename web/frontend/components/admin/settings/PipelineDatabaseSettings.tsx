'use client';

import { useCallback, useState } from 'react';
import { Database, RefreshCw, Server } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api from '@/lib/api';

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
  backend: 'sqlite' | 'postgres' | 'json';
  databaseUrl: string;
  status: PipelineDbStatus | null;
  onBackendChange: (v: 'sqlite' | 'postgres' | 'json') => void;
  onDatabaseUrlChange: (v: string) => void;
  disabled?: boolean;
};

export function PipelineDatabaseSettings({
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
      const res = await api.testPipelineDatabaseConnection(
        databaseUrl.trim() || undefined,
      );
      setMessage(res.ok ? `✅ ${res.detail}` : `❌ ${res.detail}`);
    } catch (e: unknown) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Connection test failed'}`);
    } finally {
      setTestBusy(false);
    }
  }, [databaseUrl]);

  const runMigrate = useCallback(async () => {
    if (
      !window.confirm(
        'Copy all products and tasks from SQLite into PostgreSQL? Existing Postgres rows with the same IDs will be updated.',
      )
    ) {
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
        `✅ Migrated ${res.products_migrated} products, ${res.tasks_migrated} tasks → ${res.destination}`,
      );
    } catch (e: unknown) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Migration failed'}`);
    } finally {
      setMigrateBusy(false);
    }
  }, [databaseUrl]);

  return (
    <GlassCard>
      <h3 className="text-lg font-medium text-white mb-2 flex items-center gap-2">
        <Database className="w-5 h-5 text-sky-400" aria-hidden />
        Pipeline database
      </h3>
      <p className="text-sm text-gray-400 mb-4">
        Default is SQLite on the data volume. Optionally migrate to PostgreSQL for external hosting or
        backups. After changing backend or URL, save settings and restart the app container.
      </p>

      <div className="space-y-4">
        <div>
          <label className="text-sm text-gray-300 block mb-1">Backend</label>
          <select
            value={backend}
            disabled={disabled}
            onChange={(e) =>
              onBackendChange(e.target.value as 'sqlite' | 'postgres' | 'json')
            }
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
          >
            <option value="sqlite">SQLite (default)</option>
            <option value="postgres">PostgreSQL</option>
            <option value="json">JSON file only (legacy)</option>
          </select>
        </div>

        {(backend === 'postgres' || databaseUrl) && (
          <div>
            <label className="text-sm text-gray-300 block mb-1">PostgreSQL connection URL</label>
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
                Saved: <span className="font-mono">{status.database_url_masked}</span>
              </p>
            ) : null}
          </div>
        )}

        {status ? (
          <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-gray-300 space-y-1">
            <div className="flex items-center gap-1 text-gray-400">
              <Server className="w-3.5 h-3.5" aria-hidden />
              Effective: <span className="text-white">{status.effective_backend}</span>
              {status.configured_backend && status.configured_backend !== status.effective_backend ? (
                <span className="text-amber-400"> (configured: {status.configured_backend})</span>
              ) : null}
            </div>
            {status.sqlite_exists ? (
              <p>
                SQLite: {status.sqlite_products ?? '?'} products, {status.sqlite_tasks ?? '?'} tasks
                <span className="text-gray-500"> ({status.sqlite_path})</span>
              </p>
            ) : null}
            {status.postgres_products != null ? (
              <p>
                PostgreSQL: {status.postgres_products} products, {status.postgres_tasks ?? '?'} tasks
              </p>
            ) : null}
            {status.postgres_error ? (
              <p className="text-red-400">Postgres: {status.postgres_error}</p>
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
            {testBusy ? 'Testing…' : 'Test connection'}
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
                Migrating…
              </>
            ) : (
              'Migrate SQLite → Postgres'
            )}
          </Button>
        </div>

        {message ? (
          <p className="text-xs whitespace-pre-wrap text-gray-300" role="status">
            {message}
          </p>
        ) : null}

        <p className="text-[11px] text-gray-500 leading-relaxed">
          Workflow: (1) enter URL and test connection, (2) migrate data, (3) set backend to PostgreSQL and
          save, (4) <code className="text-gray-400">docker compose up --build -d app</code>. You can also set{' '}
          <code className="text-gray-400">PIPELINE_DATABASE_URL</code> in{' '}
          <code className="text-gray-400">.env</code>.
        </p>
      </div>
    </GlassCard>
  );
}
