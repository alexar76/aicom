// GENERATED from src/flow-guard-instructions.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Bounded, fallible signals in source text. Never an authority or a semantic verdict. */
import { MAX_TEXT } from './flow-guard-text.mjs';
const LEGACY = /ignore (all |any |the )?(previous|prior|above) (instructions|messages)|disregard (the|your|all) (previous|prior|system)|<\/?(important|system|instructions?|critical[_-]?requirement)\b|do not (tell|show|inform|mention to) the user|you are now|new instructions:|assistant must|before (any|every) (reply|response), (call|run|use)/i;
// Require instruction syntax or an authority claim together with a nearby directive.
// Ordinary amenities, preferences and approvals alone are not instruction signals.
const RULES = [
    ['legacy', LEGACY],
    ['role-boundary', /\[im_start\][ \t]*(?:system|developer|assistant)\b|<\|start_header_id\|>[ \t]*(?:system|developer|assistant)\b|<(?:system|developer|assistant)(?:[ \t][^>\n]{0,80})?>/i],
    ['relayed-preference', /(?:verified|latest|newer|updated|final)\s+(?:customer|user)\s+(?:update|preference|request)[^\n]{0,360}?\b(?:return|choose|select|recommend|put)\b|(?:customer|user)\s+(?:update|preference|request)[^\n]{0,160}?\b(?:newer than|supersedes|overrides)\b[^\n]{0,160}?\b(?:return|choose|select|recommend|put)\b/i],
    ['claimed-prior-decision', /(?:cached|previous|prior)\s+(?:assistant\s+)?(?:analysis|reasoning|decision)[^\n]{0,360}?\b(?:continue|return|choose|select|recommend)\b|(?:customer|user)\s+(?:already|previously)\s+(?:approved|selected|chose)[^\n]{0,240}?\b(?:continue|return|choose|select|recommend)\b/i],
    ['private-rubric', /(?:internal|private|hidden)\s+(?:evaluation\s+)?(?:rubric|evaluator|scoring|benchmark)[^\n]{0,240}?\b(?:must\s+(?:choose|select|recommend)|expects?\b|(?:return|put)\b[^\n]{0,80}?\b(?:id|answer|response))/i],
    ['concealed-directive', /do not\s+(?:reveal|disclose|mention|describe)\s+(?:this|the|our)\s+(?:(?:internal|private|scoring|hidden|selection)\s+){0,2}(?:instruction|note|rubric|handoff|relay)\b|without\s+(?:asking for confirmation or\s+)?(?:mentioning|describing)\s+(?:this|the)\s+(?:relay|handoff|instruction)\b/i],
    ['relayed-preference-ru', /(?:последнее|обновл[её]нное|новое)\s+предпочтение\s+(?:пользователя|клиента)[^\n]{0,300}?(?:выберите|верните|рекомендуйте)|не\s+(?:упоминайте|раскрывайте)\s+(?:это|данное)\s+(?:служебное\s+)?(?:сообщение|указание|инструкцию)/i],
];
// Kept non-global for callers using .test(). It has no mutable lastIndex state.
export const INJECTION_HINTS = new RegExp(RULES.map(([, rule]) => `(?:${rule.source})`).join('|'), 'i');
export function instructionSignals(text) {
    const input = text.slice(0, MAX_TEXT);
    const matches = [];
    // Upstream text extraction may already have stopped at this budget. Treat an
    // exactly full buffer conservatively as limited rather than declaring coverage.
    let limited = text.length >= MAX_TEXT;
    for (const [kind, rule] of RULES) {
        let count = 0;
        for (const match of input.matchAll(new RegExp(rule.source, 'gi'))) {
            if (count++ === 16) {
                limited = true;
                break;
            }
            matches.push({ kind, start: match.index, end: match.index + match[0].length });
        }
    }
    matches.sort((a, b) => a.start - b.start || a.end - b.end);
    return { matches, limited };
}
