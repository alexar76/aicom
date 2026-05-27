import { CORE_DICT } from './dict/core';
import { SETUP_WIZARD_DICT } from './dict/setupWizard';
import { LOGIN_DICT } from './dict/login';
import { ONBOARDING_DICT } from './dict/onboarding';
import { DASHBOARD_DICT } from './dict/dashboard';
import { NEW_PRODUCT_DICT } from './dict/newProduct';
import { COMMON_DICT } from './dict/common';
import { AGENTS_DICT } from './dict/agents';
import { WORKSHOP_DICT } from './dict/workshop';
import { PIPELINE_TAB_DICT } from './dict/pipeline';
import { PIPELINE_IMPROVEMENT_HOLD_DICT } from './dict/pipelineImprovementHold';
import { SETTINGS_DICT } from './dict/settings';
import { FILES_TAB_DICT } from './dict/files';
import { BRAINSTORM_DICT } from './dict/brainstorm';
import { PROVIDERS_DICT } from './dict/providers';
import { SECURITY_DICT } from './dict/security';
import { SANDBOX_DICT } from './dict/sandbox';
import { LLM_LOGS_DICT } from './dict/llmLogs';
import { AGENT_LOGS_DICT } from './dict/agentLogs';
import { CORPORATE_CHAT_DICT } from './dict/corporateChat';
import { WOW_DICT } from './dict/wow';
import type { AdminLocale, I18nDict } from './types';

export type { AdminLocale } from './types';

const DICT: I18nDict = {
  ...CORE_DICT,
  ...SETUP_WIZARD_DICT,
  ...LOGIN_DICT,
  ...ONBOARDING_DICT,
  ...DASHBOARD_DICT,
  ...NEW_PRODUCT_DICT,
  ...COMMON_DICT,
  ...AGENTS_DICT,
  ...WORKSHOP_DICT,
  ...PIPELINE_TAB_DICT,
  ...PIPELINE_IMPROVEMENT_HOLD_DICT,
  ...SETTINGS_DICT,
  ...FILES_TAB_DICT,
  ...BRAINSTORM_DICT,
  ...PROVIDERS_DICT,
  ...SECURITY_DICT,
  ...SANDBOX_DICT,
  ...LLM_LOGS_DICT,
  ...AGENT_LOGS_DICT,
  ...CORPORATE_CHAT_DICT,
  ...WOW_DICT,
};

export function detectAdminLocale(): AdminLocale {
  if (typeof window === 'undefined') return 'en';
  const raw = window.localStorage.getItem('admin_locale');
  if (raw === 'ru' || raw === 'es') return raw;
  const nav = typeof navigator !== 'undefined' ? navigator.language.toLowerCase() : '';
  if (nav.startsWith('ru')) return 'ru';
  if (nav.startsWith('es')) return 'es';
  return 'en';
}

export function saveAdminLocale(locale: AdminLocale): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem('admin_locale', locale);
}

export function t(locale: AdminLocale, key: string): string {
  const row = DICT[key];
  if (!row) return key;
  return row[locale] ?? row.en ?? key;
}

export function tVars(locale: AdminLocale, key: string, vars: Record<string, string | number>): string {
  let s = t(locale, key);
  for (const [k, v] of Object.entries(vars)) {
    s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}
