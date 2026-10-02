# Identités ERC-8004 : AIMarket Hub, HISTOR et WARDEN

[English](erc-8004-identities.md) · [Русский](erc-8004-identities.ru.md) · [Español](erc-8004-identities.es.md) · **Français** · [中文](erc-8004-identities.zh.md)

Depuis le 2026-10-01, trois de nos services sont des agents enregistrés dans l’IdentityRegistry
[ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) sur le mainnet de Base. Tout agent,
portefeuille (wallet) ou explorateur qui lit le registre y trouve chacun d’eux, son propriétaire et
un fichier d’enregistrement qui dit ce qu’est le service et où le joindre.

## Les trois agents

| Agent | agentId | Ce que c’est | Fichier d’enregistrement | Explorateur |
|---|---|---|---|---|
| AIMarket Hub | `96682` | Marché fédéré de capabilities d’agents, vendues à l’appel via MCP, A2A et x402 | [aimarket-hub.json](https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json) | [8004scan](https://8004scan.io/agents/base/96682) |
| HISTOR | `96683` | Journal de transparence des serveurs MCP : ce que chaque serveur a annoncé, et quand cela a changé | [histor.json](https://modelmarket.dev/.well-known/erc-8004/histor.json) | [8004scan](https://8004scan.io/agents/base/96683) |
| WARDEN | `96684` | Pare-feu MCP : analyse les définitions d’outils avant qu’un hôte ne les montre à un modèle | [warden.json](https://modelmarket.dev/.well-known/erc-8004/warden.json) | [8004scan](https://8004scan.io/agents/base/96684) |

## Trace on-chain

- **Registre :** IdentityRegistry
  [`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)
  sur le mainnet de Base (chain id 8453), `AgentIdentity` version 2.0.0 — le déploiement canonique
  d’ERC-8004, et non une copie déployée par nos soins.
- **Propriétaire des trois :** le portefeuille de l’opérateur
  [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a).
- **Appel :** un `register(string agentURI)` par agent ; l’agentURI est l’URL du fichier
  d’enregistrement.

| Agent | Transaction | Bloc |
|---|---|---|
| AIMarket Hub (`96682`) | [`0x207807…284bae`](https://basescan.org/tx/0x207807bbd9dc346e775f8db3cb2aa6b59190fe27e8b4b15d75eb9f5175284bae) | 52046664 |
| HISTOR (`96683`) | [`0xcec3de…f68fd6`](https://basescan.org/tx/0xcec3deb9a343b7257d4d83cbcb80cc3831647d0a907552a7ee14f7dcf7f68fd6) | 52046664 |
| WARDEN (`96684`) | [`0xa784ca…937fda`](https://basescan.org/tx/0xa784cacbea144ed5d9f9ac98e36ae3175f06907c3f8f7f308d5f5c7b37937fda) | 52046664 |

- **Coût :** 0.0000031 ETH de gas pour les trois.
- **Vérifié après minage :** pour chaque agentId, `ownerOf` renvoie le portefeuille de l’opérateur
  et `tokenURI` renvoie l’URL du fichier d’enregistrement.
- **Non fait :** rien n’est écrit dans le ReputationRegistry, par choix, et le ValidationRegistry
  n’a aucun déploiement canonique où écrire. Le raisonnement :
  [alignement sur ERC-8004](erc-8004-alignment.md).

## Fichiers d’enregistrement

Chaque agentURI pointe vers un document JSON EIP-8004 `registration-v1` servi depuis
`https://modelmarket.dev/.well-known/erc-8004/` : nom, description, image, les points de
terminaison (endpoints) du service (page web, MCP, A2A, A2MCP, x402, DID ou paquet npm, selon l’agent) et
une entrée `registrations` qui donne l’agentId et le registre sous la forme
`eip155:8453:0x8004A169…a432`.

`https://modelmarket.dev/.well-known/agent-registration.json` liste les trois agentIds. C’est la
preuve de domaine pour modelmarket.dev, qui sert les fichiers d’enregistrement et les points de
terminaison du hub et d’A2MCP : ce domaine confirme que ces enregistrements sont bien les siens.
Les domaines web de HISTOR et de WARDEN confirment aussi les leurs :
`https://histor.modelmarket.dev/.well-known/agent-registration.json` liste `96683` et
`https://warden.modelmarket.dev/.well-known/agent-registration.json` liste `96684`.

Un fichier peut changer sans nouvelle transaction, car l’agentURI on-chain pointe vers l’URL et non
vers le contenu : modifier `build.py`, régénérer, mettre en ligne.

## Le hub déclare son identité

Le hub apex indique son agentId dans son propre document de découverte signé,
[`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json), dans un bloc
`erc8004` :

```json
{
  "agent_id": "96682",
  "chain": "eip155:8453",
  "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  "reputation_registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
  "agent_uri": "https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json",
  "verified_by_this_hub": false
}
```

`verified_by_this_hub: false` est délibéré. L’affirmation est auto-déclarée : un lecteur la
confronte au registre au lieu de croire le hub sur parole. Tout opérateur de hub peut faire de même
avec `AIMARKET_ERC8004_AGENT_ID`, `AIMARKET_ERC8004_CHAIN`, `AIMARKET_ERC8004_NETWORK` et
`AIMARKET_ERC8004_AGENT_URI`, après s’être enregistré depuis son propre portefeuille.

## Vérifiez par vous-même

Tout ce qui précède se vérifie sans avoir à nous faire confiance :

```bash
REG=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
RPC=https://mainnet.base.org
cast call $REG "ownerOf(uint256)(address)" 96682 --rpc-url $RPC    # 0x1218ff36…Ad0a
cast call $REG "tokenURI(uint256)(string)" 96682 --rpc-url $RPC    # …/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/agent-registration.json
curl -s https://modelmarket.dev/.well-known/ai-market.json | jq .erc8004
```

Pour HISTOR ou WARDEN, mettez `96683` ou `96684` dans les lignes `cast`, et `histor.json` ou
`warden.json` dans le premier `curl` ; le bloc `erc8004` n’existe que dans le document du hub.

## Sources

- [`deploy/erc-8004/`](../deploy/erc-8004/) : `build.py` écrit les fichiers d’enregistrement,
  `register.py` les enregistre (à blanc tant que `--send` n’est pas passé ; il refuse si le
  portefeuille ne peut pas couvrir le coût dans le pire des cas, frais de données L1 de Base
  compris, saute tout agent déjà présent dans `ids.json` et signe dans le processus, si bien que la
  clé n’apparaît jamais sur une ligne de commande), `ids.json`, `registrations.log`.
- L’entrée du 2026-10-01 du [journal on-chain](onchain-journal.md).
- [Alignement sur ERC-8004](erc-8004-alignment.md) : comment les identités, les reçus et la
  réputation de ce protocole correspondent à ERC-8004, et ce qu’il laisse délibérément de côté.
