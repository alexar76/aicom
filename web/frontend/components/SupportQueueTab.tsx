'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Inbox, Loader2, CheckCircle2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api from '@/lib/api';
import type { AdminLocale } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

type Escalation = {
  id: string;
  status: string;
  created_at: number;
  thread_id?: string;
  product_id?: string | null;
  classification?: string;
  summary?: string;
  resolved_at?: number;
  resolution_notes?: string;
};

const TXT = {
  title: { en: 'Support escalations', ru: 'Эскалации поддержки', es: 'Escalaciones de soporte', fr: 'Escalades du support', zh: '支持升级' },
  subtitle: {
    en: 'Business escalations from public support chat. Marketing / Sales / Director can close a ticket after response or resolution.',
    ru: 'Бизнес-эскалации из публичного чата поддержки. Маркетинг / сейлз / директор закрывают тикет после ответа или решения.',
    es: 'Escalaciones de negocio desde el chat público de soporte. Marketing / Ventas / Director cierran el ticket tras responder o resolver.',
    fr: 'Escalades métier issues du chat de support public. Le Marketing / les Ventes / le Directeur peuvent clôturer un ticket après réponse ou résolution.',
    zh: '来自公共支持聊天的业务升级。市场 / 销售 / 总监可在响应或解决后关闭工单。',
  },
  openOnly: { en: 'Open only', ru: 'Только открытые', es: 'Solo abiertos', fr: 'Ouverts uniquement', zh: '仅未处理' },
  all: { en: 'All', ru: 'Все', es: 'Todos', fr: 'Tous', zh: '全部' },
  refresh: { en: 'Refresh', ru: 'Обновить', es: 'Actualizar', fr: 'Actualiser', zh: '刷新' },
  noRecords: { en: 'No records', ru: 'Нет записей', es: 'Sin registros', fr: 'Aucun enregistrement', zh: '无记录' },
  product: { en: 'product', ru: 'продукт', es: 'producto', fr: 'produit', zh: '产品' },
  notes: { en: 'Notes', ru: 'Заметки', es: 'Notas', fr: 'Notes', zh: '备注' },
  closeNote: {
    en: 'Closure note (optional)',
    ru: 'Заметка при закрытии (опционально)',
    es: 'Nota de cierre (opcional)',
    fr: 'Note de clôture (facultative)',
    zh: '关闭备注（可选）',
  },
  closePlaceholder: {
    en: 'What was done, who took over…',
    ru: 'Что сделали, кому передали…',
    es: 'Qué se hizo, a quién se asignó…',
    fr: 'Ce qui a été fait, qui a pris le relais…',
    zh: '做了什么、由谁接手…',
  },
  close: { en: 'Close', ru: 'Закрыть', es: 'Cerrar', fr: 'Clôturer', zh: '关闭' },
  resolved: { en: 'Marked as resolved', ru: 'Отмечено как обработано', es: 'Marcado como resuelto', fr: 'Marqué comme résolu', zh: '已标记为已解决' },
  loadFailed: { en: 'Load failed', ru: 'Load failed', es: 'Load failed', fr: 'Échec du chargement', zh: '加载失败' },
  resolveFailed: { en: 'Resolve failed', ru: 'Resolve failed', es: 'Resolve failed', fr: 'Échec de la résolution', zh: '处理失败' },
};

const tt = (locale: AdminLocale, key: keyof typeof TXT) => TXT[key][locale] || TXT[key].en;

export default function SupportQueueTab({ locale = 'en' }: { locale?: AdminLocale }) {
  const [filter, setFilter] = useState<'open' | 'all'>('open');
  const [items, setItems] = useState<Escalation[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [notesById, setNotesById] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getSupportEscalations(filter === 'open' ? 'open' : undefined, 150);
      setItems((res.items || []) as Escalation[]);
      setOpenCount(res.open_count ?? 0);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [filter, locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = async (id: string) => {
    setResolving(id);
    try {
      await api.resolveSupportEscalation(id, notesById[id] || '');
      toast.success(tt(locale, 'resolved'));
      setNotesById((m) => ({ ...m, [id]: '' }));
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'resolveFailed'));
    } finally {
      setResolving(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Inbox className="w-6 h-6 text-amber-400" />
          {tt(locale, 'title')}
        </h2>
        <p className="text-sm text-gray-400 mt-1">
          {tt(locale, 'subtitle')}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as 'open' | 'all')}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
        >
          <option value="open">{tt(locale, 'openOnly')} ({openCount})</option>
          <option value="all">{tt(locale, 'all')}</option>
        </select>
        <Button variant="ghost" onClick={() => void load()} disabled={loading}>
          {tt(locale, 'refresh')}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <GlassCard className="p-8 text-center text-gray-400">{tt(locale, 'noRecords')}</GlassCard>
      ) : (
        <div className="space-y-3">
          {items.map((row) => (
            <GlassCard key={row.id} className="p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-gray-500 font-mono">{row.id}</div>
                  <div className="text-sm text-gray-300 mt-1">
                    {row.classification || '—'} · {tt(locale, 'product')}: {row.product_id || '—'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">thread: {row.thread_id || '—'}</div>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    row.status === 'open' ? 'bg-amber-500/20 text-amber-200' : 'bg-emerald-500/20 text-emerald-200'
                  }`}
                >
                  {row.status}
                </span>
              </div>
              <p className="text-sm text-white whitespace-pre-wrap break-words">{row.summary || '—'}</p>
              {row.resolution_notes && (
                <p className="text-xs text-gray-500">{tt(locale, 'notes')}: {row.resolution_notes}</p>
              )}
              {row.status === 'open' && (
                <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                  <div className="flex-1">
                    <label className="text-xs text-gray-500">{tt(locale, 'closeNote')}</label>
                    <Input
                      value={notesById[row.id] || ''}
                      onChange={(e) =>
                        setNotesById((m) => ({ ...m, [row.id]: e.target.value }))
                      }
                      placeholder={tt(locale, 'closePlaceholder')}
                    />
                  </div>
                  <Button
                    variant="primary"
                    onClick={() => void resolve(row.id)}
                    disabled={resolving === row.id}
                    className="shrink-0"
                  >
                    {resolving === row.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4 mr-1" />
                        {tt(locale, 'close')}
                      </>
                    )}
                  </Button>
                </div>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
