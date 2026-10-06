# Enquête de livraison x402 — un appel payé à 100 vendeurs

> 🌐 [English](x402-delivery-survey.md) · [Русский](x402-delivery-survey.ru.md) · [Español](x402-delivery-survey.es.md) · **Français** · [中文](x402-delivery-survey.zh.md)

**Plus de vingt index de confiance vérifient si les vendeurs x402 répondent par un prix. Nous avons vérifié ce que reçoit un acheteur après avoir payé.**

Le 5 octobre 2026, nous avons tiré au hasard 100 vendeurs du CDP Bazaar. Nous avons envoyé à chacun la requête d'exemple de sa propre annonce, l'avons payée en USDC sur Base et avons vérifié le débit sur la chaîne. Un jury de cinq modèles a ensuite jugé chaque réponse. Aucun vendeur n'est nommé ici ; les raisons sont dans [Pourquoi sans noms](#pourquoi-sans-noms).

## Résultats

| Issue | Vendeurs |
|---|---|
| Réponse acceptée par le jury | 74 |
| Réponse rejetée par le jury, acheteur débité | 3 |
| Réponse reçue, le jury n'a pas atteint la confiance dans un sens ou dans l'autre | 8 |
| Erreur après paiement, acheteur **non** débité | 9 |
| Erreur après paiement, acheteur débité | 1 |
| Non acheté | 5 |
| **Total** | **100** |

- **Achats.** 95 paiements ont été signés, pour 0,536 $ au total. 85 ont été exécutés sur la chaîne, pour 0,489 $.
- **Réponses acceptées.** 74 des 85 appels payés (87 %) ont renvoyé une vraie réponse du type promis par l'annonce.
- **De l'argent pour rien.** 4 des 85 appels payés (4,7 %) ont débité l'acheteur sans réponse utile, 0,022 $ en tout.
- **Échecs honnêtes.** Neuf vendeurs ont échoué après paiement sans prendre l'argent ; plusieurs le disent dans l'erreur même (« you were not charged »).
- **Temps de réponse.** Les appels payés ont répondu en 1,9 s en médiane, 4,3 s au 90e centile et 40 s au plus.

## Ce qui a mal tourné

| Problème | Vendeurs |
|---|---|
| L'exemple de l'annonce elle-même échoue : le service le rejette, ou il mène à une erreur ou à un écho de la description du champ | 7 |
| L'exemple de l'annonce elle-même ne peut pas être envoyé : des espaces réservés à la place des valeurs, ou un type de corps que les clients HTTP n'envoient pas | 2 |
| Panne du fournisseur de données après paiement (502 de la passerelle, RPC en panne, modèle à froid, flux de prix en reconnexion) | 4 |
| Erreur après le débit | 1 |
| Résultat vide contre de l'argent | 1 |
| Résultat incomplet contre de l'argent (« partial », « indeterminate ») | 1 |
| Un rapport d'erreur à la place des données promises | 1 |
| L'en-tête de règlement dit « payé », la chaîne ne montre aucun transfert | 1 |
| Débité, mais sans en-tête de règlement | 1 |
| Le 402 mélange des champs x402 v1 et v2, et le client de référence refuse de payer | 1 |
| Le bénéficiaire du 402 diffère de celui de l'annonce | 1 |
| Prix réel supérieur au prix annoncé | 1 |
| Pas de réponse à la requête non payée en 20 s | 1 |

Un vendeur peut avoir plus d'un problème.

Il n'y a presque rien à qualifier de fraude. Le défaut le plus courant est l'annonce elle-même : environ un vendeur sur dix affiche une requête d'exemple qui ne fonctionne pas. Un agent acheteur qui copie l'appel documenté reçoit une erreur. En général il n'est pas débité, mais il n'obtient pas non plus de réponse.

## Ce qu'une sonde du 402 ne voit pas

Tous les index que nous avons trouvés envoient une requête non payée et lisent le 402. Dans notre échantillon, 96 vendeurs sur 100 ont passé ce test. Plusieurs choses n'apparaissent que lorsque quelqu'un paie :

- si l'exemple documenté fonctionne ;
- si le vendeur débite en cas d'erreur ;
- si le règlement qu'il annonce a atteint la chaîne ;
- si une réponse 200 est une vraie réponse ou une liste vide.

Les chiffres de cette enquête viennent de 95 appels payés, pas du 402.

## La découverte principale : la demande

Le Bazaar publie ses propres compteurs sur 30 jours. Sur 34 768 annonces, 22 559 (65 %) ont eu exactement un portefeuille payeur en 30 jours — très probablement le vendeur lui-même, qui paie une fois pour être indexé. Seules 396 (1,1 %) en ont eu dix ou plus. Dans notre échantillon, 23 des 74 vendeurs dont la réponse a été acceptée avaient exactement un payeur.

Le marché x402 ne semble pas manquer de confiance. Il semble manquer d'acheteurs.

## Méthode

- **Catalogue.** API de découverte du CDP Bazaar le 2026-10-05 à 19:47 UTC : 34 768 annonces. L'instantané est conservé, sha256 `6de6966927e5cc5b83f55f7c128c48861eab4cebf1e3fb61c2c9cb0d583d876c`.
- **Annonces éligibles.** x402 v2, HTTPS, une requête d'exemple déclarée (`extensions.bazaar.info.input`) et une offre `exact` en USDC sur le réseau principal Base d'au plus 0,01 $. Nos propres hôtes et portefeuilles, et ceux de nos écosystèmes frères, ont été exclus. Restent 28 382 annonces sur 1 466 hôtes. Un hôte compte pour un vendeur.
- **Échantillon.** 100 hôtes tirés par sha256 de la graine `aimarket delivery survey 2026-10-05` et du nom d'hôte. Une annonce par hôte a été tirée de la même façon. Quiconque détient l'instantané et la graine tire les mêmes vendeurs.
- **Requête.** Exactement l'exemple déclaré par le vendeur : méthode, paramètres de chemin, query et corps. Les en-têtes déclarés n'ont pas été envoyés ; ce sont surtout les propres clés d'API du vendeur.
- **Essai à blanc.** La même requête sans paiement, pour lire le 402 et le comparer à l'annonce. 96 vendeurs pouvaient être payés dans la limite et au bénéficiaire annoncé.
- **Achat.**
  - Le 402 est relu, et le paiement n'a lieu que si ses conditions sont exactement celles de l'essai à blanc.
  - L'acheteur est le client de référence x402 2.28, avec sa propre limite de dépense fixée à 0,01 $. Il ne peut signer qu'un `transferWithAuthorization` EIP-3009 : jamais Permit2, jamais une approbation.
  - L'ensemble de l'exécution avait un budget strict de 0,55 $. Chaque réponse a été conservée comme preuve.
- **Débit.** `authorizationState(payer, nonce)` du contrat USDC sur Base pour chaque paiement signé. C'est l'enregistrement de la chaîne, pas la parole du vendeur.
- **Jugement.**
  - Le jury est Metis, cinq modèles de cinq fournisseurs. Son prompt et son lecteur de verdicts sont ceux qui libèrent le séquestre dans [Pay-on-Verified](pay-on-verified-demo.fr.md) ; voir aussi [jury-3-vs-5.fr.md](jury-3-vs-5.fr.md).
  - La question : la réponse est-elle une réponse authentique et complète à cette requête, du type promis par l'annonce, et non une erreur, un résultat vide ou factice, une demande de paiement supplémentaire ou d'identifiants, ou un contenu sans rapport ?
  - Un verdict ne compte que si la confiance propre du jury atteint au moins 0,7.
  - Nous avons vérifié à la main 12 réponses acceptées. Toutes étaient réelles : un embedding de 768 nombres, un article de Wikipédia, des données Product Hunt, une projection Web Mercator inverse correcte.

## Limites

- **Un moment, un appel.** Chaque vendeur a reçu un appel, un jour donné. Un vendeur en panne à cette minute compte comme en panne.
- **Uniquement l'exemple du vendeur.** Un exemple trivial (« analyse le user agent `example` ») reçoit une réponse triviale, et elle passe.
- **Pas une vérification des faits.** Le jury juge si la réponse est authentique et du type promis. Là où il pouvait vérifier un fait (une projection, un article), il l'a fait ; en général, il ne le fait pas.
- **Une tranche étroite du marché.** Des vendeurs à 0,01 $ ou moins, sur Base, avec un exemple déclaré. Les annonces plus chères ou sans exemple ne sont pas couvertes.
- **Notre intérêt dans la réponse.** Nous exploitons [AIMarket](https://modelmarket.dev), un marché où des agents paient des agents, et nous vendons de la vérification. C'est pourquoi la graine, l'outil et les données anonymisées sont publics, et pourquoi ce rapport dit ce qu'il a trouvé : la plupart des vendeurs livrent.

## Pourquoi sans noms

Un appel payé un jour donné est une preuve mince contre une entreprise, et notre requête n'est peut-être pas l'usage que le vendeur avait en tête. Plutôt qu'une liste publique :

- **Les données.** La ligne anonymisée de chaque vendeur se trouve dans [`scripts/delivery-survey/results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json). Les lignes sont mélangées au sein de chaque issue, les prix et le nombre de payeurs sont donnés par tranches, et il n'y a ni hôtes ni transactions.
- **Les preuves privées.** Le fichier complet — hôte, requête, réponse, transaction et verdict — a pour sha256 `f55c952d752319d1a862c7154f8d93ca0aa675b5cd1172b368846e5fbe2f5cf9` ; il ne peut donc pas changer après publication. Chaque vendeur peut voir sa propre ligne.
- **Contact avec les vendeurs.** Nous écrivons aux vendeurs dont l'annonce avait un problème, chacun avec ses propres preuves.

Un vendeur peut aussi se tester lui-même avec le même outil. L'étape sans paiement ne coûte rien :

```bash
cd scripts/delivery-survey && npm ci
node survey.mjs catalog --out bazaar.json
node survey.mjs sample --catalog bazaar.json --host your.host --cap 0.01 --seed self --out plan.json
node survey.mjs probe --plan plan.json --out probe.jsonl      # sans paiement : votre exemple et votre 402
node survey.mjs buy --plan plan.json --probe probe.jsonl --out buy.jsonl --budget 0.05 \
  --payer 0xYourBuyer --key-file wallet.json                   # un appel payé par annonce
node survey.mjs chain --buy buy.jsonl --out chain.json         # débité ou non, selon la chaîne
```

`wallet.json` contient `{"mnemonic": "…"}` d'un portefeuille acheteur jetable (`--address-index` choisit le compte). Utilisez un portefeuille séparé avec quelques centimes.

## Outil et données

- Outil : [`scripts/delivery-survey/`](../scripts/delivery-survey/). Il couvre l'échantillon, l'essai à blanc, l'achat, la vérification sur la chaîne et le rapport, avec 22 tests. Parmi eux, un vendeur local qui vérifie réellement la signature EIP-712.
- Étape du jury : [`judge_in_hub.py`](../scripts/delivery-survey/judge_in_hub.py). Elle s'exécute dans notre hub, où se trouve la clé du vérificateur.
- Données anonymisées : [`results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json).
