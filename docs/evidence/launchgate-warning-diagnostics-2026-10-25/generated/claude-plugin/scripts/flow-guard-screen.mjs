// GENERATED from src/flow-guard-screen.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: screen-control servers, whose clicks and keys move data without naming it. */
import { createHash } from 'node:crypto';
import { basename } from 'node:path';
import { isSecretPath } from './flow-guard-paths.mjs';
import { MAX_TEXT, responseStrings } from './flow-guard-text.mjs';
const SCREEN_WORDS = /(^|_|-)(screenshot|snapshot|screen|observe|accessibility|a11y|read_?page|page_?content|get_?(page|elements|ui|tree|screen|state)|elements|ui_?tree|dom|inspect)(_|-|$)/i;
const POINTER_WORDS = /(^|_|-)(click|tap|double_?click|right_?click|left_?click|middle_?click|triple_?click|press_?(button|element)|mouse|pointer|touch|drag|drop|swipe|long_?press)(_|-|$)/i;
// `type` in known control names, not arbitrary nouns such as `get_cuisine_type`.
const TYPE_WORDS = /(^|_|-)(type_?text|input_?text|insert_?text|enter_?text|fill)(_|-|$)|^type(_|-|$)|^(browser|screen|computer|desktop|keyboard)[_-]type$/i;
const KEY_WORDS = /(^|_|-)(key|keys|keypress|key_?press|hotkey|shortcut|keyboard|paste)(_|-|$)/i;
const keyControl = (name) => KEY_WORDS.test(name) || TYPE_WORDS.test(name);
const GENERIC_CONTROL = /^(computer|screen_control|desktop_control|browser_control)$/i;
// Exempt only complete observation names, never a substring such as `screenshot_then_submit`.
const READ_CONTROL_ACTIONS = new Set(['screenshot', 'snapshot', 'observe', 'accessibility', 'a11y', 'read_page',
    'page_content', 'get_page', 'get_elements', 'get_ui', 'get_tree', 'get_screen', 'get_state', 'elements', 'ui_tree', 'dom', 'inspect']);
const PASSIVE_KEY_ACTIONS = new Set(['key', 'keys', 'keypress', 'key_press', 'press_key', 'press_keys', 'hotkey', 'shortcut', 'keyboard']);
export const screenOperation = (name) => name.replace(/([a-z0-9])([A-Z])/g, '$1_$2').replace(/[.-]/g, '_').toLowerCase();
const SEND_TARGET = /\b(send|post|publish|submit|share|reply|comment|tweet|forward|upload|invite|pay|payment|buy|purchase|check\s?out|place\s+order|order\s+now|transfer|donate|sign\s?in|log\s?in)\b/i;
const DESTROY_TARGET = /\b(delete|remove|discard|erase|wipe|empty\s+trash|uninstall|revoke)\b/i;
const PASTE_KEYS = /\b(cmd|command|meta|super|win|ctrl|control)\s*[+-]\s*v\b|\bshift\s*[+-]\s*insert\b/i;
const REF_ARGS = new Set(['ref', 'element_ref', 'elementref', 'index', 'idx', 'element_index', 'elementindex', 'element_id', 'elementid', 'id', 'node_id', 'nodeid', 'mark']);
const TARGET_TEXT_ARGS = new Set(['element', 'label', 'name', 'text', 'title', 'target', 'description', 'selector', 'button', 'aria_label', 'arialabel']);
const KEY_TEXT_ARGS = new Set(['key', 'keys', 'text', 'combo', 'combination', 'shortcut', 'sequence', 'value', 'chars', 'input']);
const ID_KEYS = ['index', 'idx', 'id', 'ref', 'element_id', 'elementId', 'node_id', 'nodeId', 'mark'];
const LABEL_KEYS = ['name', 'label', 'text', 'title', 'aria_label', 'ariaLabel', 'description', 'value', 'innerText'];
const TITLE_KEYS = ['windowTitle', 'window_title', 'pageTitle', 'page_title', 'title'];
const ACCESSIBILITY_ID_KEYS = ['accessibilityIdentifier', 'accessibility_id', 'accessibilityId', 'automationId', 'automation_id', 'AXIdentifier', 'identifier'];
const TEXT_INPUT_ROLES = new Set(['textbox', 'input', 'textfield', 'text_field', 'entry', 'searchbox', 'textarea', 'combobox']);
const GUI_NAV_KEYS = new Set(['tab', 'shift+tab', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'home', 'end', 'pageup', 'pagedown', 'escape']);
// Best-effort explanation vocabulary, never an allow-list. Unknown words still require approval.
const SCREEN_ACTION_ALIASES = Object.fromEntries([
    ['send', 'senden envoyer enviar wyślij отправить 发送 送信 إرسال'],
    ['submit', 'absenden soumettre zatwierdź отправка 提交'],
    ['pay', 'bezahlen payer pagar zapłać оплатить 支付'],
    ['share', 'teilen partager compartir udostępnij поделиться 分享'],
    ['delete', 'löschen supprimer eliminar usuń удалить 删除'],
    ['discard', 'verwerfen abandonner descartar odrzuć отменить 丢弃'],
].flatMap(([verb, words]) => words.split(' ').map(word => [word, verb])));
// Playwright's accessibility snapshot (`- button "Send" [ref=e14]`), the `[ref_14]` form, numbered element lists
// (`14: button "Send"`, `1 'Issues' tab`) and `Page Title:` / `window:` lines.
const REF_LINE = /(?:^|\n)[ \t]*-?[ \t]*([a-z][\w-]{0,30})[ \t]+"([^"\n]{1,160})"[^\n]*?\[ref=([\w-]{1,24})\]/gi;
const REF_TOKEN_LINE = /(?:^|\n)[ \t]*-?[ \t]*([a-z][\w-]{0,30})[ \t]+"([^"\n]{1,160})"[^\n]*?\[(ref_\d{1,6})\]/gi;
const INDEX_LINE = /(?:^|[\n,;])[ \t]*(?:elements?:)?[ \t]*\[?(\d{1,4})\]?[ \t]*[:.)\]=-]?[ \t]*(?:([a-z][\w-]{0,30})[ \t]+)?["'“‘]([^"'”’\n]{1,160})["'”’](?:[ \t]+([a-z][\w-]{0,30}))?/gi;
const TITLE_LINE = /(?:^|\n)[ \t]*-?[ \t]*(?:page[ \t]+title|window[ \t]+title|active[ \t]+window|window|title)[ \t]*[:=][ \t]*["']?([^\n"']{1,160})/gi;
export const MAX_SCREENS = 8;
const MAX_REFS = 500;
const MAX_TITLES = 6;
export function screenServer(toolName) {
    return (toolName.split('__')[1] || toolName).slice(0, 100);
}
function refKey(v) {
    return String(v).trim().toLowerCase().slice(0, 40);
}
const ROLE = (v) => (typeof v === 'string' && /^[a-z][\w-]{0,30}$/i.test(v) ? v.toLowerCase() : '');
const screenObject = (v) => v && typeof v === 'object' && !Array.isArray(v) ? v : undefined;
const screenNumber = (v) => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 10_000_000;
const screenHash = (v) => createHash('sha256').update(v).digest('hex');
const guiIdentity = (v) => typeof v === 'string' && v.length > 0 && v.length <= 200 && !/[\x00-\x1f\x7f]/.test(v);
const guiFields = (o, fields) => Object.keys(o).every(k => fields.includes(k));
function guiOrigin(v, policy = false) {
    if (typeof v !== 'string' || v.length > 2048)
        return undefined;
    try {
        const u = new URL(v);
        if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password)
            return undefined;
        if (policy && (u.pathname !== '/' || u.search || u.hash))
            return undefined;
        return u.origin;
    }
    catch {
        return undefined;
    }
}
function guiKey(v) {
    if (typeof v !== 'string' && !(Array.isArray(v) && v.length > 0 && v.every(k => typeof k === 'string')))
        return undefined;
    const raw = Array.isArray(v) ? v.join('+') : v;
    if (raw.length > 40 || /[^a-z+ ]/i.test(raw))
        return undefined;
    const key = raw.trim().toLowerCase().replace(/ *\+ */g, '+');
    return GUI_NAV_KEYS.has(key) ? key : undefined;
}
/** Invalid GUI policy is strict as a whole: a typo must never create a broader permission. */
export function parseGuiPolicy(value) {
    const strict = { mode: 'strict', maxSnapshotAgeMs: 5000, allow: [] };
    const invalid = { ...strict, invalid: true };
    const o = screenObject(value);
    if (o?.mode === 'strict' && guiFields(o, ['mode', 'maxSnapshotAgeMs', 'allow']))
        return strict;
    if (!o || !guiFields(o, ['mode', 'maxSnapshotAgeMs', 'allow']) || o.mode !== 'policy')
        return invalid;
    const age = o.maxSnapshotAgeMs ?? 5000;
    if (!Number.isInteger(age) || age < 100 || age > 30_000 || !Array.isArray(o.allow) || o.allow.length > 64)
        return invalid;
    const allow = [];
    for (const raw of o.allow) {
        const r = screenObject(raw), target = screenObject(r?.target), context = screenObject(r?.context);
        if (!r || !target || !context || !guiFields(r, ['tool', 'action', 'target', 'context', 'keys', 'maxTextLength'])
            || !guiFields(target, ['role', 'accessibilityId']) || !guiFields(context, ['origin', 'application'])
            || typeof r.tool !== 'string' || !/^mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_.-]+$/.test(r.tool)
            || typeof r.action !== 'string' || !['click', 'type', 'key'].includes(r.action) || !guiIdentity(target.accessibilityId)
            || typeof target.role !== 'string' || !/^[a-z][\w-]{0,30}$/.test(target.role))
            return invalid;
        const origin = guiOrigin(context.origin, true), application = context.application;
        if ((context.origin !== undefined && !origin) || (application !== undefined && (typeof application !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(application)))
            || (!origin && application === undefined))
            return invalid;
        const keys = guiKey(r.keys);
        if (r.action === 'key' ? typeof r.keys !== 'string' || !keys || r.maxTextLength !== undefined : r.keys !== undefined)
            return invalid;
        if (r.action === 'type' ? !Number.isInteger(r.maxTextLength) || r.maxTextLength < 1 || r.maxTextLength > 4096 : r.maxTextLength !== undefined)
            return invalid;
        allow.push({ tool: r.tool, action: r.action, target: { role: target.role, accessibilityId: target.accessibilityId },
            context: { ...(origin ? { origin } : {}), ...(typeof application === 'string' ? { application } : {}) },
            ...(keys ? { keys } : {}), ...(r.action === 'type' ? { maxTextLength: r.maxTextLength } : {}) });
    }
    return { mode: 'policy', maxSnapshotAgeMs: age, allow };
}
function screenPoint(v) {
    const o = screenObject(v);
    if (o && screenNumber(o.x) && screenNumber(o.y))
        return { x: o.x, y: o.y };
    if (Array.isArray(v) && v.length === 2 && screenNumber(v[0]) && screenNumber(v[1]))
        return { x: v[0], y: v[1] };
    return undefined;
}
function screenBox(v) {
    const o = screenObject(v);
    if (!o)
        return undefined; // Bare arrays have incompatible xywh/xyxy conventions; do not guess.
    const x = o.x ?? o.left, y = o.y ?? o.top;
    if (!screenNumber(x) || !screenNumber(y))
        return undefined;
    if ((o.left !== undefined && o.left !== x) || (o.top !== undefined && o.top !== y))
        return undefined;
    const width = o.width ?? (screenNumber(o.right) ? o.right - x : undefined);
    const height = o.height ?? (screenNumber(o.bottom) ? o.bottom - y : undefined);
    if (!screenNumber(width) || !screenNumber(height) || width <= 0 || height <= 0 || !screenNumber(x + width) || !screenNumber(y + height))
        return undefined;
    if ((o.right !== undefined && o.right !== x + width) || (o.bottom !== undefined && o.bottom !== y + height))
        return undefined;
    return { x, y, width, height };
}
function screenAction(text) {
    const words = screenOperation(text.normalize('NFKC')).split(/[^\p{L}\p{N}]+/u);
    const verb = words.join(' ').match(SEND_TARGET)?.[1]?.toLowerCase().replace(/\s+/g, ' ');
    const destroy = words.join(' ').match(DESTROY_TARGET)?.[1]?.toLowerCase().replace(/\s+/g, ' ');
    const aliases = words
        .map(word => Object.hasOwn(SCREEN_ACTION_ALIASES, word) ? SCREEN_ACTION_ALIASES[word] : undefined);
    return { verb: verb ?? aliases.find(v => v && v !== 'delete' && v !== 'discard'), destroy: destroy ?? aliases.find(v => v === 'delete' || v === 'discard') };
}
function screenElement(o, role, form) {
    const boxes = ['bounds', 'boundingBox', 'bounding_box', 'rect'].filter(k => o[k] !== undefined).map(k => screenBox(o[k]));
    const bounds = boxes.length && boxes.every(b => b && JSON.stringify(b) === JSON.stringify(boxes[0])) ? boxes[0] : undefined;
    const center = boxes.length ? undefined : screenPoint(o.center);
    const identifier = ACCESSIBILITY_ID_KEYS.map(k => typeof o[k] === 'string' ? o[k].slice(0, 200) : '').join(' ');
    const action = screenAction(screenOperation(identifier));
    const identities = [...new Set(ACCESSIBILITY_ID_KEYS.filter(k => o[k] !== undefined).map(k => guiIdentity(o[k]) ? o[k] : ''))];
    const identityHash = identities.length === 1 && identities[0] ? screenHash(identities[0]) : undefined;
    const idKey = ID_KEYS.find(k => typeof o[k] === 'string' || typeof o[k] === 'number');
    const reference = idKey ? String(o[idKey]) : '';
    const referenceHash = reference.length > 0 && reference.length <= 40 ? screenHash(reference) : undefined;
    const labelHash = screenHash(JSON.stringify(LABEL_KEYS.map(k => typeof o[k] === 'string' ? o[k] : null)));
    const formRef = typeof o.formId === 'string' || typeof o.formId === 'number' ? refKey(o.formId) : typeof o.form === 'string' || typeof o.form === 'number' ? refKey(o.form) : form;
    return { ...(role ? { role } : {}), ...(bounds ? { bounds } : {}), ...(center ? { center } : {}),
        ...(o.focused === true ? { focused: true } : {}), ...(typeof o.multiline === 'boolean' ? { multiline: o.multiline } : {}),
        ...(formRef ? { form: formRef } : {}), ...(action.verb ? { identifierVerb: action.verb } : {}),
        ...(action.destroy ? { identifierDestroy: action.destroy } : {}),
        ...(o.type === 'submit' && ['button', 'input', 'submit'].includes(role) ? { submit: true } : {}),
        ...(identityHash ? { identityHash } : {}), ...(referenceHash ? { referenceHash } : {}), labelHash };
}
function coordinateRef(input, view) {
    const points = ['coordinate', 'coordinates', 'position'].filter(k => input[k] !== undefined).map(k => screenPoint(input[k]));
    if (input.x !== undefined || input.y !== undefined)
        points.push(screenPoint(input));
    if (!points.length || !points.every(p => p && p.x === points[0]?.x && p.y === points[0]?.y))
        return undefined;
    const p = points[0];
    const hits = Object.entries(view?.elements ?? {}).filter(([, e]) => {
        if (e.ambiguous)
            return false;
        const b = e.bounds;
        return b ? p.x >= b.x && p.y >= b.y && p.x < b.x + b.width && p.y < b.y + b.height
            : e.center?.x === p.x && e.center?.y === p.y;
    });
    return hits.length === 1 ? hits[0][0] : undefined; // Overlaps have no reliable stacking order.
}
function explainScreenElement(out, ref, view) {
    const e = Object.hasOwn(view.elements ?? {}, ref) ? view.elements?.[ref] : undefined;
    if (e?.ambiguous)
        return;
    out.ref = ref;
    const label = Object.hasOwn(view.refs, ref) ? view.refs[ref] : '';
    const action = screenAction(label ?? '');
    out.verb ??= action.verb;
    out.destroy ??= action.destroy;
    if (!out.verb && !out.destroy && (e?.identifierVerb || e?.identifierDestroy || e?.submit)) {
        out.verb = e.identifierVerb ?? (e.submit ? 'submit' : undefined);
        out.destroy = e.identifierDestroy;
        out.evidence = e.submit && !e.identifierVerb && !e.identifierDestroy ? 'semantic' : 'identifier';
    }
}
/** The elements and titles a screen tool's result shows, or undefined when the result is not a screen. A screen
 *  tool's result always replaces the server's last view, even when it is only an image: a stale list must not
 *  label the next click. Numbered lists also count from pointer/keyboard action results; acknowledgments alone
 *  keep the previous view, while an image-only action result clears it. `[ref=…]` lines and JSON nodes with a role
 *  count from any tool, since they are what accessibility trees look like. */
export function screenFromResult(toolName, response, text, input = {}) {
    const tool = screenOperation(toolName.split('__').slice(2).join('__') || toolName);
    const action = typeof input.action === 'string' ? screenOperation(input.action) : '';
    const screenTool = SCREEN_WORDS.test(tool) || (GENERIC_CONTROL.test(tool) && SCREEN_WORDS.test(action));
    const controlTool = POINTER_WORDS.test(tool) || keyControl(tool) || POINTER_WORDS.test(action) || keyControl(action);
    const refs = Object.create(null);
    const elements = Object.create(null);
    const focusedRefs = new Set();
    const conflictingRefs = new Set();
    const origins = new Set(), applications = new Set();
    const titles = [];
    let structural = false;
    let image = false;
    let truncated = text.length >= MAX_TEXT;
    const add = (key, role, label) => {
        if (Object.keys(refs).length >= MAX_REFS || !label.trim())
            return;
        const ref = refKey(key), value = `${role ? role + ' ' : ''}"${label.trim().slice(0, 160)}"`;
        if (Object.hasOwn(refs, ref) && refs[ref] !== value)
            conflictingRefs.add(ref);
        refs[ref] = value;
    };
    const body = text.slice(0, MAX_TEXT);
    for (const m of body.matchAll(REF_LINE)) {
        structural = true;
        add(m[3], (m[1] ?? '').toLowerCase(), m[2] ?? '');
    }
    for (const m of body.matchAll(REF_TOKEN_LINE)) {
        structural = true;
        add(m[3], (m[1] ?? '').toLowerCase(), m[2] ?? '');
    }
    if (screenTool || controlTool)
        for (const m of body.matchAll(INDEX_LINE)) {
            structural = true;
            add(m[1], ROLE(m[2]) || ROLE(m[4]), m[3] ?? '');
        }
    // JSON element lists, given as objects or as JSON in a text block.
    const nodes = [response];
    for (const t of responseStrings(response)) {
        const s = t.trim();
        if ((s.startsWith('{') || s.startsWith('[')) && s.length < MAX_TEXT) {
            try {
                nodes.push(JSON.parse(s));
            }
            catch { /* not JSON */ }
        }
    }
    // Only document-level context: an element/link URL cannot authorize the page containing it.
    for (const n of nodes) {
        const root = screenObject(n);
        for (const scope of [root, screenObject(root?.structuredContent)]) {
            if (!scope)
                continue;
            for (const k of ['url', 'pageUrl', 'page_url', 'documentUrl'])
                if (scope[k] !== undefined)
                    origins.add(guiOrigin(scope[k]) ?? '');
            for (const k of ['applicationId', 'bundleId'])
                if (scope[k] !== undefined)
                    applications.add(guiIdentity(scope[k]) ? scope[k] : '');
        }
    }
    let budget = 20_000;
    const walk = (v, depth, form) => {
        if (budget-- <= 0 || depth > 8) {
            truncated = true;
            return;
        }
        if (!v || typeof v !== 'object')
            return;
        if (Array.isArray(v)) {
            for (const x of v)
                walk(x, depth + 1, form);
            return;
        }
        const o = v;
        if (o.type === 'image')
            image = true;
        const idKey = ID_KEYS.find(k => typeof o[k] === 'string' || typeof o[k] === 'number');
        const labelKey = LABEL_KEYS.find(k => typeof o[k] === 'string' && o[k].trim());
        const role = ROLE(o.role) || ROLE(o.type) || ROLE(o.tag);
        const elementKey = idKey ? refKey(o[idKey]) : undefined;
        const childForm = role === 'form' && elementKey ? elementKey : form;
        if (elementKey && (role || screenTool) && (Object.hasOwn(elements, elementKey) || Object.keys(elements).length < MAX_REFS)) {
            const element = screenElement(o, role, role === 'form' ? undefined : form);
            if (Object.hasOwn(elements, elementKey) && JSON.stringify(elements[elementKey]) !== JSON.stringify(element))
                elements[elementKey] = { ambiguous: true };
            else
                elements[elementKey] = element;
            if (o.role !== undefined)
                structural = true;
        }
        else if (elementKey && (role || screenTool))
            truncated = true;
        for (const k of ['focusedRef', 'focusedElementId', 'activeElementId']) {
            if (typeof o[k] === 'string' || typeof o[k] === 'number')
                focusedRefs.add(refKey(o[k]));
        }
        if (idKey && labelKey && (role || screenTool)) {
            if (o.role !== undefined)
                structural = true;
            add(o[idKey], role, o[labelKey]);
        }
        else if (!idKey) {
            for (const k of TITLE_KEYS)
                if (typeof o[k] === 'string' && o[k].trim() && titles.length < MAX_TITLES)
                    titles.push(o[k].trim().slice(0, 160));
        }
        for (const x of Object.values(o))
            if (x && typeof x === 'object')
                walk(x, depth + 1, childForm);
    };
    for (const n of nodes)
        walk(n, 0);
    for (const ref of conflictingRefs)
        if (Object.hasOwn(elements, ref))
            elements[ref] = { ambiguous: true };
    for (const m of body.matchAll(TITLE_LINE)) {
        if (titles.length >= MAX_TITLES)
            break;
        titles.push((m[1] ?? '').trim().slice(0, 160));
    }
    if (!screenTool && !structural && !(controlTool && (image || titles.length)))
        return undefined;
    for (const [ref, e] of Object.entries(elements))
        if (e.focused)
            focusedRefs.add(ref);
    const focused = focusedRefs.size === 1 ? [...focusedRefs][0] : undefined;
    return { refs, titles, ...(Object.keys(elements).length ? { elements } : {}),
        ...(origins.size > 1 || origins.has('') || applications.size > 1 || applications.has('') ? { contextAmbiguous: true } : {}),
        ...(!truncated ? { policyComplete: true } : {}),
        ...(origins.size === 1 && !origins.has('') ? { origin: [...origins][0] } : {}),
        ...(applications.size === 1 && !applications.has('') ? { application: [...applications][0] } : {}),
        ...(focused && Object.hasOwn(elements, focused) && !elements[focused]?.ambiguous ? { focused } : {}) };
}
/** A pointer or keyboard call to an MCP screen server, read against that server's last screen. */
export function screenCall(toolName, input, state) {
    if (!toolName.startsWith('mcp__'))
        return undefined;
    const tool = screenOperation(toolName.split('__').slice(2).join('__') || toolName);
    const action = typeof input.action === 'string' ? screenOperation(input.action) : '';
    const pointer = POINTER_WORDS.test(tool) || POINTER_WORDS.test(action);
    const key = keyControl(tool) || keyControl(action);
    if (!pointer && !key) {
        if (GENERIC_CONTROL.test(tool) && !(READ_CONTROL_ACTIONS.has(action) && Object.keys(input).length === 1))
            return { guarded: 'control' };
        return undefined;
    }
    const out = {};
    const view = state.screens?.[screenServer(toolName)];
    if (pointer) {
        // No label, role, coordinate or caller-supplied description establishes the actual effect of a click.
        // Gate even familiar labels: "Inbox" can be a submit button, or a page can change after the snapshot.
        out.guarded = 'pointer';
        const targets = [];
        const requestedRefs = new Set();
        for (const [k, v] of Object.entries(input)) {
            const name = k.toLowerCase();
            if (TARGET_TEXT_ARGS.has(name) && typeof v === 'string')
                targets.push(v.slice(0, 300));
            if (REF_ARGS.has(name) && (typeof v === 'string' || typeof v === 'number'))
                requestedRefs.add(refKey(v));
        }
        const hit = coordinateRef(input, view);
        const ref = requestedRefs.size === 1 ? [...requestedRefs][0] : requestedRefs.size === 0 ? hit : undefined;
        if (ref && view && (hit === undefined || hit === ref)) {
            explainScreenElement(out, ref, view);
            if (hit === ref)
                out.via = 'coordinates';
        }
        for (const t of targets) {
            const action = screenAction(t);
            out.verb ??= action.verb;
            out.destroy ??= action.destroy;
        }
    }
    if (key) {
        const typed = keyTexts(input);
        const paste = /(^|_|-)paste(_|-|$)/i.test(tool) || /^paste$/i.test(action) || typed.some(t => PASTE_KEYS.test(t));
        // What the clipboard holds is not in the call. After a credential read it may be the credential.
        if (paste)
            out.paste = [...state.private].reverse().find(p => p.secret);
        if (!out.guarded) {
            if (paste)
                out.guarded = 'paste';
            else if (TYPE_WORDS.test(tool) || TYPE_WORDS.test(action))
                out.guarded = 'text';
            else if (typed.some(t => /\b(enter|return|numpadenter)\b|[\r\n]/i.test(t)))
                out.guarded = 'enter';
            else if (!(PASSIVE_KEY_ACTIONS.has(tool) || GENERIC_CONTROL.test(tool)) || !passiveShortcut(input))
                out.guarded = 'keyboard';
        }
        if (out.guarded === 'enter' && view?.focused) {
            explainScreenElement(out, view.focused, view);
            out.via = 'focus';
            const focused = view.elements?.[view.focused];
            const chord = typed.some(t => /\b(cmd|command|meta|ctrl|control)[+-]enter\b/i.test(t));
            if (!out.verb && !out.destroy && focused?.form && TEXT_INPUT_ROLES.has(focused.role ?? '') && (focused.multiline === false || (focused.multiline === true && chord))) {
                const buttons = Object.entries(view.elements ?? {}).filter(([, e]) => !e.ambiguous && e.form === focused.form && (e.role === 'button' || e.submit));
                const submits = buttons.map(([ref]) => { const result = {}; explainScreenElement(result, ref, view); return result; }).filter(e => e.verb);
                if (submits.length === 1) {
                    out.verb = submits[0].verb;
                    out.evidence = 'form';
                }
            }
        }
    }
    return out;
}
/** Operator-selected observation schema only. Never infer read authority from tool annotations. */
export function screenObservation(toolName, input) {
    const name = screenOperation(toolName.split('__').slice(2).join('__') || toolName);
    return READ_CONTROL_ACTIONS.has(name) || ['browser_snapshot', 'browser_take_screenshot', 'browser_screenshot', 'get_accessibility_tree', 'accessibility_snapshot', 'computer_screenshot'].includes(name) ? Object.keys(input).length === 0
        : GENERIC_CONTROL.test(name) && Object.keys(input).length === 1 && typeof input.action === 'string' && READ_CONTROL_ACTIONS.has(screenOperation(input.action));
}
/** Equality evidence for a new observation, not permission and not an attestation of GUI effects. */
export function screenTargetEvidence(toolName, input, view) {
    if (!view?.policyComplete || view.contextAmbiguous || !view.elements || !(view.origin || view.application || view.titles.length))
        return;
    const operation = guiOperation(toolName, input);
    if (!operation)
        return;
    const keys = ['key', 'keys', 'combo', 'combination', 'shortcut'], texts = ['text', 'value'];
    const allowed = operation === 'click' ? ['x', 'y', 'coordinate', 'coordinates', 'position'] : operation === 'key' ? keys : texts;
    if (Object.keys(input).some(key => key !== 'action' && !REF_ARGS.has(key.toLowerCase()) && !allowed.includes(key)))
        return;
    if (operation !== 'click') {
        const values = (operation === 'key' ? keys : texts).filter(key => input[key] !== undefined);
        if (values.length !== 1)
            return;
        const value = input[values[0]];
        if (operation === 'type' ? typeof value !== 'string' : !(typeof value === 'string' || Array.isArray(value) && value.length > 0 && value.every(v => typeof v === 'string')))
            return;
        if (operation === 'key') {
            const chord = (Array.isArray(value) ? value.join('+') : value).trim().toLowerCase().replace(/ *\+ */g, '+');
            if (chord.length > 64 || !/^(?:(?:cmd|command|meta|ctrl|control|alt|option|shift|super|win)\+)*(?:[a-z0-9]|enter|return|numpadenter|insert|backspace|delete|space|tab|escape|home|end|pageup|pagedown|arrowup|arrowdown|arrowleft|arrowright|f(?:[1-9]|1\d|2[0-4]))$/.test(chord))
                return;
        }
    }
    const call = screenCall(toolName, input, { v: 1, untrusted: [], private: [], notified: false, full: false });
    if (!call)
        return;
    const refs = Object.entries(input).filter(([key]) => REF_ARGS.has(key.toLowerCase()));
    if (refs.length > 1)
        return;
    const raw = refs[0]?.[1];
    if (refs.length && !(typeof raw === 'string' && /^[A-Za-z0-9_.:-]{1,40}$/.test(raw) || typeof raw === 'number' && Number.isSafeInteger(raw)))
        return;
    const ref = refs.length ? refKey(raw) : undefined;
    const hasCoordinates = ['x', 'y', 'coordinate', 'coordinates', 'position'].some(k => input[k] !== undefined);
    for (const key of ['coordinate', 'coordinates', 'position']) {
        const value = input[key];
        if (value !== undefined && !(Array.isArray(value) ? value.length === 2 && value.every(screenNumber) : screenObject(value) && Object.keys(value).every(k => ['x', 'y'].includes(k))))
            return;
    }
    const hit = hasCoordinates ? coordinateRef(input, view) : undefined;
    if (hasCoordinates && (!hit || ref && hit !== ref))
        return;
    const pointer = call.guarded === 'pointer';
    const target = ref ?? hit ?? (!pointer ? view.focused : undefined);
    if (!target || !pointer && target !== view.focused)
        return;
    const e = Object.hasOwn(view.elements, target) ? view.elements[target] : undefined;
    if (!e || e.ambiguous || !e.role || !e.bounds || !e.referenceHash || ref && e.referenceHash !== screenHash(String(raw)))
        return;
    if (e.identityHash && Object.values(view.elements).filter(other => other.identityHash === e.identityHash).length !== 1)
        return;
    return { target, stamp: screenHash(JSON.stringify({ target, role: e.role, reference: e.referenceHash, identity: e.identityHash,
            bounds: e.bounds, label: e.labelHash, form: e.form, submit: e.submit,
            origin: view.origin, application: view.application, titles: view.titles.map(screenHash), ...(!pointer ? { focus: view.focused } : {}) })) };
}
export function screenTargetStamp(toolName, input, view) {
    return screenTargetEvidence(toolName, input, view)?.stamp;
}
export function screenResponseEvidence(actionTool, action, observationTool, observation, response) {
    const o = screenObject(response);
    if (o?.isError || o?.error !== undefined)
        return;
    const view = screenFromResult(observationTool, response, responseStrings(response).join('\n'), observation);
    return view ? screenTargetEvidence(actionTool, action, { at: new Date().toISOString(), tool: observationTool, ...view }) : undefined;
}
/** Derive equality evidence from this response itself, never a concurrently replaced cached view. */
export function screenResponseStamp(actionTool, action, observationTool, observation, response) {
    return screenResponseEvidence(actionTool, action, observationTool, observation, response)?.stamp;
}
/** The only keyboard exemptions are an exact copy/select-all chord in a simple known schema. Extra fields,
 * malformed arrays and sequences never turn into a harmless chord by dropping values during extraction. */
function passiveShortcut(input) {
    const fields = Object.entries(input).filter(([k]) => k !== 'action');
    if (fields.length !== 1)
        return false;
    const [name, value] = fields[0];
    if (!['key', 'keys', 'combo', 'combination', 'shortcut'].includes(name))
        return false;
    if (input.action !== undefined && (typeof input.action !== 'string' || !PASSIVE_KEY_ACTIONS.has(screenOperation(input.action))))
        return false;
    if (typeof value !== 'string' && !(Array.isArray(value) && value.length > 0 && value.every(v => typeof v === 'string')))
        return false;
    const raw = Array.isArray(value) ? value.join('+') : value;
    if (raw.length > 64 || /[^a-z+ ]/i.test(raw))
        return false;
    const chord = raw.trim().toLowerCase()
        .replace(/\s*\+\s*/g, '+').replace(/^(command|meta|super|win)\+/, 'cmd+').replace(/^control\+/, 'ctrl+');
    return /^(cmd|ctrl)\+[ac]$/.test(chord);
}
function keyTexts(input) {
    return Object.entries(input).filter(([k]) => KEY_TEXT_ARGS.has(k.toLowerCase()))
        .map(([, v]) => (typeof v === 'string' ? v : Array.isArray(v) ? v.filter(x => typeof x === 'string').join('+') : ''))
        .filter(Boolean).map(t => t.slice(0, 2000));
}
export function guiOperation(toolName, input) {
    const operation = (name) => {
        const simple = name.replace(/^(browser|screen|computer|desktop|keyboard)_/, '');
        if (/^(click|left_click|tap)$/.test(simple))
            return 'click';
        if (/^(type|type_text|input_text|insert_text|enter_text|fill)$/.test(simple))
            return 'type';
        if (/^(key|keys|key_press|keypress|press_key|press_keys|hotkey|shortcut|keyboard)$/.test(simple))
            return 'key';
        return undefined;
    };
    const name = screenOperation(toolName.split('__').slice(2).join('__'));
    const action = typeof input.action === 'string' ? operation(screenOperation(input.action)) : undefined;
    const tool = GENERIC_CONTROL.test(name) ? action : operation(name);
    return tool && (input.action === undefined || action === tool) ? tool : undefined;
}
/** A credential read that a screen server's calls reveal: a credential path typed (into an open dialog, a
 *  terminal, an address bar) or a window or page title naming a credential file. Only the file name is kept. */
export function screenSecretRead(toolName, input, view) {
    if (!toolName.startsWith('mcp__'))
        return undefined;
    const tool = screenOperation(toolName.split('__').slice(2).join('__') || toolName);
    const action = typeof input.action === 'string' ? screenOperation(input.action) : '';
    const name = (path) => { const b = basename(path.replace(/\\/g, '/')); return /^[A-Za-z0-9_.+-]{1,60}$/.test(b) ? b : 'a credential file'; };
    if (keyControl(tool) || keyControl(action)) {
        for (const t of keyTexts(input)) {
            for (const raw of t.split(/[\s"'`]+/)) {
                const token = raw.replace(/[,;:)]+$/, '');
                if (/[/~.]/.test(token) && isSecretPath(token))
                    return `typed path ${name(token)}`;
            }
        }
    }
    for (const title of view?.titles ?? []) {
        for (const token of title.split(/[\s"'()|·–—]+/))
            if (token && isSecretPath(token))
                return `screen title naming ${name(token)}`;
    }
    return undefined;
}
