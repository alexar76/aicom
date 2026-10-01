import type { AdminLocale } from '@/lib/adminI18n';
import { t } from '@/lib/adminI18n';

export function pipelineTaskApiStatusLabel(locale: AdminLocale, st: string): string {
  const key = (
    {
      completed: 'pipeline.task.apiStatus.completed',
      running: 'pipeline.task.apiStatus.running',
      failed: 'pipeline.task.apiStatus.failed',
      pending: 'pipeline.task.apiStatus.pending',
    } as Record<string, string>
  )[st];
  return key ? t(locale, key) : st;
}
