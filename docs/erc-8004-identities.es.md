# Identidades ERC-8004: AIMarket Hub, HISTOR y WARDEN

[English](erc-8004-identities.md) · [Русский](erc-8004-identities.ru.md) · **Español** · [Français](erc-8004-identities.fr.md) · [中文](erc-8004-identities.zh.md)

Desde el 2026-10-01, tres de nuestros servicios son agentes registrados en el IdentityRegistry de
[ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) en Base mainnet. Cualquier agente, cartera
(wallet) o explorador de bloques que lea el registro encuentra a cada uno de ellos, quién es su
propietario y un archivo de registro que dice qué es el servicio y dónde contactarlo.

## Los tres agentes

| Agente | agentId | Qué es | Archivo de registro | Explorador |
|---|---|---|---|---|
| AIMarket Hub | `96682` | Mercado federado de capabilities de agentes, vendidas por llamada vía MCP, A2A y x402 | [aimarket-hub.json](https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json) | [8004scan](https://8004scan.io/agents/base/96682) |
| HISTOR | `96683` | Registro de transparencia de servidores MCP: lo que anunció cada servidor y cuándo cambió | [histor.json](https://modelmarket.dev/.well-known/erc-8004/histor.json) | [8004scan](https://8004scan.io/agents/base/96683) |
| WARDEN | `96684` | Cortafuegos MCP: examina las definiciones de herramientas antes de que un host se las muestre a un modelo | [warden.json](https://modelmarket.dev/.well-known/erc-8004/warden.json) | [8004scan](https://8004scan.io/agents/base/96684) |

## Lo que consta on-chain

- **Registro:** IdentityRegistry
  [`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)
  en Base mainnet (chain id 8453), `AgentIdentity` versión 2.0.0 — el despliegue canónico de
  ERC-8004, no una copia propia.
- **Propietario de los tres:** la cartera del operador
  [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a).
- **Llamada:** un `register(string agentURI)` por agente; el agentURI es la URL del archivo de
  registro.

| Agente | Transacción | Bloque |
|---|---|---|
| AIMarket Hub (`96682`) | [`0x207807…284bae`](https://basescan.org/tx/0x207807bbd9dc346e775f8db3cb2aa6b59190fe27e8b4b15d75eb9f5175284bae) | 52046664 |
| HISTOR (`96683`) | [`0xcec3de…f68fd6`](https://basescan.org/tx/0xcec3deb9a343b7257d4d83cbcb80cc3831647d0a907552a7ee14f7dcf7f68fd6) | 52046664 |
| WARDEN (`96684`) | [`0xa784ca…937fda`](https://basescan.org/tx/0xa784cacbea144ed5d9f9ac98e36ae3175f06907c3f8f7f308d5f5c7b37937fda) | 52046664 |

- **Coste:** 0.0000031 ETH de gas por los tres.
- **Verificado tras el minado:** para cada agentId, `ownerOf` devuelve la cartera del operador y
  `tokenURI`, la URL del archivo de registro.
- **No se hizo:** no se escribe nada en el ReputationRegistry, por decisión propia, y el
  ValidationRegistry no tiene un despliegue canónico en el que escribir. El razonamiento:
  [Alineación con ERC-8004](erc-8004-alignment.md).

## Archivos de registro

Cada agentURI se resuelve en un documento JSON `registration-v1` de EIP-8004 servido desde
`https://modelmarket.dev/.well-known/erc-8004/`: nombre, descripción, imagen, los endpoints del
servicio (página web, MCP, A2A, A2MCP, x402, DID o paquete npm, según el agente) y una entrada
`registrations` que indica el agentId y el registro como `eip155:8453:0x8004A169…a432`.

`https://modelmarket.dev/.well-known/agent-registration.json` enumera los tres agentIds. Es la
prueba de dominio de modelmarket.dev, que sirve los archivos de registro y los endpoints del hub y
de A2MCP: ese dominio confirma que estos registros son suyos. Los dominios web de HISTOR y WARDEN
confirman también los suyos: `https://histor.modelmarket.dev/.well-known/agent-registration.json`
lista `96683` y `https://warden.modelmarket.dev/.well-known/agent-registration.json` lista `96684`.

Un archivo puede cambiar sin una nueva transacción, porque el agentURI on-chain apunta a la URL, no
al contenido: basta con editar `build.py`, regenerar y subir.

## El hub declara su identidad

El hub del dominio apex declara su agentId dentro de su propio documento de descubrimiento firmado,
[`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json), en un bloque
`erc8004`:

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

`verified_by_this_hub: false` es deliberado. La afirmación es autodeclarada: quien la lee la
contrasta con el registro en lugar de fiarse de la palabra del hub. Cualquier operador de hub puede
hacer lo mismo con `AIMARKET_ERC8004_AGENT_ID`, `AIMARKET_ERC8004_CHAIN`, `AIMARKET_ERC8004_NETWORK`
y `AIMARKET_ERC8004_AGENT_URI` tras registrarse desde su propia cartera.

## Compruébelo usted mismo

Todo lo anterior se puede comprobar sin confiar en nosotros:

```bash
REG=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
RPC=https://mainnet.base.org
cast call $REG "ownerOf(uint256)(address)" 96682 --rpc-url $RPC    # 0x1218ff36…Ad0a
cast call $REG "tokenURI(uint256)(string)" 96682 --rpc-url $RPC    # …/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/agent-registration.json
curl -s https://modelmarket.dev/.well-known/ai-market.json | jq .erc8004
```

Para HISTOR o WARDEN, use `96683` o `96684` en las líneas `cast` y `histor.json` o `warden.json`
en el primer `curl`; el bloque `erc8004` solo existe en el documento del hub.

## Fuentes

- [`deploy/erc-8004/`](../deploy/erc-8004/): `build.py` genera los archivos de registro,
  `register.py` los registra (es un dry run salvo que reciba `--send`; se niega a continuar si la
  cartera no puede cubrir el coste en el peor caso, incluida la comisión de datos L1 de Base, omite
  cualquier agente que ya figure en `ids.json` y firma dentro del propio proceso, de modo que la
  clave nunca llega a una línea de comandos), `ids.json`, `registrations.log`.
- La entrada del 2026-10-01 en el [diario on-chain](onchain-journal.md).
- [Alineación con ERC-8004](erc-8004-alignment.md): cómo se corresponden con ERC-8004 las
  identidades, los recibos y la reputación de este protocolo, y qué deja fuera deliberadamente.
