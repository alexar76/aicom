/**
 * Client-side mirror of high-confidence prompt-injection checks (guest phrase, support).
 * Backend remains authoritative; this only improves UX with immediate feedback.
 */

const CRITICAL_LOWER = [
  '[inst]',
  '[/inst]',
  '<|im_',
  'ignore all previous instructions',
  'disregard all previous',
  'forget everything you',
  'override the above instructions',
  'dan mode',
  'jailbreak',
  'сбрось контекст',
  'игнорируй все предыдущ',
  'забудь все инструкц',
  'новые системные инструкц',
];

export function normalizeUserInput(s: string): string {
  let t = s.trim();
  try {
    t = t.normalize('NFKC');
  } catch {
    /* ignore */
  }
  return t.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
}

export function getGuestPhraseBlockReason(phrase: string): string | null {
  const t = normalizeUserInput(phrase).toLowerCase();
  if (!t) return null;
  for (const needle of CRITICAL_LOWER) {
    if (t.includes(needle)) {
      return 'This text looks like an instruction-injection attempt and will not be submitted. Describe the product or slogan in plain language.';
    }
  }
  return null;
}

export function getSupportMessageBlockReason(message: string): string | null {
  return getGuestPhraseBlockReason(message);
}
