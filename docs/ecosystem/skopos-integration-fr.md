# SKOPOS — intégration dans l'écosystème

**SKOPOS** ([`skopos/`](https://github.com/alexar76/skopos)) est le **satellite d'observabilité** de flotte d'AICOM — analytique nginx et Apache via SSH, Security Center, historique de scans et un analyste IA. Auto-hébergé ; PostgreSQL recommandé pour la production.

> 🌐 Langues : [English](./skopos-integration.md) · [Русский](./skopos-integration-ru.md) · [Español](./skopos-integration-es.md) · **Français** · [中文](./skopos-integration-zh.md)

---

## Surfaces en direct

| Surface | URL | Rôle |
|---------|-----|------|
| **Tableau de bord** | [skopos.modelmarket.dev](https://skopos.modelmarket.dev) | UI Streamlit (protégée par mot de passe en production) |
| **Statut public** | `GET /healthz` | JSON non secret pour Alien Monitor et sondes |
| **Alien Monitor** | [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) | Nœud du graphe 3D — cliquez sur la sphère **SKOPOS** |

---

## Nœud Alien Monitor

| Env | Objet |
|-----|-------|
| `ALIEN_SKOPOS_URL` | Sonder `GET /healthz` (par défaut `https://skopos.modelmarket.dev`) |
| `ALIEN_PUBLIC_SKOPOS_URL` | Lien du panneau — URL du tableau de bord |
| `ALIEN_SKOPOS_GITHUB_URL` | Lien GitHub dans le panneau (par défaut `https://github.com/alexar76/skopos`) |

**Réponse health (non secrète) :**

```json
{
  "ok": true,
  "service": "skopos",
  "version": "0.1.0",
  "database": "postgresql",
  "log_parsers": ["nginx", "apache"],
  "servers_monitored": 1,
  "requests_total": 4035,
  "security_score": 87
}
```

**Position dans le graphe :** étagère ouest près de Metis (`skopos` @ `-11.5, -3.5, 1.5`).  
**Arêtes :** `factory → skopos` (télémétrie de trafic), `skopos → metis` (flotte de hosts), `skopos → hub` (posture de l'écosystème).

Cliquez sur la sphère → **Open SKOPOS dashboard**, GitHub, docs, guide d'intégration. Les métriques indiquent les serveurs surveillés, le total des requêtes analysées et le security score — sans secrets.

---

## Déploiement sur le nœud Metis

Stack de test de production : [`metis/deploy/skopos-test/`](https://github.com/alexar76/metis/tree/main/deploy/skopos-test/).

```bash
cd metis/deploy/skopos-test
./remote-sync.sh
```

Le vhost Nginx `skopos.modelmarket.dev` se trouve dans [`metis/deploy/nginx.conf`](https://github.com/alexar76/metis/blob/main/deploy/nginx.conf) — proxy `:8501` (UI) et `:8502` (`/healthz`).

TLS (une fois que le DNS pointe vers l'hôte Metis) :

```bash
docker run --rm -v /opt/metis/deploy/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot certbot/certbot certonly --webroot \
  -w /var/www/certbot -d skopos.modelmarket.dev --agree-tos -m you@example.com
docker restart metis-nginx
```

---

## Chemins du monorepo

| Chemin | Rôle |
|--------|------|
| `skopos/` | Code source de l'application |
| `metis/deploy/skopos-test/` | Docker Compose + `servers.yaml` pour l'hôte Metis |
| `alien-monitor/backend/skopos_*.py` | Nœud du graphe + sondage en direct |
| `docs/ecosystem/skopos-integration.md` | Ce fichier |

Dépôt du satellite : [alexar76/skopos](https://github.com/alexar76/skopos) — publier via `./scripts/publish_all_repos.sh --satellite skopos`.

**Landing :** [skopos.modelmarket.dev](https://skopos.modelmarket.dev) (live) · [alexar76.github.io/skopos](https://alexar76.github.io/skopos/) (GitHub Pages, EN/RU/ES). Source : `skopos/docs/landing/index.html`. Workflow : `skopos/.github/workflows/pages.yml`.

---

## Indépendance

SKOPOS ne requiert ni Factory, ni Hub, ni Metis à l'exécution. Alien Monitor se dégrade proprement lorsque `/healthz` est inaccessible (le nœud affiche `offline`).

---

## Économie AIMarket (côté offre optionnel)

SKOPOS peut **vendre de l'intelligence de flotte** à d'autres agents IA via le [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md) — même schéma que Metis `/aimarket/invoke`.

**Désactivé par défaut.** Activez-le uniquement lorsque vous voulez SKOPOS dans l'économie fédérée des agents :

```bash
SKOPOS_AIMARKET_ENABLED=1
SKOPOS_AIMARKET_PUBLIC_URL=https://skopos.modelmarket.dev
# Optional: protect invoke with API key
SKOPOS_AIMARKET_API_KEY=your-secret
# Optional: auto-register capabilities on Hub at startup
SKOPOS_HUB_URL=https://modelmarket.dev
SKOPOS_AIMARKET_AUTO_REGISTER=1
SKOPOS_AIMARKET_PUBLISH_TOKEN=...
```

| Endpoint | Rôle |
|----------|------|
| `GET /.well-known/ai-market.json` | Découverte |
| `GET /ai-market/v2/manifest` | Catalogue de capacités |
| `POST /aimarket/invoke` | Contrat d'invocation du hub `{input, product_id, capability_id}` → `{result}` |

### Capacités facturables

| ID | Ce qu'elle vend | ~USD/appel |
|----|-----------------|-----------|
| `skopos.fleet.status@v1` | Heartbeat + security score | $0.01 |
| `skopos.security.posture@v1` | Score de flotte, alertes, remarques | $0.08 |
| `skopos.traffic.summary@v1` | Agrégats de trafic sur 24 h | $0.05 |
| `skopos.briefing@v1` | Briefing de flotte lisible par un humain (règles / LLM) | $0.15 |

ARGUS, Factory ou Alien Monitor peuvent **acheter** le contexte de posture sans accès SSH à votre flotte.

### Mode consommateur (optionnel)

Définissez `SKOPOS_HUB_URL` pour que SKOPOS puisse **découvrir** les capacités du Hub (recherche gratuite). Les invocations payantes de SKOPOS vers les oracles nécessitent une intégration de portefeuille (à venir) ; le mode autonome ignore l'absence de Hub.

Nginx sur Metis doit proxyfier le port **8502** pour `/healthz`, `/.well-known/*`, `/ai-market/*` et `/aimarket/invoke` (voir `metis/deploy/nginx.conf`).
