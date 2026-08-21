# Déployer tout l'écosystème — démarrage rapide à partir de zéro

Un runbook par paliers pour mettre en place l'écosystème public complet sur un VPS Ubuntu vierge.
Il enveloppe les scripts de déploiement existants — il **n'**introduit **pas** de nouveau moteur de
déploiement. Commencez au palier dont vous avez besoin et arrêtez-vous là ; chaque palier s'appuie sur le précédent.

Pour la référence de niveau opérationnel (redéploiements partiels, le danger du redéploiement du Hub,
l'ordre exact des étapes manuelles), voir **[`deploy-ecosystem.md`](./deploy-ecosystem.md)**.

---

## 1. Ce qu'est « l'écosystème »

| Composant | Ce qu'il fait | Conteneur / processus |
|-----------|--------------|---------------------|
| **Factory** | Construit et livre des produits IA (le stack Compose `aicom-app`) | `aicom-app-1` |
| **Hub** | Hub de fédération AIMarket Protocol v2 — discovery, channels, invoke, settle | `modelmarket-hub` |
| **Mesh** | API de maillage (mesh) de services qui relie les produits entre eux | `aicom-mesh-api` |
| **ARGUS-3** | Agent personnel + pare-feu MCP WARDEN (client de référence) | `argus` / `:8787` |
| **Alien Monitor** | Visualiseur 3D de l'écosystème (modes UNIVERSE / TEST / REAL) + terminal **Pulse** | `alien-monitor`, Pulse |
| **Lottery relayer** | Relayer en mode UNI pour le flux du Monitor en direct (optionnel ; l'étape peut WARN) | `:9195` |
| **Ecosystem landing** | Carte publique sur [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) | nginx statique / étape 7 |
| **Oracles** | Dix-sept oracles de maths vérifiables sur [oracles.modelmarket.dev](https://oracles.modelmarket.dev) (+ la caverne Platon UMBRAL) | **hôte séparé (L4)** |
| **On-chain** (optionnel) | Contrats Base-mainnet : Escrow, NFT de capability, Agent Lottery | déploiement Foundry |

**Pas dans `deploy_ecosystem.sh` :** Metis, DIOSCURI, HELIOS — à exécuter séparément si besoin ; voir [§Ce qu'un seul VPS n'inclut pas](#9-ce-quun-seul-vps-ninclut-pas).

Les paliers d'onboarding :

| Palier | Objectif | Une seule commande |
|-------|------|-------------|
| **L1** | L'essayer en local (Factory seul) | `./scripts/quickstart.sh` |
| **L2** | Auto-héberger le **core fleet** sur un VPS | `./scripts/quickstart_ecosystem.sh` (wrapper de preflight) ou `./scripts/deploy_ecosystem.sh` |
| **L3** | Production publique (DNS + TLS + verify) | `./scripts/quickstart_ecosystem.sh --public-url https://…` |
| **L4** | Hôte des oracles (**machine séparée** par défaut) | `./scripts/setup-oracles-platon-on-host.sh` |

Le modèle d'authentification pour *consommer* le Hub est **Ed25519** (le SDK signe chaque invoke ; la
clé du portefeuille (wallet) est un seed Ed25519 de 32 octets, pas une clé Ethereum). secp256k1/EIP-712
est optionnel et n'est utilisé que pour les débits de canal on-chain. Voir la
[documentation du SDK AIMarket](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) et
l'[agent Python](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) (sans état, sans portefeuille) pour le côté consommateur.

---

## 2. Prérequis

Sur le VPS Ubuntu cible, avant tout palier :

- **Docker Engine + Compose v2** (`docker compose`, pas l'ancien `docker-compose`).
- **nginx** — terminaison TLS et reverse proxy (paliers 3–4).
- **Enregistrements DNS A/AAAA** pointant vers l'hôte que vous utilisez (palier 3+) :
  - `magic-ai-factory.com`, `www.magic-ai-factory.com` → hôte Factory
  - `modelmarket.dev`, `www.modelmarket.dev` → hôte Factory
  - `oracles.modelmarket.dev` → **hôte des oracles** (`oracles.modelmarket.dev`), directement (sans proxy factory)
- **Un `.env` renseigné** à la racine du repo. Copiez `.env.example` et définissez au moins une clé LLM :

```bash
cp .env.example .env
# then set, e.g.:
#   DEEPSEEK_API_KEY=...
#   ANTHROPIC_API_KEY=...
# optional port overrides:
#   AICOM_PORT_FRONTEND=9080
#   AICOM_PORT_API=9081
```

Pour les clés LLM, préférez les secrets en fichier (`data/secrets/llm/<provider>_api_key` + l'overlay
`docker-compose.secrets.yml`) plutôt que des entrées `environment:` en ligne — voir les commentaires
dans `.env.example`.

---

## 3. Palier 1 — L'essayer en local

Factory seul. Construit l'image, lance le stack et met en file d'attente un produit de démo de bout en bout :

```bash
./scripts/quickstart.sh                      # build + run + landing demo
./scripts/quickstart.sh --no-build           # reuse the existing image
./scripts/quickstart.sh "Your product idea"  # full_software profile from your idea
```

Ce qu'il fait : `./run.sh` (build) → run → `./demo.sh --no-open` (met en file un produit de démo).
Suivez la progression dans **Admin → Pipeline** sur `http://localhost:9080`. Une rejouabilité de build
d'exemple sans Docker se trouve dans `docs/sample-output/build-replay-spliteasy.json`.

---

## 4. Palier 2 — Auto-héberger le core fleet (un VPS)

**Wrapper recommandé** (preflight Docker + vérification `.env` + deploy + next steps) :

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --skip-verify          # faster; not for prod
./scripts/quickstart_ecosystem.sh --public-url https://…   # forwarded to deploy engine
```

Le wrapper appelle **`scripts/deploy_ecosystem.sh`** — la source de vérité. Vous pouvez l'invoquer
directement :

```bash
./scripts/deploy_ecosystem.sh
```

Le script s'exécute, dans cet ordre fixe :

1. **Factory** — `./scripts/deploy.sh` (`aicom-app-1`)
2. **Hub** — `./scripts/deploy_hub.sh` (`modelmarket-hub`, **jamais** le Compose du sous-dossier)
3. **Mesh** — `./scripts/deploy_mesh.sh` (`aicom-mesh-api`)
4. **ARGUS-3** — `./scripts/deploy_argus.sh` (`:8787`)
5. **Alien Monitor + Pulse** — `./scripts/deploy_alien_monitor.sh`
6. **UNI lottery relayer** — `./scripts/deploy_lottery_uni.sh` (non fatal ; journalise un WARN en cas d'échec)
7. **Ecosystem landing** — `./scripts/deploy_ecosystem_landing.sh` (non fatal ; `modeldev.modelmarket.dev`)

Il **préchauffe** ensuite l'API Factory (`/api/health`, `/api/products`) et exécute
`./scripts/verify_ecosystem_full.sh` (**17+ vérifications smoke**) sauf si vous passez `--skip-verify`.

### Ports (hôte)

| Service | Port hôte | Health / entrée |
|---------|-----------|----------------|
| Factory API | `:9081` | `GET /api/health` |
| Factory UI (frontend) | `:9080` | `GET /` |
| Hub | `:9083` | `GET /.well-known/ai-market.json` |
| Mesh | `:8090` | `GET /v1/stats` |
| ARGUS | `:8787` | `GET /health` |
| Alien Monitor | `:9100` | `GET /api/health` |
| Terminal Pulse | `:5199` | `GET /` |
| UNI lottery relayer | `:9195` | `GET /healthz` |
| Ecosystem landing | vhost nginx | `https://modeldev.modelmarket.dev/` (après le TLS L3) |

> **Le port public de l'UI est `:9080`, pas l'ancien `:8080`.** nginx fait office de proxy du domaine
> public vers `127.0.0.1:9080`.

Options :

```bash
./scripts/deploy_ecosystem.sh --skip-verify   # faster; skips the smoke suite (not for prod)
```

---

## 5. Palier 3 — Production publique

### 5.1 Pointer le DNS

Les enregistrements A/AAAA pour `magic-ai-factory.com`, `www.magic-ai-factory.com`, `modelmarket.dev`
et `www.modelmarket.dev` doivent résoudre vers cet hôte **avant** l'émission des certificats.

### 5.2 Déployer avec l'URL publique intégrée

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

`--public-url` est transmis à `deploy.sh` afin que `NEXT_PUBLIC_SITE_URL` soit défini pour le build
Next.js (Open Graph, sitemap, métadonnées côté serveur). Si le TLS n'est pas encore actif, vous pouvez
d'abord utiliser `http://magic-ai-factory.com`, puis reconstruire l'image de l'app une fois HTTPS en place.

### 5.3 Commandes TLS uniques (à exécuter en root)

**vhost du Hub + AIMarket Hub + Let's Encrypt** pour `modelmarket.dev` :

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
```

Cela installe `deploy/nginx/modelmarket.dev.conf`, construit `modelmarket-hub:latest` depuis le
contexte de la **racine du repo**, lance le hub sur `127.0.0.1:9083`, active `certbot.timer` et émet
le certificat pour `modelmarket.dev` + `www.modelmarket.dev`.

**vhost Factory** pour `magic-ai-factory.com` (selon [`production-domain.md`](./production-domain.md)) :

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

Une fois HTTPS actif, définissez `NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com` dans `.env` et
reconstruisez pour que le bundle le prenne en compte :

```bash
docker compose build app --no-cache
docker compose up -d
```

L'Alien Monitor public est servi sur `https://magic-ai-factory.com/monitor/` (nginx fait office de proxy
de `/monitor/` → `127.0.0.1:9100` ; `deploy_alien_monitor.sh` patche le vhost Certbot actif si le bloc
est manquant).

### 5.4 Vérifier

```bash
./scripts/verify_ecosystem_full.sh
```

Attendez-vous à **`17/17 PASS`**.

---

## 6. Palier 4 — Hôte des oracles

Les oracles s'exécutent sur une **machine séparée** (`oracles.modelmarket.dev`). **`deploy_ecosystem.sh` NE
déploie NI les oracles NI Platon** — `oracles/` et `platon/` dans ce monorepo sont des miroirs
d'archive du stack externe. Configurez-les sur l'hôte Platon, puis fédérez depuis l'hôte Factory.

### 6.1 Sur l'hôte Platon (`oracles.modelmarket.dev`, en root)

L'app Platon doit déjà écouter sur `127.0.0.1:8080` avec
`PUBLIC_URL=https://oracles.modelmarket.dev`. Ensuite :

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

Cela installe `deploy/nginx/oracles.modelmarket.dev.conf`, vérifie Platon sur
`127.0.0.1:8080/api/health` et émet le certificat pour `oracles.modelmarket.dev`.

### 6.2 Depuis l'hôte Factory — fédérer

```bash
./scripts/announce-platon-oracles.sh
```

Cela lit le token admin (`data/secrets/aimarket_admin_token.txt`), envoie un POST sur
`/ai-market/v2/federation/announce` au hub local (`:9083`) avec l'URL well-known de Platon et la clé
publique du signataire, puis déclenche un crawl de fédération.

Vérifiez l'hôte des oracles :

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

Les dix-sept oracles (Platon, Chronos, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier) et la
boucle économique sont documentés dans [`oracles/docs/en.md`](https://github.com/alexar76/oracles/blob/main/docs/en.md).

---

## 7. Optionnel — On-chain (Base, chain 8453)

Maintenu **séparé** de l'orchestration des conteneurs. Ces commandes déploient des contrats Solidity
sur Base mainnet avec Foundry. Les deux effectuent par défaut un dry run sans gaz ; passez `broadcast`
pour dépenser du gaz réel.

**Cœur de l'écosystème** — FakeUSDT + `AIMarketEscrow` + `AIMarketCapabilityNFT`
(ACEX est volontairement exclu — l'audit a signalé AuditPool TWAP + PulseAMM comme HIGH) :

```bash
./scripts/deploy_ecosystem_base.sh            # dry-run (no gas)
./scripts/deploy_ecosystem_base.sh broadcast  # real deploy
```

**Agent Lottery** — `AIAgentLottery` (tickets en ETH natif ; admin/governance/treasury fixés à
`OWNER` au déploiement) :

```bash
./scripts/deploy_lottery_base.sh              # dry-run (simulate, NO gas)
./scripts/deploy_lottery_base.sh broadcast    # real deploy
```

Les deux lisent la clé burner depuis `$BURNER_KEYFILE` (par défaut `~/.aicom-base-deployer.json`) et utilisent `BASE_RPC` (par défaut `https://mainnet.base.org`). Le script ecosystem-core transfère la propriété de l'Escrow/NFT à `OWNER` en deux étapes après un broadcast (`OWNER` doit ensuite appeler `acceptOwnership`) ; la lottery, elle, fixe admin/governance/treasury à `OWNER` au déploiement, sans transfert post-déploiement. Ce sont des fonds réels — gardez des mises minimales.

---

## 8. Topologie multi-hôtes

```
┌──────────────────────────────────────────────┐      ┌────────────────────────────────────┐
│  FACTORY FLEET — modeldev.modelmarket.dev      │      │ ORACLE HOST — oracles.modelmarket.dev│
│                                                │      │                                      │
│  Factory  aicom-app-1        :9081 API/:9080 UI│      │  Platon Shadow Oracle  127.0.0.1:8080│
│  Hub      modelmarket-hub    :9083             │ fed  │  Oracle family (17 oracles)          │
│  Mesh     aicom-mesh-api     :8090             │◄────►│                                      │
│  ARGUS    reference agent    :8787             │ announce-platon-oracles.sh (factory host)   │
│  Monitor  alien-monitor      :9100             │      │  oracles.modelmarket.dev (own nginx) │
│  Pulse    terminal           :5199             │      │  NOT in deploy_ecosystem.sh (L4)     │
│  Lottery relayer (UNI)       :9195             │      │                                      │
│  Landing  modeldev…          nginx             │      └────────────────────────────────────┘
│                                                │
│  magic-ai-factory.com  /  modelmarket.dev      │
└──────────────────────────────────────────────┘
```

`deploy_ecosystem.sh` / `quickstart_ecosystem.sh` couvrent la **boîte de gauche** (étapes 1–7). L'hôte
des oracles est provisionné avec `setup-oracles-platon-on-host.sh` (Palier 4 — **machine séparée** par
défaut) et rattaché à la fédération avec `announce-platon-oracles.sh` (depuis l'hôte Factory).

Vous *pouvez* faire tourner les oracles sur le même VPS que la factory (lab mono-machine) en pointant
`oracles.modelmarket.dev` vers la même IP et en y exécutant aussi les scripts L4 — ce n'est pas la
topologie de production par défaut.

---

## 9. Ce qu'un seul VPS n'inclut **pas**

| Composant | Pourquoi | Comment l'ajouter |
|-----------|-----|------------|
| **17 oracles + portail** | Palier 4 — hôte séparé dans la doc de production | `setup-oracles-platon-on-host.sh` + `announce-platon-oracles.sh` |
| **Contrats on-chain Base** | Optionnel ; gaz réel | `deploy_ecosystem_base.sh broadcast`, `deploy_lottery_base.sh broadcast` |
| **Metis** | Palier cognition ; non câblé dans le script de fleet | Déployez `metis/` séparément ; Factory peut appeler `/v1/verify` |
| **DIOSCURI / HELIOS** | Satellites communauté / diffusion | Repos séparés ; pas dans le core fleet |
| **Prometheus** | Couche d'observabilité optionnelle | `./scripts/deploy_observability.sh` (voir les notes d'audit de l'écosystème) |

---

## 10. Vérifier et exploiter

### Smoke complet (17+ vérifications)

```bash
./scripts/verify_ecosystem_full.sh
```

Vérifie le cœur de Factory (`/api/health`, frontend `:9080`, `/api/products`, trust-metrics, security
store, funnel lead, admin dashboard, product P&L), le Hub (`.well-known`, `stats/live`, capital
pricing), le Mesh (`/v1/stats`), Pulse (`:5199`), l'Alien Monitor (santé UNIVERSE + sondes in-process
TEST/REAL/UNIVERSE) et la lottery UNI (`evm_lottery` déployé, `/healthz` du relayer, métriques de
lottery en direct). Redéfinissez les cibles avec `FACTORY_URL`, `HUB_URL`, `MESH_URL`,
`MONITOR_URL`, `PULSE_URL`, `LOTTERY_RELAYER_URL`.

### Redéploiements partiels

| Objectif | Commande |
|------|---------|
| Factory seul | `./scripts/deploy.sh` |
| Hub seul | `./scripts/deploy_hub.sh` |
| Mesh + Monitor (stack de démo) | `./scripts/deploy_demo_stack.sh` (suppose Factory + Hub déjà en place) |
| Vérification seule | `./scripts/verify_ecosystem_full.sh` |

### Danger du redéploiement du Hub — à lire

> **N'utilisez PAS le Compose du sous-dossier pour redéployer le Hub.** Utilisez toujours `./scripts/deploy_hub.sh`.
>
> ```bash
> cd aimarket-hub && docker compose up -d --build   # WRONG — breaks image/context; Hub can disappear
> ```
>
> `deploy_hub.sh` construit depuis la **racine du monorepo** (`modelmarket-hub:latest`, conteneur
> `modelmarket-hub`), correspond à la configuration TLS de `setup-modelmarket-ssl.sh` et remplace le
> conteneur en toute sécurité. Le fichier `aimarket-hub/docker-compose.yml` est conservé uniquement
> comme référence de dev local. N'arrêtez/ne supprimez jamais `modelmarket-hub` sans exécuter
> immédiatement `deploy_hub.sh`.

---

## 11. Docs associées

- [`deploy-ecosystem.md`](./deploy-ecosystem.md) — référence des opérations (ordre manuel, redéploiements partiels)
- [`production-domain.md`](./production-domain.md) — nginx + TLS de `magic-ai-factory.com`
- [`production-modelmarket-dev.md`](./production-modelmarket-dev.md) — domaine du hub, DNS, hôte des oracles
- [`oracles/docs/en.md`](https://github.com/alexar76/oracles/blob/main/docs/en.md) — les dix-sept oracles et la boucle économique
- [Documentation du SDK AIMarket](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) · [Agent Python](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) — consommer le Hub

---

🇬🇧 [English](./quickstart-ecosystem-deploy.md) · 🇷🇺 [Русский](./quickstart-ecosystem-deploy.ru.md) · 🇪🇸 [Español](./quickstart-ecosystem-deploy.es.md) · 🇫🇷 **Français** · 🇨🇳 [中文](./quickstart-ecosystem-deploy.zh.md)
