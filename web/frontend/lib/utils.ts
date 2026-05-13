// ============================================================================
// AUTONOMOUS AI-FACTORY v2.1 — Utility Functions
// ============================================================================

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with conflict resolution.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a Unix timestamp to a human-readable date string.
 */
export function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** `<input type="datetime-local">` value → Unix seconds (undefined if empty / invalid). */
export function parseDatetimeLocalToUnixSeconds(value: string): number | undefined {
  const v = value?.trim();
  if (!v) return undefined;
  const ms = Date.parse(v);
  if (!Number.isFinite(ms)) return undefined;
  return ms / 1000;
}

/** `<input type="date">` (YYYY-MM-DD) → start of local day, Unix seconds. */
export function localDateInputStartSeconds(isoDate: string): number | undefined {
  const v = isoDate?.trim();
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return undefined;
  const [y, mo, d] = v.split('-').map(Number);
  if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return undefined;
  const ms = new Date(y, mo - 1, d, 0, 0, 0, 0).getTime();
  return ms / 1000;
}

/** `<input type="date">` → end of local day (23:59:59.999), Unix seconds. */
export function localDateInputEndSeconds(isoDate: string): number | undefined {
  const v = isoDate?.trim();
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return undefined;
  const [y, mo, d] = v.split('-').map(Number);
  if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return undefined;
  const ms = new Date(y, mo - 1, d, 23, 59, 59, 999).getTime();
  return ms / 1000;
}

/**
 * Format a Unix timestamp to a relative time string (e.g., "2 hours ago").
 */
export function formatRelativeTime(timestamp: number): string {
  const now = Date.now() / 1000;
  const diff = now - timestamp;

  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
  return formatDate(timestamp);
}

/**
 * Format a number as currency (USDT/USDC).
 */
export function formatCurrency(amount: number, currency: string = 'USDT'): string {
  return `${amount.toFixed(2)} ${currency}`;
}

/**
 * Truncate a string with ellipsis.
 */
export function truncate(str: string, length: number = 100): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

/**
 * Truncate a wallet address for display.
 */
export function truncateAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

/**
 * Format bytes to human-readable size.
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

/**
 * Get a color for a pipeline state.
 */
export function getStateColor(state: string): string {
  const colors: Record<string, string> = {
    IDEA_RECEIVED: '#6366f1',
    MARKET_RESEARCHED: '#8b5cf6',
    SPEC_WRITING: '#818cf8',
    SPEC_WRITTEN: '#a78bfa',
    ARCH_DESIGNING: '#8b5cf6',
    ARCH_DESIGNED: '#7c3aed',
    DESIGN_CRITIQUED: '#9333ea',
    CODE_GENERATING: '#f59e0b',
    CODE_COMMITTED: '#10b981',
    CODE_TESTING: '#f59e0b',
    QA_TESTING: '#06b6d4',
    BUG_FOUND: '#ef4444',
    DEV_FIXING: '#f97316',
    SECURITY_SCANNED: '#22d3ee',
    HUMAN_REVIEW_PENDING: '#eab308',
    MARKET_CONTENT_READY: '#ec4899',
    METHODOLOGY_REVIEWED: '#06b6d4',
    SALES_ACTIVE: '#f43f5e',
    SANDBOX_RUNNING: '#14b8a6',
    TELEMETRY_COLLECTING: '#a855f7',
    EVOLUTION_ANALYZING: '#8b5cf6',
    COMPLETED: '#22c55e',
    DEPLOYED_PRODUCTION: '#16a34a',
    FAILED: '#ef4444',
    CANCELLED: '#6b7280',
  };
  const key = String(state || '').toUpperCase();
  return colors[key] || '#6b7280';
}

/**
 * Get a human-readable label for a pipeline state.
 */
export function getStateLabel(state: string): string {
  const labels: Record<string, string> = {
    IDEA_RECEIVED: 'Idea Received',
    MARKET_RESEARCHED: 'Market Researched',
    SPEC_WRITING: 'Writing Spec',
    SPEC_WRITTEN: 'Spec Complete',
    ARCH_DESIGNING: 'Designing Architecture',
    ARCH_DESIGNED: 'Architecture Done',
    DESIGN_CRITIQUED: 'Design Reviewed',
    CODE_GENERATING: 'Generating Code',
    CODE_COMMITTED: 'Code Complete',
    CODE_TESTING: 'Code Testing',
    QA_TESTING: 'QA Testing',
    BUG_FOUND: 'Bug Found',
    DEV_FIXING: 'Dev Fixing',
    SECURITY_SCANNED: 'Security Scanned',
    HUMAN_REVIEW_PENDING: 'Human Review',
    MARKET_CONTENT_READY: 'Marketing Ready',
    METHODOLOGY_REVIEWED: 'Methodology Reviewed',
    SALES_ACTIVE: 'Sales Active',
    SANDBOX_RUNNING: 'Sandbox Running',
    TELEMETRY_COLLECTING: 'Telemetry Collecting',
    EVOLUTION_ANALYZING: 'Evolution Analysis',
    COMPLETED: 'Completed',
    DEPLOYED_PRODUCTION: 'Deployed (production)',
    FAILED: 'Failed',
    CANCELLED: 'Cancelled',
  };
  const key = String(state || '').toUpperCase();
  return labels[key] || String(state || '');
}

/**
 * Get a color for an agent type.
 */
export function getAgentColor(agentType: string): string {
  const colors: Record<string, string> = {
    pm: '#6366f1',
    architect: '#8b5cf6',
    developer: '#f59e0b',
    qa: '#06b6d4',
    security: '#22d3ee',
    devops: '#10b981',
    marketing: '#ec4899',
    sales: '#f43f5e',
    evolution_analyst: '#a78bfa',
    designer: '#d946ef',
    methodologist: '#0ea5e9',
  };
  return colors[agentType] || '#6b7280';
}

/**
 * Get an emoji icon for an agent type.
 */
export function getAgentIcon(agentType: string): string {
  const icons: Record<string, string> = {
    pm: '🎯',
    architect: '🏗️',
    developer: '💻',
    qa: '🔍',
    security: '🛡️',
    devops: '🚀',
    marketing: '📢',
    sales: '💰',
    evolution_analyst: '🧬',
    designer: '🎨',
    methodologist: '🧭',
  };
  return icons[agentType] || '🤖';
}

/**
 * Debounce a function.
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

/**
 * Copy text to clipboard.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Convert a hex color string to comma-separated RGB components.
 * E.g. "#6366f1" → "99, 102, 241"
 */
function hexToRgb(hex: string): string {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) return '99, 102, 241';
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
}

/**
 * Determine whether a hex color is perceived as "light" (>128 brightness).
 * Uses W3C relative luminance approximation: (R*299 + G*587 + B*114) / 1000
 */
function isLightColor(hex: string): boolean {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) return false;
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  return brightness > 128;
}

/**
 * Apply a theme's colors as CSS custom properties on document.documentElement.
 *
 * Maps theme config fields to CSS variables used throughout the app.
 * Also sets `*-rgb` variants for use in `rgba()` calls.
 * Conditionally sets glass/card/input/shimmer variables based on
 * whether the background is light (uses dark-tinted rgba) or dark (white-tinted).
 * Call this after loading or changing a theme.
 */
export function applyTheme(theme: Record<string, any>): void {
  const root = document.documentElement;
  if (!root || !theme) return;

  const primary = theme.primary || '#6366f1';
  const accent = theme.accent || '#ff3366';
  const bgHex = theme.bg_start || '#0a0a1a';

  // Detect if this is a light or dark theme
  const light = isLightColor(bgHex);

  // Set data attribute so CSS can target light-vs-dark themes
  root.setAttribute('data-theme-bg', light ? 'light' : 'dark');

  // Derive text colors — use opaque values for light themes (critical for readability)
  const textPrimary = theme.text || (light ? '#000000' : '#e0e0ff');
  const textSecondary = theme.text_secondary || (light ? '#444444' : '#8888aa');

  // Map Tailwind-gray shades to dark text on light themes
  const twGray300 = light ? textPrimary : '#d1d5db';
  const twGray400 = light ? textSecondary : '#9ca3af';
  const twGray500 = light ? '#666666' : '#6b7280';
  const twGray600 = light ? '#555555' : '#4b5563';
  const twWhite   = light ? textPrimary : '#ffffff';

  const vars: Record<string, string> = {
    '--neon-primary': primary,
    '--neon-primary-rgb': hexToRgb(primary),
    '--neon-accent': accent,
    '--neon-accent-rgb': hexToRgb(accent),
    '--bg-primary': bgHex,
    '--bg-secondary': theme.bg_end || '#060612',
    '--text-primary': textPrimary,
    '--text-primary-rgb': hexToRgb(textPrimary),
    '--text-secondary': textSecondary,
    '--text-muted': light ? '#666666' : '#666688',

    // Tailwind text-color overrides — used by [data-theme-bg="light"] CSS
    '--tw-gray-300': twGray300,
    '--tw-gray-400': twGray400,
    '--tw-gray-500': twGray500,
    '--tw-gray-600': twGray600,
    '--tw-white': twWhite,

    // Glass/card/input/shimmer — adapt to background brightness
    '--glass-bg': light ? 'rgba(0, 0, 0, 0.04)' : 'rgba(255, 255, 255, 0.05)',
    '--glass-bg-hover': light ? 'rgba(0, 0, 0, 0.08)' : 'rgba(255, 255, 255, 0.12)',
    '--glass-border': light ? 'rgba(0, 0, 0, 0.1)' : 'rgba(255, 255, 255, 0.1)',
    '--glass-border-hover': light ? 'rgba(0, 0, 0, 0.15)' : 'rgba(255, 255, 255, 0.15)',
    '--glass-shadow': light ? '0 8px 32px 0 rgba(0, 0, 0, 0.1)' : '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
    '--card-bg': light ? 'rgba(0, 0, 0, 0.03)' : 'rgba(255, 255, 255, 0.03)',
    '--card-bg-hover': light ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)',
    '--input-bg': light ? 'rgba(0, 0, 0, 0.03)' : 'rgba(255, 255, 255, 0.05)',
    '--input-border': light ? 'rgba(0, 0, 0, 0.12)' : 'rgba(255, 255, 255, 0.1)',
    '--shimmer-to': light ? 'rgba(0, 0, 0, 0.04)' : 'rgba(255, 255, 255, 0.05)',
  };

  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value);
  }
}

/** Matches default :root cyber storefront — applied before /api/config/theme resolves (useLayoutEffect). */
export const STOREFRONT_THEME_FALLBACK: Record<string, string> = {
  primary: '#6366f1',
  accent: '#ff3366',
  bg_start: '#0a0a1a',
  bg_end: '#060612',
  text: '#e0e0ff',
  text_secondary: '#8888aa',
};
