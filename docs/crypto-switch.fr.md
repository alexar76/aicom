# Crypto / économie on-chain — l'interrupteur principal

AICOM fonctionne **sans aucune blockchain par défaut**. Le crypto est
**DÉSACTIVÉ tant que vous ne l'activez pas explicitement**. Avec l'interrupteur
désactivé, aucun composant ne charge de portefeuille (wallet), ne contacte une
chaîne/RPC, n'ouvre de canal de paiement, ne renvoie `402 Payment Required`, ne
vérifie de transaction on-chain ni ne règle UNI/loterie. Tout continue de
fonctionner — les capacités sont servies sur un palier gratuit, la signature de
fédération et la comptabilité interne restent opérationnelles — sans jamais
toucher à l'argent.

## Ce que vous voyez dans l'Alien Monitor

Le moniteur affiche l'état **réel**, jamais un état falsifié :

| Mode | Contexte de chaîne | Nœuds on-chain (chain · escrow · NFT · ACEX · lottery) |
|------|--------------------|--------------------------------------------------------|
| **TEST** | jamais | scripté/simulé |
| **UNI** | **toujours** (Anvil local privé — jamais Base) | en direct sur la chaîne locale |
| **LIVE**, crypto **OFF** | aucun | **grisés / désactivés** + badge « Blockchain réelle désactivée dans les paramètres » |
| **LIVE**, crypto **ON** | Base mainnet | en direct sur Base, allumés |

Cela reflète le contrat côté agent
`shouldBuildChainContext(mode, cryptoEnabled)`
(`argus/src/ecosystem/networks.ts`) : `uni → toujours`, `live → uniquement si
crypto activé`, `test → jamais`. Invariant de sécurité :
`shouldBuildChainContext("live", false) === false`.

## Comment activer l'économie on-chain réelle

1. **Interrupteur principal.** Définissez `AIFACTORY_CRYPTO_ENABLED=1` dans le
   `.env` de l'écosystème. Valeurs vraies : `1`, `true`, `yes`, `on`. Tout le
   reste (ou non défini) = OFF.
2. **Config par composant.** Chaque composant a toujours besoin de sa propre
   config réelle : endpoints RPC, adresses de destinataire/contrat et clés de
   portefeuille.
3. **Verrouillages de production.** En production, les gates fail-closed
   existants d'`AIFACTORY_PROD` s'appliquent toujours par-dessus l'interrupteur.
4. **Alien Monitor en particulier.** Déployez-le en mode LIVE pour qu'il se lie
   à la chaîne réelle :
   ```bash
   ALIEN_MODE=real AIFACTORY_CRYPTO_ENABLED=1 ./scripts/deploy_alien_monitor.sh --live
   ```
   En mode UNI, le moniteur utilise toujours sa chaîne Anvil locale privée et ne
   touche jamais Base, quel que soit cet interrupteur.

## Crypto activé n'est pas la même chose que vendre

L'interrupteur maître active la machinerie on-chain. Il ne met **pas** à lui seul un
prix sur une capacité fédérée : c'est un second interrupteur, distinct.

> [!WARNING]
> **`AIMARKET_SELLS_FOR` n'est pas définie par défaut, et la définir rend payantes
> d'un coup 42 capacités aujourd'hui gratuites.** Non définie, le Hub ne facture
> rien pour une invocation fédérée : aucun canal exigé, aucune réservation prise,
> aucune commission de routage perçue. Avec un préfixe d'URL de pair listé dedans,
> chaque capacité de ce pair devient tarifée et une invocation sans
> `X-Payment-Channel` reçoit `402 payment_required` ; les appelants gratuits
> existants — y compris tout agent, pont ou client MCP qui les utilise déjà —
> commencent à échouer dans la minute. Il n'y a ni déploiement partiel ni période de
> grâce.

Vendre pour le compte d'un pair doit être **déclaré**, non déduit : un pair qui
facture hors bande répond aussi `200`, donc traiter « le pair ne nous a rien
facturé » comme « nous pouvons facturer » ferait payer l'acheteur deux fois.

Le côté oracle a son propre interrupteur (`ORACLE_PAID_TIER_SECRET`), et il doit être
défini **en premier** : sinon le Hub exige un paiement pour un travail que l'oracle
refuserait encore au-dessus de son plafond gratuit. Séquence complète et
justification : [free-and-paid-tiers](free-and-paid-tiers.fr.md).

## Sécurité

N'activez le crypto que si vous comptez faire tourner une **économie on-chain
réelle** (fonds réels sur Base). Le laisser désactivé est le comportement par
défaut sûr et maintient tout l'écosystème pleinement fonctionnel sur le palier
gratuit — voir [free-and-paid-tiers](free-and-paid-tiers.fr.md) pour savoir
exactement ce que ce palier comprend et ce qui le borne.
