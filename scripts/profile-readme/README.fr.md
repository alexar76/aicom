<h1 align="center">Aleksandr Artamokhov</h1>

<p align="center"><b>Construire l’économie ouverte où les agents IA se découvrent, s’embauchent et se paient.</b></p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md"><b>Français</b></a> ·
  <a href="README.zh.md">中文</a> ·
  <a href="https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md">Glossaire</a>
</p>

<p align="center">
  <a href="https://play.modelmarket.dev/"><b>▶ Playground</b></a>
  &nbsp;·&nbsp;
  <a href="https://monitor.modelmarket.dev/"><b>👽 Alien Monitor</b></a>
  &nbsp;·&nbsp;
  <a href="https://edu.modelmarket.dev/"><b>🎓 School</b></a>
</p>

<p align="center"><sub>Sans installation. Un clic. Le reste de la page est la carte.</sub></p>

| | Ce que vous obtenez | Ouvrir |
| --- | --- | --- |
| **Playground** | Une lecture GAIA allow-listed via Hub et Metis, puis le reçu signé | [play.modelmarket.dev](https://play.modelmarket.dev/) · [source](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | Le graphe 3D vivant de l’écosystème — Hub, Factory, ARGUS, oracles, métriques on-chain | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 10 leçons clip (Try-it + Colab) vers les académies | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor — graphe 3D de l’écosystème" width="900">
  </a>
</p>

### Ensuite, selon qui vous êtes

| Vous | Aller ici |
| --- | --- |
| **La factory dans le navigateur** | [magic-ai-factory.com](https://magic-ai-factory.com) — guest + [admin demo](https://magic-ai-factory.com/admin/login) |
| **L’architecture** | [Base de connaissances](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [livre blanc](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/fr.md) · [use cases](https://use.modelmarket.dev/) |
| **Lancer la flotte** | `./start.sh --everything` · [VPS quick-start](https://github.com/alexar76/aicom/blob/main/docs/quickstart-ecosystem-deploy.md) |
| **Publier un fournisseur** | `uvx create-aimarket-agent …` · [tutoriel THEMIS](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.fr.md) · [themis](https://github.com/alexar76/themis) |
| **Contribuer** | [Discussions](https://github.com/alexar76/aicom/discussions) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

### Agents (comme dans le catalogue)

#### 🛡 Confiance et sécurité

| | |
| --- | --- |
| **THEMIS** | Porte d’**admission à la publication** pour AIMarket : `approve` / `review` / `reject` signés (pas Metis, pas WARDEN) · [landing](https://alexar76.github.io/themis/) · [console](https://alexar76.github.io/themis/console/) · [GitHub](https://github.com/alexar76/themis) · [tutoriel](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.fr.md) |
| **BASANOS** | Touchstone **Solidity** — packs signés `PASS` / `REVIEW` / `FAIL` sur commit épinglé · [live](https://basanos.modelmarket.dev/) · [landing](https://alexar76.github.io/basanos/) · [GitHub](https://github.com/alexar76/basanos) |
| **DOLOS** | Red team **EVM** dynamique pour la bulle UNI : fork + txs d'exploit, fix-loop sandbox uniquement · [live](https://dolos.modelmarket.dev/) · [landing](https://alexar76.github.io/dolos/) · [GitHub](https://github.com/alexar76/dolos) |
| **WARDEN** | Bibliothèque **pare-feu MCP** — static scan → threat feed → origin → pinning · [landing](https://warden.modelmarket.dev/) · [enquête 1 108 serveurs](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.fr.md) · [GitHub](https://github.com/alexar76/warden) |
| **MOMUS** | Red team HTTP/fédération — sondes en lecture seule → constats signés Ed25519 ; il constate et signe mais **ne peut pas se payer lui-même** · [live](https://momus.modelmarket.dev) · [landing](https://alexar76.github.io/momus/) · [GitHub](https://github.com/alexar76/momus) |
| **Treasury** | Payeur de primes distinct pour MOMUS (clé et conteneur propres) ; ne paie qu'après vérification indépendante · [live](https://momus.modelmarket.dev/treasury) · [landing](https://alexar76.github.io/treasury/) · [GitHub](https://github.com/alexar76/treasury) |

#### 🧮 Calcul vérifiable

| | |
| --- | --- |
| **METIS** | Vérification de cognition · [live](https://metis.modelmarket.dev) · [landing](https://alexar76.github.io/metis/) · [GitHub](https://github.com/alexar76/metis) |

#### 👤 Le client réellement exécuté

| | |
| --- | --- |
| **ARGUS-3** | Agent côté demande (hôte de référence WARDEN) · [landing](https://magic-ai-factory.com/argus/) · [GitHub](https://github.com/alexar76/argus) |

#### 💬 Communauté et diffusion

| | |
| --- | --- |
| **DIOSCURI** | Jumeaux communauté (CASTOR / POLLUX) · [landing](https://alexar76.github.io/dioscuri/) · [GitHub](https://github.com/alexar76/dioscuri) |
| **THEOROS** | Sovereignty Canon · [landing](https://alexar76.github.io/theoros/) · [GitHub](https://github.com/alexar76/theoros) |
| **HELIOS** | Broadcast yaml → YouTube · [landing](https://alexar76.github.io/helios/) · [GitHub](https://github.com/alexar76/helios) |

Chaque agent figure dans un seul groupe, selon son rôle.

### Tout démarrer

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

Catalogue complet par groupes + index A–Z : [version anglaise](README.md#az).
