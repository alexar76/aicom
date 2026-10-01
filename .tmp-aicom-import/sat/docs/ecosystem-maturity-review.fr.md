# Revue de maturité de l'écosystème — critique externe et plan d'action

**Date :** 2026-07-12  
**Objet :** Validation honnête d'un scorecard tiers et **actions concrètes dans le dépôt** que nous pouvons mener maintenant vs blocages opérateur/fournisseur.

**Voir aussi :** [known-issues.md](known-issues.md) · [pet-project-trust.md](pet-project-trust.md) · [oracles crypto-maturity](https://github.com/alexar76/oracles/blob/main/docs/crypto-maturity.en.md)

---

## La critique est-elle juste ?

| Composant | Score externe | Verdict | En une ligne |
|-----------|---------------|---------|--------------|
| **1. AI-Factory** | 7.8/10 | **Globalement juste** | Un vrai pipeline multi-agent + des gates en ~2 mois, c'est impressionnant ; KI-3/KI-2/KI-4 et les MVP livrés correspondent à la critique. |
| **2. Metis** | 8.0/10 | **Juste** | Conception solide (gate de confiance, chemin de vérification) ; le cluster distribué et la couverture adversariale sont naissants. |
| **3. Oracles ×17** | 6.5–6.7/10 | **Juste** | Largeur > profondeur ; crypto pas durcie ([KI-6](known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)). |
| **4. ARGUS-3** | 7.5/10 | **Juste** | WARDEN est réel et testé contre l'empoisonnement évident ; les attaques sophistiquées (encodage, exfiltration à l'exécution, contournement côté modèle) ne sont pas couvertes. |
| **5. Hub + Protocol** | 7.2/10 | **Juste** | La spec v2 + le hub de référence sont solides ; la fédération/le micro-paiement à grande échelle ne sont pas prouvés ; adoption externe ≈ 0. |
| **6. Alien Monitor** | 8.0/10 | **Juste** | Observabilité soignée ; modèle d'authentification corrigé ; pas une couche de confiance financière. |
| **7. Support (HELIOS, DIOSCURI, desktop, widget)** | 6.8–7.3/10 | **Juste** | Satellites utiles ; secondaires par rapport à Factory/Hub/ARGUS ; DIOSCURI = devrel + démo de sécurité de référence. |

**Global :** La revue est **directionnellement correcte**. Les scores sont subjectifs, mais les *risques nommés* correspondent à ce que nous suivons déjà dans les docs KI-* et pet-project trust. Rien ici n'est du FUD — c'est la même posture pre-mainnet que celle que nous affichons publiquement.

---

## Matrice d'actions

| ID | Composant | Action | Responsable | Statut |
|----|-----------|--------|-------|--------|
| **A-1** | Factory | Documenter les profils de pipeline **minimal vs complet** ; recommander minimal pour les landings MVP | in-repo | [`factory-pipeline-profiles.md`](factory-pipeline-profiles.md) |
| **A-2** | Factory | Étiqueter les sorties d'exemple comme **palier MVP** ; lier le rejeu de build | in-repo | [`sample-output/README.md`](sample-output/README.md) |
| **A-3** | Factory | Suivre explicitement les écarts de production | in-repo | **KI-7** dans known-issues |
| **A-4** | Metis | Documenter les écarts distribué + adversarial | in-repo | [`metis/docs/en/MATURITY.md`](https://github.com/alexar76/metis/blob/main/docs/en/MATURITY.md) |
| **A-5** | Metis | Amorcer des tests de régression du gate adversarial | in-repo | `metis/tests/test_adversarial_gates.py` |
| **A-6** | Metis | Suivre le soak du cluster + le benchmark red-team | in-repo | **KI-8** |
| **A-7** | Oracles | Honnêteté crypto (Chronos, PQC hybride, palier prototype) | in-repo | **KI-6** + docs crypto-maturity ✅ |
| **A-8** | ARGUS | Limites de WARDEN + écart sur les attaques sophistiquées | in-repo | [`argus/docs/security-warden.md`](https://github.com/alexar76/argus/blob/main/docs/security-warden.md) §Limitations |
| **A-9** | ARGUS | Test de fixture adversarial (injection obfusquée) | in-repo | `argus/test/adversarial-warden.test.ts` |
| **A-10** | ARGUS | Suivre le parcours red-team / bug bounty | in-repo | **KI-9** |
| **A-11** | Hub | Honnêteté fédération/adoption + plan pour les cas limites | in-repo | [`aimarket-hub/docs/MATURITY.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/MATURITY.md) + **KI-10** |
| **A-12** | Monitor | Aucun changement — maintenir l'étiquette de palier « observabilité, pas confiance » | — | table pet-project-trust |
| **A-13** | Support | Palier **secondaire / devrel** dans pet-project-trust | in-repo | pet-project-trust.md |
| **A-14** | All | Lier depuis ROADMAP + README | in-repo | ROADMAP.md |

**Opérateur uniquement (impossible à clore par la doc seule) :** audit KI-2, test de charge KI-3, multisig KI-4, audit crypto KI-6, adoption en production sur des hubs tiers.

---

## Détail par composant

### 1. AI-Factory (7.8)

**Critique validée :** Le pipeline est le plus grand sous-système ; les agents conditionnels/le directeur/les gates ajoutent de la surface opérationnelle ; le self-host Docker est un atout ; la checklist de production (charge, multisig, audit) est explicitement ouverte ; les démos publiques penchent vers des vitrines landing/MVP ([`docs/sample-output/`](sample-output/)).

**Nous ne contestons pas le « sur-ingénieré » pour un projet perso** — la stack de fragments par défaut enchaîne PM → architecte → dev → QA → sécurité → déploiement → marketing. C'est adapté aux builds vitrines, lourd pour une simple landing page.

**Actions :** A-1, A-2, A-3, `./scripts/quickstart.sh` pour une démo en une commande.

### 2. Metis (8.0)

**Critique validée :** Le mode distribué existe ([`metis/docs/en/DISTRIBUTED.md`](https://github.com/alexar76/metis/blob/main/docs/en/DISTRIBUTED.md)) mais les clusters multi-régions nécessitent des tests de soak ; le gate de confiance est fail-closed sur les signaux *structurés* mais fait confiance au `confidence` assigné par le council — des hallucinations subtiles avec un self-score élevé peuvent passer ; le métrage économique est indicatif tant que Factory n'impose pas les débits.

**Actions :** A-4, A-5, A-6 ; les benchmarks notent déjà « signal de confiance, pas plafond de précision » ([`metis/docs/benchmarks/`](https://github.com/alexar76/metis/tree/main/docs/benchmarks/)).

### 3. Oracles (6.5–6.7)

**Critique validée :** Déjà traité dans [crypto-maturity.en.md](https://github.com/alexar76/oracles/blob/main/docs/crypto-maturity.en.md). L'aléa de Platon + la réputation de Lumen nécessitent la même classe de revue externe que le VDF de Chronos.

### 4. ARGUS (7.5)

**Critique validée :** WARDEN attrape l'empoisonnement classique ([`argus/test/warden.test.ts`](https://github.com/alexar76/argus/blob/main/test/warden.test.ts)) ; `allowUnknownServers: true` dans les tests reflète des valeurs par défaut réellement permissives ; la réputation se dégrade vers neutre quand LUMEN est injoignable (autonomie plutôt que fail-closed).

**Actions :** A-8, A-9, A-10.

### 5. Hub + Protocol (7.2)

**Critique validée :** Le protocole v2 est la bonne fondation ; le crawler de fédération + les canaux fonctionnent dans le déploiement de référence ; pas de maillage de hubs tiers significatif ni de volume d'invocations en production → les cas limites (synchronisation du slashing, course sur les canaux, manifest périmé) restent surtout théoriques.

**Actions :** A-11, KI-10.

### 6. Alien Monitor (8.0)

**Critique validée :** UX solide et topologie LIVE ; critique limitée. Pas un substitut à la sécurité économique.

### 7. Outils de support (6.8–7.3)

**Critique validée :** HELIOS, le widget, les intégrations desktop sont réels mais **secondaires**. DIOSCURI (Castor/Pollux) est du **devrel + durcissement de référence** sur du chat public — utile, mais pas une infrastructure d'agents de production.

**Actions :** A-13 — étiquettes de palier, pas de survente sur la landing de l'écosystème.

---

## Communication (usage public)

> *Économie d'agents IA auto-hébergée — palier recherche/prototype. Démos solides et câblage du protocole ; audit externe, tests de charge et revue crypto requis avant un TVL à l'échelle mainnet.*

---

> 🌐 Langues : [English](ecosystem-maturity-review.en.md) · [Русский](ecosystem-maturity-review.ru.md) · **Français** · [Español](ecosystem-maturity-review.es.md) · [中文](ecosystem-maturity-review.zh.md)
