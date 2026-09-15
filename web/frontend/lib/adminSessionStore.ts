/**
 * Shared admin session state (locale, auth profile, dashboard snapshot).
 * Reduces inconsistent useState/localStorage across tabs.
 */

import { create } from 'zustand';
import { type AdminLocale, detectAdminLocale, saveAdminLocale } from '@/lib/adminI18n';
import api from '@/lib/api';

export type AdminMe = {
  role?: string | null;
  public_demo?: boolean;
  sandbox_demo_password_uses_default?: boolean;
};

type AdminSessionState = {
  locale: AdminLocale;
  me: AdminMe | null;
  authChecked: boolean;
  setLocale: (locale: AdminLocale) => void;
  setMe: (me: AdminMe | null) => void;
  setAuthChecked: (v: boolean) => void;
  hydrateLocale: () => void;
  refreshMe: () => Promise<void>;
};

export const useAdminSessionStore = create<AdminSessionState>((set, get) => ({
  locale: typeof window !== 'undefined' ? detectAdminLocale() : 'en',
  me: null,
  authChecked: false,
  setLocale: (locale) => {
    saveAdminLocale(locale);
    set({ locale });
  },
  setMe: (me) => set({ me }),
  setAuthChecked: (authChecked) => set({ authChecked }),
  hydrateLocale: () => set({ locale: detectAdminLocale() }),
  refreshMe: async () => {
    const m = await api.getMe();
    set({
      me: {
        role: m.role ?? null,
        public_demo: Boolean(m.public_demo),
        sandbox_demo_password_uses_default: Boolean(m.sandbox_demo_password_uses_default),
      },
    });
  },
}));
