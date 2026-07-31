# DIOSCURI — intégration dans l'écosystème

Comment **DIOSCURI** (agents communautaires jumeaux) s'intègre dans le stack AICOM aux côtés de GitHub, Gitea et Alien Monitor.

**Landing :** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **Langues :** **[EN](./dioscuri-integration.md)** · **[RU](./dioscuri-integration-ru.md)** · **[ES](./dioscuri-integration-es.md)** · **FR** · **[ZH](./dioscuri-integration-zh.md)**

## Plans

| Plan | Rôle |
|------|------|
| **Monorepo** `dioscuri/` | Source de vérité |
| **GitHub** `alexar76/dioscuri` | Miroir public — docs, CI, référence d'auto-hébergement |
| **Gitea#2** `alexar76/dioscuri` | Miroir ops privé (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Nœud du graphe — sonde `GET /health`, affiche le KB + l'état des adaptateurs |

Publier le miroir GitHub (sans secrets) :

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

Synchroniser Gitea (opérateur) :

```bash
./scripts/mirror_to_gitea.sh dioscuri
```

## Déploiement sur l'hôte oracle (oracles.modelmarket.dev)

DIOSCURI tourne sur le **VPS oracle**, pas sur la flotte de la fabrique (`modeldev.modelmarket.dev`). Factory Monitor ne sonde que `http://oracles.modelmarket.dev:8790/health`.

**Une seule commande** (mirror → Gitea#2 → ssh → git pull → compose) :

```bash
./scripts/deploy_dioscuri_oracle.sh
RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh   # + première colonne THEOROS
```

Nécessite un `ssh root@oracles.modelmarket.dev` sans mot de passe (ou `ssh oracle` — voir `~/.ssh/config`). L'authentification pour **git push** utilise `data/secrets/git-credentials` (comme `mirror_to_gitea.sh`), pas SSH.

Équivalent manuel sur oracle après le mirror :

```bash
ssh root@oracles.modelmarket.dev
cd /root/dioscuri && git pull --ff-only && docker compose up -d --build
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
```

`./scripts/deploy_cognition.sh` sert au stack cognition **local** sur l'hôte où vous l'exécutez — ce n'est pas un wrapper pour un oracle distant.

## Secrets — jamais dans git

| Fichier | Objet |
|---------|-------|
| `.env` | Jetons de bots, clés LLM, clés de syndication |
| `dioscuri.config.json` | Réglages non secrets (liens, sujets, boutons de modération) |

Les deux sont **exclus** du rsync des satellites (`satellite-map.yaml` → `exclude_paths`) et bloqués par `scripts/verify_mirror_secrets.sh` avant le push.

Copiez uniquement les modèles :

```bash
cp dioscuri/.env.example dioscuri/.env
cp dioscuri/dioscuri.config.example.json dioscuri/dioscuri.config.json
```

Renseignez les jetons en local — **ne committez jamais**.

## Liens communautaires (Telegram + Discord)

**Production (canonique — à utiliser dans les README et landings) :**

| Clé | URL |
|-----|-----|
| Bot Telegram (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Canal Telegram (Castor — actualités) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Les auto-hébergeurs définissent les invitations dans `dioscuri.config.json` :

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT",
  "siteUrl": "https://magic-ai-factory.com",
  "githubOrg": "https://github.com/alexar76"
}
```

Alien Monitor lit les liens publics depuis l'env (optionnel, pour le panneau du graphe) :

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790          # cible du sondage (réseau compose)
```

## THEOROS (colonne canon)

**THEOROS** est une troisième persona dans le même processus DIOSCURI — pas un bot distinct. Elle publie chaque semaine le **Agent Sovereignty Canon** sur Discord `#the-canon` (dimanche ~16 UTC, content kind `canon`).

| Ressource | URL |
|-----------|-----|
| Corpus + landing | [alexar76/theoros](https://github.com/alexar76/theoros) · [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| Débat | `#canon-debate` sur le Discord DIOSCURI |
| Config | `links.theorosUrl` dans `dioscuri.config.json` ; ajoutez `"theoros"` à `githubRepos` pour le grounding de MNEMOSYNE |
| Exécution manuelle | `DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1` |

Castor/Pollux annoncent les chapitres ; ils **n'usurpent pas** l'identité de Theoros. Guide complet : **[dioscuri/docs/theoros.md](../../dioscuri/docs/theoros.md)** (architecture, voice charter, config, checklist).

## Nœud Alien Monitor

Le nœud **DIOSCURI** apparaît au nord-ouest de la client shelf. Il sonde :

```
GET {ALIEN_DIOSCURI_URL}/health
```

Champs de réponse utilisés : `adapters.telegram`, `adapters.discord`, `kb.chunks`, `kb.repos`, `uptimeSec`, `social.*` (métriques Discord/Telegram/X mises en cache).

Gris = inaccessible ; pulsation dorée = au moins un jumeau actif ou KB initialisé.

### Statistiques sociales (mises en cache)

`GET /health` inclut `social` lorsque les jetons d'API des plateformes sont configurés :

| Champ | Source |
|-------|--------|
| `discord_members` | Discord Bot API `approximate_member_count` |
| `telegram_members` | Telegram `getChatMemberCount` |
| `twitter_followers` | X API v2 `public_metrics` |

TTL du cache : `DIOSCURI_SOCIAL_CACHE_SEC` (300s par défaut). Alien Monitor affiche les métriques depuis le cache dès le clic sur le nœud — aucun appel API en direct depuis le graphe.

Env optionnels : `TWITTER_BEARER_TOKEN`, `TWITTER_USER_ID`, `TELEGRAM_CHANNEL_ID`.

## Syndication HELIOS (optionnel)

Lorsque `HELIOS_SYNDICATION=1`, DIOSCURI ajoute des tâches `release-short` à `HELIOS_QUEUE_PATH` à chaque nouvelle release GitHub (fail-soft). Voir [helios-integration.md](./helios-integration.md).

## MNEMOSYNE ↔ GitHub

Les jumeaux synchronisent les README et les releases depuis des **dépôts GitHub publics** (`githubOwner: alexar76`). DIOSCURI n'a pas besoin de son propre dépôt dans la liste KB pour répondre aux questions sur l'écosystème — mais publier `alexar76/dioscuri` permet aux jumeaux de se documenter eux-mêmes.

## Co-auteurs et collaborateurs

Les push de satellites sont regroupés en **un seul commit à auteur humain** (`sanitize_git_commit_meta.py` retire `Co-Authored-By` et les trailers d'outils d'IA). Après le push, `prune_github_collaborators.py` supprime du dépôt les collaborateurs bot/cursor/copilot.

## Connexes

- [DIOSCURI README (EN)](../../dioscuri/README.md) · [RU](../../dioscuri/README-ru.md) · [ES](../../dioscuri/README-es.md)
- [Setup](../../dioscuri/docs/setup.md)
- [Base de connaissances de l'écosystème](./knowledge-base.md)
- [Publication Gitea](../gitea-publishing.md) (interne)
