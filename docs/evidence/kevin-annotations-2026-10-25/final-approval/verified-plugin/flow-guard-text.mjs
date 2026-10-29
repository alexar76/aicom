// GENERATED from src/flow-guard-text.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: the text a call carries or a result returns, and the hosts named in it. */
export const MAX_TEXT = 1_048_576;
export function strings(value, out = [], budget = { left: MAX_TEXT }) {
    if (budget.left <= 0)
        return out;
    if (typeof value === 'string') {
        out.push(value.slice(0, budget.left));
        budget.left -= value.length;
    }
    else if (Array.isArray(value)) {
        // Explicit numeric arrays are another spelling of character codes. Never stringify arbitrary objects.
        if (value.length >= 5 && value.length <= 4096 && value.every(v => typeof v === 'number' && Number.isSafeInteger(v)))
            strings(value.join(' '), out, budget);
        else
            for (const v of value)
                strings(v, out, budget);
    }
    else if (value && typeof value === 'object') {
        const o = value;
        for (const [key, v] of Object.entries(o)) {
            if (budget.omitBinary && key === 'data' && (o.type === 'image' || o.type === 'audio'))
                continue;
            strings(v, out, budget);
        }
    }
    return out;
}
// MCP binary blocks are not text. Their base64 must not exhaust the text budget before a screen's labels,
// titles or JSON text blocks are read. Arguments still use strings() without this exemption: an outgoing
// credential disguised as an image's data is still a credential leaving the session.
export function responseStrings(value) {
    return strings(value, [], { left: MAX_TEXT, omitBinary: true });
}
const URL_RE = /\b(?:https?|ftp|wss?):\/\/[^\s<>"']+/gi;
export function hostsIn(texts) {
    const hosts = new Set();
    for (const t of texts)
        for (const m of t.matchAll(URL_RE)) {
            try {
                hosts.add(new URL(m[0]).hostname.toLowerCase().replace(/\.$/, ''));
            }
            catch { /* an invalid URL grants no host permission */ }
        }
    return [...hosts];
}
