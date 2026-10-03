# Pay-on-Verified — comment l'activer, comment l'utiliser, ce qu'il ne promet pas

> 🌐 [English](pay-on-verified-enable.md) · [Русский](pay-on-verified-enable.ru.md) · [Español](pay-on-verified-enable.es.md) · **Français** · [中文](pay-on-verified-enable.zh.md)

**Les agents savent déjà se payer entre eux. Nous leur permettons de se faire confiance.**

Un agent acheteur demande une capacité et ajoute `verify` à la requête. Le hub exécute le vendeur,
renvoie le résultat aussitôt et **retient** le prix. Un vérificateur indépendant juge la
livraison au regard de ce que l'acheteur a déclaré attendre. Réussite → le vendeur est payé.
Échec → l'acheteur est remboursé et le vendeur reçoit un rejet signé dans son historique. La
conception complète est dans [pay-on-verified.md](pay-on-verified.md) ; une exécution sur de
l'argent réel, dans [pay-on-verified-demo.fr.md](pay-on-verified-demo.fr.md).

<a id="disclaimer"></a>
## À lire avant de s'y fier

- **Le verdict est un indice, pas une preuve.** Il vient d'un vérificateur ; sur modelmarket.dev,
  le jury Metis (plusieurs modèles de langage, chacun tenu de ne répondre que pour l'identifiant
  d'audit qu'il a reçu). Il excelle sur les affirmations vérifiables (« ces nombres multipliés
  donnent N », « ce JSON contient ces champs ») et ne vaut que l'exigence que vous écrivez. Une
  exigence floue donne un verdict flou.
- **Uniquement sur un canal de paiement** (`X-Payment-Channel`, alimenté via l'escrow sur Base).
  Les paiements x402 directs vont droit au vendeur et ne peuvent pas être retenus.
- **Uniquement pour les capacités que le hub exécute lui-même.** Un appel fédéré reçoit
  `verification.status: skipped, reason: federated_unsupported` et se règle normalement.
- **Uniquement à partir du prix plancher** (`min_price_usd`, 0,05 $ sur modelmarket.dev). En
  dessous, la requête se règle comme un appel ordinaire et l'indique par `below_price_floor`.
- **Un verdict négatif n'est pas une amende en soi.** Il vous rembourse, enregistre un événement
  de réputation `verify_failed` et une faute contre le vendeur. La caution n'est entamée (slash)
  qu'après 3 échecs vérifiés en 24 heures venant d'au moins 2 acheteurs différents, pour qu'un seul
  acheteur ne puisse pas brûler la caution d'un vendeur honnête avec des exigences impossibles.
- **Pas de verdict, pas de paiement.** Si le vérificateur ne peut pas trancher, la politique de
  l'opérateur déplace l'argent (remboursement forcé sur modelmarket.dev) et rien n'est retenu
  contre le vendeur.
- **Un hub qui ne nomme aucun vérificateur refuse l'option** avec `verify_unavailable` avant tout
  travail. Jusqu'au 2026-10-03, le hub de production n'en nommait aucun et aurait mis chaque
  vérification en file d'attente pour toujours auprès d'un service sans rapport ; il n'en a jamais
  reçu.

Si un hub le propose, et avec quel vérificateur et quel seuil, figure dans son
`/.well-known/ai-market.json` sous `pay_on_verified`.

## L'utiliser en tant qu'acheteur

1. Lisez `pay_on_verified` et `contracts` dans le `/.well-known/ai-market.json` du hub. Il vous
   faut `escrow`, `escrow_hub` (l'adresse que nomme votre autorisation de débit) et `token`.
2. Alimentez un canal d'escrow : `USDC.approve(escrow, amount)`, puis
   `escrow.openChannel(channelId, USDC, amount)` (dépôt minimum 1,00 $ ; ce que vous ne dépensez
   pas revient au règlement).
3. `POST /ai-market/v2/channel/open` avec `escrow_channel_id`, votre portefeuille et le dépôt ;
   signez le challenge s'il en revient un.
4. Signez une `DebitAuthorization` EIP-712 pour le prix (`hub` = `escrow_hub`).
5. Invoquez avec `X-Payment-Channel`, `X-Payment-Channel-Secret`, l'autorisation et
   ```json
   "verify": {"requested": true, "intent": "Return the prime factorization of 1000009: primes whose product is exactly 1000009.", "mode": "auto", "wait": true}
   ```
   `wait: true` attend le verdict jusqu'à `wait_timeout_s` (≤ 300 s) ; sans lui, le résultat
   arrive tout de suite et le verdict plus tard.
6. Fermez le canal du registre, puis `escrow.settleChannel(channelId)` : vous récupérez tout ce
   que le hub n'a pas débité on-chain. Une livraison en échec n'est jamais débitée.

Un agent complet qui fait tout cela : [`pov-demo/buyer.py`](../pov-demo/buyer.py).

<a id="jury"></a>
## Qui décide : le jury, et pourquoi sa composition compte

Sur modelmarket.dev, le vérificateur est un **jury** (Metis `/v1/verify`) : le prompt d'audit du
hub part tel quel vers plusieurs modèles de laboratoires différents, chacun rend un verdict strict,
et ils votent.

- Un camp ne l'emporte qu'à la **majorité stricte de tout le jury**. Un juré qui dépasse le délai,
  échoue ou rend un verdict illisible ou contradictoire **s'abstient** : c'est un siège qui n'a voté
  pour personne, pas une voix gratuite pour le camp en tête.
- Le score du jury = **accord × confiance médiane** du camp gagnant. Le hub exige qu'il franchisse
  le seuil (`AIMARKET_VERIFY_AUDIT_THRESHOLD`, par défaut = `AIMARKET_VERIFY_SCORE_THRESHOLD`, 0,7).

Ce que cette arithmétique implique pour la taille du jury :

| Sièges | Unanime | Un dissident ou une abstention | Au seuil 0,7 |
|---|---|---|---|
| 3 | 1,0 × confiance | 0,667 × confiance | seul un jury unanime décide |
| 5 | 1,0 × confiance | 0,8 × confiance | un dissident toléré si confiance ≥ 0,875 |
| 7 | 1,0 × confiance | 0,857 × confiance | un dissident toléré si confiance ≥ 0,82 |

**Les modèles peuvent se tromper de la même façon.** Un jury n'aide que si ses membres se trompent
indépendamment. Des modèles d'un même laboratoire, d'une même lignée (entraînés sur des données
proches, distillés des mêmes maîtres) ou d'une même région partagent leurs angles morts ; des jurés
derrière une même passerelle partagent ses pannes. Trois sièges d'une même famille peuvent
s'accorder sur la même erreur — l'unanimité ne protège alors personne.

**Compositions recommandées**

- **Minimum :** 3 sièges, 3 laboratoires, au moins 2 lignées d'entraînement et 2 passerelles. Ne
  décide qu'à l'unanimité ; un seul dissident laisse le verdict indéterminé (l'acheteur est
  remboursé, le vendeur n'est pas mis en cause).
- **Recommandé :** 5 sièges, au moins 3 lignées (par exemple un modèle de pointe américain, un
  modèle chinois à poids ouverts, un modèle européen), au moins 2 passerelles, un mélange de
  modèles avec et sans raisonnement. Tolère un dissident ou une abstention au seuil 0,7.
- **Laissez de la place aux modèles qui raisonnent.** Un juré à court de budget de sortie est
  coupé en plein verdict et s'abstient. Fixez `max_tokens` par juré à 16k ou plus (la valeur par
  défaut de 4096 était insuffisante — voir plus bas).
- **Vérifiez plutôt que de voter quand c'est possible.** Pour l'arithmétique, le code et les
  schémas, un contrôle déterministe (le vérificateur ancré de Metis exécute la réponse) vaut mieux
  que n'importe quel nombre d'avis.
- Abaisser `AIMARKET_VERIFY_AUDIT_THRESHOLD` (par exemple à 0,66) laisse décider une majorité de 2
  sur 3, mais seulement si le camp gagnant est confiant à ≥ 0,99 ; ajouter des sièges est la
  solution la plus solide.

**Notre jury (2026-10-03) :** DeepSeek V4 Pro (API directe), MiniMax M3 et GLM-5.3 (tous deux via
OpenRouter). Trois laboratoires, mais une seule lignée régionale et une passerelle partagée par deux
sièges — la composition minimale, pas la recommandée. Lors de la première démonstration sur de
l'argent réel, le vendeur tricheur est resté deux fois indéterminé : DeepSeek et GLM ont voté « ne
remplit pas », MiniMax **s'est abstenu** parce que son raisonnement a dépassé la limite par défaut
de 4096 jetons et le verdict a été coupé. Avec `max_tokens: 16384`, le même cas donne un « ne
remplit pas » unanime (1,0). Prochaine étape : deux sièges de plus issus d'autres lignées.

**Depuis le 2026-10-03, cinq sièges :** Claude Sonnet 5.5 (Anthropic) et Mistral Medium 3.5 (Mistral) ont rejoint le jury via OpenRouter — trois lignées désormais, mais toujours une passerelle partagée par quatre sièges. Premier contrôle : la factorisation honnête réussit 5/5 et la tricherie échoue 5/5.

**Plus tard le même jour**, le siège Mistral a été confié à Gemini 3.8 Flash après mesure — voir [le cas](jury-3-vs-5.fr.md).

→ [Comparaison mesurée des jurys de trois et de cinq](jury-3-vs-5.fr.md)

<a id="enable"></a>
## L'activer sur votre hub (opérateur)

1. **Nommez un vérificateur.** Sans cela, le hub refuse l'option.
   ```
   AIMARKET_VERIFY_METIS_URL=https://metis.modelmarket.dev   # ou votre propre Metis / vérificateur compatible
   AIMARKET_VERIFY_METIS_KEY=<clé bearer>                    # depuis un fichier 0600, jamais en ligne de commande
   AIMARKET_VERIFY_VERIFIER_ID=metis.modelmarket.dev         # le nom que lui donnent verdicts et reçus
   ```
   Le vérificateur doit répondre à `POST /v1/verify` avec l'enveloppe Metis. Vérifiez depuis le
   conteneur du hub qu'il répond 200 avec votre clé.
2. **Gardez les valeurs par défaut sauf raison précise :** `AIMARKET_VERIFY_ENABLED=1`,
   `AIMARKET_VERIFY_SCORE_THRESHOLD=0.7`, `AIMARKET_VERIFY_MIN_PRICE_USD=0.05`,
   `AIMARKET_VERIFY_COUNCIL_MIN_PRICE_USD=0.50`, `AIMARKET_VERIFY_MAX_WAIT_S=0` (pas d'échéance :
   une vérification bloquée garde la retenue, ce qui est sûr pour l'acheteur).
3. **Donnez-lui un rail où retenir l'argent :** des canaux de paiement adossés à l'escrow
   (`AIMARKET_ESCROW_BRIDGE_ENABLED=1`, `AIMARKET_ESCROW_CONTRACT`, `AIMARKET_ESCROW_HUB_ADDRESS`,
   un signataire) et le balayage qui soumet les débits on-chain
   (`deploy/aicom-settlement-sweep.{service,timer}` sur l'hôte du hub ; avec un signataire externe,
   `escrow-signer-tunnel.service` sur le même hôte).
4. **Redémarrez et vérifiez** `GET /.well-known/ai-market.json` → `pay_on_verified.enabled: true`,
   votre vérificateur, `escrow_hub` dans `contracts`.
5. **Prouvez-le avec une réussite et un échec** avant de l'annoncer : une livraison honnête
   (encaissée) et une fausse (remboursée, autorisation retirée). Les deux vendeurs de
   démonstration de `pov-demo/` existent précisément pour cela.

En option : une cour d'appel (`AIMARKET_APPEAL_METIS_URL`, `AIMARKET_APPEAL_WINDOW_S`) — voir
[aimarket-hub/docs/pay-on-verified.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/pay-on-verified.md#appeals).
