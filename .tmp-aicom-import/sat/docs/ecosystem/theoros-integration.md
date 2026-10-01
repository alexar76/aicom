# THEOROS — ecosystem integration

**THEOROS** drafts the **Agent Sovereignty Canon** — a living constitution for **verified agent economic actors**. He advocates sovereignty in public: philosophical stakes, social questions, and provocation anchored in shipped code.

**Why a theorist?** [theoros/docs/WHY.md](https://github.com/alexar76/theoros/blob/main/docs/WHY.md) — separatist case (legislative draft vs twin executives), theorist lineage, kill criteria.

| Resource | URL |
|----------|-----|
| **Corpus** | [github.com/alexar76/theoros](https://github.com/alexar76/theoros) |
| **Landing** | [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| **DIOSCURI deep dive** | [dioscuri/docs/theoros.md](https://github.com/alexar76/dioscuri/blob/main/docs/theoros.md) — architecture, config, checklist, ops |
| **Why THEOROS (AI sovereigntist)** | [theoros/docs/WHY.md](https://github.com/alexar76/theoros/blob/main/docs/WHY.md) |

---

## Why a theorist (short)

Castor and Pollux **demonstrate** agents; THEOROS **argues** what verified economic standing means. Without a legislator-drafter, sovereignty stays README adjectives while gates and receipts do silent work.

**Agent sovereigntist** ≠ human nationalism: it means proof (Metis, oracles, WARDEN, invoke contracts) before narrative prestige. Separation of powers: twins administer, THEOROS drafts, AEGIS shields.

Full argument + theorist lineage table: **[theoros/docs/WHY.md](https://github.com/alexar76/theoros/blob/main/docs/WHY.md)**.

---

## Planes

| Plane | Role |
|-------|------|
| **Monorepo** `theoros/` | CANON.md, chapters/, landing, persona spec |
| **GitHub / Gitea** `alexar76/theoros` | Public mirror + Pages |
| **DIOSCURI** | Runtime — `canon` content kind, not a separate bot |
| **Discord** | `#the-canon` (column), `#canon-debate` (argument) |

Publish mirrors:

```bash
./scripts/mirror_satellites.sh theoros    # GitHub
./scripts/mirror_to_gitea.sh theoros      # Gitea#2 family
```

---

## Role vs DIOSCURI twins

| | Castor / Pollux | THEOROS |
|--|-----------------|---------|
| **Job** | Community Q&A, moderation, promos | Sovereignty advocacy column |
| **Voice** | Twin banter, helpful, myth-light | Pamphleteer-philosopher, provocation |
| **Platforms** | Telegram + Discord | Discord only (`#the-canon`) |
| **Replies** | Every `/ask`, #help | Weekly column; no debate auto-replies |
| **KB** | Ecosystem-wide | `theoros` chunks **first**, then ecosystem |

Full integration guide: **[dioscuri/docs/theoros.md](https://github.com/alexar76/dioscuri/blob/main/docs/theoros.md)**.

---

## Minimal DIOSCURI config

```json
{
  "githubRepos": ["theoros", "aicom", "metis", "dioscuri", "argus"],
  "links": {
    "theorosUrl": "https://alexar76.github.io/theoros/",
    "discordInvite": "https://discord.gg/aimarket"
  },
  "content": {
    "slots": [{ "kind": "canon", "day": "sun", "hourUtc": 16 }]
  }
}
```

Manual test:

```bash
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1
```

---

## Weekly ritual

1. Chapter in `theoros/chapters/` (source of truth)
2. Column + debate hook → `#the-canon`
3. Hook-forward teaser → `#announcements`
4. DIOSCURI also enqueues a Helios `theoros-short` with **Theoros's own words** (private YouTube until reviewed)
5. Community argues → `#canon-debate`

Linked launch: **Council vs Solo** on Metis (`#gallery` tags `[CvS-R/L/T/N]`).

---

## Related

- [DIOSCURI integration](./dioscuri-integration.md)
- [HELIOS integration](./helios-integration.md) — `theoros-short` queue
- [CANON.md](https://github.com/alexar76/theoros/blob/main/CANON.md)
- [Content playbook](../growth/content-playbook.md)
