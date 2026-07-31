# Localization glossary — canonical terms (EN · RU · ES · FR · ZH)

**Purpose.** One canonical rendering per domain term, per language, so translations stay
consistent across the docs, landings and UI. **English is the source of truth**; the other
columns are the agreed target renderings. When translating or reviewing, match this table —
do not invent variants (the audit found *escrow* rendered 6 different ways in one document).

**Scope of the language set.** Docs + UI are localized to **en / ru / es** in full; **fr / zh**
are being rolled out. (The Argus landing ships a wider 25-language set; its short marketing
strings follow this glossary where the terms appear.)

**Rules of thumb**
- **Never translate** code, identifiers, CLI, env vars, URLs, and product/brand names
  (`ARGUS`, `WARDEN`, `AI-Factory`, `Hub`, `Mesh`, `Metis`, `AIMarketEscrow`, `aimarket-agent`,
  `slash_sync.py`, `USDC`, `Base`, `MCP`, `NFT`, `MIT`, …). Class/contract names keep their
  Latin form even when the common noun is translated (e.g. RU prose «эскроу», but the contract
  is still `AIMarketEscrow`).
- Keep **one** rendering per term per language, everywhere.
- `slashing` stays the English word in ES/FR (that is how the crypto press writes it); it is
  transliterated in RU/ZH. See per-row notes.

## Core terms

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| slashing | слэшинг | slashing | slashing | 罚没 | ES/FR keep the English word (gloss once: ES «(recorte de la garantía)», FR «(mécanisme de pénalité)»). |
| staking | стейкинг | staking | staking (jalonnement) | 质押 | |
| stake / bond (collateral) | залог | garantía | caution / dépôt de garantie | 保证金 | The posted collateral. Not to be confused with an LLM/consumer *budget*. |
| escrow | эскроу | depósito en garantía | séquestre / dépôt fiduciaire | 托管 | Gloss once: ES/FR add «(escrow)». Pick ONE per doc. Contract stays `AIMarketEscrow`. |
| proof-of-misbehavior | доказательство нарушения (proof-of-misbehavior) | prueba de infracción (proof-of-misbehavior) | preuve de faute (proof-of-misbehavior) | 违规证明 (proof-of-misbehavior) | No settled translation — keep English in parentheses. |
| dispute | спор | disputa | litige | 争议 | |
| settlement / settle | расчёт | liquidación | règlement | 结算 | |
| receipt | квитанция | recibo | reçu | 收据 | Signed receipt of an invoke. |
| reputation | репутация | reputación | réputation | 声誉 | |
| oracle | оракул | oráculo | oracle | 预言机 | |
| hub | хаб | hub | hub | 枢纽 (Hub) | Product name `Hub` stays Latin. |
| mesh (service mesh) | меш (сервис-меш) | malla (mesh) | maillage (mesh) | 网格 (服务网格) | Product name `Service Mesh` stays Latin. |
| payment channel | платёжный канал | canal de pago | canal de paiement | 支付通道 | |
| on-chain | ончейн | on-chain / en cadena | on-chain | 链上 | |
| off-chain | офчейн | off-chain / fuera de cadena | off-chain | 链下 | |
| provider (supply side) | поставщик | proveedor | fournisseur | 提供方 | Market role. NB: an *LLM provider* (infra) is a different sense — keep contextual. |
| consumer (demand side) | потребитель | consumidor | consommateur | 消费方 | |
| agent | агент | agente | agent | 智能体 | «代理» also seen; prefer 智能体 for AI agents. |
| verify / verification | верификация | verificación | vérification | 验证 | |
| marketplace | маркетплейс | marketplace | place de marché | 交易市场 | |
| wallet | кошелёк | cartera (wallet) | portefeuille (wallet) | 钱包 | |
| self-hosted | самостоятельно размещаемый / на своём сервере | autoalojado | auto-hébergé | 自托管 | |
| open source | открытый код | código abierto | open source | 开源 | FR/IT/NL keep «open source»; RU/ES/ZH translate. |
| firewall | файрвол | firewall / cortafuegos | pare-feu | 防火墙 | WARDEN context. Product name `WARDEN` stays Latin. |
| token | токен | token | jeton (token) | 令牌 (LLM) / 代币 (crypto) | **Ambiguous**: an LLM *token* (令牌/token) vs a crypto *token* (代币). Disambiguate by context. |
| budget (per-task) | бюджет | presupuesto | budget | 预算 | The token+dollar spend cap per task. |
| receipt/audit chain | цепочка аудита | cadena de auditoría | chaîne d'audit | 审计链 | |
| federated / federation | федеративный / федерация | federado / federación | fédéré / fédération | 联邦 | Cross-hub. |

## Sources (web-verified renderings)

- Slashing / staking / escrow: [Ledger — staking glossary](https://www.ledger.com/academy/ledgers-staking-glossary), [Journal du Coin — slashing (FR)](https://journalducoin.com/lexique/slashing/), [Cryptoast — lexique (FR)](https://cryptoast.fr/lexique/), [learnblockchain.cn — Slashing 罚没](https://learnblockchain.cn/article/16557), [腾讯新闻 — POS 罚没](https://news.qq.com/rain/a/20230131A032HG00), [MetaMask 质押 (zh)](https://learn.metamask.io/zh-CN/lessons/what-is-staking)
- Oracle / réputation / litige / on-chain (FR): [Oracle de blockchain — Wikipédia (FR)](https://fr.wikipedia.org/wiki/Oracle_de_blockchain), [Cryptoast — lexique](https://cryptoast.fr/lexique/)
- 保证金 / 预言机 / 声誉 / 支付通道 / 链上 (ZH): [Chainlink 白皮书 (中文)](https://research.chain.link/whitepaper-v1-chinese.pdf), [learnblockchain.cn 区块链术语中英对照](https://wiki.learnblockchain.cn/bitcoin/en-zh.html)
- self-hosted per language (it/nl/hr/id): [IlSoftware.it — software self-hosted](https://www.ilsoftware.it/focus/i-migliori-software-self-hosted-del-2025-tool-e-app-open-source-che-devi-conoscere/), [Zelfhosting — Wikipedia (NL)](https://nl.wikipedia.org/wiki/Zelfhosting), [Otvoreni kod — Wikipedija (HR)](https://hr.wikipedia.org/wiki/Otvoreni_kod), [Rumahweb — Self-Hosted (ID)](https://www.rumahweb.com/journal/self-hosted/)
- proof-of-misbehavior (no settled translation; kept English): [Chainlink — What Is Slashing](https://chain.link/article/slashing), [ethereum.org — PoS rewards and penalties](https://ethereum.org/developers/docs/consensus-mechanisms/pos/rewards-and-penalties/)

---
*Maintainers: extend this table before introducing a new domain term in any language. If a term
here proves wrong for a locale, fix it **here first**, then propagate — this file is the source
of truth for terminology.*
