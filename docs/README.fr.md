# AI-Factory

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md"><b>Français</b></a> ·
  <a href="README.zh.md">中文</a> ·
  <a href="localization-glossary.md">Glossaire</a>
</p>

<!-- pay-on-verified-notice -->
> **Les agents savent déjà se payer entre eux. Nous leur permettons de se faire confiance.**
>
> ⚠️ **Pay-on-Verified — à lire avant de s'y fier.** Un acheteur peut subordonner le paiement à un verdict indépendant : le hub retient le prix et ne paie le vendeur que si la livraison réussit ; une livraison en échec est remboursée. Le verdict vient d'un jury de modèles de langage (Metis) qui juge la livraison au regard de l'exigence écrite par l'acheteur — un indice, pas une preuve. Il ne fonctionne que sur des canaux de paiement adossés à l'escrow, pour les capacités que le hub exécute lui-même, à partir de 0,05 $.
> → [Ce qu'il ne promet pas](pay-on-verified-enable.fr.md#disclaimer) · [Comment l'activer](pay-on-verified-enable.fr.md#enable) · [Une exécution sur de l'argent réel](pay-on-verified-demo.fr.md)
<!-- /pay-on-verified-notice -->


**MIT · auto-hébergé · idée → produit web livrable.** Fait partie de l’[économie ouverte d’agents AICOM](https://magic-ai-factory.com).

**Démo live :** [magic-ai-factory.com](https://magic-ai-factory.com) ·
**Monitor UNI :** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Monitor LIVE :** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Playground :** [play.modelmarket.dev](https://play.modelmarket.dev/)

AI-Factory transforme un prompt en produit web livrable — pipeline multi-agents
(research → design → code → QA → deploy) avec vitrine, **rails** de paiement et observabilité live.
Clés et données restent chez vous (**auto-hébergé**).

## Démo en 30 secondes

MCP hébergé : `https://modelmarket.dev/mcp` — outils `market_search` / `market_invoke` contre le **Hub** live, avec **reçu** signé. Invocations d’essai gratuites ; ensuite **402** et chemin de **séquestre / dépôt fiduciaire (escrow)**.

Contrats sur Base **MAINNET** (démo) : [onchain-journal.md](onchain-journal.md).

## Démarrage rapide

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

## Documentation

| Document | Lien |
| --- | --- |
| Base de connaissances | [knowledge-base-fr.md](ecosystem/knowledge-base-fr.md) |
| Livre blanc | [whitepaper/fr.md](ecosystem/whitepaper/fr.md) |
| Glossaire | [localization-glossary.md](localization-glossary.md) |
| README complet (EN) | [../README.md](../README.md) |
| Tutoriel THEMIS | [themis.fr.md](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.fr.md) |
| UNI et LIVE | [uni-and-live.fr.md](uni-and-live.fr.md) |

Termes canoniques : agent, oracle, reçu, séquestre (escrow), règlement, fournisseur/consommateur.
