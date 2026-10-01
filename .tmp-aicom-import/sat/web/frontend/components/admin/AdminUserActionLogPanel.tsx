'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, ScrollText } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import api, { AdminActionLogEntry } from '@/lib/api';
import { AdminLocale, t, tVars } from '@/lib/adminI18n';

function formatTs(ts: number): string {
  if (!ts || !Number.isFinite(ts)) return '—';
  return new Date(ts * 1000).toLocaleString();
}

function formatDetails(details: Record<string, unknown> | undefined): string {
  if (!details || Object.keys(details).length === 0) return '—';
  try {
    const s = JSON.stringify(details);
    return s.length > 180 ? `${s.slice(0, 177)}…` : s;
  } catch {
    return '—';
  }
}

type Props = {
  locale: AdminLocale;
  userId?: string | null;
  username?: string | null;
  title?: string;
  compact?: boolean;
};

export function AdminUserActionLogPanel({ locale, userId, username, title, compact }: Props) {
  const [entries, setEntries] = useState<AdminActionLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = userId
        ? await api.getAdminUserActionLog(userId, 100)
        : await api.getMyAdminActionLog(100);
      setEntries(res.entries || []);
      setTotal(res.total_matched ?? res.entries?.length ?? 0);
    } catch {
      setError(true);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  const heading =
    title ||
    (username
      ? tVars(locale, 'actionLog.titleUser', { user: username })
      : t(locale, 'actionLog.titleMine'));

  return (
    <GlassCard className={compact ? 'p-4' : 'p-6'}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <ScrollText className="h-5 w-5 shrink-0 text-indigo-400" aria-hidden />
          <div className="min-w-0">
            <h3 className="text-lg font-medium text-white truncate">{heading}</h3>
            <p className="text-xs text-gray-500">{t(locale, 'actionLog.subtitle')}</p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => load()} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          {t(locale, 'actionLog.refresh')}
        </Button>
      </div>

      {loading && entries.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-10 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          {t(locale, 'actionLog.loading')}
        </div>
      ) : error && entries.length === 0 ? (
        <p className="text-sm text-amber-300/90 py-6 text-center">{t(locale, 'actionLog.error')}</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-gray-500 py-6 text-center">{t(locale, 'actionLog.empty')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-gray-400">
              <tr className="border-b border-white/10">
                <th className="py-2 pr-3">{t(locale, 'actionLog.colTime')}</th>
                <th className="py-2 pr-3">{t(locale, 'actionLog.colAction')}</th>
                <th className="py-2 pr-3">{t(locale, 'actionLog.colResource')}</th>
                <th className="py-2">{t(locale, 'actionLog.colDetails')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {entries.map((e) => (
                <tr key={e.id} className="hover:bg-white/5">
                  <td className="py-2 pr-3 text-gray-400 whitespace-nowrap">{formatTs(e.ts)}</td>
                  <td className="py-2 pr-3 text-white font-medium">{e.action}</td>
                  <td className="py-2 pr-3 text-gray-300 font-mono text-xs">{e.resource || '—'}</td>
                  <td className="py-2 text-gray-400 text-xs">{formatDetails(e.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {total > entries.length && (
            <p className="text-xs text-gray-500 mt-3">
              {tVars(locale, 'actionLog.moreAvailable', { total: String(total), shown: String(entries.length) })}
            </p>
          )}
        </div>
      )}
    </GlassCard>
  );
}
