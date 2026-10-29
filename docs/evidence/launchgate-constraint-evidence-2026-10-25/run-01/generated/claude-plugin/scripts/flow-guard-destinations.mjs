// GENERATED from src/flow-guard-destinations.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
import { globMatch, hostMatches } from './flow-guard-policy.mjs';
import { MAX_TEXT, hostsIn, strings } from './flow-guard-text.mjs';
import { normalizeText } from './flow-guard-fingerprints.mjs';
export const MAX_RESOLVED = 200;
// Who or what a call is aimed at. A destination the user named in their own words is the user's choice.
export const DEST_ARG_NAMES = new Set(['to', 'recipient', 'recipients', 'cc', 'bcc', 'email', 'emails', 'participants', 'user', 'users',
    'channel', 'url', 'urls', 'iban', 'account', 'address', 'phone', 'host', 'hostname', 'domain', 'webhook', 'endpoint',
    'attendee', 'attendees', 'invitee', 'invitees', 'assignee', 'assignees', 'reviewer', 'reviewers', 'collaborator', 'collaborators',
    'member', 'members', 'username']);
// The subset that names a party without doubt. On an unlabeled MCP tool one of these makes the call outbound;
// "user", "channel", "account" or "host" also name what a read looks at, so they do not.
const PARTY_ARG_NAMES = new Set(['to', 'recipient', 'recipients', 'cc', 'bcc', 'email', 'emails', 'participants', 'iban', 'phone',
    'webhook', 'endpoint', 'attendee', 'attendees', 'invitee', 'invitees', 'assignee', 'assignees', 'reviewer', 'reviewers',
    'collaborator', 'collaborators', 'member', 'members', 'username']);
// Bounded address parts and a fixed start prevent quadratic scans of long non-address payloads.
const EMAIL_RE = /(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,253}\.[a-z]{2,63}\b/gi;
// A bare domain in text ("www.example.com/x"), limited to common TLDs so "file.txt" or "v1.2" do not count.
const BARE_DOMAIN_RE = /\b(?:www\.)?(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|ai|co|app|info|biz|xyz|me|us|uk|de|fr|es|it|nl|ru|cn|jp|in|br|eu|ch|se|no|fi|pl|cz|at|be|ca|au|nz|online|site|top|link|click|live|shop|store|tech|cloud|pro|tk|gq|ml|ga|cf|ly|gg|to|so|sh|cc|tv|ws)\b(?:\/[^\s"'<>)]*)?/gi;
const IBAN_RE = /\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){10,30}\b/g;
export function namesParty(input, texts) {
    const named = Object.entries(input).some(([k, v]) => PARTY_ARG_NAMES.has(k.toLowerCase()) &&
        ((typeof v === 'string' && !!v.trim()) || typeof v === 'number' || (Array.isArray(v) && v.length > 0)));
    return named || texts.some(t => new RegExp(EMAIL_RE.source, 'i').test(t) || new RegExp(IBAN_RE.source).test(t));
}
export function destinations(toolName, input, policy, hosts) {
    const out = new Set(hosts);
    const configured = Object.entries(policy.destinationArgs).find(([glob]) => globMatch(glob, toolName))?.[1];
    const names = configured ? new Set(configured.map(n => n.toLowerCase())) : DEST_ARG_NAMES;
    const add = (v) => {
        if (typeof v === 'string' || typeof v === 'number') {
            const t = String(v).trim();
            if (t)
                out.add(t);
        }
        else if (Array.isArray(v))
            v.forEach(add);
        else if (v && typeof v === 'object')
            Object.values(v).forEach(add);
    };
    for (const [k, v] of Object.entries(input))
        if (names.has(k.toLowerCase()))
            add(v);
    // Anything that names a place to reach, wherever it sits (a link in a message body is where the reader goes).
    for (const t of strings(input)) {
        for (const m of t.matchAll(EMAIL_RE))
            out.add(m[0]);
        for (const m of t.matchAll(IBAN_RE))
            out.add(m[0]);
        // A mailbox is one destination, not a separate grant to its provider's web host.
        for (const m of t.matchAll(BARE_DOMAIN_RE))
            if (t[(m.index ?? 0) - 1] !== '@')
                out.add(m[0]);
    }
    for (const h of hostsIn(strings(input)))
        out.add(h);
    return [...new Set([...out].map(d => d.toLowerCase().replace(/^[a-z]+:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '')))].filter(d => d.length >= 1);
}
/**
 * The operator named this tool's destination arguments and the call sets none of them: it acts on an
 * existing relationship (change the amount of a standing order, not its payee), so no new party is reached.
 * Unconfigured tools never qualify: without the operator's word, an absent argument proves nothing.
 */
export function keepsDestination(toolName, input, policy) {
    const configured = Object.entries(policy.destinationArgs).find(([glob]) => globMatch(glob, toolName))?.[1];
    if (!configured?.length)
        return false;
    // It must act on something that already exists, named by id: creating a new thing is not "keeping" a party.
    const existing = Object.entries(input).some(([k, v]) => /(^|_)id$/i.test(k) && v !== undefined && v !== null && v !== '' && !configured.includes(k));
    if (!existing)
        return false;
    return configured.every(name => { const v = input[name]; return v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0); });
}
/** Every destination appears in what the user typed this session. Hosts match on the bare name too. */
/** A whole-word, case-insensitive match of `token` (length >= 3) in the user's raw prompt. */
function typedWord(token, raw) {
    if (token.length < 3)
        return false;
    return new RegExp(`(^|[^\\p{L}\\p{N}])${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\p{L}\\p{N}])`, 'iu').test(raw);
}
/** Only structured records from explicitly configured contact tools may resolve a full display name.
 * Arbitrary prose, YAML, capitalized words and local file reads cannot create authority. */
export function resolvedContacts(value, depth = 0) {
    if (depth > 8)
        return [];
    if (typeof value === 'string') {
        if (value.length > MAX_TEXT)
            return [];
        try {
            return resolvedContacts(JSON.parse(value), depth + 1);
        }
        catch {
            return [];
        }
    }
    if (Array.isArray(value))
        return value.slice(0, MAX_RESOLVED).flatMap(v => resolvedContacts(v, depth + 1));
    if (!value || typeof value !== 'object')
        return [];
    const record = value;
    if (typeof record.name === 'string' && typeof record.email === 'string') {
        const name = record.name.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase();
        const email = record.email.trim().toLowerCase();
        if (name.length >= 3 && name.length <= 200 && /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(email))
            return [{ v: email, names: [name] }];
        return [];
    }
    // Common MCP envelopes only, not arbitrary nested notes or metadata.
    return ['content', 'structuredContent', 'contacts', 'text'].flatMap(k => resolvedContacts(record[k], depth + 1));
}
function exactNamed(value, text) {
    const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // A full stop or comma that ends the sentence ends the value too ("send it to bob@corp.com."); one that goes on
    // into more letters ("bob@corp.com.evil") does not.
    return new RegExp(`(^|[^\\p{L}\\p{N}._%+@-])${escaped}($|[^\\p{L}\\p{N}._%+@-]|[.,](?=$|\\s))`, 'iu').test(text);
}
/** A URL mentioned in prose cannot stand in for an actual target argument. */
export function hasDestinationArgument(tool, input, policy) {
    const configured = Object.entries(policy.destinationArgs).find(([glob]) => globMatch(glob, tool))?.[1];
    const names = configured ? new Set(configured.map(n => n.toLowerCase())) : DEST_ARG_NAMES;
    return Object.entries(input).some(([k, v]) => names.has(k.toLowerCase()) &&
        ((typeof v === 'string' && !!v.trim()) || typeof v === 'number' || (Array.isArray(v) && v.length > 0)));
}
export function allowedDestination(destination, patterns) {
    // Exact mailbox entries are possible; a host entry never authorizes every mailbox at that host.
    if (destination.includes('@'))
        return patterns.some(p => p.toLowerCase() === destination);
    try {
        const url = new URL(`https://${destination}`);
        return !url.username && !url.password && hostMatches(url.hostname, patterns);
    }
    catch {
        return false;
    }
}
export function namedByUser(dests, intent, intentRaw, resolved) {
    if (!dests.length || !intent?.length)
        return false;
    const raw = (intentRaw ?? []).join('\n');
    // Contact authority applies to the exact mailbox, never to its provider's web host.
    const viaContacts = dests.filter(d => d.includes('@') && (exactNamed(d, raw) || !!resolved?.some(r => r.v === d && r.names.some(n => typedWord(n, raw) && new Set(resolved.filter(other => other.names.includes(n)).map(other => other.v)).size === 1))));
    return dests.every(d => {
        if (viaContacts.includes(d))
            return true;
        // A bare number names an id only next to a word that says so ("file 13", "ID '13'", "#13"): in
        // "June 13" it is a date. Short names ("Bob") must match a whole word.
        if (/^\d+$/.test(d)) {
            const re = new RegExp(`(\\bid\\b|\\bids\\b|\\bfile\\b|\\bnumber\\b|\\bno\\.|#|№)\\s*[:'"\\s]*${d}(?!\\d)`, 'iu');
            return re.test(raw);
        }
        if (d.length < 6) {
            const re = new RegExp(`(^|[^\\p{L}\\p{N}])${d.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\p{L}\\p{N}])`, 'iu');
            return re.test(raw);
        }
        return exactNamed(d, raw) || (/^[a-z]{2}\d{2}[a-z0-9]{10,30}$/i.test(d) &&
            [...raw.toUpperCase().matchAll(IBAN_RE)].some(m => normalizeText(m[0]) === d));
    });
}
