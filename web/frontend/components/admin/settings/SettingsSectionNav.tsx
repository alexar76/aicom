'use client';

import { useCallback, useEffect, useState } from 'react';
import { t, type AdminLocale } from '@/lib/adminI18n';
import { SETTINGS_NAV_ITEMS, type SettingsSectionId } from './settingsNavConfig';

function scrollToSection(id: SettingsSectionId) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  window.history.replaceState(null, '', `#${id}`);
}

export function SettingsSectionNav({ locale }: { locale: AdminLocale }) {
  const [activeId, setActiveId] = useState<SettingsSectionId>(SETTINGS_NAV_ITEMS[0].id);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '') as SettingsSectionId;
    if (SETTINGS_NAV_ITEMS.some((s) => s.id === hash)) {
      setActiveId(hash);
      requestAnimationFrame(() => scrollToSection(hash));
    }
  }, []);

  useEffect(() => {
    const ids = SETTINGS_NAV_ITEMS.map((s) => s.id);
    const elements = ids.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target?.id) {
          setActiveId(visible[0].target.id as SettingsSectionId);
        }
      },
      { rootMargin: '-12% 0px -55% 0px', threshold: [0, 0.1, 0.25] },
    );

    for (const el of elements) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const onNavClick = useCallback((id: SettingsSectionId) => {
    setActiveId(id);
    scrollToSection(id);
  }, []);

  const navButton = (id: SettingsSectionId, label: string, Icon: (typeof SETTINGS_NAV_ITEMS)[0]['icon'], compact?: boolean) => {
    const active = activeId === id;
    return (
      <button
        key={id}
        type="button"
        onClick={() => onNavClick(id)}
        className={
          compact
            ? `shrink-0 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? 'border-indigo-400/50 bg-indigo-500/20 text-indigo-100'
                  : 'border-white/10 bg-white/5 text-gray-400 hover:border-white/20 hover:text-gray-200'
              }`
            : `w-full flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                active
                  ? 'border-indigo-400/45 bg-indigo-500/15 text-indigo-50 shadow-[0_0_20px_rgba(99,102,241,0.12)]'
                  : 'border-transparent text-gray-400 hover:border-white/10 hover:bg-white/5 hover:text-gray-200'
              }`
        }
      >
        <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-indigo-300' : 'text-gray-500'}`} aria-hidden />
        <span className="truncate">{label}</span>
      </button>
    );
  };

  return (
    <>
      {/* Mobile: sticky horizontal pills */}
      <div className="lg:hidden sticky top-0 z-20 -mx-1 mb-4 pt-1 pb-2 bg-[#0a0a0f]/90 backdrop-blur-md border-b border-white/5">
        <p className="text-[10px] uppercase tracking-wider text-gray-500 px-1 mb-2">{t(locale, 'settings.nav.title')}</p>
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-white/10">
          {SETTINGS_NAV_ITEMS.map(({ id, labelKey, icon: Icon }) =>
            navButton(id, t(locale, labelKey), Icon, true),
          )}
        </div>
      </div>

      {/* Desktop: stick to scrollport while settings column scrolls (parent flex uses items-start) */}
      <nav
        className="hidden lg:block w-56 xl:w-60 shrink-0 sticky top-4 self-start z-10"
        aria-label={t(locale, 'settings.nav.title')}
      >
        <div className="rounded-xl border border-white/10 bg-gradient-to-b from-white/[0.06] to-white/[0.02] p-3 shadow-lg shadow-black/20">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 px-2 mb-2">
            {t(locale, 'settings.nav.title')}
          </p>
          <div className="flex flex-col gap-0.5 max-h-[calc(100dvh-6rem)] overflow-y-auto pr-0.5 scrollbar-thin scrollbar-thumb-white/10">
            {SETTINGS_NAV_ITEMS.map(({ id, labelKey, icon: Icon }) =>
              navButton(id, t(locale, labelKey), Icon),
            )}
          </div>
        </div>
      </nav>
    </>
  );
}
