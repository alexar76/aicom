# HISTOR et LEGION-tlog sur un même serveur MCP

[English](README.en.md) · [Русский](README.md) · [Español](README.es.md) · [Français](README.fr.md) · [简体中文](README.zh.md)

Deux journaux de transparence indépendants peuvent-ils corroborer les définitions d’outils annoncées par un serveur MCP à des moments comparables ? Nous avons choisi LEGION-tlog pour l’heure d’observation et l’empreinte SHA-256 qu’il publie pour chaque outil. On peut ainsi retrouver un ensemble d’outils identique et localiser les écarts avec les observations ultérieures du même serveur, `com.aiapplyd/aiapplyd`.

| Observation de HISTOR (UTC) | Comparaison avec LEGION |
|---|---|
| 19 octobre 2026, 21:37:07 | Les 23 empreintes de `name`, `description` et `inputSchema` concordent avec l’observation de LEGION à 22:01:05. |
| 24 octobre, 18:19:21 | Les 23 noms passent du préfixe `aiapplyd_` à `getmattered_` et gardent leurs suffixes. La réponse archivée de LEGION affiche encore l’enregistrement du 19 octobre. |
| 31 octobre, 12:45:49 | HISTOR enregistre 40 outils. Aucun nom ne figure dans l’enregistrement archivé de LEGION. L’instantané du 2 novembre contient cet ensemble d’outils. L’heure de la lecture ultérieure provient des métadonnées de l’instantané. |

## Vérification hors ligne

Lancer la commande depuis la racine du dépôt avec Node.js 22.

```sh
node artifacts/histor-legion-case-2026-11-03/replay.mjs
```

Comparer la sortie à [result.json](result.json). Le script vérifie les signatures Ed25519 et la preuve d’inclusion de la feuille 29030 de LEGION sous sa tête d’arbre signée (STH) de 50 578 feuilles. Il vérifie ensuite le STH de HISTOR de 1 564 894 feuilles, les signatures et les preuves d’inclusion des étiquettes MTL/1 aux feuilles 762851, 988911 et 1324412, puis l’empreinte SHA-256 qui lie chaque ensemble d’outils à son étiquette signée. Enfin, il répète la comparaison outil par outil.

Les éléments de preuve portent sur ces observations et ces têtes d’arbre de Merkle. La sécurité du serveur, la raison pour laquelle la réponse archivée de LEGION ne contient pas le changement ultérieur, la cohérence entre les têtes et l’ancrage Bitcoin restent hors du périmètre de cette vérification.

[Provenance des données](README.md) · [Documentation du journal HISTOR](../../histor/docs/log.fr.md) · [Spécification de LEGION](https://legion-api.com/tlog/docs/)
