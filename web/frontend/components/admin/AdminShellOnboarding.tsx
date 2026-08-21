'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { BookOpen, Rocket, Sparkles, Wrench, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { type AdminLocale, t } from '@/lib/adminI18n';
import { isSetupWizardMarkedDone, SETUP_WIZARD_DONE_EVENT } from '@/components/admin/tabs/SetupWizardTab';

const STORAGE_KEY = 'aicom_admin_shell_onboarding_dismissed_v1';

type Props = {
  activeTab: string;
  locale: AdminLocale;
};

export function AdminShellOnboarding({ activeTab, locale }: Props) {
  const [dismissed, setDismissed] = useState(true);
  const [setupDone, setSetupDone] = useState(false);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(STORAGE_KEY) === '1');
    } catch {
      setDismissed(false);
    }
  }, []);

  useEffect(() => {
    setSetupDone(isSetupWizardMarkedDone());
  }, [activeTab]);

  useEffect(() => {
    const sync = () => setSetupDone(isSetupWizardMarkedDone());
    window.addEventListener(SETUP_WIZARD_DONE_EVENT, sync);
    return () => window.removeEventListener(SETUP_WIZARD_DONE_EVENT, sync);
  }, []);

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore */
    }
    setDismissed(true);
  }, []);

  if (dismissed) return null;

  return (
    <GlassCard className="mb-6 border border-indigo-500/30 bg-indigo-950/30 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3">
          <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" aria-hidden />
          <div className="min-w-0 space-y-2">
            <h3 className="text-sm font-semibold text-indigo-50">{t(locale, 'onboarding.title')}</h3>
            {!setupDone ? (
              <p className="text-[11px] leading-relaxed text-indigo-200/90 rounded-lg border border-indigo-400/25 bg-indigo-500/10 px-3 py-2">
                <Rocket className="inline h-3.5 w-3.5 -mt-0.5 mr-1 text-indigo-300" aria-hidden />
                {t(locale, 'onboarding.firstInstall')}
              </p>
            ) : null}
            <ol className="list-decimal space-y-1.5 pl-4 text-xs leading-relaxed text-indigo-100/90">
              <li>{t(locale, 'onboarding.step1')}</li>
              <li>{t(locale, 'onboarding.step2')}</li>
              <li>{t(locale, 'onboarding.step3')}</li>
            </ol>
            <p className="text-[11px] text-indigo-200/70">{t(locale, 'onboarding.failHint')}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 lg:flex-col lg:items-end">
          {!setupDone ? (
            <Link
              href="/admin?tab=setup"
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500/25"
            >
              <Rocket className="h-3.5 w-3.5" aria-hidden />
              {t(locale, 'onboarding.setupWizard')}
            </Link>
          ) : null}
          <Link
            href="/admin?tab=new-product"
            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-400/40 bg-indigo-500/20 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500/30"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            {t(locale, 'onboarding.newProduct')}
          </Link>
          <Link
            href="/admin?tab=workshop"
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-indigo-100 hover:bg-white/5"
          >
            <Wrench className="h-3.5 w-3.5" aria-hidden />
            {t(locale, 'onboarding.workshop')}
          </Link>
          <button
            type="button"
            className="rounded-lg p-1.5 text-indigo-200/80 hover:bg-white/10 hover:text-white"
            aria-label={t(locale, 'onboarding.dismiss')}
            onClick={dismiss}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      {activeTab === 'new-product' ? (
        <p className="mt-3 border-t border-white/10 pt-3 text-[11px] text-indigo-100/75">
          {t(locale, 'onboarding.onNewProductTab')}
        </p>
      ) : null}
    </GlassCard>
  );
}
