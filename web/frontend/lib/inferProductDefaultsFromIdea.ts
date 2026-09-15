/**
 * Lightweight client-side hints from free-text idea (no LLM round-trip).
 */

export type IdeaHeuristic = {
  suggestedDelivery: 'marketing_landing' | 'full_software' | 'desktop_app' | null;
  suggestedCategory: 'desktop' | 'saas' | null;
  reason: string;
};

const LANDING_HINTS =
  /\b(landing|brochure|one[- ]?pager|lead\s*gen|marketing\s*page|coming\s*soon|waitlist|hero\s*section)\b/i;

const APP_HINTS =
  /\b(saas|api|dashboard|auth|jwt|postgres|websocket|microservice|mobile\s*app|crm|erp|admin\s*panel)\b/i;

const DESKTOP_HINTS =
  /\b(desktop\s*app|electron|tauri|flutter\s*desktop|native\s*client|system\s*tray|installable\s*app|macos\s*app|windows\s*app)\b/i;

export function inferProductDefaultsFromIdea(idea: string): IdeaHeuristic {
  const t = idea.trim();
  if (t.length < 12) {
    return { suggestedDelivery: null, suggestedCategory: null, reason: '' };
  }
  if (DESKTOP_HINTS.test(t) && !LANDING_HINTS.test(t)) {
    return {
      suggestedDelivery: 'desktop_app',
      suggestedCategory: 'desktop',
      reason:
        'Detected desktop / native client wording — desktop_app pipeline (Tauri/Flutter/Electron) with Desktop shelf.',
    };
  }
  if (LANDING_HINTS.test(t) && !APP_HINTS.test(t)) {
    return {
      suggestedDelivery: 'marketing_landing',
      suggestedCategory: null,
      reason: 'Detected brochure / landing style wording — marketing landing profile fits faster shipping.',
    };
  }
  if (APP_HINTS.test(t) && !LANDING_HINTS.test(t)) {
    return {
      suggestedDelivery: 'full_software',
      suggestedCategory: 'saas',
      reason: 'Detected app / platform style wording — full product pipeline is a better default.',
    };
  }
  return { suggestedDelivery: null, suggestedCategory: null, reason: '' };
}
