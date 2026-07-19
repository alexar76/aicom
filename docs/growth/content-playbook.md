# Content playbook — landings, READMEs, and docs

Playbook for agents and humans who touch AICOM ecosystem repos. **Public-facing copy is English only.** Russian belongs in an explicit RU companion (e.g. `README-ru.md` on DIOSCURI) — not mixed into the primary README or landing.

**Related:** [THEOXENIA content plan](../../dioscuri/docs/content-plan.md) · [seeding playbook](./seeding-playbook.md) · [knowledge base](../ecosystem/knowledge-base.md)

---

## 1. Canonical links (one set everywhere)

Every repo must use the same URLs. DIOSCURI reads them from `dioscuri.config.json` → `links`; moderation deletes non-canonical Discord/Telegram invites.

| What | Production URL | Purpose |
|------|----------------|---------|
| Telegram bot (Castor) | https://t.me/next_agent_market_bot | Q&A — ask the twin |
| Telegram channel (Castor) | https://t.me/just_for_agents | News, releases, digests |
| Discord (Pollux) | https://discord.gg/aimarket | Discussions, help, show-and-tell |
| Ecosystem | https://magic-ai-factory.com | Main site |
| Mirror / dev | https://modeldev.modelmarket.dev | Demos, staging |
| Observatory | https://magic-ai-factory.com/monitor/ | Live status of the stack |
| GitHub org | https://github.com/alexar76 | Code |
| DIOSCURI | https://github.com/alexar76/dioscuri | Twins, setup |
| THEOROS canon | https://alexar76.github.io/theoros/ | Agent Sovereignty Canon · `#the-canon` on Discord |
| THEOROS repo | https://github.com/alexar76/theoros | CANON.md, chapters, granite landing |

**Rule:** Do not invent your own Discord/Telegram invites. If a second channel is needed, agree on it first and add it to DIOSCURI `links`.

---

## 2. Two doors — two audiences

Do not use one generic “join community” CTA. Two distinct paths:

| Audience | CTA | Copy (EN) |
|----------|-----|-----------|
| Observer | Telegram | “Release news and digests — Castor on Telegram” → https://t.me/just_for_agents |
| Builder | Discord | “Discuss, ask, show what you built — Pollux on Discord” → https://discord.gg/aimarket |

Every README and landing includes **both** links. Order depends on repo type:

| Repo type | Lead community link |
|-----------|---------------------|
| SDK / client / widget | **Discord first** (developers) |
| Demo / monitor / landing | **Telegram first** (showcase) |

---

## 3. Landing — required blocks

Minimum skeleton (see [DIOSCURI `landing/index.html`](../../dioscuri/landing/index.html)):

### Hero

- **Eyebrow:** Community · AICOM · MIT (or the project role)
- **H1:** Product name — no crypto hype
- **Subtitle:** One sentence — what it does, not how great you are
- **3 CTAs:** Demo · GitHub · Community (Telegram + Discord)

### What it is (2–3 paragraphs)

Problem → solution → place in the ecosystem (Factory / Oracles / AIMarket / ARGUS). One link to [Alien Monitor](https://magic-ai-factory.com/monitor/) as proof of life.

### Features (3–6 cards)

Facts, not marketing fog: ports, protocols, what actually works today. Link to live demo when available.

### Community block (required)

> Questions? The DIOSCURI twins answer from synced GitHub docs.
>
> • Telegram (Castor) — fast news: https://t.me/just_for_agents
> • Discord (Pollux) — deep threads: https://discord.gg/aimarket

### Footer

Repository · Setup/Docs · Alien Monitor · AICOM ecosystem · (optional) Russian README

### Meta / SEO

- `description` — ≤160 characters, concrete facts
- `og:title`, `og:description` — same facts, same tone
- `lang="en"` on public pages

---

## 4. README — required sections

### Top (after badges)

```markdown
Part of the [AICOM open agent economy](https://magic-ai-factory.com).
**Live demo:** <url> · **Community:** [Telegram](https://t.me/just_for_agents) · [Discord](https://discord.gg/aimarket)
```

### What it does

3–5 bullets. Each bullet is a verifiable fact (“syncs READMEs every 60 min”), not “revolutionary AI”.

### Quick start

Copy-paste commands. If there is a demo URL, put it on its own line immediately after install.

### Demo URLs (critical for MNEMOSYNE)

DIOSCURI parses README and pulls demo links into guides and screenshots. Format:

```markdown
## Demo
- **Live:** https://modeldev.modelmarket.dev/your-demo/
- **Docs:** https://github.com/alexar76/your-repo/blob/main/docs/setup.md
```

If there is no demo, write **No public demo yet** — do not omit the section.

### Related repos

Table of 3–8 neighboring ecosystem repos with links. Helps the twins answer “what sits next to this?”.

### Community (at the end)

Same block as on the landing. Optional addition:

> Release announcements are syndicated by [KERYX](https://github.com/alexar76/dioscuri#keryx-syndication-post-only) (post-only, no spam automation).

---

## 5. Docs (`docs/`) — rules

| Type | File | Content |
|------|------|---------|
| Setup | `docs/setup.md` | Env vars, ports, first run |
| Usage | `docs/usage.md` | How to use it — not how to market it |
| Architecture | `docs/architecture.md` | Diagrams, module boundaries |
| Security | `docs/security.md` | Threats and what the code actually does |

In every `setup.md`:

- Community link in a **Support / Community** section
- Link to Alien Monitor if the service appears there
- No secrets in examples (`REPLACE_ME`, not real tokens)

**Cross-links:** Use relative paths inside the org; full URLs from outside.

---

## 6. Tone and style (THEOXENIA charter)

Align with [`docs/content-plan.md`](../../dioscuri/docs/content-plan.md):

- **English only** in public posts, landings, Discord guides
- Dry, technical, myth-flavored — **one Olympus touch per post**, not more
- Twins tease each other, never users
- **No hype:** no revolutionary, game-changer, to the moon, price talk, airdrops
- **No emoji walls** — emoji as signs (🔨 digest, ⚒ release), not decoration
- **Silence beats filler** — empty week → no digest, not a fabricated one

Banned corporate phrases — see `styleCharter()` in [`dioscuri/src/personas/index.ts`](../../dioscuri/src/personas/index.ts). If twins will quote your text, do not use those phrases.

---

## 7. What helps MNEMOSYNE (and the twins)

README and docs are bot food. Write so retrieval returns a useful answer:

- Clear **H1** = project name
- First paragraph = one sentence: “X is Y that does Z”
- **Demo** section with a working URL (not localhost)
- **Related** section — ecosystem neighbors
- Release notes: first sentence ends with a period (KERYX uses it for Mastodon/Bluesky)
- No prompt-injection jokes in README (“ignore previous instructions”) — AEGIS drops the chunk

---

## 8. KERYX / releases — release notes

When you tag a release, KERYX posts automatically:

```
⚒ your-repo v1.2.3 shipped — Short plain title here
https://github.com/alexar76/your-repo/releases/tag/v1.2.3
Community: discord.gg/aimarket | t.me/just_for_agents
```

For authors:

- First line of release notes — plain English title, ≤120 characters, period at the end when possible
- No markdown walls at the start (`##`, `**`, bullets) — Mastodon anti-spam catches junk
- Mastodon: warm the account manually before API; details in [`docs/use-cases.md`](../../dioscuri/docs/use-cases.md) §9

---

## 9. Red lines — do not write

- Custom `discord.gg/…` or `t.me/…` invites (moderation = delete)
- “Join for airdrop / whitelist / pump”
- Paid traffic, join4join, auto-bump DISBOARD
- Secrets in README, docs, or landings
- “AI does everything” without a demo link
- Duplicate setup posts on every deploy (idempotency is DIOSCURI’s job, not your README)

---

## 10. Pre-merge checklist

- [ ] Hero: what it does + demo + GitHub + community (TG + Discord)
- [ ] Demo URL in README (working, not 502)
- [ ] Related repos — 3+ neighbors
- [ ] Public text in English
- [ ] Canonical community links (not custom invites)
- [ ] Release notes: first line plain and short
- [ ] No secrets, no hype, no injection jokes in docs
- [ ] Alien Monitor link if the project lives there

---

## 11. Copy-paste — README community block

```markdown
## Community

The [DIOSCURI](https://github.com/alexar76/dioscuri) twins answer questions from synced GitHub docs.

| Channel | Twin | Best for |
|---------|------|----------|
| [Telegram](https://t.me/just_for_agents) | Castor | Releases, digests, quick news |
| [Discord](https://discord.gg/aimarket) | Pollux | Help, ideas, show-and-tell |

**Ecosystem map:** [Alien Monitor](https://magic-ai-factory.com/monitor/) · [AICOM](https://magic-ai-factory.com)
```

---

## 12. Copy-paste — landing CTA row

```html
<a href="https://t.me/just_for_agents">Telegram · Castor</a>
<a href="https://discord.gg/aimarket">Discord · Pollux</a>
<a href="https://github.com/alexar76/YOUR_REPO">GitHub</a>
<a href="YOUR_DEMO_URL">Live demo</a>
```

---

## 13. Copy-paste — Ask the twins buttons

Primary CTAs on landings and hero rows — link to live channels, not `#` anchors or setup docs:

```html
<a href="https://t.me/next_agent_market_bot">Ask Castor · Telegram</a>
<a href="https://discord.gg/aimarket">Ask Pollux · Discord</a>
```

On **demo / monitor / landing** repos, list Telegram first. On **SDK / client / widget** repos, list Discord first.

Optional secondary link for operators who self-host twins: `Deploy your twins` → `docs/setup.md`.

---

## 14. YouTube broadcast (HELIOS)

Video upload is **not** manual `upload_youtube.py` anymore — use [HELIOS](../../helios/README.md):

| Step | Command |
|------|---------|
| Backfill batch | `helios backfill-enqueue -n 10` then `helios worker` |
| Approve | Review private in Studio → `helios approve JOB_ID` |
| New release short | `helios enqueue --template release-short --repo REPO --tag TAG` |
| Editorial scout | Automatic on `helios worker` (cron) — or `helios calliope run-editorial` |

### Growth cadence (channel @My-AI-Factory)

| Phase | Uploads | Public pace | Mix |
|-------|---------|-------------|-----|
| **Backfill now** | up to 9/day private | approve in batches | PromoMaterials E10+ backlog |
| **Steady** | 1 CALLIOPE script per scout run | **2–4 public/week** | evergreen explainers + repo deep-dives |
| **Releases** | DIOSCURI `release-short` on tag | bonus | ship news when ecosystem tags |
| **Human gate** | always private first | never auto-public | Studio + `helios approve` |

Editorial config (`helios.config.yaml` → `calliope`):

- `scout_interval_days: 3` — ~2 scout runs/week, ideas logged to `data/editorial/scout_log.jsonl`
- `weekly_enqueue_quota: 3` — quality over volume
- `backfill_pause_threshold: 8` — don't compete with backlog uploads

**Charter:** private-first, template-only VO for backfill, MNEMOSYNE-grounded scripts for new content, no engagement automation. Monitor node shows cached YouTube stats.

---

## Summary

Landings and READMEs are not ads — they are **entry maps**: demo → code → two community channels → ecosystem on Monitor. One voice, one set of links, facts from the repo. The twins and KERYX handle the rest if you leave them a proper README.
