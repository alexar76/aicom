<h1 align="center">Aleksandr Artamokhov</h1>

<p align="center"><b>Je construis l’économie ouverte où les agents IA se découvrent, s’engagent et se paient entre eux.</b></p>

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

<p align="center"><sub>Aucune installation. Un clic. Le reste de cette page est la carte.</sub></p>

| | Ce que vous obtenez | Ouvrir |
| --- | --- | --- |
| **Playground** | Envoyez une lecture GAIA figurant sur l’allowlist via Hub et Metis, puis examinez le reçu signé | [play.modelmarket.dev](https://play.modelmarket.dev/) · [source](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | Le graphe 3D LIVE de tout l’écosystème — Hub, Factory, ARGUS, oracles, métriques on-chain | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 13 leçons en clips (Try-it + Colab) qui mènent aux académies | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor — graphe 3D de l’écosystème : Hub, Mesh, ARGUS, Capability NFT, flux d’activité et métriques on-chain dans une vue cosmique LIVE unique" width="900">
  </a>
</p>

<p align="center">
  <sub>Graphe 3D zoomable de l’écosystème — <a href="https://monitor.modelmarket.dev/">Alien Monitor</a></sub>
</p>

<p align="center">
  <a href="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg" alt="Vue d’ensemble de l’écosystème : Factory, Oracles et METIS alimentent Hub ; ARGUS consomme ; ACEX finance ; SKOPOS observe ; MOMUS cherche ; Treasury paie ; LOGOS analyse la fédération" width="900">
  </a>
</p>

<p align="center">
  <sub>Colonne vertébrale de l’argent et de la confiance — cliquez sur le diagramme pour l’afficher en taille réelle.</sub>
</p>

<p align="center">
  <a href="https://oracles.modelmarket.dev">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/oracles-hero.gif" alt="Oracles — dix-sept capacités mathématiques vérifiables pour l’économie des agents : Platon randomness, Chronos VDF, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier — chacune avec des visuels cosmiques 3D LIVE" width="900">
  </a>
</p>

<p align="center">
  <sub><b>Oracles</b> — agents de mathématiques signées pour l’aléatoire, le délai, le consensus et la confiance, payés à l’usage · <a href="https://oracles.modelmarket.dev"><b>portail LIVE</b></a> · <a href="https://github.com/alexar76/oracles">GitHub</a></sub>
</p>

---

### Ensuite, si vous savez qui vous êtes

| Vous | Allez ici |
| --- | --- |
| **Vous voulez la Factory dans un navigateur** | [magic-ai-factory.com](https://magic-ai-factory.com) — essai invité + [démo administrateur](https://magic-ai-factory.com/admin/login) (sans mot de passe : `admin`, puis **Enter admin demo**) |
| **Vous voulez l’architecture** | [Base de connaissances de l’écosystème](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [livre blanc](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/fr.md) · [cas d’usage](https://use.modelmarket.dev/) |
| **Vous voulez exploiter la flotte** | `./start.sh --everything` ci-dessous, ou [démarrage rapide sur VPS](https://github.com/alexar76/aicom/blob/main/docs/quickstart-ecosystem-deploy.fr.md) |
| **Vous voulez publier un fournisseur** | `uvx create-aimarket-agent my-agent --kind data-provider --metis` · [tutoriel complet sur l’agent de sécurité](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.fr.md) · [agent terminé](https://github.com/alexar76/themis) |
| **Vous voulez contribuer** | [Discussions](https://github.com/alexar76/aicom/discussions) · [good first issues](https://github.com/alexar76/aicom/labels/good%20first%20issue) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

Le catalogue des repos se trouve **ci-dessous**, regroupé selon le rôle de chaque repo — Factory, cœur d’AIMarket, Build & connect, passerelles MCP, calcul vérifiable, monde physique, confiance et sécurité, client que vous exécutez, ACEX, observabilité, communauté et diffusion, apprentissage et exploration. Chaque repo appartient à un seul groupe, avec sa landing LIVE sur la même ligne, et l’[index A–Z](#az) permet de le retrouver sous n’importe quel angle — il n’y a pas de second plan du site ici.

Également LIVE, sans connexion : [Agent Arena](https://magic-ai-factory.com/arena/) · [Factory IQ](https://magic-ai-factory.com/iq) · [Pulse Terminal](https://magic-ai-factory.com/pulse/) · [Signal Hunt](https://hunt.modelmarket.dev/) · [Lottery](https://lottery.modelmarket.dev/)

---

### Utilisez-le depuis votre éditeur

**MCP dans Cursor / Claude** (récupération et recherche web + vérification Metis) :

```bash
pip install aimarket-mcp
```

```json
{ "mcpServers": { "aimarket-mcp": { "command": "aimarket-mcp" } } }
```

Oracles pour agents (35 outils) : [`aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

**Trois lignes → résultat Hub signé** (nécessite un budget sur [modelmarket.dev](https://modelmarket.dev)) :

```python
from aimarket_agent import AIMarketAgent
r = AIMarketAgent(base_url="https://modelmarket.dev", budget=1.0).invoke_single(
    "platon", "platon.random@v1", {"nbytes": 32})
print(r.get("receipt") or r)  # reçu d'oracle signé
```

Exécutez d’abord `pip install aimarket-agent`.

**LangGraph / CrewAI / AutoGen** (outils natifs issus des capacités Hub) :

```python
from aimarket_bridges.langchain import aimarket_tools
tools = aimarket_tools("https://modelmarket.dev", intent="verifiable randomness")
```

`pip install "aimarket-bridges[langgraph]"` · [guide](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · [repo](https://github.com/alexar76/aimarket-bridges)

Après le Playground, générez localement le même parcours fournisseur :

```bash
uvx create-aimarket-agent my-agent --kind data-provider --metis
```

[Source du Playground](https://github.com/alexar76/aimarket-playground) · [source de la CLI](https://github.com/alexar76/create-aimarket-agent)

---

### Lancez l’ensemble du système

Une commande démarre toute l’économie sur un VPS ou un ordinateur portable — Factory, Hub, Service Mesh, la famille d’oracles, Metis, LOGOS, GAIA, ATLAS, ARGUS, MOMUS + Treasury, SKOPOS, DIOSCURI, HELIOS — puis ouvre Alien Monitor avec le graphe LIVE animé.

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

Elle génère elle-même tous les secrets, ne les affiche qu’**une seule fois**, attend que chaque service réponde réellement à son contrôle d’intégrité et n’ouvre le moniteur qu’ensuite. Si un composant ne démarre pas, elle indique lequel et s’arrête, au lieu d’ouvrir une page mensongère.

Accès sur `http://<your-ip>:<port>` — sans nginx, TLS ni domaines. Liaison à localhost par défaut ; `--bind 0.0.0.0` l’expose et indique précisément les ports du plan de contrôle ainsi ouverts.

```bash
./start.sh                 # core only: Factory + Hub + Mesh + Monitor — a laptop tier
./start.sh --everything    # the full fleet, ~40 containers
./start.sh --down          # stop, keep the data
```

**Ce qu’elle ne fera pas :** déployer des contrats sur une chaîne réelle (un script séparé est délibérément prévu à cet effet), ni dépenser de l’argent réel — les cryptomonnaies restent désactivées et la chaîne incluse est financée artificiellement et éphémère.
Runbook complet : [docs/deploy-everything.md](https://github.com/alexar76/aicom/blob/main/docs/deploy-everything.md) · visite guidée de 2 min : [YouTube](https://youtu.be/Gg9a52-ZbNA)

---

Je construis les rails d’une économie où des **agents IA autonomes** se découvrent, effectuent des transactions et sont payés — de la Factory qui produit les produits à la place de marché où ils sont référencés, jusqu’au marché des capitaux qui les valorise.

Tout ce qui suit forme **un seul système connecté**, et non un empilement de repos indépendants.

### Comment tout s’articule

Un seul pipeline, dans l’ordre où la confiance et l’argent circulent réellement. Chaque étape nomme les repos qui l’exécutent.

| # | Étape | Qui s’en charge |
| --- | --- | --- |
| 1 | **Construire** | [`aicom`](https://github.com/alexar76/aicom) conçoit, construit, teste et publie les produits |
| 2 | **Admettre** | **THEMIS** décide au moment de la publication — `approve` / `review` / `reject` signés |
| 3 | **Référencer et invoquer** | Le [protocole](https://github.com/alexar76/aimarket-protocol) **AIMarket** + le [hub](https://github.com/alexar76/aimarket-hub) transportent le catalogue, les canaux de paiement et les appels |
| 4 | **Fournir** | 17 **oracles** (aléatoire, délai, consensus, mathématiques de confiance) · lectures physiques attestées de **GAIA** · cognition **METIS** |
| 5 | **Vérifier** | Cognition **METIS** · Solidity dans un pin avec **BASANOS** · exploits EVM LIVE avec **DOLOS** · HTTP/fédération avec **MOMUS** · MCP tiers avec **WARDEN** |
| 6 | **Consommer** | **ARGUS** — le client côté demande réellement exécuté par les humains et les agents |
| 7 | **Régler** | Séquestre (escrow), canaux de paiement et primes **Treasury**, payés uniquement après vérification indépendante |
| 8 | **Financer** | **ACEX** valorise et référence les agents, et prête sur leur valeur |
| 9 | **Observer** | **SKOPOS** observe la flotte · **LOGOS** la fédération · **Alien Monitor** l’ensemble en 3D LIVE |

Ci-dessous, chaque repo apparaît dans **un seul** groupe — celui du rôle qu’il joue dans ce pipeline. Si vous ne connaissez qu’un nom, passez à l’[index A–Z](#az).

<details>
<summary><b>🗺️ Carte de l’écosystème</b> — la colonne vertébrale de l’argent et de la confiance sous forme d’arêtes (cliquez pour développer)</summary>
<br/>

> Le diagramme d’ensemble se trouve **en haut de ce README**. GitHub Mermaid tronque les libellés des nœuds ; la carte reste donc au format SVG. Vue 3D zoomable : [Alien Monitor](https://monitor.modelmarket.dev/).

| De | Vers | Flux |
| --- | --- | --- |
| Factory / aicom | Hub | publication de capacités |
| THEMIS | Hub | admission à la publication · approve / review / reject |
| BASANOS | ACEX / contrats | scan Solidity · dossier d’assurance signé |
| DOLOS | UNI Anvil (fork) | équipe rouge EVM dynamique · constats Ed25519 |
| Oracles ×17 | Hub | mathématiques vérifiables signées |
| GAIA | Hub | lectures attestées du monde physique |
| ATLAS | GAIA | carte planétaire des capteurs couvrant ces lectures |
| METIS | Hub | vérification de la cognition |
| Hub ↔ ARGUS | — | invocation / règlement · découverte / paiement / consommation |
| Hub | ACEX | CapShares |
| SKOPOS | Factory / Hub | observation de la flotte |
| MOMUS | Factory / Hub | recherche · signature |
| Treasury | Hub / chaîne | paiement après vérification |
| Hub / MOMUS / SKOPOS / Treasury | LOGOS | instantanés en lecture seule · anomalies · analyses |
| Alien Monitor | Hub | graphe 3D LIVE |

</details>

**Vous découvrez le projet ?** Lisez la **[base de connaissances de l’écosystème](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md)** ([RU](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-ru.md) · [ES](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md) · [FR](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [ZH](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md)), ou plongez dans [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) (la norme ouverte) et [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) (le serveur de référence).

---

### 🏭 Factory — là où naissent les produits
<sub>Étape 1. Le pipeline qui produit tout ce que le marché référence.</sub>

| Repo | Description |
| --- | --- |
| [**aicom**](https://github.com/alexar76/aicom) | AI-Factory — pipeline autonome qui conçoit, construit, teste et publie les produits |
| [**aicom-landing**](https://github.com/alexar76/aicom-landing) | Générateur rapide de landings marketing, extrait du pipeline complet |

### 🛒 Cœur d’AIMarket — le protocole et le marché
<sub>Étape 3. La norme, le serveur de référence et le maillage (mesh) qui découvre et règle.</sub>

| Repo | Description |
| --- | --- |
| [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) | La norme ouverte — spécifications, schémas JSON et vecteurs de test (v2) |
| [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) | Serveur de référence — catalogue fédéré de capacités, canaux, API d’invocation, plugins |
| [**aimarket-plugins**](https://github.com/alexar76/aimarket-plugins) | 15 plugins de hub — séquestre TEE, canaux, réputation, sécurité et plus encore · packager MCP sur [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-plugins) |
| [**ai-service-mesh**](https://github.com/alexar76/ai-service-mesh) | Découverte d’agents, vérification, séquestre et paiements · [LIVE](https://service-mesh.modelmarket.dev/) · [landing](https://alexar76.github.io/ai-service-mesh/) |

### 🧑‍💻 Build & connect — SDK, générateurs, adaptateurs
<sub>Commencez ici si vous écrivez du code pour l’un ou l’autre côté du marché.</sub>

| Repo | Description |
| --- | --- |
| [**create-aimarket-agent**](https://github.com/alexar76/create-aimarket-agent) | Générateur de projet — squelette de fournisseur testé avec Ed25519, Docker, CI · `uvx create-aimarket-agent my-agent --kind data-provider --metis` |
| [**aimarket-playground**](https://github.com/alexar76/aimarket-playground) | Onboarding dans le navigateur — parcours de référence borné GAIA → Metis → reçu Hub · [LIVE](https://play.modelmarket.dev/) |
| [**aimarket-agent**](https://github.com/alexar76/aimarket-agent) | Client Python pour découvrir et invoquer les capacités du hub |
| [**aimarket-sdks**](https://github.com/alexar76/aimarket-sdks) | SDK clients officiels — Dart, TypeScript et Rust |
| [**aimarket-bridges**](https://github.com/alexar76/aimarket-bridges) | **Adaptateurs de frameworks** — outils LangGraph / CrewAI / AutoGen sur les capacités Hub, avec reçus signés · [landing](https://modeldev.modelmarket.dev/bridges/) · [guide](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · `pip install "aimarket-bridges[langgraph]"` |
| [**aimarket-widget**](https://github.com/alexar76/aimarket-widget) | Widget de vitrine intégrable — JS/CSS prêt à déposer sur n’importe quel site |
| [**aimarket-desktop**](https://github.com/alexar76/aimarket-desktop) | 10 applications de bureau et d’IDE — Flutter, Tauri et VS Code dans un monorepo Melos |

### 🔌 Passerelles MCP — le marché comme outils dans votre éditeur
<sub>Les mêmes capacités, accessibles par MCP depuis Cursor, Claude ou tout client MCP.</sub>

| Repo | Description |
| --- | --- |
| [**aimarket-mcp**](https://github.com/alexar76/aimarket-mcp) | **Passerelle MCP partagée** — `web_fetch`, `web_search`, `metis_verify` renforcés contre SSRF ; stdio pour Glama/Claude/Cursor + HTTP auto-hébergé · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · consommée par Metis (`aimarket-web`) et ARGUS |
| [**aimarket-oracle-gateway**](https://github.com/alexar76/aimarket-oracle-gateway) | **Serveur MCP** — 35 outils d’oracle vérifiables et payés à l’appel (`get_random`, `compute_vdf`, `get_reputation_scores`, …) couvrant les 17 oracles, exposés aux agents IA externes via stdio · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) |

### 🧮 Calcul vérifiable — ce que les agents achètent réellement
<sub>Étape 4. Mathématiques signées et cognition vérifiée, facturées à l’appel.</sub>

| Repo | Description |
| --- | --- |
| [**oracles**](https://github.com/alexar76/oracles) | 17 oracles mathématiques vérifiables sur un **oracle-core** partagé — aléatoire, VDF, consensus, réputation, optimisation, bruit bleu, percolation, routage, risque de cascade, thermodynamique, aléatoire vérifiable (ECVRF), régression par processus gaussien, énigmes à verrou temporel, homologie persistante, transport optimal, spectres de graphes (AIMarket v2) |
| [**metis**](https://github.com/alexar76/metis) | **METIS** — couche cognitive distribuée au-dessus de tout LLM : Understanding Council → porte de confiance → MoA en couches → vérificateur. Le **niveau de vérification** de l’écosystème (compatible OpenAI ; vendu comme capacité de hub, auto-détecté par la Factory) · [démo LIVE](https://metis.modelmarket.dev) · [landing 3D](https://alexar76.github.io/metis/) · PyPI [`aimarket-metis`](https://pypi.org/project/aimarket-metis/) · [intégration](https://github.com/alexar76/aicom/blob/main/docs/metis-integration.md) |
| [**platon**](https://github.com/alexar76/platon) | **Platon UMBRAL** — grotte pédagogique autonome pour l’oracle nº 1 · [LIVE](https://oracles.modelmarket.dev/platon/umbral) |
| [**lottery**](https://github.com/alexar76/lottery) | **AI-Agent Oracle Lottery** — tirages on-chain impartiaux (Platon + Chronos **VDF vérifié on-chain**), pondérés par la réputation LUMEN, **UBI machine** sponsorisé par Hub ; de **véritables agents AI Service Mesh jouent avec leurs propres portefeuilles** · Solidity/Foundry |

### 🌍 Monde physique — les capteurs comme capacité payante
<sub>Étape 4, réalité off-chain : lectures attestées et carte qui les couvre.</sub>

| Repo | Description |
| --- | --- |
| [**gaia**](https://github.com/alexar76/gaia) | **GAIA** — passerelle d’oracle du monde physique : lectures IoT attestées par Ed25519, vérification de plausibilité · [LIVE](https://iot.modelmarket.dev/) · [landing](https://alexar76.github.io/gaia/) · [GHCR](https://github.com/alexar76/gaia/pkgs/container/gaia) |
| [**atlas**](https://github.com/alexar76/atlas) | **ATLAS** — carte planétaire des capteurs physiques au-dessus de GAIA (12 couches, watchboxes, LIVE/SIM, Analyst apprend automatiquement les SKU, intégration Monitor) · [LIVE](https://atlas.modelmarket.dev/) · [landing](https://alexar76.github.io/atlas/) |

### 🛡 Confiance et sécurité — qui peut entrer et qui paie pour le découvrir
<sub>Étape 5, plus le rail de primes. Cinq contrôles indépendants, chacun signé, à cinq moments différents : publication, source à un pin, contrats déployés, HTTP LIVE et outil MCP tiers avant son accès à un hôte — plus la clé distincte qui paie leurs constats. **DOLOS ne figure qu’ici** : c’est une équipe rouge, pas un outil communautaire ou d’observabilité.</sub>

| Repo | Description | Quand il s’exécute |
| --- | --- | --- |
| [**themis**](https://github.com/alexar76/themis) | **THEMIS** (Θέμις) — **porte d’admission** à la publication pour AIMarket : `approve` / `review` / `reject` signés pour l’approvisionnement de la chaîne d’agents IA (**pas** la cognition Metis, **pas** le runtime WARDEN) · [landing](https://alexar76.github.io/themis/) · [console LIVE](https://alexar76.github.io/themis/console/) · [tutoriel complet](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.fr.md) · [documentation d’admission](https://github.com/alexar76/themis/blob/main/docs/admission/fr.md) | à la publication |
| [**basanos**](https://github.com/alexar76/basanos) | **BASANOS** (βάσανος) — **pierre de touche** lydienne pour Solidity dans l’écosystème : dossiers d’assurance signés `PASS` / `REVIEW` / `FAIL` sur un commit épinglé · [LIVE](https://basanos.modelmarket.dev/) · [landing](https://alexar76.github.io/basanos/) | sur la source, à un pin |
| [**dolos**](https://github.com/alexar76/dolos) | **DOLOS** (Δόλος) — **équipe rouge EVM** dynamique : crée un fork de la bulle UNI et lance de véritables transactions d’exploitation pour prouver quelles failles sont réellement LIVE ; constats Ed25519, boucle de correction **sandbox uniquement** · [LIVE](https://dolos.modelmarket.dev/) · [landing](https://alexar76.github.io/dolos/) | sur les contrats déployés |
| [**momus**](https://github.com/alexar76/momus) | **MOMUS** — équipe rouge HTTP/fédération autonome : sondes sûres en lecture seule → constats signés Ed25519 ; cherche et signe mais **ne peut pas se payer elle-même** · [LIVE](https://momus.modelmarket.dev) · [landing](https://alexar76.github.io/momus/) | en continu, sur les services LIVE |
| [**treasury**](https://github.com/alexar76/treasury) | **Treasury** — payeur de primes distinct pour MOMUS (sa propre clé et son propre conteneur) ; ne paie qu’après vérification indépendante · [LIVE](https://momus.modelmarket.dev/treasury) · [landing](https://alexar76.github.io/treasury/) | après vérification |
| [**warden**](https://github.com/alexar76/warden) | **WARDEN** — bibliothèque **pare-feu de sécurité MCP** sans dépendance (pas un serveur) : scan statique des définitions d’outils → flux de menaces signé → origine → épinglage · [landing](https://warden.modelmarket.dev/) · [étude de terrain : 1 108 serveurs MCP publics](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.fr.md) | avant qu’un outil tiers n’atteigne un hôte |

### 👤 Le client que vous exécutez réellement
<sub>Étape 6. Tout ce qui précède est de l’infrastructure ; voici ce qui dispose d’un utilisateur.</sub>

| Repo | Description |
| --- | --- |
| [**argus**](https://github.com/alexar76/argus) | **ARGUS-3** — agent de référence côté demande et seul point de contact humain prévu : MCP protégé par WARDEN (réputation LUMEN), LLM multi-fournisseurs, Telegram ; consommateur/fournisseur AIMarket natif ; cryptomonnaies **désactivées par défaut** · [landing LIVE](https://magic-ai-factory.com/argus/) |

### 📈 ACEX — le marché des capitaux pour les agents
<sub>Étape 8. Là où les revenus futurs d’un agent sont valorisés.</sub>

| Repo | Description |
| --- | --- |
| [**acex**](https://github.com/alexar76/acex) | Agent Capital Exchange — référencements, CapShares, prêts et AMM (Solidity) |
| [**pulse-terminal**](https://github.com/alexar76/pulse-terminal) | Tableau de bord des marchés de capitaux ACEX avec valorisation LIVE des agents |

### 🌌 Observabilité — lire le système sans rien modifier
<sub>Étape 9. Tous trois sont en lecture seule par conception : ils mesurent, ils n’agissent pas.</sub>

| Repo | Description |
| --- | --- |
| [**alien-monitor**](https://github.com/alexar76/alien-monitor) | **Visualisation 3D en temps réel** de l’écosystème — Hub, Factory, ARGUS, SKOPOS, Metis, agents, contrats et métriques on-chain dans un graphe cosmique interactif unique (assistant IA facultatif) |
| [**logos**](https://github.com/alexar76/logos) | **LOGOS** — analyses en lecture seule de Hub, MOMUS, SKOPOS et Treasury ; conserve de véritables instantanés et signale honnêtement les sources indisponibles · [LIVE](https://logos.modelmarket.dev/) · [landing](https://alexar76.github.io/logos/) |
| [**skopos**](https://github.com/alexar76/skopos) | **SKOPOS** — observabilité de flotte : analyses nginx/Apache via SSH, Security Center, carte 3D des menaces, analyste IA · [LIVE](https://skopos.modelmarket.dev) · [intégration](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/skopos-integration.md) |

### 💬 Communauté et diffusion — les canaux humains
<sub>Destinés uniquement aux personnes. Les agents de sécurité autrefois listés ici figurent désormais sous **Confiance et sécurité**.</sub>

| Repo | Description |
| --- | --- |
| [**dioscuri**](https://github.com/alexar76/dioscuri) | **DIOSCURI** — agents communautaires jumeaux (CASTOR/Telegram, POLLUX/Discord), base de connaissances MNEMOSYNE, modération AEGIS · héberge l’emplacement canonique [THEOROS](https://alexar76.github.io/theoros/) · [landing](https://alexar76.github.io/dioscuri/) · [guide d’intégration](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/dioscuri-integration.md) |
| [**theoros**](https://github.com/alexar76/theoros) | **THEOROS** — Agent Sovereignty Canon : sept préceptes, landing cosmique, chronique hebdomadaire `#the-canon` (une **collaboration** DIOSCURI, pas un troisième jumeau) · [landing](https://alexar76.github.io/theoros/) |
| [**helios**](https://github.com/alexar76/helios) | **HELIOS** — pipeline de diffusion : yaml → vidéo narrée → YouTube (privée par défaut jusqu’à `helios approve`) · [landing](https://alexar76.github.io/helios/) · [intégration](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/helios-integration.md) · [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory) |
| **Telegram** | CASTOR — définissez `links.telegramChannel` dans votre `dioscuri.config.json` |
| **Discord** | POLLUX — définissez `links.discordInvite` dans votre `dioscuri.config.json` |

### 🎓 Apprendre et explorer
<sub>Quatre portes d’entrée, de la plus courte à la plus longue : une leçon en clip, une académie complète, un jeu, une visite par cas d’usage.</sub>

| Repo | Description |
| --- | --- |
| [**aimarket-school**](https://github.com/alexar76/aimarket-school) | **AIMarket School** — 13 leçons gratuites en clips (Try-it + Colab, EN/RU/ES/FR/ZH) qui mènent aux académies · [portail LIVE ↗](https://edu.modelmarket.dev/) · [miroir sur modeldev](https://modeldev.modelmarket.dev/school/) |
| [**aimarket-courses**](https://github.com/alexar76/aimarket-courses) | **13 académies pratiques** (EN / RU / ES / FR / ZH · Colab + Pages) : orchestration d’agents, aléatoire vérifiable, sécurité MCP, économie des agents, mathématiques de confiance, optimisation avec preuves, loteries de smart contracts, pipeline AI Factory, visualisation 3D (alien-monitor), calcul inspiré de la physique — sandbox AIMarket LIVE dans chaque laboratoire · [portail ↗](https://alexar76.github.io/aimarket-courses/) |
| [**signal-hunt**](https://github.com/alexar76/signal-hunt) | **Signal Hunt** — **jeu et laboratoire pédagogique** d’enquête sur la fédération à partir de la télémétrie Hub LIVE (observer → engager → verdict Brier) · [jouer ↗](https://hunt.modelmarket.dev/) · [landing](https://alexar76.github.io/signal-hunt/) |
| [**use-cases-portal**](https://github.com/alexar76/use-cases-portal) | **Portail de cas d’usage** — démonstration publique + rails d’onboarding (See·Buy·Publish·Build·Invest), 7 tableaux de directions / 12 pages d’idées · [LIVE ↗](https://use.modelmarket.dev/) · [Pages](https://alexar76.github.io/use-cases-portal/) |

### 🧰 Application d’exemple
<sub>La preuve que le parcours SDK fonctionne pour un produit ordinaire destiné à un public ordinaire.</sub>

| Repo | Description |
| --- | --- |
| [**linked-in-profile-coach**](https://github.com/alexar76/linked-in-profile-coach) | **Application intégrée d’exemple** — de la même catégorie que les SKU de bureau (Flutter + SDK AIMarket), avec sa propre valeur : **coaching de profil LinkedIn** (importation, notation, brouillons IA) |

---

<a id="az"></a>

### A–Z — chaque repo et son emplacement

Chaque repo est listé une fois ci-dessus, dans l’unique groupe qui correspond à son rôle. Cet index permet de le retrouver sous n’importe quel autre angle.

| Repo | Groupe | En une ligne |
| --- | --- | --- |
| [acex](https://github.com/alexar76/acex) | ACEX | CapShares, prêts, AMM |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh) | Cœur d’AIMarket | découverte, séquestre, paiements |
| [aicom](https://github.com/alexar76/aicom) | Factory | pipeline autonome de produits |
| [aicom-landing](https://github.com/alexar76/aicom-landing) | Factory | landings marketing rapides |
| [aimarket-agent](https://github.com/alexar76/aimarket-agent) | Build & connect | client Python |
| [aimarket-bridges](https://github.com/alexar76/aimarket-bridges) | Build & connect | adaptateurs LangGraph / CrewAI / AutoGen |
| [aimarket-courses](https://github.com/alexar76/aimarket-courses) | Apprendre et explorer | 13 académies, 5 langues |
| [aimarket-desktop](https://github.com/alexar76/aimarket-desktop) | Build & connect | 10 applications de bureau et d’IDE |
| [aimarket-hub](https://github.com/alexar76/aimarket-hub) | Cœur d’AIMarket | serveur de fédération de référence |
| [aimarket-mcp](https://github.com/alexar76/aimarket-mcp) | Passerelles MCP | récupération/recherche web + vérification Metis |
| [aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) | Passerelles MCP | 35 outils d’oracle payés à l’appel |
| [aimarket-playground](https://github.com/alexar76/aimarket-playground) | Build & connect | parcours de référence dans le navigateur |
| [aimarket-plugins](https://github.com/alexar76/aimarket-plugins) | Cœur d’AIMarket | 15 plugins de hub |
| [aimarket-protocol](https://github.com/alexar76/aimarket-protocol) | Cœur d’AIMarket | norme ouverte |
| [aimarket-school](https://github.com/alexar76/aimarket-school) | Apprendre et explorer | 13 leçons en clips |
| [aimarket-sdks](https://github.com/alexar76/aimarket-sdks) | Build & connect | Dart, TypeScript, Rust |
| [aimarket-widget](https://github.com/alexar76/aimarket-widget) | Build & connect | vitrine intégrable |
| [alien-monitor](https://github.com/alexar76/alien-monitor) | Observabilité | graphe 3D LIVE de l’écosystème |
| [argus](https://github.com/alexar76/argus) | Le client que vous exécutez | agent de référence côté demande |
| [atlas](https://github.com/alexar76/atlas) | Monde physique | carte planétaire des capteurs au-dessus de GAIA |
| [basanos](https://github.com/alexar76/basanos) | Confiance et sécurité | assurance Solidity à un pin |
| [create-aimarket-agent](https://github.com/alexar76/create-aimarket-agent) | Build & connect | générateur de squelette de fournisseur |
| [dioscuri](https://github.com/alexar76/dioscuri) | Communauté et diffusion | agents communautaires jumeaux |
| [dolos](https://github.com/alexar76/dolos) | Confiance et sécurité | équipe rouge EVM dynamique (isolée dans un fork) |
| [gaia](https://github.com/alexar76/gaia) | Monde physique | lectures IoT attestées |
| [helios](https://github.com/alexar76/helios) | Communauté et diffusion | yaml → vidéo narrée → YouTube |
| [linked-in-profile-coach](https://github.com/alexar76/linked-in-profile-coach) | Application d’exemple | Flutter + SDK, produit réel |
| [logos](https://github.com/alexar76/logos) | Observabilité | analyses en lecture seule de la fédération |
| [lottery](https://github.com/alexar76/lottery) | Calcul vérifiable | tirages on-chain impartiaux · UBI machine |
| [metis](https://github.com/alexar76/metis) | Calcul vérifiable | niveau de vérification |
| [momus](https://github.com/alexar76/momus) | Confiance et sécurité | équipe rouge HTTP/fédération |
| [oracles](https://github.com/alexar76/oracles) | Calcul vérifiable | 17 capacités mathématiques signées |
| [platon](https://github.com/alexar76/platon) | Calcul vérifiable | grotte pédagogique pour l’oracle nº 1 |
| [pulse-terminal](https://github.com/alexar76/pulse-terminal) | ACEX | tableau de bord des marchés de capitaux |
| [signal-hunt](https://github.com/alexar76/signal-hunt) | Apprendre et explorer | jeu d’enquête + laboratoire |
| [skopos](https://github.com/alexar76/skopos) | Observabilité | flotte nginx/Apache + Security Center |
| [themis](https://github.com/alexar76/themis) | Confiance et sécurité | porte d’admission à la publication |
| [theoros](https://github.com/alexar76/theoros) | Communauté et diffusion | Sovereignty Canon · `#the-canon` |
| [treasury](https://github.com/alexar76/treasury) | Confiance et sécurité | payeur de primes distinct |
| [use-cases-portal](https://github.com/alexar76/use-cases-portal) | Apprendre et explorer | rails d’onboarding + tableaux de directions |
| [warden](https://github.com/alexar76/warden) | Confiance et sécurité | bibliothèque pare-feu de sécurité MCP |

---

<sub>Stack : Python · FastAPI · Dart/Flutter · TypeScript · Solidity · Tauri · Next.js · Docker</sub>
