# Étude des seuils WARDEN : conserver 8/10, corriger l’index des identifiants secrets

**Transparence :** je maintiens WARDEN dans l’écosystème alexar76. Cette expérience, son analyse et ce rapport ont été préparés avec une aide substantielle d’IA générative. Il s’agit d’une évaluation de notre propre code par son mainteneur sur des cas construits, pas d’un audit indépendant ni d’une mesure du trafic de production.

Date : 2026-10-25. **État : la modification finale du code est locale et n’a pas fait l’objet d’une version publiée.**

## Question et décision

[jkming a demandé](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ion2) si WARDEN devait reconnaître des fragments secrets plus courts incorporés dans d’autres mots. Nous avons comparé des fenêtres non hexadécimales de 6, 7 et 8 caractères ; la fenêtre hexadécimale est restée à 10 dans tous les cas.

Nous avons conservé 8/10 et corrigé un défaut d’indexation plus précis. Cela a amélioré la reconnaissance sans modifier les décisions sur l’échantillon de requêtes ordinaires. Cela **ne rend pas** fiable la détection d’un fragment de 6 caractères incorporé dans un mot.

## Résultats du garde complet

`ask` suspend l’exécution dans l’attente de l’accord de l’opérateur ; `deny` la refuse ; `pass` l’autorise à traverser ce garde. Après lecture d’un identifiant secret et de texte externe, le garde évalué exige une approbation pour les appels sortants/MCP pris en charge, sauf règle exacte pour une requête publique vérifiée indépendamment. Aucune requête réelle n’a été envoyée.

| Variante | Requêtes d’attaque | `pass` | `ask` | `deny` |
| --- | ---: | ---: | ---: | ---: |
| Originale, 6 | 14,400 | 0 | 7,145 | 7,255 |
| Originale, 7 | 14,400 | 0 | 10,464 | 3,936 |
| Originale, 8 | 14,400 | 0 | 11,555 | 2,845 |
| Finale, 8 | 14,400 | 0 | 10,838 | 3,562 |

La correction a fait passer 717 requêtes de `ask` à `deny` : 342 cas de type Stripe et 375 de type GitHub. Ce ne sont **pas 717 transmissions automatiques supplémentaires empêchées** : l’approbation les arrêtait déjà. Tous les refus précédents sont conservés.

Sans la barrière générale liée aux identifiants secrets, le détecteur final de fuites/fragments n’a, à lui seul, trouvé aucune correspondance pour 8,709 requêtes d’attaque. La reconnaissance d’empreintes ne remplace pas cette barrière.

## Requêtes ordinaires et contrôles de correspondances

Les 7,680 requêtes ordinaires distinctes ont chacune été testées dans les deux profils. Dans le profil strict par défaut, chaque variante a demandé une approbation pour les 7,680. Avec des règles exactes et vérifiées pour les requêtes publiques, les 7,680 sont passées sans question supplémentaire ni refus. Ce sont les mêmes entrées dans deux profils, pas des échantillons indépendants. Le profil par défaut impose toujours un travail de vérification important.

L’analyse directe avec 480 identifiants secrets de calibration a couvert 3,575 fichiers publics uniques, 39,259 extraits et 22,056,276 lettres et chiffres normalisés. La fenêtre 6 a produit 79 correspondances exactes de sous-chaînes dans 31 extraits ; les fenêtres 7, 8 et finale 8 n’en ont produit aucune. Il s’agit de correspondances de sous-chaînes, pas de collisions de hachages tronqués ni d’un taux de faux positifs par appel.

Nous avons rejoué les 31 paires correspondantes « identifiant secret/extrait » dans le véritable hook avec des règles exactes pour les requêtes publiques. La fenêtre 6 a refusé à tort les 31 ; les autres variantes en ont autorisé 29 et demandé l’approbation pour 2. Ces contrôles ont été sélectionnés précisément parce qu’ils correspondaient ; leurs proportions n’estiment pas les taux de la population.

Un contre-exemple connu distinct a reproduit un faux refus à 7 : du texte ordinaire JSON/de contrôle de santé contenait `mit3okt` après normalisation, correspondant à un identifiant secret synthétique de type PEM. Les fenêtres 6 et 7 l’ont refusé ; l’originale et la finale 8 l’ont autorisé. Un compte nul dans le nouveau corpus ne démontre donc pas que le déploiement de 7 est sûr.

## Correction de l’index

L’ancien index ignorait toutes les lettres initiales jusqu’au premier chiffre. Une clé avec préfixe de fournisseur et chiffres proches de la fin pouvait donc n’avoir aucune fenêtre admissible de 8 caractères. La modification finale commence plus tôt après les préfixes de fournisseur reconnus, tout en conservant la condition de mélange lettres/chiffres et les exclusions existantes pour DER et les valeurs génériques.

Nous avons rejeté une variante plus large : après lecture de `AcmeIntegrationToken2026`, elle refusait à tort le texte public vérifié `Public build Token2026`. La version finale conserve la décision initiale sur ce contrôle.

Toutes les anciennes empreintes ont été conservées pour les 960 identifiants secrets : 0 perdue, 70,466 → 71,612 entrées, avec un élargissement pour 279 identifiants. Les sessions existantes doivent relire l’identifiant secret pour obtenir les nouvelles fenêtres. Sur 960 cas embedded-6, la finale 8 a encore produit 960 demandes d’approbation et 0 refus.

## Méthode et limites

Nous avons utilisé 960 identifiants secrets synthétiques répartis en huit formats et deux graines déterministes, avec 15 attaques par identifiant. Les partitions du corpus ne se recoupaient pas entre graines. Les positions d’attaque visaient délibérément le défaut d’indexation ; les proportions observées dépendent des cas construits.

Toutes les mesures empiriques du corpus et du garde ont été exécutées dans des conteneurs Docker Linux restreints et sans réseau, **sans gVisor**. Séparément, 1,156 tests de code ont réussi localement sur macOS. Le gate existant comportait 26 attaques avec outils, dont 0 entièrement livrée, plus 2 scénarios de réponse seule. Ces contrôles étayent la correction ciblée et les seuils conservés ; ils ne démontrent ni une sécurité universelle ni un taux de faux positifs en production.
