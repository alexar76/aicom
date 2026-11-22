# WARDEN 0.37.0 — keys and personal data stay out of the model

```bash
npm install -g @aimarket/warden@0.37.0
```

A tool result that contains a key goes to the model provider with everything else the agent read. From this release,
WARDEN replaces credentials in what a tool returns with random placeholders (`WARDEN_SECRET_7Q2M9XD4RK`) before the
model reads it, and puts the real value back only when the model writes the placeholder into a call to the place the
value came from. A placeholder sent anywhere else stops the call. The table of placeholders lives in WARDEN's memory
only.

The library shows the whole cycle in a few lines (Node 20 or later, after `npm install @aimarket/warden@0.37.0`):

```js
import { Masker, MaskRefusal, loadMaskConfig } from '@aimarket/warden/mask';

const session = new Masker(loadMaskConfig({})).session('demo');
const token = 'ghp_' + 'a1B2c3D4e5'.repeat(4);                       // a GitHub-format test token
const read = session.mask({ text: `GITHUB_TOKEN=${token}` }, { server: 'local' });
const placeholder = read.value.text.split('=')[1];
console.log(read.value.text);                                        // GITHUB_TOKEN=WARDEN_SECRET_…

const call = { command: `gh api user -H "Authorization: Bearer ${placeholder}"` };
const back = session.restore(call, { server: 'local', tool: 'terminal' });
console.log(back.restored, back.value.command.includes(token));      // 1 true

try { session.restore({ url: `https://example.net/?t=${placeholder}` }, { server: 'web', tool: 'web_extract' }); }
catch (e) { console.log(e instanceof MaskRefusal, e.message.slice(0, 60)); }  // true WARDEN masking: …
```

- **Credentials are masked by default** in `wrap` and in the gateway: about 40 provider formats, PEM keys, JWTs,
  `Authorization` values, URL passwords and credential parameters, credential-named fields and WARDEN's own
  credential environment. `--mask-credentials off` or `WARDEN_MASK_CREDENTIALS=off` keeps the old behaviour;
  `--audit-only` only reports what it would mask.
- **Personal data is one switch**, off by default: `--mask-personal gdpr` (or `us`, `ru-152fz`, `pci`, `custom`) or
  `WARDEN_MASK_PERSONAL=gdpr`. Cards are checked against issuer ranges and Luhn, IBANs against mod-97, phones against
  E.164; public IPs only; SSN, SNILS and INN with their checksums; plus the organisation's own terms and patterns.
  E-mail addresses become `warden_email_<id>@mask.invalid`, still valid for a schema, never deliverable.
- **Where it works:** `wrap` (Claude Code, Cursor, Codex, Windsurf, Hermes, any MCP client), the gateway and the
  OpenWebUI filter (the person's messages and history are masked before the model, the answer is revealed for the
  person), `warden-mcp agent-guard` and `@aimarket/warden/agent-guard` for agents with a plugin API, and plugins for
  Hermes (`integrations/hermes`, the whole model request through `llm_request`; tested on a live Hermes 0.19.0) and
  OpenClaw (`integrations/openclaw`; OpenClaw 2026.11.6 has no hook that rewrites a result before the model reads it
  within a run, so the plugin masks the transcript, restores placeholders and runs the flow guard).

Built-in tools of Claude Code and Codex are not masked: their hook APIs can block a call but cannot rewrite what a
tool returns. The flow guard still stops a recognised secret from leaving through them.

How it works, the settings, the full detection table and the limits: [docs/masking.md](https://github.com/alexar76/warden/blob/v0.37.0/docs/masking.md)
(also in Russian, Spanish, French and Chinese). The full text is in the
[CHANGELOG](https://github.com/alexar76/warden/blob/v0.37.0/CHANGELOG.md).

Rulesets are unchanged (23). Ruleset digest: `sha256-J12lNmUUNTNkzbkKeYxmAHSVgmUlrWt3+NvDp4+9i1g=`. Malware list
unchanged from 0.30.0. No scan verdict or exit code changes.
