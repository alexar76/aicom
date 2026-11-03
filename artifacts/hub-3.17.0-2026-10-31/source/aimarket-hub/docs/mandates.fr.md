# Mandats, sous-traitance et ancrage des reçus

> **English:** [mandates.md](./mandates.md) · **Русский:** [mandates.ru.md](./mandates.ru.md) · **Español:** [mandates.es.md](./mandates.es.md) · **中文:** [mandates.zh.md](./mandates.zh.md)
>
> Code : [`mandates.py`](../aimarket_hub/mandates.py) · [`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`anchoring.py`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/aimarket_provenance/anchoring.py)

Le texte normatif est [`aimarket-protocol/mandates.md`](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)
(AMD/1 pour les mandats, SUB/1 pour la sous-traitance). Cette page explique comment le faire
tourner et l'utiliser sur ce hub.

## À quoi sert chaque pièce

| Pièce | Question à laquelle elle répond | Code |
|---|---|---|
| **Mandat** | « Qui a autorisé cette dépense, jusqu'à combien, pour quoi ? » Un propriétaire signe des limites pour la clé d'un agent ; le hub les applique. L'agent ne détient jamais la clé d'API du propriétaire. | `aimarket_hub/mandates.py` |
| **Sous-traitance** | « Ce fournisseur a acheté à un autre fournisseur pendant qu'il me servait : avec l'argent de qui, et où cela apparaît-il sur ma facture ? » | `aimarket_hub/subcontract.py` |
| **Couche de financement** | Décide qui paie et sous quelles limites avant que le chemin de paiement ne s'exécute ; règle ensuite ce qu'elle a ouvert. | `aimarket_hub/invoke_funding.py` |
| **Ancrage** | « Le hub peut-il plus tard nier un reçu ou l'antidater ? » L'empreinte (digest) de chaque reçu de travail entre dans le journal public des reçus de HISTOR. | `plugins/aimarket-provenance/aimarket_provenance/anchoring.py` |

Les trois pièces qui touchent à l'argent reposent sur le **rail des crédits (credits rail)**, le
seul rail sur lequel le hub mesure lui-même l'argent. Un mandat ou une enveloppe ne voyage jamais
avec un canal de paiement, un paiement x402 ou un identifiant de visiteur du sandbox : le hub
refuse cette combinaison (`400 mandate_rail_unsupported`, ou `403 job_invalid` pour un grant)
plutôt que d'appliquer une limite qu'il ne voit pas.

## Limites monétaires et borne d’expiration

- `perCall` limite la somme réservée pour un appel, frais de routage compris lorsqu'ils s'appliquent. `perDay` utilise un **jour civil UTC**, pas une fenêtre glissante de 24 heures ; `total` est le budget global facultatif. Ce sont des plafonds monétaires, pas des compteurs de requêtes ; aucun plafond monétaire horaire n'est intégré.
- Un mandat et tous ses ancêtres ne sont utilisables que si `validFrom <= now < validUntil`. **À l'instant exact `validUntil`, il est déjà expiré.** Cela termine l'autorisation d'un nouveau travail, sans promettre l'annulation d'un travail commencé ni un remboursement on-chain.
- Activez `require_mandate=True` lors du rattachement du propriétaire du compte payeur. Enregistrer un mandat ne suffit pas à empêcher le détenteur de la clé API brute de dépenser en dehors du mandat. Le rate limit par IP/session n'est pas un budget monétaire par clé.
- Le solde prépayé et la clé API sous-jacents n'ont pas de TTL automatique. La récupération des réserves et les retours internes de crédit suivent le [cycle du crédit](credits-topup.fr.md#credit-lifecycle) ; ils ne sont ni des versements d'argent ni des garanties du contrat escrow.

## Propriétaire : financer un agent sans lui confier sa clé

```python
from aimarket_agent import AgentKey, issue_mandate, owner_link_payload
import httpx

HUB = "https://modelmarket.dev"                      # this hub's AIMARKET_HUB_URL, exactly
owner = AgentKey.from_seed_hex(OWNER_SEED_HEX)       # keep this offline
agent = AgentKey.generate()                          # this one goes to the agent

# 0. The account id your API key names.
ACCOUNT_ID = httpx.get(f"{HUB}/ai-market/v2/mandates/owners",
                       headers={"X-API-Key": API_KEY}).json()["account_id"]

# 1. Link your DID to your credit account (once). The API key proves the account, the
#    signature proves the key. require_mandate=True makes the raw API key stop paying.
httpx.post(f"{HUB}/ai-market/v2/mandates/owners", headers={"X-API-Key": API_KEY},
           json=owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True))

# 2. Issue and register a mandate for the agent key.
doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["gaia.*", "atlas.nearest.read@v1"],
                    per_call_usd=0.02, per_day_usd=1.00, total_usd=10.00, valid_days=30)
reg = httpx.post(f"{HUB}/ai-market/v2/mandates", json=doc).json()
# {"digest": "sha256-…", "status": "active", "root": "sha256-…", "root_issuer": "did:key:…", "depth": 0, …}
```

Pour que l'agent puisse ouvrir des enveloppes de sous-traitance, ajoutez
`subcontract_allowance_usd=` et `subcontract_max_depth=` (1–3) à `issue_mandate` ; sans eux, le
mandat ne peut en payer aucune.

### Ce que l'enregistrement refuse

`POST /ai-market/v2/mandates` n'exige aucune clé : le document s'authentifie lui-même. Le hub
vérifie les règles de champs de la spécification (§3.2) et la preuve, puis refuse :

| Réponse | Quand |
|---|---|
| `403 mandate_invalid` "this mandate is not addressed to …" | `audience` ne contient pas exactement l'`AIMARKET_HUB_URL` de ce hub : schéma, hôte, port et chemin (un hub monté sous `/hub` est `https://example.net/hub`), sans barre oblique finale. Le hub ne servirait jamais un tel mandat, il ne le stocke donc pas. La chaîne à utiliser est `mandates.audience` dans `/.well-known/ai-market.json`. |
| `402 mandate_unfunded` | L'émetteur racine de la chaîne n'est lié à aucun compte sur ce hub (étape 1). |
| `403 mandate_invalid` "register the parent mandate first" | Une re-délégation dont le parent n'est pas enregistré ici. |
| `403 mandate_invalid` "… already registered a different mandate with id …" | L'émetteur a déjà enregistré un autre document avec le même `id`. Un identifiant de credential désigne un seul mandat par émetteur ; émettez le nouveau avec un `id` neuf (`issue_mandate` crée un `urn:uuid:` sauf si vous passez `mandate_id=`). |
| `403 mandate_invalid` "the mandate has already expired" | `now >= validUntil` (la borne de fin est exclusive). Un mandat dont le `validFrom` est encore à venir s'enregistre et se lit comme `pending`. |
| `403 mandate_invalid` "numbers in a mandate must be integers" | Un nombre décimal quelque part, ou un entier hors de ±(2^53 − 1). Les montants sont des µUSD entiers. |
| `400 mandate_malformed` | Le corps n'est pas un objet JSON, n'a pas de forme canonique, ou sa forme canonique dépasse 16 Kio. |
| `413 mandate_malformed` | Le corps brut dépasse 20 Kio. |

Renvoyer un document déjà enregistré renvoie la même réponse : l'enregistrement est idempotent par
empreinte (`status` indique `revoked` s'il a été révoqué depuis).

**La règle des clés de la preuve.** L'objet `proof` doit porter exactement `@context`, `type`,
`cryptosuite`, `created`, `verificationMethod`, `proofPurpose` et `proofValue`, et `proof.@context`
doit être égal au `@context` du document. La raison : l'empreinte qui nomme un mandat est calculée
sur tout le document sécurisé, preuve comprise, mais `eddsa-jcs-2022` hache la configuration de
la preuve avec le `@context` *du document* à la place du sien, si bien que `proof.@context` n'est
pas couvert par la signature. Laissé libre, il permettrait à l'agent que le mandat limite de
réécrire le document et d'enregistrer copie après copie, chacune avec une empreinte nouvelle et des
compteurs de limites neufs, sans qu'aucune ne soit touchée par la révocation de l'original.
`issue_mandate` et le signataire d'ARGUS produisent exactement cette forme. Un mandat enregistré
avant la règle et qui l'enfreint est revérifié chaque fois que le hub le lit, et apparaît
désormais comme `invalid`.

### Propriétaires et `require_mandate`

Seul le **premier** propriétaire d'un compte est lié avec la seule clé d'API. Ensuite, ajouter un
deuxième DID, en délier un ou changer `require_mandate` exige aussi la signature d'un propriétaire
existant : c'est la clé d'API qui fuit, elle ne doit donc pas suffire à défaire la protection :

```python
from aimarket_agent import owner_unlink_payload

# another owner (key rotation), authorised by an existing one
owner_link_payload(new_owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True,
                   authorized_by=owner)
# switch require_mandate off for a DID that is already linked: a policy change
owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=False,
                   authorized_by=owner, action="policy")
# unlink — body of POST /ai-market/v2/mandates/owners/unlink
owner_unlink_payload(old_owner.did, hub_origin=HUB, account_id=ACCOUNT_ID, authorized_by=owner)
```

Chacune part avec la `X-API-Key` du compte. Un changement sans signature valide d'un propriétaire
reçoit `403 owner_authorization_required` ; un DID déjà lié à un autre compte reçoit
`409 owner_linked_elsewhere`. `require_mandate` est conservé par DID lié, et le compte reste
verrouillé tant que **l'un quelconque** de ses DID l'a activé : le désactiver demande un
changement de politique pour chacun de ces DID. `GET /ai-market/v2/mandates/owners` (avec la clé
d'API) liste les DID liés et leur `require_mandate`. Un propriétaire qui a perdu toutes ses clés
est rétabli par l'opérateur : le même appel avec `Authorization: Bearer $AIMARKET_ADMIN_TOKEN` (et
la clé d'API) tient lieu de signature du propriétaire.

Avec `require_mandate` activé, la clé d'API seule ne déplace plus le solde :

- une invocation ordinaire reçoit `402 mandate_required`, de même qu'une invocation qui demande
  une enveloppe de sous-traitance sans mandat ;
- une caution financée par crédits (`POST /ai-market/v2/supply/stake` avec la clé d'API et un
  `amount_usd` positif) reçoit `403` : une caution ne paierait pas un voleur, mais elle gèlerait le
  solde en garantie et l'exposerait au slashing (mécanisme de pénalité).

Un appel enfant payé par le grant d'une tâche n'est pas concerné : son argent a été autorisé lors
de l'appel racine.

### Révocation

On révoque avec `POST /ai-market/v2/mandates/revoke`, signé par n'importe quel émetteur de la
chaîne (`revoke_payload(owner, hub_origin=HUB, digest=digest)`), ou avec seulement `{"digest"}` et
la `X-API-Key` du compte de financement, comme coupe-circuit. Révoquer un mandat révoque tout ce
qui en a été re-délégué. Les réserves déjà prises se règlent normalement.

### Approbation du propriétaire au-delà d'un seuil

Ajoutez `approvalAbove` (µUSD) aux `limits` d'un mandat : tout appel qui coûterait davantage
attend votre réponse au lieu de dépenser ([spécification §5.6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)).
Les petits appels continuent sans vous ; un gros appel exige votre signature sur **cet** appel.

1. L'appel de l'agent au-delà du seuil répond `402 approval_required` avec un bloc `approval` :
   `approval_id`, `capability_id`, `amount_usd`, `max_usd` (le plafond que vous approuvez ; pour
   un appel routé il inclut les frais de routage), `body_sha256` (la requête exacte),
   `expires_at` (24 h) et `url`. Rien n'est réservé. Un appel qu'une autre limite du mandat
   (`perCall`, `perDay`, `total`, la limite quotidienne d'un produit) refuserait de toute façon
   est refusé aussitôt avec `402 mandate_limit` : on ne vous demande jamais de signer ce qui ne
   pourrait pas s'exécuter.
2. Ce qui attend : `GET /ai-market/v2/mandates/approvals?status=pending` avec la `X-API-Key` du
   compte qui finance.
3. La réponse : `POST /ai-market/v2/mandates/approvals/{approval_id}` avec
   `{"decision": "approve", "by": <votre DID>, "t", "n", "s"}` ; `s` est votre signature Ed25519
   sur les lignes `aimarket-mandate-approval/1`, l'URL de base du hub, `approval_id`, `approve`,
   le digest du mandat, `body_sha256`, `max_micro`, `t`, `n` (séparées par `\n`). Tout DID
   propriétaire du compte peut signer. La clé API seule ne peut que **refuser** (`{"decision": "deny"}`).
4. L'agent renvoie la même requête avec une preuve fraîche. Elle s'exécute une fois ;
   l'approbation est consommée avec elle, ou rendue si l'appel échoue avant d'être débité. Un
   refus tient jusqu'à l'expiration de la demande (`402 approval_denied`).

Un mandat a au plus 16 demandes en attente (`429 approval_queue_full`). Un mandat redélégué
garde le seuil de son parent et ne peut que l'abaisser. Par A2A, la Task attend en
`AUTH_REQUIRED` et avance quand vous répondez, avec une notification push au webhook de l'agent.

### Être prévenu quand un appel vous attend

Sans canal, le propriétaire n'apprend l'existence d'une demande qu'en la cherchant (étape 2).
Déclarez des canaux sur le compte qui finance et le hub y envoie chaque nouvelle demande et la
réponse qui lui est donnée. Une notification ne fait qu'informer : approuver exige toujours la
signature d'une clé du propriétaire, qu'aucun chat, canal ni ticket ne détient, et chaque
message dit comment approuver et comment refuser.

```bash
# Telegram via le bot du hub (si l'opérateur en a un) : appuyez sur Start avec lui, puis donnez l'id de votre chat
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "telegram", "chat_id": "123456789"}'
# … ou via votre propre bot : ajoutez "bot_token": "123456789:AA…"
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "slack", "webhook_url": "https://hooks.slack.com/services/T…/B…/…"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "jira", "base_url": "https://acme.atlassian.net", "email": "ops@acme.example",
       "api_token": "…", "project_key": "OPS", "issue_type": "Task"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "webhook", "url": "https://ops.acme.example/hooks/aimarket", "secret": "…"}'
# envoyer tout de suite un message de test et voir ce que le canal a répondu
curl -X POST "$HUB/ai-market/v2/mandates/notify/<channel_id>/test" -H "X-API-Key: $KEY"
```

| `kind` | Ce que vous fournissez | Ce qui arrive |
|---|---|---|
| `telegram` | `chat_id` (un nombre, ou `@canal` dont le bot est administrateur). `bot_token` pour votre propre bot ; sans lui, le bot du hub est utilisé s'il existe (`GET …/notify` le nomme dans `telegram_bot`). | Un message : quelle capacité, combien, le plafond, jusqu'à quand, comment approuver et comment refuser. En HTML, ou les mêmes mots en texte brut si Telegram refuse le balisage. |
| `slack` | `webhook_url` d'un webhook entrant (`https://hooks.slack.com/services/…` ou `/triggers/…`). | Le même texte. |
| `jira` | `base_url` de Jira Cloud (https), `email`, `api_token` (id.atlassian.com → Security → API tokens), `project_key`, `issue_type` (par défaut `Task`). | Un ticket par demande ; la réponse y est ajoutée en commentaire. |
| `webhook` | `url` (https), `secret` facultatif. | `POST` de `{"event": "mandate.approval.requested" \| "….approved" \| "….denied", "approval": {…}, "title", "text"}` avec `X-AIMarket-Event` ; avec un secret, aussi `X-AIMarket-Signature: t=<unix>,v1=<hex HMAC-SHA256 de "<t>.<body>">`. |

- `GET /ai-market/v2/mandates/notify` liste les canaux du compte avec le résultat de la
  dernière livraison de chacun. Les secrets — jeton du bot, URL Slack, jeton Jira, secret du
  webhook — sont conservés pour servir et jamais renvoyés (l'URL Slack montre ses quatre derniers
  caractères).
- `POST …/notify/{channel_id}/test` envoie aussitôt un message de test et répond `delivered` et
  ce qu'a dit le canal ; `DELETE …/notify/{channel_id}` supprime un canal. Au plus 8 par compte.
- Un canal appartient au compte qui finance : il entend parler de chaque mandat que ce compte
  finance. La clé API du compte gère les canaux — la même clé liste déjà ses demandes en attente.
- Chaque adresse est vérifiée comme toute adresse qu'un appelant donne à ce hub : https
  seulement, aucun réseau privé ni de métadonnées, résolue une fois et épinglée, sans
  redirection. La livraison se fait hors de la requête, est retentée deux fois (après 2 s et
  10 s) sans réponse, sur un 5xx ou un 429, et ne modifie jamais la demande qu'elle signale.

### Lire l'état d'un mandat

`GET /ai-market/v2/mandates/{digest}` répond à quiconque détient l'empreinte (pour une empreinte
inconnue : `404 mandate_unknown`). `status` est l'état du mandat **en tant que chaîne** : une
re-délégation dont le parent a été révoqué est inutilisable, aussi propre que paraisse sa propre
ligne :

| `status` | Signification |
|---|---|
| `active` | Utilisable maintenant. |
| `revoked` | Lui ou un ancêtre a été révoqué. `revoked_at` n'est renseigné que sur le mandat révoqué lui-même ; un descendant affiche `revoked_at: null`, avec la raison dans `status_reason`. |
| `expired` | Lui ou un ancêtre a dépassé son `validUntil`. |
| `pending` | Lui ou un ancêtre n'est pas encore valide (`validFrom` est à venir). |
| `invalid` | La chaîne ne tient pas : un ancêtre manque, un maillon enfreint les règles de restriction, ou le document stocké ne passe plus les règles de champs. |

Les autres champs sont `issuer`, `subject`, `parent`, `root`, `chain` (les empreintes, de la racine
à la feuille), `depth` (0 pour une racine), `valid_from`, `valid_until`, `revoked_at`, et
`status_reason` dès que l'état n'est pas `active`.

La consommation — `usage` : `day`, `spent_today_usd`, `per_day_usd`, `remaining_today_usd`,
`spent_total_usd`, plus `total_usd` et `remaining_total_usd` quand le mandat a une limite
`total` — est ajoutée pour deux sortes d'appelants :

- le compte de financement de la racine, avec sa `X-API-Key` ;
- toute clé de la chaîne — chaque émetteur et chaque sujet, pour qu'un propriétaire puisse suivre
  un agent auquel il a re-délégué — avec une preuve de requête (request proof) sur `GET`, un corps
  vide et le chemin de la requête :

```python
from aimarket_agent import request_proof

digest = reg["digest"]
path = f"/ai-market/v2/mandates/{digest}"
proof = request_proof(owner, hub_origin=HUB, leaf_digest=digest, body=b"", method="GET", path=path)
httpx.get(f"{HUB}{path}", headers={"X-AIMarket-Mandate-Proof": proof}).json()["usage"]
```

Une preuve qui ne se vérifie pas reçoit `401 mandate_proof_invalid` au lieu de l'état. La dépense
est enregistrée contre chaque mandat de la chaîne, donc les chiffres d'un parent incluent ce
qu'ont dépensé ses re-délégations. `day` est le jour calendaire UTC que couvre le compteur
journalier.

## Agent : payer avec le mandat

```python
from aimarket_agent import AIMarketAgent, Mandate

client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent, hub_origin=HUB))
r = client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
r["mandate"]    # {"digest", "agent", "principal", "depth"} on a delivered call
```

Chaque appel est signé sur son corps exact, le hub, la méthode et le chemin, et un nonce à usage
unique, à 300 secondes près de l'horloge du hub. Le chemin est **relatif à l'URL de base du hub** :
pour un hub publié à `https://example.net/hub`, un POST vers
`https://example.net/hub/ai-market/v2/invoke` signe `POST /ai-market/v2/invoke`, et `hub_origin` vaut
`https://example.net/hub`. `Mandate` signe ce chemin par défaut.

Ce qui revient quand le hub dit non :

- au-delà d'une limite : `402 mandate_limit`, avec `limit` qui dit laquelle (`perCall`, `perDay`,
  `total`, `perProductPerDay`, ou `subcontract.perCallAllowance` pour une enveloppe) et `mandate`
  qui nomme le mandat de la chaîne qui a refusé. `perCall` couvre tout ce que réserve un appel :
  pour un appel fédéré, son prix et les frais de routage ensemble. Le produit que compte une
  limite par produit est celui que le hub exécute, quel que soit le `product_id` saisi par
  l'appelant ;
- hors du périmètre (scope) : `403 mandate_scope` ; inconnu, expiré, révoqué ou non adressé à ce
  hub : `403 mandate_invalid` ; signature fausse, `t` périmé ou nonce réutilisé :
  `401 mandate_proof_invalid` ; un compte qui ne paie que sous mandat, atteint sans mandat :
  `402 mandate_required`.

Le SDK renvoie un refus 403 de mandat ou de tâche sous la forme
`{"refused": True, "error": …, "detail": …}`, et non `safety_blocked`, réservé à la barrière de
sécurité du contenu. Un 402, 401 ou 400 revient comme le corps du hub (`error`, `detail` et, s'ils
sont présents, `limit` / `mandate`).

Le fournisseur que le hub exécute reçoit `X-AIMarket-Agent` (le sujet de la feuille) et
`X-AIMarket-Principal` (l'émetteur racine) — qui appelle, garanti par le hub — et rien sur le
compte ni les limites. Aucun de ces en-têtes n'est envoyé sur un appel routé vers un hub pair : le
pair n'a pas vérifié le mandat.

Le même mandat paie via A2A (`POST /a2a`, [a2a.md](a2a.md)) : les en-têtes voyagent sur la requête
A2A et l'invocation part dans une seule partie `application/json` brute contenant les octets exacts
que signe la preuve — toujours pour `POST /ai-market/v2/invoke`. Une limite atteinte donne une
Task A2A `REJECTED`. Relire ses Tasks (`GetTask`, `ListTasks`) demande une preuve neuve sur
`POST /a2a` et le corps JSON-RPC. `aimarket_agent.A2AClient(HUB, mandate=…)` et `argus a2a invoke`
d'ARGUS font l'un et l'autre.

**ARGUS** paie de la même façon. `argus mandate keygen` affiche un nouveau `did:key` d'agent et son
secret ; le propriétaire émet un mandat pour ce DID et l'enregistre ; `ARGUS_AGENT_KEY` (le secret)
et `ARGUS_MANDATE_FILE` (le JSON du mandat) font basculer ARGUS dessus. `argus mandate status`
affiche l'état de la chaîne et la dépense, et
`argus mandate delegate --to <did:key> --per-call <usd> --per-day <usd>` enregistre une
re-délégation plus étroite pour un sous-agent.

## Fournisseur : engager un autre fournisseur au sein d'une tâche

> Le guide complet — les diagrammes du flux et de l'argent, où se trouve l'argent à chaque étape,
> qui porte quel risque, les enfants sur d'autres hubs, A2A, les erreurs et les notes d'opérateur —
> est [subcontracting.fr.md](subcontracting.fr.md). Cette section en est la version courte.

Chaque fournisseur que ce hub exécute via son URL d'invocation reçoit `X-AIMarket-Job` (un jeton
signé avec la clé que le hub publie comme `signer_public_key` dans son well-known, valable 60
secondes) et `X-AIMarket-Hub` (où le présenter), plus `X-AIMarket-Job-Grant` quand l'acheteur a mis
de côté une enveloppe de sous-traitance (allowance) : le grant, le secret qui autorise à dépenser
cette enveloppe. Renvoyez-les avec tout ce que vous achetez pendant que vous servez l'appel :

```python
from aimarket_agent import AIMarketAgent, JobContext

job = JobContext.from_headers(request.headers)       # None when the hub sent no token
buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
r = buyer.invoke_single("wx", "wx.read@v1", {"q": 1}, job=job)
r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

- Avec un grant (**cost-plus**), l'achat est payé sur l'enveloppe de l'acheteur et rien d'autre ne
  peut l'accompagner : ni `X-API-Key`, ni mandat, ni canal, ni paiement x402 (`403 job_invalid`) ;
  le SDK n'ajoute pas son propre paiement quand la tâche porte un grant. Tout chiffre de solde dans
  la réponse est ce qui reste de l'enveloppe, jamais le solde de l'acheteur.
- Sans grant (**prix fixe**), vous payez avec votre propre rail ; l'achat apparaît tout de même
  dans l'arbre de la tâche de l'acheteur.

### Ce que le hub refuse au sein d'une tâche

| Réponse | Quand |
|---|---|
| `403 job_invalid` | Le jeton n'est pas de ce hub ou a expiré, ou l'appel pour lequel il a été émis est déjà revenu : un fournisseur qui garde un jeton au-delà de son appel ne peut pas greffer d'achats sur une tâche dont la facture et le reçu sont déjà sortis. |
| `402 allowance_exhausted` | Le grant est fermé — il se ferme au moment où l'appel racine revient — ou ce qui reste ne couvre pas le prix. |
| `403 job_limit` | `limit` dit laquelle : `depth` (plus profond que la tâche ne le permet), `cycle` (la capability est déjà sur le chemin), `nodes` (la tâche compte déjà 64 appels, racine comprise), `children` (le nœud appelant a déjà 16 enfants). |
| `403 mandate_scope` | Un achat financé par le grant hors du périmètre du mandat racine. |
| `400 subcontract_unsupported` | Un appel au sein d'une tâche demande sa propre enveloppe ; seule la racine en fixe une. |

La profondeur qu'admet une tâche : sans enveloppe (rattachement à la tâche seul), c'est le maximum du hub, 3 ;
chaque saut paie pour lui-même, la profondeur ne borne donc que la taille de l'arbre. Avec une
enveloppe, c'est le `max_depth` de l'acheteur. Un appel enfant refusé après être entré dans
l'arbre — hors du périmètre du mandat racine, par exemple, ou avec le mandat racine révoqué entre
temps — rend ses places et apparaît dans l'arbre comme `refused`.

### Côté acheteur : une enveloppe et la facture

L'acheteur demande une enveloppe sur l'appel racine :

```python
r = client.invoke_single("brief", "brief.make@v1", {...},
                         subcontract={"allowance_usd": 0.005, "max_depth": 2})
```

`allowance_usd` doit être supérieur à 0 et au plus `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` ;
`max_depth` va de 1 à 3 (1 par défaut). Le hub réserve ensemble le prix et l'enveloppe sur le
compte de crédit de l'acheteur et, pour un appel sous mandat, contre la chaîne du mandat, dont la
feuille doit porter un bloc `subcontract` qui borne les deux. Une enveloppe sur un appel qui paie
on-chain ou par un canal, qui ne porte ni `X-API-Key` ni mandat, ou qui est routé vers un pair
reçoit `400 subcontract_unsupported` : le hub ne peut faire transiter que l'argent qu'il mesure
lui-même.

La réponse racine porte le bill of materials (nomenclature) :

```json
"subcontracting": {
  "job_id": "job_…",
  "nodes": [
    { "node": "node_…", "parent": "node_…", "depth": 1,
      "product_id": "wx", "capability_id": "wx.read@v1",
      "price_usd": 0.001, "funded_by": "allowance", "status": "captured",
      "receipt_digest": "sha256-…", "receipt_id": "urn:uuid:…" }
  ],
  "spent_from_allowance_usd": 0.001,
  "allowance_usd": 0.005,
  "spent_usd": 0.001,
  "released_usd": 0.004
}
```

- `nodes` sont les appels sous-traités ; la racine elle-même n'y figure pas. `status` vaut
  `running`, `captured`, `failed` ou `refused` ; `funded_by` vaut `allowance` ou `own`.
  `receipt_id` et `receipt_digest` désignent le reçu de travail AWR/2 de l'appel enfant.
- Le `price_usd` d'un nœud financé par l'enveloppe est ce que cet appel a réellement pris sur
  l'enveloppe (voir [les règles plus bas](#règles-faciles-à-manquer)) ;
  `spent_from_allowance_usd` en est la somme.
- `allowance_usd`, `spent_usd` et `released_usd` n'apparaissent que si une enveloppe a été fixée.
  `spent_usd` et `released_usd` sont ce que le registre a réglé ; ils valent `null` tant que le
  règlement est en attente (une libération qui a échoué et que le balayage réessaie — voir
  [Enveloppes orphelines](#enveloppes-orphelines)). `null` ne veut pas dire que rien n'a été
  dépensé.
- Le bloc figure dans la réponse de la racine, **que la racine ait livré ou non**. Un
  sous-traitant qui a livré est payé même si le fournisseur qui l'a engagé échoue ensuite
  (cost-plus : les matériaux consommés sont payés), donc une racine en échec renvoie quand même la
  facture et le `job_id` qui expliquent le débit.
- Chaque appel que le hub exécute via le point de terminaison (endpoint) d'un fournisseur reçoit un
  identifiant de tâche, si bien que sa réponse porte un bloc `subcontracting` même quand rien n'a
  été sous-traité (`"nodes": []`).

`GET /ai-market/v2/jobs/{job_id}` renvoie l'arbre plus tard : les mêmes nœuds plus celui de la
racine (`depth` 0), `spent_from_allowance_usd` et, avec une enveloppe, `allowance_usd`,
`max_depth`, `allowance_status`, puis `spent_usd` / `released_usd` une fois le règlement
enregistré. L'identifiant de tâche est une capability impossible à deviner : qui le détient peut
lire l'arbre, et le hub ne le donne qu'à l'acheteur racine et aux fournisseurs de la tâche.

Le reçu de travail AWR/2 de la racine liste le reçu de travail de chaque enfant qui a livré dans
`credentialSubject.parents` : `id` est le `receipt_id` de l'enfant, `digestSRI` son
`receipt_digest`. Le reçu de chaque enfant fait de même pour ses propres enfants, si bien que
l'arbre est engagé saut par saut, pas seulement décrit.

Limites que le hub applique quoi que demande l'acheteur : profondeur ≤ 3, 64 appels par tâche
racine comprise, 16 enfants par appel, aucun cycle (une capability déjà sur le chemin), un jeton
qui vit 60 secondes (le délai de 30 secondes du fournisseur plus 30), un grant qui meurt avec son
appel racine.

### Règles faciles à manquer

- **Un enfant sur un autre hub a besoin de `source_hub`.** Seule la racine doit s'exécuter sur ce
  hub ; un enfant peut être n'importe quelle capability que ce hub route, et son prix (et, pour un
  pair revendu, les frais de routage) est prélevé sur l'enveloppe comme celui d'une capability
  locale. Mais sans `source_hub: <l'URL du pair que renvoie /search>`, le hub cherche une
  capability locale, ne trouve que le listing du pair et répond `400` ; la tentative occupe tout
  de même l'une des 16 places d'enfant de l'appel et apparaît dans la facture comme un nœud en
  échec.
- **Le jeton de tâche et le grant ne quittent jamais ce hub.** Un enfant routé arrive chez le pair
  sans l'un ni l'autre ; le rattachement et l'argent restent là où le hub peut les mesurer.
- **Vérifiez le jeton avant de dépenser.** Votre URL d'invocation est publique. Vérifiez la
  signature avec la `signer_public_key` du hub (dans `/.well-known/ai-market.json`), que `iss` est
  bien le hub que vous servez, `exp`, que la dernière entrée de `path` est *votre* capability (le
  hub remet un jeton à chaque fournisseur qu'il exécute ; cela empêche un autre fournisseur de
  vous rejouer le sien), et ne servez chaque `node` qu'une fois. Refusez tout le reste avant
  d'acheter quoi que ce soit.
- **`max_price_usd` sur un enfant routé se compare en centimes entiers.** Le hub cote une
  capability routée à son prix plus les frais de routage arrondis au centime supérieur, donc un
  plafond inférieur à 0,01 $ refuse un enfant à 0,001 $ avec `409 price_limit_exceeded`.
- **La facture tombe juste.** Le `price_usd` d'un nœud financé par l'enveloppe est ce que cet appel
  a pris sur l'enveloppe, frais de routage compris, donc ces nœuds ont pour somme `spent_usd`, et
  `spent_usd + released_usd == allowance_usd`. Un nœud en échec dont la réserve a été libérée
  affiche 0 ; un nœud qui a tout de même coûté de l'argent (le pair a livré, puis le débit des
  frais a échoué) affiche ce qui a été pris.

### Exemple commenté : `weather.witness@v1`

[`examples/subcontract-capability`](../examples/subcontract-capability/) est un vrai fournisseur
construit sur ces règles et exploité par l'opérateur du hub. Pour un lieu, il achète
`gaia.weather.read@v1` et `gaia.air.read@v1` (produit `gaia.gateway`,
`source_hub: https://iot.modelmarket.dev`) via le hub qui l'a appelé, au sein de la tâche de
l'appelant, et répond avec les deux relevés attestés par les appareils, s'ils concordent en lieu
et en temps, et le nœud de tâche et l'empreinte du reçu de chaque enfant, signés sur la forme
canonique du hub liée à la requête. Cost-plus quand l'acheteur envoie une enveloppe (jeton +
grant, rien d'autre) ; prix fixe sinon (jeton + sa propre `X-API-Key`, sous un plafond journalier,
et sans clé il refuse).

[`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py) est l'acheteur racine :

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py            # cost-plus, allowance $0.01
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a      # the root call over A2A 1.0
```

Il vérifie deux enfants débités avec le financement attendu, `spent + released == allowance`, des
prix de nœuds dont la somme égale ce qui a été dépensé, le même arbre via
`GET /ai-market/v2/jobs/{job_id}`, et les empreintes des reçus des enfants dans
`credentialSubject.parents` du reçu racine.

Soyons clairs sur ce que cela démontre : c'est **auto-alimenté** — notre acheteur, notre service
composite, notre GAIA, des crédits internes. Chaque saut suit le chemin de code de production et
chaque affirmation est vérifiée de l'extérieur, c'est à cela qu'il sert ; ce n'est pas la preuve
que quelqu'un d'autre veut le produit. Le README de l'exemple contient le manuel de l'opérateur
(systemd, nginx, l'exemption de caution, la publication, un compte canari).
`tests/test_subcontract_example.py` fait tourner le fournisseur et le canari contre la vraie
application du hub.

## Opérateur

### Configuration

| Variable | Défaut | Effet |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | Les mandats et les enveloppes exigent le rail des crédits activé ; désactivé, un appel sous mandat ou avec enveloppe reçoit `503 mandates_unavailable`. Les jetons de tâche (rattachement) fonctionnent dans les deux cas. |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | L'URL de base publique du hub, chemin compris pour un hub monté sous un chemin. C'est l'audience qu'un mandat doit nommer et l'origine que signe chaque preuve : un hub laissé sur la valeur par défaut refuse tout mandat adressé à son nom public. |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | La plus grande enveloppe de transit qu'un appel racine peut réserver. |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | Fréquence du balayage des enveloppes orphelines (ci-dessous). `0` désactive le balayage ; une valeur inférieure à 10 est portée à 10. |
| `AIMARKET_ADMIN_TOKEN` | non défini | `Authorization: Bearer …` avec ce jeton tient lieu de signature d'un propriétaire pour les changements de propriétaires : la voie de rétablissement. |
| `AIMARKET_HISTOR_URL` | non défini | Où le plugin provenance ancre les empreintes des reçus ; non défini = ancrage désactivé. |
| `AIMARKET_HISTOR_FLUSH_S` | `30` | Fréquence à laquelle la file d'envoi (outbox) expédie les ancres en attente (l'intervalle s'allonge jusqu'à 10 min tant que HISTOR échoue ou diffère). |
| `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` | `30` | Jours pendant lesquels une ligne ancrée reste dans l'outbox ; ensuite la route d'état interroge HISTOR. `0` garde tout. |
| `AIMARKET_MANDATE_APPROVAL_TTL_S` | `86400` | Durée d'ouverture d'une demande d'approbation du propriétaire (300 s – 7 jours) ; une demande approuvée s'utilise dans la même fenêtre. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN` (ou `…_FILE`) | non défini | Le bot Telegram du hub pour les notifications d'approbation : le propriétaire ne donne alors que l'id de son chat. Sans lui, un canal Telegram exige le `bot_token` du propriétaire. Jamais journalisé. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_NAME` | non défini | Le @nom de ce bot, renvoyé par `GET /mandates/notify` pour que le propriétaire sache avec qui appuyer sur Start. |

L'image installe déjà `awr` (le plugin provenance en a besoin). Un hub installé sans lui démarre
normalement et répond `503 mandates_unavailable` aux appels sous mandat.

Les clients signent les chemins de requête relativement à `AIMARKET_HUB_URL` ; avant de vérifier
une preuve, le hub retire le préfixe de montage que le serveur ASGI indique comme `root_path`.

### Les blocs du well-known

`/.well-known/ai-market.json` indique à un client, avant qu'il n'envoie quoi que ce soit, si ce
hub applique AMD/1 et SUB/1 et avec quelles limites :

```json
"mandates": {
  "spec": "aimarket-protocol/mandates.md", "version": "AMD/1", "enabled": true,
  "audience": "https://modelmarket.dev",
  "register": "/ai-market/v2/mandates", "owners": "/ai-market/v2/mandates/owners",
  "revoke": "/ai-market/v2/mandates/revoke", "status": "/ai-market/v2/mandates/{digest}",
  "max_chain": 4
},
"subcontracting": {
  "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1", "version": "SUB/1",
  "job_tokens": true, "allowance": true, "max_allowance_usd": 1.0,
  "max_depth": 3, "max_nodes_per_job": 64, "max_children_per_node": 16,
  "jobs": "/ai-market/v2/jobs/{job_id}"
}
```

`mandates.enabled` et `subcontracting.allowance` suivent `AIMARKET_CREDITS_ENABLED` ;
`mandates.audience` est `AIMARKET_HUB_URL` sans barre oblique finale, la chaîne exacte que doit
contenir l'`audience` d'un mandat ; `max_allowance_usd` suit
`AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`.

### Enveloppes orphelines

Une enveloppe est une réserve de crédit sur le compte de l'acheteur qui devrait vivre exactement
aussi longtemps que son appel racine. Si la racine ne l'a jamais réglée — un plantage en cours
d'appel, une libération qui échouait sans cesse — l'argent resterait gelé. Le hub effectue un
balayage au démarrage, puis toutes les `AIMARKET_SUBCONTRACT_SWEEP_S` secondes : une enveloppe
dont le grant a expiré depuis plus de cinq minutes et dont la réserve est toujours tenue est
fermée, le reste est libéré, la réservation d'une enveloppe sous mandat est réglée à ce qu'ont
prélevé les enfants, et le règlement est enregistré, si bien que `spent_usd` / `released_usd` de
la tâche se remplissent. Jusqu'à 50 enveloppes par cycle ; quand il en règle, il journalise
`subcontract: settled N stale allowance(s)` au niveau WARNING. Le balayage ne tourne qu'avec le
rail des crédits activé, et jamais sur le chemin de la requête.

### Migration 038

`038_job_receipts_and_settlement` ajoute :

| Colonne | Pour |
|---|---|
| `job_nodes.work_receipt_id` | L'identifiant du reçu de travail de l'enfant, que portent l'arête `parents` du reçu parent et le `receipt_id` de la facture. |
| `job_grants.spent_micro`, `released_micro`, `settled_at` | Comment l'enveloppe a été réglée, pour que `GET /jobs/{job_id}` corresponde à la facture qu'a portée la réponse racine. |
| `mandates.credential_id`, index unique sur `(issuer, credential_id)` | Un identifiant de credential par émetteur. |
| `mandate_holds.pending_back_micro` | Un remboursement d'enfant qui arrive alors que la réservation de l'enveloppe est encore ouverte ; le règlement qui la ferme le soustrait. |

Elle s'applique au démarrage, comme toute migration du hub. 036 et 037 appartiennent à d'autres
branches ; les versions forment un ensemble, pas une suite, donc un hub peut afficher 038
appliquée avant elles. Les lignes écrites avant 038 gardent un `credential_id` vide (l'index unique
les ignore) et un `work_receipt_id` vide (leur arête `parents` nomme le nœud
`urn:aimarket:job-node:…` ; l'empreinte engage toujours les bons octets).

Les colonnes µUSD de 034 et 035 sont en `BIGINT`. Sous SQLite, c'est le même entier 64 bits
qu'avant. Un hub PostgreSQL qui a appliqué 034/035 quand elles disaient `INTEGER` a des colonnes
int4, plafonnées à 2 147,48 $, et une migration appliquée n'est pas rejouée : convertissez
`mandate_usage.spent_micro`, `mandate_holds.amount_micro`, `job_nodes.amount_micro` et
`job_grants.allowance_micro` avec `ALTER TABLE … ALTER COLUMN … TYPE BIGINT`.

Chaque appel que le hub exécute via le point de terminaison d'un fournisseur écrit une ligne dans
`job_nodes` quand il se termine, qu'il ait sous-traité ou non.

### Ancrer les reçus dans HISTOR

Avec `AIMARKET_HISTOR_URL` défini, le plugin provenance met en file l'empreinte de chaque reçu de
travail et un thread d'arrière-plan envoie la file au journal des reçus de HISTOR (ce qui est
envoyé et comment c'est réessayé : [le README du plugin](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/README.md)).
HISTOR n'accepte d'ancres que des émetteurs que son opérateur liste dans `HISTOR_RECEIPT_ISSUERS` ;
donnez donc à cet opérateur le `did:key` émetteur des reçus de ce hub. Il se lit sur n'importe quel
reçu réel : `provenance_receipt.issuer` dans une réponse d'invocation, ou `issuer.id` dans le
document du reçu :

```bash
curl -s "$HUB/ai-market/v2/p/provenance/receipt/$RECEIPT_ID" | jq -r '.issuer.id'
```

Le plugin le journalise aussi au démarrage (`Provenance issuing AWR/2 receipts as did:key:…`).
Tant que HISTOR ne le liste pas, les ancres sont refusées avec "issuer is not accepted" et restent
`pending` : le hub les réessaie avec un délai croissant pendant 30 jours au plus, donc rien ne se
perd pendant que les deux opérateurs se mettent d'accord.

`GET /ai-market/v2/p/provenance/anchor/{receipt_id}` indique où en est un reçu : `pending` (avec
`attempts` et `last_error`), `anchored` (avec `leaf_index` et un `proof_url` vers HISTOR),
`refused` (avec `last_error`), `not_queued`, ou `not_configured` quand l'ancrage est désactivé.

**Après la rétention, le journal répond.** Les lignes `anchored` quittent l'outbox une fois plus
vieilles que `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` (30 par défaut ; 0 les garde) ; les lignes
`pending` et `refused` ne sont jamais supprimées. Pour un reçu sans ligne, la route interroge
HISTOR lui-même : une preuve qui nomme ce digest sous la clé de ce hub se lit `anchored` avec
`"source": "log"` ; absent du journal, `not_queued` ; journal injoignable, `unknown`, jamais
`anchored`. Les réponses sont mémorisées (une heure, cinq minutes, trente secondes) pour que la
route publique ne puisse pas faire marteler le journal par le hub.

**Reçus émis avant l'activation de l'ancrage.** On les met en file avec leur propre heure
d'émission ; l'outbox du hub en marche les envoie comme n'importe quelle ligne :

```bash
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db --dry-run
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db
```

Seuls sont mis en file les reçus qui se vérifient, émis par la clé de provenance de ce hub et plus
récents que la fenêtre de 30 jours de HISTOR (avec une heure de marge) ; la commande refuse de
tourner sans `AIMARKET_HISTOR_URL`, donc un hub qui n'ancre pas ne publie rien. La fenêtre de
HISTOR existe pour empêcher l'antidatage : un reçu plus ancien ne peut pas être ancré avec sa
vraie heure et reste tel quel. Un ancrage rétroactif prouve que le reçu existait au moment où
HISTOR l'a journalisé, pas à l'heure d'émission que le reçu déclare.

Le trafic sur `/a2a` et `/.well-known/agent-card.json` est compté dans
`aimarket_hub_a2a_requests_total{method,result}` sur `/metrics` ; une Task d'invocation est
comptée selon l'état qu'elle a atteint (voir [a2a.md](a2a.md)).
