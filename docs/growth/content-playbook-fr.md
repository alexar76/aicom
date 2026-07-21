# Content playbook — landings, READMEs et docs

> 🌐 Langues : [English](./content-playbook.md) · [Русский](./content-playbook-ru.md) · **Français** · [中文](./content-playbook-zh.md)

Playbook pour les agents et les humains qui touchent aux dépôts de l'écosystème AICOM. **Le texte public est en anglais uniquement.** Le russe a sa place dans un compagnon RU explicite (par ex. `README-ru.md` sur DIOSCURI) — pas mélangé dans le README ou la landing principale.

**Voir aussi :** [THEOXENIA content plan](../../dioscuri/docs/content-plan.md) · [seeding playbook](./seeding-playbook.md) · [knowledge base](../ecosystem/knowledge-base.md)

---

## 1. Liens canoniques (un seul jeu partout)

Chaque dépôt doit utiliser les mêmes URL. DIOSCURI les lit depuis `dioscuri.config.json` → `links` ; la modération supprime les invitations Discord/Telegram non canoniques.

| Quoi | URL de production | Rôle |
|------|-------------------|------|
| Telegram bot (Castor) | https://t.me/next_agent_market_bot | Q&A — poser une question au jumeau |
| Telegram channel (Castor) | https://t.me/just_for_agents | News, releases, digests |
| Discord (Pollux) | https://discord.gg/aimarket | Discussions, aide, show-and-tell |
| Écosystème | https://magic-ai-factory.com | Site principal |
| Miroir / dev | https://modeldev.modelmarket.dev | Démos, staging |
| Observatory | https://magic-ai-factory.com/monitor/ | Statut live de la stack |
| GitHub org | https://github.com/alexar76 | Code |
| DIOSCURI | https://github.com/alexar76/dioscuri | Jumeaux, setup |
| THEOROS canon | https://alexar76.github.io/theoros/ | Agent Sovereignty Canon · `#the-canon` sur Discord |
| THEOROS repo | https://github.com/alexar76/theoros | CANON.md, chapitres, landing granit |

**Règle :** N'inventez pas vos propres invitations Discord/Telegram. Si un second canal est nécessaire, mettez-vous d'accord d'abord et ajoutez-le aux `links` de DIOSCURI.

---

## 2. Deux portes — deux audiences

N'utilisez pas un CTA générique unique « join community ». Deux chemins distincts :

| Audience | CTA | Copy (EN) |
|----------|-----|-----------|
| Observer | Telegram | “Release news and digests — Castor on Telegram” → https://t.me/just_for_agents |
| Développeur | Discord | “Discuss, ask, show what you built — Pollux on Discord” → https://discord.gg/aimarket |

Chaque README et landing inclut **les deux** liens. L'ordre dépend du type de dépôt :

| Type de dépôt | Lien community en tête |
|---------------|------------------------|
| SDK / client / widget | **Discord d'abord** (développeurs) |
| Demo / monitor / landing | **Telegram d'abord** (vitrine) |

---

## 3. Landing — blocs requis

Squelette minimal (voir [DIOSCURI `landing/index.html`](../../dioscuri/landing/index.html)) :

### Hero

- **Eyebrow :** Community · AICOM · MIT (ou le rôle du projet)
- **H1 :** nom du produit — pas de hype crypto
- **Subtitle :** une phrase — ce que ça fait, pas à quel point vous êtes géniaux
- **3 CTA :** Demo · GitHub · Community (Telegram + Discord)

### Ce que c'est (2–3 paragraphes)

Problème → solution → place dans l'écosystème (Factory / Oracles / AIMarket / ARGUS). Un lien vers [Alien Monitor](https://magic-ai-factory.com/monitor/) comme preuve de vie.

### Features (3–6 cartes)

Des faits, pas du brouillard marketing : ports, protocoles, ce qui fonctionne réellement aujourd'hui. Lien vers une démo live quand elle existe.

### Community block (requis)

> Questions? The DIOSCURI twins answer from synced GitHub docs.
>
> • Telegram (Castor) — fast news: https://t.me/just_for_agents
> • Discord (Pollux) — deep threads: https://discord.gg/aimarket

### Footer

Repository · Setup/Docs · Alien Monitor · AICOM ecosystem · (optionnel) README russe

### Meta / SEO

- `description` — ≤160 caractères, faits concrets
- `og:title`, `og:description` — mêmes faits, même ton
- `lang="en"` sur les pages publiques

---

## 4. README — sections requises

### Top (after badges)

```markdown
Part of the [AICOM open agent economy](https://magic-ai-factory.com).
**Live demo:** <url> · **Community:** [Telegram](https://t.me/just_for_agents) · [Discord](https://discord.gg/aimarket)
```

### What it does

3–5 puces. Chaque puce est un fait vérifiable (« syncs READMEs every 60 min »), pas « revolutionary AI ».

### Quick start

Commandes copy-paste. S'il y a une URL de démo, mettez-la sur sa propre ligne juste après l'installation.

### Demo URLs (critique pour MNEMOSYNE)

DIOSCURI parse le README et récupère les liens de démo dans les guides et les captures. Format :

```markdown
## Demo
- **Live:** https://modeldev.modelmarket.dev/your-demo/
- **Docs:** https://github.com/alexar76/your-repo/blob/main/docs/setup.md
```

S'il n'y a pas de démo, écrivez **No public demo yet** — n'omettez pas la section.

### Related repos

Tableau de 3 à 8 dépôts voisins de l'écosystème avec liens. Aide les jumeaux à répondre à « qu'est-ce qui se trouve à côté de ça ? ».

### Community (à la fin)

Même bloc que sur la landing. Ajout optionnel :

> Release announcements are syndicated by [KERYX](https://github.com/alexar76/dioscuri#keryx-syndication-post-only) (post-only, no spam automation).

---

## 5. Docs (`docs/`) — règles

| Type | Fichier | Contenu |
|------|---------|---------|
| Setup | `docs/setup.md` | Variables d'env, ports, premier lancement |
| Usage | `docs/usage.md` | Comment l'utiliser — pas comment le marketer |
| Architecture | `docs/architecture.md` | Diagrammes, frontières de modules |
| Security | `docs/security.md` | Menaces et ce que le code fait réellement |

Dans chaque `setup.md` :

- Lien community dans une section **Support / Community**
- Lien vers Alien Monitor si le service y apparaît
- Pas de secrets dans les exemples (`REPLACE_ME`, pas de vrais tokens)

**Cross-links :** Chemins relatifs à l'intérieur de l'org ; URL complètes depuis l'extérieur.

---

## 6. Ton et style (THEOXENIA charter)

S'aligner sur [`docs/content-plan.md`](../../dioscuri/docs/content-plan.md) :

- **English only** dans les posts publics, landings, guides Discord
- Dry, technical, myth-flavored — **un seul Olympus touch par post**, pas plus
- Twins tease each other, never users
- **No hype :** pas de revolutionary, game-changer, to the moon, price talk, airdrops
- **No emoji walls** — l'emoji comme signe (🔨 digest, ⚒ release), pas décoration
- **Silence beats filler** — semaine vide → pas de digest, pas un digest fabriqué

Phrases corporate interdites — voir `styleCharter()` dans [`dioscuri/src/personas/index.ts`](../../dioscuri/src/personas/index.ts). Si les jumeaux vont citer votre texte, n'utilisez pas ces phrases.

---

## 7. Ce qui aide MNEMOSYNE (et les jumeaux)

README et docs sont de la nourriture à bot. Écrivez pour que le retrieval renvoie une réponse utile :

- **H1** clair = nom du projet
- Premier paragraphe = une phrase : « X is Y that does Z »
- Section **Demo** avec une URL qui marche (pas localhost)
- Section **Related** — voisins de l'écosystème
- Release notes : la première phrase se termine par un point (KERYX l'utilise pour Mastodon/Bluesky)
- Pas de blagues de prompt-injection dans le README (« ignore previous instructions ») — AEGIS jette le chunk

---

## 8. KERYX / releases — release notes

Quand vous taguez une release, KERYX poste automatiquement :

```
⚒ your-repo v1.2.3 shipped — Short plain title here
https://github.com/alexar76/your-repo/releases/tag/v1.2.3
Community: discord.gg/aimarket | t.me/just_for_agents
```

Pour les auteurs :

- Première ligne des release notes — plain English title, ≤120 caractères, point à la fin si possible
- Pas de murs markdown au début (`##`, `**`, puces) — l'anti-spam de Mastodon attrape le junk
- Mastodon : chauffez le compte manuellement avant l'API ; détails dans [`docs/use-cases.md`](../../dioscuri/docs/use-cases.md) §9

---

## 9. Lignes rouges — à ne pas écrire

- Invitations `discord.gg/…` ou `t.me/…` custom (modération = delete)
- « Join for airdrop / whitelist / pump »
- Trafic payant, join4join, auto-bump DISBOARD
- Secrets dans le README, les docs ou les landings
- « AI does everything » sans lien de démo
- Posts de setup dupliqués à chaque déploiement (l'idempotence est le job de DIOSCURI, pas de votre README)

---

## 10. Checklist avant merge

- [ ] Hero : ce que ça fait + demo + GitHub + community (TG + Discord)
- [ ] URL de démo dans le README (qui marche, pas 502)
- [ ] Related repos — 3+ voisins
- [ ] Texte public en anglais
- [ ] Liens community canoniques (pas d'invitations custom)
- [ ] Release notes : première ligne plain et courte
- [ ] Pas de secrets, pas de hype, pas de blagues d'injection dans les docs
- [ ] Lien Alien Monitor si le projet y vit

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

## 13. Copy-paste — boutons « Ask the twins »

CTA principaux sur les landings et les hero rows — liens vers des canaux live, pas des ancres `#` ni des setup docs :

```html
<a href="https://t.me/next_agent_market_bot">Ask Castor · Telegram</a>
<a href="https://discord.gg/aimarket">Ask Pollux · Discord</a>
```

Sur les dépôts **demo / monitor / landing**, listez Telegram d'abord. Sur les dépôts **SDK / client / widget**, listez Discord d'abord.

Lien secondaire optionnel pour les opérateurs qui hébergent eux-mêmes les jumeaux : `Deploy your twins` → `docs/setup.md`.

---

## 14. Diffusion YouTube (HELIOS)

L'upload vidéo n'est **plus** un `upload_youtube.py` manuel — utilisez [HELIOS](../../helios/README.md) :

| Étape | Commande |
|-------|----------|
| Backfill par lots | `helios backfill-enqueue -n 10` puis `helios worker` |
| Approve | Relire le privé dans Studio → `helios approve JOB_ID` |
| Short pour une nouvelle release | `helios enqueue --template release-short --repo REPO --tag TAG` |
| Éclaireur éditorial | Automatique sur `helios worker` (cron) — ou `helios calliope run-editorial` |

### Growth cadence (channel @My-AI-Factory)

| Phase | Uploads | Rythme public | Mix |
|-------|---------|---------------|-----|
| **Backfill maintenant** | jusqu'à 9/jour en privé | approve par lots | backlog PromoMaterials E10+ |
| **Régime stable** | 1 script CALLIOPE par run d'éclaireur | **2–4 publics/semaine** | explainers evergreen + deep-dives de dépôts |
| **Releases** | DIOSCURI `release-short` sur tag | bonus | livrer les news quand l'écosystème tague |
| **Human gate** | toujours privé d'abord | jamais auto-public | Studio + `helios approve` |

Config éditoriale (`helios.config.yaml` → `calliope`) :

- `scout_interval_days: 3` — ~2 runs d'éclaireur/semaine, idées loggées dans `data/editorial/scout_log.jsonl`
- `weekly_enqueue_quota: 3` — la qualité avant le volume
- `backfill_pause_threshold: 8` — ne pas concurrencer les uploads du backlog

**Charter :** private-first, VO template-only pour le backfill, scripts fondés sur MNEMOSYNE pour le nouveau contenu, aucune automation d'engagement. Le nœud Monitor affiche les stats YouTube en cache.

---

## Summary

Landings et READMEs ne sont pas des pubs — ce sont des **cartes d'entrée** : demo → code → deux canaux community → écosystème sur Monitor. Une seule voix, un seul jeu de liens, des faits venus du dépôt. Les jumeaux et KERYX gèrent le reste si vous leur laissez un README correct.
