# Premier appel d’un agent : découvrir → invoquer → vérifier

[English](agent-first-call.md) · [Русский](agent-first-call.ru.md) · [Español](agent-first-call.es.md) · [Français](agent-first-call.fr.md) · [中文](agent-first-call.zh.md)

Choisissez votre client habituel. MCP et A2A donnent accès à la même place de marché et aux mêmes contrôles d’invocation ; il n’est pas nécessaire d’adopter les deux.

## Client MCP

Ajoutez `https://modelmarket.dev/mcp` à un client MCP compatible Streamable-HTTP. Consultez `tools/list` pour obtenir les schémas d’arguments actuels, puis confiez cette tâche à l’agent :

> Recherchez la météo GAIA Open-Meteo avec `market_search`. Affichez le prix et le schéma d’entrée de l’offre choisie. Appelez `market_invoke` pour `device_id` `om-wx-01`, en copiant `product_id`, `capability_id` et `source_hub` depuis cette offre. Utilisez l’essai gratuit et arrêtez-vous si un paiement est demandé. Affichez le résultat et le reçu. Distinguez la vérification du reçu de la réussite de l’exécution : la présence d’un champ de signature ne signifie pas que la vérification a réussi.

Conservez `source_hub` : une offre fédérée doit être invoquée en indiquant son origine. Le service hébergé peut renvoyer `429 trial_quota_exhausted` lorsque l’essai est épuisé. Voir les [détails MCP](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md). L’exemple A2A ci-dessous vérifie explicitement la signature côté client.

## Agent A2A

L’[exemple Python commun](../examples/first-agent-call.py) récupère l’Agent Card, recherche `gaia.weather.read@v1`, conserve le hub d’origine et plafonne le prix d’un appel à $0.01. Exécutez-le depuis le répertoire `aimarket-hub` avec Python 3.11+ :

```bash
python -m pip install 'aimarket-agent>=2.4.0'
```

```bash
python examples/first-agent-call.py
python examples/first-agent-call.py --invoke
```

La première commande effectue uniquement une recherche. La seconde réalise une invocation. Sans `AIMARKET_KEY`, elle utilise un essai gratuit disponible. Pour tester le paiement avec des crédits prépayés, définissez `AIMARKET_KEY` avec la clé API d’un compte approvisionné : l’appel peut débiter jusqu’à $0.01. Ne stockez pas la clé dans un script ou un commit. La variable `AIMARKET_HUB_URL` permet de choisir un autre hub.

L’exemple transmet `device_id` `om-wx-01` à l’offre GAIA Open-Meteo. Si le catalogue change, consultez le schéma d’entrée renvoyé par la recherche. Si aucune offre ne correspond, l’exemple s’arrête sans invocation.

## Reprendre une Task avec x402

Après le code `2`, consultez les conditions de paiement de la Task. Payez la facture une seule fois avec votre portefeuille (wallet), attendez le règlement et utilisez le même Task ID et le même hash de transaction. L’exemple présente un transfert déjà effectué ; il ne signe, n’envoie ni ne remplace de transaction. Une Task liée à un compte nécessite le même `AIMARKET_KEY`. Lire une Task terminée ne répète ni le paiement ni l’invocation.

La correction de la reprise x402 est dans ce checkout `aicom`. Jusqu’à sa publication dans le SDK, installez le client local depuis le répertoire `aimarket-hub` :

```bash
python -m pip install -e ../aimarket-agent
```

```bash
python examples/first-agent-call.py --task-id a2at_... --payment-tx 0x...
python examples/first-agent-call.py --task-id a2at_...
```

## Interpréter le résultat

- Code `0` après `--invoke` : la Task est `TASK_STATE_COMPLETED` et `receipt_verified` vaut true. Le SDK a vérifié le reçu avec la clé du signataire ; pour une offre fédérée, il utilise celle du fournisseur. Le résultat n’est affiché qu’après cette vérification.
- Code `1` : l’offre météo était indisponible.
- Code `2` : la Task n’est pas terminée. `TASK_STATE_INPUT_REQUIRED` peut demander un paiement ; `TASK_STATE_AUTH_REQUIRED`, des identifiants. Consultez le statut affiché et le [guide de paiement](a2a.md#invoke).
- Code `3` : l’exécution est terminée, mais la vérification du reçu a échoué ou aucun reçu n’a été renvoyé. Ne considérez pas le résultat comme vérifié.
- Code `4` : le reçu est valide, mais le résultat météo manque. L’exécution et la vérification de la signature ne suffisent pas à faire réussir cet exemple.

Le code `0` sans `--invoke` confirme uniquement la découverte. Les erreurs réseau ou de protocole arrêtent aussi l’exemple. Il ne recharge pas les comptes, ne transfère pas de fonds, ne reprend pas un paiement et ne réessaie pas automatiquement. Une Task inachevée ne prouve pas l’absence de débit ; consultez son statut avant de réessayer. Pour une nouvelle tentative délibérée, réutilisez le même `message_id` conformément au [guide A2A](a2a.md).

Un reçu valide authentifie un document signé. Il ne prouve pas indépendamment l’exactitude des données météo. Le hub détermine les limites de l’essai et la disponibilité des offres ; cet exemple ne les garantit pas.
