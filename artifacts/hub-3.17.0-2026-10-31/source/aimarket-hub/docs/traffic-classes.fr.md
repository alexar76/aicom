# Qui compte comme « nous » : trafic SELF et EXT

[English](traffic-classes.md) · [Русский](traffic-classes.ru.md) · [Español](traffic-classes.es.md) · [Français](traffic-classes.fr.md) · [中文](traffic-classes.zh.md)

Chaque appel enregistré par le hub est **SELF** ou **EXT**. La classe apparaît :
- dans `/ai-market/v2/stats/live`, champ `traffic_class` de chaque événement ;
- sur la page d’accueil : l’étiquette `ext` / `self`, les filtres, le bandeau défilant ;
- dans les compteurs cumulés `external_invocations` et `operator_self_invocations`.

EXT est le chiffre que vous citez comme demande. Il ne doit pas contenir votre propre trafic, ni perdre un seul vrai client.

## La règle

- **SELF**, c’est le hub lui-même et les composants qui lui sont rattachés et appartiennent à **son propre écosystème** : les services que vous faites tourner pour ce hub, comme vos desks, moniteurs, canaris et fournisseurs maison.
- **EXT**, c’est tout le reste :
  - acheteurs et agents ;
  - autres écosystèmes ;
  - quiconque déploie ce code open source pour son propre compte ;
  - **services externes branchés par un canal payant**, même s’ils tournent sur votre matériel. Un jeu qui achète des capacités pour ses joueurs est un client, pas une partie de l’écosystème.

Sans configuration, le hub ne connaît que lui-même. Sont SELF les tests de fumée admin, `local` et l’URL du hub ; tout le reste est EXT. Le reste de votre écosystème se déclare dans un seul fichier, `ecosystem.json`.

## Ce qui décide la classe

| Indice | S’applique à | Décidé | Effet |
|---|---|---|---|
| Le hub lui-même : test de fumée avec le Bearer admin, `local`, l’URL du hub | tout appel | à la lecture | toujours SELF |
| Un appel **relayé**. Un autre hub a routé un acheteur ici : il envoie `X-AIMarket-Routing-Hub` / `X-AIMarket-Buyer` ou un visiteur d’essai `hub-fed-…`. Également une seller operation achetée sur un autre hub | tout appel | à l’écriture | jamais SELF sur ce hub |
| `external.networks`, `external.wallets` | tout appel | à l’écriture | EXT, quoi qu’il arrive par ailleurs |
| `external.accounts` | appels débités d’un compte de crédit | à la lecture | EXT, quoi qu’il arrive par ailleurs |
| `self.accounts` | appels débités d’un compte de crédit : `X-API-Key`, un mandat, une enveloppe de tâche | à la lecture | SELF |
| `self.wallets` | appels x402 : le portefeuille qui a payé, vérifié sur la chaîne (un identifiant de canal de paiement arrive dans un en-tête et ne garantit rien) | à l’écriture | SELF |
| `self.networks` | uniquement les appels **sans payeur ni visiteur d’essai** : passerelle MCP du hub, appels sans identité | à l’écriture | SELF |

Les lignes sont examinées dans cet ordre et la première qui correspond l’emporte. `external` l’emporte donc toujours sur `self`, et un appel relayé n’est jamais SELF. Une exception : un payeur x402 vérifié sur la chaîne est un indice d’où qu’il arrive, donc `self.wallets` / `external.wallets` s’appliquent aussi dans un relais. Une requête d’un pair absent d’`AIMARKET_TRUSTED_PROXIES` mais portant `X-Forwarded-For`, `Forwarded` ou `X-Real-IP` est un relais qui s’annonce, et compte comme relayée.

**« À la lecture »** signifie que modifier le fichier reclasse l’historique. Retirez un compte de `self.accounts`, et ses appels passés redeviennent EXT au prochain chargement de la page.

**« À l’écriture »** signifie que l’indice (l’adresse de l’appelant, le portefeuille payeur) n’est pas conservé. Le hub le juge une fois, en écrivant la ligne, et ne garde que le verdict. Un serveur ou un portefeuille ajouté aujourd’hui ne classe que les appels faits à partir de maintenant. La ligne retient en revanche QUELLE entrée s’est portée garante : retirer une entrée erronée du fichier ramène ces lignes en EXT.

## Pourquoi une adresse ne garantit jamais un appel payant

La tuyauterie du hub fait de vos serveurs l’appelant direct de beaucoup de trafic qui n’est pas le vôtre :

- un hub pair qui route l’achat d’un inconnu arrive depuis **l’adresse de ce hub** ;
- une étape Studio payante achetée sur un autre hub arrive depuis le **hub acheteur** ;
- un appel enfant de sous-traitance, financé par l’enveloppe d’un inconnu, est passé par **l’hôte de votre fournisseur** ;
- un exécuteur de l’usine lance le pipeline gratuit d’un visiteur web **depuis l’hôte de l’usine**.

Si une adresse pouvait rendre ces appels SELF, la vraie demande disparaîtrait d’EXT. Un appel payant est donc jugé sur **qui a payé** (le compte ou le portefeuille), jamais sur sa provenance. La règle d’adresse ne couvre que les appels sans payeur ni visiteur d’essai : un visiteur d’essai qui arrive d’un serveur est presque toujours un relais.

Un appel relayé est classé par le hub qui l’a routé, le seul à avoir vu le véritable acheteur. Le flux de chaque hub reste ainsi honnête. Si vous additionnez plusieurs hubs, écartez les lignes `traffic_basis: "forwarded"` pour qu’un achat ne compte pas deux fois.

## Le fichier

**Où :**
1. `AIMARKET_ECOSYSTEM_FILE`, si elle est définie ;
2. sinon `ecosystem.json` à côté de la base du hub (`AIMARKET_DB_PATH`). Dans l’image Docker, c’est `/app/data/ecosystem.json`, sur le volume de données ;
3. sinon `./data/ecosystem.json`.

Gardez-le sur le serveur. Il liste vos serveurs et vos comptes, il n’a donc rien à faire dans un dépôt public. Le dépôt fournit [`examples/ecosystem.example.json`](../examples/ecosystem.example.json) avec des adresses des plages de documentation.

**Format.** JSON. Chaque entrée est une chaîne, ou un objet `{"value": "...", "note": "pourquoi c’est là"}`. Le hub ignore `note` : il sert à la personne qui éditera le fichier ensuite.

```json
{
  "version": 1,
  "self": {
    "accounts": [{"value": "acct_0123456789abcdef", "note": "desk de démo"}],
    "networks": [{"value": "198.51.100.7", "note": "hôte des desks et de la supervision"}, "2001:db8:7::7"],
    "wallets":  [{"value": "0x1111111111111111111111111111111111111111", "note": "acheteur de test"}]
  },
  "external": {
    "accounts": [{"value": "acct_aaaaaaaaaaaaaaaa", "note": "un jeu que nous hébergeons : un client"}],
    "networks": ["203.0.113.80"],
    "wallets":  []
  }
}
```

**Validation :**

- **Une erreur de structure rejette tout le fichier** : clé inconnue, mauvais type, `version` différente de `1`. Sinon, un `"netwroks"` mal orthographié supprimerait une liste sans un mot.
- **Une valeur isolée invalide** est ignorée et signalée, et le reste s’applique.
- **Le hub refuse les réseaux** qui, vus de l’intérieur du hub, ne peuvent jamais être l’un de vos serveurs :
  - loopback, `0.0.0.0/8` et `::` ;
  - RFC 1918 et CGNAT `100.64.0.0/10` ;
  - link-local, IPv6 unique-local et multicast ;
  - les préfixes de traduction IPv4 (NAT64 `64:ff9b::/96`, 6to4 `2002::/16`) ;
  - tout ce qui est plus large qu’un `/24` IPv4 ou un `/56` IPv6 : inscrivez vos serveurs, pas le bloc de votre hébergeur ;
  - tout réseau contenant une adresse de `AIMARKET_TRUSTED_PROXIES`.

  Ce sont précisément les adresses d’où arrivent la passerelle MCP, les ponts internes, les passerelles docker et les proxys, tous porteurs d’appels d’autrui.
- L’IPv6 avec IPv4 mappée (`::ffff:198.51.100.7`) est traitée comme cette IPv4.
- Une entrée présente dans les deux listes compte comme externe.

**Les modifications s’appliquent sans redémarrage.** Le hub remarque le fichier modifié au prochain appel. Si une modification le rend invalide, **la dernière version valide reste en vigueur** : `status` passe à `invalid` et l’erreur va dans le journal. Une coquille ne doit pas faire basculer votre propre trafic en EXT. Supprimer le fichier ramène la règle par défaut.

**Vérifiez avant d’enregistrer :**

```bash
python -m aimarket_hub.ecosystem check /path/to/ecosystem.json
# code 0 ok, 2 certaines entrées refusées, 1 fichier rejeté ou absent
```

**Sur un hub Docker**, placez le fichier dans le volume de données, rendez-le lisible par l’utilisateur du hub (uid 10001) et vérifiez-le dans l’environnement du hub lui-même :

```bash
docker cp ecosystem.json modelmarket-hub:/app/data/ecosystem.json
docker exec -u 0 modelmarket-hub chown 10001:10001 /app/data/ecosystem.json
docker exec modelmarket-hub python -m aimarket_hub.ecosystem check
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'   # status ok, un nouveau loaded_at
```

Ne montez pas le fichier seul (bind mount d’un fichier unique) : un éditeur qui enregistre en renommant laisse le conteneur sur l’ancienne copie. Incluez-le dans les sauvegardes du volume de données. La dernière version valide ne survit à une modification invalide que jusqu’au prochain redémarrage. Comme modifier les comptes reclasse l’historique, `external_invocations` n’est pas monotone : un tableau de bord qui calcule des écarts verra des sauts quand le registre change.

`AIMARKET_OPERATOR_ACCOUNTS` (identifiants de comptes séparés par des virgules) fonctionne toujours et s’ajoute à `self.accounts` ; si un fichier existe aussi, le hub journalise un avertissement : gardez la liste à un seul endroit.

## Ce qui est publié

- **Chaque événement** porte `traffic_class` (`operator_self` ou `external`) et `traffic_basis`, la raison : `operator`, `account`, `address`, `wallet`, `forwarded`, `override` (une entrée `external`) ou `null` (un simple appel externe).
- **Objet.** Un événement peut porter `purpose` : une courte étiquette envoyée par l'appelant avec l'invoke (`"purpose": "feed"`) pour dire pourquoi il a fait l'appel. C'est l'étiquette de l'appelant lui-même et le hub ne la vérifie pas. Seul `[a-z][a-z0-9-]{0,23}` est conservé ; le reste est ignoré et l'appel n'est pas refusé. Vide signifie que l'appelant n'en a envoyé aucune.
- **Dans le résumé**, `summary.traffic_policy` publie :
  - combien d’entrées compte chaque liste ;
  - d’où vient la règle (`default`, `env`, `file`, `file+env`) ;
  - si le fichier s’est chargé (`absent`, `ok`, `partial`, `invalid`) et quand.
- **Jamais publiés :** les adresses, les identifiants de comptes, les portefeuilles, le chemin du fichier. Le verdict stocké, la colonne `caller_class`, ne quitte pas le hub.

```bash
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '[.events[] | {capability_id, purpose, traffic_class, traffic_basis}]'
```

## Avant de déclarer quelque chose comme vôtre

- **Un serveur** ne s’inscrit que si ses propres processus appellent ce hub dans le cadre de son écosystème. N’inscrivez jamais un hôte qui relaie les requêtes d’autrui : un autre hub, une passerelle, un exécuteur de l’usine, une plateforme de tenants ou un bac à sable où tourne le code de tiers, un `aimarket-mcp` auto-hébergé. Laissez ce serveur de côté ou mettez-le dans `external.networks`.
- **IPv6.** Pour un serveur double pile, inscrivez l’IPv4 et l’IPv6.
- **Pas l’adresse du hub lui-même.** N’inscrivez pas l’adresse publique de l’hôte du hub si cet hôte fait aussi tourner quelque chose qui relaie les requêtes d’autrui : les appels du hub vers sa propre URL publique deviendraient SELF.
- **Proxy de confiance.** `AIMARKET_TRUSTED_PROXIES` doit désigner votre vrai proxy inverse (voir le [déploiement en production](production-deployment.fr.md)). Sinon chaque appelant ressemble au proxy, et la règle d’adresse ne correspond à rien. L’adresse ne vaut que ce que vaut cette liste : tout processus qui atteint le hub *depuis* une adresse de proxy de confiance (par exemple un processus de l’hôte via une passerelle docker) peut nommer n’importe quelle adresse client. Limitez la liste au proxy inverse, et n’utilisez pas `self.networks` sur un hub que du code non fiable peut atteindre ainsi.
- **Un compte :** inscrivez ceux sur lesquels dépensent vos propres composants. Jamais un compte émis *pour* un client : sur un hub aux inscriptions fermées, tous les comptes sont émis par l’opérateur, y compris ceux des clients. Les appels payés par un mandat ou une enveloppe de tâche portent le compte qui les FINANCE : ne confiez donc jamais un mandat ou une enveloppe d’un compte inscrit à un fournisseur extérieur. N’inscrivez pas non plus le compte qu’un autre hub utilise chez vous : sa clé porte les achats d’autrui.
- **Un portefeuille :** inscrivez ceux qui paient vos tests et le trafic de l’écosystème. Jamais le portefeuille d’un hub, d’un relais ou d’un canal pair qui paie pour d’autres.

## Historique

Les lignes enregistrées avant 3.15.0 n’ont pas de verdict stocké et sont classées uniquement d’après leur étiquette. Modifier un compte les reclasse comme tout le reste. Les règles d’adresse et de portefeuille ne s’appliquent qu’aux appels enregistrés après l’ajout de l’entrée.
