// GENERATED from src/flow-guard-classify.ts by scripts/sync-flow-guard.mjs. Do not edit; run npm run build.
/** Flow guard: what a call is (private read, outside text, outbound, destructive) and what its result taints. */
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, isAbsolute, normalize, resolve, sep } from 'node:path';
import { FOREIGN_DIRS, absPath, inside, isProtectedPath, isSecretPath, physicalPath, shellPath } from './flow-guard-paths.mjs';
import { globMatch, hostMatches } from './flow-guard-policy.mjs';
import { MAX_TEXT, hostsIn, strings } from './flow-guard-text.mjs';
import { screenOperation } from './flow-guard-screen.mjs';
import { namesParty } from './flow-guard-destinations.mjs';
import { INJECTION_HINTS } from './flow-guard-instructions.mjs';
// Shell commands. A segment is one command between ; && || | and newlines.
const NETWORK_CMDS = new Set(['curl', 'wget', 'nc', 'ncat', 'netcat', 'socat', 'telnet', 'ssh', 'scp', 'sftp', 'ftp', 'rsync',
    'gh', 'hub', 'aws', 'gcloud', 'gsutil', 'az', 'kubectl', 'helm', 'heroku', 'vercel', 'netlify', 'fly', 'flyctl', 'wrangler',
    'http', 'https', 'xh', 'httpie', 'aria2c', 'lynx', 'w3m', 'links', 'mail', 'sendmail', 'mutt', 'dig', 'nslookup', 'host', 'ping', 'traceroute']);
const NETWORK_SUB = {
    git: new Set(['push', 'pull', 'fetch', 'clone', 'remote', 'submodule', 'ls-remote', 'send-email', 'request-pull']),
    npm: new Set(['publish', 'install', 'i', 'add', 'update', 'login', 'adduser', 'unpublish', 'view', 'info', 'exec', 'x']),
    npx: new Set(['*']), pnpm: new Set(['publish', 'install', 'i', 'add', 'update', 'dlx']), yarn: new Set(['publish', 'add', 'install', 'dlx']),
    pip: new Set(['install', 'download']), pip3: new Set(['install', 'download']), uv: new Set(['pip', 'add', 'sync', 'run']), uvx: new Set(['*']),
    docker: new Set(['push', 'pull', 'login', 'run', 'build']), cargo: new Set(['publish', 'install', 'login']), go: new Set(['get', 'install']),
};
const DESTRUCTIVE_CMDS = new Set(['rm', 'rmdir', 'shred', 'dd', 'mkfs', 'truncate', 'crontab', 'launchctl', 'systemctl', 'chmod', 'chown', 'kill', 'pkill', 'killall', 'shutdown', 'reboot']);
const DESTRUCTIVE_SUB = { git: new Set(['reset', 'clean', 'rebase', 'filter-branch', 'filter-repo', 'update-ref', 'reflog', 'gc', 'prune']) };
// Read-only or local-only. Anything not here, in a tainted session that read private data, counts as able to send.
const LOCAL_CMDS = new Set(['ls', 'pwd', 'cd', 'cat', 'head', 'tail', 'wc', 'grep', 'egrep', 'fgrep', 'rg', 'ag', 'find', 'fd', 'tree',
    'sort', 'uniq', 'cut', 'tr', 'diff', 'cmp', 'file', 'stat', 'du', 'df', 'echo', 'printf', 'true', 'false', 'which', 'type', 'whoami',
    'date', 'uname', 'env', 'basename', 'dirname', 'realpath', 'readlink', 'jq', 'yq', 'column', 'less', 'more', 'nl', 'sed', 'awk', 'test', '[']);
const LOCAL_SUB = {
    git: new Set(['status', 'diff', 'log', 'show', 'branch', 'rev-parse', 'blame', 'ls-files', 'grep', 'describe', 'tag', 'stash', 'add', 'commit', 'checkout', 'switch', 'restore', 'merge-base', 'cat-file', 'config']),
};
function segmentWords(segment) {
    const words = segment.trim().split(/\s+/).filter(Boolean);
    while (words.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0]))
        words.shift();
    while (words.length && ['sudo', 'nohup', 'time', 'nice', 'command', 'builtin', 'env', 'xargs', 'timeout'].includes(words[0])) {
        words.shift();
        while (words.length && (words[0].startsWith('-') || /^\d+[smh]?$/.test(words[0]) || /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0])))
            words.shift();
    }
    return words.map(w => w.replace(/^['"]|['"]$/g, ''));
}
export function classifyShell(command) {
    const labels = new Set();
    const hosts = hostsIn([command]);
    for (const m of command.matchAll(/(?:^|\s)(?:[\w.-]+@)?([a-z0-9-]+(?:\.[a-z0-9-]+)+):[\w~./-]/gi))
        hosts.push(m[1].toLowerCase());
    let local = literalReadOnlyShell(command);
    if (/(^|[^<])>{1,2}\s*(~|\/etc|\/Library|\$HOME)/.test(command))
        labels.add('destructive');
    for (const segment of command.split(/\n|;|&&|\|\||\|/)) {
        const words = segmentWords(segment);
        if (!words.length)
            continue;
        const cmd = words[0].split('/').pop().toLowerCase();
        const sub = (words[1] || '').toLowerCase();
        if (NETWORK_CMDS.has(cmd) || NETWORK_SUB[cmd]?.has('*') || NETWORK_SUB[cmd]?.has(sub)) {
            labels.add('outbound');
            labels.add('untrusted');
            local = false;
        }
        if (DESTRUCTIVE_CMDS.has(cmd) || DESTRUCTIVE_SUB[cmd]?.has(sub) || (cmd === 'git' && sub === 'push' && words.some(w => /^(-f|--force.*|\+)/.test(w)))) {
            labels.add('destructive');
        }
        if (cmd === 'find' && words.some(w => w === '-exec' || w === '-execdir' || w === '-delete'))
            local = false;
        if ((cmd === 'sed' && words.some(w => /^-i/.test(w))) || (cmd === 'awk' && /system\s*\(/.test(segment)))
            local = false;
        const isLocal = LOCAL_CMDS.has(cmd) || LOCAL_SUB[cmd]?.has(sub);
        if (!isLocal)
            local = false;
    }
    if (hosts.length)
        labels.add('outbound');
    // Output of a local command is the user's data; output of a network command is someone else's.
    if (!labels.has('untrusted'))
        labels.add('private');
    return { labels, hosts: [...new Set(hosts)], local };
}
/** This is intentionally not a shell parser. Anything outside this literal subset needs consent.
 * No PATH-dependent executables, redirections, expansions, interpreters, git hooks or config writes.
 * Bare names are checked by classifyCall against the hook's PATH before being trusted. */
function literalReadOnlyShell(command) {
    if (/[^a-zA-Z0-9_./,:= @%+\-\t\n|&]/.test(command) || /[\n]/.test(command))
        return false;
    const safe = new Set(['ls', 'pwd', 'cat', 'head', 'tail', 'wc', 'grep', 'cut', 'diff', 'cmp', 'stat', 'du', 'df', 'basename', 'dirname', 'readlink', 'nl', 'true', 'false']);
    return command.split(/&&|\|\||\|/).every(segment => {
        const words = segment.trim().split(/\s+/);
        const executable = words[0] ?? '';
        const name = basename(executable);
        if (executable.includes('/') && !['/bin/', '/usr/bin/'].some(prefix => executable === prefix + name))
            return false;
        if (!safe.has(name))
            return false;
        // sort/uniq can write files and rg can run preprocessors: they are deliberately absent.
        return !words.some(w => w.includes('&') || w.startsWith('@'));
    });
}
function trustedShellExecutables(command, env) {
    if (env.RIPGREP_CONFIG_PATH || env.BASH_ENV || env.ENV || env.LD_PRELOAD || env.DYLD_INSERT_LIBRARIES)
        return false;
    return command.split(/&&|\|\||\|/).every(segment => {
        const exe = segment.trim().split(/\s+/)[0] ?? '';
        if (exe.includes('/'))
            return ['/bin', '/usr/bin'].includes(dirname(exe));
        if (['pwd', 'true', 'false'].includes(exe))
            return true;
        const found = (env.PATH ?? '/usr/bin:/bin').split(sep === '/' ? ':' : ';').map(p => resolve(p || '.', exe)).find(p => existsSync(p));
        return !!found && ['/bin', '/usr/bin'].includes(dirname(physicalPath(found)));
    });
}
// Built-in tool words for MCP tools without operator labels (hints that only ADD caution).
const SEND_WORDS = /(^|_|-)(send|post|publish|push|upload|share|tweet|email|mail|notify|message|comment|reply|create_?issue|create_?pr|pull_?request|webhook|http|request|fetch|browse|navigate|goto|open_?url|visit|submit|forward|transfer|pay|invoke)(_|-|$)/i;
const COMMIT_ACTION = /^(?:(?:git|github|repo)_)?commit(?:_|$)|^create_commit(?:_|$)/i;
const INBOUND_WORDS = /(^|_|-)(fetch|browse|navigate|scrape|crawl|search|web|url|read_?(email|mail|issue|issues|message|messages|comments?|page)|get_?(issue|issues|email|emails|messages?|comments?|page|url)|list_?(issues|emails|messages|comments)|inbox|feed|rss|snapshot|screenshot)(_|-|$)/i;
const DESTROY_WORDS = /(^|_|-)(delete|remove|drop|destroy|truncate|purge|wipe|reset|kill|terminate|force_?push|overwrite)(_|-|$)/i;
export function classifyCall(toolName, input, cwd, policy, env = process.env) {
    const texts = strings(input);
    const result = { labels: new Set(), hosts: [], src: toolName, secret: false, protectedTouch: false };
    const pathArg = typeof input.file_path === 'string' ? input.file_path : typeof input.notebook_path === 'string' ? input.notebook_path : typeof input.path === 'string' ? input.path : undefined;
    const abs = pathArg ? absPath(pathArg, cwd) : undefined;
    if (abs && isProtectedPath(abs, cwd, env) && ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'].includes(toolName))
        result.protectedTouch = true;
    const operator = Object.entries(policy.labels).find(([glob]) => globMatch(glob, toolName));
    if (operator && !['Bash', 'BashOutput', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit'].includes(toolName)) {
        for (const l of operator[1])
            result.labels.add(l);
        result.hosts = hostsIn(texts);
        return result;
    }
    switch (toolName) {
        case 'Read':
        case 'NotebookRead':
        case 'Grep':
        case 'Glob':
        case 'LS':
            result.labels.add('private');
            if (abs) {
                result.src = physicalPath(abs);
                result.secret = isSecretPath(abs) || isSecretPath(result.src);
            }
            break;
        case 'WebFetch':
        case 'WebSearch':
            result.labels.add('untrusted');
            result.labels.add('outbound');
            result.hosts = hostsIn(texts);
            result.src = result.hosts[0] || toolName;
            break;
        case 'Write':
        case 'Edit':
        case 'MultiEdit':
        case 'NotebookEdit':
            if (abs && !inside(abs, normalize(cwd)))
                result.labels.add('destructive');
            break;
        case 'Bash':
        case 'BashOutput': {
            const command = typeof input.command === 'string' ? input.command : texts.join('\n');
            const shell = classifyShell(command);
            result.opaqueShell = !shell.local || !trustedShellExecutables(command, env);
            for (const l of shell.labels)
                result.labels.add(l);
            if (result.opaqueShell)
                result.labels.add('outbound');
            result.hosts = shell.hosts;
            result.src = shell.hosts[0] ? `${shell.hosts[0]} (shell)` : 'shell output';
            for (const t of command.split(/\s+/)) {
                const cleaned = t.replace(/^['"]|['"]$/g, '');
                const path = shellPath(cleaned.replace(/^--[\w-]+=/, ''), cwd, env);
                if (/[/~.]/.test(cleaned) && isSecretPath(path))
                    result.secret = true;
                if (/[/~.$]/.test(cleaned) && isProtectedPath(path, cwd, env) && !shell.local)
                    result.protectedTouch = true;
            }
            break;
        }
        default:
            if (toolName.startsWith('mcp__')) {
                const tool = screenOperation(toolName.split('__').slice(2).join('__') || toolName);
                result.hosts = hostsIn(texts);
                result.guessed = true;
                // A tool whose name says nothing can still reach a person: it names a recipient, attendee or account,
                // or carries an e-mail address or IBAN. Reaching a party is what outbound means here.
                if (SEND_WORDS.test(tool) || COMMIT_ACTION.test(tool) || result.hosts.length || namesParty(input, texts))
                    result.labels.add('outbound');
                if (INBOUND_WORDS.test(tool) || result.hosts.length)
                    result.labels.add('untrusted');
                if (DESTROY_WORDS.test(tool))
                    result.labels.add('destructive');
                // The server wrote the result; without an operator label it is outside text.
                result.labels.add('untrusted');
                result.src = `MCP ${toolName.split('__')[1] || 'server'}`;
            }
    }
    return result;
}
// These source signals never authorize actions or establish semantic compliance.
export { INJECTION_HINTS } from './flow-guard-instructions.mjs';
export function resultTaints(toolName, input, responseText, cwd, policy, classified) {
    const labels = classified.labels;
    let untrusted = labels.has('untrusted');
    const isPrivate = labels.has('private');
    if (untrusted && toolName === 'WebFetch' && typeof input.url === 'string') {
        try {
            if (hostMatches(new URL(input.url).hostname, policy.trustedSources))
                untrusted = false;
        }
        catch { /* invalid URL stays untrusted */ }
    }
    if (!untrusted && isPrivate && ['Read', 'NotebookRead', 'Grep'].includes(toolName)) {
        const abs = classified.src;
        // A file outside the project is someone else's (a download, another checkout) unless it is the
        // user's own key or config: ~/.ssh/id_ed25519 is private data, not outside text.
        const home = homedir();
        const ownConfig = classified.secret || (inside(abs, home) && /\/\.[^/]+/.test(abs.slice(home.length)));
        const foreign = FOREIGN_DIRS.test(abs) || (isAbsolute(abs) && !inside(abs, normalize(cwd)) && !ownConfig);
        if (policy.taintLocalFiles || foreign || INJECTION_HINTS.test(responseText.slice(0, MAX_TEXT)))
            untrusted = true;
    }
    if (!untrusted && toolName === 'Bash' && INJECTION_HINTS.test(responseText.slice(0, MAX_TEXT)))
        untrusted = true;
    return { untrusted, private: isPrivate, src: classified.src };
}
